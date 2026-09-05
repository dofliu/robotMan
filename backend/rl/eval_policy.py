"""Evaluate a versioned PPO artifact in its matching training environment.

This is a bounded development evaluator. A command-conditioned training-env
result is not the 500 Hz Live Motion Task acceptance result and cannot enter the
deployable policy registry without a separate adapter and review.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import mujoco
import numpy as np

from controller import quat_to_pitch_roll
from rl.action_interface_v7 import (
    PROTOCOL_ID as V7_PROTOCOL_ID,
    PROTOCOL_PATH as V7_PROTOCOL_PATH,
    load_v7_protocol,
    resolve_v7_action_interface,
)
from rl.policy_registry import sha256_file
from rl.train_ppo import git_source_identity, make_env, resolve_profile


SOURCE_FILES = (
    Path(__file__).resolve(),
    Path(__file__).with_name("humanoid_env.py"),
    Path(__file__).with_name("action_interface_v7.py"),
    V7_PROTOCOL_PATH,
    Path(__file__).with_name("training_profiles.json"),
    Path(__file__).parent.parent / "motion_tasks.py",
    Path(__file__).parent.parent / "model_builder.py",
    Path(__file__).parent.parent / "config_schema.py",
)


def _finite_round(value, digits: int = 6):
    if value is None:
        return None
    number = float(value)
    return round(number, digits) if math.isfinite(number) else None


def _finite_list(values) -> tuple[list[float | None], bool]:
    sanitized: list[float | None] = []
    saw_nonfinite = False
    for value in values:
        number = float(value)
        if math.isfinite(number):
            sanitized.append(number)
        else:
            sanitized.append(None)
            saw_nonfinite = True
    return sanitized, saw_nonfinite


def _write_json_atomic(path: Path, payload: dict) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    os.replace(temporary, path)


def evaluate(
    model_path: Path,
    profile_id: str,
    episodes: int,
    seed_base: int,
    *,
    pilot_arm_id: str | None = None,
) -> dict:
    from stable_baselines3 import PPO

    started_at = datetime.now(timezone.utc)
    repository = Path(__file__).parents[2]
    model_path = model_path.resolve()
    if not model_path.is_file() or model_path.suffix.lower() != ".zip":
        raise FileNotFoundError("evaluation policy artifact 不存在或不是 .zip")
    profile = resolve_profile(profile_id)
    pilot_protocol = None
    pilot_interface = None
    if pilot_arm_id is not None:
        protocol = load_v7_protocol()
        pilot_interface = resolve_v7_action_interface(pilot_arm_id)
        arm = next(
            item for item in protocol["arms"] if item["arm_id"] == pilot_arm_id
        )
        expected_seeds = protocol["evaluation_design"]["evaluation_seeds"]
        if profile.pilot_protocol_id != V7_PROTOCOL_ID:
            raise ValueError("V7_EVALUATION_PROFILE_PROTOCOL_MISMATCH")
        if profile.pilot_arm_id != pilot_arm_id:
            raise ValueError("V7_EVALUATION_ARM_MISMATCH")
        if pilot_interface.profile_id != profile_id:
            raise ValueError("V7_EVALUATION_PROFILE_MISMATCH")
        if episodes != len(expected_seeds) or seed_base != expected_seeds[0]:
            raise ValueError("V7_EVALUATION_SEED_SCHEDULE_OVERRIDE_FORBIDDEN")
        expected_model_path = (
            Path(__file__).parent / "artifacts" / arm["training_run_id"] / "policy.zip"
        ).resolve()
        if model_path != expected_model_path:
            raise ValueError("V7_EVALUATION_POLICY_PATH_MISMATCH")
        pilot_protocol = {
            "protocol_id": V7_PROTOCOL_ID,
            "arm_id": pilot_arm_id,
            "path": str(V7_PROTOCOL_PATH.relative_to(Path(__file__).parents[2])).replace(
                "\\", "/"
            ),
            "bytes": V7_PROTOCOL_PATH.stat().st_size,
            "sha256": f"sha256:{sha256_file(V7_PROTOCOL_PATH)}",
        }
    source_git_pre = git_source_identity()
    if pilot_interface is not None and (
        source_git_pre.get("available") is not True
        or source_git_pre.get("working_tree_dirty") is not False
        or not source_git_pre.get("git_sha")
    ):
        raise ValueError("V7_EVALUATION_SOURCE_GIT_NOT_CLEAN")
    model = PPO.load(str(model_path), device="cpu")
    env = make_env(profile.model_dump(), rank=0, seed_base=seed_base)()
    episode_results = []
    action_interface_contract = None
    try:
        if model.observation_space.shape != env.observation_space.shape:
            raise ValueError("POLICY_OBSERVATION_CONTRACT_MISMATCH")
        if model.action_space.shape != env.action_space.shape:
            raise ValueError("POLICY_ACTION_CONTRACT_MISMATCH")
        if pilot_interface is not None:
            action_interface_contract = env.action_interface_contract()
            if action_interface_contract != {
                "pilot_arm_id": pilot_interface.arm_id,
                "action_interface_id": pilot_interface.interface_id,
                "action_scale_rad": list(pilot_interface.action_scale_rad),
                "low_pass_alpha": pilot_interface.low_pass_alpha,
                "rate_limit_normalized_per_control_step": (
                    pilot_interface.rate_limit_per_step
                ),
                "previous_action_semantics": "PREVIOUS_APPLIED_NORMALIZED_ACTION",
            }:
                raise ValueError("V7_EVALUATION_ACTION_INTERFACE_DRIFT")
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
            applied_action_delta_values: list[float] = []
            requested_applied_delta_values: list[float] = []
            control_step_trace: list[dict] = []
            trace_saw_nonfinite = False
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
                if "applied_action_delta_l2" in info:
                    applied_action_delta_values.append(
                        float(info["applied_action_delta_l2"])
                    )
                    requested_applied_delta_values.append(
                        float(info["requested_applied_delta_l2"])
                    )
                if pilot_interface is not None:
                    requested_values, requested_nonfinite = _finite_list(
                        info["requested_action"]
                    )
                    applied_values, applied_nonfinite = _finite_list(
                        info["applied_action"]
                    )
                    target_values, target_nonfinite = _finite_list(
                        info["joint_target_rad"]
                    )
                    trace_saw_nonfinite = trace_saw_nonfinite or any((
                        requested_nonfinite,
                        applied_nonfinite,
                        target_nonfinite,
                    ))
                    control_step_trace.append({
                        "control_step": len(rewards) - 1,
                        "command_phase": info.get("command_phase"),
                        "requested_action": requested_values,
                        "applied_action": applied_values,
                        "joint_target_rad": target_values,
                        "applied_action_delta_l2": _finite_round(
                            info["applied_action_delta_l2"], 12
                        ),
                        "requested_applied_delta_l2": _finite_round(
                            info["requested_applied_delta_l2"], 12
                        ),
                        "saturation_substeps_over_threshold": info[
                            "saturation_substeps_over_threshold"
                        ],
                        "saturation_substeps_total": info[
                            "saturation_substeps_total"
                        ],
                    })
            mujoco.mj_forward(env.model, env.data)
            pitch, roll = quat_to_pitch_roll(env.data.qpos[3:7])
            metrics = {
                "fell": bool(terminated),
                "steady_walk_mean_speed_mps": (
                    _finite_round(np.mean(steady_speeds)) if steady_speeds else None
                ),
                "steady_walk_progress_m": (
                    _finite_round(steady_positions[-1] - steady_positions[0])
                    if len(steady_positions) >= 2 else None
                ),
                "final_stand_mean_abs_speed_mps": (
                    _finite_round(np.mean(final_phase_errors))
                    if final_phase_errors else None
                ),
                "lateral_drift_m": _finite_round(
                    abs(float(env.data.qpos[1]) - lateral_start)
                ),
                "saturation_duty_pct": _finite_round(
                    100.0 * saturation_substeps_over_threshold
                    / max(saturation_substeps_total, 1)
                ),
            }
            required_numeric = (
                "steady_walk_mean_speed_mps",
                "steady_walk_progress_m",
                "final_stand_mean_abs_speed_mps",
                "lateral_drift_m",
                "saturation_duty_pct",
            )
            raw_scalars = {
                "duration_s": _finite_round(len(rewards) * 0.02, 3),
                "distance_m": _finite_round(float(env.data.qpos[0]) - distance_start),
                "return": _finite_round(np.sum(rewards)),
                "mean_abs_command_error_mps": (
                    _finite_round(np.mean(command_errors)) if command_errors else None
                ),
                "final_speed_mps": _finite_round(env.data.qvel[0]),
                "final_pitch_deg": _finite_round(np.degrees(pitch)),
                "final_roll_deg": _finite_round(np.degrees(roll)),
                "max_abs_lateral_m": (
                    _finite_round(np.max(np.abs(lateral_positions)))
                    if lateral_positions else None
                ),
                "max_abs_yaw_deg": (
                    _finite_round(np.degrees(np.max(np.abs(yaw_values))))
                    if yaw_values else None
                ),
                "mean_applied_action_delta_l2": (
                    _finite_round(np.mean(applied_action_delta_values))
                    if applied_action_delta_values else None
                ),
                "max_applied_action_delta_l2": (
                    _finite_round(np.max(applied_action_delta_values))
                    if applied_action_delta_values else None
                ),
                "mean_requested_applied_delta_l2": (
                    _finite_round(np.mean(requested_applied_delta_values))
                    if requested_applied_delta_values else None
                ),
            }
            state_saw_nonfinite = not all((
                np.all(np.isfinite(env.data.qpos)),
                np.all(np.isfinite(env.data.qvel)),
                np.all(np.isfinite(rewards)),
                np.all(np.isfinite(command_errors)),
                np.all(np.isfinite(steady_speeds)),
                np.all(np.isfinite(steady_positions)),
                np.all(np.isfinite(final_phase_errors)),
                np.all(np.isfinite(lateral_positions)),
                np.all(np.isfinite(yaw_values)),
                np.all(np.isfinite(applied_action_delta_values)),
                np.all(np.isfinite(requested_applied_delta_values)),
            ))
            required_null_fields = [
                key for key in required_numeric if metrics[key] is None
            ]
            if trace_saw_nonfinite or state_saw_nonfinite:
                outcome_state = "NONFINITE"
                reason = "NONFINITE_REQUIRED_OR_TRACE_FIELD"
            elif required_null_fields:
                outcome_state = "NULL"
                reason = "EARLY_TERMINATION_REQUIRED_OUTCOME_UNOBSERVED"
            else:
                outcome_state = "OBSERVED"
                reason = None
            episode_record = {
                "episode": episode,
                "seed": seed_base + episode,
                "terminal_record_state": "COMPLETED",
                "outcome_state": outcome_state,
                "reason": reason,
                "metrics": metrics,
                **raw_scalars,
                "saturation_sample_rate_hz": 500.0,
            }
            if pilot_interface is not None:
                episode_record["control_step_trace"] = control_step_trace
            else:
                episode_record.update(metrics)
            episode_results.append(episode_record)
    finally:
        env.close()

    observed = [item for item in episode_results if item["outcome_state"] == "OBSERVED"]
    completed = [item for item in episode_results if not item["metrics"]["fell"]]
    final_values = [
        item["metrics"]["final_stand_mean_abs_speed_mps"]
        for item in episode_results
        if item["metrics"]["final_stand_mean_abs_speed_mps"] is not None
    ]
    steady_speed_values = [
        item["metrics"]["steady_walk_mean_speed_mps"]
        for item in episode_results
        if item["metrics"]["steady_walk_mean_speed_mps"] is not None
    ]
    steady_progress_values = [
        item["metrics"]["steady_walk_progress_m"]
        for item in episode_results
        if item["metrics"]["steady_walk_progress_m"] is not None
    ]
    lateral_values = [
        item["metrics"]["lateral_drift_m"] for item in episode_results
        if item["metrics"]["lateral_drift_m"] is not None
    ]
    saturation_values = [
        item["metrics"]["saturation_duty_pct"] for item in episode_results
        if item["metrics"]["saturation_duty_pct"] is not None
    ]
    speed_gate = all(
        item["metrics"]["steady_walk_mean_speed_mps"] is not None
        and 0.35 <= item["metrics"]["steady_walk_mean_speed_mps"] <= 1.05
        for item in episode_results
    )
    progress_gate = all(
        item["metrics"]["steady_walk_progress_m"] is not None
        and item["metrics"]["steady_walk_progress_m"] >= 1.40
        for item in episode_results
    )
    stop_gate = all(
        item["metrics"]["final_stand_mean_abs_speed_mps"] is not None
        and item["metrics"]["final_stand_mean_abs_speed_mps"] <= 0.15
        for item in episode_results
    )
    lateral_gate = all(
        item["metrics"]["lateral_drift_m"] is not None
        and item["metrics"]["lateral_drift_m"] <= 0.30
        for item in episode_results
    )
    saturation_gate = all(
        item["metrics"]["saturation_duty_pct"] is not None
        and item["metrics"]["saturation_duty_pct"] <= 30.0
        for item in episode_results
    )
    no_fall_gate = all(not item["metrics"]["fell"] for item in episode_results)
    all_outcomes_observed = len(observed) == episodes
    gate_status = "PASS" if all([
        all_outcomes_observed,
        no_fall_gate,
        speed_gate,
        progress_gate,
        stop_gate,
        lateral_gate,
        saturation_gate,
    ]) else "FAIL"
    action_delta_values = [
        item["mean_applied_action_delta_l2"] for item in episode_results
        if item["mean_applied_action_delta_l2"] is not None
    ]
    requested_applied_values = [
        item["mean_requested_applied_delta_l2"] for item in episode_results
        if item["mean_requested_applied_delta_l2"] is not None
    ]
    source_git_post = git_source_identity()
    if pilot_interface is not None and (
        source_git_post.get("available") is not True
        or source_git_post.get("working_tree_dirty") is not False
        or source_git_post.get("git_sha") != source_git_pre.get("git_sha")
    ):
        raise ValueError("V7_EVALUATION_SOURCE_GIT_DRIFT")
    result = {
        "schema_version": (
            "RL_TRAINING_ENV_EVALUATION_V4"
            if pilot_interface is not None else "RL_TRAINING_ENV_EVALUATION_V3"
        ),
        "status": "COMPLETED" if all_outcomes_observed else "COMPLETED_WITH_BLOCKER",
        "evidence_scope": "SOFTWARE_TRAINING_ENV_DEVELOPMENT_EVALUATION_ONLY",
        "model": {
            "path": (
                str(model_path.relative_to(repository)).replace("\\", "/")
                if pilot_interface is not None else str(model_path)
            ),
            "bytes": model_path.stat().st_size,
            "sha256": f"sha256:{sha256_file(model_path)}",
        },
        "profile_id": profile_id,
        "episodes": episodes,
        "seed_base": seed_base,
        "evaluation_seeds": [item["seed"] for item in episode_results],
        "source_git_pre": source_git_pre,
        "source_git_post": source_git_post,
        "source_files": {
            str(path.relative_to(Path(__file__).parents[2])).replace("\\", "/"):
                f"sha256:{sha256_file(path)}"
            for path in SOURCE_FILES
        },
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(
            (datetime.now(timezone.utc) - started_at).total_seconds(), 3
        ),
        "summary": {
            "completion_rate": round(len(completed) / episodes, 6),
            "fall_rate": round(1.0 - len(completed) / episodes, 6),
            "observed_outcome_count": len(observed),
            "null_outcome_count": sum(
                item["outcome_state"] == "NULL" for item in episode_results
            ),
            "nonfinite_outcome_count": sum(
                item["outcome_state"] == "NONFINITE" for item in episode_results
            ),
            "mean_duration_s": _finite_round(np.mean([
                item["duration_s"] for item in episode_results
                if item["duration_s"] is not None
            ])),
            "mean_abs_command_error_mps": _finite_round(np.mean([
                item["mean_abs_command_error_mps"] for item in episode_results
                if item["mean_abs_command_error_mps"] is not None
            ])),
            "mean_steady_walk_speed_mps": (
                _finite_round(np.mean(steady_speed_values)) if steady_speed_values else None
            ),
            "mean_steady_walk_progress_m": (
                _finite_round(np.mean(steady_progress_values))
                if steady_progress_values else None
            ),
            "mean_final_stand_abs_speed_mps": (
                _finite_round(np.mean(final_values)) if final_values else None
            ),
            "mean_lateral_drift_m": (
                _finite_round(np.mean(lateral_values)) if lateral_values else None
            ),
            "worst_lateral_drift_m": (
                _finite_round(np.max(lateral_values)) if lateral_values else None
            ),
            "mean_saturation_duty_pct": (
                _finite_round(np.mean(saturation_values)) if saturation_values else None
            ),
            "worst_saturation_duty_pct": (
                _finite_round(np.max(saturation_values)) if saturation_values else None
            ),
            "mean_applied_action_delta_l2": (
                _finite_round(np.mean(action_delta_values))
                if action_delta_values else None
            ),
            "mean_requested_applied_delta_l2": (
                _finite_round(np.mean(requested_applied_values))
                if requested_applied_values else None
            ),
            "gate_status": gate_status,
            "gates": {
                "no_fall": no_fall_gate,
                "steady_speed": speed_gate,
                "steady_progress": progress_gate,
                "final_stop_speed": stop_gate,
                "lateral_drift": lateral_gate,
                "saturation_duty": saturation_gate,
            },
        },
        "episode_results": episode_results,
    }
    if pilot_protocol is not None:
        result["pilot_protocol"] = pilot_protocol
        result["action_interface"] = action_interface_contract
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model_path", type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--seed-base", type=int, default=10_000)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pilot-arm", choices=[
        "V7A_REWARD_ONLY",
        "V7B_REDUCED_JOINT_ENVELOPE",
        "V7C_FILTERED_ACTION",
    ])
    args = parser.parse_args()
    repository = Path(__file__).parents[2]
    if args.episodes <= 0 or args.seed_base < 0:
        raise ValueError("episodes 必須 > 0，seed-base 必須 >= 0")
    output_path = args.output.resolve() if args.output is not None else None
    if output_path is not None and output_path.exists():
        raise FileExistsError("evaluation output 已存在，禁止覆寫")
    if args.pilot_arm is not None:
        if output_path is None:
            raise ValueError("v7 pilot evaluation 必須指定 --output")
        protocol = load_v7_protocol()
        arm = next(
            item for item in protocol["arms"] if item["arm_id"] == args.pilot_arm
        )
        expected_dir = (
            Path(__file__).parent / "artifacts" / arm["training_run_id"]
        ).resolve()
        expected_model = expected_dir / "policy.zip"
        expected_output = expected_dir / "evaluation_dev18000_18029.json"
        if args.model_path.resolve() != expected_model:
            raise ValueError("V7_EVALUATION_POLICY_PATH_MISMATCH")
        if output_path != expected_output:
            raise ValueError("V7_EVALUATION_OUTPUT_PATH_MISMATCH")

    try:
        result = evaluate(
            args.model_path,
            args.profile,
            args.episodes,
            args.seed_base,
            pilot_arm_id=args.pilot_arm,
        )
    except BaseException as exc:
        if output_path is not None and not output_path.exists():
            status = "CANCELLED" if isinstance(
                exc, (KeyboardInterrupt, SystemExit)
            ) else "FAILED"
            terminal_model_path = str(args.model_path.resolve())
            if args.pilot_arm is not None:
                try:
                    terminal_model_path = str(
                        args.model_path.resolve().relative_to(repository)
                    ).replace("\\", "/")
                except ValueError:
                    terminal_model_path = "INVALID_PATH_OUTSIDE_REPOSITORY"
            terminal_metrics = {
                "fell": None,
                "steady_walk_mean_speed_mps": None,
                "steady_walk_progress_m": None,
                "final_stand_mean_abs_speed_mps": None,
                "lateral_drift_m": None,
                "saturation_duty_pct": None,
            }
            terminal_rows = [
                {
                    "episode": episode,
                    "seed": args.seed_base + episode,
                    "terminal_record_state": status,
                    "outcome_state": "NULL",
                    "reason": f"EVALUATION_{status}:{type(exc).__name__}",
                    "metrics": terminal_metrics,
                    "control_step_trace": [],
                }
                for episode in range(args.episodes)
            ]
            terminal_source_git = git_source_identity()
            terminal = {
                "schema_version": (
                    "RL_TRAINING_ENV_EVALUATION_V4"
                    if args.pilot_arm is not None
                    else "RL_TRAINING_ENV_EVALUATION_V3"
                ),
                "status": status,
                "evidence_scope": (
                    "SOFTWARE_TRAINING_ENV_DEVELOPMENT_EVALUATION_ONLY"
                ),
                "model": {
                    "path": terminal_model_path,
                    "bytes": (
                        args.model_path.stat().st_size
                        if args.model_path.is_file() else None
                    ),
                    "sha256": (
                        f"sha256:{sha256_file(args.model_path)}"
                        if args.model_path.is_file() else None
                    ),
                },
                "profile_id": args.profile,
                "episodes": args.episodes,
                "seed_base": args.seed_base,
                "evaluation_seeds": [
                    args.seed_base + episode for episode in range(args.episodes)
                ],
                "pilot_protocol": (
                    {"protocol_id": V7_PROTOCOL_ID, "arm_id": args.pilot_arm}
                    if args.pilot_arm is not None else None
                ),
                "failure": {"type": type(exc).__name__},
                "episode_results": terminal_rows,
                "source_git_pre": terminal_source_git,
                "source_git_post": terminal_source_git,
                "source_files": {
                    str(path.relative_to(repository)).replace("\\", "/"):
                        f"sha256:{sha256_file(path)}"
                    for path in SOURCE_FILES
                },
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _write_json_atomic(output_path, terminal)
        raise

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(output_path, result)
        print(
            f"evaluation 完成：{output_path.name}；status={result['status']}；"
            f"gate={result['summary']['gate_status']}"
        )
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
