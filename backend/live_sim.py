"""即時互動模擬 session：MuJoCo forward contact simulation + 控制器 + 指令處理。

指令（WebSocket JSON）：
- {"type":"push","dir":[x,y,z],"force":N,"duration":s}  對軀幹施加外力
- {"type":"obstacle","dist":m,"height":m,"depth":m}     於機器人前方放障礙物
- {"type":"mode","mode":"stand"|"walk"}                 站立平衡 / 行走
- {"type":"speed","value":0.05~1.0}                     模擬速度倍率（慢動作）
- {"type":"pause","on":bool} / {"type":"step","dt":s}   暫停 / 單步前進
- {"type":"gait", ...GaitParams 欄位}                    更新步態參數
- {"type":"reset"}                                      重置
"""

import numpy as np
import mujoco
from pydantic import ValidationError

from config_schema import (
    MAX_OBSTACLES, GaitParams, Obstacle, RobotConfig, validate_live_command,
    validate_robot_gait_compatibility,
)
from model_builder import make_model, geom_render_list, JOINT_ORDER, pelvis_height
from gait import GaitEngine
from controller import BalanceController
from controller_raibert import RaibertController
from run_trace import RunTraceRecorder, TRACE_STORE, TraceIntegrityError
from motion_tasks import MotionTaskRunner, get_motion_task

DT = 0.002


def validation_error_message(exc: ValidationError) -> str:
    """產生不含整份 input payload 的精簡驗證訊息。"""
    err = exc.errors(include_input=False)[0]
    loc = ".".join(str(p) for p in err.get("loc", ()))
    return f"{loc}: {err['msg']}" if loc else err["msg"]


def live_error(code: str, message: str) -> dict:
    return {"type": "error", "code": code, "message": message}


