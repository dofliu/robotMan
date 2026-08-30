"""Process-independent replay for the bounded V1 raw contact evidence bundle.

This module intentionally imports neither MuJoCo nor the live controller. It
recomputes the receipt-level contact closure, friction utilization and foot CoP
from the serialized raw quantities only.
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


def _transpose_multiply(matrix: list[list[float]], vector: list[float]) -> list[float]:
    return [
        sum(matrix[row][column] * vector[row] for row in range(3))
        for column in range(3)
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


def _friction_utilization(contact: dict, cone_name: str, prefix: str) -> float:
    dimension = int(_number(contact.get("dimension"), f"{prefix}.dimension"))
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


def _foot_support_metrics(step: dict, support_names: list[str], prefix: str) -> tuple[list[float], int]:
    support_receipts = step.get("foot_support")
    contacts = step.get("contacts")
    if not isinstance(support_receipts, dict) or not isinstance(contacts, list):
        raise ReplayValidationError(f"{prefix} lacks foot_support or contacts")

    margins: list[float] = []
    loaded_count = 0
    for support_name in support_names:
        support = support_receipts.get(support_name)
        if not isinstance(support, dict):
            raise ReplayValidationError(f"{prefix}.foot_support.{support_name} missing")
        geom_id = int(_number(
            support.get("geom_id"),
            f"{prefix}.foot_support.{support_name}.geom_id",
        ))
        size = _vector(
            support.get("geom_size_m"),
            3,
            f"{prefix}.foot_support.{support_name}.geom_size_m",
        )
        origin = _vector(
            support.get("origin_world_m"),
            3,
            f"{prefix}.foot_support.{support_name}.origin_world_m",
        )
        rotation = _matrix3(
            support.get("rotation_world"),
            f"{prefix}.foot_support.{support_name}.rotation_world",
        )
        total_force_world = [0.0, 0.0, 0.0]
        total_moment_world = [0.0, 0.0, 0.0]
        contact_count = 0
        for contact_index, contact in enumerate(contacts):
            if not isinstance(contact, dict):
                raise ReplayValidationError(f"{prefix}.contacts[{contact_index}] invalid")
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
        if contact_count == 0 or normal_load <= 1.0e-12:
            continue
        loaded_count += 1
        sole_z = -size[2]
        cop_x = (sole_z * total_force_local[0] - total_moment_local[1]) / normal_load
        cop_y = (total_moment_local[0] + sole_z * total_force_local[1]) / normal_load
        margins.append(min(size[0] - abs(cop_x), size[1] - abs(cop_y)))
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
    if bundle.get("schema_version") != "V1_STATIC_DOUBLE_SUPPORT_ORACLE_V3":
        raise ReplayValidationError("unsupported source schema_version")
    contract = bundle.get("contract")
    model = bundle.get("resolved_model")
    trace = bundle.get("raw_trace")
    if not isinstance(contract, dict) or not isinstance(model, dict) or not isinstance(trace, list):
        raise ReplayValidationError("bundle lacks contract, resolved_model, or raw_trace")

    duration_s = _number(contract.get("duration_s"), "contract.duration_s")
    window_s = _number(contract.get("evaluation_window_s"), "contract.evaluation_window_s")
    dt_s = _number(contract.get("physics_dt_s"), "contract.physics_dt_s")
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

    cone_name = model.get("friction_cone")
    if cone_name != contract.get("expected_friction_cone"):
        raise ReplayValidationError("resolved friction cone does not match contract")
    mass_kg = _number(model.get("mass_kg"), "resolved_model.mass_kg")
    gravity = _vector(model.get("gravity_mps2"), 3, "resolved_model.gravity_mps2")
    model_weight_n = mass_kg * abs(gravity[2])
    moment_scale_nm = model_weight_n * characteristic_length
    expected_step_count = round(duration_s / dt_s)
    times: list[float] = []
    evaluation_rows: list[tuple[float, float, float, float, float, float, float, int]] = []
    evaluation_start = duration_s - window_s

    for step_index, step in enumerate(trace):
        if not isinstance(step, dict):
            raise ReplayValidationError(f"raw_trace[{step_index}] invalid")
        prefix = f"raw_trace[{step_index}]"
        time_s = _number(step.get("time_s"), f"{prefix}.time_s")
        times.append(time_s)
        if time_s <= evaluation_start + 1.0e-12:
            continue

        qfrc_constraint_value = step.get("qfrc_constraint")
        contacts = step.get("contacts")
        if not isinstance(qfrc_constraint_value, list) or not isinstance(contacts, list):
            raise ReplayValidationError(f"{prefix} lacks qfrc_constraint or contacts")
        nv = len(qfrc_constraint_value)
        if nv <= 6:
            raise ReplayValidationError(f"{prefix}.qfrc_constraint has invalid length")
        qfrc_constraint = _vector(qfrc_constraint_value, nv, f"{prefix}.qfrc_constraint")
        reconstructed = [0.0] * nv
        normal_forces: list[float] = []
        friction_utilizations: list[float] = []
        for contact_index, contact in enumerate(contacts):
            if not isinstance(contact, dict):
                raise ReplayValidationError(f"{prefix}.contacts[{contact_index}] invalid")
            contact_prefix = f"{prefix}.contacts[{contact_index}]"
            generalized = _vector(
                contact.get("generalized_force"),
                nv,
                f"{contact_prefix}.generalized_force",
            )
            reconstructed = _add(reconstructed, generalized)
            wrench = _vector(
                contact.get("wrench_local_force_torque"),
                6,
                f"{contact_prefix}.wrench_local_force_torque",
            )
            normal_forces.append(wrench[0])
            friction_utilizations.append(
                _friction_utilization(contact, str(cone_name), contact_prefix)
            )

        residual = _subtract(qfrc_constraint, reconstructed)
        normalized_components = [
            *(item / max(model_weight_n, 1.0e-12) for item in residual[0:3]),
            *(item / max(moment_scale_nm, 1.0e-12) for item in residual[3:]),
        ]
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
    metrics = {
        "trace_step_count": len(trace),
        "evaluation_step_count": len(evaluation_rows),
        "sample_period_error_max_s": sample_period_error,
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
        "schema_version": "V1_RAW_REPLAY_RECEIPT_V1",
        "source_schema_version": bundle["schema_version"],
        "source_artifact_sha256": artifact_sha256,
        "evidence_scope": "PROCESS_INDEPENDENT_RAW_RECEIPT_REPLAY_PARTIAL",
        "claim_boundary": (
            "Runs without MuJoCo or controller imports and independently recomputes raw "
            "receipt aggregation, friction and CoP. Per-contact generalized forces remain "
            "source-engine receipts because raw Jacobian matrices are not yet serialized; "
            "this is not contact-model, plant, hardware, or V1 validation."
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
        artifact_sha256=hashlib.sha256(payload).hexdigest(),
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
