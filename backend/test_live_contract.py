"""P0 numerical-resolution and live WebSocket contract regression tests."""

import math

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from config_schema import GaitParams, Obstacle, SimRequest, default_robot, validate_live_command
from live_sim import LiveSession
from main import app
from simulator import run_simulation


def _receive_type(socket, wanted: str, limit: int = 30) -> dict:
    """Live endpoint 會持續送 frame；測試只取指定訊息類型。"""
    for _ in range(limit):
        message = socket.receive_json()
        if message.get("type") == wanted:
            return message
    pytest.fail(f"未在 {limit} 則 WebSocket 訊息內收到 type={wanted}")


def test_pathological_phase_resolution_is_rejected_before_simulation():
    robot = default_robot()
    invalid_gait = {
        "mode": "run",
        "speed": 10.0,
        "step_length": 0.02,
        "duty": 0.25,
        "duration": 0.1,
    }

    with pytest.raises(ValidationError):
        GaitParams.model_validate(invalid_gait)
    # 即使 duration 達到最低資源窗，過短步態 phase 仍 fail-closed。
    with pytest.raises(ValidationError, match="planner grid"):
        GaitParams.model_validate({**invalid_gait, "duration": 0.25})

    response = TestClient(app).post(
        "/api/simulate", json={"robot": robot.model_dump(mode="json"), "gait": invalid_gait},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "gait",
    [
        GaitParams(mode="walk", speed=0.3, step_length=0.2, duty=0.60, duration=0.25),
        GaitParams(mode="run", speed=2.8, step_length=0.85, duty=0.38, duration=0.25),
        # 最小允許單步時間與 duty 邊界，覆蓋 planner/analysis resolution gate。
        GaitParams(mode="run", speed=2.0, step_length=0.2, duty=0.25, duration=0.25),
    ],
)
def test_supported_resolution_boundary_requests_complete(gait):
    out = run_simulation(SimRequest(robot=default_robot(), gait=gait, obstacles=[]))
    assert out["meta"]["n_frames"] >= 10
    assert out["meta"]["summary"]["actuator_stats_window"]["n_samples"] > 0


def test_live_session_rejects_nonfinite_and_mistyped_commands_without_mutation():
    session = LiveSession(default_robot(), GaitParams(), [])
    initial_speed = session.speed
    initial_controller = session.controller
    initial_label = session.walk_controller

    for message in (
        {"type": "speed", "value": math.nan},
        {"type": "speed", "value": True},
        {"type": "speed", "value": "0.5"},
        {"type": "push", "dir": [1, 0, 0], "force": math.nan, "duration": 0.2},
        {"type": "push", "dir": [1, 0, 0], "force": True, "duration": 0.2},
        {"type": "push", "dir": [1, 0, 0], "force": "100", "duration": 0.2},
        {"type": "push", "dir": [True, 0, 0], "force": 100, "duration": 0.2},
        {"type": "push", "dir": [1e308, 0, 0], "force": 100, "duration": 0.2},
        {"type": "assist", "on": "false"},
        {"type": "mode", "mode": "walk", "controller": "bogus"},
    ):
        error = session.command(message)
        assert error["type"] == "error"
        assert error["code"] == "INVALID_COMMAND"

    assert session.speed == initial_speed
    assert session.controller is initial_controller
    assert session.walk_controller == initial_label
    assert session.assist_balance is True
    assert session.startup_assist_enabled is True
    assert session.push is None


def test_json_push_direction_list_remains_valid_under_strict_numeric_contract():
    command = validate_live_command({
        "type": "push", "dir": [1, 0, 0], "force": 100, "duration": 0.2,
    })
    assert command.dir == [1.0, 0.0, 0.0]


@pytest.mark.parametrize("kind", ["track", "raibert"])
def test_runtime_gait_update_synchronizes_actual_controller_without_replacement(kind):
    session = LiveSession(default_robot(), GaitParams(), [])
    assert session.command({"type": "mode", "mode": "walk", "controller": kind}) is None
    controller = session.controller
    state = controller.state
    phase = getattr(controller, "phase", None)

    result = session.command({
        "type": "gait",
        "speed": 0.6,
        "step_length": 0.3,
        "clearance": 0.09,
        "arm_swing_deg": 25.0,
        "torso_lean_deg": 6.0,
    })

    assert result is None
    assert session.controller is controller
    assert controller.state == state == "WALK"
    assert session.engine.g is session.gait
    assert controller.engine is session.engine
    assert controller.lean == pytest.approx(math.radians(6.0))
    if kind == "raibert":
        assert controller.gait is session.gait
        assert controller.T_step == pytest.approx(0.5)
        assert controller.phase == phase


def test_rl_runtime_gait_update_fails_closed_without_session_mutation():
    session = LiveSession(default_robot(), GaitParams(), [])
    old_gait = session.gait
    old_engine = session.engine
    old_controller = session.controller
    session.walk_controller = "rl"  # 隔離測試 fixed-policy runtime contract，無需載入模型。

    error = session.command({"type": "gait", "speed": 0.8})

    assert error["type"] == "error"
    assert error["code"] == "RUNTIME_GAIT_UNSUPPORTED"
    assert "speed" in error["message"]
    assert session.gait is old_gait
    assert session.engine is old_engine
    assert session.controller is old_controller


