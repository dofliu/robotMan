"""V1 oracle contract, replay, and claim-boundary regressions."""

from copy import deepcopy

import pytest

from v1_replay import ReplayValidationError, replay_static_double_support_bundle
from vv_oracles import run_static_double_support_oracle


@pytest.fixture(scope="module")
def static_bundle() -> dict:
    return run_static_double_support_oracle(include_raw_trace=True)


def test_static_double_support_internal_oracle_passes_frozen_reference_case(static_bundle):
    result = static_bundle

    assert result["schema_version"] == "V1_STATIC_DOUBLE_SUPPORT_ORACLE_V3"
    assert result["evidence_scope"] == (
        "MUJOCO_INTERNAL_WRENCH_FRICTION_COP_RECONSTRUCTION_ONLY"
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
    assert "V1 gate pass" in result["claim_boundary"]


def test_process_independent_replay_matches_primary_metrics(static_bundle):
    replay = replay_static_double_support_bundle(static_bundle)

    assert replay["schema_version"] == "V1_RAW_REPLAY_RECEIPT_V1"
    assert replay["status"] == "PASS"
    assert len(replay["criteria"]) == 11
    assert all(item["passed"] for item in replay["criteria"])
    assert replay["metrics"]["trace_step_count"] == 1000
    assert replay["metrics"]["evaluation_step_count"] == 250
    assert replay["metrics"]["primary_metric_delta_max"] <= 1e-12
    assert "raw Jacobian matrices are not yet serialized" in replay["claim_boundary"]


def test_replay_retains_friction_violation_as_fail(static_bundle):
    tampered = deepcopy(static_bundle)
    tampered["raw_trace"][-1]["contacts"][0]["wrench_local_force_torque"][1] = 1.0e6

    replay = replay_static_double_support_bundle(tampered)

    assert replay["status"] == "FAIL"
    friction = next(
        item for item in replay["criteria"] if item["id"] == "FRICTION_CONE_FEASIBILITY"
    )
    assert friction["passed"] is False


def test_replay_retains_generalized_force_closure_violation_as_fail(static_bundle):
    tampered = deepcopy(static_bundle)
    tampered["raw_trace"][-1]["contacts"][0]["generalized_force"][0] += 1.0e3

    replay = replay_static_double_support_bundle(tampered)

    assert replay["status"] == "FAIL"
    closure = next(
        item
        for item in replay["criteria"]
        if item["id"] == "CONTACT_GENERALIZED_FORCE_CLOSURE"
    )
    assert closure["passed"] is False


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
    tampered["raw_trace"][0]["qpos"][0] = float("nan")

    with pytest.raises(ReplayValidationError, match="must be finite"):
        replay_static_double_support_bundle(tampered)
