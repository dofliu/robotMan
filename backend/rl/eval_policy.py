"""Evaluate a versioned PPO artifact in its matching training environment.

This is a bounded development evaluator. A command-conditioned training-env
result is not the 500 Hz Live Motion Task acceptance result and cannot enter the
deployable policy registry without a separate adapter and review.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import mujoco
import numpy as np

from controller import quat_to_pitch_roll
from rl.policy_registry import sha256_file
from rl.train_ppo import make_env, resolve_profile


def evaluate(model_path: Path, profile_id: str, episodes: int, seed_base: int) -> dict:
    from stable_baselines3 import PPO

    profile = resolve_profile(profile_id)
    model = PPO.load(str(model_path), device="cpu")
    env = make_env(profile.model_dump(), rank=0, seed_base=seed_base)()
    episode_results = []
    try:
        if model.observation_space.shape != env.observation_space.shape:
            raise ValueError("POLICY_OBSERVATION_CONTRACT_MISMATCH")
        for episode in range(episodes):
            obs, _ = env.reset(seed=seed_base + episode)
            distance_start = float(env.data.qpos[0])
            rewards: list[float] = []
            command_errors: list[float] = []
            final_phase_errors: list[float] = []
            steady_speeds: list[float] = []
            steady_positions: list[float] = []
            lateral_positions: list[float] = []
            saturation_substeps_over_threshold = 0
            saturation_substeps_total = 0
            yaw_values: list[float] = []
            lateral_start = float(env.data.qpos[1])
            terminated = truncated = False
            while not (terminated or truncated):
                action, _ = model.predict(obs, deterministic=True)
                obs, reward, terminated, truncated, info = env.step(action)
                rewards.append(float(reward))
                lateral_positions.append(float(env.data.qpos[1]))
                quat = env.data.qpos[3:7]
                w, x, y, z = (float(item) for item in quat)
                yaw_values.append(float(np.arctan2(
                    2.0 * (w * z + x * y),
                    1.0 - 2.0 * (y * y + z * z),
                )))
                if "saturation_substeps_total" in info:
                    saturation_substeps_over_threshold += int(
                        info["saturation_substeps_over_threshold"]
                    )
                    saturation_substeps_total += int(info["saturation_substeps_total"])
                else:
                    tau_ratio = (
                        np.abs(env.data.actuator_force) / np.maximum(env.tau_lim, 1e-6)
                    )
                    saturation_substeps_over_threshold += int(np.max(tau_ratio) >= 0.95)
                    saturation_substeps_total += 1
                command_vx = float(info.get("command_vx", profile.speed_mps))
                error = abs(float(info["vx"]) - command_vx)
                command_errors.append(error)
                if info.get("command_phase") == "STEADY_WALK":
                    steady_speeds.append(float(info["vx"]))
                    steady_positions.append(float(info["x"]))
                if info.get("command_phase") == "FINAL_STAND":
                    final_phase_errors.append(abs(float(info["vx"])))
            mujoco.mj_forward(env.model, env.data)
            pitch, roll = quat_to_pitch_roll(env.data.qpos[3:7])
            episode_results.append({
                "episode": episode,
                "seed": seed_base + episode,
                "duration_s": round(len(rewards) * 0.02, 3),
                "fell": bool(terminated),
                "distance_m": round(float(env.data.qpos[0]) - distance_start, 6),
                "return": round(float(np.sum(rewards)), 6),
                "mean_abs_command_error_mps": round(float(np.mean(command_errors)), 6),
                "steady_walk_mean_speed_mps": (
                    round(float(np.mean(steady_speeds)), 6) if steady_speeds else None
                ),
                "steady_walk_progress_m": (
                    round(steady_positions[-1] - steady_positions[0], 6)
                    if len(steady_positions) >= 2 else None
                ),
                "final_stand_mean_abs_speed_mps": (
                    round(float(np.mean(final_phase_errors)), 6) if final_phase_errors else None
                ),
                "final_speed_mps": round(float(env.data.qvel[0]), 6),
                "final_pitch_deg": round(float(np.degrees(pitch)), 6),
                "final_roll_deg": round(float(np.degrees(roll)), 6),
                "lateral_drift_m": round(abs(float(env.data.qpos[1]) - lateral_start), 6),
                "max_abs_lateral_m": round(float(np.max(np.abs(lateral_positions))), 6),
                "max_abs_yaw_deg": round(float(np.degrees(np.max(np.abs(yaw_values)))), 6),
                "saturation_duty_pct": round(
                    100.0 * saturation_substeps_over_threshold
                    / max(saturation_substeps_total, 1),
                    6,
                ),
                "saturation_sample_rate_hz": 500.0,
            })
    finally:
        env.close()

    completed = [item for item in episode_results if not item["fell"]]
    final_values = [
        item["final_stand_mean_abs_speed_mps"]
        for item in episode_results
        if item["final_stand_mean_abs_speed_mps"] is not None
    ]
    steady_speed_values = [
        item["steady_walk_mean_speed_mps"]
        for item in episode_results
        if item["steady_walk_mean_speed_mps"] is not None
    ]
    steady_progress_values = [
        item["steady_walk_progress_m"]
        for item in episode_results
        if item["steady_walk_progress_m"] is not None
    ]
    lateral_values = [item["lateral_drift_m"] for item in episode_results]
    saturation_values = [item["saturation_duty_pct"] for item in episode_results]
    speed_gate = all(
        item["steady_walk_mean_speed_mps"] is not None
        and 0.35 <= item["steady_walk_mean_speed_mps"] <= 1.05
        for item in episode_results
    )
    progress_gate = all(
        item["steady_walk_progress_m"] is not None
        and item["steady_walk_progress_m"] >= 1.40
        for item in episode_results
    )
    stop_gate = all(
        item["final_stand_mean_abs_speed_mps"] is not None
        and item["final_stand_mean_abs_speed_mps"] <= 0.15
        for item in episode_results
    )
    lateral_gate = all(item["lateral_drift_m"] <= 0.30 for item in episode_results)
    saturation_gate = all(item["saturation_duty_pct"] <= 30.0 for item in episode_results)
    return {
        "schema_version": "RL_TRAINING_ENV_EVALUATION_V3",
        "evidence_scope": "SOFTWARE_TRAINING_ENV_DEVELOPMENT_EVALUATION_ONLY",
        "model": {
            "path": str(model_path),
            "sha256": f"sha256:{sha256_file(model_path)}",
        },
        "profile_id": profile_id,
        "episodes": episodes,
        "seed_base": seed_base,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "completion_rate": round(len(completed) / episodes, 6),
            "fall_rate": round(1.0 - len(completed) / episodes, 6),
            "mean_duration_s": round(float(np.mean([item["duration_s"] for item in episode_results])), 6),
            "mean_abs_command_error_mps": round(float(np.mean([
                item["mean_abs_command_error_mps"] for item in episode_results
            ])), 6),
            "mean_steady_walk_speed_mps": (
                round(float(np.mean(steady_speed_values)), 6) if steady_speed_values else None
            ),
            "mean_steady_walk_progress_m": (
                round(float(np.mean(steady_progress_values)), 6) if steady_progress_values else None
            ),
            "mean_final_stand_abs_speed_mps": (
                round(float(np.mean(final_values)), 6) if final_values else None
            ),
            "mean_lateral_drift_m": round(float(np.mean(lateral_values)), 6),
            "worst_lateral_drift_m": round(float(np.max(lateral_values)), 6),
            "mean_saturation_duty_pct": round(float(np.mean(saturation_values)), 6),
            "worst_saturation_duty_pct": round(float(np.max(saturation_values)), 6),
            "gate_status": "PASS" if all([
                len(completed) == episodes,
                speed_gate,
                progress_gate,
                stop_gate,
                lateral_gate,
                saturation_gate,
            ]) else "FAIL",
            "gates": {
                "no_fall": len(completed) == episodes,
                "steady_speed": speed_gate,
                "steady_progress": progress_gate,
                "final_stop_speed": stop_gate,
                "lateral_drift": lateral_gate,
                "saturation_duty": saturation_gate,
            },
        },
        "episode_results": episode_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model_path", type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--seed-base", type=int, default=10_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.episodes <= 0 or args.seed_base < 0:
        raise ValueError("episodes 必須 > 0，seed-base 必須 >= 0")
    result = evaluate(args.model_path, args.profile, args.episodes, args.seed_base)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
