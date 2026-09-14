"""Versioned PPO training pipeline for fixed-speed humanoid policies.

Examples:
  python train_ppo.py --profile walk_0p4_fixed_v1
  python train_ppo.py --profile walk_0p7_fixed_v1 --smoke

每次 run 寫入 rl/artifacts/<run-id>/；若目錄已存在則 fail closed，永不覆寫
既有 checkpoint 或 ppo_walk_final.zip。Smoke 只驗證 pipeline，不是 policy
performance evidence。
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rl.action_interface_v7 import (
    PROTOCOL_ID as V7_PROTOCOL_ID,
    PROTOCOL_PATH as V7_PROTOCOL_PATH,
    load_v7_protocol,
    resolve_v7_action_interface,
)
from rl.policy_registry import resolve_policy, sha256_file


RL_DIR = Path(__file__).resolve().parent
PROFILE_PATH = RL_DIR / "training_profiles.json"

# SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1 reuses the pilot's arms, plant, PPO
# geometry and warm start, and differs only in the training seed. The pilot's
# own guard pins seed_base to 8700, so a second, mutually exclusive frozen
# identity is required: without it a v7 arm can only ever be trained on one
# seed and independent training-seed variance cannot be measured at all.
SEEDVAR_PROTOCOL_PATH = RL_DIR / "training_seed_variance_protocol.json"
SEEDVAR_PROTOCOL_ID = "SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1"
SEEDVAR_PROFILE_SUFFIX = "_seedvar"
SOURCE_FILES = (
    Path(__file__).resolve(),
    RL_DIR / "humanoid_env.py",
    RL_DIR / "training_profiles.json",
    RL_DIR / "action_interface_v7.py",
    RL_DIR / "v7_action_interface_pilot_protocol.json",
    RL_DIR / "eval_policy.py",
    RL_DIR.parent / "controller_rl.py",
    RL_DIR.parent / "motion_tasks.py",
    RL_DIR.parent / "model_builder.py",
    RL_DIR.parent / "config_schema.py",
)


# TRACKED-LINEAGE-TRAINING-V1 is the third mutually exclusive identity. It is
# not a v7 arm: it trains from scratch on the v5 environment, so the pilot and
# seedvar guards cannot express it. Two things it needs that no existing branch
# provides: a training seed resolved from its own frozen protocol, and a
# checkpoint_interval small enough that a 2M-step run retains intermediate
# checkpoints at all -- the full-run default of 2_000_000 below saves none,
# which is exactly the lineage gap ROADMAP section 9 item 2 exists to close.
TRACKED_LINEAGE_PROTOCOL_PATH = RL_DIR / "tracked_lineage_training_protocol.json"
TRACKED_LINEAGE_PROTOCOL_ID = "TRACKED-LINEAGE-TRAINING-V1"
TRACKED_LINEAGE_PROFILE_PREFIX = "stand_start_walk_stop_0p7_tracked_lineage_b1_r"

# TRACKED-LINEAGE-TRAINING-V2 is the fourth identity. It is V1's line continued,
# not a new one: each replicate resumes from its own V1 retained checkpoint. V1's
# branch below is untouched and still refuses resume -- V1 is executed evidence
# and its rules do not move. Two things V2 needs that V1's branch forbids: a
# REQUIRED --resume-from pinned by digest, and a resume source that lives in
# version control rather than under the gitignored artifacts directory.
TRACKED_LINEAGE_V2_PROTOCOL_PATH = RL_DIR / "tracked_lineage_training_v2_protocol.json"
TRACKED_LINEAGE_V2_PROTOCOL_ID = "TRACKED-LINEAGE-TRAINING-V2"
TRACKED_LINEAGE_V2_PROFILE_PREFIX = "stand_start_walk_stop_0p7_tracked_lineage_b2_r"
TRACKED_LINEAGE_EVIDENCE_DIR = RL_DIR.parent / "tracked_lineage_evidence"


def load_tracked_lineage_protocol(path: Path = TRACKED_LINEAGE_PROTOCOL_PATH) -> dict:
    """Load the frozen tracked-lineage protocol; the seed schedule lives there.

    Same reasoning as the seed-variance loader: the schedule is deliberately not
    restated in the training profile, because two sources for one frozen list is
    how they drift apart.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("protocol_id") != TRACKED_LINEAGE_PROTOCOL_ID:
        raise ValueError("TRACKED_LINEAGE_PROTOCOL_ID_MISMATCH")
    design = payload.get("training_design", {})
    seeds = design.get("training_seeds")
    if not isinstance(seeds, list) or not seeds:
        raise ValueError("TRACKED_LINEAGE_PROTOCOL_MISSING_TRAINING_SEEDS")
    if len(seeds) != design.get("replicate_count"):
        raise ValueError("TRACKED_LINEAGE_PROTOCOL_SEED_COUNT_MISMATCH")
    return payload


def tracked_lineage_training_seeds(path: Path = TRACKED_LINEAGE_PROTOCOL_PATH) -> list[int]:
    design = load_tracked_lineage_protocol(path)["training_design"]
    return [int(seed) for seed in design["training_seeds"]]


def tracked_lineage_checkpoint_interval(path: Path = TRACKED_LINEAGE_PROTOCOL_PATH) -> int:
    """The retention interval is the protocol's to set, not the driver's.

    Without this the full-run branch pins 2_000_000 and a 2M-step run ends with
    no intermediate checkpoint, so there is no lineage to version-control.
    """
    interval = load_tracked_lineage_protocol(path)["training_design"]["checkpoint_interval"]
    if not isinstance(interval, int) or interval <= 0:
        raise ValueError("TRACKED_LINEAGE_PROTOCOL_CHECKPOINT_INTERVAL_INVALID")
    return interval


def tracked_lineage_replicate_index(profile_id: str) -> int:
    """Derive the replicate index from the profile id.

    This line has one profile per replicate, so the index is already part of the
    frozen profile identity. Deriving it here rather than accepting
    --replicate-index keeps the seed unreachable from the command line: there is
    no invocation that can pair a profile with another replicate's seed.
    """
    if not profile_id.startswith(TRACKED_LINEAGE_PROFILE_PREFIX):
        raise ValueError("TRACKED_LINEAGE_PROFILE_ID_MISMATCH")
    suffix = profile_id[len(TRACKED_LINEAGE_PROFILE_PREFIX):]
    if not suffix.isdigit():
        raise ValueError("TRACKED_LINEAGE_PROFILE_ID_MISMATCH")
    return int(suffix)


