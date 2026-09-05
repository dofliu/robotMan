"""Frozen v7 normalized-action interface contract and pure transform.

The protocol JSON is the single source of truth for the three DEVELOPMENT
arms.  Loading is deliberately strict: duplicate keys, NaN/Infinity, arm
drift, malformed vectors, and unsupported filter combinations fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path

import numpy as np


PROTOCOL_PATH = Path(__file__).with_name("v7_action_interface_pilot_protocol.json")
PROTOCOL_SCHEMA = "V7_ACTION_INTERFACE_PILOT_PROTOCOL_V1"
PROTOCOL_ID = "PILOT-V7-ACTION-INTERFACE-DEV-V1"
ARM_IDS = (
    "V7A_REWARD_ONLY",
    "V7B_REDUCED_JOINT_ENVELOPE",
    "V7C_FILTERED_ACTION",
)
JOINT_ORDER = (
    "hip_roll_l",
    "hip_pitch_l",
    "knee_l",
    "ankle_l",
    "hip_roll_r",
    "hip_pitch_r",
    "knee_r",
    "ankle_r",
    "shoulder_l",
    "elbow_l",
    "shoulder_r",
    "elbow_r",
)


def _strict_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"V7_PROTOCOL_DUPLICATE_KEY:{key}")
        result[key] = value
    return result


def _reject_constant(value: str):
    raise ValueError(f"V7_PROTOCOL_NONFINITE_JSON:{value}")


def load_v7_protocol(path: Path = PROTOCOL_PATH) -> dict:
    """Read and validate the frozen protocol without accepting JSON extensions."""
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"V7_PROTOCOL_INVALID:{type(exc).__name__}") from exc
    if not isinstance(payload, dict):
        raise ValueError("V7_PROTOCOL_ROOT_NOT_OBJECT")
    if payload.get("schema_version") != PROTOCOL_SCHEMA:
        raise ValueError("V7_PROTOCOL_SCHEMA_MISMATCH")
    if payload.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("V7_PROTOCOL_ID_MISMATCH")
    if payload.get("protocol_status") != "FROZEN_INTERNAL_DEVELOPMENT":
        raise ValueError("V7_PROTOCOL_NOT_FROZEN")
    if payload.get("run_class") != "DEVELOPMENT":
        raise ValueError("V7_PROTOCOL_RUN_CLASS_MISMATCH")
    if payload.get("paper_data_ready") is not False:
        raise ValueError("V7_PROTOCOL_PAPER_DATA_BOUNDARY_MISMATCH")

    task = payload.get("task_contract")
    if not isinstance(task, dict) or {
        "task_id": task.get("task_id"),
        "duration_s": task.get("duration_s"),
        "physics_rate_hz": task.get("physics_rate_hz"),
        "control_rate_hz": task.get("control_rate_hz"),
        "assist_enabled": task.get("assist_enabled"),
    } != {
        "task_id": "stand_start_walk_stop_v1",
        "duration_s": 9.0,
        "physics_rate_hz": 500.0,
        "control_rate_hz": 50.0,
        "assist_enabled": False,
    }:
        raise ValueError("V7_PROTOCOL_TASK_CONTRACT_MISMATCH")
    if task.get("criteria") != {
        "posture_limit_deg": 15.0,
        "steady_speed_min_mps": 0.35,
        "steady_speed_max_mps": 1.05,
        "steady_progress_min_m": 1.4,
        "stop_speed_max_mps": 0.15,
        "lateral_drift_max_m": 0.3,
        "saturation_threshold_pct": 95.0,
        "saturation_duty_max_pct": 30.0,
        "final_window_s": 0.5,
    }:
        raise ValueError("V7_PROTOCOL_TASK_THRESHOLDS_MISMATCH")

    joint_order = payload.get("joint_order")
    if joint_order != list(JOINT_ORDER):
        raise ValueError("V7_PROTOCOL_JOINT_ORDER_INVALID")

    training = payload.get("training_design")
    if not isinstance(training, dict) or {
        "agent_seed": training.get("agent_seed"),
        "parallel_envs": training.get("parallel_envs"),
        "environment_seed_start": training.get("environment_seed_start"),
        "environment_seed_end": training.get("environment_seed_end"),
        "independent_training_replicates_per_arm": training.get(
            "independent_training_replicates_per_arm"
        ),
        "requested_timesteps": training.get("requested_timesteps"),
        "expected_realized_timesteps": training.get("expected_realized_timesteps"),
        "ppo_rollout_steps_per_env": training.get("ppo_rollout_steps_per_env"),
        "ppo_batch_size": training.get("ppo_batch_size"),
        "ppo_epochs": training.get("ppo_epochs"),
        "device": training.get("device"),
    } != {
        "agent_seed": 8700,
        "parallel_envs": 12,
        "environment_seed_start": 8700,
        "environment_seed_end": 8711,
        "independent_training_replicates_per_arm": 1,
        "requested_timesteps": 100_000,
        "expected_realized_timesteps": 122_880,
        "ppo_rollout_steps_per_env": 2048,
        "ppo_batch_size": 8192,
        "ppo_epochs": 5,
        "device": "cpu",
    }:
        raise ValueError("V7_PROTOCOL_TRAINING_DESIGN_MISMATCH")

    arms = payload.get("arms")
    if (
        not isinstance(arms, list)
        or any(not isinstance(arm, dict) for arm in arms)
        or [arm.get("arm_id") for arm in arms] != list(ARM_IDS)
    ):
        raise ValueError("V7_PROTOCOL_ARM_SET_MISMATCH")
    seen_profiles: set[str] = set()
    seen_environments: set[str] = set()
    for arm in arms:
        for field, seen in (
            ("profile_id", seen_profiles),
            ("environment_id", seen_environments),
        ):
            value = arm.get(field)
            if not isinstance(value, str) or not value or value in seen:
                raise ValueError(f"V7_PROTOCOL_{field.upper()}_INVALID")
            seen.add(value)
        for field in ("training_run_id", "action_interface_id"):
            value = arm.get(field)
            if (
                not isinstance(value, str)
                or not value
                or not value.replace("-", "").replace("_", "").isalnum()
            ):
                raise ValueError(f"V7_PROTOCOL_{field.upper()}_INVALID")
        scales = arm.get("action_scale_rad")
        if (
            not isinstance(scales, list)
            or len(scales) != 12
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) <= 0.0
                for value in scales
            )
        ):
            raise ValueError(f"V7_PROTOCOL_ACTION_SCALE_INVALID:{arm.get('arm_id')}")
        alpha = arm.get("low_pass_alpha")
        rate_limit = arm.get("rate_limit_normalized_per_control_step")
        if arm.get("arm_id") == "V7C_FILTERED_ACTION":
            if not isinstance(alpha, (int, float)) or isinstance(alpha, bool) or not 0.0 < float(alpha) <= 1.0:
                raise ValueError("V7_PROTOCOL_FILTER_ALPHA_INVALID")
            if (
                not isinstance(rate_limit, (int, float))
                or isinstance(rate_limit, bool)
                or not math.isfinite(float(rate_limit))
                or not 0.0 < float(rate_limit) <= 2.0
            ):
                raise ValueError("V7_PROTOCOL_RATE_LIMIT_INVALID")
        elif alpha is not None or rate_limit is not None:
            raise ValueError(f"V7_PROTOCOL_UNEXPECTED_FILTER:{arm.get('arm_id')}")

    evaluation = payload.get("evaluation_design")
    if not isinstance(evaluation, dict):
        raise ValueError("V7_PROTOCOL_EVALUATION_INVALID")
    if evaluation.get("evaluation_seeds") != list(range(18000, 18030)):
        raise ValueError("V7_PROTOCOL_DEV_SEED_SCHEDULE_MISMATCH")
    if (
        evaluation.get("episodes_per_arm") != 30
        or evaluation.get("evaluation_seed_start") != 18000
        or evaluation.get("evaluation_seed_end") != 18029
        or evaluation.get("pair_key") != "evaluation_seed"
    ):
        raise ValueError("V7_PROTOCOL_EVALUATION_DESIGN_MISMATCH")
    if evaluation.get("retired_seed_range") != [19000, 19029]:
        raise ValueError("V7_PROTOCOL_RETIRED_SEED_RANGE_MISMATCH")
    if evaluation.get("sealed_formal_seed_range") != [20000, 20029]:
        raise ValueError("V7_PROTOCOL_FORMAL_SEED_RANGE_MISMATCH")
    return payload


@dataclass(frozen=True)
class V7ActionInterface:
    arm_id: str
    profile_id: str
    environment_id: str
    interface_id: str
    action_scale_rad: tuple[float, ...]
    low_pass_alpha: float | None
    rate_limit_per_step: float | None

    def transform(
        self,
        requested_action,
        previous_applied_action,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return clipped requested action and the frozen applied action."""
        requested = np.asarray(requested_action, dtype=np.float64)
        previous = np.asarray(previous_applied_action, dtype=np.float64)
        if requested.shape != (12,):
            raise ValueError(f"V7_ACTION_SHAPE_INVALID:{requested.shape}")
        if previous.shape != (12,):
            raise ValueError(f"V7_PREVIOUS_ACTION_SHAPE_INVALID:{previous.shape}")
        if not np.all(np.isfinite(requested)):
            raise ValueError("V7_ACTION_NONFINITE")
        if not np.all(np.isfinite(previous)):
            raise ValueError("V7_PREVIOUS_ACTION_NONFINITE")

        requested = np.clip(requested, -1.0, 1.0)
        if self.low_pass_alpha is None:
            return requested, requested.copy()

        candidate = previous + self.low_pass_alpha * (requested - previous)
        delta = np.clip(
            candidate - previous,
            -float(self.rate_limit_per_step),
            float(self.rate_limit_per_step),
        )
        applied = np.clip(previous + delta, -1.0, 1.0)
        return requested, applied


def resolve_v7_action_interface(
    arm_id: str,
    path: Path = PROTOCOL_PATH,
) -> V7ActionInterface:
    protocol = load_v7_protocol(path)
    arm = next((item for item in protocol["arms"] if item["arm_id"] == arm_id), None)
    if arm is None:
        raise KeyError(f"unknown v7 pilot arm: {arm_id}")
    return V7ActionInterface(
        arm_id=arm["arm_id"],
        profile_id=arm["profile_id"],
        environment_id=arm["environment_id"],
        interface_id=arm["action_interface_id"],
        action_scale_rad=tuple(float(value) for value in arm["action_scale_rad"]),
        low_pass_alpha=(
            None if arm["low_pass_alpha"] is None else float(arm["low_pass_alpha"])
        ),
        rate_limit_per_step=(
            None
            if arm["rate_limit_normalized_per_control_step"] is None
            else float(arm["rate_limit_normalized_per_control_step"])
        ),
    )
