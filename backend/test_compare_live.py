"""Development-only 三 controller 同步比較 contract tests。"""

import pytest
from fastapi.testclient import TestClient

from compare_live import CONTROLLERS, CompareSession
from config_schema import GaitParams, default_robot
from live_sim import LiveSession
from main import app


@pytest.fixture
def lightweight_rl(monkeypatch):
    """隔離 comparison contract；PPO artifact load 另由真實 smoke 驗證。"""
    original = LiveSession._make_controller

    def make_controller(self, lean, kind=None):
        if kind == "rl" or (kind is None and self.walk_controller == "rl"):
            return original(self, lean, kind="raibert")
        return original(self, lean, kind)

    monkeypatch.setattr(LiveSession, "_make_controller", make_controller)


def new_compare() -> CompareSession:
    return CompareSession(default_robot(), GaitParams(), [])


def test_compare_uses_three_fixed_controllers_and_independent_plants(lightweight_rl):
    comparison = new_compare()

    assert tuple(comparison.sessions) == CONTROLLERS
    assert [comparison.sessions[kind].walk_controller for kind in CONTROLLERS] == list(CONTROLLERS)
    assert len({id(comparison.sessions[kind].model) for kind in CONTROLLERS}) == 3
    assert len({id(comparison.sessions[kind].data) for kind in CONTROLLERS}) == 3
    assert all(comparison.sessions[kind].assist_balance is False for kind in CONTROLLERS)
    assert all(comparison.sessions[kind].startup_assist_enabled is False for kind in CONTROLLERS)

    scene = comparison.scene()
    assert scene["controllers"] == list(CONTROLLERS)
    assert scene["plant_isolation"] is True
    assert scene["assist_default"] is False
    assert scene["evidence_scope"] == "DEVELOPMENT_COMPARISON_ONLY"
    assert scene["plant_signature"].startswith("sha256:")


def test_compare_shared_commands_keep_sim_time_and_interventions_synchronized(lightweight_rl):
    comparison = new_compare()
    assert comparison.command({"type": "mode", "mode": "walk"}) is None
    assert comparison.command({"type": "speed", "value": 0.5}) is None
    comparison.advance(0.04)
    frame = comparison.frame()

    assert frame["sync"] == {
        "max_time_skew_s": 0.0,
        "same_input": True,
        "independent_plants": True,
    }
    assert {item["walk_controller"] for item in frame["frames"].values()} == set(CONTROLLERS)
    assert {item["t"] for item in frame["frames"].values()} == {0.02}
    assert {item["speed"] for item in frame["frames"].values()} == {0.5}
    assert all(item["assist_enabled"] is False for item in frame["frames"].values())

    assert comparison.command({
        "type": "push", "dir": [1, 0, 0], "force": 125, "duration": 0.2,
    }) is None
    pushed = comparison.frame()["frames"]
    assert {item["push"]["force"] for item in pushed.values()} == {125.0}


@pytest.mark.parametrize(
    "message,code",
    [
        ({"type": "speed", "value": "0.5"}, "INVALID_COMPARE_COMMAND"),
        ({"type": "gait", "speed": 0.8}, "UNSUPPORTED_COMPARE_COMMAND"),
        ({"type": "obstacle", "dist": 1.0}, "UNSUPPORTED_COMPARE_COMMAND"),
        ({"type": "mode", "mode": "walk", "controller": "rl"}, "FIXED_COMPARE_CONTROLLER"),
    ],
)
def test_invalid_or_unsupported_compare_commands_do_not_mutate_sessions(lightweight_rl, message, code):
    comparison = new_compare()
    before = {
        kind: (
            comparison.sessions[kind].speed,
            comparison.sessions[kind].mode,
            comparison.sessions[kind].walk_controller,
            comparison.sessions[kind].sim_t,
        )
        for kind in CONTROLLERS
    }

    error = comparison.command(message)

    assert error["type"] == "error"
    assert error["code"] == code
    assert before == {
        kind: (
            comparison.sessions[kind].speed,
            comparison.sessions[kind].mode,
            comparison.sessions[kind].walk_controller,
            comparison.sessions[kind].sim_t,
        )
        for kind in CONTROLLERS
    }


def test_compare_reset_preserves_controller_identity_and_assist_off(lightweight_rl):
    comparison = new_compare()
    comparison.command({"type": "mode", "mode": "walk"})
    comparison.advance(0.04)

    assert comparison.command({"type": "reset"}) == "scene"

    for kind in CONTROLLERS:
        session = comparison.sessions[kind]
        assert session.walk_controller == kind
        assert session.mode == "stand"
        assert session.sim_t == 0.0
        assert session.assist_balance is False
        assert session.startup_assist_enabled is False


def test_compare_init_fails_closed_when_rl_controller_cannot_load(monkeypatch):
    original = LiveSession._make_controller

    def fail_rl(self, lean, kind=None):
        if kind == "rl":
            raise FileNotFoundError("test checkpoint absent")
        return original(self, lean, kind)

    monkeypatch.setattr(LiveSession, "_make_controller", fail_rl)
    with pytest.raises(RuntimeError, match="rl controller init failed"):
        new_compare()


def test_compare_websocket_exposes_scene_frame_and_rejects_controller_switch(lightweight_rl):
    client = TestClient(app)
    with client.websocket_connect("/ws/compare") as socket:
        socket.send_json({
            "type": "init",
            "robot": default_robot().model_dump(mode="json"),
            "gait": GaitParams().model_dump(mode="json"),
            "obstacles": [],
        })
        scene = socket.receive_json()
        assert scene["type"] == "compare_scene"
        assert scene["controllers"] == list(CONTROLLERS)

        frame = socket.receive_json()
        assert frame["type"] == "compare_frame"
        assert frame["sync"]["max_time_skew_s"] == 0.0

        socket.send_json({"type": "mode", "mode": "walk", "controller": "rl"})
        while True:
            message = socket.receive_json()
            if message["type"] == "error":
                break
        assert message["code"] == "FIXED_COMPARE_CONTROLLER"
