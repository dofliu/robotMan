"""V1 dynamic reference suite: frozen contract, primary PASS, stdlib replay, fail-closed negatives."""

import ast
from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

import v1_dynamic_reference_suite as suite
from v1_dynamic_replay import ReplayValidationError, replay_dynamic_suite
import v1_dynamic_replay as replay

HERE = Path(__file__).resolve().parent


@pytest.fixture(scope="module")
def primary() -> dict:
    return suite.run_dynamic_suite()


# ---------------------------------------------------------------- 凍結的契約


def test_contract_matches_the_frozen_specification():
    c = suite.DYNAMIC_SUITE_CONTRACT
    assert c["contract_id"] == "v1_dynamic_reference_suite_v1"
    assert [s["case_id"] for s in c["case_matrix"]] == list(replay.FROZEN_CASE_IDS)
    assert [s["physics_dt_s"] for s in c["case_matrix"]] == [0.004, 0.002, 0.001] * 2
    assert c["tolerances"] == replay.FROZEN_TOLERANCES
    assert c["pendulum"]["duration_s"] == 6.0 and c["articulated"]["duration_s"] == 3.0
    assert [s["energy_fluctuation_relative_max"] for s in c["case_matrix"][:3]] == [0.02, 0.01, 0.005]
    assert [s["energy_residual_relative_max"] for s in c["case_matrix"][3:]] == [0.05, 0.025, 0.0125]
    assert c["articulated"]["analytic_inertia_bodies"] == ["trunk", "foot_l", "foot_r"]


def test_elliptic_integral_matches_known_values_in_both_implementations():
    for impl in (suite.complete_elliptic_integral_first_kind, replay.complete_elliptic_integral_first_kind):
        assert impl(0.0) == pytest.approx(math.pi / 2, abs=1e-15)
        assert impl(0.5) == pytest.approx(1.6857503548125960, abs=1e-13)   # K(k=sin 30°)
        assert impl(math.sin(math.pi / 6)) == pytest.approx(impl(0.5), abs=1e-16)
    closed = suite.pendulum_closed_form(suite.DYNAMIC_SUITE_CONTRACT)
    assert closed["inertia_pivot_kgm2"] == pytest.approx(0.502)
    assert closed["period_s"] > closed["small_angle_period_s"]          # 大角度週期一定比小角度長
    assert closed["period_s"] == pytest.approx(closed["small_angle_period_s"] * 2 / math.pi * 1.6857503548125960, rel=1e-12)


def test_articulated_variant_applies_exactly_the_four_declared_transforms():
    variant, original = suite.build_articulated_mjcf(0.002)
    assert '<freejoint name="root"/>' in original and '<freejoint' not in variant
    assert 'name="floor"' in original and 'name="floor"' not in variant
    assert "<actuator>" in original and "<actuator>" not in variant
    assert '<body name="trunk" pos="0 0 1.6">' in variant
    assert 'timestep="0.002" integrator="implicitfast"><flag energy="enable"/>' in variant
    geoms_o = {g["name"] for g in suite.geom_records_from_mjcf(original)}
    geoms_v = {g["name"] for g in suite.geom_records_from_mjcf(variant)}
    assert geoms_o - geoms_v == {"floor"}


def test_articulated_transform_fails_closed_when_a_declared_pattern_is_missing(monkeypatch):
    _, original = suite.build_articulated_mjcf(0.002)
    monkeypatch.setattr(suite, "build_mjcf", lambda cfg, obstacles, dynamic=False: original.replace('name="floor"', 'name="ground"'))
    with pytest.raises(RuntimeError, match="exactly one match"):
        suite.build_articulated_mjcf(0.002)


def test_analytic_inertia_matches_textbook_values():
    box = [{"type": "box", "size": [0.1, 0.2, 0.3], "pos": [0.0, 0.0, 0.0], "mass": 6.0}]
    out = suite.analytic_body_inertia(box)
    assert out["principal_kgm2"] == pytest.approx(sorted([6 / 3 * (0.04 + 0.09), 6 / 3 * (0.01 + 0.09), 6 / 3 * (0.01 + 0.04)]))
    two_spheres = [{"type": "sphere", "size": [0.1], "pos": [0.0, 0.0, 0.5], "mass": 1.0},
                   {"type": "sphere", "size": [0.1], "pos": [0.0, 0.0, -0.5], "mass": 1.0}]
    out = suite.analytic_body_inertia(two_spheres)
    assert out["com_m"] == pytest.approx([0.0, 0.0, 0.0], abs=1e-15)
    assert out["principal_kgm2"] == pytest.approx(sorted([2 * 0.004, 2 * (0.004 + 0.25), 2 * (0.004 + 0.25)]))
    assert suite.analytic_body_inertia([{"type": "capsule", "size": [0.05], "pos": None, "mass": 1.0}]) is None
    assert replay.analytic_body_inertia(box)["principal_kgm2"] == pytest.approx(suite.analytic_body_inertia(box)["principal_kgm2"], rel=1e-15)


# ---------------------------------------------------------------- primary


def test_primary_suite_passes_the_frozen_contract(primary):
    failing = [(c["case_id"], [k["id"] for k in c["criteria"] if not k["passed"]]) for c in primary["cases"] if c["status"] != "PASS"]
    assert primary["status"] == "PASS", f"suite {primary['suite']['status']}; failing cases: {failing}; suite criteria: {[k for k in primary['suite']['criteria'] if not k['passed']]}"
    assert [c["case_id"] for c in primary["cases"]] == list(replay.FROZEN_CASE_IDS)
    for case in primary["cases"]:
        ids = [k["id"] for k in case["criteria"]]
        assert ids == list(suite.PENDULUM_CRITERION_IDS if case["family"] == "pendulum" else suite.ARTICULATED_CRITERION_IDS)
        assert len(case["raw_trace"]) == case["expected_sample_count"]
    assert [k["id"] for k in primary["suite"]["criteria"]] == list(suite.SUITE_CRITERION_IDS)


