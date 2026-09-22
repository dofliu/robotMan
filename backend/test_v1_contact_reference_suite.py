"""V1 contact reference suite: frozen contract, closed forms, primary PASS, stdlib replay, fail-closed negatives."""

import ast
from copy import deepcopy
import json
import math
from pathlib import Path

import mujoco
import pytest

import v1_contact_reference_suite as suite
from v1_contact_replay import ReplayValidationError, replay_contact_suite
import v1_contact_replay as replay

HERE = Path(__file__).resolve().parent


@pytest.fixture(scope="module")
def primary() -> dict:
    return suite.run_contact_suite()


# ---------------------------------------------------------------- 凍結的契約與閉式

def test_contract_matches_the_frozen_replay_constants():
    c = suite.CONTACT_SUITE_CONTRACT
    assert c["contract_id"] == replay.FROZEN_CONTRACT_ID == "v1_contact_reference_suite_v1"
    assert c["tolerances"] == replay.FROZEN_TOLERANCES
    assert c["drop"] == replay.FROZEN_DROP and c["slider"] == replay.FROZEN_SLIDER and c["hypothesis"] == replay.FROZEN_HYPOTHESIS
    assert c["friction"] == replay.FROZEN_FRICTION and c["solref"] == replay.FROZEN_SOLREF and c["solimp"] == replay.FROZEN_SOLIMP
    assert c["solver"] == replay.FROZEN_SOLVER and c["gravity_mps2"] == replay.FROZEN_GRAVITY
    assert [s["case_id"] for s in c["case_matrix"]] == list(replay.FROZEN_CASE_IDS)
    assert [s["physics_dt_s"] for s in c["case_matrix"]] == list(replay.FROZEN_CASE_DT)
    assert [s["gates_suite"] for s in c["case_matrix"]] == list(replay.FROZEN_CASE_GATES)
    assert [s.get("kick_velocity_mps") for s in c["case_matrix"]] == list(replay.FROZEN_KICKS)
    assert c["case_matrix"][-1]["hypothesis"] is True and c["case_matrix"][-1]["gates_suite"] is False


def test_closed_forms_match_the_engine_model_semantics():
    c = suite.CONTACT_SUITE_CONTRACT
    assert suite.impedance(0.0, c["solimp"]) == pytest.approx(0.9)                  # x = 0 → d_min
    assert suite.impedance(0.0005, c["solimp"]) == pytest.approx(0.925)             # midpoint → (d_min + d_max)/2
    assert suite.impedance(0.01, c["solimp"]) == pytest.approx(0.95)                # x ≥ 1 → d_max
    assert suite.constraint_stiffness(c["solref"], c["solimp"]) == pytest.approx(1 / (0.95 ** 2 * 0.02 ** 2))
    assert suite.constraint_damping(c["solref"], c["solimp"]) == pytest.approx(2 / (0.95 * 0.02))
    forms = suite.closed_forms(c)
    # 單點與四點分擔的平衡穿透：設計期以引擎的 efc_aref／efc_R／efc_force 核對過的閉式（規格 §2.4）
    assert forms["rest_penetration_drop_m"] == pytest.approx(3.6718184e-4, rel=1e-6)
    assert forms["rest_penetration_slider_m"] == pytest.approx(1.0775542e-4, rel=1e-6)
    assert forms["rest_penetration_drop_m"] > 3 * forms["rest_penetration_slider_m"]
    assert forms["viscous_slip_rate_per_s"] == pytest.approx(99.7907, rel=1e-5)
    assert forms["saturation_speed_mps"] == pytest.approx(9.81 / forms["viscous_slip_rate_per_s"])
    assert forms["touchdown_time_continuous_s"] == pytest.approx(math.sqrt(2 * 0.5 / 9.81))
    for k, v in forms.items():
        assert replay.closed_forms(c)[k] == pytest.approx(v, rel=1e-15), k