def load_tracked_lineage_v2_protocol(path: Path = TRACKED_LINEAGE_V2_PROTOCOL_PATH) -> dict:
    """Load the frozen V2 protocol; the resume sources and budget live there."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("protocol_id") != TRACKED_LINEAGE_V2_PROTOCOL_ID:
        raise ValueError("TRACKED_LINEAGE_V2_PROTOCOL_ID_MISMATCH")
    sources = (payload.get("tracked_warm_start") or {}).get("sources")
    design = payload.get("training_design", {})
    if not isinstance(sources, dict) or not sources:
        raise ValueError("TRACKED_LINEAGE_V2_PROTOCOL_MISSING_RESUME_SOURCES")
    if len(sources) != design.get("replicate_count", len(sources)):
        raise ValueError("TRACKED_LINEAGE_V2_PROTOCOL_RESUME_SOURCE_COUNT_MISMATCH")
    return payload


def tracked_lineage_v2_replicate_index(profile_id: str) -> int:
    if not profile_id.startswith(TRACKED_LINEAGE_V2_PROFILE_PREFIX):
        raise ValueError("TRACKED_LINEAGE_V2_PROFILE_ID_MISMATCH")
    suffix = profile_id[len(TRACKED_LINEAGE_V2_PROFILE_PREFIX):]
    if not suffix.isdigit():
        raise ValueError("TRACKED_LINEAGE_V2_PROFILE_ID_MISMATCH")
    return int(suffix)


def tracked_lineage_v2_resume_source(replicate_index: int) -> dict:
    """The V1 checkpoint this replicate must resume from, by digest.

    Pinned in the protocol rather than discovered on disk, so a run cannot
    quietly continue from a different checkpoint than the one frozen.
    """
    sources = load_tracked_lineage_v2_protocol()["tracked_warm_start"]["sources"]
    entry = sources.get(str(replicate_index))
    if entry is None:
        raise ValueError("TRACKED_LINEAGE_V2_RESUME_SOURCE_MISSING")
    return entry


def tracked_lineage_v2_checkpoint_interval(path: Path = TRACKED_LINEAGE_V2_PROTOCOL_PATH) -> int:
    interval = load_tracked_lineage_v2_protocol(path)["training_design"]["checkpoint_interval"]
    if not isinstance(interval, int) or interval <= 0:
        raise ValueError("TRACKED_LINEAGE_V2_PROTOCOL_CHECKPOINT_INTERVAL_INVALID")
    return interval


def load_seedvar_protocol(path: Path = SEEDVAR_PROTOCOL_PATH) -> dict:
    """Load the frozen seed-variance protocol; the seed schedule lives there.

    The schedule is deliberately not restated in the training profile: two
    sources for the same frozen list is how they drift apart.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("protocol_id") != SEEDVAR_PROTOCOL_ID:
        raise ValueError("SEEDVAR_PROTOCOL_ID_MISMATCH")
    design = payload.get("training_design", {})
    seeds = design.get("training_seeds")
    if not isinstance(seeds, list) or not seeds:
        raise ValueError("SEEDVAR_PROTOCOL_MISSING_TRAINING_SEEDS")
    if len(seeds) != design.get("replicate_count"):
        raise ValueError("SEEDVAR_PROTOCOL_SEED_COUNT_MISMATCH")
    return payload


def seedvar_training_seeds(path: Path = SEEDVAR_PROTOCOL_PATH) -> list[int]:
    return [int(seed) for seed in load_seedvar_protocol(path)["training_design"]["training_seeds"]]


class ProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TrainingProfile(ProfileModel):
    profile_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    speed_mps: float = Field(gt=0.0)
    step_length_m: float = Field(gt=0.0)
    duty: float = Field(gt=0.0, lt=1.0)
    clearance_m: float = Field(ge=0.0)
    planned_timesteps: int = Field(gt=0)
    parallel_envs: int = Field(gt=0)
    seed_base: int = Field(ge=0)
    status: str
    environment_id: Literal[
        "fixed_walk_v1",
        "motion_task_command_v1",
        "motion_task_command_envelope_v2",
        "motion_task_path_efficiency_v3",
        "motion_task_path_stop_v4",
        "motion_task_phase_observable_v5",
        "motion_task_substep_saturation_v6",
        "motion_task_v7_reward_only",
        "motion_task_v7_reduced_joint_envelope",
        "motion_task_v7_filtered_action",
    ] = "fixed_walk_v1"
    task_id: str | None = None
    warm_start_policy_id: str | None = None
    pilot_protocol_id: str | None = None
    seedvar_protocol_id: str | None = None
    tracked_lineage_protocol_id: str | None = None
    pilot_arm_id: Literal[
        "V7A_REWARD_ONLY",
        "V7B_REDUCED_JOINT_ENVELOPE",
        "V7C_FILTERED_ACTION",
    ] | None = None

    def validate_tracked_lineage_v2_identity(self):
        """Fail closed on any drift from the frozen TRACKED-LINEAGE-TRAINING-V2 design.

        V2 continues V1's replicates, so almost everything is checked against the
        V2 protocol's copy of V1's values: same environment, same task, same
        seeds in the same order, same parallel_envs. What differs is the budget,
        which here is an INCREMENT rather than a total.
        """
        design = load_tracked_lineage_v2_protocol()["training_design"]
        unchanged = load_tracked_lineage_v2_protocol()["unchanged_from_v1"]
        index = tracked_lineage_v2_replicate_index(self.profile_id)
        seeds = [int(seed) for seed in design["training_seeds"]]
        if not 0 <= index < len(seeds):
            raise ValueError("TRACKED_LINEAGE_V2_REPLICATE_INDEX_OUT_OF_RANGE")
        if self.environment_id != unchanged["environment_id"]:
            raise ValueError("TRACKED_LINEAGE_V2_ENVIRONMENT_ID_MISMATCH")
        if self.task_id != unchanged["task_id"]:
            raise ValueError("TRACKED_LINEAGE_V2_TASK_ID_MISMATCH")
        # The start is a RESUME, not a warm start: warm_start_policy_id stays
        # null and the resume source is pinned by digest in the protocol.
        if self.warm_start_policy_id is not None:
            raise ValueError("TRACKED_LINEAGE_V2_WARM_START_FORBIDDEN")
        if self.seed_base != seeds[index]:
            raise ValueError("TRACKED_LINEAGE_V2_TRAINING_SEED_MISMATCH")
        if self.parallel_envs != int(unchanged["parallel_envs"]):
            raise ValueError("TRACKED_LINEAGE_V2_PARALLEL_ENVS_MISMATCH")
        # planned_timesteps carries the INCREMENT for this line.
        if self.planned_timesteps != int(design["increment_planned_timesteps"]):
            raise ValueError("TRACKED_LINEAGE_V2_INCREMENT_MISMATCH")
        return self

    def validate_tracked_lineage_identity(self):
        """Fail closed on any drift from the frozen TRACKED-LINEAGE-TRAINING-V1 design.

        Every value compared here is read from the frozen protocol rather than
        restated, so a profile cannot quietly disagree with the document that
        governs it.
        """
        if self.tracked_lineage_protocol_id == TRACKED_LINEAGE_V2_PROTOCOL_ID:
            return self.validate_tracked_lineage_v2_identity()
        if self.tracked_lineage_protocol_id != TRACKED_LINEAGE_PROTOCOL_ID:
            raise ValueError("TRACKED_LINEAGE_PROFILE_MISSING_FROZEN_IDENTITY")
        design = load_tracked_lineage_protocol()["training_design"]
        index = tracked_lineage_replicate_index(self.profile_id)
        seeds = [int(seed) for seed in design["training_seeds"]]
        if not 0 <= index < len(seeds):
            raise ValueError("TRACKED_LINEAGE_REPLICATE_INDEX_OUT_OF_RANGE")
        if self.environment_id != design["environment_id"]:
            raise ValueError("TRACKED_LINEAGE_ENVIRONMENT_ID_MISMATCH")
        if self.task_id != design["task_id"]:
            raise ValueError("TRACKED_LINEAGE_TASK_ID_MISMATCH")
        # Scratch is the whole point of this line (specification section 3), so
        # a warm start is not a configuration choice here but a contradiction:
        # it would carry CONDITIONAL_ON_FIXED_WARM_START straight back in.
        if self.warm_start_policy_id is not None:
            raise ValueError("TRACKED_LINEAGE_WARM_START_FORBIDDEN")
        if self.seed_base != seeds[index]:
            raise ValueError("TRACKED_LINEAGE_TRAINING_SEED_MISMATCH")
        if self.parallel_envs != design["parallel_envs"]:
            raise ValueError("TRACKED_LINEAGE_PARALLEL_ENVS_MISMATCH")
        if self.planned_timesteps != design["planned_timesteps_per_replicate"]:
            raise ValueError("TRACKED_LINEAGE_TRAINING_BUDGET_MISMATCH")
        gait = design["gait"]
        if (
            self.speed_mps != gait["speed_mps"]
            or self.step_length_m != gait["step_length_m"]
            or self.duty != gait["duty"]
            or self.clearance_m != gait["clearance_m"]
        ):
            raise ValueError("TRACKED_LINEAGE_GAIT_MISMATCH")
        return self

    @model_validator(mode="after")
    def validate_pilot_identity(self):
        is_v7 = self.environment_id.startswith("motion_task_v7_")
        if not is_v7:
            # This check and its message are unchanged. The tracked-lineage
            # branch is added after it, never before: a non-v7 profile that
            # declares a pilot identity must still be rejected for that reason
            # first, whatever else it declares.
            if (
                self.pilot_protocol_id is not None
                or self.seedvar_protocol_id is not None
                or self.pilot_arm_id is not None
            ):
                raise ValueError("NON_V7_PROFILE_HAS_PILOT_IDENTITY")
            if self.tracked_lineage_protocol_id is not None:
                return self.validate_tracked_lineage_identity()
            return self
        # The third identity is mutually exclusive with the other two, and its
        # environment is not a v7 one, so a v7 profile may never declare it.
        # Checked before the pilot/seedvar arbitration below so the rejection
        # names the real problem instead of reporting an ambiguous identity.
        if self.tracked_lineage_protocol_id is not None:
            raise ValueError("V7_PROFILE_HAS_TRACKED_LINEAGE_IDENTITY")
        # Exactly one governing protocol. A profile that satisfied both could be
        # reported under either, which is precisely the confusion these guards
        # exist to prevent.
        declared = [
            item
            for item in (self.pilot_protocol_id, self.seedvar_protocol_id)
            if item is not None
        ]
        if len(declared) != 1:
            raise ValueError("V7_PROFILE_AMBIGUOUS_PROTOCOL_IDENTITY")
        if self.pilot_arm_id is None:
            raise ValueError("V7_PROFILE_MISSING_FROZEN_IDENTITY")
        interface = resolve_v7_action_interface(self.pilot_arm_id)

        if self.seedvar_protocol_id is not None:
            if self.seedvar_protocol_id != SEEDVAR_PROTOCOL_ID:
                raise ValueError("SEEDVAR_PROFILE_MISSING_FROZEN_IDENTITY")
            if self.profile_id != interface.profile_id + SEEDVAR_PROFILE_SUFFIX:
                raise ValueError("SEEDVAR_PROFILE_ID_MISMATCH")
            if interface.environment_id != self.environment_id:
                raise ValueError("V7_ENVIRONMENT_ID_MISMATCH")
            if self.task_id != "stand_start_walk_stop_v1":
                raise ValueError("V7_TASK_ID_MISMATCH")
            if self.warm_start_policy_id != "stand_start_walk_stop_0p7_phase_observable_v5":
                raise ValueError("V7_WARM_START_ID_MISMATCH")
            seeds = seedvar_training_seeds()
            # The profile anchors the schedule at replicate 0; the per-run seed
            # is resolved from the protocol by replicate index, never from CLI.
            if self.seed_base != seeds[0] or self.parallel_envs != 12:
                raise ValueError("SEEDVAR_PROFILE_SEED_ANCHOR_MISMATCH")
            if self.planned_timesteps != 100_000:
                raise ValueError("V7_TRAINING_BUDGET_MISMATCH")
            return self

        # The pilot branch below is the original check sequence, in the original
        # order. Which rejection fires first is itself observable behaviour, so
        # the shared checks are deliberately not hoisted above it.
        if self.pilot_protocol_id != V7_PROTOCOL_ID:
            raise ValueError("V7_PROFILE_MISSING_FROZEN_IDENTITY")
        if interface.profile_id != self.profile_id:
            raise ValueError("V7_PROFILE_ID_MISMATCH")
        if interface.environment_id != self.environment_id:
            raise ValueError("V7_ENVIRONMENT_ID_MISMATCH")
        if self.task_id != "stand_start_walk_stop_v1":
            raise ValueError("V7_TASK_ID_MISMATCH")
        if self.warm_start_policy_id != "stand_start_walk_stop_0p7_phase_observable_v5":
            raise ValueError("V7_WARM_START_ID_MISMATCH")
        if self.seed_base != 8700 or self.parallel_envs != 12:
            raise ValueError("V7_TRAINING_SEED_OR_ENV_COUNT_MISMATCH")
        if self.planned_timesteps != 100_000:
            raise ValueError("V7_TRAINING_BUDGET_MISMATCH")
        return self


class TrainingProfiles(ProfileModel):
    schema_version: str
    evidence_scope: str
    profiles: list[TrainingProfile] = Field(min_length=1)


def load_profiles(path: Path = PROFILE_PATH) -> TrainingProfiles:
    return TrainingProfiles.model_validate(json.loads(path.read_text(encoding="utf-8")))


def resolve_profile(profile_id: str, path: Path = PROFILE_PATH) -> TrainingProfile:
    profiles = load_profiles(path)
    profile = next((item for item in profiles.profiles if item.profile_id == profile_id), None)
    if profile is None:
        raise KeyError(f"unknown training profile: {profile_id}")
    return profile


def public_training_inventory(path: Path = PROFILE_PATH) -> dict:
    """Read-only UI inventory; this endpoint never launches a training process."""
    inventory = load_profiles(path)
    return {
        "schema_version": inventory.schema_version,
        "evidence_scope": inventory.evidence_scope,
        "execution_mode": "OFFLINE_EXPLICIT_COMMAND_ONLY",
        "profiles": [item.model_dump(mode="json") for item in inventory.profiles],
    }


