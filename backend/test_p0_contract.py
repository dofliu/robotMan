"""P0 輸入契約、實際運動指標與 provenance regression tests。"""

import copy
import hashlib
import json
import re
import uuid

import numpy as np
import pytest
from pydantic import ValidationError

from config_schema import (
    GaitParams,
    GearSpec,
    MAX_OBSTACLES,
    MotorSpec,
    Obstacle,
    RobotConfig,
    RobotDims,
    SegmentMasses,
    SimRequest,
    default_robot,
)
from simulator import _actual_motion_metrics, run_simulation


def _minimum_robot() -> RobotConfig:
    """建立 physical fields 均位於 current-model minima 的合法配置。"""
    raw = default_robot().model_dump(mode="json")
    raw["dims"].update({
        "torso_len": 0.11, "torso_width": 0.05, "head_radius": 0.03,
        "hip_width": 0.05, "thigh_len": 0.10, "shin_len": 0.10,
        "foot_len": 0.05, "foot_height": 0.01,
        "upper_arm_len": 0.05, "forearm_len": 0.05,
    })
    raw["masses"].update({
        "trunk": 0.001, "head": 0.001, "thigh": 0.001, "shin": 0.001,
        "foot": 0.001, "upper_arm": 0.001, "forearm": 0.001, "payload": 0.0,
    })
    for actuator in raw["actuators"].values():
        actuator["motor"].update({
            "rated_torque": 0.001, "peak_torque": 0.001,
            "rated_speed_rpm": 1.0, "mass": 0.001,
            "rotor_inertia": 1e-9, "efficiency": 0.01,
        })
        actuator["gear"].update({
            "ratio": 0.1, "efficiency": 0.01, "mass": 0.0,
            "rated_torque_out": 0.001,
        })
    return RobotConfig.model_validate(raw)


def _independent_content_hash(out: dict) -> str:
    """不呼叫 production helper，依 provenance 聲明獨立重算 content hash。"""
    result = copy.deepcopy(out)
    provenance = result["meta"].pop("provenance")
    payload = {
        "schema_version": provenance["schema_version"],
        "metric_set_version": provenance["metric_set_version"],
        "deterministic": provenance["deterministic"],
        "simulation_class": provenance["simulation_class"],
        "config_hash": provenance["config_hash"],
        "model_hash": provenance["model_hash"],
        "code_hash": provenance["code_hash"],
        "engine": provenance["engine"],
        "engine_version": provenance["engine_version"],
        "result": result,
    }
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


@pytest.mark.parametrize(
    "factory",
    [
        lambda: GaitParams(mode="jump"),
        lambda: GaitParams(speed=0.0),
        lambda: GaitParams(speed=-0.1),
        lambda: GaitParams(duty=0.1),
        lambda: GaitParams(duration=0.0),
        lambda: GaitParams(duration=60.1),
        lambda: GaitParams(speed=float("nan")),
        lambda: GaitParams(speed=True),
        lambda: GaitParams(speed="1.2"),
        lambda: RobotDims(torso_len=0.10),
        lambda: RobotDims(thigh_len=-0.3),
        lambda: SegmentMasses(trunk=0.0),
        lambda: MotorSpec(rated_torque=2.0, peak_torque=1.0),
        lambda: GearSpec(ratio=0.0),
        lambda: Obstacle(depth=0.0),
        lambda: Obstacle(height=0.0),
        lambda: Obstacle(width=float("inf")),
        lambda: Obstacle(unknown_field=1),
        lambda: RobotConfig(actuators={}),
        lambda: SimRequest(
            robot=default_robot(), obstacles=[Obstacle() for _ in range(MAX_OBSTACLES + 1)],
        ),
    ],
)
def test_invalid_physical_inputs_are_rejected(factory):
    with pytest.raises(ValidationError):
        factory()


def test_existing_default_configuration_remains_valid():
    cfg = default_robot()
    assert set(cfg.actuators) == {
        "hip_roll", "hip_pitch", "knee", "ankle", "shoulder", "elbow",
    }
    assert GaitParams().mode == "walk"
    assert Obstacle().height == pytest.approx(0.15)


