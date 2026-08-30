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
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rl.policy_registry import resolve_policy, sha256_file


RL_DIR = Path(__file__).resolve().parent
PROFILE_PATH = RL_DIR / "training_profiles.json"
SOURCE_FILES = (
    Path(__file__).resolve(),
    RL_DIR / "humanoid_env.py",
    RL_DIR / "training_profiles.json",
    RL_DIR.parent / "controller_rl.py",
    RL_DIR.parent / "motion_tasks.py",
    RL_DIR.parent / "model_builder.py",
    RL_DIR.parent / "config_schema.py",
)


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
    ] = "fixed_walk_v1"
    task_id: str | None = None
    warm_start_policy_id: str | None = None


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
    if total <= 0 or n_envs <= 0 or seed_base < 0:
        raise ValueError("total-timesteps/n-envs 必須 > 0，seed-base 必須 >= 0")

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
    }
    if args.resume_from is not None and args.warm_start_from is not None:
        raise ValueError("--resume-from 與 --warm-start-from 不可同時使用")
    resume_path = None
    local_warm_start_path = None
    if args.resume_from is not None:
        resume_path = args.resume_from.resolve()
        artifact_root = (RL_DIR / "artifacts").resolve()
        if not resume_path.is_relative_to(artifact_root):
            raise ValueError("resume artifact 必須位於 backend/rl/artifacts")
        if not resume_path.is_file() or resume_path.suffix.lower() != ".zip":
            raise FileNotFoundError("resume policy artifact 不存在或不是 .zip")
        manifest["resume"] = {
            "artifact": str(resume_path.relative_to(RL_DIR)).replace("\\", "/"),
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
        env = VecMonitor(vector_env)
        if args.smoke:
            n_steps, batch_size, n_epochs = 128, 128, 1
            checkpoint_interval = 128
        elif args.preflight:
            n_steps, batch_size, n_epochs = 512, 2048, 2
            checkpoint_interval = 32_768
        else:
            n_steps, batch_size, n_epochs = 2048, 8192, 5
            checkpoint_interval = 2_000_000
        manifest["checkpoint_interval_timesteps"] = checkpoint_interval
        manifest["policy_contract"] = {
            "observation_dim": int(env.observation_space.shape[0]),
            "action_dim": int(env.action_space.shape[0]),
            "algorithm": "PPO_MLP",
            "n_steps_per_env": n_steps,
            "batch_size": batch_size,
            "n_epochs": n_epochs,
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
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        manifest["elapsed_seconds"] = round(time.time() - t0, 3)
        write_manifest(manifest_path, manifest)
    print(f"run 完成：{run_id}；artifact={manifest['artifact']['relative_path']}；status={manifest['status']}")


if __name__ == "__main__":
    main()