def make_env(profile_payload: dict, rank: int, seed_base: int):
    def _init():
        from rl.humanoid_env import (
            HumanoidMotionTaskCurriculumEnv,
            HumanoidMotionTaskEnv,
            HumanoidMotionTaskPathEfficiencyEnv,
            HumanoidMotionTaskPathStopEnv,
            HumanoidMotionTaskPhaseObservableEnv,
            HumanoidMotionTaskFilteredActionV7Env,
            HumanoidMotionTaskReducedJointEnvelopeV7Env,
            HumanoidMotionTaskRewardOnlyV7Env,
            HumanoidMotionTaskSubstepSaturationEnv,
            HumanoidWalkEnv,
        )
        kwargs = {
            "speed": profile_payload["speed_mps"],
            "step_length": profile_payload["step_length_m"],
            "duty": profile_payload["duty"],
            "clearance": profile_payload["clearance_m"],
        }
        if profile_payload["environment_id"] in {
            "motion_task_command_v1",
            "motion_task_command_envelope_v2",
            "motion_task_path_efficiency_v3",
            "motion_task_path_stop_v4",
            "motion_task_phase_observable_v5",
            "motion_task_substep_saturation_v6",
            "motion_task_v7_reward_only",
            "motion_task_v7_reduced_joint_envelope",
            "motion_task_v7_filtered_action",
        }:
            if not profile_payload.get("task_id"):
                raise ValueError("motion task environment requires task_id")
            env_class = {
                "motion_task_command_v1": HumanoidMotionTaskEnv,
                "motion_task_command_envelope_v2": HumanoidMotionTaskCurriculumEnv,
                "motion_task_path_efficiency_v3": HumanoidMotionTaskPathEfficiencyEnv,
                "motion_task_path_stop_v4": HumanoidMotionTaskPathStopEnv,
                "motion_task_phase_observable_v5": HumanoidMotionTaskPhaseObservableEnv,
                "motion_task_substep_saturation_v6": HumanoidMotionTaskSubstepSaturationEnv,
                "motion_task_v7_reward_only": HumanoidMotionTaskRewardOnlyV7Env,
                "motion_task_v7_reduced_joint_envelope": (
                    HumanoidMotionTaskReducedJointEnvelopeV7Env
                ),
                "motion_task_v7_filtered_action": HumanoidMotionTaskFilteredActionV7Env,
            }[profile_payload["environment_id"]]
            env = env_class(task_id=profile_payload["task_id"], **kwargs)
        else:
            env = HumanoidWalkEnv(**kwargs)
        env.reset(seed=seed_base + rank)
        return env
    return _init


def package_versions() -> dict[str, str]:
    packages = ("stable-baselines3", "gymnasium", "torch", "mujoco", "numpy", "pydantic")
    versions = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "MISSING"
    return versions


def git_source_identity() -> dict:
    """Record the complete non-ignored worktree identity for evidence runs."""
    repository = RL_DIR.parent.parent
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status_text = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return {
            "available": False,
            "git_sha": None,
            "working_tree_dirty": None,
            "working_tree_status": [],
            "error_type": type(exc).__name__,
        }
    return {
        "available": True,
        "git_sha": sha,
        "working_tree_dirty": bool(status_text),
        "working_tree_status": status_text.splitlines(),
    }


def seedvar_run_id(profile: TrainingProfile, replicate_index: int) -> str:
    return f"{profile.profile_id}-r{replicate_index}"


def validate_v7_seedvar_request(
    *,
    profile: TrainingProfile,
    run_id: str,
    total: int,
    n_envs: int,
    seed_base: int,
    replicate_index: int | None,
    seed_base_from_cli: bool,
    device: str,
    resume_from: Path | None,
    warm_start_from: Path | None,
    smoke: bool,
    preflight: bool,
    source_git: dict,
) -> None:
    """Fail closed on any drift from the frozen seed-variance design.

    Structurally the same discipline as the pilot guard, with one difference
    that matters: the seed is not a CLI input at all. It is resolved from the
    frozen protocol by replicate index, so no invocation can train a replicate
    on a seed the protocol does not schedule.
    """
    protocol = load_seedvar_protocol()
    design = protocol["training_design"]
    seeds = [int(seed) for seed in design["training_seeds"]]
    if replicate_index is None:
        raise ValueError("SEEDVAR_REPLICATE_INDEX_REQUIRED")
    if not 0 <= replicate_index < len(seeds):
        raise ValueError("SEEDVAR_REPLICATE_INDEX_OUT_OF_RANGE")
    if seed_base_from_cli:
        raise ValueError("SEEDVAR_SEED_OVERRIDE_FORBIDDEN")
    if seed_base != seeds[replicate_index]:
        raise ValueError("SEEDVAR_TRAINING_SEED_MISMATCH")
    if run_id != seedvar_run_id(profile, replicate_index):
        raise ValueError("SEEDVAR_RUN_ID_OVERRIDE_FORBIDDEN")
    if (
        total != design["requested_timesteps"]
        or n_envs != design["parallel_envs"]
    ):
        raise ValueError("SEEDVAR_TRAINING_OVERRIDE_FORBIDDEN")
    if device != design["device"]:
        raise ValueError("SEEDVAR_DEVICE_OVERRIDE_FORBIDDEN")
    if resume_from is not None or warm_start_from is not None:
        raise ValueError("SEEDVAR_CHECKPOINT_OVERRIDE_FORBIDDEN")
    if smoke or preflight:
        raise ValueError("SEEDVAR_RUN_KIND_OVERRIDE_FORBIDDEN")
    if (
        source_git.get("available") is not True
        or source_git.get("working_tree_dirty") is not False
        or not source_git.get("git_sha")
    ):
        raise ValueError("SEEDVAR_SOURCE_GIT_NOT_CLEAN")


def resume_artifact_relative_path(resume_path: Path) -> str:
    """How a resume source is recorded in the run manifest.

    Sources under backend/rl/ are recorded relative to it, as they always were.
    A version-controlled evidence source is recorded relative to the REPOSITORY
    ROOT instead, which makes the manifest field directly comparable with the
    path the protocol pins -- and relative_to(RL_DIR) would simply raise on it.
    """
    repository = RL_DIR.parent.parent
    for root in (RL_DIR, repository):
        try:
            return str(resume_path.relative_to(root)).replace("\\", "/")
        except ValueError:
            continue
    raise ValueError("RESUME_ARTIFACT_OUTSIDE_REPOSITORY")


def tracked_lineage_v2_run_id(profile: TrainingProfile) -> str:
    return f"{profile.profile_id}-run"


