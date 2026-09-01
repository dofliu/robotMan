"""Fail-closed regressions for the stdlib-only V1 analytical replay."""

import ast
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from v1_analytical_replay import (
    AnalyticalReplayValidationError,
    replay_analytical_suite,
)
from v1_analytical_suite import (
    ANALYTICAL_SUITE_CONTRACT,
    AnalyticalSuiteValidationError,
    CLAIM_BOUNDARY,
    PRIMARY_SCHEMA_VERSION,
    _evaluate_suite,
    build_analytical_model_package,
    validate_analytical_model_package,
    validate_primary_result,
)


def _compiled_model(record: dict) -> dict:
    config = record["config"]
    return {
        "model_xml_sha256": record["model_xml_sha256"],
        "config_sha256": record["config_sha256"],
        "compiled_timestep_s": config["physics_dt_s"],
        "compiled_mass_kg": config["base_mass_kg"] + config["payload_kg"],
        "gravity_mps2": [0.0, 0.0, -config["gravity_mps2"]],
        "integrator": config["integrator"],
        "solver": config["solver"],
        "solver_iterations": config["solver_iterations"],
        "solver_tolerance": config["solver_tolerance"],
        "friction_cone": "PYRAMIDAL",
        "nv": 6,
        "nq": 7,
        "nu": 0,
        "nbody": 2,
        "support_geom_id": 1,
        "support_geom_name": "support_foot",
        "floor_geom_id": 0,
        "floor_geom_name": "floor",
        "support_half_size_m": [0.12, 0.06, 0.025],
    }