def test_incompatible_runtime_gait_fails_closed_without_session_mutation():
    session = LiveSession(default_robot(), GaitParams(), [])
    old_gait = session.gait
    old_engine = session.engine
    old_controller = session.controller
    old_anchor = session.anchor

    error = session.command({"type": "gait", "crouch": 0.60, "pelvis_bounce": 0.50})

    assert error["type"] == "error"
    assert error["code"] == "ROBOT_GAIT_INCOMPATIBLE"
    assert session.gait is old_gait
    assert session.engine is old_engine
    assert session.controller is old_controller
    assert session.anchor == old_anchor


def test_incompatible_robot_gait_live_init_returns_invalid_init():
    client = TestClient(app)
    gait = GaitParams(crouch=0.60, pelvis_bounce=0.50)
    with client.websocket_connect("/ws/live") as socket:
        socket.send_json({
            "type": "init",
            "robot": default_robot().model_dump(mode="json"),
            "gait": gait.model_dump(mode="json"),
        })
        error = _receive_type(socket, "error")
        assert error["code"] == "INVALID_INIT"
        assert "Robot×Gait" in error["message"]


def test_reset_restores_init_obstacle_snapshot_after_runtime_additions():
    initial = [Obstacle(x=2.0, depth=0.3, height=0.12, width=1.2)]
    session = LiveSession(default_robot(), GaitParams(), initial)
    assert session.command({
        "type": "obstacle", "dist": 1.0, "height": 0.15, "depth": 0.3,
    }) == "scene"
    assert len(session.obstacles) == 2
    assert session.command({
        "type": "push", "dir": [1, 0, 0], "force": 100, "duration": 0.2,
    }) is None

    assert session.command({"type": "reset"}) == "scene"

    assert len(session.obstacles) == 1
    assert session.obstacles[0] == initial[0]
    assert session.obstacles[0] is not initial[0]
    assert session.push is None
    assert session.push_info is None


def test_live_obstacle_limit_fails_closed_before_scene_mutation():
    obstacles = [
        Obstacle(x=100.0 + 2.0 * i, depth=0.1, height=0.05, width=1.2)
        for i in range(100)
    ]
    session = LiveSession(default_robot(), GaitParams(), obstacles)
    before_obstacles = [ob.model_dump() for ob in session.obstacles]
    before_scene = session.scene()
    before_model = session.model
    before_controller = session.controller

    error = session.command({
        "type": "obstacle", "dist": 1.0, "height": 0.15, "depth": 0.3,
    })

    assert error["type"] == "error"
    assert error["code"] == "OBSTACLE_LIMIT_REACHED"
    assert len(session.obstacles) == 100
    assert [ob.model_dump() for ob in session.obstacles] == before_obstacles
    assert session.model is before_model
    assert session.controller is before_controller
    assert session.scene() == before_scene


def test_rl_load_failure_preserves_controller_and_returns_structured_error(monkeypatch):
    session = LiveSession(default_robot(), GaitParams(), [])
    old_controller = session.controller
    old_label = session.walk_controller
    old_mode = session.mode
    original = LiveSession._make_controller

    def fail_rl(self, lean, kind=None):
        if kind == "rl":
            raise FileNotFoundError("test model absent")
        return original(self, lean, kind)

    monkeypatch.setattr(LiveSession, "_make_controller", fail_rl)
    error = session.command({"type": "mode", "mode": "walk", "controller": "rl"})

    assert error["type"] == "error"
    assert error["code"] == "RL_LOAD_FAILED"
    assert session.controller is old_controller
    assert session.walk_controller == old_label
    assert session.mode == old_mode


def test_assist_false_disables_balance_and_track_startup_interventions():
    session = LiveSession(default_robot(), GaitParams(), [])
    assert session.command({"type": "assist", "on": False}) is None
    assert session.command({"type": "mode", "mode": "walk", "controller": "track"}) is None
    session.advance(0.05)
    frame = session.frame()

    assert frame["assist_enabled"] is False
    assert frame["interventions"] == {
        "balance_assist_enabled": False,
        "startup_assist_active": False,
        "external_push_active": False,
    }


def test_websocket_invalid_inputs_and_rl_failure_are_client_visible(monkeypatch):
    original = LiveSession._make_controller

    def fail_rl(self, lean, kind=None):
        if kind == "rl":
            raise FileNotFoundError("test model absent")
        return original(self, lean, kind)

    monkeypatch.setattr(LiveSession, "_make_controller", fail_rl)
    robot = default_robot().model_dump(mode="json")
    client = TestClient(app)
    with client.websocket_connect("/ws/live") as socket:
        socket.send_json({"type": "init", "robot": robot, "unexpected": True})
        invalid_init = _receive_type(socket, "error")
        assert invalid_init["code"] == "INVALID_INIT"

        socket.send_json({"type": "init", "robot": robot})
        _receive_type(socket, "scene")

        socket.send_json({"type": "assist", "on": "false"})
        assert _receive_type(socket, "error")["code"] == "INVALID_COMMAND"
        frame = _receive_type(socket, "frame")
        assert frame["assist_enabled"] is True

        socket.send_json({"type": "mode", "mode": "walk", "controller": "bogus"})
        assert _receive_type(socket, "error")["code"] == "INVALID_COMMAND"
        frame = _receive_type(socket, "frame")
        assert frame["walk_controller"] == "raibert"
        assert frame["mode"] == "stand"

        socket.send_json({"type": "mode", "mode": "walk", "controller": "rl"})
        assert _receive_type(socket, "error")["code"] == "RL_LOAD_FAILED"
        frame = _receive_type(socket, "frame")
        assert frame["walk_controller"] == "raibert"
        assert frame["mode"] == "stand"
