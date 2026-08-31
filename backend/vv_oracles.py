"""Bounded V1 numerical/reference oracles.

These checks intentionally separate MuJoCo-internal numerical consistency from
independent plant validation. Passing this module never promotes the project to
V1 or physical validation.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib

import mujoco
import numpy as np

from config_schema import GaitParams, RobotConfig, default_robot
from live_sim import LiveSession
from model_builder import build_mjcf


STATIC_DOUBLE_SUPPORT_CONTRACT = {
    "contract_id": "v1_static_double_support_internal_v4",
    "duration_s": 2.0,
    "evaluation_window_s": 0.5,
    "physics_dt_s": 0.002,
    "expected_friction_cone": "PYRAMIDAL",
    "expected_contact_dimension": 3,
    "expected_contact_adhesion_n": 0.0,
    "relative_jacobian_convention": (
        "BODY2_MINUS_BODY1_AT_CONTACT_POINT_WORLD_ALIGNED_ROWS_DOF_COLUMNS"
    ),
    "support_geom_names": ["foot_l", "foot_r"],
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
        "maximum_friction_utilization": 1.0 + 1.0e-9,
        "minimum_cop_support_margin_m": -1.0e-9,
        "minimum_loaded_foot_count": 2,
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


def _friction_cone_name(model: mujoco.MjModel) -> str:
    return mujoco.mjtCone(model.opt.cone).name.removeprefix("mjCONE_")


def contact_friction_utilization(
    cone_name: str,
    dimension: int,
    wrench_local: np.ndarray,
    friction_parameters: np.ndarray,
) -> float:
    """依 compiled cone semantics 計算單一 contact 的 friction utilization。"""
    friction_dimensions = max(0, min(int(dimension) - 1, 5))
    if friction_dimensions == 0:
        return 0.0

    # MuJoCo 的 contact component 順序為 normal、tangent1/2、spin、roll1/2。
    components = np.asarray([
        wrench_local[1],
        wrench_local[2],
        wrench_local[3],
        wrench_local[4],
        wrench_local[5],
    ], dtype=np.float64)[:friction_dimensions]
    coefficients = np.asarray(
        friction_parameters,
        dtype=np.float64,
    )[:friction_dimensions]
    normal_force = float(wrench_local[0])
    if normal_force <= 1.0e-12:
        return 0.0 if float(np.max(np.abs(components))) <= 1.0e-12 else 1.0e12

    scaled = components / np.maximum(coefficients, 1.0e-12)
    if cone_name == "PYRAMIDAL":
        return float(np.sum(np.abs(scaled)) / normal_force)
    if cone_name == "ELLIPTIC":
        return float(np.linalg.norm(scaled) / normal_force)
    raise ValueError(f"unsupported MuJoCo friction cone: {cone_name}")


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
    cone_name = _friction_cone_name(model)
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

        jacobian_translation_relative_world = jacp2 - jacp1
        jacobian_rotation_relative_world = jacr2 - jacr1
        generalized_force = (
            jacobian_translation_relative_world.T @ force_world
            + jacobian_rotation_relative_world.T @ torque_world
        )
        friction_parameters = np.asarray(contact.friction, dtype=np.float64)
        friction_utilization = contact_friction_utilization(
            cone_name,
            int(contact.dim),
            wrench_local,
            friction_parameters,
        )
        exclude = int(contact.exclude)
        efc_address = int(contact.efc_address)
        active = bool(exclude == 0 and efc_address >= 0)
        reconstructed += generalized_force
        contacts.append({
            "contact_index": contact_index,
            "dimension": int(contact.dim),
            "exclude": exclude,
            "efc_address": efc_address,
            "active": active,
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
            "adhesion_n": float(contact.adhesion),
            "friction_cone": cone_name,
            "friction_parameters": friction_parameters.tolist(),
            "friction_utilization": friction_utilization,
            "jacobian_translation_relative_world": (
                jacobian_translation_relative_world.tolist()
            ),
            "jacobian_rotation_relative_world": (
                jacobian_rotation_relative_world.tolist()
            ),
        })
    return reconstructed, contacts


def reconstruct_foot_support(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    contacts: list[dict],
    support_geom_names: list[str],
) -> dict[str, dict]:
    """由 aggregate foot wrench 在 foot-local sole plane 重建 CoP。"""
    supports: dict[str, dict] = {}
    for geom_name in support_geom_names:
        geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, geom_name)
        if geom_id < 0:
            supports[geom_name] = {
                "available": False,
                "reason": "SUPPORT_GEOM_NOT_FOUND",
            }
            continue

        geom_type = int(model.geom_type[geom_id])
        geom_size = np.asarray(model.geom_size[geom_id], dtype=np.float64).copy()
        origin_world = np.asarray(data.geom_xpos[geom_id], dtype=np.float64).copy()
        rotation_world = np.asarray(
            data.geom_xmat[geom_id],
            dtype=np.float64,
        ).reshape(3, 3).copy()
        total_force_world = np.zeros(3, dtype=np.float64)
        total_moment_world = np.zeros(3, dtype=np.float64)
        active_contact_count = 0

        for contact in contacts:
            if not contact["active"]:
                continue
            sign = 0.0
            if contact["geom2_id"] == geom_id:
                sign = 1.0
            elif contact["geom1_id"] == geom_id:
                sign = -1.0
            if sign == 0.0:
                continue

            active_contact_count += 1
            position_world = np.asarray(contact["position_world_m"], dtype=np.float64)
            force_on_support = sign * np.asarray(
                contact["force_world_n"],
                dtype=np.float64,
            )
            torque_on_support = sign * np.asarray(
                contact["torque_world_nm"],
                dtype=np.float64,
            )
            total_force_world += force_on_support
            total_moment_world += (
                np.cross(position_world - origin_world, force_on_support)
                + torque_on_support
            )

        total_force_local = rotation_world.T @ total_force_world
        total_moment_local = rotation_world.T @ total_moment_world
        normal_load_n = float(total_force_local[2])
        is_box = geom_type == int(mujoco.mjtGeom.mjGEOM_BOX)
        available = bool(active_contact_count > 0 and normal_load_n > 1.0e-12 and is_box)
        cop_local: list[float] | None = None
        support_margin_m: float | None = None
        if available:
            sole_plane_z = -float(geom_size[2])
            cop_x = (
                sole_plane_z * total_force_local[0] - total_moment_local[1]
            ) / normal_load_n
            cop_y = (
                total_moment_local[0] + sole_plane_z * total_force_local[1]
            ) / normal_load_n
            cop_local = [float(cop_x), float(cop_y), sole_plane_z]
            support_margin_m = float(min(
                geom_size[0] - abs(cop_x),
                geom_size[1] - abs(cop_y),
            ))

        supports[geom_name] = {
            "available": available,
            "reason": None if available else "NO_LOADED_BOX_SUPPORT",
            "geom_id": geom_id,
            "geom_type": mujoco.mjtGeom(geom_type).name,
            "geom_size_m": geom_size.tolist(),
            "origin_world_m": origin_world.tolist(),
            "rotation_world": rotation_world.tolist(),
            "active_contact_count": active_contact_count,
            "aggregate_force_local_n": total_force_local.tolist(),
            "aggregate_moment_local_nm": total_moment_local.tolist(),
            "normal_load_n": normal_load_n,
            "cop_local_m": cop_local,
            "support_margin_m": support_margin_m,
        }
    return supports


def _step_evidence_receipt(
    session: LiveSession,
    reconstructed: np.ndarray,
    contacts: list[dict],
    foot_support: dict[str, dict],
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
        "foot_support": foot_support,
    }


def _resolved_model_receipt(session: LiveSession, model_xml_sha256: str) -> dict:
    model = session.model
    return {
        "mass_kg": float(np.sum(model.body_mass)),
        "gravity_mps2": np.asarray(model.opt.gravity, dtype=np.float64).tolist(),
        "friction_cone": _friction_cone_name(model),
        "solver": mujoco.mjtSolver(model.opt.solver).name,
        "adhesion_enabled": bool(model.flg_adhesion),
        "model_xml_sha256": model_xml_sha256,
        "nv": int(model.nv),
        "nq": int(model.nq),
        "nu": int(model.nu),
        "nbody": int(model.nbody),
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


def run_static_double_support_oracle(
    *,
    include_raw_trace: bool = False,
    robot_config: RobotConfig | None = None,
    gait_params: GaitParams | None = None,
) -> dict:
    """Run one frozen static double-support numerical reference case."""
    contract = STATIC_DOUBLE_SUPPORT_CONTRACT
    robot = (
        robot_config.model_copy(deep=True)
        if robot_config is not None
        else default_robot()
    )
    gait = (
        gait_params.model_copy(deep=True)
        if gait_params is not None
        else GaitParams()
    )
    model_xml = build_mjcf(robot, [], dynamic=True)
    model_xml_sha256 = f"sha256:{hashlib.sha256(model_xml.encode('utf-8')).hexdigest()}"
    session = LiveSession(robot, gait, [])
    session.assist_balance = False
    session.startup_assist_enabled = False
    session.model.opt.enableflags |= int(mujoco.mjtEnableBit.mjENBL_FWDINV)
    resolved_model = _resolved_model_receipt(session, model_xml_sha256)
    if resolved_model["friction_cone"] != contract["expected_friction_cone"]:
        raise RuntimeError(
            "compiled friction cone does not match frozen oracle contract: "
            f"{resolved_model['friction_cone']} != {contract['expected_friction_cone']}"
        )

    steps = round(contract["duration_s"] / contract["physics_dt_s"])
    evaluation_start = contract["duration_s"] - contract["evaluation_window_s"]
    fwdinv: list[np.ndarray] = []
    window_rows: list[tuple[float, float, float, float, bool]] = []
    closure_rows: list[tuple[float, float, float, float, float, float, float, int]] = []
    raw_trace: list[dict] = []
    finite = True
    for _ in range(steps):
        session._advance_sim(contract["physics_dt_s"])
        reconstructed, contacts = reconstruct_contact_generalized_force(
            session.model,
            session.data,
        )
        unexpected_adhesion = [
            item["adhesion_n"]
            for item in contacts
            if item["adhesion_n"] != contract["expected_contact_adhesion_n"]
        ]
        if unexpected_adhesion:
            raise RuntimeError(
                "compiled contact violates frozen non-adhesive oracle contract: "
                f"{unexpected_adhesion}"
            )
        unexpected_dimensions = [
            item["dimension"]
            for item in contacts
            if item["dimension"] != contract["expected_contact_dimension"]
        ]
        if unexpected_dimensions:
            raise RuntimeError(
                "compiled contact violates frozen dimension contract: "
                f"{unexpected_dimensions}"
            )
        foot_support = reconstruct_foot_support(
            session.model,
            session.data,
            contacts,
            contract["support_geom_names"],
        )
        if include_raw_trace:
            raw_trace.append(_step_evidence_receipt(
                session,
                reconstructed,
                contacts,
                foot_support,
            ))
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
            active_contacts = [item for item in contacts if item["active"]]
            normal_forces = [item["normal_force_n"] for item in active_contacts]
            friction_utilizations = [
                item["friction_utilization"] for item in active_contacts
            ]
            loaded_feet = [
                item for item in foot_support.values() if item["available"]
            ]
            cop_margins = [
                float(item["support_margin_m"]) for item in loaded_feet
            ]
            closure_rows.append((
                float(np.max(np.abs(normalized_components))),
                float(np.linalg.norm(residual[0:3]) / max(model_weight_n, 1e-12)),
                float(np.linalg.norm(residual[3:6]) / max(moment_scale_nm, 1e-12)),
                float(np.linalg.norm(residual[6:]) / max(moment_scale_nm, 1e-12)),
                float(min(normal_forces, default=0.0)),
                float(max(friction_utilizations, default=0.0)),
                float(min(cop_margins, default=-1.0e12)),
                len(loaded_feet),
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
        "maximum_friction_utilization": float(np.max(closure[:, 5])),
        "minimum_cop_support_margin_m": float(np.min(closure[:, 6])),
        "minimum_loaded_foot_count": int(np.min(closure[:, 7])),
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
            "FRICTION_CONE_FEASIBILITY",
            metrics["maximum_friction_utilization"],
            "<=",
            limits["maximum_friction_utilization"],
            "utilization ratio",
        ),
        _criterion(
            "COP_SUPPORT_MARGIN",
            metrics["minimum_cop_support_margin_m"],
            ">=",
            limits["minimum_cop_support_margin_m"],
            "m",
        ),
        _criterion(
            "BILATERAL_COP_AVAILABLE",
            metrics["minimum_loaded_foot_count"],
            ">=",
            limits["minimum_loaded_foot_count"],
            "foot count",
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
        "schema_version": "V1_STATIC_DOUBLE_SUPPORT_ORACLE_V4",
        "evidence_scope": (
            "MUJOCO_INTERNAL_RAW_JACOBIAN_WRENCH_RECONSTRUCTION_ONLY"
        ),
        "claim_boundary": (
            "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED. The evaluator serializes "
            "body2-minus-body1 contact-point Jacobians, "
            "aggregates MuJoCo-reported 6-D contact wrenches, and recomputes cone "
            "utilization and foot-local CoP. Jacobians and contact forces still come "
            "from the same MuJoCo engine. It does not establish independent contact-model "
            "or plant validation, hardware feasibility, or V1 gate pass."
        ),
        "contract": contract,
        "resolved_model": resolved_model,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(item["passed"] for item in criteria) else "FAIL",
        "metrics": metrics,
        "criteria": criteria,
    }
    if include_raw_trace:
        result["raw_trace"] = raw_trace
    return result
