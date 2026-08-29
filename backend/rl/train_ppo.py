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

from pydantic import BaseModel, ConfigDict, Field

from rl.policy_registry import sha256_file


RL_DIR = Path(__file__).resolve().parent
PROFILE_PATH = RL_DIR / "training_profiles.json"
SOURCE_FILES = (
    Path(__file__).resolve(),
    RL_DIR / "humanoid_env.py",
    RL_DIR.parent / "controller_rl.py",
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


def make_env(profile_payload: dict, rank: int, seed_base: int):
    def _init():
        from rl.humanoid_env import HumanoidWalkEnv
        env = HumanoidWalkEnv(
            speed=profile_payload["speed_mps"],
            step_length=profile_payload["step_length_m"],
            duty=profile_payload["duty"],
            clearance=profile_payload["clearance_m"],
        )
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--total-timesteps", type=int)
    parser.add_argument("--n-envs", type=int)
    parser.add_argument("--seed-base", type=int)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--smoke", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    profile = resolve_profile(args.profile)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = args.run_id or f"{profile.profile_id}-{timestamp}"
    if not run_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("run-id 只允許英數字、-、_")

    if args.smoke:
        total = args.total_timesteps or 256
        n_envs = args.n_envs or 1
    else:
        total = args.total_timesteps or profile.planned_timesteps
        n_envs = args.n_envs or profile.parallel_envs
    seed_base = profile.seed_base if args.seed_base is None else args.seed_base
    if total <= 0 or n_envs <= 0 or seed_base < 0:
        raise ValueError("total-timesteps/n-envs 必須 > 0，seed-base 必須 >= 0")

    run_dir = RL_DIR / "artifacts" / run_id
    # exist_ok=False 是防覆寫 gate；重跑時必須提供新 run-id。
    run_dir.mkdir(parents=True, exist_ok=False)
    checkpoint_dir = run_dir / "checkpoints"
    checkpoint_dir.mkdir()

    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import CheckpointCallback
    from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv, VecMonitor

    payload = profile.model_dump()
    factories = [make_env(payload, rank, seed_base) for rank in range(n_envs)]
    vector_env = DummyVecEnv(factories) if n_envs == 1 else SubprocVecEnv(factories)
    env = VecMonitor(vector_env)
    model = PPO(
        "MlpPolicy", env,
        learning_rate=3e-4,
        n_steps=128 if args.smoke else 2048,
        batch_size=128 if args.smoke else 8192,
        n_epochs=1 if args.smoke else 5,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=0.002,
        policy_kwargs=dict(net_arch=[256, 256]),
        verbose=1,
        device=args.device,
        seed=seed_base,
    )
    callback = CheckpointCallback(
        save_freq=max((128 if args.smoke else 2_000_000) // n_envs, 1),
        save_path=str(checkpoint_dir),
        name_prefix=profile.profile_id,
    )

    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.time()
    try:
        model.learn(total_timesteps=total, callback=callback, progress_bar=False)
        model.save(str(run_dir / "policy"))
    finally:
        env.close()
    artifact = run_dir / "policy.zip"
    elapsed = time.time() - t0
    manifest = {
        "schema_version": "RL_TRAINING_RUN_V1",
        "run_id": run_id,
        "profile": profile.model_dump(),
        "resolved": {
            "total_timesteps": total,
            "parallel_envs": n_envs,
            "seed_base": seed_base,
            "device": args.device,
            "smoke": args.smoke,
        },
        "status": "PIPELINE_SMOKE_NOT_POLICY_EVIDENCE" if args.smoke else "DEVELOPMENT_TRAINING_UNEVALUATED",
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed, 3),
        "artifact": {
            "relative_path": "policy.zip",
            "bytes": artifact.stat().st_size,
            "sha256": f"sha256:{sha256_file(artifact)}",
        },
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
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(f"run 完成：{run_id}；artifact={artifact}；status={manifest['status']}")


if __name__ == "__main__":
    main()
