"""V1 oracle contract, replay, and claim-boundary regressions."""

import ast
from copy import deepcopy
from pathlib import Path

import pytest

from v1_replay import ReplayValidationError, replay_static_double_support_bundle
from vv_oracles import run_static_double_support_oracle


@pytest.fixture(scope="module")
def static_bundle() -> dict:
    return run_static_double_support_oracle(include_raw_trace=True)


def _pre_window_contact(bundle: dict) -> dict:
    evaluation_start = (
        bundle["contract"]["duration_s"]
        - bundle["contract"]["evaluation_window_s"]
    )
    return next(
        step["contacts"][0]
        for step in bundle["raw_trace"]
        if step["time_s"] <= evaluation_start and step["contacts"]
    )


def test_static_double_support_internal_oracle_passes_frozen_reference_case(static_bundle):
    result = static_bundle

    assert result["contract"] == {
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
    assert result["schema_version"] == "V1_STATIC_DOUBLE_SUPPORT_ORACLE_V4"
    assert result["evidence_scope"] == (
        "MUJOCO_INTERNAL_RAW_JACOBIAN_WRENCH_RECONSTRUCTION_ONLY"
    )
    assert result["status"] == "PASS"
    assert len(result["criteria"]) == 16
    assert all(item["passed"] for item in result["criteria"])
    assert result["metrics"]["model_mass_kg"] > 0.0
    assert result["metrics"]["bilateral_contact_duty"] >= 0.99
    assert result["metrics"]["contact_generalized_force_component_relative_max"] <= 1e-9
    assert result["metrics"]["minimum_contact_normal_force_n"] >= -1e-8
    assert result["metrics"]["maximum_friction_utilization"] <= 1.0 + 1e-9
    assert result["metrics"]["minimum_cop_support_margin_m"] >= -1e-9
    assert result["metrics"]["minimum_loaded_foot_count"] == 2
    assert result["metrics"]["physics_step_count"] == 1000
    assert len(result["raw_trace"]) == 1000
    assert result["raw_trace"][-1]["contact_count"] > 0
    assert len(result["raw_trace"][-1]["qfrc_contact_reconstructed"]) > 6
    nv = result["resolved_model"]["nv"]
    contact = result["raw_trace"][-1]["contacts"][0]
    assert contact["dimension"] == 3
    assert contact["exclude"] == 0
    assert contact["efc_address"] >= 0
    assert contact["active"] is True
    assert contact["adhesion_n"] == 0.0
    assert result["resolved_model"]["model_xml_sha256"].startswith("sha256:")
    assert len(contact["jacobian_translation_relative_world"]) == 3
    assert all(
        len(row) == nv for row in contact["jacobian_translation_relative_world"]
    )
    assert len(contact["jacobian_rotation_relative_world"]) == 3
    assert all(
        len(row) == nv for row in contact["jacobian_rotation_relative_world"]
    )
    assert "generalized_force" not in contact
    assert "V1 gate pass" in result["claim_boundary"]


def test_process_independent_replay_matches_primary_metrics(static_bundle):
    replay = replay_static_double_support_bundle(static_bundle)

    assert replay["schema_version"] == "V1_RAW_JACOBIAN_REPLAY_RECEIPT_V2"
    assert replay["status"] == "PASS"
    assert len(replay["criteria"]) == 14
    assert all(item["passed"] for item in replay["criteria"])
    assert replay["metrics"]["trace_step_count"] == 1000
    assert replay["metrics"]["evaluation_step_count"] == 250
    assert replay["metrics"]["time_grid_error_max_s"] <= 1e-12
    assert replay["metrics"]["raw_jacobian_closure_all_steps_relative_max"] <= 1e-9
    assert replay["metrics"]["primary_metric_delta_max"] <= 1e-12
    assert "serialized relative Jacobians" in replay["claim_boundary"]
    assert "same MuJoCo engine" in replay["claim_boundary"]


def test_replay_retains_friction_violation_as_fail(static_bundle):
    tampered = deepcopy(static_bundle)
    tampered["raw_trace"][-1]["contacts"][0]["wrench_local_force_torque"][1] = 1.0e6

    replay = replay_static_double_support_bundle(tampered)

    assert replay["status"] == "FAIL"
    friction = next(
        item for item in replay["criteria"] if item["id"] == "FRICTION_CONE_FEASIBILITY"
    )
    assert friction["passed"] is False


def test_replay_retains_jacobian_closure_violation_as_fail(static_bundle):
    tampered = deepcopy(static_bundle)
    tampered["raw_trace"][-1]["contacts"][0][
        "jacobian_translation_relative_world"
    ][0][0] += 1.0e3

    replay = replay_static_double_support_bundle(tampered)

    assert replay["status"] == "FAIL"
    closure = next(
        item
        for item in replay["criteria"]
        if item["id"] == "CONTACT_GENERALIZED_FORCE_CLOSURE"
    )
    assert closure["passed"] is False


def test_replay_retains_pre_window_jacobian_closure_violation_as_fail(static_bundle):
    tampered = deepcopy(static_bundle)
    _pre_window_contact(tampered)["jacobian_translation_relative_world"][0][0] += 1.0e3

    replay = replay_static_double_support_bundle(tampered)

    assert replay["status"] == "FAIL"
    closure = next(
        item
        for item in replay["criteria"]
        if item["id"] == "RAW_JACOBIAN_CLOSURE_ALL_STEPS"
    )
    assert closure["passed"] is False
    assert replay["metrics"]["primary_metric_delta_max"] == 0.0


def test_replay_retains_cop_support_violation_as_fail(static_bundle):
    tampered = deepcopy(static_bundle)
    tampered["raw_trace"][-1]["foot_support"]["foot_l"]["origin_world_m"][0] += 1.0

    replay = replay_static_double_support_bundle(tampered)

    assert replay["status"] == "FAIL"
    cop = next(item for item in replay["criteria"] if item["id"] == "COP_SUPPORT_MARGIN")
    assert cop["passed"] is False


def test_replay_rejects_nonfinite_raw_contact_value(static_bundle):
    tampered = deepcopy(static_bundle)
    # 即使位於 evaluation window 之前，也必須拒絕整份 bundle。
    _pre_window_contact(tampered)["jacobian_rotation_relative_world"][0][0] = float(
        "nan"
    )

    with pytest.raises(ReplayValidationError, match="must be finite"):
        replay_static_double_support_bundle(tampered)


def test_replay_rejects_missing_pre_window_jacobian(static_bundle):
    tampered = deepcopy(static_bundle)
    del _pre_window_contact(tampered)["jacobian_translation_relative_world"]

    with pytest.raises(
        ReplayValidationError,
        match="jacobian_translation_relative_world",
    ):
        replay_static_double_support_bundle(tampered)


@pytest.mark.parametrize("field", ["qpos", "solver_fwdinv"])
def test_replay_rejects_missing_frozen_step_field(static_bundle, field):
    tampered = deepcopy(static_bundle)
    del tampered["raw_trace"][0][field]

    with pytest.raises(ReplayValidationError, match="frozen step fields"):
        replay_static_double_support_bundle(tampered)


def test_replay_rejects_missing_resolved_model_field(static_bundle):
    tampered = deepcopy(static_bundle)
    del tampered["resolved_model"]["solver"]

    with pytest.raises(ReplayValidationError, match="frozen fields"):
        replay_static_double_support_bundle(tampered)


def test_replay_rejects_jacobian_nv_mismatch(static_bundle):
    tampered = deepcopy(static_bundle)
    tampered["raw_trace"][-1]["contacts"][0][
        "jacobian_rotation_relative_world"
    ][0].pop()

    with pytest.raises(ReplayValidationError, match="must contain"):
        replay_static_double_support_bundle(tampered)


def test_replay_rejects_nonzero_contact_adhesion(static_bundle):
    tampered = deepcopy(static_bundle)
    _pre_window_contact(tampered)["adhesion_n"] = 1.0

    with pytest.raises(ReplayValidationError, match="CONTRACT_VIOLATION_ADHESION"):
        replay_static_double_support_bundle(tampered)


def test_replay_rejects_contact_dimension_drift(static_bundle):
    tampered = deepcopy(static_bundle)
    _pre_window_contact(tampered)["dimension"] = 1

    with pytest.raises(
        ReplayValidationError,
        match="CONTRACT_VIOLATION_CONTACT_DIMENSION",
    ):
        replay_static_double_support_bundle(tampered)


def test_replay_rejects_inconsistent_active_contact_receipt(static_bundle):
    tampered = deepcopy(static_bundle)
    _pre_window_contact(tampered)["active"] = False

    with pytest.raises(ReplayValidationError, match="does not match"):
        replay_static_double_support_bundle(tampered)


def test_replay_rejects_inactive_contact_with_nonzero_wrench(static_bundle):
    tampered = deepcopy(static_bundle)
    contact = _pre_window_contact(tampered)
    contact["exclude"] = 1
    contact["efc_address"] = -1
    contact["active"] = False

    with pytest.raises(ReplayValidationError, match="inactive contact must have a zero wrench"):
        replay_static_double_support_bundle(tampered)


def test_replay_retains_constant_time_offset_as_fail(static_bundle):
    tampered = deepcopy(static_bundle)
    for step in tampered["raw_trace"]:
        step["time_s"] += 0.1

    replay = replay_static_double_support_bundle(tampered)

    assert replay["status"] == "FAIL"
    time_grid = next(
        item for item in replay["criteria"] if item["id"] == "TRACE_TIME_GRID"
    )
    evaluation_count = next(
        item
        for item in replay["criteria"]
        if item["id"] == "EVALUATION_STEP_COUNT"
    )
    assert time_grid["passed"] is False
    assert evaluation_count["passed"] is False


def test_replay_source_has_no_mujoco_or_controller_dependency():
    source = Path(__file__).with_name("v1_replay.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".", 1)[0])

    assert imported_roots <= {
        "__future__",
        "argparse",
        "datetime",
        "hashlib",
        "json",
        "math",
        "pathlib",
        "typing",
    }
