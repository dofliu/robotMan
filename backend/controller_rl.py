"""RL 學習策略行走控制器（路線二：強化學習）。

載入 PPO 訓練出的策略（rl/ppo_walk_final.zip，或最新 checkpoint），
以 50 Hz 推論關節目標角，PD 轉扭矩（與訓練環境完全一致的介面）。
站立/跌倒行為沿用基底控制器。

注意：觀測建構必須與 rl/humanoid_env.py 完全一致（鏡像實作）。
"""

import numpy as np
import mujoco
from config_schema import RobotConfig, GaitParams
from controller import BalanceController, quat_to_pitch_roll
from gait import GaitEngine
from model_builder import JOINT_ORDER
from rl.policy_registry import resolve_policy

CTRL_SUBSTEPS = 10          # 50 Hz 推論（物理 500 Hz）


def find_model_path(policy_id: str | None = None):
    """相容既有 caller；實際解析由 registry 與 SHA-256 gate 控制。"""
    _, path = resolve_policy(policy_id)
    return path


class RLWalkController(BalanceController):
    blend_T = 0.4

    def __init__(
        self,
        model,
        cfg: RobotConfig,
        gait: GaitParams,
        lean: float,
        *,
        policy_id: str | None = None,
    ):
        super().__init__(model, cfg, None, lean)
        from stable_baselines3 import PPO
        policy_record, path = resolve_policy(policy_id)
        self.policy = PPO.load(str(path), device="cpu")
        policy_obs_dim = int(self.policy.observation_space.shape[0])
        if policy_obs_dim != policy_record.observation_contract.dimension:
            raise ValueError(
                f"policy observation mismatch: registry={policy_record.observation_contract.dimension}, "
                f"artifact={policy_obs_dim}"
            )
        self.model_name = path.stem
        self.policy_id = policy_record.policy_id
        self.policy_evidence_status = policy_record.evidence_status
        self.policy_contract = policy_record.gait_contract
        self.observation_contract = policy_record.observation_contract
        self.runtime_adapter = policy_record.runtime_adapter

        # reference gait 由 versioned registry contract 決定，不再由 runtime
        # controller 內隱式硬編碼。
        contract = self.policy_contract
        ref_gait = GaitParams(mode=contract.mode, speed=contract.speed_mps,
                              step_length=contract.step_length_m, duty=contract.duty,
                              clearance=contract.clearance_m, duration=4.0)
        eng = GaitEngine(cfg, ref_gait, [])
        self.T_cycle = eng.T
        self.act_scale = np.array([0.5, 0.8, 0.9, 0.6] * 2 + [0.6, 0.6] * 2)
        # 站姿基準用參考步態關節角的週期平均（與訓練環境一致）
        n = 50
        refq = np.stack([eng.qpos_at(eng.T + i * eng.T / n, model.nq)[7:] for i in range(n)])
        self.rl_stand_q = refq.mean(axis=0)

        self.phase = 0.0
        self.prev_action = np.zeros(12)
        self._q_target = self.stand_q.copy()
        self._substep = 0

    def set_mode(self, mode: str, engine=None):
        if mode == "walk":
            self.state = "WALK"
            self._stop_start_t = None
            self._walk_start_t = self.t
            self.phase = 0.0
            self.prev_action = np.zeros(12)
            self._substep = 0
            self.decide(
                "mode",
                f"🚶 RL 學習策略行走（policy {self.policy_id}，訓練速度 "
                f"{self.policy_contract.speed_mps:.1f} m/s）",
                "mode", 0,
            )
        else:
            super().set_mode("stand")

    def update_gait(self, gait: GaitParams, engine) -> None:
        """目前 policy 使用固定訓練 gait contract，不接受 runtime 改值。"""
        raise RuntimeError("RL_RUNTIME_GAIT_UPDATE_UNSUPPORTED")

    def _obs(self, data) -> np.ndarray:
        """鏡像 rl/humanoid_env.py 的觀測建構。"""
        q = data.qpos[7:] - self.rl_stand_q
        qd = data.qvel[6:]
        R = np.zeros(9)
        mujoco.mju_quat2Mat(R, data.qpos[3:7])
        R = R.reshape(3, 3)
        grav_local = R.T @ np.array([0.0, 0.0, -1.0])
        ang_vel = data.qvel[3:6]
        lin_vel = R.T @ data.qvel[0:3]
        ph = np.array([np.sin(2 * np.pi * self.phase), np.cos(2 * np.pi * self.phase)])
        return np.concatenate([q, qd * 0.1, grav_local, ang_vel * 0.25,
                               lin_vel, ph, self.prev_action])

    def compute(self, data: mujoco.MjData, t_gait: float, dt: float) -> np.ndarray:
        self._complete_stop_if_due()
        if not self.is_locomoting():
            return super().compute(data, t_gait, dt)

        self.t += dt
        q = data.qpos[7:]
        qd = data.qvel[6:]
        pitch, roll = quat_to_pitch_roll(data.qpos[3:7])
        if abs(pitch) > 0.95 or abs(roll) > 0.95 or data.qpos[2] < 0.45 * self.z_nom:
            self.state = "FALLEN"
            self.decide("fall", f"💥 跌倒！pitch {np.degrees(pitch):.0f}° / roll {np.degrees(roll):.0f}° — 進入阻尼癱軟", "fall", 0)
            return -1.5 * qd

        self._v_filt += 0.2 * (data.qvel[0:3] - self._v_filt)

        # 50 Hz 推論（每 10 個物理步一次）
        if self._substep % CTRL_SUBSTEPS == 0:
            action, _ = self.policy.predict(self._obs(data), deterministic=True)
            action = np.clip(np.asarray(action, dtype=np.float64), -1, 1)
            self._q_target = self.rl_stand_q + action * self.act_scale
            self.prev_action = action
            self.phase = (self.phase + CTRL_SUBSTEPS * dt / self.T_cycle) % 1.0
        self._substep += 1

        # Frozen policy 沒有 stop command observation；以明示的 hybrid transition
        # 將 policy joint target 平滑收斂至站姿。若機體仍有明顯前進速度，
        # 保留較多 policy stepping，避免雙腳過早併回站姿而失去 capture step。
        stop_scale = self.stop_scale()
        velocity_guard = float(np.clip(abs(self._v_filt[0]) / 0.7, 0.0, 1.0))
        pose_scale = max(stop_scale, velocity_guard) if self.state == "STOPPING" else 1.0
        q_target = pose_scale * self._q_target + (1.0 - pose_scale) * self.stand_q
        tau = self.kp * (q_target - q) - self.kd * qd + 0.8 * data.qfrc_bias[6:]

        if self.state == "STOPPING":
            # Policy 本身未受過 stop command 訓練，因此加上明示的 contact-aware
            # ankle/hip braking layer；只經由關節扭矩作用於 simulated plant。
            contact_l, contact_r = self._foot_contacts(data)
            v_des = self.policy_contract.speed_mps * stop_scale
            self.ankle_corr = float(np.clip(-95.0 * (self._v_filt[0] - v_des), -55.0, 35.0))
            lean_target = self.lean + float(
                np.clip(0.40 * (v_des - self._v_filt[0]), -0.18, 0.10)
            )
            pitch_err = pitch - lean_target
            self.hip_corr = float(
                np.clip(160.0 * pitch_err + 100.0 * data.qvel[4], -70.0, 70.0)
            )
            self.roll_corr = float(
                np.clip(-150.0 * roll - 45.0 * data.qvel[3], -45.0, 45.0)
            )
            for side, contact in (("l", contact_l), ("r", contact_r)):
                if not contact:
                    continue
                tau[JOINT_ORDER.index(f"ankle_{side}")] += self.ankle_corr
                tau[JOINT_ORDER.index(f"hip_pitch_{side}")] += self.hip_corr
                tau[JOINT_ORDER.index(f"hip_roll_{side}")] += self.roll_corr
        return np.clip(tau, -self.tau_lim, self.tau_lim)