class LiveSession:
    def __init__(self, cfg: RobotConfig, gait: GaitParams, obstacles: list[Obstacle]):
        self.cfg = cfg
        self.gait = gait
        # reset 必須回到 init scenario；使用 deep snapshot 避免 caller/runtime mutation。
        self._initial_obstacles: tuple[Obstacle, ...] = tuple(
            ob.model_copy(deep=True) for ob in obstacles
        )
        self.obstacles: list[Obstacle] = [
            ob.model_copy(deep=True) for ob in self._initial_obstacles
        ]
        self.speed = 0.25                 # 預設慢動作，方便觀察決策
        self.assist_balance = True        # 輔助平衡（虛擬護具）：行走時輕扶軀幹姿態
        self.startup_assist_enabled = True  # track controller 起步外力；assist=false 時一併關閉
        self._balance_assist_active = False
        self._startup_assist_active = False
        self.walk_controller = "raibert"  # track | raibert | rl | rl_task_v2 | rl_task_v5
        self.paused = False
        self.mode = "stand"
        self.sim_t = 0.0
        self.gait_t = 0.0
        self.anchor = 0.0                 # 世界座標 = 步態引擎座標 + anchor
        self.push: tuple[np.ndarray, float] | None = None   # (力向量, 結束時間)
        self.push_info: dict | None = None
        self._carry = 0.0
        self._last_reanchor = 0.0
        self.trace_recorder: RunTraceRecorder | None = None
        self.last_trace_receipt: dict | None = None
        self.trace_error: dict | None = None
        self.motion_task: MotionTaskRunner | None = None
        self.last_task_result: dict | None = None
        self.task_error: dict | None = None
        self._build(reset_state=True)

    # ---------------- 模型 / 引擎建構 ----------------

    def _engine_obstacles(self, anchor: float | None = None) -> list[Obstacle]:
        """世界座標障礙物 → 步態引擎座標（引擎從 x=0 開始規劃）。"""
        origin = self.anchor if anchor is None else anchor
        return [Obstacle(x=ob.x - origin, depth=ob.depth,
                         height=ob.height, width=ob.width) for ob in self.obstacles]

    def _build(self, reset_state: bool):
        keep = None
        if not reset_state and hasattr(self, "data"):
            keep = (self.data.qpos.copy(), self.data.qvel.copy())
        self.model = make_model(self.cfg, self.obstacles, dynamic=True)
        self.data = mujoco.MjData(self.model)
        self.engine = GaitEngine(self.cfg, self.gait, self._engine_obstacles())
        lean = np.deg2rad(self.gait.torso_lean_deg)
        # 控制器保留決策日誌（重建模型不清空歷史）
        old = getattr(self, "controller", None)
        self.controller = self._make_controller(lean)
        if old is not None:
            self.controller.decisions = old.decisions
            self.controller._decide_last = old._decide_last
            self.controller.t = old.t
            self.controller.state = old.state
            self.controller._v_filt = old._v_filt
        if keep is not None:
            self.data.qpos[:] = keep[0]
            self.data.qvel[:] = keep[1]
        else:
            self._init_standing()
        mujoco.mj_forward(self.model, self.data)

    def _make_controller(self, lean: float, kind: str | None = None):
        """依 walk_controller 種類建立控制器（STAND/FALLEN 行為皆相同）。"""
        selected = kind or self.walk_controller
        if selected == "raibert":
            return RaibertController(self.model, self.cfg, self.gait, lean)
        if selected == "rl":
            from controller_rl import RLWalkController
            return RLWalkController(self.model, self.cfg, self.gait, lean)
        if selected == "rl_task_v2":
            from controller_rl import RLTaskController
            return RLTaskController(self.model, self.cfg, self.gait, lean)
        if selected == "rl_task_v5":
            from controller_rl import RLPhaseTaskController
            return RLPhaseTaskController(self.model, self.cfg, self.gait, lean)
        if selected == "track":
            return BalanceController(self.model, self.cfg, self.engine, lean)
        raise ValueError(f"unsupported controller: {selected}")

    def _init_standing(self):
        self.data.qpos[:] = 0
        self.data.qpos[2] = pelvis_height(self.cfg, 0.10) + 0.004
        self.data.qpos[3] = 1.0
        self.data.qpos[7:] = self.controller.stand_q
        self.data.qvel[:] = 0
        self.sim_t = 0.0
        self.gait_t = 0.0
        self.anchor = 0.0
        self.controller.state = "STAND"
        self.mode = "stand"

    # ---------------- 指令 ----------------

    def command(self, msg: dict) -> str | dict | None:
        """回傳 "scene" 表示場景已重建（前端需重新載入 geom）。"""
        try:
            command = validate_live_command(msg)
        except ValidationError as exc:
            return live_error("INVALID_COMMAND", validation_error_message(exc))
        payload = command.model_dump(exclude_none=True)
        t = payload.pop("type")
        if self.motion_task is not None and self.motion_task.active:
            if t == "task_cancel":
                return self.cancel_motion_task()
            if t not in {"pause", "speed", "step"}:
                return live_error(
                    "TASK_ACTIVE_LOCKED",
                    f"正式任務進行中不可執行 {t}；僅允許 pause、speed、step 或 task_cancel",
                )
        if t == "task_start":
            return self.start_motion_task(payload["task_id"])
        if t == "task_cancel":
            return live_error("TASK_NOT_ACTIVE", "目前沒有 active motion task")
        if self.trace_recorder is not None and self.trace_recorder.active:
            identity_mutation = t in {"obstacle", "gait", "reset"}
            identity_mutation = identity_mutation or (
                t == "mode" and payload.get("controller") not in (None, self.walk_controller)
            )
            if identity_mutation:
                return live_error(
                    "TRACE_IDENTITY_LOCKED",
                    f"recording active 時不可執行 {t}；請先 record_stop",
                )
        if t == "record_start":
            return self.start_recording(
                label=payload.get("label", ""),
                max_duration_s=float(payload["max_duration_s"]),
            )
        if t == "record_stop":
            return self.stop_recording()
        if t == "push":
            d = np.array(payload["dir"], dtype=float)
            n = np.linalg.norm(d)
            d = d / n
            force = float(payload["force"])
            dur = float(payload["duration"])
            self.push = (d * force, self.sim_t + dur)
            self.push_info = {"dir": d.tolist(), "force": force}
            self.controller.decide("push_cmd", f"👊 外力施加：{force:.0f} N，方向 ({d[0]:+.1f},{d[1]:+.1f},{d[2]:+.1f})，{dur:.2f} s", "impact", 0)
            return None
        if t == "obstacle":
            if len(self.obstacles) >= MAX_OBSTACLES:
                return live_error(
                    "OBSTACLE_LIMIT_REACHED",
                    f"obstacle 上限為 {MAX_OBSTACLES}；command 未執行，scene 保持不變",
                )
            px = float(self.data.qpos[0])
            ob = Obstacle(x=px + float(payload["dist"]),
                          height=float(payload["height"]),
                          depth=float(payload["depth"]),
                          width=1.2)
            self.obstacles.append(ob)
            self.controller.decide("obs", f"🧱 臨時加入障礙物：前方 {payload['dist']:.1f} m，高 {ob.height:.2f} m — 重新規劃步態", "event", 0)
            self._reanchor()
            self._build(reset_state=False)
            return "scene"
        if t == "mode":
            new_mode = payload["mode"]
            kind = payload.get("controller")
            if kind and kind != self.walk_controller:
                # 先完整建立候選控制器；失敗時不得改 label、mode 或舊 controller。
                old = self.controller
                try:
                    candidate = self._make_controller(
                        np.deg2rad(self.gait.torso_lean_deg), kind=kind,
                    )
                except Exception as exc:
                    code = "RL_LOAD_FAILED" if kind.startswith("rl") else "CONTROLLER_LOAD_FAILED"
                    return live_error(code, f"{kind} controller 載入失敗：{type(exc).__name__}")
                candidate.decisions = old.decisions
                candidate._decide_last = old._decide_last
                candidate.t = old.t
                candidate._v_filt = old._v_filt
                candidate.state = old.state if old.state == "FALLEN" else "STAND"
                self.controller = candidate
                self.walk_controller = kind
                labels = {
                    "track": "軌跡追蹤（開環時序）",
                    "raibert": "Raibert 閉環",
                    "rl": "RL legacy 學習策略",
                    "rl_task_v2": "RL curriculum-v2 任務策略",
                    "rl_task_v5": "RL phase-observable-v5 任務策略",
                }
                self.controller.decide("ctrl_switch", f"🔁 行走控制器切換：{labels.get(self.walk_controller, kind)}", "event", 0)
                self.mode = "stand"     # 換控制器後回站立，再由下方切走
            self._set_mode_internal(new_mode)
            return None
        if t == "speed":
            self.speed = float(payload["value"])
            return None
        if t == "pause":
            self.paused = payload["on"]
            return None
        if t == "step":
            self._advance_sim(float(payload["dt"]))
            return None
        if t == "gait":
            if not payload:
                return None
            if self.walk_controller.startswith("rl"):
                fields = ", ".join(sorted(payload))
                return live_error(
                    "RUNTIME_GAIT_UNSUPPORTED",
                    f"RL policy 使用固定訓練 gait contract；runtime fields [{fields}] 未支援，session 未變更",
                )
            try:
                new_gait = GaitParams.model_validate({**self.gait.model_dump(), **payload})
            except ValidationError as exc:
                return live_error("INVALID_COMMAND", validation_error_message(exc))
            try:
                validate_robot_gait_compatibility(self.cfg, new_gait)
            except ValueError as exc:
                return live_error("ROBOT_GAIT_INCOMPATIBLE", str(exc))
            # 先完整建立候選 engine；任何失敗都不改 gait/anchor/controller。
            candidate_anchor = self.anchor
            if self.mode == "walk":
                candidate_anchor = float(self.data.qpos[0]) - self.engine.base_x(self.gait_t)
            try:
                candidate_engine = GaitEngine(
                    self.cfg, new_gait, self._engine_obstacles(anchor=candidate_anchor),
                )
            except Exception as exc:
                return live_error("GAIT_UPDATE_FAILED", f"runtime gait 建構失敗：{type(exc).__name__}")
            self.gait = new_gait
            self.anchor = candidate_anchor
            self.engine = candidate_engine
            self.controller.update_gait(new_gait, candidate_engine)
            if self.mode == "walk":
                self.gait_t = 0.0
                self.controller.decide("gait", "⚙️ 步態參數更新，重新規劃", "event", 0)
            return None
        if t == "assist":
            enabled = payload["on"]
            self.assist_balance = enabled
            self.startup_assist_enabled = enabled
            if not enabled:
                self._balance_assist_active = False
                self._startup_assist_active = False
            state = "開啟" if enabled else "關閉"
            self.controller.decide("assist_toggle", f"🛡️ 外加平衡與起步輔助{state}", "event", 0)
            return None
        if t == "reset":
            self.obstacles = [ob.model_copy(deep=True) for ob in self._initial_obstacles]
            self.push = None
            self.push_info = None
            self._build(reset_state=True)
            self.controller.decisions.append({"t": 0.0, "text": "🔄 重置", "level": "event"})
            return "scene"
        return live_error("INVALID_COMMAND", "unsupported command")

    # ---------------- Dynamic Run Trace ----------------

    def _set_mode_internal(self, new_mode: str, *, preserve_fall: bool = False) -> None:
        """Apply a mode event after its external command has been validated."""
        if new_mode == "walk" and self.mode != "walk":
            self.mode = "walk"
            self.gait_t = 0.0
            self._reanchor()
            self.engine = GaitEngine(self.cfg, self.gait, self._engine_obstacles())
            if not (preserve_fall and self.controller.state == "FALLEN"):
                self.controller.set_mode("walk", self.engine)
        elif new_mode == "stand" and self.mode != "stand":
            self.mode = "stand"
            if not (preserve_fall and self.controller.state == "FALLEN"):
                self.controller.set_mode("stand")

    def apply_motion_action(self, action: dict, *, preserve_fall: bool = False) -> None:
        """Dispatch a validated Motion Task primitive without exposing raw session methods."""
        action_type = action.get("type")
        if action_type == "set_mode":
            self._set_mode_internal(str(action["mode"]), preserve_fall=preserve_fall)
            return
        if action_type == "hold":
            return
        raise ValueError(f"unsupported motion action: {action_type}")

    def start_recording(
        self,
        *,
        label: str,
        max_duration_s: float,
        group_id: str | None = None,
        source_mode: str = "live",
        task_id: str | None = None,
        task_contract: dict | None = None,
        task_phase_events: list[dict] | None = None,
    ) -> dict:
        if self.trace_recorder is not None and self.trace_recorder.active:
            return live_error("TRACE_ALREADY_RECORDING", "目前已有 active recording")
        policy_id = getattr(self.controller, "policy_id", None)
        policy_status = getattr(self.controller, "policy_evidence_status", None)
        self.trace_recorder = RunTraceRecorder(
            model=self.model,
            config=self.cfg.model_dump(mode="json"),
            gait=self.gait.model_dump(mode="json"),
            obstacles=[item.model_dump(mode="json") for item in self.obstacles],
            controller=self.walk_controller,
            policy_id=policy_id,
            policy_evidence_status=policy_status,
            assist_enabled=bool(self.assist_balance or self.startup_assist_enabled),
            sim_t=self.sim_t,
            physics_dt=DT,
            max_duration_s=max_duration_s,
            label=label,
            group_id=group_id,
            source_mode=source_mode,
            task_id=task_id,
            task_contract=task_contract,
            task_phase_events=task_phase_events,
        )
        self.trace_error = None
        return {
            "type": "trace_recording_started",
            "trace": self.recording_status(),
        }

    def recording_status(self) -> dict:
        recorder = self.trace_recorder
        if recorder is None:
            return {"active": False}
        return {
            "active": bool(recorder.active),
            "run_id": recorder.run_id,
            "group_id": recorder.group_id,
            "sample_count": recorder.count,
            "elapsed_s": round(max(self.sim_t - recorder.sim_t_start, 0.0), 3),
            "max_duration_s": recorder.max_duration_s,
        }

    def _finalize_recording(self, stop_reason: str) -> dict:
        recorder = self.trace_recorder
        if recorder is None or not recorder.active:
            raise TraceIntegrityError("no active recording")
        receipt = TRACE_STORE.finalize(
            recorder,
            stop_reason=stop_reason,
            decisions=list(self.controller.decisions),
        )
        self.last_trace_receipt = receipt
        return receipt

    def stop_recording(self) -> dict:
        if self.trace_recorder is None or not self.trace_recorder.active:
            return live_error("TRACE_NOT_RECORDING", "目前沒有 active recording")
        if self.trace_recorder.count == 0:
            return live_error("TRACE_EMPTY", "尚未完成任何 physics step，recording 保持 active")
        try:
            receipt = self._finalize_recording("user_stop")
        except Exception as exc:
            self.trace_error = live_error("TRACE_FINALIZE_FAILED", type(exc).__name__)
            return self.trace_error
        return {"type": "trace_ready", "trace": receipt}

    # ---------------- Motion Task ----------------

    def _motion_task_candidate(
        self,
        task_id: str,
        *,
        group_id: str | None = None,
        source_mode: str = "live",
    ) -> "LiveSession":
        """Build a complete candidate so a failed controller load cannot mutate this session."""
        contract = get_motion_task(task_id)
        target_gait = GaitParams.model_validate({
            **self.gait.model_dump(mode="json"),
            **contract["gait"],
            "duration": contract["duration_s"],
        })
        validate_robot_gait_compatibility(self.cfg, target_gait)
        candidate = LiveSession(
            self.cfg.model_copy(deep=True),
            target_gait,
            [],
        )
        if self.walk_controller != candidate.walk_controller:
            switched = candidate.command({
                "type": "mode", "mode": "stand", "controller": self.walk_controller,
            })
            if isinstance(switched, dict) and switched.get("type") == "error":
                raise RuntimeError(switched.get("code", "TASK_CONTROLLER_PREPARE_FAILED"))
        candidate.speed = self.speed
        candidate.paused = False
        candidate.assist_balance = False
        candidate.startup_assist_enabled = False
        candidate.push = None
        candidate.push_info = None
        candidate.controller.t = 0.0
        candidate.controller._v_filt[:] = 0.0
        runner = MotionTaskRunner(contract, started_sim_t=candidate.sim_t, group_id=group_id)
        candidate.motion_task = runner
        started = candidate.start_recording(
            label=task_id,
            max_duration_s=float(contract["duration_s"]) + 0.5,
            group_id=group_id,
            source_mode=source_mode,
            task_id=task_id,
            task_contract=contract,
            task_phase_events=runner.phase_events,
        )
        if started.get("type") == "error":
            raise RuntimeError(started.get("code", "TASK_TRACE_START_FAILED"))
        candidate.controller.decide(
            "motion_task",
            f"🧪 正式任務開始：{contract['name']}；固定 gait、assist OFF、障礙物清除",
            "event",
            0,
        )
        return candidate

    def start_motion_task(
        self,
        task_id: str,
        *,
        group_id: str | None = None,
        source_mode: str = "live",
    ) -> dict:
        if self.motion_task is not None and self.motion_task.active:
            return live_error("TASK_ALREADY_ACTIVE", "目前已有 active motion task")
        if self.trace_recorder is not None and self.trace_recorder.active:
            return live_error("TRACE_ALREADY_RECORDING", "請先停止目前 Dynamic Run Trace")
        try:
            candidate = self._motion_task_candidate(
                task_id, group_id=group_id, source_mode=source_mode,
            )
        except KeyError:
            return live_error("UNKNOWN_TASK", f"未知 motion task：{task_id}")
        except Exception as exc:
            return live_error("TASK_PREPARE_FAILED", type(exc).__name__)
        self.__dict__.clear()
        self.__dict__.update(candidate.__dict__)
        return {
            "type": "task_started",
            "task": self.motion_task_status(),
            "scene": self.scene(),
        }

    def motion_task_status(self) -> dict:
        if self.motion_task is None:
            return {"active": False}
        return self.motion_task.status(self.sim_t)

    def _complete_motion_task_if_due(self) -> None:
        runner = self.motion_task
        if runner is None or not runner.active:
            return
        if runner.elapsed(self.sim_t) + 0.5 * DT < float(runner.contract["duration_s"]):
            return
        runner.active = False
        try:
            receipt = self._finalize_recording("task_complete")
            self.last_task_result = receipt.get("task")
        except Exception as exc:
            self.task_error = live_error("TASK_FINALIZE_FAILED", type(exc).__name__)

    def cancel_motion_task(self) -> dict:
        runner = self.motion_task
        if runner is None or not runner.active:
            return live_error("TASK_NOT_ACTIVE", "目前沒有 active motion task")
        runner.active = False
        if self.trace_recorder is None or self.trace_recorder.count == 0:
            self.abort_recording()
            self.last_task_result = {
                "task_id": runner.task_id,
                "contract": runner.contract,
                "phase_events": runner.phase_events,
                "evaluation": {"status": "CANCELLED", "criteria": [], "evaluated_samples": 0},
            }
        else:
            try:
                receipt = self._finalize_recording("task_cancelled")
                self.last_task_result = receipt.get("task")
            except Exception as exc:
                self.task_error = live_error("TASK_FINALIZE_FAILED", type(exc).__name__)
                return self.task_error
        return {"type": "task_cancelled", "task": self.last_task_result}

    def abort_recording(self) -> None:
        if self.trace_recorder is not None:
            self.trace_recorder.active = False
        self.trace_recorder = None

    def _reanchor(self):
        """把步態引擎座標原點對齊目前機器人位置（漂移補償）。"""
        if self.mode == "walk" and hasattr(self, "engine"):
            self.anchor = float(self.data.qpos[0]) - self.engine.base_x(self.gait_t)
        else:
            self.anchor = float(self.data.qpos[0])

    # ---------------- 模擬推進 ----------------

    def advance(self, wall_dt: float):
        if self.paused:
            self._balance_assist_active = False
            self._startup_assist_active = False
            return
        self._advance_sim(wall_dt * self.speed)

    def _advance_sim(self, sim_dt: float):
        self._balance_assist_active = False
        self._startup_assist_active = False
        self._carry += sim_dt
        n = int(self._carry / DT)
        self._carry -= n * DT
        trunk = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "trunk")
        for _ in range(min(n, 600)):
            if self.motion_task is not None and self.motion_task.active:
                self.motion_task.apply_due_transitions(self)
            self.data.xfrc_applied[trunk] = 0
            # 起步輔助：僅「軌跡追蹤」控制器需要（開環參考不自洽的
            # bootstrap 問題）；閉環控制器自己會起步
            if (self.mode == "walk" and self.controller.state == "WALK"
                    and self.walk_controller == "track" and self.startup_assist_enabled):
                tw = self.controller.t - getattr(self.controller, "_walk_start_t", self.controller.t)
                if tw < 2.5:
                    self._startup_assist_active = True
                    fade = 1.0 - min(tw / 2.5, 1.0)
                    v_des = self.gait.speed * self.controller.walk_alpha()
                    f_assist = float(np.clip(300.0 * (v_des - self.controller._v_filt[0]), -40.0, 160.0)) * fade
                    self.data.xfrc_applied[trunk, 0] += f_assist
                    self.controller.decide("assist", "🤝 起步輔助中：漸退的前向扶持力協助建立動量", "event", 2.0)
            # 輔助平衡（虛擬護具）：行走時對軀幹施加姿態穩定力矩。
            # 這是外加輔助（如實驗室吊架/護具），非機器人自身能力 —
            # 介面明示狀態，可關閉觀察目前 simulated plant 在未施加外加
            # assist 時的反應；此結果不代表實體硬體能力。
            if (self.assist_balance and self.mode == "walk"
                    and self.controller.state == "WALK"):
                self._balance_assist_active = True
                from controller import quat_to_pitch_roll
                pitch, roll = quat_to_pitch_roll(self.data.qpos[3:7])
                lean = np.deg2rad(self.gait.torso_lean_deg)
                ty = float(np.clip(-140.0 * (pitch - lean) - 30.0 * self.data.qvel[4], -70, 70))
                tx = float(np.clip(-140.0 * roll - 30.0 * self.data.qvel[3], -70, 70))
                self.data.xfrc_applied[trunk, 3] += tx
                self.data.xfrc_applied[trunk, 4] += ty
            if self.push is not None:
                F, t_end = self.push
                if self.sim_t < t_end:
                    self.data.xfrc_applied[trunk, 0:3] = F
                else:
                    self.push = None
                    self.push_info = None
            tau = self.controller.compute(self.data, self.gait_t, DT)
            self.data.ctrl[:] = tau
            mujoco.mj_step(self.model, self.data)
            self.sim_t += DT
            if self.trace_recorder is not None and self.trace_recorder.active:
                reached_cap = self.trace_recorder.record_step(
                    data=self.data,
                    controller=self.controller,
                    engine=self.engine,
                    gait_t=self.gait_t,
                )
                if reached_cap:
                    try:
                        self._finalize_recording("duration_cap")
                    except Exception as exc:
                        self.trace_error = live_error("TRACE_FINALIZE_FAILED", type(exc).__name__)
            if self.controller.is_locomoting():
                # 步態時鐘：混合慢啟動 + 實際速度回授（落後時參考不跑掉）
                self.gait_t += DT * self.controller.gait_clock_rate()
            self._complete_motion_task_if_due()
        # 行走漂移補償（僅軌跡追蹤控制器需要；閉環控制器不用預排計畫）
        if (self.mode == "walk" and self.walk_controller == "track"
                and self.sim_t - self._last_reanchor > 1.0):
            self._last_reanchor = self.sim_t
            drift = float(self.data.qpos[0]) - self.anchor - self.engine.base_x(self.gait_t)
            if abs(drift) > 0.10 and self.controller.state == "WALK":
                self._reanchor()
                self.engine = GaitEngine(self.cfg, self.gait, self._engine_obstacles())
                self.controller.engine = self.engine
                self.controller.decide("drift", f"📍 里程漂移 {drift*100:+.0f} cm，步態座標重新對齊", "event", 2.0)

    # ---------------- 輸出 ----------------

    def scene(self) -> dict:
        return {
            "type": "scene",
            "geoms": geom_render_list(self.model),
            "body_names": [mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_BODY, b)
                           for b in range(1, self.model.nbody)],
        }

    def frame(self) -> dict:
        d = self.data
        tel = self.controller.telemetry(d)
        return {
            "type": "frame",
            "t": round(self.sim_t, 3),
            "mode": self.mode,
            "walk_controller": self.walk_controller,
            "speed": self.speed,
            "paused": self.paused,
            "assist_enabled": bool(self.assist_balance or self.startup_assist_enabled),
            "interventions": {
                "balance_assist_enabled": bool(self.assist_balance),
                "startup_assist_active": bool(self._startup_assist_active),
                "external_push_active": self.push is not None,
            },
            "xpos": np.round(d.xpos[1:], 4).tolist(),
            "xquat": np.round(d.xquat[1:], 4).tolist(),
            "ctrl": tel,
            "push": self.push_info,
            "decisions": self.controller.decisions[-30:],
            "joints": {
                "q": np.round(d.qpos[7:], 3).tolist(),
                "tau": np.round(d.actuator_force, 1).tolist(),
            },
            "recording": self.recording_status(),
            "last_trace": self.last_trace_receipt,
            "trace_error": self.trace_error,
            "motion_task": self.motion_task_status(),
            "last_task": self.last_task_result,
            "task_error": self.task_error,
        }
