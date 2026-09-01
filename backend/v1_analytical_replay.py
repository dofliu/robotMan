"""Stdlib-only replay for the frozen V1 analytical fixture suite.

The replay intentionally does not import MuJoCo, NumPy, controllers, or any
project module.  It validates the exact model package, then recomputes the
scientific receipts from serialized raw Jacobians, contact wrenches, and state
traces.  The primary summaries are comparison receipts, never replay inputs.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any


PRIMARY_SCHEMA_VERSION = "V1_ANALYTICAL_FIXTURE_SUITE_V1"
MODEL_PACKAGE_SCHEMA_VERSION = "V1_ANALYTICAL_MODEL_PACKAGE_V1"
REPLAY_SCHEMA_VERSION = "V1_ANALYTICAL_REPLAY_RECEIPT_V1"
PRIMARY_CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED. This passive one-rigid-body "
    "analytical fixture checks serialized contact arithmetic, static single-support "
    "load balance, a centered 5 kg simulated mass increment, and selected 4/2/1 ms "
    "grid-refinement quantities. It does not verify the articulated humanoid, a "
    "controller, physical contact fidelity, payload capacity, safety, sim-to-real, "
    "or the complete V1 gate."
)
REPLAY_CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED. This stdlib-only process replay "
    "recomputes J^T contact-wrench closure, static single-support load balance, "
    "the centered 5 kg simulated mass/GRF increment, and selected 4/2/1 ms QoIs "
    "from serialized evidence. The model, Jacobians, and wrenches remain MuJoCo "
    "receipts; this is not an independent contact model, articulated-humanoid or "
    "controller validation, physical payload validation, safety evidence, or "
    "sim-to-real evidence."
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

FROZEN_CONTRACT = {
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
    "case_matrix": [
        {
            "case_id": spec["case_id"],
            "physics_dt_s": spec["physics_dt_s"],
            "payload_kg": spec["payload_kg"],
            "roles": list(spec["roles"]),
        }
        for spec in CASE_SPECS
    ],
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

MODEL_PACKAGE_KEYS = frozenset({
    "schema_version",
    "contract_id",
    "case_ids",
    "models",
    "content_sha256",
})
MODEL_RECORD_KEYS = frozenset({
    "case_id",
    "config",
    "config_sha256",
    "model_xml",
    "model_xml_bytes",
    "model_xml_sha256",
})
PRIMARY_KEYS = frozenset({
    "schema_version",
    "evidence_scope",
    "claim_boundary",
    "contract",
    "model_package_content_sha256",
    "completed_at",
    "status",
    "cases",
    "case_receipts",
    "metrics",
    "criteria",
})
CASE_KEYS = frozenset({"case_id", "config", "compiled_model", "raw_trace"})
COMPILED_MODEL_KEYS = frozenset({
    "model_xml_sha256",
    "config_sha256",
    "compiled_timestep_s",
    "compiled_mass_kg",
    "gravity_mps2",
    "integrator",
    "solver",
    "solver_iterations",
    "solver_tolerance",
    "friction_cone",
    "nv",
    "nq",
    "nu",
    "nbody",
    "support_geom_id",
    "support_geom_name",
    "floor_geom_id",
    "floor_geom_name",
    "support_half_size_m",
})
RAW_STEP_KEYS = frozenset({
    "time_s",
    "qpos",
    "qvel",
    "qacc",
    "qfrc_constraint",
    "qfrc_contact_reconstructed",
    "qfrc_applied",
    "xfrc_applied",
    "solver_fwdinv",
    "contact_count",
    "contacts",
    "support_origin_world_m",
    "support_rotation_world",
})
RAW_CONTACT_KEYS = frozenset({
    "contact_index",
    "dimension",
    "exclude",
    "efc_address",
    "active",
    "geom1_id",
    "geom1_name",
    "geom2_id",
    "geom2_name",
    "body1_id",
    "body1_name",
    "body2_id",
    "body2_name",
    "position_world_m",
    "contact_frame_world",
    "wrench_local_force_torque",
    "force_world_n",
    "torque_world_nm",
    "normal_force_n",
    "adhesion_n",
    "friction_cone",
    "friction_parameters",
    "friction_utilization",
    "jacobian_translation_relative_world",
    "jacobian_rotation_relative_world",
})
CASE_METRIC_KEYS = frozenset({
    "finite",
    "trace_step_count",
    "evaluation_step_count",
    "time_grid_error_max_s",
    "compiled_timestep_error_s",
    "compiled_model_contract_valid",
    "model_mass_error_kg",
    "forward_inverse_joint_force_norm_max",
    "forward_inverse_constraint_force_norm_max",
    "raw_jacobian_closure_relative_max",
    "maximum_external_applied_force",
    "exact_single_support_duty",
    "maximum_unexpected_contact_count",
    "contact_model_contract_valid",
    "minimum_contact_normal_force_n",
    "maximum_friction_utilization",
    "minimum_cop_support_margin_m",
    "model_weight_n",
    "mean_vertical_grf_n",
    "weight_balance_relative_error",
    "mean_linear_speed_mps",
    "mean_angular_speed_rps",
    "timestep_qoi_normalized_mean_grf",
})
SUITE_METRIC_KEYS = frozenset({
    "case_count",
    "case_pass_count",
    "payload_mass_delta_error_kg",
    "payload_grf_delta_relative_error",
    "timestep_qoi_4ms",
    "timestep_qoi_2ms",
    "timestep_qoi_1ms",
    "timestep_coarse_delta",
    "timestep_fine_delta",
    "timestep_order_status",
    "timestep_observed_order",
    "timestep_non_dt_config_identity",
})


class AnalyticalReplayValidationError(ValueError):
    """Evidence is non-finite, incomplete, or outside the frozen contract."""


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


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnalyticalReplayValidationError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise AnalyticalReplayValidationError(f"{field} must be finite")
    return result


def _integer(value: Any, field: str) -> int:
    result = _number(value, field)
    if not result.is_integer():
        raise AnalyticalReplayValidationError(f"{field} must be an integer")
    return int(result)


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise AnalyticalReplayValidationError(f"{field} must be a non-empty string")
    return value


def _assert_finite_tree(value: Any, field: str) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, (int, float)):
        _number(value, field)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_finite_tree(item, f"{field}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise AnalyticalReplayValidationError(
                    f"{field} contains a non-string key"
                )
            _assert_finite_tree(item, f"{field}.{key}")
        return
    raise AnalyticalReplayValidationError(f"{field} contains unsupported value type")


def _vector(value: Any, length: int, field: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise AnalyticalReplayValidationError(
            f"{field} must contain exactly {length} numbers"
        )
    return [_number(item, f"{field}[{index}]") for index, item in enumerate(value)]


def _matrix(value: Any, rows: int, columns: int, field: str) -> list[list[float]]:
    if not isinstance(value, list) or len(value) != rows:
        raise AnalyticalReplayValidationError(
            f"{field} must be a {rows}x{columns} matrix"
        )
    return [
        _vector(row, columns, f"{field}[{index}]")
        for index, row in enumerate(value)
    ]


def _add(left: list[float], right: list[float]) -> list[float]:
    return [a + b for a, b in zip(left, right, strict=True)]


def _subtract(left: list[float], right: list[float]) -> list[float]:
    return [a - b for a, b in zip(left, right, strict=True)]


def _scale(vector: list[float], factor: float) -> list[float]:
    return [factor * item for item in vector]


def _norm(vector: list[float]) -> float:
    return math.sqrt(sum(item * item for item in vector))


def _cross(left: list[float], right: list[float]) -> list[float]:
    return [
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    ]


def _transpose_vector(matrix: list[list[float]], vector: list[float]) -> list[float]:
    return [
        sum(matrix[row][column] * vector[row] for row in range(len(matrix)))
        for column in range(len(matrix[0]))
    ]


def _max_abs_delta(left: list[float], right: list[float]) -> float:
    return max((abs(a - b) for a, b in zip(left, right, strict=True)), default=0.0)


def _criterion(
    criterion_id: str,
    value: float | int | bool,
    operator: str,
    limit: float | int | bool,
    unit: str,
) -> dict:
    _assert_finite_tree(value, f"criterion.{criterion_id}.value")
    _assert_finite_tree(limit, f"criterion.{criterion_id}.limit")
    if operator == "<=":
        passed = float(value) <= float(limit)
    elif operator == ">=":
        passed = float(value) >= float(limit)
    elif operator == "==":
        passed = value == limit
    else:
        raise AnalyticalReplayValidationError(
            f"unsupported criterion operator: {operator}"
        )
    return {
        "id": criterion_id,
        "passed": bool(passed),
        "value": value,
        "operator": operator,
        "limit": limit,
        "unit": unit,
    }


def _expected_config(spec: dict) -> dict:
    return {
        "case_id": spec["case_id"],
        "physics_dt_s": spec["physics_dt_s"],
        "payload_kg": spec["payload_kg"],
        "roles": list(spec["roles"]),
        "duration_s": FROZEN_CONTRACT["duration_s"],
        "evaluation_start_s": FROZEN_CONTRACT["evaluation_start_s"],
        "gravity_mps2": FROZEN_CONTRACT["gravity_mps2"],
        "base_mass_kg": FROZEN_CONTRACT["base_mass_kg"],
        "support_half_size_m": list(FROZEN_CONTRACT["support_half_size_m"]),
        "friction": [1.0, 0.005, 0.0001],
        "contact_dimension": FROZEN_CONTRACT["expected_contact_dimension"],
        "adhesion_n": FROZEN_CONTRACT["expected_contact_adhesion_n"],
        "integrator": FROZEN_CONTRACT["integrator"],
        "solver": FROZEN_CONTRACT["solver"],
        "solver_iterations": FROZEN_CONTRACT["solver_iterations"],
        "solver_tolerance": FROZEN_CONTRACT["solver_tolerance"],
        "initial_position_m": [0.0, 0.0, 0.25],
        "initial_quaternion_wxyz": [1.0, 0.0, 0.0, 0.0],
        "controller_id": "PASSIVE_ANALYTICAL_FIXTURE_NO_ACTUATION_V1",
        "assist_enabled": False,
    }


def _expected_model_xml(config: dict) -> str:
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


def _valid_sha256(value: Any, field: str) -> str:
    text = _required_string(value, field)
    if (
        len(text) != 71
        or not text.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in text[7:])
    ):
        raise AnalyticalReplayValidationError(f"{field} must be sha256:<64 lowercase hex>")
    return text


def _validate_model_package(package: Any) -> dict[str, dict]:
    _assert_finite_tree(package, "model_package")
    if not isinstance(package, dict) or set(package) != MODEL_PACKAGE_KEYS:
        raise AnalyticalReplayValidationError("model package key set mismatch")
    if package.get("schema_version") != MODEL_PACKAGE_SCHEMA_VERSION:
        raise AnalyticalReplayValidationError("model package schema mismatch")
    if package.get("contract_id") != FROZEN_CONTRACT["contract_id"]:
        raise AnalyticalReplayValidationError("model package contract mismatch")
    expected_ids = [spec["case_id"] for spec in CASE_SPECS]
    if package.get("case_ids") != expected_ids:
        raise AnalyticalReplayValidationError("model package case inventory mismatch")
    models = package.get("models")
    if not isinstance(models, list) or len(models) != len(CASE_SPECS):
        raise AnalyticalReplayValidationError("model package model count mismatch")
    unsigned = {key: value for key, value in package.items() if key != "content_sha256"}
    content_sha = _valid_sha256(package.get("content_sha256"), "model_package.content_sha256")
    if content_sha != canonical_json_sha256(unsigned):
        raise AnalyticalReplayValidationError("model package content SHA-256 mismatch")

    records: dict[str, dict] = {}
    for index, (record, spec) in enumerate(zip(models, CASE_SPECS, strict=True)):
        prefix = f"model_package.models[{index}]"
        if not isinstance(record, dict) or set(record) != MODEL_RECORD_KEYS:
            raise AnalyticalReplayValidationError(f"{prefix} key set mismatch")
        expected_config = _expected_config(spec)
        if record.get("case_id") != spec["case_id"]:
            raise AnalyticalReplayValidationError(f"{prefix}.case_id mismatch")
        if record.get("config") != expected_config:
            raise AnalyticalReplayValidationError(f"{prefix}.config mismatch")
        expected_config_sha = canonical_json_sha256(expected_config)
        if record.get("config_sha256") != expected_config_sha:
            raise AnalyticalReplayValidationError(f"{prefix}.config SHA-256 mismatch")
        expected_xml = _expected_model_xml(expected_config)
        if record.get("model_xml") != expected_xml:
            raise AnalyticalReplayValidationError(f"{prefix}.model_xml differs from frozen model")
        if _integer(record.get("model_xml_bytes"), f"{prefix}.model_xml_bytes") != len(
            expected_xml.encode("utf-8")
        ):
            raise AnalyticalReplayValidationError(f"{prefix}.model_xml byte count mismatch")
        if record.get("model_xml_sha256") != _sha256_text(expected_xml):
            raise AnalyticalReplayValidationError(f"{prefix}.model_xml SHA-256 mismatch")
        records[spec["case_id"]] = record
    return records


def _validate_criterion_shape(value: Any, expected_ids: tuple[str, ...], field: str) -> None:
    if not isinstance(value, list) or len(value) != len(expected_ids):
        raise AnalyticalReplayValidationError(f"{field} count mismatch")
    for index, (item, expected_id) in enumerate(zip(value, expected_ids, strict=True)):
        if not isinstance(item, dict) or set(item) != {
            "id", "passed", "value", "operator", "limit", "unit"
        }:
            raise AnalyticalReplayValidationError(f"{field}[{index}] key set mismatch")
        if item.get("id") != expected_id:
            raise AnalyticalReplayValidationError(f"{field}[{index}].id mismatch")
        if type(item.get("passed")) is not bool:
            raise AnalyticalReplayValidationError(f"{field}[{index}].passed must be bool")
        if item.get("operator") not in {"<=", ">=", "=="}:
            raise AnalyticalReplayValidationError(f"{field}[{index}].operator invalid")
        _required_string(item.get("unit"), f"{field}[{index}].unit")


def _validate_primary_shell(primary: Any, package: dict) -> None:
    _assert_finite_tree(primary, "primary")
    if not isinstance(primary, dict) or set(primary) != PRIMARY_KEYS:
        raise AnalyticalReplayValidationError("primary result key set mismatch")
    if primary.get("schema_version") != PRIMARY_SCHEMA_VERSION:
        raise AnalyticalReplayValidationError("primary schema mismatch")
    if primary.get("evidence_scope") != "SIM_ONLY_MUJOCO":
        raise AnalyticalReplayValidationError("primary evidence scope mismatch")
    if primary.get("claim_boundary") != PRIMARY_CLAIM_BOUNDARY:
        raise AnalyticalReplayValidationError("primary claim boundary mismatch")
    if primary.get("contract") != FROZEN_CONTRACT:
        raise AnalyticalReplayValidationError("primary frozen contract mismatch")
    if primary.get("model_package_content_sha256") != package.get("content_sha256"):
        raise AnalyticalReplayValidationError("primary/model package identity mismatch")
    _required_string(primary.get("completed_at"), "primary.completed_at")
    if primary.get("status") not in {"PASS", "FAIL"}:
        raise AnalyticalReplayValidationError("primary.status invalid")
    cases = primary.get("cases")
    expected_ids = [spec["case_id"] for spec in CASE_SPECS]
    if not isinstance(cases, list):
        raise AnalyticalReplayValidationError("primary.cases must be a list")
    actual_ids = [case.get("case_id") if isinstance(case, dict) else None for case in cases]
    if actual_ids != expected_ids or len(set(actual_ids)) != len(expected_ids):
        raise AnalyticalReplayValidationError("primary raw case inventory mismatch")
    case_receipts = primary.get("case_receipts")
    if not isinstance(case_receipts, list) or len(case_receipts) != len(CASE_SPECS):
        raise AnalyticalReplayValidationError("primary.case_receipts count mismatch")
    for index, (receipt, expected_id) in enumerate(
        zip(case_receipts, expected_ids, strict=True)
    ):
        prefix = f"primary.case_receipts[{index}]"
        if not isinstance(receipt, dict) or set(receipt) != {
            "case_id", "status", "metrics", "criteria"
        }:
            raise AnalyticalReplayValidationError(f"{prefix} key set mismatch")
        if receipt.get("case_id") != expected_id or receipt.get("status") not in {"PASS", "FAIL"}:
            raise AnalyticalReplayValidationError(f"{prefix} identity/status mismatch")
        metrics = receipt.get("metrics")
        if not isinstance(metrics, dict) or set(metrics) != CASE_METRIC_KEYS:
            raise AnalyticalReplayValidationError(f"{prefix}.metrics key set mismatch")
        _validate_criterion_shape(receipt.get("criteria"), CASE_CRITERION_IDS, f"{prefix}.criteria")
    metrics = primary.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != SUITE_METRIC_KEYS:
        raise AnalyticalReplayValidationError("primary.metrics key set mismatch")
    _validate_criterion_shape(primary.get("criteria"), SUITE_CRITERION_IDS, "primary.criteria")


def _contact_is_active(contact: dict, field: str) -> bool:
    exclude = _integer(contact.get("exclude"), f"{field}.exclude")
    efc_address = _integer(contact.get("efc_address"), f"{field}.efc_address")
    active = contact.get("active")
    if type(active) is not bool:
        raise AnalyticalReplayValidationError(f"{field}.active must be bool")
    if active != (exclude == 0 and efc_address >= 0):
        raise AnalyticalReplayValidationError(
            f"{field}.active conflicts with exclude/efc_address"
        )
    return active


def _friction_utilization(contact: dict, field: str) -> float:
    dimension = _integer(contact.get("dimension"), f"{field}.dimension")
    wrench = _vector(
        contact.get("wrench_local_force_torque"),
        6,
        f"{field}.wrench_local_force_torque",
    )
    friction = _vector(contact.get("friction_parameters"), 5, f"{field}.friction_parameters")
    normal = wrench[0]
    if normal <= 1.0e-12:
        tangential = max(abs(wrench[1]), abs(wrench[2]))
        return 0.0 if tangential <= 1.0e-12 else 1.0e12
    if contact.get("friction_cone") != "PYRAMIDAL":
        return 1.0e12
    # Frozen condim=3 case uses the two tangential force components only.
    _ = dimension
    return (
        abs(wrench[1]) / max(friction[0] * normal, 1.0e-12)
        + abs(wrench[2]) / max(friction[1] * normal, 1.0e-12)
    )


def _replay_contact(
    contact: Any,
    contact_index: int,
    field: str,
) -> tuple[list[float], list[float], list[float], float, float, bool]:
    if not isinstance(contact, dict) or set(contact) != RAW_CONTACT_KEYS:
        raise AnalyticalReplayValidationError(f"{field} frozen key set mismatch")
    if _integer(contact.get("contact_index"), f"{field}.contact_index") != contact_index:
        raise AnalyticalReplayValidationError(f"{field}.contact_index mismatch")
    active = _contact_is_active(contact, field)
    for name in ("geom1_id", "geom2_id", "body1_id", "body2_id"):
        if _integer(contact.get(name), f"{field}.{name}") < 0:
            raise AnalyticalReplayValidationError(f"{field}.{name} must be nonnegative")
    for name in ("geom1_name", "geom2_name", "body1_name", "body2_name"):
        _required_string(contact.get(name), f"{field}.{name}")
    _vector(contact.get("position_world_m"), 3, f"{field}.position_world_m")
    frame = _matrix(contact.get("contact_frame_world"), 3, 3, f"{field}.contact_frame_world")
    wrench = _vector(
        contact.get("wrench_local_force_torque"),
        6,
        f"{field}.wrench_local_force_torque",
    )
    jacobian_translation = _matrix(
        contact.get("jacobian_translation_relative_world"),
        3,
        6,
        f"{field}.jacobian_translation_relative_world",
    )
    jacobian_rotation = _matrix(
        contact.get("jacobian_rotation_relative_world"),
        3,
        6,
        f"{field}.jacobian_rotation_relative_world",
    )
    force_world = _transpose_vector(frame, wrench[:3])
    torque_world = _transpose_vector(frame, wrench[3:])
    generalized = _add(
        _transpose_vector(jacobian_translation, force_world),
        _transpose_vector(jacobian_rotation, torque_world),
    )
    serialized_force = _vector(contact.get("force_world_n"), 3, f"{field}.force_world_n")
    serialized_torque = _vector(contact.get("torque_world_nm"), 3, f"{field}.torque_world_nm")
    serialized_normal = _number(contact.get("normal_force_n"), f"{field}.normal_force_n")
    serialized_friction = _number(
        contact.get("friction_utilization"), f"{field}.friction_utilization"
    )
    utilization = _friction_utilization(contact, field)
    receipt_delta = max(
        _max_abs_delta(force_world, serialized_force),
        _max_abs_delta(torque_world, serialized_torque),
        abs(wrench[0] - serialized_normal),
        abs(utilization - serialized_friction),
    )
    if not active and any(item != 0.0 for item in wrench):
        raise AnalyticalReplayValidationError(f"{field} inactive contact has nonzero wrench")
    contact_contract = bool(
        _integer(contact.get("dimension"), f"{field}.dimension")
        == FROZEN_CONTRACT["expected_contact_dimension"]
        and _number(contact.get("adhesion_n"), f"{field}.adhesion_n")
        == FROZEN_CONTRACT["expected_contact_adhesion_n"]
        and contact.get("friction_cone") == FROZEN_CONTRACT["expected_friction_cone"]
    )
    return generalized, force_world, torque_world, utilization, receipt_delta, contact_contract


def _compiled_contract(compiled: dict, config: dict) -> bool:
    return bool(
        compiled["integrator"] == config["integrator"]
        and compiled["solver"] == config["solver"]
        and compiled["solver_iterations"] == config["solver_iterations"]
        and compiled["solver_tolerance"] == config["solver_tolerance"]
        and compiled["friction_cone"] == FROZEN_CONTRACT["expected_friction_cone"]
        and compiled["nv"] == 6
        and compiled["nq"] == 7
        and compiled["nu"] == 0
        and compiled["nbody"] == 2
        and compiled["support_geom_id"] == 1
        and compiled["support_geom_name"] == FROZEN_CONTRACT["expected_support_geom_name"]
        and compiled["floor_geom_id"] == 0
        and compiled["floor_geom_name"] == FROZEN_CONTRACT["expected_floor_geom_name"]
        and compiled["support_half_size_m"] == FROZEN_CONTRACT["support_half_size_m"]
        and compiled["gravity_mps2"] == [0.0, 0.0, -float(config["gravity_mps2"])]
    )


def _evaluate_case(case: Any, model_record: dict, case_index: int) -> tuple[dict, float]:
    field = f"primary.cases[{case_index}]"
    if not isinstance(case, dict) or set(case) != CASE_KEYS:
        raise AnalyticalReplayValidationError(f"{field} key set mismatch")
    spec = CASE_SPECS[case_index]
    expected_config = _expected_config(spec)
    if case.get("case_id") != spec["case_id"] or case.get("config") != expected_config:
        raise AnalyticalReplayValidationError(f"{field} exact case/config identity mismatch")
    config = case["config"]
    compiled = case.get("compiled_model")
    if not isinstance(compiled, dict) or set(compiled) != COMPILED_MODEL_KEYS:
        raise AnalyticalReplayValidationError(f"{field}.compiled_model key set mismatch")
    if compiled.get("model_xml_sha256") != model_record["model_xml_sha256"]:
        raise AnalyticalReplayValidationError(f"{field} compiled model SHA-256 mismatch")
    if compiled.get("config_sha256") != model_record["config_sha256"]:
        raise AnalyticalReplayValidationError(f"{field} compiled config SHA-256 mismatch")
    for name in (
        "compiled_timestep_s", "compiled_mass_kg", "solver_tolerance"
    ):
        _number(compiled.get(name), f"{field}.compiled_model.{name}")
    for name in (
        "solver_iterations", "nv", "nq", "nu", "nbody", "support_geom_id", "floor_geom_id"
    ):
        _integer(compiled.get(name), f"{field}.compiled_model.{name}")
    for name in (
        "integrator", "solver", "friction_cone", "support_geom_name", "floor_geom_name"
    ):
        _required_string(compiled.get(name), f"{field}.compiled_model.{name}")
    _vector(compiled.get("gravity_mps2"), 3, f"{field}.compiled_model.gravity_mps2")
    _vector(
        compiled.get("support_half_size_m"),
        3,
        f"{field}.compiled_model.support_half_size_m",
    )

    trace = case.get("raw_trace")
    if not isinstance(trace, list) or not trace:
        raise AnalyticalReplayValidationError(f"{field}.raw_trace must be nonempty")
    dt = float(config["physics_dt_s"])
    expected_steps = round(float(config["duration_s"]) / dt)
    expected_eval = round(
        (float(config["duration_s"]) - float(config["evaluation_start_s"])) / dt
    )
    model_mass_expected = float(config["base_mass_kg"] + config["payload_kg"])
    force_scale = max(
        model_mass_expected * float(config["gravity_mps2"]),
        1.0e-12,
    )
    moment_scale = force_scale * max(
        float(config["support_half_size_m"][0]),
        float(config["support_half_size_m"][1]),
    )
    evaluation_rows: list[dict] = []
    time_errors: list[float] = []
    qfrc_errors: list[float] = []
    applied_max = 0.0
    fwdinv_joint: list[float] = []
    fwdinv_constraint: list[float] = []
    serialized_receipt_delta_max = 0.0

    for step_index, step in enumerate(trace):
        prefix = f"{field}.raw_trace[{step_index}]"
        if not isinstance(step, dict) or set(step) != RAW_STEP_KEYS:
            raise AnalyticalReplayValidationError(f"{prefix} frozen key set mismatch")
        time_s = _number(step.get("time_s"), f"{prefix}.time_s")
        time_errors.append(abs(time_s - (step_index + 1) * dt))
        _vector(step.get("qpos"), 7, f"{prefix}.qpos")
        qvel = _vector(step.get("qvel"), 6, f"{prefix}.qvel")
        _vector(step.get("qacc"), 6, f"{prefix}.qacc")
        qfrc_constraint = _vector(
            step.get("qfrc_constraint"), 6, f"{prefix}.qfrc_constraint"
        )
        serialized_reconstructed = _vector(
            step.get("qfrc_contact_reconstructed"),
            6,
            f"{prefix}.qfrc_contact_reconstructed",
        )
        qfrc_applied = _vector(step.get("qfrc_applied"), 6, f"{prefix}.qfrc_applied")
        xfrc_applied = _matrix(step.get("xfrc_applied"), 2, 6, f"{prefix}.xfrc_applied")
        solver_fwdinv = _vector(step.get("solver_fwdinv"), 2, f"{prefix}.solver_fwdinv")
        fwdinv_joint.append(solver_fwdinv[0])
        fwdinv_constraint.append(solver_fwdinv[1])
        applied_max = max(
            applied_max,
            max((abs(item) for item in qfrc_applied), default=0.0),
            max((abs(item) for row in xfrc_applied for item in row), default=0.0),
        )
        support_origin = _vector(
            step.get("support_origin_world_m"), 3, f"{prefix}.support_origin_world_m"
        )
        support_rotation = _matrix(
            step.get("support_rotation_world"),
            3,
            3,
            f"{prefix}.support_rotation_world",
        )
        contacts = step.get("contacts")
        if not isinstance(contacts, list):
            raise AnalyticalReplayValidationError(f"{prefix}.contacts must be a list")
        if _integer(step.get("contact_count"), f"{prefix}.contact_count") != len(contacts):
            raise AnalyticalReplayValidationError(f"{prefix}.contact_count mismatch")

        reconstructed = [0.0] * 6
        contact_rows = []
        for contact_index, contact in enumerate(contacts):
            contact_prefix = f"{prefix}.contacts[{contact_index}]"
            (
                generalized,
                force_world,
                torque_world,
                friction_utilization,
                receipt_delta,
                contact_contract,
            ) = _replay_contact(contact, contact_index, contact_prefix)
            reconstructed = _add(reconstructed, generalized)
            serialized_receipt_delta_max = max(
                serialized_receipt_delta_max,
                receipt_delta,
            )
            contact_rows.append({
                "contact": contact,
                "force_world": force_world,
                "torque_world": torque_world,
                "friction_utilization": friction_utilization,
                "contact_contract": contact_contract,
            })
        serialized_receipt_delta_max = max(
            serialized_receipt_delta_max,
            _max_abs_delta(reconstructed, serialized_reconstructed),
        )
        residual = _subtract(qfrc_constraint, reconstructed)
        serialized_residual = _subtract(serialized_reconstructed, reconstructed)
        qfrc_errors.append(max(
            max((abs(item) for item in residual[:3]), default=0.0) / force_scale,
            max((abs(item) for item in residual[3:]), default=0.0) / moment_scale,
            max((abs(item) for item in serialized_residual[:3]), default=0.0)
            / force_scale,
            max((abs(item) for item in serialized_residual[3:]), default=0.0)
            / moment_scale,
            serialized_receipt_delta_max,
        ))

        if time_s <= float(config["evaluation_start_s"]) + 1.0e-12:
            continue
        support_id = int(compiled["support_geom_id"])
        floor_id = int(compiled["floor_geom_id"])
        total_force_world = [0.0, 0.0, 0.0]
        total_moment_world = [0.0, 0.0, 0.0]
        active = 0
        expected_active = 0
        unexpected = 0
        normal_forces: list[float] = []
        friction_values: list[float] = []
        contact_contract_valid = True
        for item in contact_rows:
            contact = item["contact"]
            if contact["active"] is not True:
                continue
            active += 1
            pair = {int(contact["geom1_id"]), int(contact["geom2_id"])}
            names = {contact["geom1_name"], contact["geom2_name"]}
            expected_names = {
                compiled["support_geom_name"],
                compiled["floor_geom_name"],
            }
            if pair != {support_id, floor_id} or names != expected_names:
                unexpected += 1
                continue
            expected_active += 1
            contact_contract_valid = bool(
                contact_contract_valid and item["contact_contract"]
            )
            sign = 1.0 if int(contact["geom2_id"]) == support_id else -1.0
            position = _vector(
                contact.get("position_world_m"), 3, "contact.position_world_m"
            )
            force_on_support = _scale(item["force_world"], sign)
            torque_on_support = _scale(item["torque_world"], sign)
            total_force_world = _add(total_force_world, force_on_support)
            total_moment_world = _add(
                total_moment_world,
                _add(
                    _cross(_subtract(position, support_origin), force_on_support),
                    torque_on_support,
                ),
            )
            wrench = _vector(
                contact.get("wrench_local_force_torque"),
                6,
                "contact.wrench_local_force_torque",
            )
            normal_forces.append(wrench[0])
            friction_values.append(float(item["friction_utilization"]))
        force_local = _transpose_vector(support_rotation, total_force_world)
        moment_local = _transpose_vector(support_rotation, total_moment_world)
        vertical_force = force_local[2]
        margin = -1.0e300
        if expected_active > 0 and vertical_force > 1.0e-12:
            half = list(FROZEN_CONTRACT["support_half_size_m"])
            sole_z = -half[2]
            cop_x = (sole_z * force_local[0] - moment_local[1]) / vertical_force
            cop_y = (moment_local[0] + sole_z * force_local[1]) / vertical_force
            margin = min(half[0] - abs(cop_x), half[1] - abs(cop_y))
        evaluation_rows.append({
            "exact_support": bool(active > 0 and unexpected == 0),
            "unexpected_contact_count": unexpected,
            "contact_model_contract_valid": contact_contract_valid,
            "minimum_contact_normal_force_n": min(normal_forces, default=-1.0e300),
            "maximum_friction_utilization": max(friction_values, default=0.0),
            "cop_support_margin_m": margin,
            "vertical_support_force_n": total_force_world[2],
            "linear_speed_mps": _norm(qvel[:3]),
            "angular_speed_rps": _norm(qvel[3:]),
        })

    if not evaluation_rows:
        raise AnalyticalReplayValidationError(f"{field} has no evaluation samples")
    model_weight = model_mass_expected * float(config["gravity_mps2"])
    mean_grf = sum(row["vertical_support_force_n"] for row in evaluation_rows) / len(
        evaluation_rows
    )
    metrics = {
        "finite": True,
        "trace_step_count": len(trace),
        "evaluation_step_count": len(evaluation_rows),
        "time_grid_error_max_s": max(time_errors),
        "compiled_timestep_error_s": abs(float(compiled["compiled_timestep_s"]) - dt),
        "compiled_model_contract_valid": _compiled_contract(compiled, config),
        "model_mass_error_kg": abs(float(compiled["compiled_mass_kg"]) - model_mass_expected),
        "forward_inverse_joint_force_norm_max": max(fwdinv_joint),
        "forward_inverse_constraint_force_norm_max": max(fwdinv_constraint),
        "raw_jacobian_closure_relative_max": max(qfrc_errors),
        "maximum_external_applied_force": applied_max,
        "exact_single_support_duty": sum(
            1.0 if row["exact_support"] else 0.0 for row in evaluation_rows
        ) / len(evaluation_rows),
        "maximum_unexpected_contact_count": max(
            row["unexpected_contact_count"] for row in evaluation_rows
        ),
        "contact_model_contract_valid": all(
            row["contact_model_contract_valid"] for row in evaluation_rows
        ),
        "minimum_contact_normal_force_n": min(
            row["minimum_contact_normal_force_n"] for row in evaluation_rows
        ),
        "maximum_friction_utilization": max(
            row["maximum_friction_utilization"] for row in evaluation_rows
        ),
        "minimum_cop_support_margin_m": min(
            row["cop_support_margin_m"] for row in evaluation_rows
        ),
        "model_weight_n": model_weight,
        "mean_vertical_grf_n": mean_grf,
        "weight_balance_relative_error": abs(mean_grf - model_weight) / max(model_weight, 1.0e-12),
        "mean_linear_speed_mps": sum(row["linear_speed_mps"] for row in evaluation_rows) / len(evaluation_rows),
        "mean_angular_speed_rps": sum(row["angular_speed_rps"] for row in evaluation_rows) / len(evaluation_rows),
        "timestep_qoi_normalized_mean_grf": mean_grf / max(model_weight, 1.0e-12),
    }
    limits = FROZEN_CONTRACT["tolerances"]
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
    receipt = {
        "case_id": config["case_id"],
        "status": "PASS" if all(item["passed"] for item in criteria) else "FAIL",
        "metrics": metrics,
        "criteria": criteria,
    }
    return receipt, serialized_receipt_delta_max


def _non_dt_config(config: dict) -> dict:
    return {
        key: value
        for key, value in config.items()
        if key not in {"case_id", "physics_dt_s", "payload_kg", "roles"}
    }


def _evaluate_suite(cases: list[dict], model_records: dict[str, dict]) -> tuple[list[dict], dict, list[dict], float]:
    receipts: list[dict] = []
    raw_identity_max = 0.0
    for index, case in enumerate(cases):
        case_id = CASE_SPECS[index]["case_id"]
        receipt, case_raw_identity = _evaluate_case(
            case,
            model_records[case_id],
            index,
        )
        receipts.append(receipt)
        raw_identity_max = max(raw_identity_max, case_raw_identity)
    by_id = {item["case_id"]: item for item in receipts}
    raw_by_id = {item["case_id"]: item for item in cases}
    nominal = by_id["single_support_nominal_dt_2ms"]["metrics"]
    payload = by_id["single_support_payload_5kg_dt_2ms"]["metrics"]
    payload_expected = float(FROZEN_CONTRACT["known_payload_kg"])
    nominal_mass = float(
        raw_by_id["single_support_nominal_dt_2ms"]["compiled_model"]["compiled_mass_kg"]
    )
    payload_mass = float(
        raw_by_id["single_support_payload_5kg_dt_2ms"]["compiled_model"]["compiled_mass_kg"]
    )
    mass_delta_error = abs((payload_mass - nominal_mass) - payload_expected)
    expected_grf_delta = payload_expected * float(FROZEN_CONTRACT["gravity_mps2"])
    measured_grf_delta = payload["mean_vertical_grf_n"] - nominal["mean_vertical_grf_n"]
    grf_delta_error = abs(measured_grf_delta - expected_grf_delta) / expected_grf_delta
    q4 = by_id["single_support_nominal_dt_4ms"]["metrics"]["timestep_qoi_normalized_mean_grf"]
    q2 = nominal["timestep_qoi_normalized_mean_grf"]
    q1 = by_id["single_support_nominal_dt_1ms"]["metrics"]["timestep_qoi_normalized_mean_grf"]
    coarse_delta = abs(q4 - q2)
    fine_delta = abs(q2 - q1)
    floor = float(FROZEN_CONTRACT["tolerances"]["timestep_roundoff_floor"])
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
    same_non_dt = all(
        _non_dt_config(item) == _non_dt_config(nominal_configs[0])
        for item in nominal_configs[1:]
    )
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
    limits = FROZEN_CONTRACT["tolerances"]
    criteria = [
        _criterion("EXACT_CASE_INVENTORY", True, "==", True, "bool"),
        _criterion("EXACT_MODEL_INVENTORY", True, "==", True, "bool"),
        _criterion("ALL_CASES_PASS", metrics["case_pass_count"], "==", len(CASE_SPECS), "cases"),
        _criterion("PAYLOAD_MASS_DELTA", mass_delta_error, "<=", limits["payload_mass_delta_error_max_kg"], "kg"),
        _criterion("PAYLOAD_GRF_DELTA", grf_delta_error, "<=", limits["payload_grf_delta_relative_error_max"], "relative error"),
        _criterion("TIMESTEP_NON_DT_CONFIG_IDENTITY", same_non_dt, "==", True, "bool"),
        _criterion("TIMESTEP_FINE_QOI_DELTA", fine_delta, "<=", limits["timestep_fine_qoi_delta_max"], "normalized GRF delta"),
        _criterion("TIMESTEP_NON_DIVERGENCE", fine_delta, "<=", max(coarse_delta, floor), "normalized GRF delta"),
    ]
    return receipts, metrics, criteria, raw_identity_max


def _tree_match(left: Any, right: Any) -> tuple[bool, float]:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is bool and type(right) is bool and left == right, 0.0
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return True, abs(float(left) - float(right))
    if left is None or right is None:
        return left is None and right is None, 0.0
    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right, 0.0
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return False, 0.0
        exact = True
        delta = 0.0
        for left_item, right_item in zip(left, right, strict=True):
            item_exact, item_delta = _tree_match(left_item, right_item)
            exact = exact and item_exact
            delta = max(delta, item_delta)
        return exact, delta
    if isinstance(left, dict) and isinstance(right, dict):
        if set(left) != set(right):
            return False, 0.0
        exact = True
        delta = 0.0
        for key in left:
            item_exact, item_delta = _tree_match(left[key], right[key])
            exact = exact and item_exact
            delta = max(delta, item_delta)
        return exact, delta
    return left == right, 0.0


def replay_analytical_suite(
    primary_result: dict,
    model_package: dict,
    *,
    source_artifact_sha256: str | None = None,
    model_package_artifact_sha256: str | None = None,
) -> dict:
    """Recompute the frozen suite without importing the simulation stack."""
    model_records = _validate_model_package(model_package)
    _validate_primary_shell(primary_result, model_package)
    if source_artifact_sha256 is not None:
        _valid_sha256(source_artifact_sha256, "source_artifact_sha256")
    if model_package_artifact_sha256 is not None:
        _valid_sha256(model_package_artifact_sha256, "model_package_artifact_sha256")
    case_receipts, metrics, scientific_criteria, raw_identity_max = _evaluate_suite(
        primary_result["cases"],
        model_records,
    )
    case_exact, case_delta = _tree_match(primary_result["case_receipts"], case_receipts)
    metric_exact, metric_delta = _tree_match(primary_result["metrics"], metrics)
    criteria_exact, criteria_delta = _tree_match(primary_result["criteria"], scientific_criteria)
    expected_primary_status = (
        "PASS" if all(item["passed"] for item in scientific_criteria) else "FAIL"
    )
    summary_delta = max(case_delta, metric_delta, criteria_delta)
    replay_metrics = dict(metrics)
    replay_metrics.update({
        "raw_serialized_receipt_delta_max": raw_identity_max,
        "primary_summary_numeric_delta_max": summary_delta,
        "primary_case_receipts_exact": case_exact,
        "primary_metrics_exact": metric_exact,
        "primary_criteria_exact": criteria_exact,
        "primary_status_matches_replay": primary_result["status"] == expected_primary_status,
    })
    criteria = list(scientific_criteria)
    criteria.extend([
        _criterion("RAW_SERIALIZED_RECEIPT_IDENTITY", raw_identity_max, "<=", 1.0e-12, "max absolute delta"),
        _criterion("PRIMARY_CASE_RECEIPT_IDENTITY", case_exact and case_delta <= 1.0e-12, "==", True, "bool"),
        _criterion("PRIMARY_SUITE_METRIC_IDENTITY", metric_exact and metric_delta <= 1.0e-12, "==", True, "bool"),
        _criterion("PRIMARY_SUITE_CRITERIA_IDENTITY", criteria_exact and criteria_delta <= 1.0e-12, "==", True, "bool"),
        _criterion("PRIMARY_STATUS_IDENTITY", primary_result["status"] == expected_primary_status, "==", True, "bool"),
    ])
    return {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "source_schema_version": primary_result["schema_version"],
        "model_package_schema_version": model_package["schema_version"],
        "source_artifact_sha256": source_artifact_sha256,
        "model_package_artifact_sha256": model_package_artifact_sha256,
        "model_package_content_sha256": model_package["content_sha256"],
        "evidence_scope": "PROCESS_INDEPENDENT_ANALYTICAL_REPLAY_ONLY",
        "claim_boundary": REPLAY_CLAIM_BOUNDARY,
        "replayed_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(item["passed"] for item in criteria) else "FAIL",
        "case_receipts": case_receipts,
        "metrics": replay_metrics,
        "criteria": criteria,
    }


def _reject_nonstandard_json(value: str) -> None:
    raise AnalyticalReplayValidationError(
        f"non-standard JSON constant is forbidden: {value}"
    )


def _load_json(path: Path) -> tuple[dict, str]:
    payload = path.read_bytes()
    value = json.loads(
        payload.decode("utf-8"),
        parse_constant=_reject_nonstandard_json,
    )
    if not isinstance(value, dict):
        raise AnalyticalReplayValidationError(f"{path} must contain a JSON object")
    return value, f"sha256:{hashlib.sha256(payload).hexdigest()}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay a frozen V1 analytical primary result and model package"
    )
    parser.add_argument("primary_artifact", type=Path)
    parser.add_argument("model_package_artifact", type=Path)
    args = parser.parse_args()
    primary, primary_sha = _load_json(args.primary_artifact)
    package, package_sha = _load_json(args.model_package_artifact)
    receipt = replay_analytical_suite(
        primary,
        package,
        source_artifact_sha256=primary_sha,
        model_package_artifact_sha256=package_sha,
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
