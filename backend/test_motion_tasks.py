"""Motion Task V1 contract, execution, comparison, and evaluator tests."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

import live_sim
import main
from compare_live import CONTROLLERS, CompareSession
from config_schema import GaitParams, Obstacle, default_robot
from live_sim import LiveSession
from motion_tasks import TASK_ID, evaluate_motion_task, get_motion_task
from run_trace import RunTraceStore


@pytest.fixture
def trace_store(tmp_path, monkeypatch):
    store = RunTraceStore(tmp_path / "task-traces")
    monkeypatch.setattr(live_sim, "TRACE_STORE", store)
    monkeypatch.setattr(main, "TRACE_STORE", store)
    return store


@pytest.fixture
def lightweight_rl(monkeypatch):
    original = LiveSession._make_controller

    def make_controller(self, lean, kind=None):
        if kind == "rl" or (kind is None and self.walk_controller == "rl"):
            return original(self, lean, kind="raibert")
        return original(self, lean, kind)

    monkeypatch.setattr(LiveSession, "_make_controller", make_controller)


def test_task_contract_is_versioned_and_frozen_by_copy():
    contract = get_motion_task(TASK_ID)
    assert contract["schema_version"] == "MOTION_TASK_V1"
    assert contract["duration_s"] == 9.0
    assert [phase["id"] for phase in contract["phases"]] == [
        "INITIAL_STAND", "START", "STEADY_WALK", "STOP", "FINAL_STAND",
    ]
    assert contract["gait"] == {
        "mode": "walk", "speed": 0.7, "step_length": 0.35,
        "duty": 0.62, "clearance": 0.07,
    }
    contract["gait"]["speed"] = 99
    assert get_motion_task(TASK_ID)["gait"]["speed"] == 0.7


def test_evaluator_reports_deterministic_pass_for_conforming_trace():
    contract = get_motion_task(TASK_ID)
    dt = 0.002
    n = int(contract["duration_s"] / dt)
    relative = np.arange(1, n + 1) * dt
    vx = np.zeros(n)
    vx[(relative >= 1.0) & (relative <= 6.5)] = 0.7
    qpos = np.zeros((n, 19), dtype=float)
    qpos[:, 0] = np.cumsum(vx) * dt
    arrays = {
        "time": relative.copy(),
        "qpos": qpos,
        "com_vel": np.column_stack([vx, np.zeros(n), np.zeros(n)]),
        "pitch_deg": np.zeros(n),
        "roll_deg": np.zeros(n),
        "state_code": np.zeros(n, dtype=np.int8),
        "saturation_pct": np.zeros((n, 6)),
    }
    result = evaluate_motion_task(
        arrays, contract, physics_dt=dt, stop_reason="task_complete",
        assist_enabled_at_start=False,
    )
    assert result["status"] == "PASS"
    assert all(item["passed"] for item in result["criteria"])


def test_live_task_resets_contract_locks_manual_commands_and_finalizes(trace_store):
    session = LiveSession(
        default_robot(), GaitParams(), [Obstacle(x=1.5, depth=0.3, height=0.15, width=1.2)],
    )
    started = session.command({"type": "task_start", "task_id": TASK_ID})
    assert started["type"] == "task_started"
    assert session.gait.speed == 0.7
    assert session.gait.step_length == 0.35
    assert session.obstacles == []
    assert session.assist_balance is False
    assert session.command({"type": "push", "force": 100, "duration": 0.2})["code"] == "TASK_ACTIVE_LOCKED"

    while session.motion_task.active:
        session._advance_sim(0.2)

    assert session.last_task_result is not None
    assert session.last_task_result["evaluation"]["status"] in {"PASS", "FAIL"}
    assert session.last_trace_receipt["task"]["task_id"] == TASK_ID
    assert [event["phase"] for event in session.last_task_result["phase_events"]] == [
        "INITIAL_STAND", "START", "STEADY_WALK", "STOP", "FINAL_STAND",
    ]
    assert {item["id"] for item in session.last_task_result["evaluation"]["criteria"]} == {
        "TRACE_INTEGRITY", "ASSIST_DISABLED", "NO_FALL", "INITIAL_STAND_POSTURE",
        "STEADY_SPEED", "STEADY_PROGRESS", "STOP_SPEED", "FINAL_STAND_POSTURE",
        "FINAL_STATE", "LATERAL_DRIFT", "SATURATION_DUTY",
    }
    loaded = trace_store.load_trace(session.last_trace_receipt["run_id"])
    assert loaded["manifest"]["task"]["evaluation"] == session.last_task_result["evaluation"]


def test_task_cancel_preserves_partial_trace_as_cancelled(trace_store):
    session = LiveSession(default_robot(), GaitParams(), [])
    session.command({"type": "task_start", "task_id": TASK_ID})
    session._advance_sim(0.05)
    cancelled = session.command({"type": "task_cancel"})
    assert cancelled["type"] == "task_cancelled"
    assert cancelled["task"]["evaluation"]["status"] == "CANCELLED"
    assert trace_store.list_traces()[0]["task"]["evaluation"]["status"] == "CANCELLED"


def test_compare_task_uses_shared_contract_and_synchronized_group(trace_store, lightweight_rl):
    comparison = CompareSession(default_robot(), GaitParams(), [])
    comparison.command({"type": "speed", "value": 1.0})
    started = comparison.command({"type": "task_start", "task_id": TASK_ID})
    assert started["type"] == "task_started"
    assert {item["group_id"] for item in started["tasks"].values()} == {started["group_id"]}
    assert all(comparison.sessions[kind].gait.speed == 0.7 for kind in CONTROLLERS)

    while comparison.sessions["track"].motion_task.active:
        comparison.advance(0.2)

    assert not any(comparison.sessions[kind].motion_task.active for kind in CONTROLLERS)
    results = [comparison.sessions[kind].last_task_result for kind in CONTROLLERS]
    assert {result["task_id"] for result in results} == {TASK_ID}
    assert len(trace_store.list_traces()) == 3
    assert {item["group_id"] for item in trace_store.list_traces()} == {started["group_id"]}


def test_live_websocket_starts_task_rebuilds_scene_and_returns_cancelled_trace(trace_store):
    client = TestClient(main.app)
    with client.websocket_connect("/ws/live") as socket:
        socket.send_json({
            "type": "init",
            "robot": default_robot().model_dump(mode="json"),
            "gait": GaitParams().model_dump(mode="json"),
            "obstacles": [],
        })
        while socket.receive_json()["type"] != "scene":
            pass
        socket.send_json({"type": "task_start", "task_id": TASK_ID})
        while True:
            message = socket.receive_json()
            if message["type"] == "task_started":
                break
        assert message["task"]["phase"] == "INITIAL_STAND"
        assert message["scene"]["type"] == "scene"
        while True:
            message = socket.receive_json()
            if message["type"] == "frame" and message["recording"]["sample_count"] > 0:
                break
        socket.send_json({"type": "task_cancel"})
        while True:
            message = socket.receive_json()
            if message["type"] == "task_cancelled":
                break
        assert message["task"]["evaluation"]["status"] == "CANCELLED"
