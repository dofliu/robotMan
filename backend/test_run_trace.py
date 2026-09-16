"""Dynamic Run Trace V1 recorder, integrity, API, and comparison tests."""

import pytest
from fastapi.testclient import TestClient

import live_sim
import main
from compare_live import CONTROLLERS, CompareSession
from config_schema import GaitParams, default_robot
from live_sim import LiveSession
from run_trace import STATE_CODES, RunTraceStore, TraceIntegrityError


@pytest.fixture
def trace_store(tmp_path, monkeypatch):
    store = RunTraceStore(tmp_path / "traces")
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


def capture_short_trace(store: RunTraceStore) -> tuple[LiveSession, dict]:
    session = LiveSession(default_robot(), GaitParams(), [])
    started = session.command({
        "type": "record_start", "label": "unit walk", "max_duration_s": 2.0,
    })
    assert started["type"] == "trace_recording_started"
    session._advance_sim(0.02)
    ready = session.command({"type": "record_stop"})
    assert ready["type"] == "trace_ready"
    return session, ready["trace"]


def test_trace_state_contract_exposes_controlled_stop():
    assert STATE_CODES == {"STAND": 0, "WALK": 1, "FALLEN": 2, "STOPPING": 3}


def test_live_trace_records_physics_steps_and_validated_artifact(trace_store):
    session, receipt = capture_short_trace(trace_store)
    loaded = trace_store.load_trace(receipt["run_id"], max_points=100)
    manifest = loaded["manifest"]

    assert receipt["sample_count"] == 10
    assert manifest["sample_rate_hz"] == pytest.approx(500.0)
    assert manifest["sample_count"] == 10
    assert manifest["controller"] == "raibert"
    assert manifest["evidence_scope"] == "SOFTWARE_ONLY_MUJOCO_REALIZED_SIMULATION"
    assert manifest["arrays"]["qpos"]["shape"][0] == 10
    assert manifest["arrays"]["tau"]["shape"] == [10, session.model.nu]
    assert loaded["returned_points"] == 10
    assert len(loaded["series"]["joint_tau"]) == 10
    assert loaded["series"]["time"][1] - loaded["series"]["time"][0] == pytest.approx(0.002)


def test_recording_locks_scenario_identity_but_allows_task_events(trace_store):
    session = LiveSession(default_robot(), GaitParams(), [])
    session.command({"type": "record_start", "max_duration_s": 2.0})

    assert session.command({"type": "mode", "mode": "walk"}) is None
    assert session.command({
        "type": "push", "dir": [1, 0, 0], "force": 100.0, "duration": 0.2,
    }) is None
    for command in (
        {"type": "gait", "speed": 0.6},
        {"type": "obstacle", "dist": 1.0},
        {"type": "mode", "mode": "walk", "controller": "track"},
        {"type": "reset"},
    ):
        error = session.command(command)
        assert error["code"] == "TRACE_IDENTITY_LOCKED"
    assert session.trace_recorder.active is True


def test_duration_cap_auto_finalizes_without_unbounded_samples(trace_store):
    session = LiveSession(default_robot(), GaitParams(), [])
    session.command({"type": "record_start", "max_duration_s": 1.0})

    session._advance_sim(1.2)

    assert session.trace_recorder.active is False
    assert session.last_trace_receipt is not None
    assert session.last_trace_receipt["sample_count"] == 500
    assert session.frame()["recording"]["active"] is False
    assert len(trace_store.list_traces()) == 1


def test_empty_or_duplicate_recording_commands_fail_closed(trace_store):
    session = LiveSession(default_robot(), GaitParams(), [])
    assert session.command({"type": "record_stop"})["code"] == "TRACE_NOT_RECORDING"
    assert session.command({"type": "record_start", "max_duration_s": 2.0})["type"] == "trace_recording_started"
    assert session.command({"type": "record_start", "max_duration_s": 2.0})["code"] == "TRACE_ALREADY_RECORDING"
    assert session.command({"type": "record_stop"})["code"] == "TRACE_EMPTY"
    assert session.trace_recorder.active is True


