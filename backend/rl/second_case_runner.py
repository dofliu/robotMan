"""Training + evaluation driver for ``SECONDCASE-EXPOSURE-CENSORING-WALKER2D-V1`` (PUB-A1).

Every constant comes from the frozen protocol; the CLI accepts *which cell* to
run and *where*, nothing else.  Before a cell runs the driver refuses a dirty
worktree and re-measures the environment against the pinned lock record.  A
failed cell is retained as ``FAILED`` with whatever it produced; it is never
deleted or retried under the same directory.

Usage
-----
    python rl/second_case_runner.py run-cell --arm W2D_A_DIRECT --replicate-index 0 \
        --output-root <runs> --lock-record <lock.json>
    python rl/second_case_runner.py assemble --output-root <runs> --bundle-root <bundle> \
        --lock-record <lock.json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

RL_DIR = Path(__file__).resolve().parent
BACKEND_DIR = RL_DIR.parent
REPOSITORY = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import second_case_exposure_contract as sc  # noqa: E402
from environment_lock import (  # noqa: E402
    EnvironmentLockError,
    capture_environment_lock,
    load_lock_record,
    validate_lock_record,
    verify_environment_lock,
)

PROVENANCE_SCHEMA = "SECOND_CASE_EXPOSURE_CELL_PROVENANCE_V1"


class SecondCaseRunError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# provenance
# --------------------------------------------------------------------------- #


def git_source_identity() -> dict[str, Any]:
    """Same observable as rl/train_ppo.git_source_identity, without importing the trainer."""
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, check=True, capture_output=True, text=True).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=REPOSITORY,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return {"available": False, "git_sha": None, "working_tree_dirty": None, "error": str(exc)}
    return {"available": True, "git_sha": sha, "working_tree_dirty": bool(status), "status_lines": status.splitlines()}


def require_clean_source() -> dict[str, Any]:
    identity = git_source_identity()
    if identity.get("available") is not True or identity.get("working_tree_dirty") is not False or not identity.get("git_sha"):
        raise SecondCaseRunError(f"SECONDCASE_SOURCE_GIT_NOT_CLEAN: {identity}")
    return identity


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def verify_lock_now(lock_record_path: Path, design: dict[str, Any]) -> dict[str, Any]:
    """Re-measure the environment and require identity with the pinned record."""
    pinned = load_lock_record(lock_record_path)
    sc.check_environment_lock(design, pinned)  # class / completeness / threading requirement
    observed = capture_environment_lock()
    verification = verify_environment_lock(pinned, observed)
    if verification.get("environment_lock_match") is not True:
        raise SecondCaseRunError(
            "SECONDCASE_ENVIRONMENT_LOCK_MISMATCH: "
            + json.dumps([f for f in verification.get("findings", []) if f.get("severity") == "LOCK_MISMATCH"], ensure_ascii=False)
        )
    return {
        "environment_locked_sha256": validate_lock_record(pinned)["locked_sha256"],
        "lock_record_sha256": sha256_file(lock_record_path),
        "mismatch_count": verification["mismatch_count"],
        "retained_finding_count": verification["retained_finding_count"],
    }


# --------------------------------------------------------------------------- #
# environment
# --------------------------------------------------------------------------- #


def _lazy_imports():
    import gymnasium as gym
    import numpy as np

    return gym, np


class SharedActionInterface:
    """gymnasium.Wrapper: clip -> first-order low-pass(alpha) -> apply; previous applied action in obs.

    Both arms use this class; alpha = 1.0 is the identity filter.  Built lazily
    so the module can be imported (for its constants) without gymnasium.
    """

    @staticmethod
    def build(alpha: float, threshold: float, recorder: dict[str, Any] | None):
        gym, np = _lazy_imports()

        class _Wrapper(gym.Wrapper):
            def __init__(self, env):
                super().__init__(env)
                self.alpha = float(alpha)
                self.threshold = float(threshold)
                self.recorder = recorder
                low = env.action_space.low.astype(np.float64)
                high = env.action_space.high.astype(np.float64)
                self._low, self._high = low, high
                self._prev = np.zeros(env.action_space.shape, dtype=np.float64)
                obs_space = env.observation_space
                self.observation_space = gym.spaces.Box(
                    low=np.concatenate([obs_space.low.astype(np.float64), low]),
                    high=np.concatenate([obs_space.high.astype(np.float64), high]),
                    dtype=np.float64,
                )

            def _obs(self, obs):
                return np.concatenate([np.asarray(obs, dtype=np.float64), self._prev])

            def reset(self, **kwargs):
                obs, info = self.env.reset(**kwargs)
                self._prev = np.zeros_like(self._prev)
                return self._obs(obs), info

            def step(self, action):
                raw = np.clip(np.asarray(action, dtype=np.float64), self._low, self._high)
                applied = self.alpha * raw + (1.0 - self.alpha) * self._prev
                obs, reward, terminated, truncated, info = self.env.step(applied)
                saturated = np.abs(applied) >= self.threshold
                if self.recorder is not None:
                    self.recorder["raw"].append(raw.copy())
                    self.recorder["applied"].append(applied.copy())
                    self.recorder["saturated"].append(saturated.copy())
                    self.recorder["reward"].append(float(reward))
                    self.recorder["terminated"].append(bool(terminated))
                    self.recorder["truncated"].append(bool(truncated))
                self._prev = applied
                return self._obs(obs), reward, terminated, truncated, info

        return _Wrapper


def make_env(protocol: dict[str, Any], design: dict[str, Any], alpha: float, recorder: dict[str, Any] | None = None):
    gym, _ = _lazy_imports()
    env_spec = protocol["environment"]
    env = gym.make(env_spec["gymnasium_env_id"], **env_spec["gymnasium_make_kwargs"])
    # Pin the plant: the file gymnasium actually loaded must be the frozen one.
    xml = Path(env.unwrapped.fullpath)
    actual = sha256_file(xml)
    if actual != design["plant_asset_sha256"]:
        raise SecondCaseRunError(f"SECONDCASE_PLANT_MISMATCH: {xml.name} {actual} != {design['plant_asset_sha256']}")
    if env.spec.max_episode_steps != design["horizon_steps"]:
        raise SecondCaseRunError("SECONDCASE_HORIZON_MISMATCH")
    for key, expected in env_spec["expected_defaults"].items():
        attr = getattr(env.unwrapped, "_" + key, None)
        if attr is None:
            continue
        if isinstance(expected, list):
            expected = tuple(expected)
        if attr != expected:
            raise SecondCaseRunError(f"SECONDCASE_ENV_DEFAULT_DRIFT: {key}={attr!r} expected {expected!r}")
    wrapper_cls = SharedActionInterface.build(alpha, design["saturation_threshold"], recorder)
    return wrapper_cls(env)


# --------------------------------------------------------------------------- #
# train / evaluate
# --------------------------------------------------------------------------- #


_ACTIVATIONS = ("Tanh", "ReLU")


def wrap_normalizer(training: dict[str, Any], vec):
    """Optionally wrap a vec env in VecNormalize as the frozen recipe demands.

    ``training.normalize`` is absent for the SB3-default recipe (V1) and present
    for a tuned recipe.  Normalization statistics are part of the policy for
    evaluation purposes, so the caller saves them next to ``policy.zip``.
    """
    spec = training.get("normalize")
    if not spec:
        return vec, False
    from stable_baselines3.common.vec_env import VecNormalize

    return (
        VecNormalize(
            vec,
            norm_obs=bool(spec["norm_obs"]),
            norm_reward=bool(spec["norm_reward"]),
            clip_obs=float(spec["clip_obs"]),
            gamma=float(training["hyperparameters"]["gamma"]),
        ),
        True,
    )


def build_model(training: dict[str, Any], vec, seed: int):
    """Construct PPO from the frozen training block only; no value comes from anywhere else."""
    import torch.nn as nn
    from stable_baselines3 import PPO

    hyper = training["hyperparameters"]
    policy_kwargs = None
    spec = training.get("policy_kwargs")
    if spec:
        if spec["activation_fn"] not in _ACTIVATIONS:
            raise SecondCaseRunError(f"unsupported activation {spec['activation_fn']!r}")
        policy_kwargs = {
            "log_std_init": float(spec["log_std_init"]),
            "ortho_init": bool(spec["ortho_init"]),
            "activation_fn": getattr(nn, spec["activation_fn"]),
            "net_arch": {"pi": [int(v) for v in spec["net_arch"]["pi"]], "vf": [int(v) for v in spec["net_arch"]["vf"]]},
        }
    return PPO(
        training["policy"],
        vec,
        learning_rate=hyper["learning_rate"],
        n_steps=hyper["n_steps"],
        batch_size=hyper["batch_size"],
        n_epochs=hyper["n_epochs"],
        gamma=hyper["gamma"],
        gae_lambda=hyper["gae_lambda"],
        clip_range=hyper["clip_range"],
        ent_coef=hyper["ent_coef"],
        vf_coef=hyper["vf_coef"],
        max_grad_norm=hyper["max_grad_norm"],
        normalize_advantage=hyper["normalize_advantage"],
        policy_kwargs=policy_kwargs,
        seed=seed,
        device=training["device"],
        verbose=0,
    )


def normalizer_path_for(policy_path: Path) -> Path:
    return policy_path.with_name("vecnormalize.pkl")


def train_cell(protocol: dict[str, Any], design: dict[str, Any], alpha: float, training_seed: int, policy_path: Path) -> dict[str, Any]:
    import torch
    from stable_baselines3.common.vec_env import DummyVecEnv

    training = protocol["training"]
    torch.set_num_threads(int(training["torch_threads"]))
    torch.use_deterministic_algorithms(True, warn_only=True)
    vec = DummyVecEnv([lambda: make_env(protocol, design, alpha)])
    vec, normalized = wrap_normalizer(training, vec)
    model = build_model(training, vec, training_seed)
    started = time.time()
    model.learn(total_timesteps=int(training["requested_timesteps"]))
    wall = time.time() - started
    realized = int(model.num_timesteps)
    model.save(policy_path)
    normalizer_sha = None
    if normalized:
        vec.save(str(normalizer_path_for(policy_path)))
        normalizer_sha = sha256_file(normalizer_path_for(policy_path))
    vec.close()
    return {
        "realized_timesteps": realized,
        "training_wall_time_s": round(wall, 3),
        "policy_sha256": sha256_file(policy_path),
        "normalizer_sha256": normalizer_sha,
    }


def evaluate_cell(protocol: dict[str, Any], design: dict[str, Any], alpha: float, policy_path: Path, trace_dir: Path) -> list[dict[str, Any]]:
    import numpy as np
    from stable_baselines3 import PPO

    model = PPO.load(policy_path, device=protocol["training"]["device"])
    normalizer = normalizer_path_for(policy_path)
    normalized = bool(protocol["training"].get("normalize"))
    if normalized and not normalizer.is_file():
        raise SecondCaseRunError("SECONDCASE_NORMALIZER_MISSING: recipe trained with VecNormalize but no statistics were saved")
    rows = []
    for seed in design["evaluation_seeds"]:
        recorder = {"raw": [], "applied": [], "saturated": [], "reward": [], "terminated": [], "truncated": []}
        if normalized:
            from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

            venv = DummyVecEnv([lambda: make_env(protocol, design, alpha, recorder)])
            venv = VecNormalize.load(str(normalizer), venv)
            venv.training = False
            venv.norm_reward = False
            venv.seed(int(seed))
            obs = venv.reset()
            done = False
            steps = 0
            while not done:
                action, _ = model.predict(obs, deterministic=True)
                obs, _, dones, _ = venv.step(action)
                done = bool(dones[0])
                steps += 1
                if steps > design["horizon_steps"]:
                    raise SecondCaseRunError("SECONDCASE_TRACE_INCONSISTENT: episode exceeded the horizon")
            venv.close()
        else:
            env = make_env(protocol, design, alpha, recorder)
            obs, _ = env.reset(seed=int(seed))
            terminated = truncated = False
            steps = 0
            while not (terminated or truncated):
                action, _ = model.predict(obs, deterministic=True)
                obs, _, terminated, truncated, _ = env.step(action)
                steps += 1
                if steps > design["horizon_steps"]:
                    raise SecondCaseRunError("SECONDCASE_TRACE_INCONSISTENT: episode exceeded the horizon")
            env.close()
        raw = np.asarray(recorder["raw"], dtype=np.float64)
        applied = np.asarray(recorder["applied"], dtype=np.float64)
        saturated = np.asarray(recorder["saturated"], dtype=bool)
        reward = np.asarray(recorder["reward"], dtype=np.float64)
        term = np.asarray(recorder["terminated"], dtype=bool)
        trunc = np.asarray(recorder["truncated"], dtype=bool)
        trace_dir.mkdir(parents=True, exist_ok=True)
        trace_path = trace_dir / f"seed_{seed}.npz"
        np.savez_compressed(trace_path, raw_action=raw, applied_action=applied, saturated_joint_flags=saturated, reward=reward, terminated=term, truncated=trunc)
        all_finite = bool(np.isfinite(raw).all() and np.isfinite(applied).all() and np.isfinite(reward).all())
        episode_return = 0.0
        for value in reward.tolist():
            episode_return += value
        rows.append(
            sc.episode_row(
                evaluation_seed=int(seed),
                realized_steps=int(raw.shape[0]),
                saturated_joint_steps=int(saturated.sum()),
                terminated=bool(term[-1]),
                truncated=bool(trunc[-1]),
                all_finite=all_finite,
                episode_return=episode_return if all_finite else None,
                trace_sha256=sha256_file(trace_path),
                design=design,
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #


def _write_json(path: Path, payload: Any) -> None:
    path.write_bytes(sc.json_bytes(payload))


def run_cell(args: argparse.Namespace) -> dict[str, Any]:
    protocol = sc.load_protocol(args.protocol)
    design = sc.validate_protocol(protocol)
    if args.arm not in design["arm_ids"]:
        raise SecondCaseRunError(f"unknown arm {args.arm!r}; frozen arms are {design['arm_ids']}")
    if not (0 <= args.replicate_index < design["replicate_count"]):
        raise SecondCaseRunError("replicate index outside the frozen design")
    alpha = design["alphas"][args.arm]
    training_seed = design["training_seeds"][args.replicate_index]

    source_pre = require_clean_source()
    cell_dir = Path(args.output_root).resolve() / args.arm / f"replicate_{args.replicate_index}"
    cell_dir.mkdir(parents=True, exist_ok=False)
    lock_train = verify_lock_now(Path(args.lock_record), design)

    provenance: dict[str, Any] = {
        "schema_version": PROVENANCE_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": sc.PINNED_PROTOCOLS[protocol["protocol_id"]],
        "arm_id": args.arm,
        "replicate_index": args.replicate_index,
        "training_seed": training_seed,
        "low_pass_alpha": alpha,
        "source_git_sha_pre": source_pre["git_sha"],
        "source_dirty_pre": source_pre["working_tree_dirty"],
        "lock_verification_training": lock_train,
        "plant_asset_sha256": design["plant_asset_sha256"],
        "started_at_unix": time.time(),
    }
    cell: dict[str, Any] = {
        "schema_version": sc.CELL_SCHEMA_V2 if design["schema_version"] == sc.PROTOCOL_SCHEMA_V2 else sc.CELL_SCHEMA,
        "arm_id": args.arm,
        "low_pass_alpha": alpha,
        "realized_timesteps": 0,
        "training_terminal_state": "FAILED",
        "evaluation_terminal_state": "FAILED",
        "policy_sha256": None,
        "training_environment_lock_verified": True,
        "evaluation_environment_lock_verified": False,
        "environment_locked_sha256": lock_train["environment_locked_sha256"],
        "evaluation_output_sha256": sc.sha256_bytes(sc.json_bytes([])),
        "episodes": [],
    }
    if design["schema_version"] == sc.PROTOCOL_SCHEMA_V2:
        cell["normalizer_sha256"] = None
    try:
        policy_path = cell_dir / "policy.zip"
        training = train_cell(protocol, design, alpha, training_seed, policy_path)
        provenance["training"] = training
        cell["realized_timesteps"] = training["realized_timesteps"]
        cell["policy_sha256"] = training["policy_sha256"]
        if design["schema_version"] == sc.PROTOCOL_SCHEMA_V2:
            cell["normalizer_sha256"] = training["normalizer_sha256"]
        if training["realized_timesteps"] != design["expected_realized_timesteps"]:
            raise SecondCaseRunError("SECONDCASE_REALIZED_TIMESTEPS_MISMATCH")
        cell["training_terminal_state"] = "COMPLETED"
        lock_eval = verify_lock_now(Path(args.lock_record), design)
        provenance["lock_verification_evaluation"] = lock_eval
        cell["evaluation_environment_lock_verified"] = True
        rows = evaluate_cell(protocol, design, alpha, policy_path, cell_dir / "traces")
        cell["episodes"] = rows
        cell["evaluation_output_sha256"] = sc.sha256_bytes(sc.json_bytes(rows))
        cell["evaluation_terminal_state"] = "COMPLETED"
    except Exception as exc:  # retained, never swallowed
        provenance["failure"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        source_post = git_source_identity()
        provenance["source_git_sha_post"] = source_post.get("git_sha")
        provenance["source_dirty_post"] = source_post.get("working_tree_dirty")
        provenance["finished_at_unix"] = time.time()
        _write_json(cell_dir / "cell_manifest.json", cell)
        _write_json(cell_dir / "cell_provenance.json", provenance)
    if "failure" in provenance:
        raise SecondCaseRunError(f"cell retained as FAILED: {provenance['failure']}")
    return {"cell_dir": str(cell_dir), "training_terminal_state": cell["training_terminal_state"], "evaluation_terminal_state": cell["evaluation_terminal_state"], "episodes": len(cell["episodes"]), "realized_timesteps": cell["realized_timesteps"], "training_wall_time_s": provenance["training"]["training_wall_time_s"]}


def assemble(args: argparse.Namespace) -> dict[str, Any]:
    protocol = sc.load_protocol(args.protocol)
    design = sc.validate_protocol(protocol)
    output_root = Path(args.output_root).resolve()
    bundle_root = Path(args.bundle_root).resolve()
    if bundle_root.exists() and any(bundle_root.iterdir()):
        raise SecondCaseRunError("bundle root must be empty")
    bundle_root.mkdir(parents=True, exist_ok=True)
    git_shas: set[str] = set()
    dirty: set[bool] = set()
    replicates = []
    for index in range(design["replicate_count"]):
        arms = []
        for arm_id in design["arm_ids"]:
            cell_dir = output_root / arm_id / f"replicate_{index}"
            cell = sc.load_json_file(cell_dir / "cell_manifest.json")
            provenance = sc.load_json_file(cell_dir / "cell_provenance.json")
            if provenance["plant_asset_sha256"] != design["plant_asset_sha256"]:
                raise SecondCaseRunError(f"{cell_dir}: plant digest drift")
            git_shas.update({provenance["source_git_sha_pre"], provenance["source_git_sha_post"]})
            dirty.update({bool(provenance["source_dirty_pre"]), bool(provenance["source_dirty_post"])})
            arms.append(cell)
        replicates.append({"replicate_index": index, "training_seed": design["training_seeds"][index], "arms": arms})
    if len(git_shas) != 1 or dirty != {False}:
        raise SecondCaseRunError(f"SECONDCASE_SOURCE_GIT_NOT_CLEAN: shas={sorted(git_shas)} dirty={sorted(dirty)}")
    (git_sha,) = git_shas
    lock_src = Path(args.lock_record)
    protocol_bytes = Path(args.protocol).read_bytes()
    (bundle_root / "second_case_exposure_protocol.json").write_bytes(protocol_bytes)
    (bundle_root / "environment_lock.json").write_bytes(lock_src.read_bytes())
    raw = {
        "schema_version": sc.RAW_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": sc.sha256_bytes(protocol_bytes),
        "bundle_class": sc.DEVELOPMENT_BUNDLE_CLASS,
        "environment_lock_sha256": sha256_file(lock_src),
        "plant_asset_sha256": design["plant_asset_sha256"],
        "source_git_sha_pre": git_sha,
        "source_git_sha_post": git_sha,
        "source_dirty_pre": False,
        "source_dirty_post": False,
        "replicates": replicates,
    }
    stats = sc.validate_raw_bundle(raw, protocol)
    _write_json(bundle_root / "raw_replicates.json", raw)
    return {"bundle_root": str(bundle_root), "terminal_record_count": stats["terminal_record_count"], "raw_sha256": sha256_file(bundle_root / "raw_replicates.json")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    rc = sub.add_parser("run-cell")
    rc.add_argument("--arm", required=True)
    rc.add_argument("--replicate-index", type=int, required=True)
    rc.add_argument("--output-root", type=Path, required=True)
    rc.add_argument("--lock-record", type=Path, required=True)
    rc.add_argument("--protocol", type=Path, default=sc.DEFAULT_PROTOCOL)
    asm = sub.add_parser("assemble")
    asm.add_argument("--output-root", type=Path, required=True)
    asm.add_argument("--bundle-root", type=Path, required=True)
    asm.add_argument("--lock-record", type=Path, required=True)
    asm.add_argument("--protocol", type=Path, default=sc.DEFAULT_PROTOCOL)
    args = parser.parse_args()
    try:
        payload = run_cell(args) if args.command == "run-cell" else assemble(args)
    except (SecondCaseRunError, sc.SecondCaseError, EnvironmentLockError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
