"""Process-independent replay for the bounded V1 raw-Jacobian evidence bundle.

This module intentionally imports neither MuJoCo nor the live controller. It
recomputes contact generalized forces, friction utilization and foot CoP from
the serialized contact frame, wrench and relative Jacobians only.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any


class ReplayValidationError(ValueError):
    """Raw evidence 不完整、非有限或不符合 frozen schema。"""


RELATIVE_JACOBIAN_CONVENTION = (
    "BODY2_MINUS_BODY1_AT_CONTACT_POINT_WORLD_ALIGNED_ROWS_DOF_COLUMNS"
)
RESOLVED_MODEL_KEYS = frozenset({
    "mass_kg",
    "gravity_mps2",
    "friction_cone",
    "solver",
    "adhesion_enabled",
    "model_xml_sha256",
    "nv",
    "nq",
    "nu",
    "nbody",
})
RAW_STEP_KEYS = frozenset({
    "time_s",
    "qpos",
    "qvel",
    "qacc",
    "ctrl",
    "qfrc_inverse",
    "qfrc_actuator",
    "qfrc_applied",
    "xfrc_applied",
    "qfrc_passive",
    "qfrc_bias",
    "qfrc_constraint",
    "qfrc_contact_reconstructed",
    "solver_fwdinv",
    "contact_count",
    "contacts",
    "foot_support",
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
FOOT_SUPPORT_KEYS = frozenset({
    "available",
    "reason",
    "geom_id",
    "geom_type",
    "geom_size_m",
    "origin_world_m",
    "rotation_world",
    "active_contact_count",
    "aggregate_force_local_n",
    "aggregate_moment_local_nm",
    "normal_load_n",
    "cop_local_m",
    "support_margin_m",
})


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReplayValidationError(f"{field} must be a finite number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ReplayValidationError(f"{field} must be finite")
    return numeric


def _assert_finite_tree(value: Any, field: str) -> None:
    """Fail closed：evaluation window 外的 raw value 也不得含 NaN/Infinity。"""
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
                raise ReplayValidationError(f"{field} contains a non-string key")
            _assert_finite_tree(item, f"{field}.{key}")
        return
    raise ReplayValidationError(f"{field} contains unsupported value type")


def _vector(value: Any, length: int, field: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise ReplayValidationError(f"{field} must contain {length} numbers")
    return [_number(item, f"{field}[{index}]") for index, item in enumerate(value)]


def _matrix3(value: Any, field: str) -> list[list[float]]:
    if not isinstance(value, list) or len(value) != 3:
        raise ReplayValidationError(f"{field} must be a 3x3 matrix")
    return [_vector(row, 3, f"{field}[{index}]") for index, row in enumerate(value)]


def _matrix3_by_nv(value: Any, nv: int, field: str) -> list[list[float]]:
    if not isinstance(value, list) or len(value) != 3:
        raise ReplayValidationError(f"{field} must be a 3x{nv} matrix")
    return [_vector(row, nv, f"{field}[{index}]") for index, row in enumerate(value)]


def _matrix(value: Any, rows: int, columns: int, field: str) -> list[list[float]]:
    if not isinstance(value, list) or len(value) != rows:
        raise ReplayValidationError(f"{field} must be a {rows}x{columns} matrix")
    return [
        _vector(row, columns, f"{field}[{index}]")
        for index, row in enumerate(value)
    ]


def _integer(value: Any, field: str) -> int:
    numeric = _number(value, field)
    if not numeric.is_integer():
        raise ReplayValidationError(f"{field} must be an integer")
    return int(numeric)


def _transpose_multiply(matrix: list[list[float]], vector: list[float]) -> list[float]:
    width = len(matrix[0])
    return [
        sum(matrix[row][column] * vector[row] for row in range(3))
        for column in range(width)
    ]


def _cross(left: list[float], right: list[float]) -> list[float]:
    return [
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    ]


def _add(left: list[float], right: list[float]) -> list[float]:
    return [a + b for a, b in zip(left, right, strict=True)]


def _subtract(left: list[float], right: list[float]) -> list[float]:
    return [a - b for a, b in zip(left, right, strict=True)]


def _scale(vector: list[float], factor: float) -> list[float]:
    return [factor * item for item in vector]


def _norm(vector: list[float]) -> float:
    return math.sqrt(sum(item * item for item in vector))


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReplayValidationError(f"{field} must be a non-empty string")
    return value


def _friction_utilization(contact: dict, cone_name: str, prefix: str) -> float:
    dimension = _integer(contact.get("dimension"), f"{prefix}.dimension")
    friction_dimensions = max(0, min(dimension - 1, 5))
    if friction_dimensions == 0:
        return 0.0
    wrench = _vector(
        contact.get("wrench_local_force_torque"),
        6,
        f"{prefix}.wrench_local_force_torque",
    )
    friction = _vector(
        contact.get("friction_parameters"),
        5,
        f"{prefix}.friction_parameters",
    )
    components = [wrench[1], wrench[2], wrench[3], wrench[4], wrench[5]][
        :friction_dimensions
    ]
    normal_force = wrench[0]
    if normal_force <= 1.0e-12:
        return 0.0 if max(abs(item) for item in components) <= 1.0e-12 else 1.0e12
    scaled = [
        component / max(coefficient, 1.0e-12)
        for component, coefficient in zip(
            components,
            friction[:friction_dimensions],
            strict=True,
        )
    ]
    if cone_name == "PYRAMIDAL":
        return sum(abs(item) for item in scaled) / normal_force
    if cone_name == "ELLIPTIC":
        return _norm(scaled) / normal_force
    raise ReplayValidationError(f"unsupported friction cone: {cone_name}")


def _contact_world_wrench(contact: dict, prefix: str) -> tuple[list[float], list[float]]:
    frame = _matrix3(contact.get("contact_frame_world"), f"{prefix}.contact_frame_world")
    wrench = _vector(
        contact.get("wrench_local_force_torque"),
        6,
        f"{prefix}.wrench_local_force_torque",
    )
    return (
        _transpose_multiply(frame, wrench[0:3]),
        _transpose_multiply(frame, wrench[3:6]),
    )


def _contact_generalized_force(
    contact: dict,
    contact_index: int,
    nv: int,
    expected_contact_dimension: int,
    expected_adhesion_n: float,
    cone_name: str,
    prefix: str,
) -> list[float]:
    """只由 raw frame、wrench 與 relative Jacobian 重建 generalized force。"""
    missing_fields = RAW_CONTACT_KEYS - set(contact)
    unexpected_fields = set(contact) - RAW_CONTACT_KEYS
    if missing_fields or unexpected_fields:
        raise ReplayValidationError(
            f"{prefix} frozen contact fields mismatch; "
            f"missing={sorted(missing_fields)}, unexpected={sorted(unexpected_fields)}"
        )
    if _integer(contact.get("contact_index"), f"{prefix}.contact_index") != contact_index:
        raise ReplayValidationError(f"{prefix}.contact_index does not match list index")
    dimension = _integer(contact.get("dimension"), f"{prefix}.dimension")
    if dimension != expected_contact_dimension:
        raise ReplayValidationError(
            f"{prefix}.dimension CONTRACT_VIOLATION_CONTACT_DIMENSION: "
            f"{dimension} != {expected_contact_dimension}"
        )
    active = _contact_is_active(contact, prefix)
    for field in ("geom1_id", "geom2_id", "body1_id", "body2_id"):
        if _integer(contact.get(field), f"{prefix}.{field}") < 0:
            raise ReplayValidationError(f"{prefix}.{field} must be nonnegative")
    for field in ("geom1_name", "geom2_name", "body1_name", "body2_name"):
        _required_string(contact.get(field), f"{prefix}.{field}")
    _vector(contact.get("position_world_m"), 3, f"{prefix}.position_world_m")
    adhesion_n = _number(contact.get("adhesion_n"), f"{prefix}.adhesion_n")
    if adhesion_n != expected_adhesion_n:
        raise ReplayValidationError(
            f"{prefix}.adhesion_n CONTRACT_VIOLATION_ADHESION: "
            f"{adhesion_n} != {expected_adhesion_n}"
        )
    jacobian_translation = _matrix3_by_nv(
        contact.get("jacobian_translation_relative_world"),
        nv,
        f"{prefix}.jacobian_translation_relative_world",
    )
    jacobian_rotation = _matrix3_by_nv(
        contact.get("jacobian_rotation_relative_world"),
        nv,
        f"{prefix}.jacobian_rotation_relative_world",
    )
    force_world, torque_world = _contact_world_wrench(contact, prefix)
    _vector(
        contact.get("force_world_n"),
        3,
        f"{prefix}.force_world_n",
    )
    _vector(
        contact.get("torque_world_nm"),
        3,
        f"{prefix}.torque_world_nm",
    )
    wrench = _vector(
        contact.get("wrench_local_force_torque"),
        6,
        f"{prefix}.wrench_local_force_torque",
    )
    _number(contact.get("normal_force_n"), f"{prefix}.normal_force_n")
    if contact.get("friction_cone") != cone_name:
        raise ReplayValidationError(f"{prefix}.friction_cone receipt mismatch")
    _vector(contact.get("friction_parameters"), 5, f"{prefix}.friction_parameters")
    _number(
        contact.get("friction_utilization"),
        f"{prefix}.friction_utilization",
    )
    if not active:
        if any(item != 0.0 for item in wrench):
            raise ReplayValidationError(
                f"{prefix} inactive contact must have a zero wrench"
            )
    return _add(
        _transpose_multiply(jacobian_translation, force_world),
        _transpose_multiply(jacobian_rotation, torque_world),
    )


def _contact_is_active(contact: dict, prefix: str) -> bool:
    exclude = _integer(contact.get("exclude"), f"{prefix}.exclude")
    efc_address = _integer(contact.get("efc_address"), f"{prefix}.efc_address")
    active = contact.get("active")
    if type(active) is not bool:
        raise ReplayValidationError(f"{prefix}.active must be a boolean")
    expected_active = exclude == 0 and efc_address >= 0
    if active != expected_active:
        raise ReplayValidationError(
            f"{prefix}.active does not match exclude/efc_address"
        )
    return active


def _foot_support_metrics(step: dict, support_names: list[str], prefix: str) -> tuple[list[float], int]:
    support_receipts = step.get("foot_support")
    contacts = step.get("contacts")
    if not isinstance(support_receipts, dict) or not isinstance(contacts, list):
        raise ReplayValidationError(f"{prefix} lacks foot_support or contacts")
    if set(support_receipts) != set(support_names):
        raise ReplayValidationError(f"{prefix}.foot_support names do not match contract")

    margins: list[float] = []
    loaded_count = 0
    for support_name in support_names:
        support = support_receipts.get(support_name)
        if not isinstance(support, dict):
            raise ReplayValidationError(f"{prefix}.foot_support.{support_name} missing")
        support_prefix = f"{prefix}.foot_support.{support_name}"
        if set(support) != FOOT_SUPPORT_KEYS:
            raise ReplayValidationError(
                f"{support_prefix} does not match frozen support fields"
            )
        available_receipt = support.get("available")
        if type(available_receipt) is not bool:
            raise ReplayValidationError(f"{support_prefix}.available must be a boolean")
        reason = support.get("reason")
        if reason is not None and (not isinstance(reason, str) or not reason):
            raise ReplayValidationError(f"{support_prefix}.reason invalid")
        geom_id = _integer(
            support.get("geom_id"),
            f"{support_prefix}.geom_id",
        )
        geom_type = _required_string(
            support.get("geom_type"),
            f"{support_prefix}.geom_type",
        )
        size = _vector(
            support.get("geom_size_m"),
            3,
            f"{support_prefix}.geom_size_m",
        )
        origin = _vector(
            support.get("origin_world_m"),
            3,
            f"{support_prefix}.origin_world_m",
        )
        rotation = _matrix3(
            support.get("rotation_world"),
            f"{support_prefix}.rotation_world",
        )
        active_count_receipt = _integer(
            support.get("active_contact_count"),
            f"{support_prefix}.active_contact_count",
        )
        aggregate_force_receipt = _vector(
            support.get("aggregate_force_local_n"),
            3,
            f"{support_prefix}.aggregate_force_local_n",
        )
        aggregate_moment_receipt = _vector(
            support.get("aggregate_moment_local_nm"),
            3,
            f"{support_prefix}.aggregate_moment_local_nm",
        )
        normal_load_receipt = _number(
            support.get("normal_load_n"),
            f"{support_prefix}.normal_load_n",
        )
        total_force_world = [0.0, 0.0, 0.0]
        total_moment_world = [0.0, 0.0, 0.0]
        contact_count = 0
        for contact_index, contact in enumerate(contacts):
            if not isinstance(contact, dict):
                raise ReplayValidationError(f"{prefix}.contacts[{contact_index}] invalid")
            if not _contact_is_active(contact, f"{prefix}.contacts[{contact_index}]"):
                continue
            geom1 = int(_number(
                contact.get("geom1_id"),
                f"{prefix}.contacts[{contact_index}].geom1_id",
            ))
            geom2 = int(_number(
                contact.get("geom2_id"),
                f"{prefix}.contacts[{contact_index}].geom2_id",
            ))
            sign = 1.0 if geom2 == geom_id else -1.0 if geom1 == geom_id else 0.0
            if sign == 0.0:
                continue
            contact_count += 1
            contact_prefix = f"{prefix}.contacts[{contact_index}]"
            force_world, torque_world = _contact_world_wrench(contact, contact_prefix)
            force_on_support = _scale(force_world, sign)
            torque_on_support = _scale(torque_world, sign)
            position = _vector(
                contact.get("position_world_m"),
                3,
                f"{contact_prefix}.position_world_m",
            )
            total_force_world = _add(total_force_world, force_on_support)
            total_moment_world = _add(
                total_moment_world,
                _add(_cross(_subtract(position, origin), force_on_support), torque_on_support),
            )

        total_force_local = _transpose_multiply(rotation, total_force_world)
        total_moment_local = _transpose_multiply(rotation, total_moment_world)
        normal_load = total_force_local[2]
        available = bool(
            contact_count > 0
            and normal_load > 1.0e-12
            and geom_type == "mjGEOM_BOX"
        )
        # Summary receipts 只做 schema/finite 檢查；criterion 只信任上方重算值。
        _ = (
            active_count_receipt,
            aggregate_force_receipt,
            aggregate_moment_receipt,
            normal_load_receipt,
            available_receipt,
        )
        if not available:
            if support.get("cop_local_m") is not None:
                _vector(
                    support.get("cop_local_m"),
                    3,
                    f"{support_prefix}.cop_local_m",
                )
            if support.get("support_margin_m") is not None:
                _number(
                    support.get("support_margin_m"),
                    f"{support_prefix}.support_margin_m",
                )
            continue
        loaded_count += 1
        sole_z = -size[2]
        cop_x = (sole_z * total_force_local[0] - total_moment_local[1]) / normal_load
        cop_y = (total_moment_local[0] + sole_z * total_force_local[1]) / normal_load
        margin = min(size[0] - abs(cop_x), size[1] - abs(cop_y))
        _vector(
            support.get("cop_local_m"),
            3,
            f"{support_prefix}.cop_local_m",
        )
        _number(
            support.get("support_margin_m"),
            f"{support_prefix}.support_margin_m",
        )
        margins.append(margin)
    return margins, loaded_count


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
        raise ReplayValidationError(f"unsupported replay operator: {operator}")
    return {
        "id": criterion_id,
        "passed": bool(passed),
        "value": value,
        "operator": operator,
        "limit": limit,
        "unit": unit,
    }


def replay_static_double_support_bundle(
    bundle: dict,
    *,
    artifact_sha256: str | None = None,
) -> dict:
    """只使用 serialized bundle 重算 contact-related V1 metrics。"""
    _assert_finite_tree(bundle, "bundle")
    if bundle.get("schema_version") != "V1_STATIC_DOUBLE_SUPPORT_ORACLE_V4":
        raise ReplayValidationError("unsupported source schema_version")
    contract = bundle.get("contract")
    model = bundle.get("resolved_model")
    trace = bundle.get("raw_trace")
    if not isinstance(contract, dict) or not isinstance(model, dict) or not isinstance(trace, list):
        raise ReplayValidationError("bundle lacks contract, resolved_model, or raw_trace")

    duration_s = _number(contract.get("duration_s"), "contract.duration_s")
    window_s = _number(contract.get("evaluation_window_s"), "contract.evaluation_window_s")
    dt_s = _number(contract.get("physics_dt_s"), "contract.physics_dt_s")
    if duration_s <= 0.0 or dt_s <= 0.0 or window_s <= 0.0 or window_s > duration_s:
        raise ReplayValidationError("contract duration/window/dt must define a valid grid")
    characteristic_length = _number(
        contract.get("characteristic_length_m"),
        "contract.characteristic_length_m",
    )
    support_names = contract.get("support_geom_names")
    tolerances = contract.get("tolerances")
    if not isinstance(support_names, list) or not all(isinstance(item, str) for item in support_names):
        raise ReplayValidationError("contract.support_geom_names invalid")
    if not isinstance(tolerances, dict):
        raise ReplayValidationError("contract.tolerances invalid")
    if contract.get("relative_jacobian_convention") != RELATIVE_JACOBIAN_CONVENTION:
        raise ReplayValidationError("unsupported relative Jacobian convention")
    expected_contact_dimension = _integer(
        contract.get("expected_contact_dimension"),
        "contract.expected_contact_dimension",
    )
    if expected_contact_dimension != 3:
        raise ReplayValidationError("frozen replay requires condim=3 contacts")
    expected_adhesion_n = _number(
        contract.get("expected_contact_adhesion_n"),
        "contract.expected_contact_adhesion_n",
    )
    if expected_adhesion_n != 0.0:
        raise ReplayValidationError("frozen replay only supports non-adhesive contacts")

    cone_name = model.get("friction_cone")
    if set(model) != RESOLVED_MODEL_KEYS:
        raise ReplayValidationError("resolved_model does not match frozen fields")
    if cone_name != contract.get("expected_friction_cone"):
        raise ReplayValidationError("resolved friction cone does not match contract")
    _required_string(model.get("solver"), "resolved_model.solver")
    model_xml_sha256 = _required_string(
        model.get("model_xml_sha256"),
        "resolved_model.model_xml_sha256",
    )
    if (
        not model_xml_sha256.startswith("sha256:")
        or len(model_xml_sha256) != 71
        or any(character not in "0123456789abcdef" for character in model_xml_sha256[7:])
    ):
        raise ReplayValidationError("resolved_model.model_xml_sha256 invalid")
    if model.get("adhesion_enabled") is not False:
        raise ReplayValidationError("resolved model must disable contact adhesion")
    nv = _integer(model.get("nv"), "resolved_model.nv")
    if nv <= 6:
        raise ReplayValidationError("resolved_model.nv must exceed floating-base DOFs")
    nq = _integer(model.get("nq"), "resolved_model.nq")
    nu = _integer(model.get("nu"), "resolved_model.nu")
    nbody = _integer(model.get("nbody"), "resolved_model.nbody")
    if nq <= 0 or nu < 0 or nbody <= 0:
        raise ReplayValidationError("resolved model dimensions invalid")
    mass_kg = _number(model.get("mass_kg"), "resolved_model.mass_kg")
    if mass_kg <= 0.0:
        raise ReplayValidationError("resolved_model.mass_kg must be positive")
    gravity = _vector(model.get("gravity_mps2"), 3, "resolved_model.gravity_mps2")
    model_weight_n = mass_kg * abs(gravity[2])
    moment_scale_nm = model_weight_n * characteristic_length
    expected_step_count = round(duration_s / dt_s)
    expected_evaluation_step_count = round(window_s / dt_s)
    times: list[float] = []
    raw_jacobian_closure_all_steps_relative_max = 0.0
    evaluation_rows: list[tuple[float, float, float, float, float, float, float, int]] = []
    evaluation_start = duration_s - window_s

    for step_index, step in enumerate(trace):
        if not isinstance(step, dict):
            raise ReplayValidationError(f"raw_trace[{step_index}] invalid")
        prefix = f"raw_trace[{step_index}]"
        if set(step) != RAW_STEP_KEYS:
            raise ReplayValidationError(f"{prefix} does not match frozen step fields")
        time_s = _number(step.get("time_s"), f"{prefix}.time_s")
        times.append(time_s)

        _vector(step.get("qpos"), nq, f"{prefix}.qpos")
        for field in (
            "qvel",
            "qacc",
            "qfrc_inverse",
            "qfrc_actuator",
            "qfrc_applied",
            "qfrc_passive",
            "qfrc_bias",
        ):
            _vector(step.get(field), nv, f"{prefix}.{field}")
        _vector(step.get("ctrl"), nu, f"{prefix}.ctrl")
        _matrix(step.get("xfrc_applied"), nbody, 6, f"{prefix}.xfrc_applied")
        _vector(step.get("solver_fwdinv"), 2, f"{prefix}.solver_fwdinv")

        qfrc_constraint_value = step.get("qfrc_constraint")
        contacts = step.get("contacts")
        if not isinstance(qfrc_constraint_value, list) or not isinstance(contacts, list):
            raise ReplayValidationError(f"{prefix} lacks qfrc_constraint or contacts")
        if len(qfrc_constraint_value) != nv:
            raise ReplayValidationError(
                f"{prefix}.qfrc_constraint must contain resolved_model.nv={nv} numbers"
            )
        contact_count = _integer(step.get("contact_count"), f"{prefix}.contact_count")
        if contact_count != len(contacts):
            raise ReplayValidationError(
                f"{prefix}.contact_count does not match serialized contacts"
            )
        qfrc_constraint = _vector(qfrc_constraint_value, nv, f"{prefix}.qfrc_constraint")
        reconstructed = [0.0] * nv
        for contact_index, contact in enumerate(contacts):
            if not isinstance(contact, dict):
                raise ReplayValidationError(f"{prefix}.contacts[{contact_index}] invalid")
            contact_prefix = f"{prefix}.contacts[{contact_index}]"
            generalized = _contact_generalized_force(
                contact,
                contact_index,
                nv,
                expected_contact_dimension,
                expected_adhesion_n,
                str(cone_name),
                contact_prefix,
            )
            reconstructed = _add(reconstructed, generalized)

        serialized_reconstructed = _vector(
            step.get("qfrc_contact_reconstructed"),
            nv,
            f"{prefix}.qfrc_contact_reconstructed",
        )
        # Primary aggregate 只保留為 summary receipt；closure 只用 raw J/wrench 重算。
        _ = serialized_reconstructed

        residual = _subtract(qfrc_constraint, reconstructed)
        normalized_components = [
            *(item / max(model_weight_n, 1.0e-12) for item in residual[0:3]),
            *(item / max(moment_scale_nm, 1.0e-12) for item in residual[3:]),
        ]
        raw_jacobian_closure_all_steps_relative_max = max(
            raw_jacobian_closure_all_steps_relative_max,
            max(abs(item) for item in normalized_components),
        )

        # 每個 raw step都先完成 schema/Jacobian closure，再限定 scientific window。
        if time_s <= evaluation_start + 1.0e-12:
            continue

        normal_forces: list[float] = []
        friction_utilizations: list[float] = []
        for contact_index, contact in enumerate(contacts):
            contact_prefix = f"{prefix}.contacts[{contact_index}]"
            if contact["active"] is not True:
                continue
            wrench = _vector(
                contact.get("wrench_local_force_torque"),
                6,
                f"{contact_prefix}.wrench_local_force_torque",
            )
            normal_forces.append(wrench[0])
            friction_utilizations.append(
                _friction_utilization(contact, str(cone_name), contact_prefix)
            )

        cop_margins, loaded_count = _foot_support_metrics(
            step,
            support_names,
            prefix,
        )
        evaluation_rows.append((
            max(abs(item) for item in normalized_components),
            _norm(residual[0:3]) / max(model_weight_n, 1.0e-12),
            _norm(residual[3:6]) / max(moment_scale_nm, 1.0e-12),
            _norm(residual[6:]) / max(moment_scale_nm, 1.0e-12),
            min(normal_forces, default=0.0),
            max(friction_utilizations, default=0.0),
            min(cop_margins, default=-1.0e12),
            loaded_count,
        ))

    if not evaluation_rows:
        raise ReplayValidationError("evaluation window contains no samples")
    sample_period_error = max(
        (abs((times[index] - times[index - 1]) - dt_s) for index in range(1, len(times))),
        default=0.0,
    )
    time_grid_error = max(
        (
            abs(time_s - ((index + 1) * dt_s))
            for index, time_s in enumerate(times)
        ),
        default=0.0,
    )
    metrics = {
        "trace_step_count": len(trace),
        "evaluation_step_count": len(evaluation_rows),
        "sample_period_error_max_s": sample_period_error,
        "time_grid_error_max_s": time_grid_error,
        "raw_jacobian_closure_all_steps_relative_max": (
            raw_jacobian_closure_all_steps_relative_max
        ),
        "contact_generalized_force_component_relative_max": max(row[0] for row in evaluation_rows),
        "base_force_residual_relative_max": max(row[1] for row in evaluation_rows),
        "base_moment_residual_relative_max": max(row[2] for row in evaluation_rows),
        "joint_torque_residual_relative_max": max(row[3] for row in evaluation_rows),
        "minimum_contact_normal_force_n": min(row[4] for row in evaluation_rows),
        "maximum_friction_utilization": max(row[5] for row in evaluation_rows),
        "minimum_cop_support_margin_m": min(row[6] for row in evaluation_rows),
        "minimum_loaded_foot_count": min(row[7] for row in evaluation_rows),
    }
    primary_metrics = bundle.get("metrics")
    if not isinstance(primary_metrics, dict):
        raise ReplayValidationError("bundle.metrics missing")
    comparison_keys = [
        "contact_generalized_force_component_relative_max",
        "base_force_residual_relative_max",
        "base_moment_residual_relative_max",
        "joint_torque_residual_relative_max",
        "minimum_contact_normal_force_n",
        "maximum_friction_utilization",
        "minimum_cop_support_margin_m",
        "minimum_loaded_foot_count",
    ]
    primary_metric_delta_max = max(
        abs(metrics[key] - _number(primary_metrics.get(key), f"metrics.{key}"))
        for key in comparison_keys
    )
    metrics["primary_metric_delta_max"] = primary_metric_delta_max

    criteria = [
        _criterion("TRACE_STEP_COUNT", metrics["trace_step_count"], "==", expected_step_count, "count"),
        _criterion("TRACE_SAMPLE_PERIOD", sample_period_error, "<=", 1.0e-12, "s"),
        _criterion("TRACE_TIME_GRID", time_grid_error, "<=", 1.0e-12, "s"),
        _criterion(
            "EVALUATION_STEP_COUNT",
            metrics["evaluation_step_count"],
            "==",
            expected_evaluation_step_count,
            "count",
        ),
        _criterion(
            "RAW_JACOBIAN_CLOSURE_ALL_STEPS",
            metrics["raw_jacobian_closure_all_steps_relative_max"],
            "<=",
            _number(
                tolerances.get("contact_generalized_force_component_relative_max"),
                "tolerances.contact_generalized_force_component_relative_max",
            ),
            "normalized max component",
        ),
        _criterion(
            "CONTACT_GENERALIZED_FORCE_CLOSURE",
            metrics["contact_generalized_force_component_relative_max"],
            "<=",
            _number(
                tolerances.get("contact_generalized_force_component_relative_max"),
                "tolerances.contact_generalized_force_component_relative_max",
            ),
            "normalized max component",
        ),
        _criterion(
            "BASE_FORCE_CLOSURE",
            metrics["base_force_residual_relative_max"],
            "<=",
            _number(
                tolerances.get("base_force_residual_relative_max"),
                "tolerances.base_force_residual_relative_max",
            ),
            "normalized force norm",
        ),
        _criterion(
            "BASE_MOMENT_CLOSURE",
            metrics["base_moment_residual_relative_max"],
            "<=",
            _number(
                tolerances.get("base_moment_residual_relative_max"),
                "tolerances.base_moment_residual_relative_max",
            ),
            "normalized moment norm",
        ),
        _criterion(
            "JOINT_TORQUE_CLOSURE",
            metrics["joint_torque_residual_relative_max"],
            "<=",
            _number(
                tolerances.get("joint_torque_residual_relative_max"),
                "tolerances.joint_torque_residual_relative_max",
            ),
            "normalized torque norm",
        ),
        _criterion(
            "UNILATERAL_NORMAL_FORCE",
            metrics["minimum_contact_normal_force_n"],
            ">=",
            _number(
                tolerances.get("minimum_contact_normal_force_n"),
                "tolerances.minimum_contact_normal_force_n",
            ),
            "N",
        ),
        _criterion(
            "FRICTION_CONE_FEASIBILITY",
            metrics["maximum_friction_utilization"],
            "<=",
            _number(
                tolerances.get("maximum_friction_utilization"),
                "tolerances.maximum_friction_utilization",
            ),
            "utilization ratio",
        ),
        _criterion(
            "COP_SUPPORT_MARGIN",
            metrics["minimum_cop_support_margin_m"],
            ">=",
            _number(
                tolerances.get("minimum_cop_support_margin_m"),
                "tolerances.minimum_cop_support_margin_m",
            ),
            "m",
        ),
        _criterion(
            "BILATERAL_COP_AVAILABLE",
            metrics["minimum_loaded_foot_count"],
            ">=",
            _number(
                tolerances.get("minimum_loaded_foot_count"),
                "tolerances.minimum_loaded_foot_count",
            ),
            "foot count",
        ),
        _criterion(
            "PRIMARY_REPLAY_METRIC_MATCH",
            primary_metric_delta_max,
            "<=",
            1.0e-12,
            "max absolute delta",
        ),
    ]
    return {
        "schema_version": "V1_RAW_JACOBIAN_REPLAY_RECEIPT_V2",
        "source_schema_version": bundle["schema_version"],
        "source_artifact_sha256": artifact_sha256,
        "evidence_scope": "PROCESS_INDEPENDENT_RAW_JACOBIAN_REPLAY_ONLY",
        "claim_boundary": (
            "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED. Runs without MuJoCo or "
            "controller imports and reconstructs per-contact "
            "generalized forces from serialized relative Jacobians, contact frames and "
            "6-D wrenches before recomputing friction and CoP. Jacobians and wrenches "
            "remain receipts from the same MuJoCo engine; this is not independent "
            "contact-model, plant, hardware, or V1 validation."
        ),
        "replayed_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(item["passed"] for item in criteria) else "FAIL",
        "metrics": metrics,
        "criteria": criteria,
    }


def _reject_nonstandard_json(value: str) -> None:
    raise ReplayValidationError(f"non-standard JSON constant is forbidden: {value}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a V1 raw contact evidence bundle")
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    payload = args.artifact.read_bytes()
    bundle = json.loads(
        payload.decode("utf-8"),
        parse_constant=_reject_nonstandard_json,
    )
    receipt = replay_static_double_support_bundle(
        bundle,
        artifact_sha256=f"sha256:{hashlib.sha256(payload).hexdigest()}",
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
