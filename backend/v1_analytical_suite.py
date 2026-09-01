"""Frozen V1 analytical fixture cases for single support, payload, and dt sensitivity.

The fixture is intentionally passive and controller-free.  It is a small
analytical/numerical reference, not a substitute for the articulated humanoid
plant, dynamic contact validation, or physical validation.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any

import mujoco
import numpy as np

from vv_oracles import reconstruct_contact_generalized_force


PRIMARY_SCHEMA_VERSION = "V1_ANALYTICAL_FIXTURE_SUITE_V1"
MODEL_PACKAGE_SCHEMA_VERSION = "V1_ANALYTICAL_MODEL_PACKAGE_V1"
CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED. This passive one-rigid-body "
    "analytical fixture checks serialized contact arithmetic, static single-support "
    "load balance, a centered 5 kg simulated mass increment, and selected 4/2/1 ms "
    "grid-refinement quantities. It does not verify the articulated humanoid, a "
    "controller, physical contact fidelity, payload capacity, safety, sim-to-real, "
    "or the complete V1 gate."
)

CASE_SPECS = (
    {
        "case_id": "single_support_nominal_dt_4ms",
        "physics_dt_s": 0.004,
        "payload_kg": 0.0,
        "roles": ["TIMESTEP_COARSE"],
    },
    {
        "case_id": "single_support_nominal_dt_2ms",
        "physics_dt_s": 0.002,
        "payload_kg": 0.0,
        "roles": ["SINGLE_SUPPORT", "PAYLOAD_BASELINE", "TIMESTEP_MEDIUM"],
    },
    {
        "case_id": "single_support_nominal_dt_1ms",
        "physics_dt_s": 0.001,
        "payload_kg": 0.0,
        "roles": ["TIMESTEP_FINE"],
    },
    {
        "case_id": "single_support_payload_5kg_dt_2ms",
        "physics_dt_s": 0.002,
        "payload_kg": 5.0,
        "roles": ["KNOWN_PAYLOAD"],
    },
)

ANALYTICAL_SUITE_CONTRACT = {
    "contract_id": "v1_single_support_payload_timestep_fixture_v1",
    "fixture_id": "passive_centered_single_box_support_v1",
    "duration_s": 1.2,
    "evaluation_start_s": 0.8,
    "evaluation_window_semantics": "(evaluation_start_s, duration_s]",
    "gravity_mps2": 9.81,
    "base_mass_kg": 20.0,
    "known_payload_kg": 5.0,
    "expected_support_geom_name": "support_foot",
    "expected_floor_geom_name": "floor",
    "support_half_size_m": [0.12, 0.06, 0.025],
    "expected_friction_cone": "PYRAMIDAL",
    "expected_contact_dimension": 3,
    "expected_contact_adhesion_n": 0.0,
    "integrator": "IMPLICITFAST",
    "solver": "NEWTON",
    "solver_iterations": 100,
    "solver_tolerance": 1.0e-12,
    "controller_cadence": None,
    "assist_enabled": False,
    "deterministic": True,
    "case_matrix": deepcopy(list(CASE_SPECS)),
    "tolerances": {
        "time_grid_error_max_s": 1.0e-12,
        "raw_jacobian_closure_relative_max": 1.0e-9,
        "forward_inverse_joint_force_norm_max": 1.0e-8,
        "forward_inverse_constraint_force_norm_max": 1.0e-8,
        "model_mass_error_max_kg": 1.0e-12,
        "weight_balance_relative_error_max": 0.02,
        "payload_mass_delta_error_max_kg": 1.0e-12,
        "payload_grf_delta_relative_error_max": 0.02,
        "mean_linear_speed_max_mps": 1.0e-3,
        "mean_angular_speed_max_rps": 1.0e-3,
        "minimum_contact_normal_force_n": -1.0e-8,
        "maximum_friction_utilization": 1.0 + 1.0e-9,
        "minimum_cop_support_margin_m": -1.0e-9,
        "maximum_external_applied_force": 0.0,
        "minimum_exact_support_duty": 1.0,
        "maximum_unexpected_contact_count": 0,
        "timestep_fine_qoi_delta_max": 5.0e-4,
        "timestep_roundoff_floor": 1.0e-10,
    },
}

CASE_CRITERION_IDS = (
    "FINITE_RAW_VALUES",
    "TRACE_STEP_COUNT",
    "TRACE_EVALUATION_COUNT",
    "TRACE_TIME_GRID",
    "COMPILED_TIMESTEP_IDENTITY",
    "COMPILED_MODEL_CONTRACT",
    "MODEL_MASS_IDENTITY",
    "FWDINV_JOINT_FORCE",
    "FWDINV_CONSTRAINT_FORCE",
    "RAW_JACOBIAN_CLOSURE",
    "EXTERNAL_FORCE_ABSENT",
    "EXACT_SINGLE_SUPPORT",
    "UNEXPECTED_CONTACT_ABSENT",
    "CONTACT_MODEL_CONTRACT",
    "UNILATERAL_NORMAL_FORCE",
    "FRICTION_FEASIBILITY",
    "COP_SUPPORT_MARGIN",
    "WEIGHT_BALANCE",
    "LINEAR_STATICITY",
    "ANGULAR_STATICITY",
)

SUITE_CRITERION_IDS = (
    "EXACT_CASE_INVENTORY",
    "EXACT_MODEL_INVENTORY",
    "ALL_CASES_PASS",
    "PAYLOAD_MASS_DELTA",
    "PAYLOAD_GRF_DELTA",
    "TIMESTEP_NON_DT_CONFIG_IDENTITY",
    "TIMESTEP_FINE_QOI_DELTA",
    "TIMESTEP_NON_DIVERGENCE",
)

CASE_KEYS = frozenset({"case_id", "config", "compiled_model", "raw_trace"})
COMPILED_MODEL_KEYS = frozenset({
    "model_xml_sha256", "config_sha256", "compiled_timestep_s",
    "compiled_mass_kg", "gravity_mps2", "integrator", "solver",
    "solver_iterations", "solver_tolerance", "friction_cone", "nv", "nq",
    "nu", "nbody", "support_geom_id", "support_geom_name", "floor_geom_id",
    "floor_geom_name", "support_half_size_m",
})
RAW_STEP_KEYS = frozenset({
    "time_s", "qpos", "qvel", "qacc", "qfrc_constraint",
    "qfrc_contact_reconstructed", "qfrc_applied", "xfrc_applied",
    "solver_fwdinv", "contact_count", "contacts", "support_origin_world_m",
    "support_rotation_world",
})
RAW_CONTACT_KEYS = frozenset({
    "contact_index", "dimension", "exclude", "efc_address", "active",
    "geom1_id", "geom1_name", "geom2_id", "geom2_name", "body1_id",
    "body1_name", "body2_id", "body2_name", "position_world_m",
    "contact_frame_world", "wrench_local_force_torque", "force_world_n",
    "torque_world_nm", "normal_force_n", "adhesion_n", "friction_cone",
    "friction_parameters", "friction_utilization",
    "jacobian_translation_relative_world", "jacobian_rotation_relative_world",
})


class AnalyticalSuiteValidationError(RuntimeError):
    """Frozen suite schema, identity, or finite-value validation failed."""


def _sha256_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def canonical_json_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return _sha256_text(payload)


def _finite_tree(value: object) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, list):
        return all(_finite_tree(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _finite_tree(item) for key, item in value.items())
    return False


def _criterion(
    criterion_id: str,
    value: float | int | bool,
    operator: str,
    limit: float | int | bool,
    unit: str,
) -> dict:
    if not _finite_tree(value) or not _finite_tree(limit):
        raise AnalyticalSuiteValidationError(f"non-finite criterion: {criterion_id}")
    if operator == "<=":
        passed = float(value) <= float(limit)
    elif operator == ">=":
        passed = float(value) >= float(limit)
    elif operator == "==":
        passed = value == limit
    else:
        raise AnalyticalSuiteValidationError(f"unsupported criterion operator: {operator}")
    return {
        "id": criterion_id,
        "passed": bool(passed),
        "value": value,
        "operator": operator,
        "limit": limit,
        "unit": unit,
    }


def _case_config(spec: dict) -> dict:
    contract = ANALYTICAL_SUITE_CONTRACT
    return {
        "case_id": spec["case_id"],
        "physics_dt_s": spec["physics_dt_s"],
        "payload_kg": spec["payload_kg"],
        "roles": deepcopy(spec["roles"]),
        "duration_s": contract["duration_s"],
        "evaluation_start_s": contract["evaluation_start_s"],
        "gravity_mps2": contract["gravity_mps2"],
        "base_mass_kg": contract["base_mass_kg"],
        "support_half_size_m": deepcopy(contract["support_half_size_m"]),
        "friction": [1.0, 0.005, 0.0001],
        "contact_dimension": contract["expected_contact_dimension"],
        "adhesion_n": contract["expected_contact_adhesion_n"],
        "integrator": contract["integrator"],
        "solver": contract["solver"],
        "solver_iterations": contract["solver_iterations"],
        "solver_tolerance": contract["solver_tolerance"],
        "initial_position_m": [0.0, 0.0, 0.25],
        "initial_quaternion_wxyz": [1.0, 0.0, 0.0, 0.0],
        "controller_id": "PASSIVE_ANALYTICAL_FIXTURE_NO_ACTUATION_V1",
        "assist_enabled": False,
    }


def build_fixture_mjcf(config: dict) -> str:
    """Build the exact passive fixture MJCF for one frozen case."""
    payload = float(config["payload_kg"])
    payload_geom = ""
    if payload > 0.0:
        payload_geom = (
            '<geom name="known_payload" type="box" size="0.05 0.05 0.05" '
            'pos="0 0 0.22" contype="0" conaffinity="0" '
            f'mass="{payload:.17g}" rgba="0.8 0.4 0.1 1"/>'
        )
    dt = float(config["physics_dt_s"])
    gravity = float(config["gravity_mps2"])
    iterations = int(config["solver_iterations"])
    tolerance = float(config["solver_tolerance"])
    return f"""<mujoco model="v1_passive_analytical_fixture">
  <compiler angle="radian" autolimits="true"/>
  <option gravity="0 0 {-gravity:.17g}" timestep="{dt:.17g}"
          integrator="implicitfast" cone="pyramidal" solver="Newton"
          iterations="{iterations}" tolerance="{tolerance:.17g}"/>
  <size nconmax="32" njmax="128"/>
  <worldbody>
    <geom name="floor" type="plane" size="2 2 0.1" contype="2"
          conaffinity="1" condim="3" friction="1 0.005 0.0001"/>
    <body name="fixture_body" pos="0 0 0.25">
      <freejoint name="fixture_root"/>
      <geom name="support_foot" type="box" size="0.12 0.06 0.025"
            pos="0 0 -0.225" mass="2" contype="1" conaffinity="2"
            condim="3" friction="1 0.005 0.0001" rgba="0.2 0.3 0.4 1"/>
      <geom name="carrier" type="box" size="0.08 0.08 0.18"
            pos="0 0 0" mass="18" contype="0" conaffinity="0"
            rgba="0.5 0.6 0.7 1"/>
      {payload_geom}
    </body>
  </worldbody>