def test_pendulum_metrics_are_physically_sensible(primary):
    for case in primary["cases"][:3]:
        m = case["metrics"]
        assert m["period_count"] >= 3
        assert m["period_relative_error"] < 1e-3
        assert m["energy_relative_fluctuation_max"] < case["spec"]["energy_fluctuation_relative_max"]
        assert m["compiled_inertia_relative_error"] < 1e-9


def test_articulated_metrics_are_physically_sensible(primary):
    for case in primary["cases"][3:]:
        m = case["metrics"]
        assert m["energy_scale_j"] > 1.0
        assert m["damping_work_final_j"] > 0.0                       # 阻尼只會耗能
        assert m["kinetic_energy_max_j"] > 0.0
        assert m["inertia_bodies_checked"] == ["foot_l", "foot_r", "trunk"]
        assert m["body_mass_abs_error_max_kg"] <= 1e-12


# ---------------------------------------------------------------- replay


def test_replay_reproduces_primary_metrics_and_passes(primary):
    receipt = replay_dynamic_suite(deepcopy(primary))
    assert receipt["status"] == "PASS", receipt["primary_replay_agreement"]
    assert receipt["primary_replay_agreement"]["all_agree"]
    for comparison in receipt["primary_replay_agreement"]["cases"]:
        assert comparison["agree"] and comparison["criteria_identical"], comparison
    assert receipt["suite"]["timestep_study"]["pendulum_period_s"]["closed_form"] == pytest.approx(
        primary["suite"]["timestep_study"]["pendulum_period_s"]["closed_form"], rel=1e-15)


def test_replay_source_has_no_mujoco_numpy_or_project_dependency():
    tree = ast.parse((HERE / "v1_dynamic_replay.py").read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    assert modules <= {"argparse", "datetime", "hashlib", "json", "math", "pathlib", "sys", "__future__"}, modules


def test_replay_retains_period_tamper_as_fail(primary):
    tampered = deepcopy(primary)
    case = tampered["cases"][1]                                  # known_pendulum_2ms
    for sample in case["raw_trace"]:
        sample["qpos"][0] *= 1.02                               # 有限值的篡改：週期不變但能量與引擎一致性會破
    receipt = replay_dynamic_suite(tampered)
    assert receipt["status"] == "FAIL"
    replayed = next(c for c in receipt["cases"] if c["case_id"] == "known_pendulum_2ms")
    failed = {k["id"] for k in replayed["criteria"] if not k["passed"]}
    assert "ENGINE_POTENTIAL_ENERGY_AGREEMENT" in failed
    assert receipt["primary_replay_agreement"]["all_agree"] is False


def test_replay_retains_velocity_tamper_as_energy_fail(primary):
    tampered = deepcopy(primary)
    case = tampered["cases"][4]                                  # articulated 2ms
    for sample in case["raw_trace"][len(case["raw_trace"]) // 2:]:
        sample["qvel"] = [v * 1.5 for v in sample["qvel"]]
        for body in sample["bodies"]:
            body["linvel_com_world"] = [v * 1.5 for v in body["linvel_com_world"]]
            body["angvel_world"] = [v * 1.5 for v in body["angvel_world"]]
    receipt = replay_dynamic_suite(tampered)
    replayed = next(c for c in receipt["cases"] if c["case_id"] == "articulated_passive_swing_2ms")
    failed = {k["id"] for k in replayed["criteria"] if not k["passed"]}
    assert "ENGINE_KINETIC_ENERGY_AGREEMENT" in failed
    assert receipt["status"] == "FAIL"


@pytest.mark.parametrize("mutation", ["drop_raw_trace", "drop_body_key", "nan_value", "tolerance_drift", "case_inventory_drift", "shape_drift"])
def test_replay_rejects_structural_problems(primary, mutation):
    tampered = deepcopy(primary)
    case = tampered["cases"][0]
    if mutation == "drop_raw_trace":
        case.pop("raw_trace")
    elif mutation == "drop_body_key":
        case["raw_trace"][10]["bodies"][0].pop("ximat")
    elif mutation == "nan_value":
        case["raw_trace"][10]["qvel"][0] = float("nan")
    elif mutation == "tolerance_drift":
        tampered["contract"]["tolerances"]["pendulum_period_relative_error_max"] = 0.5
    elif mutation == "case_inventory_drift":
        tampered["cases"] = tampered["cases"][:5]
    elif mutation == "shape_drift":
        case["raw_trace"][10]["qpos"] = [0.0, 0.0]
    with pytest.raises(ReplayValidationError):
        replay_dynamic_suite(tampered)


def test_replay_cli_rejects_non_standard_json(tmp_path, primary):
    path = tmp_path / "primary.json"
    text = json.dumps({"schema_version": "V1_DYNAMIC_REFERENCE_SUITE_V1", "x": 1.0}).replace("1.0", "NaN")
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ReplayValidationError):
        replay.main([str(path)])


def test_summary_without_raw_drops_traces_but_keeps_criteria(primary):
    compact = suite.summary_without_raw(primary)
    assert all("raw_trace" not in c and "mjcf" not in c for c in compact["cases"])
    assert compact["status"] == primary["status"]
    assert len(json.dumps(compact)) < len(json.dumps(primary)) / 50
