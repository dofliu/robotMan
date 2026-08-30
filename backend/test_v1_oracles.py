"""V1 oracle contract and claim-boundary regressions."""

from vv_oracles import run_static_double_support_oracle


def test_static_double_support_internal_oracle_passes_frozen_reference_case():
    result = run_static_double_support_oracle(include_raw_trace=True)

    assert result["schema_version"] == "V1_STATIC_DOUBLE_SUPPORT_ORACLE_V2"
    assert result["evidence_scope"] == (
        "MUJOCO_INTERNAL_NUMERICAL_AND_WRENCH_RECONSTRUCTION_ONLY"
    )
    assert result["status"] == "PASS"
    assert len(result["criteria"]) == 13
    assert all(item["passed"] for item in result["criteria"])
    assert result["metrics"]["model_mass_kg"] > 0.0
    assert result["metrics"]["bilateral_contact_duty"] >= 0.99
    assert result["metrics"]["contact_generalized_force_component_relative_max"] <= 1e-9
    assert result["metrics"]["minimum_contact_normal_force_n"] >= -1e-8
    assert result["metrics"]["physics_step_count"] == 1000
    assert len(result["raw_trace"]) == 1000
    assert result["raw_trace"][-1]["contact_count"] > 0
    assert len(result["raw_trace"][-1]["qfrc_contact_reconstructed"]) > 6
    assert "V1 gate pass" in result["claim_boundary"]
