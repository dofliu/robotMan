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
    "contract_id": "v1_static_double_support_internal_v2",
    "duration_s": 2.0,
    "evaluation_window_s": 0.5,
    "physics_dt_s": 0.002,
    # 以名義大腿加小腿長度固定 moment normalization，避免看完結果後調整尺度。
    "characteristic_length_m": 0.76,
    "tolerances": {
        "forward_inverse_joint_force_norm_max": 1.0e-8,
        "forward_inverse_constraint_force_norm_max": 1.0e-8,
        "contact_generalized_force_component_relative_max": 1.0e-9,
        "base_force_residual_relative_max": 1.0e-9,
        "base_moment_residual_relative_max": 1.0e-9,
        "joint_torque_residual_relative_max": 1.0e-9,
        "minimum_contact_normal_force_n": -1.0e-8,
        "weight_balance_relative_error_max": 0.02,
        "mean_linear_speed_max_mps": 0.01,
        "mean_angular_speed_max_rps": 0.01,
        "max_abs_posture_deg": 3.0,
        "bilateral_contact_duty_min": 0.99,
    },
}


def _name_or_id(model: mujoco.MjModel, object_type: mujoco.mjtObj, object_id: int) -> str:
    name = mujoco.mj_id2name(model, object_type, object_id)
    return name if name is not None else f"{object_type.name.lower()}_{object_id}"


def reconstruct_contact_generalized_force(
    model: mujoco.MjModel,
    data: mujoco.MjData,
) -> tuple[np.ndarray, list[dict]]:
    """以 6-D contact wrench 與 body Jacobian 重建 generalized constraint force。

    這是獨立於 UI/telemetry 的座標與聚合計算，但 contact wrench 本身仍由
    MuJoCo 提供，因此不能視為獨立 contact-physics validation。
    """
    reconstructed = np.zeros(model.nv, dtype=np.float64)
    contacts: list[dict] = []
    for contact_index in range(data.ncon):
        contact = data.contact[contact_index]
        wrench_local = np.zeros(6, dtype=np.float64)
        mujoco.mj_contactForce(model, data, contact_index, wrench_local)

        # contact.frame 的列向量是 contact-frame axes；轉置後映射到 world frame。
        contact_frame = np.asarray(contact.frame, dtype=np.float64).reshape(3, 3)
        force_world = contact_frame.T @ wrench_local[0:3]
        torque_world = contact_frame.T @ wrench_local[3:6]

        geom1 = int(contact.geom1)
        geom2 = int(contact.geom2)
        body1 = int(model.geom_bodyid[geom1])
        body2 = int(model.geom_bodyid[geom2])
        position_world = np.asarray(contact.pos, dtype=np.float64).copy()

        jacp1 = np.zeros((3, model.nv), dtype=np.float64)
        jacr1 = np.zeros((3, model.nv), dtype=np.float64)
        jacp2 = np.zeros((3, model.nv), dtype=np.float64)
        jacr2 = np.zeros((3, model.nv), dtype=np.float64)
        mujoco.mj_jac(model, data, jacp1, jacr1, position_world, body1)
        mujoco.mj_jac(model, data, jacp2, jacr2, position_world, body2)

        generalized_force = (
            (jacp2 - jacp1).T @ force_world
            + (jacr2 - jacr1).T @ torque_world
        )
        reconstructed += generalized_force
        contacts.append({
            "contact_index": contact_index,
            "dimension": int(contact.dim),
            "geom1_id": geom1,
            "geom1_name": _name_or_id(model, mujoco.mjtObj.mjOBJ_GEOM, geom1),
            "geom2_id": geom2,
            "geom2_name": _name_or_id(model, mujoco.mjtObj.mjOBJ_GEOM, geom2),
            "body1_id": body1,
            "body1_name": _name_or_id(model, mujoco.mjtObj.mjOBJ_BODY, body1),
            "body2_id": body2,
            "body2_name": _name_or_id(model, mujoco.mjtObj.mjOBJ_BODY, body2),
            "position_world_m": position_world.tolist(),
            "contact_frame_world": contact_frame.tolist(),
            "wrench_local_force_torque": wrench_local.tolist(),
            "force_world_n": force_world.tolist(),
            "torque_world_nm": torque_world.tolist(),
            "normal_force_n": float(wrench_local[0]),
            "friction_parameters": np.asarray(contact.friction, dtype=np.float64).tolist(),
            "generalized_force": generalized_force.tolist(),
        })
    return reconstructed, contacts


