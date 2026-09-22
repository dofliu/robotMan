"""V1 actuated energy suite: frozen contract, references, primary PASS, stdlib replay, fail-closed negatives."""

import ast
from copy import deepcopy
import json
import math
from pathlib import Path

import mujoco
import numpy as np
import pytest

import v1_actuated_energy_suite as suite
from v1_actuated_energy_replay import ReplayValidationError, replay_actuated_suite
import v1_actuated_energy_replay as replay
from config_schema import default_robot
from controller import BalanceController
from model_builder import JOINT_ORDER

HERE = Path(__file__).resolve().parent


@pytest.fixture(scope="module")
def primary() -> dict:
    return suite.run_actuated_suite()


def _light_copy(primary: dict, case_index: int | None = None, copy_contract: bool = False) -> dict:
    """Copy only what a tamper touches: the 1 ms traces are large, a full deepcopy is not needed."""
    tampered = dict(primary)
    tampered["cases"] = list(primary["cases"])
    if case_index is not None:
        tampered["cases"][case_index] = deepcopy(primary["cases"][case_index])
    if copy_contract:
        tampered["contract"] = deepcopy(primary["contract"])
    return tampered


# ---------------------------------------------------------------- 凍結的契約與參考訊號

def test_contract_matches_the_frozen_replay_constants():
    c = suite.ACTUATED_SUITE_CONTRACT
    assert c["contract_id"] == replay.FROZEN_CONTRACT_ID == "v1_actuated_energy_suite_v1"
    assert c["tolerances"] == replay.FROZEN_TOLERANCES
    assert c["openloop"] == replay.FROZEN_OPENLOOP and c["squat"] == replay.FROZEN_SQUAT
    assert c["joint_order"] == replay.FROZEN_JOINT_ORDER == list(JOINT_ORDER)
    assert [s["case_id"] for s in c["case_matrix"]] == list(replay.FROZEN_CASE_IDS)
    assert [s["physics_dt_s"] for s in c["case_matrix"]] == list(replay.FROZEN_CASE_DT)
    assert [s["energy_residual_relative_max"] for s in c["case_matrix"]] == list(replay.FROZEN_RESIDUAL_MAX)
    assert c["gravity_mps2"] == replay.FROZEN_GRAVITY == 9.81


def test_prescribed_torque_stays_inside_the_force_range_and_matches_replay():
    c = suite.ACTUATED_SUITE_CONTRACT
    hi = [270.0, 540.0, 270.0, 270.0, 270.0, 540.0, 270.0, 270.0, 30.46, 11.84, 30.46, 11.84]
    for t in (0.0, 0.123, 1.5, 2.999):
        u = suite.prescribed_ctrl(t, hi, c)
        assert all(abs(x) <= c["openloop"]["amplitude_fraction"] * h + 1e-15 for x, h in zip(u, hi))
        assert u == replay.prescribed_ctrl(t, hi, c)
    assert suite.prescribed_ctrl(0.0, hi, c)[0] == 0.0                    # phase 0 at joint 0
    assert suite.squat_depth(0.5, c) == 0.0 and suite.squat_depth(1.0, c) == 0.0
    assert suite.squat_depth(3.0, c) == pytest.approx(c["squat"]["depth_m"])   # half period after settle → deepest
    assert suite.squat_depth(5.0, c) == pytest.approx(0.0, abs=1e-15)         # full period → back up


def test_mjcf_builders_apply_exactly_the_declared_transforms():
    c = suite.ACTUATED_SUITE_CONTRACT
    variant, original = suite.build_openloop_mjcf(0.002, c)
    assert "<freejoint" in original and "<freejoint" not in variant
    assert 'name="floor"' in original and 'name="floor"' not in variant
    assert "<actuator>" in variant and '<body name="trunk" pos="0 0 1.6">' in variant
    assert '<flag energy="enable"/>' in variant and 'timestep="0.002" integrator="implicitfast"' in variant
    squat, original2 = suite.build_squat_mjcf(0.004, c)
    assert original2 == original
    assert "<freejoint" in squat and 'name="floor"' in squat and "<actuator>" in squat and '<flag energy="enable"/>' in squat
    model = mujoco.MjModel.from_xml_string(variant)
    receipt = suite.compiled_model_receipt(model, variant, original)
    assert receipt["nu"] == 12 and [a["joint"] for a in receipt["actuators"]] == list(JOINT_ORDER)
    assert all(a["gear"][0] == 1.0 and a["ctrlrange"] == a["forcerange"] for a in receipt["actuators"])
    assert receipt["has_floor"] is False and receipt["has_freejoint"] is False and receipt["energy_flag_enabled"]
    model2 = mujoco.MjModel.from_xml_string(squat)
    receipt2 = suite.compiled_model_receipt(model2, squat, original)
    assert receipt2["has_floor"] and receipt2["has_freejoint"] and receipt2["nv"] == 18