def test_zero_or_near_zero_mjcf_box_sizes_are_rejected_by_api_contract():
    robot = default_robot().model_dump(mode="json")
    robot["dims"]["torso_len"] = 0.10
    from fastapi.testclient import TestClient
    from main import app

    response = TestClient(app).post("/api/simulate", json={"robot": robot})
    assert response.status_code == 422

    response = TestClient(app).post(
        "/api/simulate",
        json={
            "robot": default_robot().model_dump(mode="json"),
            "obstacles": [{"x": 2.0, "depth": 0.3, "height": 0.0, "width": 1.2}],
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "field",
    ["rated_torque", "peak_torque", "rated_speed_rpm", "mass", "rotor_inertia", "efficiency"],
)
def test_subnormal_motor_fields_are_rejected(field):
    with pytest.raises(ValidationError):
        MotorSpec(**{field: 5e-324})


@pytest.mark.parametrize("field", ["ratio", "efficiency", "rated_torque_out"])
def test_subnormal_gear_denominators_are_rejected(field):
    with pytest.raises(ValidationError):
        GearSpec(**{field: 5e-324})


@pytest.mark.parametrize(
    "field", ["trunk", "head", "thigh", "shin", "foot", "upper_arm", "forearm"],
)
def test_subnormal_segment_masses_are_rejected(field):
    with pytest.raises(ValidationError):
        SegmentMasses(**{field: 5e-324})


@pytest.mark.parametrize("field", ["depth", "height", "width"])
def test_subnormal_obstacle_dimensions_are_rejected(field):
    with pytest.raises(ValidationError):
        Obstacle(**{field: 5e-324})


def test_robot_gait_compatibility_is_rejected_directly_and_by_rest():
    gait = GaitParams(crouch=0.60, pelvis_bounce=0.50)
    with pytest.raises(ValidationError, match="Robot×Gait"):
        SimRequest(robot=default_robot(), gait=gait, obstacles=[])

    from fastapi.testclient import TestClient
    from main import app

    response = TestClient(app).post(
        "/api/simulate",
        json={
            "robot": default_robot().model_dump(mode="json"),
            "gait": gait.model_dump(mode="json"),
        },
    )
    assert response.status_code == 422


def test_all_minimum_physical_config_has_positive_exact_dynamic_actuator_caps():
    from model_builder import JOINT_ORDER, joint_peak_torque, make_model

    robot = _minimum_robot()
    obstacle = Obstacle(x=2.0, depth=0.001, height=0.001, width=0.001)
    model = make_model(robot, [obstacle], dynamic=True)
    expected = np.array([joint_peak_torque(robot, name) for name in JOINT_ORDER])

    assert np.all(model.actuator_ctrlrange[:, 0] < 0.0)
    assert np.all(model.actuator_ctrlrange[:, 1] > 0.0)
    assert np.all(model.actuator_forcerange[:, 0] < 0.0)
    assert np.all(model.actuator_forcerange[:, 1] > 0.0)
    np.testing.assert_allclose(model.actuator_ctrlrange[:, 1], expected, rtol=1e-12)
    np.testing.assert_allclose(model.actuator_forcerange[:, 1], expected, rtol=1e-12)


def test_all_minimum_physical_config_compiles_through_rest_and_live_init():
    from fastapi.testclient import TestClient
    from main import app

    robot = _minimum_robot()
    gait = GaitParams(
        mode="walk", speed=0.1, step_length=0.02, duty=0.5,
        clearance=0.0, arm_swing_deg=0.0, torso_lean_deg=0.0,
        pelvis_sway=0.0, pelvis_bounce=0.0, crouch=0.0, duration=0.25,
    )
    obstacles = [Obstacle(x=2.0, depth=0.001, height=0.001, width=0.001)]
    payload = {
        "robot": robot.model_dump(mode="json"),
        "gait": gait.model_dump(mode="json"),
        "obstacles": [ob.model_dump(mode="json") for ob in obstacles],
    }
    client = TestClient(app)

    response = client.post("/api/simulate", json=payload)
    assert response.status_code == 200
    json.dumps(response.json(), ensure_ascii=False, allow_nan=False)

    with client.websocket_connect("/ws/live") as socket:
        socket.send_json({"type": "init", **payload})
        scene = socket.receive_json()
        assert scene["type"] == "scene"
        assert any(g["name"] == "obstacle_0" for g in scene["geoms"])


def test_actual_motion_metrics_use_sampled_trajectory_and_elapsed_time():
    times = np.array([0.0, 0.5, 1.0])
    qpos = np.zeros((3, 19))
    qpos[:, 0] = [0.0, 0.4, 1.0]
    power = np.full((3, 12), 2.0)

    m = _actual_motion_metrics(times, qpos, power, total_mass=10.0)

    assert m["elapsed_time_s"] == pytest.approx(1.0)
    assert m["distance_m"] == pytest.approx(1.0)
    assert m["avg_speed_mps"] == pytest.approx(1.0)
    assert m["energy_J"] == pytest.approx(24.0)
    assert m["cot"] == pytest.approx(24.0 / (10.0 * 9.81 * 1.0))


def test_short_run_uses_explicit_full_window_stats_fallback():
    req = SimRequest(
        robot=default_robot(),
        gait=GaitParams(speed=1.2, step_length=0.5, duration=0.5),
        obstacles=[],
    )
    out = run_simulation(req)
    summary = out["meta"]["summary"]

    assert summary["actuator_stats_window"]["mode"] == "full_window_fallback"
    assert summary["actuator_stats_window"]["n_samples"] > 0
    assert any("完整 sampled window" in w for w in out["meta"]["warnings"])
    assert any(v["peak_tau_joint"] > 0.0 for v in summary["groups"].values())
    for stats in summary["groups"].values():
        assert stats["peak_tau_joint"] >= stats["p99_5_tau_joint"]
        assert stats["peak_tau_motor"] >= stats["p99_5_tau_motor"]
        assert stats["peak_speed_rpm"] >= stats["p99_5_speed_rpm"]


def test_zero_forward_distance_returns_json_null_and_warning():
    req = SimRequest(
        robot=default_robot(),
        gait=GaitParams(speed=0.7, step_length=0.35, duration=2.0),
        obstacles=[Obstacle(x=0.1, height=0.5, depth=0.3)],
    )
    out = run_simulation(req)
    summary = out["meta"]["summary"]

    assert summary["stopped_by_obstacle"] is True
    assert summary["distance"] == 0.0
    assert summary["avg_speed"] == 0.0
    assert summary["cot"] is None
    assert any("CoT 無法計算" in w for w in out["meta"]["warnings"])
    # allow_nan=False 同時驗證 API payload 不含 NaN/Inf。
    json.dumps(out, ensure_ascii=False, allow_nan=False)


def test_zmp_empty_sample_set_is_unavailable_not_perfectly_stable():
    req = SimRequest(
        robot=default_robot(),
        gait=GaitParams(
            mode="walk", speed=10.0, step_length=1.0, duty=0.5, duration=0.25,
        ),
        obstacles=[],
    )
    out = run_simulation(req)
    summary = out["meta"]["summary"]

    assert summary["zmp_valid_sample_count"] == 0
    assert summary["zmp_candidate_sample_count"] == 0
    assert summary["zmp_valid_coverage_pct"] is None
    assert summary["zmp_stable_pct"] is None
    assert summary["min_zmp_margin_cm"] is None
    assert summary["p01_zmp_margin_cm"] is None
    assert any("ZMP_STABILITY=UNAVAILABLE" in w for w in out["meta"]["warnings"])
    json.dumps(out, ensure_ascii=False, allow_nan=False)


def test_provenance_and_stable_hashes():
    req = SimRequest(
        robot=default_robot(),
        gait=GaitParams(speed=0.3, step_length=0.2, duration=1.0),
        obstacles=[],
    )
    out1 = run_simulation(req)
    out2 = run_simulation(req)
    p1 = out1["meta"]["provenance"]
    p2 = out2["meta"]["provenance"]

    uuid.UUID(p1["run_id"])
    assert p1["run_id"] != p2["run_id"]
    assert p1["schema_version"] == "1.0"
    assert p1["metric_set_version"] == "ANALYSIS_METRICS_V1"
    assert p1["deterministic"] is True
    assert p1["simulation_class"] == "KINEMATIC_INVERSE_DYNAMICS_ESTIMATE"
    assert p1["assist_enabled"] is False
    assert p1["random_seed"] is None
    assert p1["controller_rate_hz"] is None
    assert p1["controller_rate_applicable"] is False
    assert p1["integrator_applicable"] is False
    assert p1["solver_applicable"] is False
    assert p1["git_sha"] is None
    assert p1["policy_version"] is None
    assert p1["engine"] == "MuJoCo"
    assert p1["engine_version"]
    assert p1["evidence_scope"] == "SOFTWARE_ONLY_KINEMATIC_INVERSE_DYNAMICS_ESTIMATE"
    assert p1["calibration_status"] == "UNCALIBRATED_REPRESENTATIVE_PARAMETERS"

    zmp_summary = out1["meta"]["summary"]
    assert zmp_summary["zmp_valid_sample_count"] > 0
    assert zmp_summary["min_zmp_margin_cm"] is not None
    assert zmp_summary["p01_zmp_margin_cm"] is not None
    assert zmp_summary["p01_zmp_margin_cm"] >= zmp_summary["min_zmp_margin_cm"]

    sha256 = re.compile(r"^sha256:[0-9a-f]{64}$")
    for key in (
        "config_hash", "result_hash", "deterministic_content_hash", "model_hash", "code_hash",
    ):
        assert sha256.match(p1[key])
        assert p1[key] == p2[key]
    assert p1["scenario_id"] == p2["scenario_id"]
    assert p1["deterministic_content_hash"] == p1["result_hash"]
    assert p1["content_hash_algorithm"] == "SHA-256"
    assert "sort_keys=true" in p1["content_hash_canonicalization"]
    assert p1["content_hash_excluded_fields"] == ["meta.provenance", "run_id", "created_at"]
    assert _independent_content_hash(out1) == p1["result_hash"]

    mutated_req = SimRequest(
        robot=default_robot(),
        gait=GaitParams(speed=0.31, step_length=0.2, duration=1.0),
        obstacles=[],
    )
    mutated = run_simulation(mutated_req)
    pm = mutated["meta"]["provenance"]
    assert pm["config_hash"] != p1["config_hash"]
    assert pm["result_hash"] != p1["result_hash"]

    tampered = copy.deepcopy(out1)
    tampered["meta"]["summary"]["distance"] += 1.0
    assert _independent_content_hash(tampered) != p1["result_hash"]