class RLTaskController(RLWalkController):
    """48-D command-conditioned curriculum-v2 的獨立 Live adapter。

    這個 adapter 刻意不覆寫 legacy controller identity。它把 Motion Task
    state machine 的 smooth start/stop 轉成 policy 最後一維的 normalized
    forward-speed command，並鏡像 training environment 的 action envelope
    與低速 active-balance layer。
    """

    POLICY_ID = "stand_start_walk_stop_0p7_curriculum_v2"
    RUNTIME_ADAPTER = "motion_task_command_envelope_v2"
    OBSERVATION_CONTRACT_ID = "motion_task_command_48d_v1"
    blend_T = 1.5

    def __init__(self, model, cfg: RobotConfig, gait: GaitParams, lean: float):
        super().__init__(
            model,
            cfg,
            gait,
            lean,
            policy_id=self.POLICY_ID,
        )
        if self.runtime_adapter != self.RUNTIME_ADAPTER:
            raise ValueError(f"unsupported runtime adapter: {self.runtime_adapter}")
        if self.observation_contract.contract_id != self.OBSERVATION_CONTRACT_ID:
            raise ValueError(
                f"unsupported observation contract: {self.observation_contract.contract_id}"
            )
        self._held_command_scale = 0.0
        self.command_speed = 0.0

    def _obs(self, data) -> np.ndarray:
        base = super()._obs(data)
        return np.concatenate([base, np.array([self._held_command_scale])])

    def _target_from_action(self, action: np.ndarray, command_scale: float) -> np.ndarray:
        """鏡像 HumanoidMotionTaskCurriculumEnv 的 command action envelope。"""
        gait_q_target = self.rl_stand_q + action * self.act_scale
        return self.stand_q + command_scale * (gait_q_target - self.stand_q)

    def gait_clock_rate(self) -> float:
        # LiveSession 的 external gait clock 只用於 trace/reference；policy 使用內部 phase。
        return float(self._held_command_scale)

    def compute(self, data: mujoco.MjData, t_gait: float, dt: float) -> np.ndarray:
        self.t += dt
        self._complete_stop_if_due()
        q = data.qpos[7:]
        qd = data.qvel[6:]
        pitch, roll = quat_to_pitch_roll(data.qpos[3:7])
        if abs(pitch) > 0.95 or abs(roll) > 0.95 or data.qpos[2] < 0.45 * self.z_nom:
            self.state = "FALLEN"
            self.decide(
                "fall",
                f"💥 跌倒！pitch {np.degrees(pitch):.0f}° / roll {np.degrees(roll):.0f}° — 進入阻尼癱軟",
                "fall",
                0,
            )
            return -1.5 * qd

        self._v_filt += 0.2 * (data.qvel[0:3] - self._v_filt)

        # 與 50 Hz training step 一致：command、observation、action target 在十個
        # 500 Hz physics substeps 期間保持不變。
        if self._substep % CTRL_SUBSTEPS == 0:
            self._held_command_scale = float(self.walk_alpha())
            self.command_speed = self.policy_contract.speed_mps * self._held_command_scale
            action, _ = self.policy.predict(self._obs(data), deterministic=True)
            action = np.clip(np.asarray(action, dtype=np.float64), -1, 1)
            self._q_target = self._target_from_action(action, self._held_command_scale)
            self.prev_action = action
            self.phase = (
                self.phase
                + CTRL_SUBSTEPS * dt * self._held_command_scale / self.T_cycle
            ) % 1.0
        self._substep += 1

        tau = self.kp * (self._q_target - q) - self.kd * qd + 0.8 * data.qfrc_bias[6:]

        # 訓練環境在 command 接近零時仍使用 ankle/hip feedback；否則只是把
        # gait action 乘零，站姿會成為不受控的倒立擺。
        balance_scale = 1.0 - self._held_command_scale
        if balance_scale > 0.0:
            contact_l, contact_r = self._foot_contacts(data)
            self.ankle_corr = float(np.clip(
                -95.0 * (data.qvel[0] - self.command_speed), -55.0, 35.0,
            ))
            self.hip_corr = float(np.clip(
                280.0 * pitch + 60.0 * data.qvel[4], -80.0, 80.0,
            ))
            self.roll_corr = float(np.clip(
                -150.0 * roll - 45.0 * data.qvel[3], -45.0, 45.0,
            ))
            for side, contact in (("l", contact_l), ("r", contact_r)):
                if not contact:
                    continue
                tau[JOINT_ORDER.index(f"ankle_{side}")] += balance_scale * self.ankle_corr
                tau[JOINT_ORDER.index(f"hip_pitch_{side}")] += balance_scale * self.hip_corr
                tau[JOINT_ORDER.index(f"hip_roll_{side}")] += balance_scale * self.roll_corr

        return np.clip(tau, -self.tau_lim, self.tau_lim)