def test_squat_reference_uses_the_plant_stand_law_gains_and_pose():
    c = suite.ACTUATED_SUITE_CONTRACT
    cfg = default_robot()
    model = mujoco.MjModel.from_xml_string(suite.build_squat_mjcf(0.002, c)[0])
    controller = BalanceController(model, cfg, None, 0.0)
    ref = suite.SquatReference(cfg, controller, c)
    assert np.allclose(ref.q_ref(0.0), controller.stand_q, atol=1e-12)     # settle phase = plant stand pose
    deep = ref.q_ref(3.0)
    assert deep[JOINT_ORDER.index("knee_l")] != controller.stand_q[JOINT_ORDER.index("knee_l")]
    assert deep[JOINT_ORDER.index("knee_l")] == deep[JOINT_ORDER.index("knee_r")]     # 對稱
    assert deep[JOINT_ORDER.index("shoulder_l")] == c["squat"]["shoulder_rad"] and deep[JOINT_ORDER.index("elbow_r")] == c["squat"]["elbow_rad"]
    assert np.all(controller.kd == pytest.approx(0.06 * controller.kp)) and np.all(controller.kp >= 60.0) and np.all(controller.kp <= 900.0)


# ---------------------------------------------------------------- primary

def test_primary_suite_passes_the_frozen_contract(primary):
    failing = [(c["case_id"], [k["id"] for k in c["criteria"] if not k["passed"]]) for c in primary["cases"] if c["status"] != "PASS"]
    assert primary["status"] == "PASS", f"suite {primary['suite']['status']}; failing: {failing}; suite criteria: {[k['id'] for k in primary['suite']['criteria'] if not k['passed']]}"
    assert [c["case_id"] for c in primary["cases"]] == list(replay.FROZEN_CASE_IDS)
    for case in primary["cases"]:
        ids = [k["id"] for k in case["criteria"]]
        assert ids == list(suite.OPENLOOP_CRITERION_IDS if case["family"] == "openloop" else suite.SQUAT_CRITERION_IDS)
        assert len(case["raw_trace"]) == case["expected_sample_count"]
    assert [k["id"] for k in primary["suite"]["criteria"]] == list(suite.SUITE_CRITERION_IDS)


def test_openloop_metrics_are_physically_sensible(primary):
    for case in primary["cases"][:3]:
        m = case["metrics"]
        assert m["actuator_work_abs_max_j"] > 1.0 and m["damping_work_final_j"] > 0.0
        assert m["ncon_max"] == 0 and m["prescribed_ctrl_relative_error_max"] <= 1e-12
        assert m["energy_residual_relative_max"] < case["spec"]["energy_residual_relative_max"]
        assert m["implicit_velocity_correction_max"] > 1e-6          # implicitfast 有阻尼時不是半隱式 Euler（規格 §1.1 第 3 點）


def test_squat_metrics_are_physically_sensible(primary):
    for case in primary["cases"][3:]:
        m = case["metrics"]
        assert m["planted_contact_count_constant"] == 1 and m["ncon_max"] == 8
        assert m["pelvis_z_fraction_min"] > 0.75 and m["trunk_angle_abs_max_rad"] < 0.2
        assert m["contact_work_final_j"] < 0.0                        # 軟接觸只耗能
        assert m["actuator_work_final_j"] < 0.0                       # 蹲下再站起：致動器淨吸收
        assert m["pd_law_error_max"] <= 1e-9 and m["qd_ref_error_max"] <= 1e-9
        first = case["raw_trace"][0]
        assert first["q_ref"] == pytest.approx(case["controller"]["stand_q"]) and first["qd_ref"] == [0.0] * 12


# ---------------------------------------------------------------- replay

def test_replay_reproduces_primary_metrics_and_passes(primary):
    receipt = replay_actuated_suite(primary)
    assert receipt["status"] == "PASS", receipt["primary_replay_agreement"]
    assert receipt["primary_replay_agreement"]["all_agree"] and receipt["primary_replay_agreement"]["suite_criteria_identical"]
    for comparison in receipt["primary_replay_agreement"]["cases"]:
        assert comparison["agree"] and comparison["criteria_identical"], comparison


