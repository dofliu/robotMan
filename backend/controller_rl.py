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
from rl.policy_registry import resolve_policy

CTRL_SUBSTEPS = 10          # 50 Hz 推論（物理 500 Hz）


def find_model_path():
    """相容既有 caller；實際解析由 registry 與 SHA-256 gate 控制。"""
    _, path = resolve_policy()
    return path


class RLWalkController(BalanceController):
    blend_T = 0.4

    def __init__(self, model, cfg: RobotConfig, gait: GaitParams, lean: float):
        super().__init__(model, cfg, None, lean)
        from stable_baselines3 import PPO
        policy_record, path = resolve_policy()
        self.policy = PPO.load(str(path), device="cpu")
        self.model_name = path.stem
        self.policy_id = policy_record.policy_id
        self.policy_evidence_status = policy_record.evidence_status
        self.policy_contract = policy_record.gait_contract

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
            self.state = "STAND"
            self.decide("mode", "🧍 切換至站立平衡模式", "mode", 0)

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
        if self.state != "WALK":
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

        tau = self.kp * (self._q_target - q) - self.kd * qd + 0.8 * data.qfrc_bias[6:]
        return np.clip(tau, -self.tau_lim, self.tau_lim)