class RLPhaseTaskController(RLTaskController):
    """51-D v5 Live adapter：加入 path error、heading error 與 task phase trend。"""

    POLICY_ID = "stand_start_walk_stop_0p7_phase_observable_v5"
    RUNTIME_ADAPTER = "motion_task_phase_observable_v5"
    OBSERVATION_CONTRACT_ID = "motion_task_phase_observable_51d_v1"

    def _phase_trend(self) -> float:
        """鏡像 frozen task：START=+1、STOP=-1，其餘 phase=0。"""
        if self.state == "STOPPING":
            return -1.0
        if self.state == "WALK":
            elapsed = self.t - getattr(self, "_walk_start_t", self.t)
            if elapsed < self.blend_T - 1e-9:
                return 1.0
        return 0.0

    def _obs(self, data) -> np.ndarray:
        base = super()._obs(data)
        quat = data.qpos[3:7]
        w, x, y, z = (float(item) for item in quat)
        yaw = float(np.arctan2(
            2.0 * (w * z + x * y),
            1.0 - 2.0 * (y * y + z * z),
        ))
        lateral = float(data.qpos[1])
        path_and_phase = np.array([
            np.clip(lateral / 0.30, -5.0, 5.0),
            np.clip(yaw / np.pi, -1.0, 1.0),
            self._phase_trend(),
        ])
        return np.concatenate([base, path_and_phase])