def test_discrete_touchdown_step_and_gap_are_exact_combinatorics():
    assert suite.discrete_touchdown_step(0.2, 9.81, 0.004) == 50                    # 設計期 pilot 的非凍結組態
    assert suite.discrete_touchdown_step(0.2, 9.81, 0.002) == 101
    for dt in (0.004, 0.002, 0.001):
        n = suite.discrete_touchdown_step(0.5, 9.81, dt)
        assert 9.81 * dt * dt * n * (n + 1) / 2 > 0.5 >= 9.81 * dt * dt * (n - 1) * n / 2
        assert abs(n * dt - math.sqrt(1.0 / 9.81)) <= dt
        assert replay.discrete_touchdown_step(0.5, 9.81, dt) == n
    assert suite.discrete_continuous_gap(0.4, 50) == pytest.approx(max(abs(0.6 ** k - math.exp(-0.4 * k)) for k in range(1, 51)))
    assert suite.discrete_continuous_gap(0.1, 500) < suite.discrete_continuous_gap(0.2, 500) < suite.discrete_continuous_gap(0.4, 500)


def test_mjcf_builders_use_the_plant_floor_and_compile_to_the_contract():
    c = suite.CONTACT_SUITE_CONTRACT
    for build, body in ((suite.build_drop_mjcf, "ball"), (suite.build_slider_mjcf, "slider")):
        xml = build(0.002, c)
        assert suite.FLOOR_XML in xml and 'friction="1.0 0.005 0.0001"' in xml and 'integrator="implicitfast"' in xml
        model = mujoco.MjModel.from_xml_string(xml)
        receipt = suite.compiled_model_receipt(model, xml)
        assert receipt["integrator"] == "mjINT_IMPLICITFAST" and receipt["cone"] == "mjCONE_PYRAMIDAL" and receipt["nu"] == 0
        assert receipt["timestep_s"] == 0.002 and receipt["solver_tolerance"] == 1e-8 and receipt["solver_iterations"] == 100
        geoms = {g["name"]: g for g in receipt["geoms"]}
        assert set(geoms) == {"floor", body}
        for g in geoms.values():
            assert g["solref"] == c["solref"] and g["solimp"] == c["solimp"] and g["friction"] == c["friction"] and g["condim"] == 3
        assert receipt["body_mass"][body] == pytest.approx(1.0, abs=1e-12)
    slider = mujoco.MjModel.from_xml_string(suite.build_slider_mjcf(0.002, c))
    assert slider.nq == 2 and slider.nv == 2 and slider.nu == 0
    drop = mujoco.MjModel.from_xml_string(suite.build_drop_mjcf(0.002, c))
    assert drop.nq == 7 and drop.nv == 6


# ---------------------------------------------------------------- primary

def test_primary_gate_cases_pass_the_frozen_contract(primary):
    failing = [(c["case_id"], [k["id"] for k in c["criteria"] if not k["passed"]]) for c in primary["cases"] if c["status"] != "PASS"]
    assert primary["status"] == "PASS", f"suite {primary['suite']['status']}; failing: {failing}; suite criteria: {[k['id'] for k in primary['suite']['criteria'] if not k['passed']]}"
    assert [c["case_id"] for c in primary["cases"]] == list(replay.FROZEN_CASE_IDS)
    for case in primary["cases"]:
        ids = [k["id"] for k in case["criteria"]]
        if case["family"] == "drop":
            assert ids == list(suite.DROP_CRITERION_IDS)
        elif case["spec"].get("hypothesis"):
            assert ids == list(suite.SLIDER_GATE_CRITERION_IDS)
            assert [h["id"] for h in case["hypotheses"]] == list(suite.HYPOTHESIS_IDS)
            assert all(h["role"] == "hypothesis" for h in case["hypotheses"])
        else:
            assert ids == list(suite.VISCOUS_CRITERION_IDS) and case["hypotheses"] == []
        assert all(k["role"] == "gate" for k in case["criteria"])
        assert len(case["raw_trace"]) == case["expected_sample_count"]
    assert [k["id"] for k in primary["suite"]["criteria"]] == list(suite.SUITE_CRITERION_IDS)