def test_replay_source_has_no_mujoco_numpy_or_project_dependency():
    tree = ast.parse((HERE / "v1_actuated_energy_replay.py").read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    assert modules <= {"argparse", "datetime", "hashlib", "json", "math", "pathlib", "sys", "__future__"}, modules


def test_replay_retains_torque_tamper_as_fail(primary):
    tampered = _light_copy(primary, 1)
    case = tampered["cases"][1]                                     # openloop 2 ms
    for sample in case["raw_trace"][200:600]:
        sample["qfrc_actuator"] = [x * 1.1 for x in sample["qfrc_actuator"]]
    receipt = replay_actuated_suite(tampered)
    replayed = next(c for c in receipt["cases"] if c["case_id"] == "actuated_openloop_2ms")
    failed = {k["id"] for k in replayed["criteria"] if not k["passed"]}
    assert "QFRC_ACTUATOR_MATCHES_GEAR_FORCE" in failed and "ENERGY_BALANCE_RESIDUAL_RELATIVE_MAX" in failed
    assert receipt["status"] == "FAIL" and receipt["primary_replay_agreement"]["all_agree"] is False


def test_replay_retains_contact_force_tamper_as_fail(primary):
    tampered = _light_copy(primary, 4)
    case = tampered["cases"][4]                                     # squat 2 ms
    for sample in case["raw_trace"][600:1600]:
        for contact in sample["contacts"]:
            contact["force_contact_frame"][0] *= 1.5
    receipt = replay_actuated_suite(tampered)
    replayed = next(c for c in receipt["cases"] if c["case_id"] == "planted_squat_2ms")
    failed = {k["id"] for k in replayed["criteria"] if not k["passed"]}
    assert "CONTACT_FORCE_WORLD_SUM_MATCHES_QFRC_CONSTRAINT" in failed
    assert receipt["status"] == "FAIL"


@pytest.mark.parametrize("mutation", ["drop_raw_trace", "drop_body_key", "nan_value", "tolerance_drift",
                                      "case_inventory_drift", "shape_drift", "reference_missing", "controller_missing", "threshold_drift"])
def test_replay_rejects_structural_problems(primary, mutation):
    tampered = _light_copy(primary, 0, copy_contract=True)
    tampered["cases"][3] = deepcopy(primary["cases"][3]) if mutation in ("reference_missing", "controller_missing") else tampered["cases"][3]
    case = tampered["cases"][0]
    if mutation == "drop_raw_trace":
        case.pop("raw_trace")
    elif mutation == "drop_body_key":
        case["raw_trace"][10]["bodies"][0].pop("ximat")
    elif mutation == "nan_value":
        case["raw_trace"][10]["qvel"][0] = float("nan")
    elif mutation == "tolerance_drift":
        tampered["contract"]["tolerances"]["pd_law_abs_max"] = 1.0
    elif mutation == "case_inventory_drift":
        tampered["cases"] = tampered["cases"][:5]
    elif mutation == "shape_drift":
        case["raw_trace"][10]["ctrl"] = [0.0]
    elif mutation == "reference_missing":
        tampered["cases"][3]["raw_trace"][5].pop("q_ref")
    elif mutation == "controller_missing":
        tampered["cases"][3]["controller"] = None
    elif mutation == "threshold_drift":
        tampered["contract"]["case_matrix"][0]["energy_residual_relative_max"] = 0.5
    with pytest.raises(ReplayValidationError):
        replay_actuated_suite(tampered)


def test_replay_cli_rejects_non_standard_json(tmp_path):
    path = tmp_path / "primary.json"
    path.write_text(json.dumps({"schema_version": "V1_ACTUATED_ENERGY_SUITE_V1", "x": 1.0}).replace("1.0", "Infinity"), encoding="utf-8")
    with pytest.raises(ReplayValidationError):
        replay.main([str(path)])


def test_summary_without_raw_drops_traces_but_keeps_criteria(primary):
    compact = suite.summary_without_raw(primary)
    assert all("raw_trace" not in c and "mjcf" not in c for c in compact["cases"])
    assert compact["status"] == primary["status"]
    assert len(json.dumps(compact)) < len(json.dumps(primary)) / 50