def test_record_start_duration_outside_the_declared_range_is_rejected(trace_store, lightweight_rl):
    """`max_duration_s` 的 `1–60` 值域由命令 schema 強制，live 與 compare 同一條路徑。

    規格 DYNAMIC_RUN_TRACE_SPEC §3 宣告這個值域。它實際由
    `LiveRecordStartCommand` 的 `Field(ge=1.0, le=60.0)` 在
    `validate_live_command()` 強制，因此越界值在抵達 `start_recording()`
    之前就被擋掉——本測試把那件事釘住，避免日後有人把欄位放寬或改走
    未驗證的路徑而沒有人發現。
    """
    session = LiveSession(default_robot(), GaitParams(), [])
    comparison = CompareSession(default_robot(), GaitParams(), [])

    # 越界、非有限值都必須 fail closed，且不得留下 recorder。
    # 兩條路徑用各自的具名 code：live 是 INVALID_COMMAND、compare 是 INVALID_COMPARE_COMMAND。
    for value in (0.0, 0.5, 60.5, 600.0, -1.0, float("inf"), float("nan")):
        for target, expected_code in ((session, "INVALID_COMMAND"), (comparison, "INVALID_COMPARE_COMMAND")):
            rejected = target.command({"type": "record_start", "max_duration_s": value})
            assert rejected["type"] == "error", (value, expected_code)
            assert rejected["code"] == expected_code, (value, rejected["code"])
    assert session.trace_recorder is None
    assert all(item.trace_recorder is None for item in comparison.sessions.values())
    assert trace_store.list_traces() == []

    # 兩個邊界值本身必須是可接受的，否則就不是「1–60」而是更窄的範圍。
    for value in (1.0, 60.0):
        started = session.command({"type": "record_start", "max_duration_s": value})
        assert started["type"] == "trace_recording_started"
        assert session.trace_recorder.max_duration_s == value
        session.command({"type": "record_stop"})
        session.trace_recorder = None


def test_record_start_duration_defaults_to_thirty_when_omitted(trace_store):
    """省略時採規格的預設 30 秒；預設值不得靜默漂移。"""
    session = LiveSession(default_robot(), GaitParams(), [])
    started = session.command({"type": "record_start"})

    assert started["type"] == "trace_recording_started"
    assert session.trace_recorder.max_duration_s == 30.0


def test_trace_hash_tamper_is_rejected(trace_store):
    _, receipt = capture_short_trace(trace_store)
    _, artifact = trace_store._paths(receipt["run_id"])
    raw = bytearray(artifact.read_bytes())
    raw[len(raw) // 2] ^= 0x01
    artifact.write_bytes(raw)

    with pytest.raises(TraceIntegrityError, match="SHA-256 mismatch"):
        trace_store.load_trace(receipt["run_id"])


def test_trace_rest_api_lists_and_returns_bounded_series(trace_store):
    _, receipt = capture_short_trace(trace_store)
    client = TestClient(main.app)

    listing = client.get("/api/traces").json()
    assert listing["traces"][0]["run_id"] == receipt["run_id"]
    response = client.get(f"/api/traces/{receipt['run_id']}?max_points=10")
    assert response.status_code == 200
    assert response.json()["returned_points"] == 10
    assert client.get("/api/traces/invalid").status_code == 409


def test_compare_capture_uses_shared_group_and_synchronized_time(trace_store, lightweight_rl):
    comparison = CompareSession(default_robot(), GaitParams(), [])
    started = comparison.command({
        "type": "record_start", "label": "compare unit", "max_duration_s": 2.0,
    })
    comparison.advance(0.04)
    ready = comparison.command({"type": "record_stop"})

    assert started["type"] == "trace_recording_started"
    assert ready["type"] == "trace_ready"
    assert set(ready["traces"]) == set(CONTROLLERS)
    assert {item["group_id"] for item in ready["traces"].values()} == {ready["group_id"]}
    traces = [trace_store.load_trace(ready["traces"][kind]["run_id"]) for kind in CONTROLLERS]
    assert len({tuple(item["series"]["time"]) for item in traces}) == 1
    assert len(trace_store.list_traces()) == 3


def test_live_websocket_exposes_record_start_and_ready_receipts(trace_store):
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
        socket.send_json({"type": "record_start", "label": "ws", "max_duration_s": 2.0})
        while True:
            message = socket.receive_json()
            if message["type"] == "trace_recording_started":
                run_id = message["trace"]["run_id"]
                break
        while True:
            frame = socket.receive_json()
            if frame["type"] == "frame" and frame["recording"]["sample_count"] > 0:
                break
        socket.send_json({"type": "record_stop"})
        while True:
            message = socket.receive_json()
            if message["type"] == "trace_ready":
                break
        assert message["trace"]["run_id"] == run_id
        assert trace_store.list_traces()[0]["run_id"] == run_id