def test_drop_metrics_are_physically_sensible(primary):
    for case in primary["cases"][:3]:
        m = case["metrics"]
        assert m["touchdown_step"] == m["touchdown_step_closed"]
        assert 0 < m["touchdown_time_error_s"] <= case["physics_dt_s"]
        assert m["peak_normal_force_n"] > 10 * 9.81                         # 撞擊尖峰遠大於重量
        assert 0 < m["max_penetration_m"] < 0.05
        assert m["rest_penetration_m"] == pytest.approx(m["rest_penetration_closed_m"], rel=1e-5)
        assert m["normal_impulse_ns"] == pytest.approx(m["weight_integral_ns"], rel=1e-6)


def test_slider_metrics_are_physically_sensible(primary):
    for case in primary["cases"][3:6]:
        m = case["metrics"]
        assert m["slip_utilisation_max"] < 0.5 and m["contact_count_constant"] == 1
        assert m["viscous_discrete_relative_error_max"] < 1e-6                 # 幾何衰減逐步 exact
        assert m["viscous_continuous_relative_error_max"] == pytest.approx(m["viscous_discrete_continuous_gap"], abs=1e-6)
        assert m["viscous_rate_measured_mean_per_s"] == pytest.approx(m["viscous_rate_closed_per_s"], rel=1e-6)
        assert m["lost_contact_samples_after_kick"] == 0
    kicked = primary["cases"][3]["raw_trace"][primary["cases"][3]["kick_step"]]
    assert kicked["qvel"][0] == 0.02 and kicked["time_s"] == pytest.approx(1.0)


def test_hypothesis_case_records_outcomes_without_gating_the_suite(primary):
    hyp = primary["cases"][6]
    assert hyp["gates_suite"] is False and hyp["status"] == "PASS"            # 簿記判準仍要過
    outcomes = {h["id"]: h["passed"] for h in hyp["hypotheses"]}
    assert set(outcomes) == set(suite.HYPOTHESIS_IDS)
    assert primary["suite"]["hypothesis_outcomes"][0]["case_id"] == hyp["case_id"]
    # 假說翻面不改變 suite 狀態
    flipped = deepcopy(primary["cases"])
    evaluations = [{k: c[k] for k in ("case_id", "status", "criteria", "hypotheses", "metrics", "gates_suite")} for c in flipped]
    for h in evaluations[6]["hypotheses"]:
        h["passed"] = not h["passed"]
    again = suite.evaluate_suite(flipped, evaluations)
    assert again["status"] == primary["suite"]["status"]
    assert [x["passed"] for x in again["hypothesis_outcomes"][0]["hypotheses"]] == [not outcomes[i] for i in suite.HYPOTHESIS_IDS]


# ---------------------------------------------------------------- replay

def test_replay_reproduces_primary_metrics_and_passes(primary):
    receipt = replay_contact_suite(deepcopy(primary))
    assert receipt["status"] == "PASS", receipt["primary_replay_agreement"]
    assert receipt["primary_replay_agreement"]["all_agree"] and receipt["primary_replay_agreement"]["suite_criteria_identical"]
    for comparison in receipt["primary_replay_agreement"]["cases"]:
        assert comparison["agree"] and comparison["criteria_identical"] and comparison["hypotheses_identical"], comparison
    assert receipt["suite"]["closed_forms"]["viscous_slip_rate_per_s"] == pytest.approx(primary["suite"]["closed_forms"]["viscous_slip_rate_per_s"], rel=1e-15)