</mujoco>
"""


def build_analytical_model_package() -> dict:
    models = []
    for spec in CASE_SPECS:
        config = _case_config(spec)
        xml = build_fixture_mjcf(config)
        models.append({
            "case_id": spec["case_id"],
            "config": config,
            "config_sha256": canonical_json_sha256(config),
            "model_xml": xml,
            "model_xml_bytes": len(xml.encode("utf-8")),
            "model_xml_sha256": _sha256_text(xml),
        })
    package = {
        "schema_version": MODEL_PACKAGE_SCHEMA_VERSION,
        "contract_id": ANALYTICAL_SUITE_CONTRACT["contract_id"],
        "case_ids": [spec["case_id"] for spec in CASE_SPECS],
        "models": models,
    }
    package["content_sha256"] = canonical_json_sha256(package)
    return package


def validate_analytical_model_package(package: dict) -> None:
    expected_keys = {
        "schema_version", "contract_id", "case_ids", "models", "content_sha256"
    }
    if not isinstance(package, dict) or set(package) != expected_keys:
        raise AnalyticalSuiteValidationError("model package key set mismatch")
    if package["schema_version"] != MODEL_PACKAGE_SCHEMA_VERSION:
        raise AnalyticalSuiteValidationError("model package schema mismatch")
    if package["contract_id"] != ANALYTICAL_SUITE_CONTRACT["contract_id"]:
        raise AnalyticalSuiteValidationError("model package contract mismatch")
    expected_ids = [spec["case_id"] for spec in CASE_SPECS]
    if package["case_ids"] != expected_ids:
        raise AnalyticalSuiteValidationError("model package case inventory mismatch")
    if not isinstance(package["models"], list) or len(package["models"]) != len(CASE_SPECS):
        raise AnalyticalSuiteValidationError("model package model count mismatch")
    unsigned = deepcopy(package)
    content_sha = unsigned.pop("content_sha256")
    if content_sha != canonical_json_sha256(unsigned):
        raise AnalyticalSuiteValidationError("model package content SHA-256 mismatch")
    for model_record, spec in zip(package["models"], CASE_SPECS, strict=True):
        expected_record_keys = {
            "case_id", "config", "config_sha256", "model_xml", "model_xml_bytes",
            "model_xml_sha256",
        }
        if not isinstance(model_record, dict) or set(model_record) != expected_record_keys:
            raise AnalyticalSuiteValidationError("model record key set mismatch")
        expected_config = _case_config(spec)
        if model_record["case_id"] != spec["case_id"] or model_record["config"] != expected_config:
            raise AnalyticalSuiteValidationError("model record config mismatch")
        if model_record["config_sha256"] != canonical_json_sha256(expected_config):
            raise AnalyticalSuiteValidationError("model record config SHA-256 mismatch")
        xml = model_record["model_xml"]
        if not isinstance(xml, str):
            raise AnalyticalSuiteValidationError("model XML must be text")
        if xml != build_fixture_mjcf(expected_config):
            raise AnalyticalSuiteValidationError("model XML differs from frozen fixture")
        if model_record["model_xml_bytes"] != len(xml.encode("utf-8")):
            raise AnalyticalSuiteValidationError("model XML byte count mismatch")
        if model_record["model_xml_sha256"] != _sha256_text(xml):
            raise AnalyticalSuiteValidationError("model XML SHA-256 mismatch")


def _compiled_model_receipt(model: mujoco.MjModel, record: dict) -> dict:
    support_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "support_foot")
    floor_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "floor")
    return {
        "model_xml_sha256": record["model_xml_sha256"],
        "config_sha256": record["config_sha256"],
        "compiled_timestep_s": float(model.opt.timestep),
        "compiled_mass_kg": float(np.sum(model.body_mass)),
        "gravity_mps2": np.asarray(model.opt.gravity, dtype=np.float64).tolist(),
        "integrator": mujoco.mjtIntegrator(model.opt.integrator).name.removeprefix("mjINT_"),
        "solver": mujoco.mjtSolver(model.opt.solver).name.removeprefix("mjSOL_"),
        "solver_iterations": int(model.opt.iterations),
        "solver_tolerance": float(model.opt.tolerance),
        "friction_cone": mujoco.mjtCone(model.opt.cone).name.removeprefix("mjCONE_"),
        "nv": int(model.nv),
        "nq": int(model.nq),
        "nu": int(model.nu),
        "nbody": int(model.nbody),
        "support_geom_id": int(support_id),
        "support_geom_name": "support_foot",
        "floor_geom_id": int(floor_id),
        "floor_geom_name": "floor",
        "support_half_size_m": np.asarray(model.geom_size[support_id], dtype=np.float64).tolist(),
    }


def _run_case(model_record: dict) -> dict:
    config = model_record["config"]
    model = mujoco.MjModel.from_xml_string(model_record["model_xml"])
    data = mujoco.MjData(model)
    model.opt.enableflags |= int(mujoco.mjtEnableBit.mjENBL_FWDINV)
    mujoco.mj_forward(model, data)
    compiled = _compiled_model_receipt(model, model_record)
    dt = float(config["physics_dt_s"])
    duration = float(config["duration_s"])
    exact_steps = duration / dt
    if not math.isclose(exact_steps, round(exact_steps), rel_tol=0.0, abs_tol=1.0e-12):
        raise AnalyticalSuiteValidationError("duration is not an integer timestep grid")
    trace = []
    for _ in range(round(exact_steps)):
        mujoco.mj_step(model, data)
        reconstructed, contacts = reconstruct_contact_generalized_force(model, data)
        support_id = compiled["support_geom_id"]
        trace.append({
            "time_s": float(data.time),
            "qpos": data.qpos.tolist(),
            "qvel": data.qvel.tolist(),
            "qacc": data.qacc.tolist(),
            "qfrc_constraint": data.qfrc_constraint.tolist(),
            "qfrc_contact_reconstructed": reconstructed.tolist(),
            "qfrc_applied": data.qfrc_applied.tolist(),
            "xfrc_applied": data.xfrc_applied.tolist(),
            "solver_fwdinv": data.solver_fwdinv.tolist(),
            "contact_count": int(data.ncon),
            "contacts": contacts,
            "support_origin_world_m": np.asarray(
                data.geom_xpos[support_id], dtype=np.float64
            ).tolist(),
            "support_rotation_world": np.asarray(
                data.geom_xmat[support_id], dtype=np.float64
            ).reshape(3, 3).tolist(),
        })
    return {
        "case_id": config["case_id"],
        "config": deepcopy(config),
        "compiled_model": compiled,
        "raw_trace": trace,
    }


def _support_step_metrics(step: dict, compiled: dict) -> dict:
    support_id = compiled["support_geom_id"]
    floor_id = compiled["floor_geom_id"]
    origin = np.asarray(step["support_origin_world_m"], dtype=np.float64)
    rotation = np.asarray(step["support_rotation_world"], dtype=np.float64)
    total_force_world = np.zeros(3, dtype=np.float64)
    total_moment_world = np.zeros(3, dtype=np.float64)
    unexpected = 0
    contact_contract_valid = True
    active = 0
    normal_min = math.inf
    friction_max = 0.0
    for contact in step["contacts"]:
        if not contact["active"]:
            continue
        active += 1
        pair = {int(contact["geom1_id"]), int(contact["geom2_id"])}
        names = {contact["geom1_name"], contact["geom2_name"]}
        expected_names = {compiled["support_geom_name"], compiled["floor_geom_name"]}
        if pair != {support_id, floor_id} or names != expected_names:
            unexpected += 1
            continue
        contact_contract_valid = bool(
            contact_contract_valid
            and int(contact["dimension"])
            == ANALYTICAL_SUITE_CONTRACT["expected_contact_dimension"]
            and float(contact["adhesion_n"])
            == ANALYTICAL_SUITE_CONTRACT["expected_contact_adhesion_n"]
            and contact["friction_cone"]
            == ANALYTICAL_SUITE_CONTRACT["expected_friction_cone"]
        )
        sign = 1.0 if int(contact["geom2_id"]) == support_id else -1.0
        arithmetic = _raw_contact_arithmetic(contact, int(compiled["nv"]))
        position = np.asarray(contact["position_world_m"], dtype=np.float64)
        force = sign * arithmetic["force_world"]
        torque = sign * arithmetic["torque_world"]
        total_force_world += force
        total_moment_world += np.cross(position - origin, force) + torque
        normal_min = min(normal_min, arithmetic["normal_force_n"])
        friction_max = max(friction_max, arithmetic["friction_utilization"])
        contact_contract_valid = bool(
            contact_contract_valid and arithmetic["contact_contract_valid"]
        )
    force_local = rotation.T @ total_force_world
    moment_local = rotation.T @ total_moment_world
    fz = float(force_local[2])
    half = np.asarray(compiled["support_half_size_m"], dtype=np.float64)
    cop_margin = -math.inf
    if active > 0 and fz > 1.0e-12:
        sole_z = -float(half[2])
        cop_x = (sole_z * force_local[0] - moment_local[1]) / fz
        cop_y = (moment_local[0] + sole_z * force_local[1]) / fz
        cop_margin = float(min(half[0] - abs(cop_x), half[1] - abs(cop_y)))
    return {
        "exact_support": bool(active > 0 and unexpected == 0),
        "active_contact_count": active,
        "unexpected_contact_count": unexpected,
        "vertical_support_force_n": float(total_force_world[2]),
        "horizontal_support_force_n": float(np.linalg.norm(force_local[:2])),
        "minimum_contact_normal_force_n": normal_min if active else -1.0e300,
        "maximum_friction_utilization": friction_max,
        "cop_support_margin_m": cop_margin if math.isfinite(cop_margin) else -1.0e300,
        "contact_contract_valid": contact_contract_valid,
    }


def _raw_contact_arithmetic(contact: dict, nv: int) -> dict:
    """Recompute authoritative contact arithmetic from raw frame/wrench/Jacobians."""
    frame = np.asarray(contact["contact_frame_world"], dtype=np.float64)
    wrench = np.asarray(contact["wrench_local_force_torque"], dtype=np.float64)
    jacp = np.asarray(
        contact["jacobian_translation_relative_world"], dtype=np.float64
    )
    jacr = np.asarray(
        contact["jacobian_rotation_relative_world"], dtype=np.float64
    )
    if frame.shape != (3, 3) or wrench.shape != (6,):
        raise AnalyticalSuiteValidationError("raw contact frame/wrench shape mismatch")
    if jacp.shape != (3, nv) or jacr.shape != (3, nv):
        raise AnalyticalSuiteValidationError("raw relative Jacobian shape mismatch")
    force_world = frame.T @ wrench[:3]
    torque_world = frame.T @ wrench[3:]
    generalized_force = jacp.T @ force_world + jacr.T @ torque_world
    dimension = int(contact["dimension"])
    friction = np.asarray(contact["friction_parameters"], dtype=np.float64)
    if friction.shape != (5,):
        raise AnalyticalSuiteValidationError("raw friction parameter shape mismatch")
    normal = float(wrench[0])
    if normal <= 1.0e-12:
        tangential = float(np.max(np.abs(wrench[1:3])))
        utilization = 0.0 if tangential <= 1.0e-12 else 1.0e12
    else:
        utilization = float(
            abs(wrench[1]) / max(float(friction[0]) * normal, 1.0e-12)
            + abs(wrench[2]) / max(float(friction[1]) * normal, 1.0e-12)
        )
    derived_active = bool(int(contact["exclude"]) == 0 and int(contact["efc_address"]) >= 0)
    active_matches = contact["active"] is derived_active
    inactive_zero = bool(
        derived_active or float(np.max(np.abs(wrench), initial=0.0)) <= 1.0e-12
    )
    receipt_delta = max(
        float(np.max(np.abs(force_world - np.asarray(contact["force_world_n"])) , initial=0.0)),
        float(np.max(np.abs(torque_world - np.asarray(contact["torque_world_nm"])), initial=0.0)),
        abs(normal - float(contact["normal_force_n"])),
        abs(utilization - float(contact["friction_utilization"])),
    )
    return {
        "force_world": force_world,
        "torque_world": torque_world,
        "generalized_force": generalized_force,
        "normal_force_n": normal,
        "friction_utilization": utilization,
        "receipt_delta": receipt_delta,
        "contact_contract_valid": bool(
            active_matches
            and inactive_zero
            and dimension == ANALYTICAL_SUITE_CONTRACT["expected_contact_dimension"]
            and float(contact["adhesion_n"])
            == ANALYTICAL_SUITE_CONTRACT["expected_contact_adhesion_n"]
            and contact["friction_cone"]
            == ANALYTICAL_SUITE_CONTRACT["expected_friction_cone"]
        ),
    }


def _evaluate_case(case: dict) -> dict:
    if not isinstance(case, dict) or set(case) != CASE_KEYS:
        raise AnalyticalSuiteValidationError("raw case key set mismatch")
    config = case["config"]
    compiled = case["compiled_model"]
    trace = case["raw_trace"]
    if not isinstance(compiled, dict) or set(compiled) != COMPILED_MODEL_KEYS:
        raise AnalyticalSuiteValidationError("compiled model key set mismatch")
    dt = float(config["physics_dt_s"])
    model_mass_expected = float(config["base_mass_kg"] + config["payload_kg"])
    expected_steps = round(float(config["duration_s"]) / dt)
    expected_eval = round(
        (float(config["duration_s"]) - float(config["evaluation_start_s"])) / dt
    )
    finite = _finite_tree(case)
    if not isinstance(trace, list) or not trace:
        raise AnalyticalSuiteValidationError(f"empty raw trace: {config['case_id']}")
    time_errors = [abs(float(row["time_s"]) - (index + 1) * dt) for index, row in enumerate(trace)]
    eval_rows = [
        row for row in trace
        if float(row["time_s"]) > float(config["evaluation_start_s"]) + 1.0e-12
    ]
    if not eval_rows:
        raise AnalyticalSuiteValidationError(f"empty evaluation window: {config['case_id']}")
    qfrc_errors = []
    applied_max = 0.0
    fwdinv_joint = []
    fwdinv_constraint = []
    for row in trace:
        if not isinstance(row, dict) or set(row) != RAW_STEP_KEYS:
            raise AnalyticalSuiteValidationError("raw step key set mismatch")
        expected_shapes = {
            "qpos": (int(compiled["nq"]),),
            "qvel": (int(compiled["nv"]),),
            "qacc": (int(compiled["nv"]),),
            "qfrc_constraint": (int(compiled["nv"]),),
            "qfrc_contact_reconstructed": (int(compiled["nv"]),),
            "qfrc_applied": (int(compiled["nv"]),),
            "xfrc_applied": (int(compiled["nbody"]), 6),
            "solver_fwdinv": (2,),
            "support_origin_world_m": (3,),
            "support_rotation_world": (3, 3),
        }
        for field, shape in expected_shapes.items():
            if np.asarray(row[field]).shape != shape:
                raise AnalyticalSuiteValidationError(
                    f"raw step {field} shape mismatch"
                )
        if not isinstance(row["contacts"], list):
            raise AnalyticalSuiteValidationError("raw contacts must be a list")
        if int(row["contact_count"]) != len(row["contacts"]):
            raise AnalyticalSuiteValidationError("raw contact count mismatch")
        actual = np.asarray(row["qfrc_constraint"], dtype=np.float64)
        serialized_rebuilt = np.asarray(
            row["qfrc_contact_reconstructed"], dtype=np.float64
        )
        rebuilt = np.zeros(int(compiled["nv"]), dtype=np.float64)
        serialized_receipt_delta = 0.0
        for contact_index, contact in enumerate(row["contacts"]):
            if not isinstance(contact, dict) or set(contact) != RAW_CONTACT_KEYS:
                raise AnalyticalSuiteValidationError("raw contact key set mismatch")
            if int(contact["contact_index"]) != contact_index:
                raise AnalyticalSuiteValidationError("raw contact index mismatch")
            arithmetic = _raw_contact_arithmetic(contact, int(compiled["nv"]))
            rebuilt += arithmetic["generalized_force"]
            serialized_receipt_delta = max(
                serialized_receipt_delta,
                arithmetic["receipt_delta"],
            )
        force_scale = max(model_mass_expected * float(config["gravity_mps2"]), 1.0e-12)
        moment_scale = force_scale * max(
            float(config["support_half_size_m"][0]),
            float(config["support_half_size_m"][1]),
        )
        residual = actual - rebuilt
        serialized_residual = serialized_rebuilt - rebuilt
        qfrc_errors.append(max(
            float(np.max(np.abs(residual[:3]), initial=0.0) / force_scale),
            float(np.max(np.abs(residual[3:]), initial=0.0) / moment_scale),
            float(np.max(np.abs(serialized_residual[:3]), initial=0.0) / force_scale),
            float(np.max(np.abs(serialized_residual[3:]), initial=0.0) / moment_scale),
            serialized_receipt_delta,
        ))
        applied_values = np.concatenate((
            np.asarray(row["qfrc_applied"], dtype=np.float64).reshape(-1),
            np.asarray(row["xfrc_applied"], dtype=np.float64).reshape(-1),
        ))
        applied_max = max(applied_max, float(np.max(np.abs(applied_values), initial=0.0)))
        fwdinv_joint.append(float(row["solver_fwdinv"][0]))
        fwdinv_constraint.append(float(row["solver_fwdinv"][1]))
    support_rows = [_support_step_metrics(row, compiled) for row in eval_rows]
    model_weight = model_mass_expected * float(config["gravity_mps2"])
    mean_grf = float(np.mean([item["vertical_support_force_n"] for item in support_rows]))
    linear_speeds = [float(np.linalg.norm(np.asarray(row["qvel"][:3]))) for row in eval_rows]
    angular_speeds = [float(np.linalg.norm(np.asarray(row["qvel"][3:6]))) for row in eval_rows]
    metrics = {
        "finite": bool(finite),
        "trace_step_count": len(trace),
        "evaluation_step_count": len(eval_rows),
        "time_grid_error_max_s": max(time_errors),
        "compiled_timestep_error_s": abs(float(compiled["compiled_timestep_s"]) - dt),
        "compiled_model_contract_valid": bool(
            compiled["integrator"] == config["integrator"]
            and compiled["solver"] == config["solver"]
            and compiled["solver_iterations"] == config["solver_iterations"]
            and compiled["solver_tolerance"] == config["solver_tolerance"]
            and compiled["friction_cone"]
            == ANALYTICAL_SUITE_CONTRACT["expected_friction_cone"]
            and compiled["nv"] == 6
            and compiled["nq"] == 7
            and compiled["nu"] == 0
            and compiled["support_geom_name"]
            == ANALYTICAL_SUITE_CONTRACT["expected_support_geom_name"]
            and compiled["floor_geom_name"]
            == ANALYTICAL_SUITE_CONTRACT["expected_floor_geom_name"]
            and compiled["support_half_size_m"]
            == ANALYTICAL_SUITE_CONTRACT["support_half_size_m"]
            and compiled["gravity_mps2"]
            == [0.0, 0.0, -float(config["gravity_mps2"])]
        ),
        "model_mass_error_kg": abs(float(compiled["compiled_mass_kg"]) - model_mass_expected),
        "forward_inverse_joint_force_norm_max": max(fwdinv_joint),
        "forward_inverse_constraint_force_norm_max": max(fwdinv_constraint),
        "raw_jacobian_closure_relative_max": max(qfrc_errors),
        "maximum_external_applied_force": applied_max,
        "exact_single_support_duty": float(np.mean([item["exact_support"] for item in support_rows])),
        "maximum_unexpected_contact_count": max(item["unexpected_contact_count"] for item in support_rows),
        "contact_model_contract_valid": all(item["contact_contract_valid"] for item in support_rows),
        "minimum_contact_normal_force_n": min(item["minimum_contact_normal_force_n"] for item in support_rows),
        "maximum_friction_utilization": max(item["maximum_friction_utilization"] for item in support_rows),
        "minimum_cop_support_margin_m": min(item["cop_support_margin_m"] for item in support_rows),
        "model_weight_n": model_weight,
        "mean_vertical_grf_n": mean_grf,
        "weight_balance_relative_error": abs(mean_grf - model_weight) / max(model_weight, 1.0e-12),
        "mean_linear_speed_mps": float(np.mean(linear_speeds)),
        "mean_angular_speed_rps": float(np.mean(angular_speeds)),
        "timestep_qoi_normalized_mean_grf": mean_grf / max(model_weight, 1.0e-12),
    }
    limits = ANALYTICAL_SUITE_CONTRACT["tolerances"]
    criteria = [
        _criterion("FINITE_RAW_VALUES", metrics["finite"], "==", True, "bool"),
        _criterion("TRACE_STEP_COUNT", metrics["trace_step_count"], "==", expected_steps, "steps"),
        _criterion("TRACE_EVALUATION_COUNT", metrics["evaluation_step_count"], "==", expected_eval, "steps"),
        _criterion("TRACE_TIME_GRID", metrics["time_grid_error_max_s"], "<=", limits["time_grid_error_max_s"], "s"),
        _criterion("COMPILED_TIMESTEP_IDENTITY", metrics["compiled_timestep_error_s"], "<=", limits["time_grid_error_max_s"], "s"),
        _criterion("COMPILED_MODEL_CONTRACT", metrics["compiled_model_contract_valid"], "==", True, "bool"),
        _criterion("MODEL_MASS_IDENTITY", metrics["model_mass_error_kg"], "<=", limits["model_mass_error_max_kg"], "kg"),
        _criterion("FWDINV_JOINT_FORCE", metrics["forward_inverse_joint_force_norm_max"], "<=", limits["forward_inverse_joint_force_norm_max"], "generalized-force norm"),
        _criterion("FWDINV_CONSTRAINT_FORCE", metrics["forward_inverse_constraint_force_norm_max"], "<=", limits["forward_inverse_constraint_force_norm_max"], "constraint-force norm"),
        _criterion("RAW_JACOBIAN_CLOSURE", metrics["raw_jacobian_closure_relative_max"], "<=", limits["raw_jacobian_closure_relative_max"], "relative max component"),
        _criterion("EXTERNAL_FORCE_ABSENT", metrics["maximum_external_applied_force"], "<=", limits["maximum_external_applied_force"], "generalized/cartesian force"),
        _criterion("EXACT_SINGLE_SUPPORT", metrics["exact_single_support_duty"], ">=", limits["minimum_exact_support_duty"], "fraction"),
        _criterion("UNEXPECTED_CONTACT_ABSENT", metrics["maximum_unexpected_contact_count"], "<=", limits["maximum_unexpected_contact_count"], "contacts"),
        _criterion("CONTACT_MODEL_CONTRACT", metrics["contact_model_contract_valid"], "==", True, "bool"),
        _criterion("UNILATERAL_NORMAL_FORCE", metrics["minimum_contact_normal_force_n"], ">=", limits["minimum_contact_normal_force_n"], "N"),
        _criterion("FRICTION_FEASIBILITY", metrics["maximum_friction_utilization"], "<=", limits["maximum_friction_utilization"], "utilization ratio"),
        _criterion("COP_SUPPORT_MARGIN", metrics["minimum_cop_support_margin_m"], ">=", limits["minimum_cop_support_margin_m"], "m"),
        _criterion("WEIGHT_BALANCE", metrics["weight_balance_relative_error"], "<=", limits["weight_balance_relative_error_max"], "relative error"),
        _criterion("LINEAR_STATICITY", metrics["mean_linear_speed_mps"], "<=", limits["mean_linear_speed_max_mps"], "m/s"),
        _criterion("ANGULAR_STATICITY", metrics["mean_angular_speed_rps"], "<=", limits["mean_angular_speed_max_rps"], "rad/s"),
    ]
    return {
        "case_id": config["case_id"],
        "status": "PASS" if all(item["passed"] for item in criteria) else "FAIL",
        "metrics": metrics,
        "criteria": criteria,
    }


def _non_dt_config(config: dict) -> dict:
    return {key: value for key, value in config.items() if key not in {"case_id", "physics_dt_s", "payload_kg", "roles"}}


def _evaluate_suite(
    cases: list[dict],
    package: dict,
) -> tuple[list[dict], dict, list[dict]]:
    expected_ids = [spec["case_id"] for spec in CASE_SPECS]
    actual_ids = [case.get("case_id") for case in cases]
    model_ids = package.get("case_ids")
    exact_cases = actual_ids == expected_ids and len(set(actual_ids)) == len(actual_ids)
    exact_models = model_ids == expected_ids and len(set(model_ids)) == len(model_ids)
    if not exact_cases:
        raise AnalyticalSuiteValidationError("raw case inventory mismatch")
    for case, model_record, spec in zip(
        cases, package["models"], CASE_SPECS, strict=True
    ):
        expected_config = _case_config(spec)
        if case.get("case_id") != spec["case_id"] or case.get("config") != expected_config:
            raise AnalyticalSuiteValidationError("raw case/config identity mismatch")
        compiled = case.get("compiled_model")
        if not isinstance(compiled, dict):
            raise AnalyticalSuiteValidationError("compiled model receipt missing")
        if (
            compiled.get("model_xml_sha256") != model_record["model_xml_sha256"]
            or compiled.get("config_sha256") != model_record["config_sha256"]
        ):
            raise AnalyticalSuiteValidationError("case-to-model package identity mismatch")
        compiled_model = mujoco.MjModel.from_xml_string(model_record["model_xml"])
        expected_compiled = _compiled_model_receipt(compiled_model, model_record)
        if compiled != expected_compiled:
            raise AnalyticalSuiteValidationError("compiled model receipt mismatch")
    receipts = [_evaluate_case(case) for case in cases]
    by_id = {item["case_id"]: item for item in receipts}
    raw_by_id = {item["case_id"]: item for item in cases}
    nominal = by_id["single_support_nominal_dt_2ms"]["metrics"]
    payload = by_id["single_support_payload_5kg_dt_2ms"]["metrics"]
    payload_expected = ANALYTICAL_SUITE_CONTRACT["known_payload_kg"]
    compiled_nominal = raw_by_id["single_support_nominal_dt_2ms"]["compiled_model"]["compiled_mass_kg"]
    compiled_payload = raw_by_id["single_support_payload_5kg_dt_2ms"]["compiled_model"]["compiled_mass_kg"]
    mass_delta_error = abs((compiled_payload - compiled_nominal) - payload_expected)
    expected_grf_delta = payload_expected * ANALYTICAL_SUITE_CONTRACT["gravity_mps2"]
    measured_grf_delta = payload["mean_vertical_grf_n"] - nominal["mean_vertical_grf_n"]
    grf_delta_error = abs(measured_grf_delta - expected_grf_delta) / expected_grf_delta
    q4 = by_id["single_support_nominal_dt_4ms"]["metrics"]["timestep_qoi_normalized_mean_grf"]
    q2 = nominal["timestep_qoi_normalized_mean_grf"]
    q1 = by_id["single_support_nominal_dt_1ms"]["metrics"]["timestep_qoi_normalized_mean_grf"]
    coarse_delta = abs(q4 - q2)
    fine_delta = abs(q2 - q1)
    floor = ANALYTICAL_SUITE_CONTRACT["tolerances"]["timestep_roundoff_floor"]
    signed_coarse = q4 - q2
    signed_fine = q2 - q1
    if coarse_delta <= floor and fine_delta <= floor:
        order_status = "ROUND_OFF_LIMITED"
        observed_order = None
    elif signed_coarse * signed_fine > 0.0 and coarse_delta > floor and fine_delta > floor:
        order_status = "ESTIMATED"
        observed_order = math.log(coarse_delta / fine_delta) / math.log(2.0)
    else:
        order_status = "NON_MONOTONIC_OR_NOT_ESTIMABLE"
        observed_order = None
    nominal_configs = [
        raw_by_id[case_id]["config"]
        for case_id in (
            "single_support_nominal_dt_4ms",
            "single_support_nominal_dt_2ms",
            "single_support_nominal_dt_1ms",
        )
    ]
    same_non_dt = all(_non_dt_config(item) == _non_dt_config(nominal_configs[0]) for item in nominal_configs[1:])
    metrics = {
        "case_count": len(cases),
        "case_pass_count": sum(item["status"] == "PASS" for item in receipts),
        "payload_mass_delta_error_kg": mass_delta_error,
        "payload_grf_delta_relative_error": grf_delta_error,
        "timestep_qoi_4ms": q4,
        "timestep_qoi_2ms": q2,
        "timestep_qoi_1ms": q1,
        "timestep_coarse_delta": coarse_delta,
        "timestep_fine_delta": fine_delta,
        "timestep_order_status": order_status,
        "timestep_observed_order": observed_order,
        "timestep_non_dt_config_identity": same_non_dt,
    }
    limits = ANALYTICAL_SUITE_CONTRACT["tolerances"]
    criteria = [
        _criterion("EXACT_CASE_INVENTORY", exact_cases, "==", True, "bool"),
        _criterion("EXACT_MODEL_INVENTORY", exact_models, "==", True, "bool"),
        _criterion("ALL_CASES_PASS", metrics["case_pass_count"], "==", len(CASE_SPECS), "cases"),
        _criterion("PAYLOAD_MASS_DELTA", mass_delta_error, "<=", limits["payload_mass_delta_error_max_kg"], "kg"),
        _criterion("PAYLOAD_GRF_DELTA", grf_delta_error, "<=", limits["payload_grf_delta_relative_error_max"], "relative error"),
        _criterion("TIMESTEP_NON_DT_CONFIG_IDENTITY", same_non_dt, "==", True, "bool"),
        _criterion("TIMESTEP_FINE_QOI_DELTA", fine_delta, "<=", limits["timestep_fine_qoi_delta_max"], "normalized GRF delta"),
        _criterion("TIMESTEP_NON_DIVERGENCE", fine_delta, "<=", max(coarse_delta, floor), "normalized GRF delta"),
    ]
    return receipts, metrics, criteria


def run_analytical_suite(*, model_package: dict | None = None) -> dict:
    """Run all exact cases and return a raw-retaining primary result."""
    package = deepcopy(model_package) if model_package is not None else build_analytical_model_package()
    validate_analytical_model_package(package)
    cases = [_run_case(record) for record in package["models"]]
    case_receipts, metrics, criteria = _evaluate_suite(cases, package)
    result = {
        "schema_version": PRIMARY_SCHEMA_VERSION,
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "claim_boundary": CLAIM_BOUNDARY,
        "contract": deepcopy(ANALYTICAL_SUITE_CONTRACT),
        "model_package_content_sha256": package["content_sha256"],
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(item["passed"] for item in criteria) else "FAIL",
        "cases": cases,
        "case_receipts": case_receipts,
        "metrics": metrics,
        "criteria": criteria,
    }
    if not _finite_tree(result):
        raise AnalyticalSuiteValidationError("primary result contains unsupported/non-finite values")
    return result


def validate_primary_result(result: dict, package: dict) -> None:
    """Reject forged/self-reported primary summaries by re-evaluating raw cases."""
    validate_analytical_model_package(package)
    expected_keys = {
        "schema_version", "evidence_scope", "claim_boundary", "contract",
        "model_package_content_sha256", "completed_at", "status", "cases",
        "case_receipts", "metrics", "criteria",
    }
    if not isinstance(result, dict) or set(result) != expected_keys:
        raise AnalyticalSuiteValidationError("primary result key set mismatch")
    if result["schema_version"] != PRIMARY_SCHEMA_VERSION:
        raise AnalyticalSuiteValidationError("primary schema mismatch")
    if result["evidence_scope"] != "SIM_ONLY_MUJOCO" or result["claim_boundary"] != CLAIM_BOUNDARY:
        raise AnalyticalSuiteValidationError("primary claim boundary mismatch")
    if result["contract"] != ANALYTICAL_SUITE_CONTRACT:
        raise AnalyticalSuiteValidationError("primary contract mismatch")
    if result["model_package_content_sha256"] != package["content_sha256"]:
        raise AnalyticalSuiteValidationError("primary model package identity mismatch")
    if not _finite_tree(result):
        raise AnalyticalSuiteValidationError("primary contains unsupported/non-finite values")
    expected_case_receipts, expected_metrics, expected_criteria = _evaluate_suite(
        result["cases"], package
    )
    if (
        result["case_receipts"] != expected_case_receipts
        or result["metrics"] != expected_metrics
        or result["criteria"] != expected_criteria
    ):
        raise AnalyticalSuiteValidationError("primary summary does not match raw recomputation")
    expected_status = "PASS" if all(item["passed"] for item in expected_criteria) else "FAIL"
    if result["status"] != expected_status:
        raise AnalyticalSuiteValidationError("primary status is forged or inconsistent")
    for receipt in expected_criteria:
        if receipt["id"] not in SUITE_CRITERION_IDS:
            raise AnalyticalSuiteValidationError("unexpected suite criterion")
    for case in result["cases"]:
        receipt = _evaluate_case(case)
        if tuple(item["id"] for item in receipt["criteria"]) != CASE_CRITERION_IDS:
            raise AnalyticalSuiteValidationError("case criterion mapping mismatch")