def validate_tracked_lineage_v2_request(
    *,
    profile: TrainingProfile,
    run_id: str,
    total: int,
    n_envs: int,
    seed_base: int,
    replicate_index: int | None,
    seed_base_from_cli: bool,
    device: str,
    resume_from: Path | None,
    warm_start_from: Path | None,
    smoke: bool,
    preflight: bool,
    source_git: dict,
    root: Path | None = None,
) -> None:
    """Fail closed on any drift from the frozen V2 design.

    The inverse of V1's guard on one point: V2 REQUIRES --resume-from, and the
    file it names must be the exact V1 checkpoint the protocol pins for this
    replicate, verified by digest rather than by path. A resume from anything
    else -- including V1's unretained policy.zip, which sits 15_264 steps past
    the reference and is not in version control -- is refused.
    """
    if profile.tracked_lineage_protocol_id != TRACKED_LINEAGE_V2_PROTOCOL_ID:
        return
    payload = load_tracked_lineage_v2_protocol()
    design = payload["training_design"]
    # parallel_envs lives under unchanged_from_v1, not training_design: V2
    # changes only the budget, so everything it inherits is recorded there.
    parallel_envs = int(payload["unchanged_from_v1"]["parallel_envs"])
    seeds = [int(seed) for seed in design["training_seeds"]]
    index = tracked_lineage_v2_replicate_index(profile.profile_id)
    if replicate_index is not None:
        raise ValueError("TRACKED_LINEAGE_V2_REPLICATE_INDEX_FORBIDDEN")
    if seed_base_from_cli:
        raise ValueError("TRACKED_LINEAGE_V2_SEED_OVERRIDE_FORBIDDEN")
    if seed_base != seeds[index]:
        raise ValueError("TRACKED_LINEAGE_V2_TRAINING_SEED_MISMATCH")
    if run_id != tracked_lineage_v2_run_id(profile):
        raise ValueError("TRACKED_LINEAGE_V2_RUN_ID_OVERRIDE_FORBIDDEN")
    if (
        total != int(design["increment_planned_timesteps"])
        or n_envs != parallel_envs
    ):
        raise ValueError("TRACKED_LINEAGE_V2_TRAINING_OVERRIDE_FORBIDDEN")
    if device != "cpu":
        raise ValueError("TRACKED_LINEAGE_V2_DEVICE_OVERRIDE_FORBIDDEN")
    if warm_start_from is not None:
        raise ValueError("TRACKED_LINEAGE_V2_WARM_START_FORBIDDEN")
    if resume_from is None:
        raise ValueError("TRACKED_LINEAGE_V2_RESUME_REQUIRED")
    expected = tracked_lineage_v2_resume_source(index)
    repository = (root or RL_DIR.parent.parent).resolve()
    expected_path = (repository / expected["relative_path"]).resolve()
    if resume_from.resolve() != expected_path:
        raise ValueError("TRACKED_LINEAGE_V2_RESUME_PATH_MISMATCH")
    if not expected_path.is_file():
        raise FileNotFoundError("TRACKED_LINEAGE_V2_RESUME_SOURCE_MISSING")
    if f"sha256:{sha256_file(expected_path)}" != expected["sha256"]:
        raise ValueError("TRACKED_LINEAGE_V2_RESUME_DIGEST_MISMATCH")
    if smoke or preflight:
        raise ValueError("TRACKED_LINEAGE_V2_RUN_KIND_OVERRIDE_FORBIDDEN")
    if (
        source_git.get("available") is not True
        or source_git.get("working_tree_dirty") is not False
        or not source_git.get("git_sha")
    ):
        raise ValueError("TRACKED_LINEAGE_V2_SOURCE_GIT_NOT_CLEAN")


def tracked_lineage_run_id(profile: TrainingProfile) -> str:
    return f"{profile.profile_id}-run"


def validate_tracked_lineage_request(
    *,
    profile: TrainingProfile,
    run_id: str,
    total: int,
    n_envs: int,
    seed_base: int,
    replicate_index: int | None,
    seed_base_from_cli: bool,
    device: str,
    resume_from: Path | None,
    warm_start_from: Path | None,
    smoke: bool,
    preflight: bool,
    source_git: dict,
) -> None:
    """Fail closed on any CLI or source drift from the frozen tracked-lineage design.

    Deliberately a separate function rather than a branch inside
    validate_v7_training_request: specification section 6.1 forbids changing the
    order in which the existing pilot and seedvar checks fire, and the surest way
    not to change it is not to touch that function at all.
    """
    # Must compare against V1's id, not merely test for None: a V2 profile also
    # sets this field, and before this guard returned early for it the V1 branch
    # ran on a b2_ profile id and raised. This narrows V1's guard to exactly V1's
    # profiles, which is what it always meant; behaviour for V1 profiles and for
    # profiles with no tracked-lineage identity is unchanged.
    if profile.tracked_lineage_protocol_id != TRACKED_LINEAGE_PROTOCOL_ID:
        return
    design = load_tracked_lineage_protocol()["training_design"]
    seeds = [int(seed) for seed in design["training_seeds"]]
    index = tracked_lineage_replicate_index(profile.profile_id)
    # The index is carried by the profile, so passing one on the command line is
    # a second source for a value that already has one.
    if replicate_index is not None:
        raise ValueError("TRACKED_LINEAGE_REPLICATE_INDEX_FORBIDDEN")
    if seed_base_from_cli:
        raise ValueError("TRACKED_LINEAGE_SEED_OVERRIDE_FORBIDDEN")
    if seed_base != seeds[index]:
        raise ValueError("TRACKED_LINEAGE_TRAINING_SEED_MISMATCH")
    if run_id != tracked_lineage_run_id(profile):
        raise ValueError("TRACKED_LINEAGE_RUN_ID_OVERRIDE_FORBIDDEN")
    if (
        total != design["planned_timesteps_per_replicate"]
        or n_envs != design["parallel_envs"]
    ):
        raise ValueError("TRACKED_LINEAGE_TRAINING_OVERRIDE_FORBIDDEN")
    if device != "cpu":
        raise ValueError("TRACKED_LINEAGE_DEVICE_OVERRIDE_FORBIDDEN")
    if resume_from is not None or warm_start_from is not None:
        raise ValueError("TRACKED_LINEAGE_CHECKPOINT_OVERRIDE_FORBIDDEN")
    if smoke or preflight:
        raise ValueError("TRACKED_LINEAGE_RUN_KIND_OVERRIDE_FORBIDDEN")
    if (
        source_git.get("available") is not True
        or source_git.get("working_tree_dirty") is not False
        or not source_git.get("git_sha")
    ):
        raise ValueError("TRACKED_LINEAGE_SOURCE_GIT_NOT_CLEAN")


def validate_v7_training_request(
    *,
    profile: TrainingProfile,
    run_id: str,
    total: int,
    n_envs: int,
    seed_base: int,
    device: str,
    resume_from: Path | None,
    warm_start_from: Path | None,
    smoke: bool,
    preflight: bool,
    source_git: dict,
    replicate_index: int | None = None,
    seed_base_from_cli: bool = False,
) -> None:
    """Fail closed on any CLI or source drift from the frozen v7 design."""
    if profile.pilot_arm_id is None:
        if replicate_index is not None:
            raise ValueError("SEEDVAR_REPLICATE_INDEX_ON_NON_V7_PROFILE")
        return
    if profile.seedvar_protocol_id is not None:
        validate_v7_seedvar_request(
            profile=profile,
            run_id=run_id,
            total=total,
            n_envs=n_envs,
            seed_base=seed_base,
            replicate_index=replicate_index,
            seed_base_from_cli=seed_base_from_cli,
            device=device,
            resume_from=resume_from,
            warm_start_from=warm_start_from,
            smoke=smoke,
            preflight=preflight,
            source_git=source_git,
        )
        return
    if replicate_index is not None:
        raise ValueError("V7_PILOT_REPLICATE_INDEX_FORBIDDEN")
    protocol = load_v7_protocol()
    design = protocol["training_design"]
    arm = next(
        item for item in protocol["arms"]
        if item["arm_id"] == profile.pilot_arm_id
    )
    if run_id != arm["training_run_id"]:
        raise ValueError("V7_PILOT_RUN_ID_OVERRIDE_FORBIDDEN")
    if (
        total != design["requested_timesteps"]
        or n_envs != design["parallel_envs"]
        or seed_base != design["agent_seed"]
    ):
        raise ValueError("V7_PILOT_TRAINING_OVERRIDE_FORBIDDEN")
    if device != design["device"]:
        raise ValueError("V7_PILOT_DEVICE_OVERRIDE_FORBIDDEN")
    if resume_from is not None or warm_start_from is not None:
        raise ValueError("V7_PILOT_CHECKPOINT_OVERRIDE_FORBIDDEN")
    if smoke or preflight:
        raise ValueError("V7_PILOT_RUN_KIND_OVERRIDE_FORBIDDEN")
    if (
        source_git.get("available") is not True
        or source_git.get("working_tree_dirty") is not False
        or not source_git.get("git_sha")
    ):
        raise ValueError("V7_PILOT_SOURCE_GIT_NOT_CLEAN")