def test_replay_source_has_no_mujoco_numpy_or_project_dependency():
    tree = ast.parse((HERE / "v1_contact_replay.py").read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    assert modules <= {"argparse", "datetime", "hashlib", "json", "math", "pathlib", "sys", "__future__"}, modules


def test_replay_retains_rest_force_tamper_as_fail(primary):
    tampered = deepcopy(primary)
    case = tampered["cases"][1]                                     # drop 2 ms
    for sample in case["raw_trace"][-50:]:
        for contact in sample["contacts"]:
            contact["force_contact_frame"][0] *= 1.001              # 有限值篡改：靜止 GRF 偏 0.1%
    receipt = replay_contact_suite(tampered)
    replayed = next(c for c in receipt["cases"] if c["case_id"] == "drop_and_settle_2ms")
    failed = {k["id"] for k in replayed["criteria"] if not k["passed"]}
    assert {"REST_NORMAL_FORCE_VS_WEIGHT", "CONTACT_FORCE_WORLD_SUM_MATCHES_QFRC_CONSTRAINT"} <= failed
    assert receipt["status"] == "FAIL" and receipt["primary_replay_agreement"]["all_agree"] is False


def test_replay_retains_slip_velocity_tamper_as_fail(primary):
    tampered = deepcopy(primary)
    case = tampered["cases"][4]                                     # viscous slider 2 ms
    kick = case["kick_step"]
    for sample in case["raw_trace"][kick + 1:kick + 6]:
        sample["qvel"][0] *= 1.05
    receipt = replay_contact_suite(tampered)
    replayed = next(c for c in receipt["cases"] if c["case_id"] == "viscous_slider_2ms")
    failed = {k["id"] for k in replayed["criteria"] if not k["passed"]}
    assert "VISCOUS_SLIP_VS_DISCRETE_CLOSED_FORM" in failed and "STEP_VELOCITY_UPDATE_IDENTITY" in failed
    assert receipt["status"] == "FAIL"


@pytest.mark.parametrize("mutation", ["drop_raw_trace", "drop_contact_key", "nan_value", "tolerance_drift",
                                      "case_inventory_drift", "shape_drift", "window_drift", "kick_drift"])
def test_replay_rejects_structural_problems(primary, mutation):
    tampered = deepcopy(primary)
    case = tampered["cases"][0]
    if mutation == "drop_raw_trace":
        case.pop("raw_trace")
    elif mutation == "drop_contact_key":
        sample = next(s for s in tampered["cases"][3]["raw_trace"] if s["contacts"])
        sample["contacts"][0].pop("frame")
    elif mutation == "nan_value":
        case["raw_trace"][10]["qvel"][0] = float("nan")
    elif mutation == "tolerance_drift":
        tampered["contract"]["tolerances"]["rest_penetration_relative_max"] = 0.5
    elif mutation == "case_inventory_drift":
        tampered["cases"] = tampered["cases"][:6]
    elif mutation == "shape_drift":
        case["raw_trace"][10]["qpos"] = [0.0, 0.0]
    elif mutation == "window_drift":
        tampered["contract"]["slider"]["pre_rest_window_s"] = [0.1, 1.0]
    elif mutation == "kick_drift":
        tampered["contract"]["case_matrix"][3]["kick_velocity_mps"] = 0.5
    with pytest.raises(ReplayValidationError):
        replay_contact_suite(tampered)


def test_replay_cli_rejects_non_standard_json(tmp_path):
    path = tmp_path / "primary.json"
    path.write_text(json.dumps({"schema_version": "V1_CONTACT_REFERENCE_SUITE_V1", "x": 1.0}).replace("1.0", "NaN"), encoding="utf-8")
    with pytest.raises(ReplayValidationError):
        replay.main([str(path)])


def test_summary_without_raw_drops_traces_but_keeps_criteria_and_hypotheses(primary):
    compact = suite.summary_without_raw(primary)
    assert all("raw_trace" not in c and "mjcf" not in c for c in compact["cases"])
    assert compact["status"] == primary["status"] and compact["cases"][6]["hypotheses"] == primary["cases"][6]["hypotheses"]
    assert len(json.dumps(compact)) < len(json.dumps(primary)) / 50
