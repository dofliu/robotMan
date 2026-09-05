"""Fail-closed evidence bundle contract for the frozen v7 DEVELOPMENT pilot.

The builder consumes existing ``RL_TRAINING_RUN_V2`` run directories.  It does
not launch training or evaluation.  It snapshots each manifest, policy and
``RL_TRAINING_ENV_EVALUATION_V4`` artifact, derives only the preregistered
conditional statistics, and requires a second ``python -I -S`` process to
reconstruct the summary from canonical raw episode rows.
"""

from __future__ import annotations

from collections import Counter
import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import statistics
import subprocess
import sys
from typing import Any


PROTOCOL_SCHEMA = "V7_ACTION_INTERFACE_PILOT_PROTOCOL_V1"
TRAINING_SCHEMA = "RL_TRAINING_RUN_V2"
EVALUATION_SCHEMA = "RL_TRAINING_ENV_EVALUATION_V4"
SOURCE_INDEX_SCHEMA = "V7_PILOT_SOURCE_INDEX_V1"
RAW_SCHEMA = "V7_PILOT_RAW_EPISODES_V1"
SUMMARY_SCHEMA = "V7_PILOT_SUMMARY_V1"
REPLAY_SCHEMA = "V7_PILOT_REPLAY_RECEIPT_V1"
RECEIPT_SCHEMA = "V7_PILOT_EVIDENCE_RECEIPT_V1"
VALIDATION_SCHEMA = "V7_PILOT_BUNDLE_VALIDATION_V1"
ERROR_SCHEMA = "V7_PILOT_EVIDENCE_ERROR_RECEIPT_V1"
PROTOCOL_ID = "PILOT-V7-ACTION-INTERFACE-DEV-V1"
PROTOCOL_SHA256 = (
    "sha256:719b70a2bdf8d23af5f4ec5dff51a6099e88d6de4e2221fa74f6f7464cdfcb96"
)
CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED / DEVELOPMENT_ONLY. The pilot "
    "may support only a conditional action-interface screening statement for this "
    "frozen simulated plant, checkpoint, task, and evaluation-seed set. It does "
    "not support controller superiority, method-population power, formal sample-"
    "size adequacy, paper readiness, physical torque or thermal margins, safety, "
    "or sim-to-real claims."
)
ARM_IDS = (
    "V7A_REWARD_ONLY",
    "V7B_REDUCED_JOINT_ENVELOPE",
    "V7C_FILTERED_ACTION",
)
CANDIDATE_ARM_IDS = ARM_IDS[1:]
EXPECTED_SEEDS = tuple(range(18000, 18030))
RETIRED_SEED_RANGE = range(19000, 19030)
SEALED_SEED_RANGE = range(20000, 20030)
RETAINED_TERMINAL_STATES = ("COMPLETED", "FAILED", "CANCELLED")
RETAINED_OUTCOME_STATES = ("OBSERVED", "NULL", "NONFINITE")
MEASUREMENT_IDS = (
    "no_fall",
    "steady_speed_mps",
    "steady_progress_m",
    "final_stop_speed_mps",
    "lateral_drift_m",
    "saturation_duty_pct",
)
SOURCE_METRIC_KEYS = {
    "no_fall": "fell",
    "steady_speed_mps": "steady_walk_mean_speed_mps",
    "steady_progress_m": "steady_walk_progress_m",
    "final_stop_speed_mps": "final_stand_mean_abs_speed_mps",
    "lateral_drift_m": "lateral_drift_m",
    "saturation_duty_pct": "saturation_duty_pct",
}
GATE_SPECS = (
    ("NO_FALL", "no_fall", "==", True, None),
    ("STEADY_SPEED", "steady_speed_mps", "between_inclusive", 0.35, 1.05),
    ("STEADY_PROGRESS", "steady_progress_m", ">=", 1.4, None),
    ("STOP_SPEED", "final_stop_speed_mps", "<=", 0.15, None),
    ("LATERAL_DRIFT", "lateral_drift_m", "<=", 0.3, None),
    ("SATURATION_DUTY", "saturation_duty_pct", "<=", 30.0, None),
)
ACCEPTANCE_IDS = tuple(f"AP-{index:02d}" for index in range(1, 11))
EXPECTED_ACCEPTANCE = (
    "AP-01_PROTOCOL_AND_ARM_IDENTITY",
    "AP-02_CLEAN_GIT_SOURCE_PRE_POST_IDENTITY",
    "AP-03_EXACT_COMMON_TRAINING_SEED_BUDGET_AND_WARM_START",
    "AP-04_EXACT_30_PAIRED_DEV_EVALUATION_SEEDS_PER_ARM",
    "AP-05_FAILED_CANCELLED_NULL_NONFINITE_RETENTION",
    "AP-06_UNCHANGED_PILOT_SUBSET_THRESHOLDS_AND_EXPLICIT_GATE_RESULTS",
    "AP-07_CONDITIONAL_VARIANCE_AND_PAIRED_DIFFERENCE_WITH_POWER_BLOCKER",
    "AP-08_SAFE_ARTIFACT_PATH_BYTES_AND_SHA256_INVENTORY",
    "AP-09_STDLIB_ONLY_RAW_EPISODE_TO_SUMMARY_EXACT_REPLAY",
    "AP-10_SIM_ONLY_CLAIM_BOUNDARY_AND_PAPER_DATA_FALSE",
)
MAX_JSON_BYTES = 256 * 1024 * 1024
MAX_ARTIFACT_BYTES = 1024 * 1024 * 1024
MAX_JSON_DEPTH = 96
MAX_JSON_NODES = 5_000_000
MAX_REPLAY_STDOUT_BYTES = 1024 * 1024
REPLAY_TIMEOUT_SECONDS = 120
REPLAY_SCRIPT = Path(__file__).with_name("v7_pilot_replay.py")
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class V7PilotIntegrityError(RuntimeError):
    """A structural, identity, path, or replay gate failed closed."""


def _reject_constant(value: str) -> None:
    raise V7PilotIntegrityError(f"JSON non-finite constant is forbidden: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise V7PilotIntegrityError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _bounded_int(value: str) -> int:
    if len(value.lstrip("-")) > 1000:
        raise V7PilotIntegrityError("pathological JSON integer is forbidden")
    return int(value)


def _check_tree(root: Any) -> None:
    stack = [(root, 1)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise V7PilotIntegrityError("JSON node limit exceeded")
        if depth > MAX_JSON_DEPTH:
            raise V7PilotIntegrityError("JSON nesting limit exceeded")
        if isinstance(value, dict):
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)
        elif type(value) is float and not math.isfinite(value):
            # ``json.loads('1e400')`` produces infinity without invoking
            # parse_constant, so the decoded tree also needs a finite check.
            raise V7PilotIntegrityError("JSON non-finite number is forbidden")


def _load_json_bytes(payload: bytes, label: str) -> dict[str, Any]:
    if len(payload) > MAX_JSON_BYTES:
        raise V7PilotIntegrityError(f"JSON artifact exceeds byte limit: {label}")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            parse_constant=_reject_constant,
            parse_int=_bounded_int,
            object_pairs_hook=_reject_duplicate_keys,
        )
        _check_tree(value)
    except V7PilotIntegrityError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise V7PilotIntegrityError(f"invalid JSON artifact: {label}") from exc
    if not isinstance(value, dict):
        raise V7PilotIntegrityError(f"JSON root must be an object: {label}")
    return value


def load_json_object_strict(path: Path) -> dict[str, Any]:
    """Load bounded UTF-8 JSON with duplicate keys and NaN/Infinity rejected."""
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise V7PilotIntegrityError(f"cannot read JSON artifact: {path.name}") from exc
    return _load_json_bytes(payload, path.name)


def _load_json_text_strict(payload: str, label: str) -> dict[str, Any]:
    return _load_json_bytes(payload.encode("utf-8"), label)


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _require_object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise V7PilotIntegrityError(f"{context} must be an object")
    return value


def _require_list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise V7PilotIntegrityError(f"{context} must be an array")
    return value


def _require_string(
    value: Any,
    context: str,
    *,
    pattern: re.Pattern[str] | None = None,
    choices: set[str] | None = None,
) -> str:
    if not isinstance(value, str) or not value:
        raise V7PilotIntegrityError(f"{context} must be a non-empty string")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise V7PilotIntegrityError(f"{context} has invalid format")
    if choices is not None and value not in choices:
        raise V7PilotIntegrityError(f"{context} has unsupported value: {value}")
    return value