def _contact(weight_n: float) -> dict:
    # Contact frame 的第一軸是 +world-Z，因此 local normal 會成為 vertical GRF。
    frame = [
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
    ]
    jacobian_translation = [
        [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
    ]
    return {
        "contact_index": 0,
        "dimension": 3,
        "exclude": 0,
        "efc_address": 0,
        "active": True,
        "geom1_id": 0,
        "geom1_name": "floor",
        "geom2_id": 1,
        "geom2_name": "support_foot",
        "body1_id": 0,
        "body1_name": "world",
        "body2_id": 1,
        "body2_name": "fixture_body",
        "position_world_m": [0.0, 0.0, 0.0],
        "contact_frame_world": frame,
        "wrench_local_force_torque": [weight_n, 0.0, 0.0, 0.0, 0.0, 0.0],
        "force_world_n": [0.0, 0.0, weight_n],
        "torque_world_nm": [0.0, 0.0, 0.0],
        "normal_force_n": weight_n,
        "adhesion_n": 0.0,
        "friction_cone": "PYRAMIDAL",
        "friction_parameters": [1.0, 1.0, 0.005, 0.0001, 0.0001],
        "friction_utilization": 0.0,
        "jacobian_translation_relative_world": jacobian_translation,
        "jacobian_rotation_relative_world": [[0.0] * 6 for _ in range(3)],
    }


def _case(record: dict) -> dict:
    config = deepcopy(record["config"])
    compiled = _compiled_model(record)
    dt = float(config["physics_dt_s"])
    count = round(float(config["duration_s"]) / dt)
    weight_n = float(compiled["compiled_mass_kg"] * config["gravity_mps2"])
    qfrc = [0.0, 0.0, weight_n, 0.0, 0.0, 0.0]
    contact = _contact(weight_n)
    trace = []
    for index in range(count):
        trace.append({
            "time_s": (index + 1) * dt,
            "qpos": [0.0, 0.0, 0.25, 1.0, 0.0, 0.0, 0.0],
            "qvel": [0.0] * 6,
            "qacc": [0.0] * 6,
            "qfrc_constraint": list(qfrc),
            "qfrc_contact_reconstructed": list(qfrc),
            "qfrc_applied": [0.0] * 6,
            "xfrc_applied": [[0.0] * 6 for _ in range(2)],
            "solver_fwdinv": [0.0, 0.0],
            "contact_count": 1,
            "contacts": [deepcopy(contact)],
            "support_origin_world_m": [0.0, 0.0, 0.025],
            "support_rotation_world": [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
            ],
        })
    return {
        "case_id": config["case_id"],
        "config": config,
        "compiled_model": compiled,
        "raw_trace": trace,
    }


def _synthetic_primary_and_package() -> tuple[dict, dict]:
    package = build_analytical_model_package()
    cases = [_case(record) for record in package["models"]]
    case_receipts, metrics, criteria = _evaluate_suite(cases, package)
    primary = {
        "schema_version": PRIMARY_SCHEMA_VERSION,
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "claim_boundary": CLAIM_BOUNDARY,
        "contract": deepcopy(ANALYTICAL_SUITE_CONTRACT),
        "model_package_content_sha256": package["content_sha256"],
        "completed_at": "2026-09-02T00:00:00+00:00",
        "status": "PASS" if all(item["passed"] for item in criteria) else "FAIL",
        "cases": cases,
        "case_receipts": case_receipts,
        "metrics": metrics,
        "criteria": criteria,
    }
    return primary, package


@pytest.fixture(scope="module")
def valid_bundle() -> tuple[dict, dict]:
    return _synthetic_primary_and_package()


def _criterion(receipt: dict, criterion_id: str) -> dict:
    return next(item for item in receipt["criteria"] if item["id"] == criterion_id)


def _case_criterion(receipt: dict, case_id: str, criterion_id: str) -> dict:
    case = next(item for item in receipt["case_receipts"] if item["case_id"] == case_id)
    return next(item for item in case["criteria"] if item["id"] == criterion_id)


def test_stdlib_replay_passes_exact_synthetic_fixture(valid_bundle):
    primary, package = valid_bundle

    replay = replay_analytical_suite(primary, package)

    assert replay["schema_version"] == "V1_ANALYTICAL_REPLAY_RECEIPT_V1"
    assert replay["status"] == "PASS"
    assert replay["metrics"]["case_count"] == 4
    assert replay["metrics"]["case_pass_count"] == 4
    assert replay["metrics"]["payload_mass_delta_error_kg"] == 0.0
    assert replay["metrics"]["payload_grf_delta_relative_error"] <= 1.0e-12
    assert replay["metrics"]["timestep_qoi_4ms"] == pytest.approx(1.0)
    assert replay["metrics"]["timestep_qoi_2ms"] == pytest.approx(1.0)
    assert replay["metrics"]["timestep_qoi_1ms"] == pytest.approx(1.0)
    assert replay["metrics"]["timestep_order_status"] == "ROUND_OFF_LIMITED"
    assert replay["metrics"]["timestep_observed_order"] is None
    assert replay["metrics"]["raw_serialized_receipt_delta_max"] == 0.0
    assert all(item["passed"] for item in replay["criteria"])


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra"])
def test_replay_rejects_missing_duplicate_or_extra_case(valid_bundle, mutation):
    primary, package = deepcopy(valid_bundle)
    if mutation == "missing":
        primary["cases"].pop()
    elif mutation == "duplicate":
        primary["cases"][1] = deepcopy(primary["cases"][0])
    else:
        primary["cases"].append(deepcopy(primary["cases"][-1]))

    with pytest.raises(AnalyticalReplayValidationError, match="case inventory"):
        replay_analytical_suite(primary, package)


def test_replay_rejects_exact_case_dt_mismatch(valid_bundle):
    primary, package = deepcopy(valid_bundle)
    primary["cases"][0]["config"]["physics_dt_s"] = 0.003

    with pytest.raises(AnalyticalReplayValidationError, match="case/config identity"):
        replay_analytical_suite(primary, package)


def test_replay_retains_compiled_dt_mismatch_as_fail(valid_bundle):
    primary, package = deepcopy(valid_bundle)
    primary["cases"][0]["compiled_model"]["compiled_timestep_s"] = 0.003

    replay = replay_analytical_suite(primary, package)

    assert replay["status"] == "FAIL"
    assert _case_criterion(
        replay,
        "single_support_nominal_dt_4ms",
        "COMPILED_TIMESTEP_IDENTITY",
    )["passed"] is False


def test_replay_retains_wrong_support_as_fail(valid_bundle):
    primary, package = deepcopy(valid_bundle)
    contact = primary["cases"][1]["raw_trace"][-1]["contacts"][0]
    contact["geom2_id"] = 99
    contact["geom2_name"] = "wrong_support"

    replay = replay_analytical_suite(primary, package)

    assert replay["status"] == "FAIL"
    assert _case_criterion(
        replay,
        "single_support_nominal_dt_2ms",
        "EXACT_SINGLE_SUPPORT",
    )["passed"] is False
    assert _case_criterion(
        replay,
        "single_support_nominal_dt_2ms",
        "UNEXPECTED_CONTACT_ABSENT",
    )["passed"] is False


def test_replay_retains_hidden_applied_force_as_fail(valid_bundle):
    primary, package = deepcopy(valid_bundle)
    primary["cases"][1]["raw_trace"][0]["qfrc_applied"][0] = 1.0

    replay = replay_analytical_suite(primary, package)

    assert replay["status"] == "FAIL"
    assert _case_criterion(
        replay,
        "single_support_nominal_dt_2ms",
        "EXTERNAL_FORCE_ABSENT",
    )["passed"] is False


def test_replay_recomputes_payload_mass_delta(valid_bundle):
    primary, package = deepcopy(valid_bundle)
    primary["cases"][3]["compiled_model"]["compiled_mass_kg"] = 24.0

    replay = replay_analytical_suite(primary, package)

    assert replay["status"] == "FAIL"
    assert replay["metrics"]["payload_mass_delta_error_kg"] == 1.0
    assert _criterion(replay, "PAYLOAD_MASS_DELTA")["passed"] is False


def test_replay_rejects_nonfinite_raw_value(valid_bundle):
    primary, package = deepcopy(valid_bundle)
    primary["cases"][0]["raw_trace"][0]["contacts"][0][
        "jacobian_translation_relative_world"
    ][0][0] = float("nan")

    with pytest.raises(AnalyticalReplayValidationError, match="must be finite"):
        replay_analytical_suite(primary, package)


def test_replay_does_not_trust_forged_primary_pass(valid_bundle):
    primary, package = deepcopy(valid_bundle)
    # Primary summary/status保持 PASS，只破壞 raw generalized-force closure。
    primary["cases"][1]["raw_trace"][-1]["qfrc_constraint"][2] += 100.0

    replay = replay_analytical_suite(primary, package)

    assert primary["status"] == "PASS"
    assert replay["status"] == "FAIL"
    assert _case_criterion(
        replay,
        "single_support_nominal_dt_2ms",
        "RAW_JACOBIAN_CLOSURE",
    )["passed"] is False
    assert _criterion(replay, "PRIMARY_CASE_RECEIPT_IDENTITY")["passed"] is False


def test_replay_rejects_model_package_hash_tamper(valid_bundle):
    primary, package = deepcopy(valid_bundle)
    package["models"][0]["model_xml_sha256"] = "sha256:" + "0" * 64

    with pytest.raises(AnalyticalReplayValidationError, match="content SHA-256 mismatch"):
        replay_analytical_suite(primary, package)


def test_replay_rejects_rehashed_nonfrozen_model_xml(valid_bundle):
    primary, package = deepcopy(valid_bundle)
    package["models"][0]["model_xml"] += "<!-- tampered -->"
    model = package["models"][0]
    model["model_xml_bytes"] = len(model["model_xml"].encode("utf-8"))
    model["model_xml_sha256"] = (
        "sha256:" + hashlib.sha256(model["model_xml"].encode("utf-8")).hexdigest()
    )
    unsigned = {key: value for key, value in package.items() if key != "content_sha256"}
    from v1_analytical_replay import canonical_json_sha256

    package["content_sha256"] = canonical_json_sha256(unsigned)
    primary["model_package_content_sha256"] = package["content_sha256"]

    with pytest.raises(AnalyticalSuiteValidationError, match="frozen fixture"):
        validate_analytical_model_package(package)
    with pytest.raises(AnalyticalReplayValidationError, match="frozen model"):
        replay_analytical_suite(primary, package)


def test_replay_rejects_model_inventory_drift(valid_bundle):
    primary, package = deepcopy(valid_bundle)
    package["case_ids"][1] = package["case_ids"][0]

    with pytest.raises(AnalyticalReplayValidationError, match="model package case inventory"):
        replay_analytical_suite(primary, package)


def test_primary_and_replay_reject_case_to_package_hash_drift(valid_bundle):
    primary, package = deepcopy(valid_bundle)
    primary["cases"][0]["compiled_model"]["model_xml_sha256"] = "sha256:" + "1" * 64

    with pytest.raises(AnalyticalSuiteValidationError, match="case-to-model package"):
        validate_primary_result(primary, package)
    with pytest.raises(AnalyticalReplayValidationError, match="compiled model SHA-256"):
        replay_analytical_suite(primary, package)


def test_primary_and_replay_reject_zeroed_raw_jacobian(valid_bundle):
    primary, package = deepcopy(valid_bundle)
    contact = primary["cases"][1]["raw_trace"][-1]["contacts"][0]
    contact["jacobian_translation_relative_world"] = [[0.0] * 6 for _ in range(3)]

    with pytest.raises(AnalyticalSuiteValidationError, match="summary does not match"):
        validate_primary_result(primary, package)
    replay = replay_analytical_suite(primary, package)
    assert replay["status"] == "FAIL"
    assert _case_criterion(
        replay,
        "single_support_nominal_dt_2ms",
        "RAW_JACOBIAN_CLOSURE",
    )["passed"] is False


@pytest.mark.parametrize("mutation", ["qpos_shape", "contact_count"])
def test_primary_and_replay_reject_raw_shape_or_count(valid_bundle, mutation):
    primary, package = deepcopy(valid_bundle)
    row = primary["cases"][0]["raw_trace"][0]
    if mutation == "qpos_shape":
        row["qpos"].pop()
        primary_match = "qpos shape mismatch"
        replay_match = "qpos must contain exactly 7"
    else:
        row["contact_count"] = 2
        primary_match = "contact count mismatch"
        replay_match = "contact_count mismatch"

    with pytest.raises(AnalyticalSuiteValidationError, match=primary_match):
        validate_primary_result(primary, package)
    with pytest.raises(AnalyticalReplayValidationError, match=replay_match):
        replay_analytical_suite(primary, package)


def test_replay_reconstructs_raw_jacobian_instead_of_trusting_aggregate(valid_bundle):
    primary, package = deepcopy(valid_bundle)
    primary["cases"][1]["raw_trace"][-1]["qfrc_contact_reconstructed"][2] += 1.0

    replay = replay_analytical_suite(primary, package)

    assert replay["status"] == "FAIL"
    assert _case_criterion(
        replay,
        "single_support_nominal_dt_2ms",
        "RAW_JACOBIAN_CLOSURE",
    )["passed"] is False
    assert _criterion(replay, "RAW_SERIALIZED_RECEIPT_IDENTITY")["passed"] is False


def test_analytical_replay_source_has_only_stdlib_dependencies():
    source_path = Path(__file__).with_name("v1_analytical_replay.py")
    source = source_path.read_text(encoding="utf-8")
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
    forbidden = {"mujoco", "numpy", "controller", "v1_analytical_suite", "vv_oracles"}
    assert imported_roots.isdisjoint(forbidden)