def transplant_policy_input(model, source_model) -> dict:
    """將既有 policy 移植至較大的 observation，新增欄位以零權重開始。

    其餘 tensor 必須完全同形；任何未預期的 architecture 差異都 fail
    closed，避免產生看似可用、實際只載入部分權重的 checkpoint。
    """
    source_state = source_model.policy.state_dict()
    target_state = model.policy.state_dict()
    expanded_keys: list[str] = []
    for key, target_value in target_state.items():
        if key not in source_state:
            raise ValueError(f"WARM_START_MISSING_TENSOR:{key}")
        source_value = source_state[key]
        if source_value.shape == target_value.shape:
            target_state[key] = source_value.detach().clone()
            continue
        is_expandable_input = (
            key in {
                "mlp_extractor.policy_net.0.weight",
                "mlp_extractor.value_net.0.weight",
            }
            and source_value.ndim == 2
            and target_value.ndim == 2
            and target_value.shape[0] == source_value.shape[0]
            and target_value.shape[1] > source_value.shape[1]
        )
        if not is_expandable_input:
            raise ValueError(
                f"WARM_START_TENSOR_SHAPE_MISMATCH:{key}:"
                f"{tuple(source_value.shape)}->{tuple(target_value.shape)}"
            )
        expanded = target_value.detach().clone()
        expanded.zero_()
        expanded[:, :source_value.shape[1]] = source_value
        target_state[key] = expanded
        expanded_keys.append(key)
    model.policy.load_state_dict(target_state, strict=True)
    source_dim = int(source_model.observation_space.shape[0])
    target_dim = int(model.observation_space.shape[0])
    if not expanded_keys and source_dim != target_dim:
        raise ValueError(f"WARM_START_OBSERVATION_MISMATCH:{source_dim}->{target_dim}")
    return {
        "method": (
            "EXPAND_OBSERVATION_INPUT_ZERO_INIT_V1"
            if expanded_keys else "EXACT_POLICY_STATE_TRANSFER_V1"
        ),
        "source_observation_dim": source_dim,
        "target_observation_dim": target_dim,
        "expanded_tensors": expanded_keys,
    }