def _require_int(
    value: Any,
    context: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise V7PilotIntegrityError(
            f"{context} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _require_number(value: Any, context: str) -> float:
    if type(value) not in {int, float}:
        raise V7PilotIntegrityError(f"{context} must be a number")
    try:
        number = float(value)
        finite = math.isfinite(number)
    except (OverflowError, ValueError):
        finite = False
        number = 0.0
    if not finite:
        raise V7PilotIntegrityError(f"{context} must be finite")
    return number


def _safe_relative_path(value: Any, context: str) -> str:
    path = _require_string(value, context)
    normalized = path.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if (
        pure.is_absolute()
        or normalized.startswith("//")
        or any(":" in part for part in pure.parts)
        or ".." in pure.parts
        or normalized != pure.as_posix()
    ):
        raise V7PilotIntegrityError(f"{context} must be a canonical safe relative path")
    return normalized


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


def _safe_source_file(root: Path, relative_path: str, context: str) -> Path:
    normalized = _safe_relative_path(relative_path, context)
    candidate = root.joinpath(*PurePosixPath(normalized).parts)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise V7PilotIntegrityError(f"missing source artifact: {normalized}") from exc
    if not resolved.is_relative_to(root.resolve()):
        raise V7PilotIntegrityError(f"source artifact escapes bounded root: {normalized}")
    current = root.resolve()
    for part in PurePosixPath(normalized).parts:
        current = current / part
        if _is_link_or_junction(current):
            raise V7PilotIntegrityError(f"source artifact uses link/reparse point: {normalized}")
    if not resolved.is_file():
        raise V7PilotIntegrityError(f"source artifact is not a file: {normalized}")
    return resolved


def _read_bounded_file(path: Path, context: str) -> bytes:
    try:
        size = path.stat().st_size
        if size <= 0 or size > MAX_ARTIFACT_BYTES:
            raise V7PilotIntegrityError(f"{context} has invalid byte size: {size}")
        payload = path.read_bytes()
    except V7PilotIntegrityError:
        raise
    except OSError as exc:
        raise V7PilotIntegrityError(f"cannot read {context}") from exc
    if len(payload) != size:
        raise V7PilotIntegrityError(f"{context} changed during read")
    return payload


def _validate_protocol(protocol: dict[str, Any], protocol_sha256: str) -> None:
    if protocol_sha256 != PROTOCOL_SHA256:
        raise V7PilotIntegrityError("frozen protocol SHA-256 mismatch")
    frozen = {
        "schema_version": PROTOCOL_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "protocol_status": "FROZEN_INTERNAL_DEVELOPMENT",
        "run_class": "DEVELOPMENT",
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "validation_status": "NOT_PHYSICALLY_VALIDATED",
        "paper_data_ready": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    for key, expected in frozen.items():
        if protocol.get(key) != expected:
            raise V7PilotIntegrityError(f"frozen protocol {key} mismatch")
    training = _require_object(protocol.get("training_design"), "training_design")
    expected_training = {
        "agent_seed": 8700,
        "parallel_envs": 12,
        "environment_seed_start": 8700,
        "environment_seed_end": 8711,
        "independent_training_replicates_per_arm": 1,
        "requested_timesteps": 100000,
        "expected_realized_timesteps": 122880,
        "ppo_rollout_steps_per_env": 2048,
        "ppo_batch_size": 8192,
        "ppo_epochs": 5,
        "device": "cpu",
    }
    for key, expected in expected_training.items():
        if training.get(key) != expected:
            raise V7PilotIntegrityError(f"frozen training {key} mismatch")
    evaluation = _require_object(protocol.get("evaluation_design"), "evaluation_design")
    if evaluation.get("evaluation_seeds") != list(EXPECTED_SEEDS):
        raise V7PilotIntegrityError("frozen evaluation seed schedule mismatch")
    if evaluation.get("retired_seed_range") != [19000, 19029]:
        raise V7PilotIntegrityError("retired evaluation seed range mismatch")
    if evaluation.get("sealed_formal_seed_range") != [20000, 20029]:
        raise V7PilotIntegrityError("sealed FORMAL/HOLDOUT seed range mismatch")
    if evaluation.get("deterministic_policy") is not True:
        raise V7PilotIntegrityError("frozen evaluation must be deterministic")
    arms = _require_list(protocol.get("arms"), "arms")
    if len(arms) != 3 or tuple(
        item.get("arm_id") for item in arms if isinstance(item, dict)
    ) != ARM_IDS:
        raise V7PilotIntegrityError("frozen protocol arm inventory/order mismatch")
    if protocol.get("acceptance_criteria") != list(EXPECTED_ACCEPTANCE):
        raise V7PilotIntegrityError("frozen acceptance criteria mismatch")
    estimand = _require_object(
        protocol.get("estimand_and_selection"), "estimand_and_selection"
    )
    if (
        estimand.get("reference_arm") != ARM_IDS[0]
        or estimand.get("candidate_arms") != list(CANDIDATE_ARM_IDS)
        or estimand.get("primary_outcome") != "saturation_duty_pct"
        or estimand.get("method_level_power_ready") is not False
        or estimand.get("formal_sample_size_decision")
        != "BLOCKED_INDEPENDENT_TRAINING_SEED_VARIANCE_NOT_ESTIMATED"
    ):
        raise V7PilotIntegrityError("frozen estimand/power blocker mismatch")


def _git_identity(value: Any, context: str) -> str:
    item = _require_object(value, context)
    if item.get("available") is not True:
        raise V7PilotIntegrityError(f"{context} Git identity unavailable")
    sha = _require_string(item.get("git_sha"), context + ".git_sha", pattern=GIT_SHA_PATTERN)
    if item.get("working_tree_dirty") is not False:
        raise V7PilotIntegrityError(f"{context} non-ignored worktree must be clean")
    if item.get("working_tree_status") != []:
        raise V7PilotIntegrityError(f"{context}.working_tree_status must be empty")
    return sha


def _validate_source_files(
    value: Any,
    context: str,
    *,
    repo_root: Path,
    verify_repository: bool,
) -> dict[str, str]:
    item = _require_object(value, context)
    if not item:
        raise V7PilotIntegrityError(f"{context} must not be empty")
    result: dict[str, str] = {}
    casefold_paths: set[str] = set()
    for raw_path, raw_hash in item.items():
        path = _safe_relative_path(raw_path, context + ".path")
        if path.casefold() in casefold_paths:
            raise V7PilotIntegrityError(f"{context} contains case-colliding paths")
        casefold_paths.add(path.casefold())
        digest = _require_string(raw_hash, context + f"[{path}]", pattern=SHA256_PATTERN)
        result[path] = digest
        if verify_repository:
            source_path = _safe_source_file(repo_root, path, context + f"[{path}]")
            if sha256_file(source_path) != digest:
                raise V7PilotIntegrityError(f"{context} source SHA-256 mismatch: {path}")
    return result


def _validate_live_repository(repo_root: Path, expected_sha: str) -> None:
    try:
        sha_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        status_result = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise V7PilotIntegrityError("cannot verify live Git source identity") from exc
    if sha_result.returncode != 0 or status_result.returncode != 0:
        raise V7PilotIntegrityError("live Git source identity command failed")
    if sha_result.stdout.strip() != expected_sha:
        raise V7PilotIntegrityError("live Git SHA differs from recorded pilot source")
    if status_result.stdout.strip():
        raise V7PilotIntegrityError("live tracked worktree is dirty")


def _terminal_reason(payload: dict[str, Any], default: str) -> str:
    for key in ("reason", "terminal_reason", "failure_reason"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value[:1000]
    failure = payload.get("failure")
    if isinstance(failure, dict):
        parts = [f"{key}={failure[key]}" for key in sorted(failure) if failure[key] is not None]
        if parts:
            return (";".join(parts))[:1000]
    if isinstance(failure, str) and failure:
        return failure[:1000]
    return default


def _training_state(status: Any) -> str:
    mapping = {
        "DEVELOPMENT_TRAINING_UNEVALUATED": "COMPLETED",
        "TRAINING_FAILED": "FAILED",
        "TRAINING_INTERRUPTED": "CANCELLED",
        "TRAINING_CANCELLED": "CANCELLED",
    }
    if status not in mapping:
        raise V7PilotIntegrityError(f"training manifest is not terminal: {status!r}")
    return mapping[status]


def _evaluation_state(status: Any) -> str:
    mapping = {
        "COMPLETED": "COMPLETED",
        "COMPLETED_WITH_BLOCKER": "COMPLETED",
        "FAILED": "FAILED",
        "EVALUATION_FAILED": "FAILED",
        "CANCELLED": "CANCELLED",
        "EVALUATION_CANCELLED": "CANCELLED",
        "INTERRUPTED": "CANCELLED",
    }
    if status not in mapping:
        raise V7PilotIntegrityError(f"evaluation receipt is not terminal: {status!r}")
    return mapping[status]


def _artifact_binding(
    *,
    state: str,
    path: str | None,
    payload: bytes | None,
    reason: str | None,
) -> dict[str, Any]:
    if state == "PRESENT":
        if path is None or payload is None:
            raise AssertionError("present artifact binding requires path and payload")
        return {
            "state": "PRESENT",
            "path": path,
            "bytes": len(payload),
            "sha256": _sha256_bytes(payload),
            "reason": None,
        }
    return {
        "state": "NULL",
        "path": None,
        "bytes": None,
        "sha256": None,
        "reason": reason,
    }


def _validate_training_manifest(
    manifest: dict[str, Any],
    frozen_arm: dict[str, Any],
    *,
    protocol: dict[str, Any],
    protocol_bytes: bytes,
    run_dir: Path,
    repo_root: Path,
    verify_repository: bool,
) -> dict[str, Any]:
    context = f"training[{frozen_arm['arm_id']}]"
    if manifest.get("schema_version") != TRAINING_SCHEMA:
        raise V7PilotIntegrityError(f"{context} schema mismatch")
    if manifest.get("run_id") != frozen_arm["training_run_id"]:
        raise V7PilotIntegrityError(f"{context} run_id mismatch")
    state = _training_state(manifest.get("status"))
    profile = _require_object(manifest.get("profile"), context + ".profile")
    expected_profile = {
        "profile_id": frozen_arm["profile_id"],
        "planned_timesteps": 100000,
        "parallel_envs": 12,
        "seed_base": 8700,
        "environment_id": frozen_arm["environment_id"],
        "task_id": protocol["task_contract"]["task_id"],
        "warm_start_policy_id": protocol["source_baseline"]["warm_start_policy_id"],
        "pilot_protocol_id": PROTOCOL_ID,
        "pilot_arm_id": frozen_arm["arm_id"],
    }
    for key, expected in expected_profile.items():
        if profile.get(key) != expected:
            raise V7PilotIntegrityError(f"{context}.profile.{key} mismatch")
    resolved = _require_object(manifest.get("resolved"), context + ".resolved")
    expected_resolved = {
        "total_timesteps": 100000,
        "parallel_envs": 12,
        "seed_base": 8700,
        "device": "cpu",
        "run_kind": "development_training",
    }
    for key, expected in expected_resolved.items():
        if resolved.get(key) != expected:
            raise V7PilotIntegrityError(f"{context}.resolved.{key} mismatch")
    actual_steps = manifest.get("actual_total_timesteps")
    if state == "COMPLETED":
        if actual_steps != 122880:
            raise V7PilotIntegrityError(f"{context} realized timestep budget mismatch")
    elif actual_steps is not None:
        _require_int(actual_steps, context + ".actual_total_timesteps", minimum=0, maximum=122880)
    pre_sha = _git_identity(manifest.get("source_git_pre"), context + ".source_git_pre")
    post_sha = _git_identity(manifest.get("source_git_post"), context + ".source_git_post")
    if pre_sha != post_sha:
        raise V7PilotIntegrityError(f"{context} Git pre/post identity drift")
    source_files = _validate_source_files(
        manifest.get("source_files"),
        context + ".source_files",
        repo_root=repo_root,
        verify_repository=verify_repository,
    )
    source_baseline = protocol["source_baseline"]
    for path, expected_hash in (
        (
            source_baseline["motion_task_source"],
            source_baseline["motion_task_source_sha256"],
        ),
        (
            source_baseline["model_builder_source"],
            source_baseline["model_builder_source_sha256"],
        ),
        (
            source_baseline["config_schema_source"],
            source_baseline["config_schema_source_sha256"],
        ),
    ):
        if source_files.get(path) != expected_hash:
            raise V7PilotIntegrityError(f"{context} frozen baseline source mismatch: {path}")
    protocol_record = _require_object(
        manifest.get("pilot_protocol"), context + ".pilot_protocol"
    )
    expected_protocol_path = "backend/rl/v7_action_interface_pilot_protocol.json"
    if (
        protocol_record.get("protocol_id") != PROTOCOL_ID
        or protocol_record.get("pilot_arm_id") != frozen_arm["arm_id"]
        or protocol_record.get("path") != expected_protocol_path
        or protocol_record.get("bytes") != len(protocol_bytes)
        or protocol_record.get("sha256") != _sha256_bytes(protocol_bytes)
    ):
        raise V7PilotIntegrityError(f"{context} pilot protocol artifact mismatch")
    interface = _require_object(
        protocol_record.get("action_interface"), context + ".pilot_protocol.action_interface"
    )
    expected_interface = {
        "action_interface_id": frozen_arm["action_interface_id"],
        "action_scale_rad": frozen_arm["action_scale_rad"],
        "low_pass_alpha": frozen_arm["low_pass_alpha"],
        "rate_limit_normalized_per_control_step": frozen_arm[
            "rate_limit_normalized_per_control_step"
        ],
    }
    for key, expected in expected_interface.items():
        if interface.get(key) != expected:
            raise V7PilotIntegrityError(f"{context} action interface {key} mismatch")
    warm_start = _require_object(manifest.get("warm_start"), context + ".warm_start")
    warm_path = str(warm_start.get("artifact", "")).replace("\\", "/")
    accepted_warm_paths = {
        source_baseline["warm_start_path"],
        PurePosixPath(source_baseline["warm_start_path"]).name,
    }
    if (
        warm_start.get("policy_id") != source_baseline["warm_start_policy_id"]
        or warm_path not in accepted_warm_paths
        or warm_start.get("bytes") != source_baseline["warm_start_bytes"]
        or warm_start.get("sha256") != source_baseline["warm_start_sha256"]
    ):
        raise V7PilotIntegrityError(f"{context} warm-start identity mismatch")
    if verify_repository:
        warm_source = _safe_source_file(
            repo_root,
            source_baseline["warm_start_path"],
            context + ".warm_start.artifact",
        )
        if (
            warm_source.stat().st_size != source_baseline["warm_start_bytes"]
            or sha256_file(warm_source) != source_baseline["warm_start_sha256"]
        ):
            raise V7PilotIntegrityError(f"{context} warm-start artifact readback mismatch")
    policy_contract = _require_object(
        manifest.get("policy_contract"), context + ".policy_contract"
    )
    expected_policy = {
        "observation_dim": 51,
        "action_dim": 12,
        "algorithm": "PPO_MLP",
        "n_steps_per_env": 2048,
        "batch_size": 8192,
        "n_epochs": 5,
    }
    for key, expected in expected_policy.items():
        if policy_contract.get(key) != expected:
            raise V7PilotIntegrityError(f"{context}.policy_contract.{key} mismatch")
    policy_interface = _require_object(
        policy_contract.get("action_interface"), context + ".policy_contract.action_interface"
    )
    if (
        policy_interface.get("pilot_arm_id") != frozen_arm["arm_id"]
        or policy_interface.get("action_interface_id") != frozen_arm["action_interface_id"]
        or policy_interface.get("action_scale_rad") != frozen_arm["action_scale_rad"]
        or policy_interface.get("low_pass_alpha") != frozen_arm["low_pass_alpha"]
        or policy_interface.get("rate_limit_normalized_per_control_step")
        != frozen_arm["rate_limit_normalized_per_control_step"]
        or policy_interface.get("previous_action_semantics")
        != "PREVIOUS_APPLIED_NORMALIZED_ACTION"
    ):
        raise V7PilotIntegrityError(f"{context} policy action-interface mismatch")
    artifact = manifest.get("artifact")
    policy_payload: bytes | None = None
    policy_source_path: str | None = None
    policy_reason: str | None = None
    if artifact is None:
        if state == "COMPLETED":
            raise V7PilotIntegrityError(f"{context} completed training lacks policy")
        policy_reason = f"TRAINING_{state}_NO_POLICY_ARTIFACT"
    else:
        artifact_record = _require_object(artifact, context + ".artifact")
        policy_source_path = _safe_relative_path(
            artifact_record.get("relative_path"), context + ".artifact.relative_path"
        )
        policy_path = _safe_source_file(run_dir, policy_source_path, context + ".artifact")
        policy_payload = _read_bounded_file(policy_path, context + ".policy")
        if (
            artifact_record.get("bytes") != len(policy_payload)
            or artifact_record.get("sha256") != _sha256_bytes(policy_payload)
        ):
            raise V7PilotIntegrityError(f"{context} policy bytes/SHA-256 mismatch")
    return {
        "terminal_state": state,
        "terminal_reason": (
            None if state == "COMPLETED" else _terminal_reason(manifest, f"TRAINING_{state}")
        ),
        "actual_total_timesteps": actual_steps,
        "source_git_sha": pre_sha,
        "source_files": source_files,
        "policy_payload": policy_payload,
        "policy_source_path": policy_source_path,
        "policy_reason": policy_reason,
    }


def _evaluation_protocol_arm(
    value: Any,
    context: str,
    *,
    require_artifact_identity: bool,
) -> str:
    item = _require_object(value, context)
    if item.get("protocol_id") != PROTOCOL_ID:
        raise V7PilotIntegrityError(f"{context}.protocol_id mismatch")
    arm = item.get("arm_id", item.get("pilot_arm_id"))
    if "arm_id" in item and "pilot_arm_id" in item and item["arm_id"] != item["pilot_arm_id"]:
        raise V7PilotIntegrityError(f"{context} contains conflicting arm identities")
    if require_artifact_identity:
        if (
            item.get("path") != "backend/rl/v7_action_interface_pilot_protocol.json"
            or item.get("bytes") != 9753
            or item.get("sha256") != PROTOCOL_SHA256
        ):
            raise V7PilotIntegrityError(f"{context} protocol artifact identity mismatch")
    return _require_string(arm, context + ".arm_id")


def _evaluation_git_sha(evaluation: dict[str, Any], context: str) -> str:
    pre = _git_identity(evaluation.get("source_git_pre"), context + ".source_git_pre")
    post = _git_identity(evaluation.get("source_git_post"), context + ".source_git_post")
    if pre != post:
        raise V7PilotIntegrityError(f"{context} Git pre/post identity drift")
    return pre


def _canonical_measurements(row: dict[str, Any], context: str) -> dict[str, Any]:
    outcome_state = _require_string(
        row.get("outcome_state"),
        context + ".outcome_state",
        choices=set(RETAINED_OUTCOME_STATES),
    )
    terminal_state = _require_string(
        row.get("terminal_record_state"),
        context + ".terminal_record_state",
        choices=set(RETAINED_TERMINAL_STATES),
    )
    reason: str | None = row.get("reason")
    if terminal_state == "COMPLETED" and outcome_state == "OBSERVED":
        if reason is not None:
            raise V7PilotIntegrityError(f"{context}.reason must be null for observed completion")
    else:
        if not isinstance(reason, str) or not reason:
            reason = _terminal_reason(
                row,
                f"SOURCE_REPORTED_{terminal_state}_{outcome_state}_WITHOUT_DETAIL",
            )
    metrics = _require_object(row.get("metrics"), context + ".metrics")
    measurements: dict[str, dict[str, Any]] = {}
    for measurement_id in MEASUREMENT_IDS:
        source_key = SOURCE_METRIC_KEYS[measurement_id]
        if source_key not in metrics:
            raise V7PilotIntegrityError(f"{context}.metrics missing {source_key}")
        value = metrics[source_key]
        if measurement_id == "no_fall":
            if type(value) is not bool:
                if value is not None:
                    raise V7PilotIntegrityError(f"{context}.metrics.fell must be boolean/null")
                state = outcome_state if outcome_state != "OBSERVED" else "NULL"
                measurements[measurement_id] = {
                    "state": state,
                    "value": None,
                    "reason": reason or "FALL_STATE_NOT_OBSERVED",
                }
            else:
                measurements[measurement_id] = {
                    "state": "OBSERVED",
                    "value": not value,
                    "reason": None,
                }
            continue
        if value is None:
            if outcome_state == "OBSERVED":
                raise V7PilotIntegrityError(
                    f"{context}.metrics.{source_key} is null but outcome_state is OBSERVED"
                )
            measurements[measurement_id] = {
                "state": outcome_state,
                "value": None,
                "reason": reason,
            }
        else:
            number = _require_number(value, f"{context}.metrics.{source_key}")
            measurements[measurement_id] = {
                "state": "OBSERVED",
                "value": value if type(value) is int else number,
                "reason": None,
            }
    severity = {"OBSERVED": 0, "NULL": 1, "NONFINITE": 2}
    measurement_severity = max(severity[item["state"]] for item in measurements.values())
    if severity[outcome_state] < measurement_severity:
        raise V7PilotIntegrityError(f"{context} outcome_state understates required metrics")
    return {
        "terminal_state": terminal_state,
        "outcome_state": outcome_state,
        "reason": reason,
        "measurements": measurements,
    }


def _trace_vector(value: Any, context: str) -> list[float]:
    values = _require_list(value, context)
    if len(values) != 12:
        raise V7PilotIntegrityError(f"{context} must contain exactly 12 values")
    return [
        _require_number(item, f"{context}[{index}]")
        for index, item in enumerate(values)
    ]


def _canonical_control_trace(
    row: dict[str, Any],
    frozen_arm: dict[str, Any],
    normalized: dict[str, Any],
    context: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_trace = _require_list(row.get("control_step_trace"), context + ".control_step_trace")
    terminal_state = normalized["terminal_state"]
    if terminal_state == "COMPLETED" and not source_trace:
        raise V7PilotIntegrityError(f"{context} completed row requires non-empty 500 Hz trace")
    if terminal_state != "COMPLETED" and source_trace:
        raise V7PilotIntegrityError(f"{context} terminal failure must retain an empty trace")
    if terminal_state != "COMPLETED":
        return [], {
            "sample_rate_hz": 500.0,
            "control_step_count": 0,
            "saturation_substeps_total": 0,
            "saturation_substeps_over_threshold": 0,
            "recomputed_saturation_duty_pct": None,
            "reported_saturation_duty_pct": None,
            "reported_absolute_delta": None,
            "action_operator_state": "NULL",
            "action_operator_max_abs_delta": None,
        }
    if row.get("saturation_sample_rate_hz") != 500.0:
        raise V7PilotIntegrityError(f"{context} saturation sample rate must be 500 Hz")
    alpha = frozen_arm["low_pass_alpha"]
    rate_limit = frozen_arm["rate_limit_normalized_per_control_step"]
    previous = [0.0] * 12
    trace: list[dict[str, Any]] = []
    over_total = 0
    substep_total = 0
    max_delta = 0.0
    for index, source_value in enumerate(source_trace):
        item_context = f"{context}.control_step_trace[{index}]"
        item = _require_object(source_value, item_context)
        if item.get("control_step") != index:
            raise V7PilotIntegrityError(f"{item_context}.control_step is not contiguous")
        over = _require_int(
            item.get("saturation_substeps_over_threshold"),
            item_context + ".saturation_substeps_over_threshold",
            minimum=0,
            maximum=10,
        )
        total = _require_int(
            item.get("saturation_substeps_total"),
            item_context + ".saturation_substeps_total",
            minimum=10,
            maximum=10,
        )
        if over > total:
            raise V7PilotIntegrityError(f"{item_context} saturation count exceeds total")
        requested = _trace_vector(
            item.get("requested_action"), item_context + ".requested_action"
        )
        applied = _trace_vector(
            item.get("applied_action"), item_context + ".applied_action"
        )
        joint_target = _trace_vector(
            item.get("joint_target_rad"), item_context + ".joint_target_rad"
        )
        command_phase = _require_string(
            item.get("command_phase"), item_context + ".command_phase"
        )
        applied_delta_raw = item.get("applied_action_delta_l2")
        requested_delta_raw = item.get("requested_applied_delta_l2")
        applied_delta = _require_number(
            applied_delta_raw, item_context + ".applied_action_delta_l2"
        )
        requested_delta = _require_number(
            requested_delta_raw,
            item_context + ".requested_applied_delta_l2",
        )
        if applied_delta < 0.0 or requested_delta < 0.0:
            raise V7PilotIntegrityError(f"{item_context} L2 delta must be non-negative")
        requested_values = [float(value) for value in requested]
        applied_values = [float(value) for value in applied]
        if any(not -1.0 <= value <= 1.0 for value in requested_values):
            raise V7PilotIntegrityError(f"{item_context} requested action is not clipped")
        if alpha is None:
            expected = requested_values
        else:
            expected = []
            for prior, requested_value in zip(previous, requested_values, strict=True):
                candidate = prior + float(alpha) * (requested_value - prior)
                delta = max(-float(rate_limit), min(float(rate_limit), candidate - prior))
                expected.append(prior + delta)
        step_delta = max(
            abs(actual - expected_value)
            for actual, expected_value in zip(applied_values, expected, strict=True)
        )
        max_delta = max(max_delta, step_delta)
        if step_delta > 1.0e-12:
            raise V7PilotIntegrityError(f"{item_context} action operator identity mismatch")
        applied_delta_expected = math.sqrt(sum(
            (actual - prior) ** 2
            for actual, prior in zip(applied_values, previous, strict=True)
        ))
        requested_delta_expected = math.sqrt(sum(
            (requested_value - actual) ** 2
            for requested_value, actual in zip(
                requested_values, applied_values, strict=True
            )
        ))
        if (
            abs(applied_delta - applied_delta_expected) > 1.0e-12
            or abs(requested_delta - requested_delta_expected) > 1.0e-12
        ):
            raise V7PilotIntegrityError(f"{item_context} action delta receipt mismatch")
        previous = applied_values
        over_total += over
        substep_total += total
        trace.append({
            "control_step": index,
            "command_phase": command_phase,
            "requested_action": requested,
            "applied_action": applied,
            "joint_target_rad": joint_target,
            "applied_action_delta_l2": applied_delta,
            "requested_applied_delta_l2": requested_delta,
            "saturation_substeps_over_threshold": over,
            "saturation_substeps_total": total,
        })
    recomputed = round(100.0 * over_total / substep_total, 6)
    reported = normalized["measurements"]["saturation_duty_pct"]
    if reported["state"] == "OBSERVED":
        reported_value = float(reported["value"])
        reported_delta = abs(recomputed - reported_value)
        if reported_delta > 1.0e-12:
            raise V7PilotIntegrityError(f"{context} 500 Hz saturation duty mismatch")
    else:
        reported_value = None
        reported_delta = None
    return trace, {
        "sample_rate_hz": 500.0,
        "control_step_count": len(trace),
        "saturation_substeps_total": substep_total,
        "saturation_substeps_over_threshold": over_total,
        "recomputed_saturation_duty_pct": recomputed,
        "reported_saturation_duty_pct": reported_value,
        "reported_absolute_delta": reported_delta,
        "action_operator_state": "PASS",
        "action_operator_max_abs_delta": max_delta,
    }


def _gate_results(measurements: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for gate_id, measurement_id, operator, threshold, upper in GATE_SPECS:
        measurement = measurements[measurement_id]
        state = measurement["state"]
        value = measurement["value"]
        passed: bool | None
        if state != "OBSERVED":
            passed = None
        elif operator == "==":
            passed = value == threshold
        elif operator == "between_inclusive":
            passed = float(threshold) <= float(value) <= float(upper)
        elif operator == ">=":
            passed = float(value) >= float(threshold)
        elif operator == "<=":
            passed = float(value) <= float(threshold)
        else:  # pragma: no cover
            raise V7PilotIntegrityError(f"unsupported frozen gate operator: {operator}")
        results.append({
            "gate_id": gate_id,
            "measurement_id": measurement_id,
            "state": state,
            "observed_value": value,
            "operator": operator,
            "threshold": threshold,
            "upper_threshold": upper,
            "passed": passed,
            "reason": measurement["reason"],
        })
    return results


def _validate_evaluation(
    evaluation: dict[str, Any],
    frozen_arm: dict[str, Any],
    *,
    policy_payload: bytes | None,
    policy_source_path: str | None,
    source_git_sha: str,
    repo_root: Path,
    verify_repository: bool,
) -> dict[str, Any]:
    context = f"evaluation[{frozen_arm['arm_id']}]"
    if evaluation.get("schema_version") != EVALUATION_SCHEMA:
        raise V7PilotIntegrityError(f"{context} schema mismatch")
    if evaluation.get("evidence_scope") != "SOFTWARE_TRAINING_ENV_DEVELOPMENT_EVALUATION_ONLY":
        raise V7PilotIntegrityError(f"{context} evidence_scope mismatch")
    state = _evaluation_state(evaluation.get("status"))
    if evaluation.get("profile_id") != frozen_arm["profile_id"]:
        raise V7PilotIntegrityError(f"{context} profile_id mismatch")
    if evaluation.get("episodes") != 30 or evaluation.get("seed_base") != 18000:
        raise V7PilotIntegrityError(f"{context} frozen episode/seed schedule mismatch")
    if _evaluation_protocol_arm(
        evaluation.get("pilot_protocol"),
        context + ".pilot_protocol",
        require_artifact_identity=state == "COMPLETED",
    ) != frozen_arm["arm_id"]:
        raise V7PilotIntegrityError(f"{context} pilot arm mismatch")
    eval_git_sha = _evaluation_git_sha(evaluation, context)
    if eval_git_sha != source_git_sha:
        raise V7PilotIntegrityError(f"{context} Git source differs from training")
    source_files = _validate_source_files(
        evaluation.get("source_files"),
        context + ".source_files",
        repo_root=repo_root,
        verify_repository=verify_repository,
    )
    if state == "COMPLETED":
        interface = _require_object(
            evaluation.get("action_interface"), context + ".action_interface"
        )
        expected_interface = {
            "pilot_arm_id": frozen_arm["arm_id"],
            "action_interface_id": frozen_arm["action_interface_id"],
            "action_scale_rad": frozen_arm["action_scale_rad"],
            "low_pass_alpha": frozen_arm["low_pass_alpha"],
            "rate_limit_normalized_per_control_step": frozen_arm[
                "rate_limit_normalized_per_control_step"
            ],
            "previous_action_semantics": "PREVIOUS_APPLIED_NORMALIZED_ACTION",
        }
        for key, expected in expected_interface.items():
            if interface.get(key) != expected:
                raise V7PilotIntegrityError(f"{context}.action_interface.{key} mismatch")
    model = _require_object(evaluation.get("model"), context + ".model")
    model_path = _safe_relative_path(model.get("path"), context + ".model.path")
    if policy_payload is None or policy_source_path is None:
        if state == "COMPLETED":
            raise V7PilotIntegrityError(f"{context} completed evaluation lacks training policy")
        expected_missing_model_paths = {
            "policy.zip",
            f"backend/rl/artifacts/{frozen_arm['training_run_id']}/policy.zip",
        }
        if model_path not in expected_missing_model_paths:
            raise V7PilotIntegrityError(f"{context} failed evaluation model path mismatch")
        if model.get("bytes") is not None or model.get("sha256") is not None:
            raise V7PilotIntegrityError(f"{context} missing model binding must be typed null")
    else:
        expected_model_paths = {
            policy_source_path,
            (
                "backend/rl/artifacts/"
                f"{frozen_arm['training_run_id']}/{policy_source_path}"
            ),
        }
        if model_path not in expected_model_paths:
            raise V7PilotIntegrityError(f"{context} evaluated model path mismatch")
        if (
            model.get("bytes") != len(policy_payload)
            or model.get("sha256") != _sha256_bytes(policy_payload)
        ):
            raise V7PilotIntegrityError(f"{context} model bytes/SHA-256 mismatch")
    rows = _require_list(evaluation.get("episode_results"), context + ".episode_results")
    if len(rows) != 30:
        raise V7PilotIntegrityError(f"{context} must preserve exactly 30 terminal records")
    declared_seeds = _require_list(
        evaluation.get("evaluation_seeds"), context + ".evaluation_seeds"
    )
    if len(declared_seeds) != len(set(declared_seeds)):
        raise V7PilotIntegrityError(f"{context} duplicate evaluation seed access")
    for seed in declared_seeds:
        _require_int(seed, context + ".evaluation_seeds[]", minimum=0, maximum=2**63 - 1)
        if seed in RETIRED_SEED_RANGE:
            raise V7PilotIntegrityError(f"{context} accessed retired seed {seed}")
        if seed in SEALED_SEED_RANGE:
            raise V7PilotIntegrityError(f"{context} accessed sealed FORMAL/HOLDOUT seed {seed}")
    if declared_seeds != list(EXPECTED_SEEDS):
        raise V7PilotIntegrityError(f"{context} evaluation seed access log mismatch")
    canonical_rows: list[dict[str, Any]] = []
    seen_seeds: list[int] = []
    for index, row_value in enumerate(rows):
        row_context = f"{context}.episode_results[{index}]"
        row = _require_object(row_value, row_context)
        seed = _require_int(row.get("seed"), row_context + ".seed", minimum=0, maximum=2**63 - 1)
        if seed in RETIRED_SEED_RANGE:
            raise V7PilotIntegrityError(f"{context} accessed retired seed {seed}")
        if seed in SEALED_SEED_RANGE:
            raise V7PilotIntegrityError(f"{context} accessed sealed FORMAL/HOLDOUT seed {seed}")
        seen_seeds.append(seed)
        normalized = _canonical_measurements(row, row_context)
        control_trace, trace_receipt = _canonical_control_trace(
            row,
            frozen_arm,
            normalized,
            row_context,
        )
        canonical_rows.append({
            "evaluation_seed": seed,
            "terminal_record_state": normalized["terminal_state"],
            "outcome_state": normalized["outcome_state"],
            "reason": normalized["reason"],
            "measurements": normalized["measurements"],
            "gates": _gate_results(normalized["measurements"]),
            "control_step_trace": control_trace,
            "trace_receipt": trace_receipt,
        })
    if len(seen_seeds) != len(set(seen_seeds)):
        raise V7PilotIntegrityError(f"{context} duplicate evaluation seed")
    if sorted(seen_seeds) != list(EXPECTED_SEEDS):
        raise V7PilotIntegrityError(f"{context} missing or unexpected evaluation seed")
    canonical_rows.sort(key=lambda item: item["evaluation_seed"])
    return {
        "terminal_state": state,
        "terminal_reason": (
            None if state == "COMPLETED" else _terminal_reason(evaluation, f"EVALUATION_{state}")
        ),
        "source_git_sha": eval_git_sha,
        "source_files": source_files,
        "accessed_evaluation_seeds": list(declared_seeds),
        "episodes": canonical_rows,
    }


def _state_counts(values: list[str], states: tuple[str, ...]) -> dict[str, int]:
    counts = Counter(values)
    return {state: counts[state] for state in states}


def _conditional_statistics(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    measurements = [item["measurements"]["saturation_duty_pct"] for item in episodes]
    observed = [float(item["value"]) for item in measurements if item["state"] == "OBSERVED"]
    if len(observed) == len(EXPECTED_SEEDS):
        return {
            "state": "OBSERVED",
            "n_expected": 30,
            "n_observed": 30,
            "mean": statistics.fmean(observed),
            "sample_standard_deviation": statistics.stdev(observed),
            "reason": None,
        }
    return {
        "state": "NULL",
        "n_expected": 30,
        "n_observed": len(observed),
        "mean": None,
        "sample_standard_deviation": None,
        "reason": "BLOCKED_REQUIRED_OUTCOME_NOT_OBSERVED_NO_COMPLETE_CASE_DELETION",
    }


def _arm_summary(arm: dict[str, Any]) -> dict[str, Any]:
    episodes = arm["episodes"]
    blockers: list[str] = []
    if arm["training_terminal_state"] != "COMPLETED":
        blockers.append("TRAINING_TERMINAL_STATE_" + arm["training_terminal_state"])
    if arm["evaluation_terminal_state"] != "COMPLETED":
        blockers.append("EVALUATION_TERMINAL_STATE_" + arm["evaluation_terminal_state"])
    for episode in episodes:
        seed = episode["evaluation_seed"]
        if episode["terminal_record_state"] != "COMPLETED":
            blockers.append(f"SEED_{seed}_TERMINAL_{episode['terminal_record_state']}")
        if episode["outcome_state"] != "OBSERVED":
            blockers.append(f"SEED_{seed}_OUTCOME_{episode['outcome_state']}")
        for gate in episode["gates"]:
            if gate["passed"] is False:
                blockers.append(f"SEED_{seed}_GATE_{gate['gate_id']}_FAIL")
            elif gate["passed"] is None:
                blockers.append(f"SEED_{seed}_GATE_{gate['gate_id']}_UNOBSERVED")
    return {
        "arm_id": arm["arm_id"],
        "record_count": len(episodes),
        "training_terminal_state": arm["training_terminal_state"],
        "evaluation_terminal_state": arm["evaluation_terminal_state"],
        "terminal_record_state_counts": _state_counts(
            [item["terminal_record_state"] for item in episodes], RETAINED_TERMINAL_STATES
        ),
        "outcome_state_counts": _state_counts(
            [item["outcome_state"] for item in episodes], RETAINED_OUTCOME_STATES
        ),
        "negative_episode_count": sum(
            any(gate["passed"] is False for gate in item["gates"]) for item in episodes
        ),
        "saturation_duty_pct": _conditional_statistics(episodes),
        "eligible": arm["arm_id"] in CANDIDATE_ARM_IDS and not blockers,
        "eligibility_blockers": blockers,
    }


def _paired_contrast(reference: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    reference_rows = {item["evaluation_seed"]: item for item in reference["episodes"]}
    candidate_rows = {item["evaluation_seed"]: item for item in candidate["episodes"]}
    differences: list[dict[str, Any]] = []
    observed: list[float] = []
    for seed in EXPECTED_SEEDS:
        reference_value = reference_rows[seed]["measurements"]["saturation_duty_pct"]
        candidate_value = candidate_rows[seed]["measurements"]["saturation_duty_pct"]
        if reference_value["state"] == candidate_value["state"] == "OBSERVED":
            difference = float(candidate_value["value"]) - float(reference_value["value"])
            observed.append(difference)
            differences.append({
                "evaluation_seed": seed,
                "state": "OBSERVED",
                "value": difference,
                "reason": None,
            })
        else:
            state = (
                "NONFINITE"
                if "NONFINITE" in {reference_value["state"], candidate_value["state"]}
                else "NULL"
            )
            differences.append({
                "evaluation_seed": seed,
                "state": state,
                "value": None,
                "reason": (
                    "PAIRED_REQUIRED_OUTCOME_NOT_OBSERVED:"
                    f"reference={reference_value['state']},candidate={candidate_value['state']}"
                ),
            })
    complete = len(observed) == 30
    return {
        "reference_arm_id": reference["arm_id"],
        "candidate_arm_id": candidate["arm_id"],
        "contrast": "candidate_minus_reference_by_evaluation_seed",
        "state": "OBSERVED" if complete else "NULL",
        "n_expected": 30,
        "n_observed": len(observed),
        "mean_difference": statistics.fmean(observed) if complete else None,
        "sample_standard_deviation": statistics.stdev(observed) if complete else None,
        "reason": None if complete else "BLOCKED_REQUIRED_PAIR_NOT_OBSERVED_NO_COMPLETE_CASE_DELETION",
        "differences": differences,
    }


def _semantic_blockers(arms: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for arm in arms:
        arm_id = arm["arm_id"]
        if arm["training_terminal_state"] != "COMPLETED":
            blockers.append(f"{arm_id}:TRAINING_{arm['training_terminal_state']}")
        if arm["evaluation_terminal_state"] != "COMPLETED":
            blockers.append(f"{arm_id}:EVALUATION_{arm['evaluation_terminal_state']}")
        for episode in arm["episodes"]:
            seed = episode["evaluation_seed"]
            if episode["terminal_record_state"] != "COMPLETED":
                blockers.append(f"{arm_id}:SEED_{seed}_{episode['terminal_record_state']}")
            if episode["outcome_state"] != "OBSERVED":
                blockers.append(f"{arm_id}:SEED_{seed}_{episode['outcome_state']}")
    return blockers


def _build_summary(raw: dict[str, Any]) -> dict[str, Any]:
    arms = raw["arms"]
    arm_summaries = [_arm_summary(arm) for arm in arms]
    by_id = {item["arm_id"]: item for item in arms}
    summary_by_id = {item["arm_id"]: item for item in arm_summaries}
    contrasts = [
        _paired_contrast(by_id[ARM_IDS[0]], by_id[candidate_id])
        for candidate_id in CANDIDATE_ARM_IDS
    ]
    semantic_blockers = _semantic_blockers(arms)
    selected: str | None = None
    if semantic_blockers:
        selection_status = "PILOT_RETAINED_SEMANTIC_BLOCKER"
    else:
        eligible = [
            candidate_id
            for candidate_id in CANDIDATE_ARM_IDS
            if summary_by_id[candidate_id]["eligible"]
        ]
        if not eligible:
            selection_status = "PILOT_COMPLETE_NEGATIVE_RESULT_NO_CANDIDATE"
        elif len(eligible) == 1:
            selected = eligible[0]
            selection_status = "PILOT_COMPLETE_CANDIDATE_SELECTED"
        else:
            means = {
                candidate_id: summary_by_id[candidate_id]["saturation_duty_pct"]["mean"]
                for candidate_id in eligible
            }
            if means[eligible[0]] == means[eligible[1]]:
                selection_status = "PILOT_COMPLETE_NO_SELECTION_EXACT_TIE"
            else:
                selected = min(eligible, key=lambda arm_id: means[arm_id])
                selection_status = "PILOT_COMPLETE_CANDIDATE_SELECTED"
    return {
        "schema_version": SUMMARY_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": raw["protocol_sha256"],
        "source_git_sha_pre": raw["source_git_sha_pre"],
        "source_git_sha_post": raw["source_git_sha_post"],
        "source_dirty_pre": False,
        "source_dirty_post": False,
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "validation_status": "NOT_PHYSICALLY_VALIDATED",
        "evidence_complete": True,
        "pilot_planning_ready": not semantic_blockers,
        "selection_status": selection_status,
        "selected_candidate_arm_id": selected,
        "arm_summaries": arm_summaries,
        "paired_contrasts": contrasts,
        "semantic_blockers": semantic_blockers,
        "confidence_interval": "NOT_COMPUTED_DEVELOPMENT_PILOT",
        "method_level_power_ready": False,
        "formal_sample_size_decision": "BLOCKED_INDEPENDENT_TRAINING_SEED_VARIANCE_NOT_ESTIMATED",
        "paper_data_ready": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def _write_bytes(path: Path, payload: bytes) -> None:
    if path.exists():
        raise V7PilotIntegrityError(f"refusing to overwrite artifact: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    if path.stat().st_size != len(payload) or sha256_file(path) != _sha256_bytes(payload):
        raise V7PilotIntegrityError(f"artifact readback mismatch: {path.name}")


def _json_bytes(payload: Any) -> bytes:
    try:
        return (
            json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise V7PilotIntegrityError("derived payload is not strict finite JSON") from exc


def _write_json(path: Path, payload: Any) -> None:
    _write_bytes(path, _json_bytes(payload))


def _inventory_record(root: Path, path: Path, role: str) -> dict[str, Any]:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
        raise V7PilotIntegrityError(f"inventory artifact escapes bundle: {path.name}")
    return {
        "role": role,
        "path": resolved.relative_to(resolved_root).as_posix(),
        "bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def _run_replay(
    protocol_path: Path,
    raw_path: Path,
    summary_path: Path,
    *,
    cwd: Path,
) -> dict[str, Any]:
    if not REPLAY_SCRIPT.is_file():
        raise V7PilotIntegrityError("stdlib-only replay script is missing")
    command = [
        sys.executable,
        "-I",
        "-S",
        str(REPLAY_SCRIPT),
        str(protocol_path),
        str(raw_path),
        str(summary_path),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=REPLAY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise V7PilotIntegrityError("stdlib-only replay process failed to run") from exc
    if len(completed.stdout.encode("utf-8")) > MAX_REPLAY_STDOUT_BYTES:
        raise V7PilotIntegrityError("stdlib-only replay stdout exceeds bounded size")
    replay = _load_json_text_strict(completed.stdout, "stdlib-only replay stdout")
    if completed.returncode != 0 or completed.stderr != "":
        raise V7PilotIntegrityError(
            "stdlib-only replay failed: "
            f"returncode={completed.returncode}, stderr={completed.stderr[:500]!r}, "
            f"status={replay.get('status')!r}"
        )
    expected = {
        "schema_version": REPLAY_SCHEMA,
        "status": "PASS",
        "exact_identity": True,
        "paper_data_ready": False,
        "claim_boundary": CLAIM_BOUNDARY,
        "protocol_sha256": sha256_file(protocol_path),
        "raw_episodes_sha256": sha256_file(raw_path),
        "pilot_summary_sha256": sha256_file(summary_path),
    }
    for key, value in expected.items():
        if replay.get(key) != value:
            raise V7PilotIntegrityError(f"stdlib-only replay receipt {key} mismatch")
    checks = replay.get("checks")
    if not isinstance(checks, dict) or not checks or not all(value is True for value in checks.values()):
        raise V7PilotIntegrityError("stdlib-only replay checks are incomplete")
    return replay


def _prepare_output_root(output_root: Path, source_run_dirs: list[Path]) -> Path:
    output_root = output_root.resolve()
    if output_root == Path(output_root.anchor) or (output_root / ".git").exists():
        raise V7PilotIntegrityError("output root must be a bounded evidence directory")
    for run_dir in source_run_dirs:
        if output_root == run_dir or output_root.is_relative_to(run_dir):
            raise V7PilotIntegrityError("output root must not be inside a source run directory")
    if output_root.exists():
        if not output_root.is_dir() or any(output_root.iterdir()):
            raise V7PilotIntegrityError("output root must not exist or must be empty")
    else:
        output_root.mkdir(parents=True)
    return output_root


def build_v7_pilot_bundle(
    protocol_path: Path,
    output_root: Path,
    *,
    artifacts_root: Path | None = None,
    repo_root: Path | None = None,
    verify_repository: bool = True,
) -> dict[str, Any]:
    """Snapshot three frozen run directories and build one replayed bundle."""
    protocol_path = protocol_path.resolve()
    if protocol_path.name != "v7_action_interface_pilot_protocol.json":
        raise V7PilotIntegrityError("protocol filename mismatch")
    protocol_bytes = _read_bounded_file(protocol_path, "frozen protocol")
    protocol = _load_json_bytes(protocol_bytes, protocol_path.name)
    protocol_sha = _sha256_bytes(protocol_bytes)
    _validate_protocol(protocol, protocol_sha)
    if repo_root is None:
        repo_root = protocol_path.parents[2]
    repo_root = repo_root.resolve()
    if artifacts_root is None:
        artifacts_root = protocol_path.parent / "artifacts"
    artifacts_root = artifacts_root.resolve()
    frozen_arms = [_require_object(item, "protocol.arm") for item in protocol["arms"]]
    run_dirs = [
        _safe_source_file(
            artifacts_root,
            f"{arm['training_run_id']}/run_manifest.json",
            f"{arm['arm_id']}.run_manifest",
        ).parent
        for arm in frozen_arms
    ]
    output_root = _prepare_output_root(output_root, run_dirs)

    source_snapshots: list[dict[str, Any]] = []
    source_git_sha: str | None = None
    canonical_manifest_sources: dict[str, str] | None = None
    canonical_evaluation_sources: dict[str, str] | None = None
    for frozen_arm, run_dir in zip(frozen_arms, run_dirs, strict=True):
        manifest_path = _safe_source_file(run_dir, "run_manifest.json", "training manifest")
        manifest_bytes = _read_bounded_file(manifest_path, "training manifest")
        manifest = _load_json_bytes(manifest_bytes, manifest_path.name)
        training = _validate_training_manifest(
            manifest,
            frozen_arm,
            protocol=protocol,
            protocol_bytes=protocol_bytes,
            run_dir=run_dir,
            repo_root=repo_root,
            verify_repository=verify_repository,
        )
        if source_git_sha is None:
            source_git_sha = training["source_git_sha"]
        elif source_git_sha != training["source_git_sha"]:
            raise V7PilotIntegrityError("training arms use different Git source identities")
        if canonical_manifest_sources is None:
            canonical_manifest_sources = training["source_files"]
        elif canonical_manifest_sources != training["source_files"]:
            raise V7PilotIntegrityError("training arms use different source file identities")
        evaluation_path = _safe_source_file(
            run_dir,
            "evaluation_dev18000_18029.json",
            f"{frozen_arm['arm_id']}.evaluation",
        )
        evaluation_bytes = _read_bounded_file(evaluation_path, "evaluation artifact")
        evaluation_payload = _load_json_bytes(evaluation_bytes, evaluation_path.name)
        evaluation = _validate_evaluation(
            evaluation_payload,
            frozen_arm,
            policy_payload=training["policy_payload"],
            policy_source_path=training["policy_source_path"],
            source_git_sha=training["source_git_sha"],
            repo_root=repo_root,
            verify_repository=verify_repository,
        )
        if canonical_evaluation_sources is None:
            canonical_evaluation_sources = evaluation["source_files"]
        elif canonical_evaluation_sources != evaluation["source_files"]:
            raise V7PilotIntegrityError("evaluation arms use different source file identities")
        for path, digest in evaluation["source_files"].items():
            if path in training["source_files"] and training["source_files"][path] != digest:
                raise V7PilotIntegrityError(f"training/evaluation source identity drift: {path}")
        source_snapshots.append({
            "frozen_arm": frozen_arm,
            "run_dir": run_dir,
            "manifest_bytes": manifest_bytes,
            "training": training,
            "evaluation_bytes": evaluation_bytes,
            "evaluation": evaluation,
        })
    if source_git_sha is None:  # pragma: no cover - protocol always has three arms
        raise V7PilotIntegrityError("no training source identity")
    if verify_repository:
        _validate_live_repository(repo_root, source_git_sha)

    bundle_protocol_path = output_root / "protocol.json"
    _write_bytes(bundle_protocol_path, protocol_bytes)
    source_index_arms: list[dict[str, Any]] = []
    raw_arms: list[dict[str, Any]] = []
    inventory_paths: list[tuple[Path, str]] = [(bundle_protocol_path, "protocol")]
    for snapshot in source_snapshots:
        frozen_arm = snapshot["frozen_arm"]
        arm_id = frozen_arm["arm_id"]
        arm_root = output_root / "arms" / arm_id
        manifest_output = arm_root / "training_manifest.json"
        evaluation_output = arm_root / "evaluation_dev18000_18029.json"
        _write_bytes(manifest_output, snapshot["manifest_bytes"])
        _write_bytes(evaluation_output, snapshot["evaluation_bytes"])
        inventory_paths.extend([
            (manifest_output, f"{arm_id}.training_manifest"),
            (evaluation_output, f"{arm_id}.evaluation"),
        ])
        training = snapshot["training"]
        policy_output: Path | None = None
        if training["policy_payload"] is not None:
            policy_output = arm_root / "policy.zip"
            _write_bytes(policy_output, training["policy_payload"])
            inventory_paths.append((policy_output, f"{arm_id}.trained_policy"))
            policy_binding = _artifact_binding(
                state="PRESENT",
                path=policy_output.relative_to(output_root).as_posix(),
                payload=training["policy_payload"],
                reason=None,
            )
        else:
            policy_binding = _artifact_binding(
                state="NULL",
                path=None,
                payload=None,
                reason=training["policy_reason"],
            )
        manifest_binding = _artifact_binding(
            state="PRESENT",
            path=manifest_output.relative_to(output_root).as_posix(),
            payload=snapshot["manifest_bytes"],
            reason=None,
        )
        evaluation_binding = _artifact_binding(
            state="PRESENT",
            path=evaluation_output.relative_to(output_root).as_posix(),
            payload=snapshot["evaluation_bytes"],
            reason=None,
        )
        source_index_arms.append({
            "arm_id": arm_id,
            "training_run_id": frozen_arm["training_run_id"],
            "source_run_path": frozen_arm["training_run_id"],
            "training_manifest": manifest_binding,
            "trained_policy": policy_binding,
            "evaluation": evaluation_binding,
        })
        raw_arms.append({
            "arm_id": arm_id,
            "profile_id": frozen_arm["profile_id"],
            "environment_id": frozen_arm["environment_id"],
            "training_run_id": frozen_arm["training_run_id"],
            "training_terminal_state": training["terminal_state"],
            "training_terminal_reason": training["terminal_reason"],
            "actual_total_timesteps": training["actual_total_timesteps"],
            "evaluation_terminal_state": snapshot["evaluation"]["terminal_state"],
            "evaluation_terminal_reason": snapshot["evaluation"]["terminal_reason"],
            "expected_evaluation_seeds": list(EXPECTED_SEEDS),
            "accessed_evaluation_seeds": snapshot["evaluation"][
                "accessed_evaluation_seeds"
            ],
            "artifacts": {
                "training_manifest": manifest_binding,
                "trained_policy": policy_binding,
                "evaluation": evaluation_binding,
            },
            "episodes": snapshot["evaluation"]["episodes"],
        })
    source_index = {
        "schema_version": SOURCE_INDEX_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": protocol_sha,
        "source_git_sha_pre": source_git_sha,
        "source_git_sha_post": source_git_sha,
        "source_dirty_pre": False,
        "source_dirty_post": False,
        "run_class": "DEVELOPMENT",
        "data_partition": "DEVELOPMENT",
        "arms": source_index_arms,
        "paper_data_ready": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    source_index_path = output_root / "source_index.json"
    _write_json(source_index_path, source_index)
    inventory_paths.append((source_index_path, "source_index"))
    raw = {
        "schema_version": RAW_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": protocol_sha,
        "source_git_sha_pre": source_git_sha,
        "source_git_sha_post": source_git_sha,
        "source_dirty_pre": False,
        "source_dirty_post": False,
        "run_class": "DEVELOPMENT",
        "data_partition": "DEVELOPMENT",
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "validation_status": "NOT_PHYSICALLY_VALIDATED",
        "expected_arm_count": 3,
        "expected_episodes_per_arm": 30,
        "retained_terminal_states": list(RETAINED_TERMINAL_STATES),
        "retained_outcome_states": list(RETAINED_OUTCOME_STATES),
        "arms": raw_arms,
        "paper_data_ready": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    raw_path = output_root / "raw_episodes.json"
    _write_json(raw_path, raw)
    inventory_paths.append((raw_path, "raw_episodes"))
    summary = _build_summary(raw)
    summary_path = output_root / "pilot_summary.json"
    _write_json(summary_path, summary)
    inventory_paths.append((summary_path, "pilot_summary"))
    replay = _run_replay(
        bundle_protocol_path,
        raw_path,
        summary_path,
        cwd=output_root,
    )
    replay_path = output_root / "replay_receipt.json"
    _write_json(replay_path, replay)
    inventory_paths.append((replay_path, "independent_replay_receipt"))
    artifacts = [
        _inventory_record(output_root, path, role)
        for path, role in sorted(inventory_paths, key=lambda item: item[0].as_posix())
    ]
    criteria = [
        {"criterion_id": criterion_id, "passed": True, "detail": detail}
        for criterion_id, detail in zip(
            ACCEPTANCE_IDS,
            (
                "frozen protocol and exact three-arm identity verified",
                "recorded Git pre/post SHA identical and non-ignored worktree clean",
                "warm start, profile, common seed and requested/realized budget verified",
                "exact DEV seeds 18000-18029 retained for every arm",
                "terminal and typed outcome states retained without imputation",
                "six frozen gates reconstructed episode by episode",
                "conditional sample SD and paired differences include power blocker",
                "safe bundle inventory has bytes and SHA-256 readback",
                "python -I -S replay reconstructed the primary summary exactly",
                "SIM_ONLY claim boundary and paper_data_ready=false retained",
            ),
            strict=True,
        )
    ]
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": protocol_sha,
        "validation_status": "PILOT_CONTRACT_VALID",
        "contract_valid": True,
        "evidence_complete": True,
        "pilot_planning_ready": summary["pilot_planning_ready"],
        "selection_status": summary["selection_status"],
        "selected_candidate_arm_id": summary["selected_candidate_arm_id"],
        "semantic_blockers": summary["semantic_blockers"],
        "source_git_sha_pre": source_git_sha,
        "source_git_sha_post": source_git_sha,
        "source_dirty_pre": False,
        "source_dirty_post": False,
        "criteria": criteria,
        "artifacts": artifacts,
        "method_level_power_ready": False,
        "formal_sample_size_decision": "BLOCKED_INDEPENDENT_TRAINING_SEED_VARIANCE_NOT_ESTIMATED",
        "paper_data_ready": False,
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "validation_boundary": "NOT_PHYSICALLY_VALIDATED",
        "claim_boundary": CLAIM_BOUNDARY,
    }
    receipt_path = output_root / "pilot_receipt.json"
    _write_json(receipt_path, receipt)
    validate_v7_pilot_bundle(receipt_path)
    return receipt


def _validate_inventory(root: Path, receipt: dict[str, Any]) -> dict[str, Path]:
    artifacts = _require_list(receipt.get("artifacts"), "receipt.artifacts")
    paths: dict[str, Path] = {}
    roles: set[str] = set()
    casefold_paths: set[str] = set()
    for index, record_value in enumerate(artifacts):
        context = f"receipt.artifacts[{index}]"
        record = _require_object(record_value, context)
        if set(record) != {"role", "path", "bytes", "sha256"}:
            raise V7PilotIntegrityError(f"{context} fields mismatch")
        role = _require_string(record["role"], context + ".role")
        path_text = _safe_relative_path(record["path"], context + ".path")
        if role in roles or path_text.casefold() in casefold_paths:
            raise V7PilotIntegrityError("duplicate/case-colliding inventory role or path")
        roles.add(role)
        casefold_paths.add(path_text.casefold())
        path = _safe_source_file(root, path_text, context + ".path")
        expected_bytes = _require_int(
            record["bytes"], context + ".bytes", minimum=1, maximum=MAX_ARTIFACT_BYTES
        )
        expected_sha = _require_string(record["sha256"], context + ".sha256", pattern=SHA256_PATTERN)
        if path.stat().st_size != expected_bytes or sha256_file(path) != expected_sha:
            raise V7PilotIntegrityError(f"bundle artifact bytes/SHA-256 mismatch: {path_text}")
        paths[role] = path
    discovered: set[str] = set()
    entry_count = 0
    for directory, directories, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        for name in list(directories) + list(filenames):
            entry_count += 1
            if entry_count > 1000:
                raise V7PilotIntegrityError("bundle entry count exceeds bound")
            candidate = directory_path / name
            if _is_link_or_junction(candidate):
                raise V7PilotIntegrityError("bundle contains link/reparse point")
        for filename in filenames:
            discovered.add((directory_path / filename).relative_to(root).as_posix())
    expected = {path.relative_to(root).as_posix() for path in paths.values()} | {"pilot_receipt.json"}
    if discovered != expected:
        raise V7PilotIntegrityError(
            f"bundle contains missing or unindexed files: {sorted(discovered ^ expected)}"
        )
    return paths


def _binding_for_inventory_path(
    root: Path,
    path: Path,
) -> dict[str, Any]:
    payload = _read_bounded_file(path, "bundle inventory artifact")
    return _artifact_binding(
        state="PRESENT",
        path=path.relative_to(root).as_posix(),
        payload=payload,
        reason=None,
    )


def _validate_source_index_deep(
    source_index: dict[str, Any],
    *,
    root: Path,
    paths: dict[str, Path],
    protocol: dict[str, Any],
    raw: dict[str, Any],
) -> None:
    expected_keys = {
        "schema_version",
        "protocol_id",
        "protocol_sha256",
        "source_git_sha_pre",
        "source_git_sha_post",
        "source_dirty_pre",
        "source_dirty_post",
        "run_class",
        "data_partition",
        "arms",
        "paper_data_ready",
        "claim_boundary",
    }
    if set(source_index) != expected_keys:
        raise V7PilotIntegrityError("source index fields mismatch")
    expected_identity = {
        "schema_version": SOURCE_INDEX_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": PROTOCOL_SHA256,
        "source_dirty_pre": False,
        "source_dirty_post": False,
        "run_class": "DEVELOPMENT",
        "data_partition": "DEVELOPMENT",
        "paper_data_ready": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    for key, expected in expected_identity.items():
        if source_index.get(key) != expected:
            raise V7PilotIntegrityError(f"source index {key} mismatch")
    pre_sha = _require_string(
        source_index.get("source_git_sha_pre"),
        "source_index.source_git_sha_pre",
        pattern=GIT_SHA_PATTERN,
    )
    if source_index.get("source_git_sha_post") != pre_sha:
        raise V7PilotIntegrityError("source index Git pre/post identity drift")
    source_arms = _require_list(source_index["arms"], "source_index.arms")
    if len(source_arms) != 3:
        raise V7PilotIntegrityError("source index must contain exactly three arms")
    raw_arms = _require_list(raw.get("arms"), "raw.arms")
    raw_by_id = {
        item.get("arm_id"): item
        for item in raw_arms
        if isinstance(item, dict)
    }
    protocol_by_id = {item["arm_id"]: item for item in protocol["arms"]}
    manifest_source_identity: dict[str, str] | None = None
    evaluation_source_identity: dict[str, str] | None = None
    expected_roles = {
        "protocol",
        "source_index",
        "raw_episodes",
        "pilot_summary",
        "independent_replay_receipt",
    }
    seen_arm_ids: list[str] = []
    for index, arm_value in enumerate(source_arms):
        context = f"source_index.arms[{index}]"
        arm = _require_object(arm_value, context)
        if set(arm) != {
            "arm_id",
            "training_run_id",
            "source_run_path",
            "training_manifest",
            "trained_policy",
            "evaluation",
        }:
            raise V7PilotIntegrityError(f"{context} fields mismatch")
        arm_id = _require_string(arm["arm_id"], context + ".arm_id")
        seen_arm_ids.append(arm_id)
        if arm_id not in protocol_by_id or arm_id not in raw_by_id:
            raise V7PilotIntegrityError(f"{context} unexpected arm identity")
        frozen_arm = protocol_by_id[arm_id]
        if (
            arm["training_run_id"] != frozen_arm["training_run_id"]
            or arm["source_run_path"] != frozen_arm["training_run_id"]
        ):
            raise V7PilotIntegrityError(f"{context} run identity mismatch")
        _safe_relative_path(arm["source_run_path"], context + ".source_run_path")
        raw_arm = raw_by_id[arm_id]
        role_map = {
            "training_manifest": f"{arm_id}.training_manifest",
            "evaluation": f"{arm_id}.evaluation",
        }
        for binding_name, role in role_map.items():
            expected_roles.add(role)
            if role not in paths:
                raise V7PilotIntegrityError(f"source-indexed role missing: {role}")
            expected_binding = _binding_for_inventory_path(root, paths[role])
            if arm[binding_name] != expected_binding:
                raise V7PilotIntegrityError(f"{context}.{binding_name} inventory drift")
            if raw_arm["artifacts"][binding_name] != expected_binding:
                raise V7PilotIntegrityError(f"raw/source-index {binding_name} binding drift")
        policy_binding = _require_object(arm["trained_policy"], context + ".trained_policy")
        policy_role = f"{arm_id}.trained_policy"
        if policy_binding.get("state") == "PRESENT":
            expected_roles.add(policy_role)
            if policy_role not in paths:
                raise V7PilotIntegrityError(f"source-indexed role missing: {policy_role}")
            expected_policy_binding = _binding_for_inventory_path(root, paths[policy_role])
            if policy_binding != expected_policy_binding:
                raise V7PilotIntegrityError(f"{context}.trained_policy inventory drift")
        elif policy_binding.get("state") == "NULL":
            if policy_role in paths:
                raise V7PilotIntegrityError(f"NULL policy has inventoried artifact: {policy_role}")
            expected_policy_binding = policy_binding
            if any(policy_binding.get(key) is not None for key in ("path", "bytes", "sha256")):
                raise V7PilotIntegrityError(f"{context}.trained_policy NULL payload mismatch")
            _require_string(policy_binding.get("reason"), context + ".trained_policy.reason")
        else:
            raise V7PilotIntegrityError(f"{context}.trained_policy state mismatch")
        if raw_arm["artifacts"]["trained_policy"] != expected_policy_binding:
            raise V7PilotIntegrityError("raw/source-index trained policy binding drift")

        manifest_bytes = _read_bounded_file(paths[role_map["training_manifest"]], "copied manifest")
        manifest = _load_json_bytes(manifest_bytes, "copied training manifest")
        training = _validate_training_manifest(
            manifest,
            frozen_arm,
            protocol=protocol,
            protocol_bytes=_read_bounded_file(paths["protocol"], "bundle protocol"),
            run_dir=paths[role_map["training_manifest"]].parent,
            repo_root=root,
            verify_repository=False,
        )
        evaluation_payload = load_json_object_strict(paths[role_map["evaluation"]])
        evaluation = _validate_evaluation(
            evaluation_payload,
            frozen_arm,
            policy_payload=training["policy_payload"],
            policy_source_path=training["policy_source_path"],
            source_git_sha=training["source_git_sha"],
            repo_root=root,
            verify_repository=False,
        )
        for path, digest in evaluation["source_files"].items():
            if path in training["source_files"] and training["source_files"][path] != digest:
                raise V7PilotIntegrityError(
                    f"copied training/evaluation source identity drift: {path}"
                )
        if training["source_git_sha"] != source_index["source_git_sha_pre"]:
            raise V7PilotIntegrityError(f"{context} source Git SHA mismatch")
        if manifest_source_identity is None:
            manifest_source_identity = training["source_files"]
        elif manifest_source_identity != training["source_files"]:
            raise V7PilotIntegrityError("copied training source identities differ across arms")
        if evaluation_source_identity is None:
            evaluation_source_identity = evaluation["source_files"]
        elif evaluation_source_identity != evaluation["source_files"]:
            raise V7PilotIntegrityError("copied evaluation source identities differ across arms")
        expected_raw_projection = {
            "training_terminal_state": training["terminal_state"],
            "training_terminal_reason": training["terminal_reason"],
            "actual_total_timesteps": training["actual_total_timesteps"],
            "evaluation_terminal_state": evaluation["terminal_state"],
            "evaluation_terminal_reason": evaluation["terminal_reason"],
            "expected_evaluation_seeds": list(EXPECTED_SEEDS),
            "accessed_evaluation_seeds": evaluation["accessed_evaluation_seeds"],
            "episodes": evaluation["episodes"],
        }
        for key, expected in expected_raw_projection.items():
            if raw_arm.get(key) != expected:
                raise V7PilotIntegrityError(f"copied source/raw projection mismatch: {arm_id}.{key}")
    if tuple(seen_arm_ids) != ARM_IDS:
        raise V7PilotIntegrityError("source index arm order/identity mismatch")
    if set(paths) != expected_roles:
        raise V7PilotIntegrityError(
            f"unexpected or missing artifact roles: {sorted(set(paths) ^ expected_roles)}"
        )


def validate_v7_pilot_bundle(receipt_path: Path) -> dict[str, Any]:
    """Recheck exact inventory, raw summary, and isolated replay binding."""
    receipt_path = receipt_path.resolve()
    if receipt_path.name != "pilot_receipt.json" or not receipt_path.is_file():
        raise V7PilotIntegrityError("receipt path must name pilot_receipt.json")
    receipt = load_json_object_strict(receipt_path)
    receipt_keys = {
        "schema_version",
        "protocol_id",
        "protocol_sha256",
        "validation_status",
        "contract_valid",
        "evidence_complete",
        "pilot_planning_ready",
        "selection_status",
        "selected_candidate_arm_id",
        "semantic_blockers",
        "source_git_sha_pre",
        "source_git_sha_post",
        "source_dirty_pre",
        "source_dirty_post",
        "criteria",
        "artifacts",
        "method_level_power_ready",
        "formal_sample_size_decision",
        "paper_data_ready",
        "evidence_scope",
        "validation_boundary",
        "claim_boundary",
    }
    if set(receipt) != receipt_keys:
        raise V7PilotIntegrityError("receipt fields mismatch")
    expected_receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": PROTOCOL_SHA256,
        "validation_status": "PILOT_CONTRACT_VALID",
        "contract_valid": True,
        "evidence_complete": True,
        "source_dirty_pre": False,
        "source_dirty_post": False,
        "method_level_power_ready": False,
        "formal_sample_size_decision": "BLOCKED_INDEPENDENT_TRAINING_SEED_VARIANCE_NOT_ESTIMATED",
        "paper_data_ready": False,
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "validation_boundary": "NOT_PHYSICALLY_VALIDATED",
        "claim_boundary": CLAIM_BOUNDARY,
    }
    for key, expected in expected_receipt.items():
        if receipt.get(key) != expected:
            raise V7PilotIntegrityError(f"receipt {key} mismatch")
    pre_sha = _require_string(
        receipt.get("source_git_sha_pre"), "receipt.source_git_sha_pre", pattern=GIT_SHA_PATTERN
    )
    if receipt.get("source_git_sha_post") != pre_sha:
        raise V7PilotIntegrityError("receipt Git pre/post identity drift")
    criteria = _require_list(receipt.get("criteria"), "receipt.criteria")
    if [item.get("criterion_id") for item in criteria if isinstance(item, dict)] != list(ACCEPTANCE_IDS):
        raise V7PilotIntegrityError("receipt acceptance criterion inventory mismatch")
    if any(item.get("passed") is not True for item in criteria if isinstance(item, dict)):
        raise V7PilotIntegrityError("receipt contains failed acceptance criterion")
    root = receipt_path.parent.resolve()
    paths = _validate_inventory(root, receipt)
    required_roles = {"protocol", "source_index", "raw_episodes", "pilot_summary", "independent_replay_receipt"}
    required_roles.update(f"{arm_id}.training_manifest" for arm_id in ARM_IDS)
    required_roles.update(f"{arm_id}.evaluation" for arm_id in ARM_IDS)
    if not required_roles.issubset(paths):
        raise V7PilotIntegrityError(f"required artifact roles missing: {sorted(required_roles - set(paths))}")
    protocol = load_json_object_strict(paths["protocol"])
    _validate_protocol(protocol, sha256_file(paths["protocol"]))
    raw = load_json_object_strict(paths["raw_episodes"])
    summary = load_json_object_strict(paths["pilot_summary"])
    if _build_summary(raw) != summary:
        raise V7PilotIntegrityError("primary summary no longer matches raw episodes")
    replay = load_json_object_strict(paths["independent_replay_receipt"])
    rerun = _run_replay(
        paths["protocol"],
        paths["raw_episodes"],
        paths["pilot_summary"],
        cwd=root,
    )
    if replay != rerun:
        raise V7PilotIntegrityError("stored replay receipt differs from isolated rerun")
    projections = {
        "pilot_planning_ready": summary["pilot_planning_ready"],
        "selection_status": summary["selection_status"],
        "selected_candidate_arm_id": summary["selected_candidate_arm_id"],
        "semantic_blockers": summary["semantic_blockers"],
    }
    for key, expected in projections.items():
        if receipt.get(key) != expected:
            raise V7PilotIntegrityError(f"receipt/summary projection mismatch: {key}")
    source_index = load_json_object_strict(paths["source_index"])
    if (
        source_index.get("schema_version") != SOURCE_INDEX_SCHEMA
        or source_index.get("protocol_sha256") != PROTOCOL_SHA256
        or source_index.get("source_git_sha_pre") != pre_sha
        or source_index.get("source_git_sha_post") != pre_sha
        or source_index.get("paper_data_ready") is not False
        or source_index.get("claim_boundary") != CLAIM_BOUNDARY
    ):
        raise V7PilotIntegrityError("source index identity mismatch")
    _validate_source_index_deep(
        source_index,
        root=root,
        paths=paths,
        protocol=protocol,
        raw=raw,
    )
    return {
        "schema_version": VALIDATION_SCHEMA,
        "validation_status": "BUNDLE_VALID",
        "contract_valid": True,
        "evidence_complete": True,
        "pilot_planning_ready": summary["pilot_planning_ready"],
        "selection_status": summary["selection_status"],
        "artifact_count": len(receipt["artifacts"]),
        "artifact_bytes": sum(item["bytes"] for item in receipt["artifacts"]),
        "receipt_sha256": sha256_file(receipt_path),
        "source_git_sha": pre_sha,
        "method_level_power_ready": False,
        "paper_data_ready": False,
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "claim_boundary": CLAIM_BOUNDARY,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build or validate a frozen v7 action-interface pilot bundle"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("protocol", type=Path)
    build_parser.add_argument("output_root", type=Path)
    build_parser.add_argument("--artifacts-root", type=Path)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "build":
            payload = build_v7_pilot_bundle(
                args.protocol,
                args.output_root,
                artifacts_root=args.artifacts_root,
            )
            exit_code = 0 if payload["pilot_planning_ready"] else 1
        else:
            payload = validate_v7_pilot_bundle(args.receipt)
            exit_code = 0 if payload["pilot_planning_ready"] else 1
    except Exception as exc:
        payload = {
            "schema_version": ERROR_SCHEMA,
            "validation_status": "STRUCTURAL_FAILURE",
            "contract_valid": False,
            "evidence_complete": False,
            "pilot_planning_ready": False,
            "error": f"{type(exc).__name__}: {exc}"[:1000],
            "paper_data_ready": False,
            "evidence_scope": "SIM_ONLY_MUJOCO",
            "claim_boundary": CLAIM_BOUNDARY,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
        raise SystemExit(2) from exc
    print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
