"""Bounded V1 numerical/reference oracles.

These checks intentionally separate MuJoCo-internal numerical consistency from
independent plant validation. Passing this module never promotes the project to
V1 or physical validation.
"""

from __future__ import annotations

from datetime import datetime, timezone

import mujoco
import numpy as np

from config_schema import GaitParams, default_robot
from live_sim import LiveSession


STATIC_DOUBLE_SUPPORT_CONTRACT = {
    "contract_id": "v1_static_double_support_internal_v1",
    "duration_s": 2.0,
    "evaluation_window_s": 0.5,
    "physics_dt_s": 0.002,
    "tolerances": {
        "forward_inverse_joint_force_norm_max": 1.0e-8,
        "forward_inverse_constraint_force_norm_max": 1.0e-8,
        "weight_balance_relative_error_max": 0.02,
        "mean_linear_speed_max_mps": 0.01,
        "mean_angular_speed_max_rps": 0.01,
        "max_abs_posture_deg": 3.0,
        "bilateral_contact_duty_min": 0.99,
    },
}


def _criterion(
    criterion_id: str,
    value: float | bool,
    operator: str,
    limit: float | bool,
    unit: str,
) -> dict:
    if operator == "<=":
        passed = float(value) <= float(limit)
    elif operator == ">=":
        passed = float(value) >= float(limit)
    elif operator == "==":
        passed = value == limit
    else:
        raise ValueError(f"unsupported oracle operator: {operator}")
    return {
        "id": criterion_id,
        "passed": bool(passed),
        "value": value,
        "operator": operator,
        "limit": limit,
        "unit": unit,
    }


def run_static_double_support_oracle() -> dict:
    """Run one frozen static double-support numerical reference case."""
    contract = STATIC_DOUBLE_SUPPORT_CONTRACT
    session = LiveSession(default_robot(), GaitParams(), [])
    session.assist_balance = False
    session.startup_assist_enabled = False
    session.model.opt.enableflags |= int(mujoco.mjtEnableBit.mjENBL_FWDINV)

    steps = round(contract["duration_s"] / contract["physics_dt_s"])
    evaluation_start = contract["duration_s"] - contract["evaluation_window_s"]
    fwdinv: list[np.ndarray] = []
    window_rows: list[tuple[float, float, float, float, bool]] = []
    finite = True
    for _ in range(steps):
        session._advance_sim(contract["physics_dt_s"])
        finite = finite and bool(
            np.all(np.isfinite(session.data.qpos))
            and np.all(np.isfinite(session.data.qvel))
            and np.all(np.isfinite(session.data.qacc))
            and np.all(np.isfinite(session.data.solver_fwdinv))
        )
        fwdinv.append(session.data.solver_fwdinv.copy())
        if session.data.time + 1e-12 >= evaluation_start:
            telemetry = session.controller.telemetry(session.data)
            contact_l, contact_r = session.controller._foot_contacts(session.data)
            window_rows.append((
                float(np.linalg.norm(session.data.qvel[0:3])),
                float(np.linalg.norm(session.data.qvel[3:6])),
                float(telemetry["grf"]["l"] + telemetry["grf"]["r"]),
                max(abs(float(telemetry["pitch_deg"])), abs(float(telemetry["roll_deg"]))),
                bool(contact_l and contact_r),
            ))

    residuals = np.asarray(fwdinv, dtype=np.float64)
    rows = np.asarray(window_rows, dtype=np.float64)
    model_weight_n = float(np.sum(session.model.body_mass) * abs(session.model.opt.gravity[2]))
    mean_grf_n = float(np.mean(rows[:, 2]))
    metrics = {
        "finite": finite,
        "forward_inverse_joint_force_norm_max": float(np.max(residuals[:, 0])),
        "forward_inverse_constraint_force_norm_max": float(np.max(residuals[:, 1])),
        "model_mass_kg": float(np.sum(session.model.body_mass)),
        "model_weight_n": model_weight_n,
        "mean_vertical_grf_n": mean_grf_n,
        "weight_balance_relative_error": abs(mean_grf_n - model_weight_n)
        / max(model_weight_n, 1e-12),
        "mean_linear_speed_mps": float(np.mean(rows[:, 0])),
        "mean_angular_speed_rps": float(np.mean(rows[:, 1])),
        "max_abs_posture_deg": float(np.max(rows[:, 3])),
        "bilateral_contact_duty": float(np.mean(rows[:, 4])),
    }
    limits = contract["tolerances"]
    criteria = [
        _criterion("FINITE_STATE", metrics["finite"], "==", True, "bool"),
        _criterion(
            "FWDINV_JOINT_FORCE",
            metrics["forward_inverse_joint_force_norm_max"],
            "<=",
            limits["forward_inverse_joint_force_norm_max"],
            "generalized-force norm",
        ),
        _criterion(
            "FWDINV_CONSTRAINT_FORCE",
            metrics["forward_inverse_constraint_force_norm_max"],
            "<=",
            limits["forward_inverse_constraint_force_norm_max"],
            "constraint-force norm",
        ),
        _criterion(
            "WEIGHT_BALANCE",
            metrics["weight_balance_relative_error"],
            "<=",
            limits["weight_balance_relative_error_max"],
            "relative error",
        ),
        _criterion(
            "LINEAR_STATICITY",
            metrics["mean_linear_speed_mps"],
            "<=",
            limits["mean_linear_speed_max_mps"],
            "m/s",
        ),
        _criterion(
            "ANGULAR_STATICITY",
            metrics["mean_angular_speed_rps"],
            "<=",
            limits["mean_angular_speed_max_rps"],
            "rad/s",
        ),
        _criterion(
            "POSTURE_STATICITY",
            metrics["max_abs_posture_deg"],
            "<=",
            limits["max_abs_posture_deg"],
            "deg",
        ),
        _criterion(
            "BILATERAL_CONTACT",
            metrics["bilateral_contact_duty"],
            ">=",
            limits["bilateral_contact_duty_min"],
            "fraction",
        ),
    ]
    return {
        "schema_version": "V1_STATIC_DOUBLE_SUPPORT_ORACLE_V1",
        "evidence_scope": "MUJOCO_INTERNAL_NUMERICAL_AND_REFERENCE_CASE_ONLY",
        "claim_boundary": (
            "Does not establish independent contact-wrench closure, plant validation, "
            "hardware feasibility, or V1 gate pass."
        ),
        "contract": contract,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(item["passed"] for item in criteria) else "FAIL",
        "metrics": metrics,
        "criteria": criteria,
    }
