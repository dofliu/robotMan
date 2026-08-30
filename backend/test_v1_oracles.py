"""V1 oracle contract and claim-boundary regressions."""

from vv_oracles import run_static_double_support_oracle


def test_static_double_support_internal_oracle_passes_frozen_reference_case():
    result = run_static_double_support_oracle()

    assert result["schema_version"] == "V1_STATIC_DOUBLE_SUPPORT_ORACLE_V1"
    assert result["evidence_scope"] == "MUJOCO_INTERNAL_NUMERICAL_AND_REFERENCE_CASE_ONLY"
    assert result["status"] == "PASS"
    assert len(result["criteria"]) == 8
    assert all(item["passed"] for item in result["criteria"])
    assert result["metrics"]["model_mass_kg"] > 0.0
    assert result["metrics"]["bilateral_contact_duty"] >= 0.99
    assert "V1 gate pass" in result["claim_boundary"]
