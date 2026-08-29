"""RL 訓練環境：人形機器人行走（Gymnasium 介面）。

設計（Unitree/DeepMimic 混合配方）：
- 動作：12 維關節目標角（相對站姿的偏移，PD 轉扭矩，受馬達峰值限制）
- 觀測：關節狀態 + 軀幹姿態/速度 + 步態相位時鐘 + 上一動作（47 維）
- 獎勵：模仿步態引擎參考（DeepMimic-lite）+ 前進速度追蹤 + 存活
  - 模仿參考直接用分析模式的運動學步態 → 收斂快、步態自然
- Reference State Init（RSI）：每回合從參考步態的隨機相位初始化，
  讓策略同時學到步態各階段，是 DeepMimic 收斂的關鍵技巧
- 控制頻率 50 Hz（物理 500 Hz × 10 substeps）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import mujoco
import gymnasium as gym
from gymnasium import spaces

from config_schema import default_robot, GaitParams, RobotConfig
from model_builder import make_model, JOINT_ORDER, JOINT_GROUP, joint_peak_torque, pelvis_height
from gait import GaitEngine

PHYS_DT = 0.002
SUBSTEPS = 10
CTRL_DT = PHYS_DT * SUBSTEPS      # 0.02 s = 50 Hz
G = 9.81


class HumanoidWalkEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, cfg: RobotConfig | None = None, speed: float = 0.7,
                 step_length: float = 0.35, duty: float = 0.62,
                 clearance: float = 0.07, episode_s: float = 10.0):
        super().__init__()
        self.cfg = cfg or default_robot()
        self.gait = GaitParams(speed=speed, step_length=step_length,
                               duty=duty, clearance=clearance, duration=4.0)
        self.v_des = speed
        self.model = make_model(self.cfg, [], dynamic=True)
        self.data = mujoco.MjData(self.model)
        self.max_steps = int(episode_s / CTRL_DT)

        # PD 增益與扭矩上限（與互動模式控制器一致 → 硬體限制生效）
        nj = len(JOINT_ORDER)
        self.kp = np.zeros(nj)
        self.kd = np.zeros(nj)
        self.tau_lim = np.zeros(nj)
        for j, name in enumerate(JOINT_ORDER):
            a = self.cfg.actuators[JOINT_GROUP[name]]
            rated = a.motor.rated_torque * a.gear.ratio * a.gear.efficiency
            self.kp[j] = np.clip(rated * 12.0, 60.0, 900.0)
            self.kd[j] = self.kp[j] * 0.06
            self.tau_lim[j] = joint_peak_torque(self.cfg, name)

        # 參考步態：預先取樣一個完整週期（50 Hz）
        self.engine = GaitEngine(self.cfg, self.gait, [])
        self.T_cycle = self.engine.T
        n_ref = max(int(round(self.T_cycle / CTRL_DT)), 8)
        self.n_ref = n_ref
        self.ref_qpos = np.zeros((n_ref, self.model.nq))
        # 取穩態段（跳過第 1 個週期避免起步暫態）
        for i in range(n_ref):
            self.ref_qpos[i] = self.engine.qpos_at(self.T_cycle + i * CTRL_DT, self.model.nq)
        self.ref_qvel_j = np.gradient(self.ref_qpos[:, 7:], CTRL_DT, axis=0)

        # 站姿（動作偏移的基準）
        self.z_nom = pelvis_height(self.cfg, 0.10)
        self.stand_q = self.ref_qpos[:, 7:].mean(axis=0)

        # 動作縮放：各關節允許偏移（rad）
        self.act_scale = np.array([0.5, 0.8, 0.9, 0.6] * 2 + [0.6, 0.6] * 2)

        obs_dim = 12 + 12 + 3 + 3 + 3 + 2 + 12
        self.observation_space = spaces.Box(-np.inf, np.inf, (obs_dim,), np.float64)
        self.action_space = spaces.Box(-1.0, 1.0, (12,), np.float32)

        self.step_count = 0
        self.phase = 0.0
        self.prev_action = np.zeros(12)
        self.np_random_seeded = False

    # ------------------------------------------------------------------

    def _obs(self) -> np.ndarray:
        d = self.data
        q = d.qpos[7:] - self.stand_q
        qd = d.qvel[6:]
        # 重力方向在軀幹座標系（等效 IMU 姿態）
        R = np.zeros(9)
        mujoco.mju_quat2Mat(R, d.qpos[3:7])
        R = R.reshape(3, 3)
        grav_local = R.T @ np.array([0.0, 0.0, -1.0])
        ang_vel = d.qvel[3:6]
        lin_vel = R.T @ d.qvel[0:3]
        ph = np.array([np.sin(2 * np.pi * self.phase), np.cos(2 * np.pi * self.phase)])
        return np.concatenate([q, qd * 0.1, grav_local, ang_vel * 0.25,
                               lin_vel, ph, self.prev_action])

    def _ref_at_phase(self) -> tuple[np.ndarray, np.ndarray]:
        i = int(self.phase * self.n_ref) % self.n_ref
        return self.ref_qpos[i, 7:], self.ref_qvel_j[i]

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        mujoco.mj_resetData(self.model, self.data)
        # RSI：從參考步態隨機相位初始化
        self.phase = float(self.np_random.uniform(0, 1))
        i = int(self.phase * self.n_ref) % self.n_ref
        qpos = self.ref_qpos[i].copy()
        qpos[0] = 0.0                            # 世界 x 歸零（平移不變）
        qpos[2] += 0.002
        self.data.qpos[:] = qpos
        self.data.qvel[:] = 0
        self.data.qvel[0] = self.v_des           # 給前進初速（符合步態假設）
        self.data.qvel[6:] = self.ref_qvel_j[i]
        # 小雜訊增強韌性
        self.data.qpos[7:] += self.np_random.uniform(-0.03, 0.03, 12)
        mujoco.mj_forward(self.model, self.data)
        self.step_count = 0
        self.prev_action = np.zeros(12)
        return self._obs(), {}

    def step(self, action):
        action = np.clip(np.asarray(action, dtype=np.float64), -1, 1)
        q_target = self.stand_q + action * self.act_scale
        for _ in range(SUBSTEPS):
            q = self.data.qpos[7:]
            qd = self.data.qvel[6:]
            tau = self.kp * (q_target - q) - self.kd * qd + 0.8 * self.data.qfrc_bias[6:]
            self.data.ctrl[:] = np.clip(tau, -self.tau_lim, self.tau_lim)
            mujoco.mj_step(self.model, self.data)
        self.phase = (self.phase + CTRL_DT / self.T_cycle) % 1.0
        self.step_count += 1

        d = self.data
        # 姿態
        R = np.zeros(9)
        mujoco.mju_quat2Mat(R, d.qpos[3:7])
        Rm = R.reshape(3, 3)
        up_z = Rm[2, 2]                          # 軀幹 z 軸與世界 z 的夾角餘弦
        fallen = up_z < 0.5 or d.qpos[2] < 0.45 * self.z_nom

        # --- 獎勵 ---
        q_ref, qd_ref = self._ref_at_phase()
        pose_err = np.mean((d.qpos[7:] - q_ref) ** 2)
        vel_err = np.mean((d.qvel[6:] - qd_ref) ** 2)
        r_imitate = 0.6 * np.exp(-5.0 * pose_err) + 0.1 * np.exp(-0.05 * vel_err)
        r_vel = 0.5 * np.exp(-3.0 * (d.qvel[0] - self.v_des) ** 2)
        r_alive = 0.3
        r_upright = 0.2 * np.exp(-5.0 * (1.0 - up_z))
        tau_n = self.data.ctrl / np.maximum(self.tau_lim, 1e-6)
        p_energy = 0.02 * float(np.mean(tau_n ** 2))
        p_rate = 0.05 * float(np.mean((action - self.prev_action) ** 2))
        p_side = 0.1 * abs(d.qvel[1])            # 側向速度懲罰（直線行走）
        reward = r_imitate + r_vel + r_alive + r_upright - p_energy - p_rate - p_side
        if fallen:
            reward -= 5.0

        self.prev_action = action
        terminated = bool(fallen)
        truncated = self.step_count >= self.max_steps
        return self._obs(), float(reward), terminated, truncated, {
            "x": float(d.qpos[0]), "vx": float(d.qvel[0])}