def write_manifest(path: Path, payload: dict) -> None:
    """原子化更新長時間 run 狀態，避免中斷時只剩半份 JSON。"""
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--total-timesteps", type=int)
    parser.add_argument("--n-envs", type=int)
    parser.add_argument("--seed-base", type=int)
    parser.add_argument(
        "--replicate-index",
        type=int,
        help=(
            "SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1 replicate index; the training "
            "seed is resolved from the frozen protocol, never from the CLI."
        ),
    )
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--resume-from", type=Path)
    parser.add_argument("--warm-start-from", type=Path)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    profile = resolve_profile(args.profile)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    is_seedvar = profile.seedvar_protocol_id is not None
    is_tracked_lineage = profile.tracked_lineage_protocol_id == TRACKED_LINEAGE_PROTOCOL_ID
    is_tracked_lineage_v2 = profile.tracked_lineage_protocol_id == TRACKED_LINEAGE_V2_PROTOCOL_ID
    if is_seedvar and args.replicate_index is not None:
        # A deterministic run id per replicate, so the artifact directory is
        # itself part of the frozen identity rather than a timestamp.
        run_id = args.run_id or seedvar_run_id(profile, args.replicate_index)
    elif is_tracked_lineage:
        # Same reasoning; here the replicate is already in the profile id.
        run_id = args.run_id or tracked_lineage_run_id(profile)
    elif is_tracked_lineage_v2:
        run_id = args.run_id or tracked_lineage_v2_run_id(profile)
    else:
        run_id = args.run_id or f"{profile.profile_id}-{timestamp}"
    if not run_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("run-id 只允許英數字、-、_")

    if args.smoke and args.preflight:
        raise ValueError("--smoke 與 --preflight 不可同時使用")
    if args.smoke:
        total = args.total_timesteps or 256
        n_envs = args.n_envs or 1
        run_kind = "smoke"
    elif args.preflight:
        total = args.total_timesteps or 65_536
        n_envs = args.n_envs or min(profile.parallel_envs, 4)
        run_kind = "learning_preflight"
    else:
        total = args.total_timesteps or profile.planned_timesteps
        n_envs = args.n_envs or profile.parallel_envs
        run_kind = "development_training"
    seed_base = profile.seed_base if args.seed_base is None else args.seed_base
    if is_seedvar and args.replicate_index is not None:
        seeds = seedvar_training_seeds()
        if not 0 <= args.replicate_index < len(seeds):
            raise ValueError("SEEDVAR_REPLICATE_INDEX_OUT_OF_RANGE")
        seed_base = seeds[args.replicate_index]
    if is_tracked_lineage:
        seeds = tracked_lineage_training_seeds()
        index = tracked_lineage_replicate_index(profile.profile_id)
        if not 0 <= index < len(seeds):
            raise ValueError("TRACKED_LINEAGE_REPLICATE_INDEX_OUT_OF_RANGE")
        seed_base = seeds[index]
    if is_tracked_lineage_v2:
        design = load_tracked_lineage_v2_protocol()["training_design"]
        seeds = [int(seed) for seed in design["training_seeds"]]
        index = tracked_lineage_v2_replicate_index(profile.profile_id)
        if not 0 <= index < len(seeds):
            raise ValueError("TRACKED_LINEAGE_V2_REPLICATE_INDEX_OUT_OF_RANGE")
        seed_base = seeds[index]
    if total <= 0 or n_envs <= 0 or seed_base < 0:
        raise ValueError("total-timesteps/n-envs 必須 > 0，seed-base 必須 >= 0")

    source_git_pre = git_source_identity()
    validate_v7_training_request(
        profile=profile,
        run_id=run_id,
        total=total,
        n_envs=n_envs,
        seed_base=seed_base,
        device=args.device,
        resume_from=args.resume_from,
        warm_start_from=args.warm_start_from,
        smoke=args.smoke,
        preflight=args.preflight,
        source_git=source_git_pre,
        replicate_index=args.replicate_index,
        seed_base_from_cli=args.seed_base is not None,
    )
    validate_tracked_lineage_v2_request(
        profile=profile,
        run_id=run_id,
        total=total,
        n_envs=n_envs,
        seed_base=seed_base,
        replicate_index=args.replicate_index,
        seed_base_from_cli=args.seed_base is not None,
        device=args.device,
        resume_from=args.resume_from,
        warm_start_from=args.warm_start_from,
        smoke=args.smoke,
        preflight=args.preflight,
        source_git=source_git_pre,
    )
    validate_tracked_lineage_request(
        profile=profile,
        run_id=run_id,
        total=total,
        n_envs=n_envs,
        seed_base=seed_base,
        replicate_index=args.replicate_index,
        seed_base_from_cli=args.seed_base is not None,
        device=args.device,
        resume_from=args.resume_from,
        warm_start_from=args.warm_start_from,
        smoke=args.smoke,
        preflight=args.preflight,
        source_git=source_git_pre,
    )
    run_dir = RL_DIR / "artifacts" / run_id
    # exist_ok=False 是防覆寫 gate；重跑時必須提供新 run-id。
    run_dir.mkdir(parents=True, exist_ok=False)
    checkpoint_dir = run_dir / "checkpoints"
    checkpoint_dir.mkdir()
    log_dir = run_dir / "logs"
    log_dir.mkdir()
    manifest_path = run_dir / "run_manifest.json"

    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.time()
    manifest = {
        "schema_version": "RL_TRAINING_RUN_V2",
        "run_id": run_id,
        "profile": profile.model_dump(),
        "resolved": {
            "total_timesteps": total,
            "parallel_envs": n_envs,
            "seed_base": seed_base,
            "device": args.device,
            "run_kind": run_kind,
        },
        "status": "TRAINING_INITIALIZING",
        "started_at": started_at,
        "completed_at": None,
        "elapsed_seconds": None,
        "artifact": None,
        "actual_total_timesteps": None,
        "checkpoint_interval_timesteps": None,
        "logs": {"directory": "logs", "format": "stable_baselines3_csv"},
        "source_files": {
            str(path.relative_to(RL_DIR.parent.parent)).replace("\\", "/"): f"sha256:{sha256_file(path)}"
            for path in SOURCE_FILES
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": package_versions(),
        },
        "evidence_scope": "SOFTWARE_TRAINING_PIPELINE_ONLY",
        "source_git_pre": source_git_pre,
        "source_git_post": None,
    }
    if is_seedvar and profile.pilot_arm_id is not None:
        interface = resolve_v7_action_interface(profile.pilot_arm_id)
        manifest["seedvar_protocol"] = {
            "protocol_id": SEEDVAR_PROTOCOL_ID,
            "pilot_arm_id": profile.pilot_arm_id,
            "replicate_index": args.replicate_index,
            "training_seed": seed_base,
            "environment_seed_block": [seed_base, seed_base + n_envs - 1],
            "path": str(
                SEEDVAR_PROTOCOL_PATH.relative_to(RL_DIR.parent.parent)
            ).replace("\\", "/"),
            "bytes": SEEDVAR_PROTOCOL_PATH.stat().st_size,
            "sha256": f"sha256:{sha256_file(SEEDVAR_PROTOCOL_PATH)}",
            "inherited_pilot_protocol_sha256": f"sha256:{sha256_file(V7_PROTOCOL_PATH)}",
            "action_interface": {
                "action_interface_id": interface.interface_id,
                "action_scale_rad": list(interface.action_scale_rad),
                "low_pass_alpha": interface.low_pass_alpha,
                "rate_limit_normalized_per_control_step": interface.rate_limit_per_step,
            },
        }
    elif profile.pilot_arm_id is not None:
        interface = resolve_v7_action_interface(profile.pilot_arm_id)
        manifest["pilot_protocol"] = {
            "protocol_id": V7_PROTOCOL_ID,
            "pilot_arm_id": profile.pilot_arm_id,
            "path": str(V7_PROTOCOL_PATH.relative_to(RL_DIR.parent.parent)).replace("\\", "/"),
            "bytes": V7_PROTOCOL_PATH.stat().st_size,
            "sha256": f"sha256:{sha256_file(V7_PROTOCOL_PATH)}",
            "action_interface": {
                "action_interface_id": interface.interface_id,
                "action_scale_rad": list(interface.action_scale_rad),
                "low_pass_alpha": interface.low_pass_alpha,
                "rate_limit_normalized_per_control_step": interface.rate_limit_per_step,
            },
        }
    if args.resume_from is not None and args.warm_start_from is not None:
        raise ValueError("--resume-from 與 --warm-start-from 不可同時使用")
    resume_path = None
    local_warm_start_path = None
    if args.resume_from is not None:
        resume_path = args.resume_from.resolve()
        artifact_root = (RL_DIR / "artifacts").resolve()
        evidence_root = TRACKED_LINEAGE_EVIDENCE_DIR.resolve()
        # The original rule allowed only the gitignored artifacts directory.
        # Version-controlled evidence is a STRICTLY BETTER resume source: it can
        # be re-derived offline by anyone, where an artifacts/ copy dies with the
        # container. Allowing it widens the set of paths but narrows what a
        # resume can silently depend on. The artifacts/ path is still accepted,
        # so every existing invocation behaves exactly as before.
        if not (
            resume_path.is_relative_to(artifact_root)
            or resume_path.is_relative_to(evidence_root)
        ):
            raise ValueError(
                "resume artifact 必須位於 backend/rl/artifacts 或 backend/tracked_lineage_evidence"
            )
        if not resume_path.is_file() or resume_path.suffix.lower() != ".zip":
            raise FileNotFoundError("resume policy artifact 不存在或不是 .zip")
        manifest["resume"] = {
            "artifact": resume_artifact_relative_path(resume_path),
            "bytes": resume_path.stat().st_size,
            "sha256": f"sha256:{sha256_file(resume_path)}",
            "mode": "PPO_FULL_STATE_RESUME_V1",
        }
    if args.warm_start_from is not None:
        local_warm_start_path = args.warm_start_from.resolve()
        artifact_root = (RL_DIR / "artifacts").resolve()
        if not local_warm_start_path.is_relative_to(artifact_root):
            raise ValueError("warm-start artifact 必須位於 backend/rl/artifacts")
        if not local_warm_start_path.is_file() or local_warm_start_path.suffix.lower() != ".zip":
            raise FileNotFoundError("warm-start policy artifact 不存在或不是 .zip")
    write_manifest(manifest_path, manifest)

    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import CheckpointCallback
    from stable_baselines3.common.logger import configure
    from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv, VecMonitor

    env = None
    warm_start_source_model = None
    try:
        payload = profile.model_dump()
        factories = [make_env(payload, rank, seed_base) for rank in range(n_envs)]
        vector_env = DummyVecEnv(factories) if n_envs == 1 else SubprocVecEnv(factories)
        action_contracts = vector_env.env_method("action_interface_contract")
        if any(contract != action_contracts[0] for contract in action_contracts[1:]):
            raise ValueError("VECTORIZED_ACTION_INTERFACE_MISMATCH")
        env = VecMonitor(vector_env)
        if args.smoke:
            n_steps, batch_size, n_epochs = 128, 128, 1
            checkpoint_interval = 128
        elif args.preflight:
            n_steps, batch_size, n_epochs = 512, 2048, 2
            checkpoint_interval = 32_768
        else:
            n_steps, batch_size, n_epochs = 2048, 8192, 5
            # 2_000_000 means a 2M-step run keeps no intermediate checkpoint at
            # all. The tracked-lineage line reads its interval from its own
            # frozen protocol, which is what makes a version-controlled lineage
            # possible; every other profile keeps the historical default.
            if is_tracked_lineage:
                checkpoint_interval = tracked_lineage_checkpoint_interval()
            elif is_tracked_lineage_v2:
                checkpoint_interval = tracked_lineage_v2_checkpoint_interval()
            else:
                checkpoint_interval = 2_000_000
        manifest["checkpoint_interval_timesteps"] = checkpoint_interval
        manifest["policy_contract"] = {
            "observation_dim": int(env.observation_space.shape[0]),
            "action_dim": int(env.action_space.shape[0]),
            "algorithm": "PPO_MLP",
            "n_steps_per_env": n_steps,
            "batch_size": batch_size,
            "n_epochs": n_epochs,
            "action_interface": action_contracts[0],
        }
        if local_warm_start_path is not None:
            warm_start_source_model = PPO.load(str(local_warm_start_path), device="cpu")
            manifest["warm_start"] = {
                "policy_id": None,
                "artifact": str(local_warm_start_path.relative_to(RL_DIR)).replace("\\", "/"),
                "bytes": local_warm_start_path.stat().st_size,
                "sha256": f"sha256:{sha256_file(local_warm_start_path)}",
                "evidence_status": "LOCAL_DEVELOPMENT_ARTIFACT_NOT_REGISTRY_POLICY",
                "transfer": None,
            }
        elif profile.warm_start_policy_id is not None and resume_path is None:
            warm_record, warm_artifact = resolve_policy(profile.warm_start_policy_id)
            warm_start_source_model = PPO.load(str(warm_artifact), device="cpu")
            manifest["warm_start"] = {
                "policy_id": warm_record.policy_id,
                "artifact": str(warm_artifact.relative_to(RL_DIR)).replace("\\", "/"),
                "bytes": warm_artifact.stat().st_size,
                "sha256": f"sha256:{sha256_file(warm_artifact)}",
                "evidence_status": warm_record.evidence_status,
                "transfer": None,
            }
        manifest["status"] = "TRAINING_IN_PROGRESS"
        write_manifest(manifest_path, manifest)

        if resume_path is not None:
            model = PPO.load(str(resume_path), env=env, device=args.device)
            if model.observation_space.shape != env.observation_space.shape:
                raise ValueError("RESUME_OBSERVATION_CONTRACT_MISMATCH")
            if model.action_space.shape != env.action_space.shape:
                raise ValueError("RESUME_ACTION_CONTRACT_MISMATCH")
            manifest["resume"]["source_num_timesteps"] = int(model.num_timesteps)
        else:
            model = PPO(
                "MlpPolicy", env,
                learning_rate=3e-4,
                n_steps=n_steps,
                batch_size=batch_size,
                n_epochs=n_epochs,
                gamma=0.99,
                gae_lambda=0.95,
                clip_range=0.2,
                ent_coef=0.002,
                policy_kwargs=dict(net_arch=[256, 256]),
                verbose=1,
                device=args.device,
                seed=seed_base,
            )
            if warm_start_source_model is not None:
                manifest["warm_start"]["transfer"] = transplant_policy_input(
                    model, warm_start_source_model,
                )
        write_manifest(manifest_path, manifest)
        model.set_logger(configure(str(log_dir), ["stdout", "csv"]))
        callback = CheckpointCallback(
            save_freq=max(checkpoint_interval // n_envs, 1),
            save_path=str(checkpoint_dir),
            name_prefix=profile.profile_id,
        )
        model.learn(
            total_timesteps=total,
            callback=callback,
            progress_bar=False,
            reset_num_timesteps=resume_path is None,
        )
        manifest["actual_total_timesteps"] = int(model.num_timesteps)
        if profile.pilot_arm_id is not None and model.num_timesteps != 122_880:
            raise ValueError(
                f"V7_REALIZED_TIMESTEPS_MISMATCH:{model.num_timesteps}:122880"
            )
        if is_tracked_lineage:
            # A prediction the run must satisfy, not a formality: SB3 collects
            # whole rollouts of n_steps * n_envs, so the realized total is the
            # first multiple of 24_576 at or above the planned ceiling. The same
            # arithmetic reproduces the seedvar line's recorded 122_880 from its
            # planned 100_000 (specification section 15.2).
            expected = load_tracked_lineage_protocol()["training_design"][
                "realized_timesteps_per_replicate"
            ]
            if model.num_timesteps != expected:
                raise ValueError(
                    f"TRACKED_LINEAGE_REALIZED_TIMESTEPS_MISMATCH:"
                    f"{model.num_timesteps}:{expected}"
                )
        if is_tracked_lineage_v2:
            # Same prediction-not-formality as V1, recomputed for a resume:
            # SB3 adds num_timesteps to total_timesteps when reset_num_timesteps
            # is False, so the run ends at the first rollout boundary at or past
            # 1_999_968 + 2_000_000 (specification section 4.2).
            expected = load_tracked_lineage_v2_protocol()["training_design"][
                "total_realized_timesteps"
            ]
            if model.num_timesteps != expected:
                raise ValueError(
                    f"TRACKED_LINEAGE_V2_REALIZED_TIMESTEPS_MISMATCH:"
                    f"{model.num_timesteps}:{expected}"
                )
        if profile.pilot_arm_id is not None or is_tracked_lineage or is_tracked_lineage_v2:
            source_git_post = git_source_identity()
            manifest["source_git_post"] = source_git_post
            if (
                source_git_post.get("available") is not True
                or source_git_post.get("working_tree_dirty") is not False
                or source_git_post.get("git_sha") != source_git_pre.get("git_sha")
            ):
                raise ValueError(
                    "TRACKED_LINEAGE_V2_SOURCE_GIT_DRIFT_DURING_TRAINING"
                    if is_tracked_lineage_v2
                    else "TRACKED_LINEAGE_SOURCE_GIT_DRIFT_DURING_TRAINING"
                    if is_tracked_lineage
                    else "V7_PILOT_SOURCE_GIT_DRIFT_DURING_TRAINING"
                )
        model.save(str(run_dir / "policy"))
        artifact = run_dir / "policy.zip"
        manifest["status"] = {
            "smoke": "PIPELINE_SMOKE_NOT_POLICY_EVIDENCE",
            "learning_preflight": "LEARNING_PREFLIGHT_NOT_POLICY_EVIDENCE",
            "development_training": "DEVELOPMENT_TRAINING_UNEVALUATED",
        }[run_kind]
        manifest["artifact"] = {
            "relative_path": "policy.zip",
            "bytes": artifact.stat().st_size,
            "sha256": f"sha256:{sha256_file(artifact)}",
        }
    except KeyboardInterrupt:
        manifest["status"] = "TRAINING_INTERRUPTED"
        manifest["failure"] = {"type": "KeyboardInterrupt"}
        raise
    except Exception as exc:
        manifest["status"] = "TRAINING_FAILED"
        manifest["failure"] = {"type": type(exc).__name__}
        raise
    finally:
        if env is not None:
            env.close()
        if manifest["source_git_post"] is None:
            manifest["source_git_post"] = git_source_identity()
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        manifest["elapsed_seconds"] = round(time.time() - t0, 3)
        write_manifest(manifest_path, manifest)
    print(f"run 完成：{run_id}；artifact={manifest['artifact']['relative_path']}；status={manifest['status']}")


if __name__ == "__main__":
    main()
