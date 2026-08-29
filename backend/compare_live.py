"""三 controller 同輸入、獨立 plant 的 development-only 即時比較。

這裡刻意不把三台機器人放進同一個 MuJoCo world，因為共享 contact
state 或互相碰撞會破壞比較隔離。三個 LiveSession 只共享已驗證命令與
advance 時間增量；它們不共享 model、data 或 controller instance。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from pydantic import ValidationError

from config_schema import GaitParams, Obstacle, RobotConfig, validate_live_command
from live_sim import LiveSession, live_error, validation_error_message


CONTROLLERS = ("track", "raibert", "rl")
SUPPORTED_COMMANDS = frozenset({
    "mode", "push", "speed", "pause", "step", "assist", "reset",
    "record_start", "record_stop", "task_start", "task_cancel",
})


class CompareSession:
    """三個固定 controller 的同步 comparison session。"""

    def __init__(self, cfg: RobotConfig, gait: GaitParams, obstacles: list[Obstacle]):
        self.cfg = cfg.model_copy(deep=True)
        self.gait = gait.model_copy(deep=True)
        self.obstacles = [item.model_copy(deep=True) for item in obstacles]
        self.plant_signature = self._plant_signature()

        # 先在 local candidates 完整建構；RL checkpoint 缺失等錯誤不得留下
        # 半套 comparison state。
        candidates: dict[str, LiveSession] = {}
        for kind in CONTROLLERS:
            session = LiveSession(
                self.cfg.model_copy(deep=True),
                self.gait.model_copy(deep=True),
                [item.model_copy(deep=True) for item in self.obstacles],
            )
            result = session.command({"type": "mode", "mode": "stand", "controller": kind})
            if isinstance(result, dict) and result.get("type") == "error":
                raise RuntimeError(f"{kind} controller init failed: {result.get('code', 'UNKNOWN')}")
            result = session.command({"type": "assist", "on": False})
            if isinstance(result, dict) and result.get("type") == "error":
                raise RuntimeError(f"{kind} assist init failed: {result.get('code', 'UNKNOWN')}")
            candidates[kind] = session
        self.sessions = candidates

    def _plant_signature(self) -> str:
        payload = {
            "robot": self.cfg.model_dump(mode="json"),
            "gait": self.gait.model_dump(mode="json"),
            "obstacles": [item.model_dump(mode="json") for item in self.obstacles],
        }
        raw = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(raw).hexdigest()}"

    def command(self, msg: dict) -> str | dict | None:
        """驗證一次後把同一命令套用至三個 session。

        runtime gait/obstacle 與 controller 切換在第一版刻意 fail closed，
        避免不同 controller contract 造成部分 mutation。
        """
        try:
            command = validate_live_command(msg)
        except ValidationError as exc:
            return live_error("INVALID_COMPARE_COMMAND", validation_error_message(exc))

        payload = command.model_dump(exclude_none=True)
        command_type = payload["type"]
        if command_type not in SUPPORTED_COMMANDS:
            return live_error(
                "UNSUPPORTED_COMPARE_COMMAND",
                f"comparison mode 不支援 runtime {command_type}；請以新 init 套用共同設定",
            )
        if command_type == "mode" and "controller" in payload:
            return live_error(
                "FIXED_COMPARE_CONTROLLER",
                "comparison mode 的 controller identity 固定，mode command 不接受 controller",
            )
        active_recorders = [
            kind for kind in CONTROLLERS
            if self.sessions[kind].trace_recorder is not None
            and self.sessions[kind].trace_recorder.active
        ]
        active_tasks = [
            kind for kind in CONTROLLERS
            if self.sessions[kind].motion_task is not None
            and self.sessions[kind].motion_task.active
        ]
        if command_type == "task_start":
            if active_recorders:
                return live_error("TRACE_ALREADY_RECORDING", "請先停止 comparison recording")
            if active_tasks:
                return live_error("TASK_ALREADY_ACTIVE", "comparison 已有 active motion task")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%S")
            group_id = f"task-{stamp}-{uuid.uuid4().hex[:8]}"
            candidates: dict[str, LiveSession] = {}
            try:
                for kind in CONTROLLERS:
                    candidates[kind] = self.sessions[kind]._motion_task_candidate(
                        payload["task_id"], group_id=group_id, source_mode="compare",
                    )
            except Exception as exc:
                return live_error("COMPARE_TASK_PREPARE_FAILED", type(exc).__name__)
            self.sessions = candidates
            first = self.sessions[CONTROLLERS[0]]
            self.gait = first.gait.model_copy(deep=True)
            self.obstacles = []
            self.plant_signature = self._plant_signature()
            return {
                "type": "task_started",
                "group_id": group_id,
                "plant_signature": self.plant_signature,
                "tasks": {kind: self.sessions[kind].motion_task_status() for kind in CONTROLLERS},
                "scenes": {kind: self.sessions[kind].scene() for kind in CONTROLLERS},
            }
        if command_type == "task_cancel":
            if len(active_tasks) != len(CONTROLLERS):
                return live_error(
                    "COMPARE_TASK_NOT_ACTIVE",
                    "三個 comparison sessions 必須全部處於 active motion task",
                )
            group_id = self.sessions[CONTROLLERS[0]].motion_task.group_id
            results = {kind: self.sessions[kind].cancel_motion_task() for kind in CONTROLLERS}
            failed = [kind for kind, result in results.items() if result.get("type") == "error"]
            if failed:
                return live_error("COMPARE_TASK_CANCEL_FAILED", ",".join(failed))
            return {
                "type": "task_cancelled",
                "group_id": group_id,
                "tasks": {kind: result["task"] for kind, result in results.items()},
            }
        if active_recorders and command_type == "reset":
            return live_error(
                "TRACE_IDENTITY_LOCKED",
                "comparison recording active 時不可 reset；請先 record_stop",
            )
        if command_type == "record_start":
            if active_recorders:
                return live_error("TRACE_ALREADY_RECORDING", "comparison 已有 active recording")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%S")
            group_id = f"compare-{stamp}-{uuid.uuid4().hex[:8]}"
            started: dict[str, dict] = {}
            for kind in CONTROLLERS:
                result = self.sessions[kind].start_recording(
                    label=payload.get("label", ""),
                    max_duration_s=float(payload["max_duration_s"]),
                    group_id=group_id,
                    source_mode="compare",
                )
                if result.get("type") == "error":
                    for previous in started:
                        self.sessions[previous].abort_recording()
                    return live_error(
                        "COMPARE_TRACE_START_FAILED",
                        f"{kind} trace 啟動失敗：{result.get('code', 'UNKNOWN')}",
                    )
                started[kind] = result["trace"]
            return {
                "type": "trace_recording_started",
                "group_id": group_id,
                "traces": started,
            }
        if command_type == "record_stop":
            if len(active_recorders) != len(CONTROLLERS):
                return live_error(
                    "COMPARE_TRACE_NOT_RECORDING",
                    "三個 comparison sessions 必須全部處於 active recording",
                )
            if any(self.sessions[kind].trace_recorder.count == 0 for kind in CONTROLLERS):
                return live_error("TRACE_EMPTY", "尚未完成 physics step，recording 保持 active")
            receipts: dict[str, dict] = {}
            for kind in CONTROLLERS:
                result = self.sessions[kind].stop_recording()
                if result.get("type") == "error":
                    return live_error(
                        "COMPARE_TRACE_STOP_FAILED",
                        f"{kind} trace finalize 失敗：{result.get('code', 'UNKNOWN')}",
                    )
                receipts[kind] = result["trace"]
            return {
                "type": "trace_ready",
                "group_id": next(iter(receipts.values()))["group_id"],
                "traces": receipts,
            }

        results: list[str | dict | None] = []
        for kind in CONTROLLERS:
            result = self.sessions[kind].command(payload)
            if isinstance(result, dict) and result.get("type") == "error":
                # 受支援命令已先通過共同 schema，正常不應進入此分支。保留明確
                # 錯誤，避免後端默默吞掉 divergence。
                return live_error(
                    "COMPARE_COMMAND_FAILED",
                    f"{kind} session 拒絕已驗證命令：{result.get('code', 'UNKNOWN')}",
                )
            results.append(result)
        return "scene" if any(result == "scene" for result in results) else None

    def advance(self, wall_dt: float) -> None:
        for kind in CONTROLLERS:
            self.sessions[kind].advance(wall_dt)

    def scene(self) -> dict:
        return {
            "type": "compare_scene",
            "controllers": list(CONTROLLERS),
            "scenes": {kind: self.sessions[kind].scene() for kind in CONTROLLERS},
            "plant_signature": self.plant_signature,
            "evidence_scope": "DEVELOPMENT_COMPARISON_ONLY",
            "plant_isolation": True,
            "assist_default": False,
        }

    def frame(self) -> dict:
        frames = {kind: self.sessions[kind].frame() for kind in CONTROLLERS}
        times = [float(frames[kind]["t"]) for kind in CONTROLLERS]
        return {
            "type": "compare_frame",
            "t": max(times),
            "frames": frames,
            "sync": {
                "max_time_skew_s": round(max(times) - min(times), 6),
                "same_input": True,
                "independent_plants": True,
            },
        }