def _step_evidence_receipt(
    session: LiveSession,
    reconstructed: np.ndarray,
    contacts: list[dict],
) -> dict:
    """保存重播 dynamics closure 所需的 physics-step 原始量。"""
    data = session.data
    return {
        "time_s": float(data.time),
        "qpos": data.qpos.tolist(),
        "qvel": data.qvel.tolist(),
        "qacc": data.qacc.tolist(),
        "ctrl": data.ctrl.tolist(),
        "qfrc_inverse": data.qfrc_inverse.tolist(),
        "qfrc_actuator": data.qfrc_actuator.tolist(),
        "qfrc_applied": data.qfrc_applied.tolist(),
        "xfrc_applied": data.xfrc_applied.tolist(),
        "qfrc_passive": data.qfrc_passive.tolist(),
        "qfrc_bias": data.qfrc_bias.tolist(),
        "qfrc_constraint": data.qfrc_constraint.tolist(),
        "qfrc_contact_reconstructed": reconstructed.tolist(),
        "solver_fwdinv": data.solver_fwdinv.tolist(),
        "contact_count": int(data.ncon),
        "contacts": contacts,
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


def run_static_double_support_oracle(*, include_raw_trace: bool = False) -> dict:
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
    closure_rows: list[tuple[float, float, float, float, float]] = []
    raw_trace: list[dict] = []
    finite = True
    for _ in range(steps):
        session._advance_sim(contract["physics_dt_s"])
        reconstructed, contacts = reconstruct_contact_generalized_force(
            session.model,
            session.data,
        )
        if include_raw_trace:
            raw_trace.append(_step_evidence_receipt(session, reconstructed, contacts))
        finite = finite and bool(
            np.all(np.isfinite(session.data.qpos))
            and np.all(np.isfinite(session.data.qvel))
            and np.all(np.isfinite(session.data.qacc))
            and np.all(np.isfinite(session.data.solver_fwdinv))
        )
        fwdinv.append(session.data.solver_fwdinv.copy())
        # 只取 (1.5, 2.0]，確保 0.5 秒視窗恰為 250 個 500 Hz samples。
        if session.data.time > evaluation_start + 1e-12:
            telemetry = session.controller.telemetry(session.data)
            contact_l, contact_r = session.controller._foot_contacts(session.data)
            residual = session.data.qfrc_constraint - reconstructed
            model_weight_n = float(
                np.sum(session.model.body_mass) * abs(session.model.opt.gravity[2])
            )
            moment_scale_nm = model_weight_n * contract["characteristic_length_m"]
            normalized_components = np.concatenate((
                residual[0:3] / max(model_weight_n, 1e-12),
                residual[3:] / max(moment_scale_nm, 1e-12),
            ))
            normal_forces = [item["normal_force_n"] for item in contacts]
            closure_rows.append((
                float(np.max(np.abs(normalized_components))),
                float(np.linalg.norm(residual[0:3]) / max(model_weight_n, 1e-12)),
                float(np.linalg.norm(residual[3:6]) / max(moment_scale_nm, 1e-12)),
                float(np.linalg.norm(residual[6:]) / max(moment_scale_nm, 1e-12)),
                float(min(normal_forces, default=0.0)),
            ))
            window_rows.append((
                float(np.linalg.norm(session.data.qvel[0:3])),
                float(np.linalg.norm(session.data.qvel[3:6])),
                float(telemetry["grf"]["l"] + telemetry["grf"]["r"]),
                max(abs(float(telemetry["pitch_deg"])), abs(float(telemetry["roll_deg"]))),
                bool(contact_l and contact_r),
            ))

    residuals = np.asarray(fwdinv, dtype=np.float64)
    rows = np.asarray(window_rows, dtype=np.float64)
    closure = np.asarray(closure_rows, dtype=np.float64)
    model_weight_n = float(np.sum(session.model.body_mass) * abs(session.model.opt.gravity[2]))
    mean_grf_n = float(np.mean(rows[:, 2]))
    metrics = {
        "finite": finite,
        "forward_inverse_joint_force_norm_max": float(np.max(residuals[:, 0])),
        "forward_inverse_constraint_force_norm_max": float(np.max(residuals[:, 1])),
        "contact_generalized_force_component_relative_max": float(np.max(closure[:, 0])),
        "base_force_residual_relative_max": float(np.max(closure[:, 1])),
        "base_moment_residual_relative_max": float(np.max(closure[:, 2])),
        "joint_torque_residual_relative_max": float(np.max(closure[:, 3])),
        "minimum_contact_normal_force_n": float(np.min(closure[:, 4])),
        "physics_step_count": steps,
        "physics_sample_rate_hz": 1.0 / contract["physics_dt_s"],
        "evaluation_step_count": len(closure_rows),
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
            "CONTACT_GENERALIZED_FORCE_CLOSURE",
            metrics["contact_generalized_force_component_relative_max"],
            "<=",
            limits["contact_generalized_force_component_relative_max"],
            "normalized max component",
        ),
        _criterion(
            "BASE_FORCE_CLOSURE",
            metrics["base_force_residual_relative_max"],
            "<=",
            limits["base_force_residual_relative_max"],
            "normalized force norm",
        ),
        _criterion(
            "BASE_MOMENT_CLOSURE",
            metrics["base_moment_residual_relative_max"],
            "<=",
            limits["base_moment_residual_relative_max"],
            "normalized moment norm",
        ),
        _criterion(
            "JOINT_TORQUE_CLOSURE",
            metrics["joint_torque_residual_relative_max"],
            "<=",
            limits["joint_torque_residual_relative_max"],
            "normalized torque norm",
        ),
        _criterion(
            "UNILATERAL_NORMAL_FORCE",
            metrics["minimum_contact_normal_force_n"],
            ">=",
            limits["minimum_contact_normal_force_n"],
            "N",
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
    result = {
        "schema_version": "V1_STATIC_DOUBLE_SUPPORT_ORACLE_V2",
        "evidence_scope": "MUJOCO_INTERNAL_NUMERICAL_AND_WRENCH_RECONSTRUCTION_ONLY",
        "claim_boundary": (
            "The evaluator independently aggregates MuJoCo-reported 6-D contact wrenches "
            "with body Jacobians, but the wrench and qfrc_constraint reference both come "
            "from the same engine. It does not establish independent contact-model or plant "
            "validation, hardware feasibility, or V1 gate pass."
        ),
        "contract": contract,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(item["passed"] for item in criteria) else "FAIL",
        "metrics": metrics,
        "criteria": criteria,
    }
    if include_raw_trace:
        result["raw_trace"] = raw_trace
    return result
