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
from controller import quat_to_pitch_roll
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
        self.action_interface_id = "DIRECT_NORMALIZED_ACTION_LEGACY_V1"

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

    def _process_action(self, action) -> tuple[np.ndarray, np.ndarray]:
        """Validate once, then return requested/applied normalized actions.

        Shape and finite-value checks are fail-closed because silently
        broadcasting or forwarding NaN into MuJoCo would make a retained run
        impossible to interpret.
        """
        requested = np.asarray(action, dtype=np.float64)
        if requested.shape != (len(JOINT_ORDER),):
            raise ValueError(f"ACTION_SHAPE_INVALID:{requested.shape}")
        if not np.all(np.isfinite(requested)):
            raise ValueError("ACTION_NONFINITE")
        requested = np.clip(requested, -1.0, 1.0)
        return requested, requested.copy()

    def action_interface_contract(self) -> dict:
        return {
            "action_interface_id": self.action_interface_id,
            "action_scale_rad": [float(value) for value in self.act_scale],
            "low_pass_alpha": None,
            "rate_limit_normalized_per_control_step": None,
            "previous_action_semantics": "PREVIOUS_APPLIED_NORMALIZED_ACTION",
        }

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
        _, action = self._process_action(action)
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


class HumanoidMotionTaskEnv(HumanoidWalkEnv):
    """Command-conditioned start/stop curriculum using a frozen Motion Task timeline.

    This environment has a different 48-D observation contract from the legacy
    walk-only policy: the final scalar is normalized commanded forward speed.
    A resulting checkpoint therefore requires a separate controller adapter and
    registry record; it cannot replace the current 47-D policy by filename.
    """

    def __init__(
        self,
        *,
        task_id: str = "stand_start_walk_stop_v1",
        command_action_envelope: bool = False,
        velocity_reward_weight: float = 0.6,
        progress_reward_weight: float = 0.0,
        reverse_penalty_weight: float = 0.0,
        **kwargs,
    ):
        from motion_tasks import get_motion_task

        self.task_contract = get_motion_task(task_id)
        self.task_id = task_id
        self.command_action_envelope = bool(command_action_envelope)
        self.velocity_reward_weight = float(velocity_reward_weight)
        self.progress_reward_weight = float(progress_reward_weight)
        self.reverse_penalty_weight = float(reverse_penalty_weight)
        kwargs["episode_s"] = float(self.task_contract["duration_s"])
        super().__init__(**kwargs)
        self.rl_stand_q = self.stand_q.copy()
        self.static_stand_q = self._static_stand_pose()
        self.command_speed = 0.0
        self.task_elapsed_s = 0.0
        self.observation_space = spaces.Box(
            -np.inf, np.inf, (self.observation_space.shape[0] + 1,), np.float64,
        )

    def _static_stand_pose(self) -> np.ndarray:
        """與 Live BalanceController 一致的對稱微蹲站姿。"""
        hip = np.array([0.0, self.engine.hw, self.z_nom])
        ankle = np.array([0.0, self.engine.hw, self.engine.ankle_h])
        _, hip_pitch, knee, ankle_pitch = self.engine.leg_ik(hip, ankle, 0.0)
        pose = np.zeros(len(JOINT_ORDER))
        for side in ("l", "r"):
            pose[JOINT_ORDER.index(f"hip_pitch_{side}")] = hip_pitch
            pose[JOINT_ORDER.index(f"knee_{side}")] = knee
            pose[JOINT_ORDER.index(f"ankle_{side}")] = ankle_pitch
            pose[JOINT_ORDER.index(f"shoulder_{side}")] = 0.05
            pose[JOINT_ORDER.index(f"elbow_{side}")] = 0.35
        return pose

    def _command_at(self, elapsed_s: float) -> tuple[float, str]:
        """Return smooth speed command and frozen phase ID at simulation time."""
        phase = next(
            (item for item in self.task_contract["phases"]
             if item["start_s"] <= elapsed_s < item["end_s"]),
            self.task_contract["phases"][-1],
        )
        phase_id = str(phase["id"])
        if phase_id in {"INITIAL_STAND", "FINAL_STAND"}:
            return 0.0, phase_id
        if phase_id == "START":
            u = np.clip(
                (elapsed_s - phase["start_s"]) / (phase["end_s"] - phase["start_s"]),
                0.0,
                1.0,
            )
            blend = u * u * (3.0 - 2.0 * u)
            return float(self.v_des * blend), phase_id
        if phase_id == "STOP":
            u = np.clip(
                (elapsed_s - phase["start_s"]) / (phase["end_s"] - phase["start_s"]),
                0.0,
                1.0,
            )
            blend = u * u * (3.0 - 2.0 * u)
            return float(self.v_des * (1.0 - blend)), phase_id
        return float(self.v_des), phase_id

    def _obs(self) -> np.ndarray:
        base = super()._obs()
        normalized = self.command_speed / max(self.v_des, 1e-6)
        return np.concatenate([base, np.array([normalized])])

    def reset(self, *, seed=None, options=None):
        gym.Env.reset(self, seed=seed)
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[:] = 0.0
        self.data.qpos[2] = self.z_nom + 0.004
        self.data.qpos[3] = 1.0
        self.data.qpos[7:] = (
            self.static_stand_q if self.command_action_envelope else self.stand_q
        )
        self.data.qvel[:] = 0.0
        self.data.qpos[7:] += self.np_random.uniform(-0.01, 0.01, 12)
        mujoco.mj_forward(self.model, self.data)
        self.step_count = 0
        self.phase = 0.0
        self.prev_action = np.zeros(12)
        self.task_elapsed_s = 0.0
        self.command_speed, self.command_phase = self._command_at(0.0)
        return self._obs(), {
            "command_vx": self.command_speed,
            "command_phase": self.command_phase,
        }

    def step(self, action):
        previous_action = self.prev_action.copy()
        requested_action, action = self._process_action(action)
        command_scale_before_step = self.command_speed / max(self.v_des, 1e-6)
        gait_q_target = self.rl_stand_q + action * self.act_scale
        q_target = (
            self.static_stand_q
            + command_scale_before_step * (gait_q_target - self.static_stand_q)
            if self.command_action_envelope else gait_q_target
        )
        saturation_substeps_over_threshold = 0
        saturation_excess_sq_sum = 0.0
        for _ in range(SUBSTEPS):
            q = self.data.qpos[7:]
            qd = self.data.qvel[6:]
            tau = self.kp * (q_target - q) - self.kd * qd + 0.8 * self.data.qfrc_bias[6:]
            if self.command_action_envelope:
                # 站立時仍需主動 ankle/hip balance；若只把 gait action 歸零，
                # nominal pose 本身無法抵抗前後倒立擺的不穩定性。
                balance_scale = 1.0 - command_scale_before_step
                pitch, roll = quat_to_pitch_roll(self.data.qpos[3:7])
                ankle_corr = float(np.clip(
                    -95.0 * (self.data.qvel[0] - self.command_speed), -55.0, 35.0,
                ))
                hip_corr = float(np.clip(
                    280.0 * pitch + 60.0 * self.data.qvel[4], -80.0, 80.0,
                ))
                roll_corr = float(np.clip(
                    -150.0 * roll - 45.0 * self.data.qvel[3], -45.0, 45.0,
                ))
                for side in ("l", "r"):
                    tau[JOINT_ORDER.index(f"ankle_{side}")] += balance_scale * ankle_corr
                    tau[JOINT_ORDER.index(f"hip_pitch_{side}")] += balance_scale * hip_corr
                    tau[JOINT_ORDER.index(f"hip_roll_{side}")] += balance_scale * roll_corr
            self.data.ctrl[:] = np.clip(tau, -self.tau_lim, self.tau_lim)
            mujoco.mj_step(self.model, self.data)
            # Motion Task 的正式 gate 使用 500 Hz trace；這裡同步保留每個
            # physics substep，避免 50 Hz evaluator 系統性漏掉短暫 torque peaks。
            tau_ratio_substep = (
                np.abs(self.data.actuator_force) / np.maximum(self.tau_lim, 1e-6)
            )
            saturation_substeps_over_threshold += int(
                np.max(tau_ratio_substep) >= 0.95
            )
            saturation_excess = np.clip(
                (tau_ratio_substep - 0.80) / 0.20, 0.0, 1.0,
            )
            saturation_excess_sq_sum += float(np.mean(saturation_excess ** 2))

        self.task_elapsed_s += CTRL_DT
        self.command_speed, self.command_phase = self._command_at(self.task_elapsed_s)
        clock_scale = self.command_speed / max(self.v_des, 1e-6)
        self.phase = (self.phase + CTRL_DT * clock_scale / self.T_cycle) % 1.0
        self.step_count += 1

        d = self.data
        R = np.zeros(9)
        mujoco.mju_quat2Mat(R, d.qpos[3:7])
        up_z = R.reshape(3, 3)[2, 2]
        fallen = up_z < 0.5 or d.qpos[2] < 0.45 * self.z_nom

        q_ref_walk, qd_ref_walk = self._ref_at_phase()
        command_scale = self.command_speed / max(self.v_des, 1e-6)
        stand_reference = (
            self.static_stand_q if self.command_action_envelope else self.stand_q
        )
        q_ref = stand_reference + command_scale * (q_ref_walk - stand_reference)
        qd_ref = command_scale * qd_ref_walk
        pose_err = np.mean((d.qpos[7:] - q_ref) ** 2)
        vel_err = np.mean((d.qvel[6:] - qd_ref) ** 2)
        r_imitate = 0.6 * np.exp(-5.0 * pose_err) + 0.1 * np.exp(-0.05 * vel_err)
        r_vel = self.velocity_reward_weight * np.exp(
            -4.0 * (d.qvel[0] - self.command_speed) ** 2
        )
        r_progress = self.progress_reward_weight * command_scale * float(
            np.clip(d.qvel[0] / max(self.v_des, 1e-6), -1.0, 1.2)
        )
        r_alive = 0.3
        r_upright = 0.2 * np.exp(-5.0 * (1.0 - up_z))
        r_stop = 0.35 * np.exp(-8.0 * d.qvel[0] ** 2) if self.command_speed < 0.1 else 0.0
        tau_n = self.data.ctrl / np.maximum(self.tau_lim, 1e-6)
        p_energy = 0.02 * float(np.mean(tau_n ** 2))
        p_rate = 0.05 * float(np.mean((action - self.prev_action) ** 2))
        p_side = 0.15 * abs(d.qvel[1])
        p_reverse = (
            self.reverse_penalty_weight * command_scale * max(-float(d.qvel[0]), 0.0)
        )
        reward = (
            r_imitate + r_vel + r_progress + r_alive + r_upright + r_stop
            - p_energy - p_rate - p_side - p_reverse
        )
        if fallen:
            reward -= 5.0

        self.prev_action = action
        terminated = bool(fallen)
        truncated = self.step_count >= self.max_steps
        return self._obs(), float(reward), terminated, truncated, {
            "x": float(d.qpos[0]),
            "vx": float(d.qvel[0]),
            "command_vx": float(self.command_speed),
            "command_phase": self.command_phase,
            "saturation_substeps_over_threshold": saturation_substeps_over_threshold,
            "saturation_substeps_total": SUBSTEPS,
            "saturation_excess_sq_mean_500hz": saturation_excess_sq_sum / SUBSTEPS,
            "action_interface_id": self.action_interface_id,
            "requested_action": requested_action.tolist(),
            "applied_action": action.tolist(),
            "joint_target_rad": q_target.tolist(),
            "applied_action_delta_l2": float(np.linalg.norm(action - previous_action)),
            "requested_applied_delta_l2": float(
                np.linalg.norm(requested_action - action)
            ),
        }


class HumanoidMotionTaskCurriculumEnv(HumanoidMotionTaskEnv):
    """Warm-start-friendly task environment with a command action envelope.

    The envelope preserves a learned full-speed gait at command=1 while making
    command=0 resolve to the nominal stand pose.  Forward progress and reverse
    motion are then explicit optimization terms instead of being hidden behind
    survival reward.
    """

    def __init__(self, **kwargs):
        super().__init__(
            command_action_envelope=True,
            velocity_reward_weight=1.2,
            progress_reward_weight=0.35,
            reverse_penalty_weight=0.8,
            **kwargs,
        )


class HumanoidMotionTaskPathEfficiencyEnv(HumanoidMotionTaskCurriculumEnv):
    """加入可觀測 path error 與 actuator saturation penalty 的 v3 環境。

    v2 observation 沒有 world-frame heading 或 lateral position，因此 policy
    可維持直立與前進，卻無法判斷是否已偏離目標路徑。v3 額外提供 normalized
    lateral error 與 yaw error，讓「沿指定方向走」成為可觀測的控制問題。
    """

    LATERAL_SCALE_M = 0.30

    def _path_state(self) -> tuple[float, float]:
        quat = self.data.qpos[3:7]
        w, x, y, z = (float(item) for item in quat)
        yaw = float(np.arctan2(
            2.0 * (w * z + x * y),
            1.0 - 2.0 * (y * y + z * z),
        ))
        lateral = float(self.data.qpos[1])
        return lateral, yaw

    def _obs(self) -> np.ndarray:
        base = super()._obs()
        lateral, yaw = self._path_state()
        path_obs = np.array([
            np.clip(lateral / self.LATERAL_SCALE_M, -5.0, 5.0),
            np.clip(yaw / np.pi, -1.0, 1.0),
        ])
        return np.concatenate([base, path_obs])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.observation_space = spaces.Box(
            -np.inf, np.inf, (self.observation_space.shape[0] + 2,), np.float64,
        )

    def step(self, action):
        observation, reward, terminated, truncated, info = super().step(action)
        lateral, yaw = self._path_state()
        lateral_velocity = float(self.data.qvel[1])
        yaw_rate = float(self.data.qvel[5])
        tau_ratio = np.abs(self.data.actuator_force) / np.maximum(self.tau_lim, 1e-6)
        saturation_excess = np.clip((tau_ratio - 0.80) / 0.20, 0.0, 1.0)

        # 權重在 DEV profile 中固定；正式 V3 study 前仍需 preregistration。
        p_lateral = 0.80 * min((lateral / self.LATERAL_SCALE_M) ** 2, 9.0)
        p_heading = 0.60 * (1.0 - np.cos(yaw))
        p_lateral_velocity = 0.25 * abs(lateral_velocity)
        p_yaw_rate = 0.10 * abs(yaw_rate)
        p_saturation = 0.50 * float(np.mean(saturation_excess ** 2))
        reward -= (
            p_lateral + p_heading + p_lateral_velocity + p_yaw_rate + p_saturation
        )
        info.update({
            "lateral_y": lateral,
            "lateral_vy": lateral_velocity,
            "yaw_rad": yaw,
            "yaw_rate_rps": yaw_rate,
            "max_torque_ratio": float(np.max(tau_ratio)),
        })
        return observation, float(reward), terminated, truncated, info


class HumanoidMotionTaskPathStopEnv(HumanoidMotionTaskPathEfficiencyEnv):
    """v4：保留 path correction，對 STOP/FINAL transition 加強穩定代價。"""

    def step(self, action):
        observation, reward, terminated, truncated, info = super().step(action)
        phase = info.get("command_phase")
        if phase in {"STOP", "FINAL_STAND"}:
            pitch, roll = quat_to_pitch_roll(self.data.qpos[3:7])
            forward_speed = float(self.data.qvel[0])
            pose_error = float(np.mean((self.data.qpos[7:] - self.static_stand_q) ** 2))
            reward -= (
                2.0 * forward_speed ** 2
                + 0.8 * (pitch ** 2 + roll ** 2)
                + 0.8 * pose_error
            )
        if terminated:
            # v3 只扣 5，4M 時仍可用高 return 掩蓋末段跌倒；v4 明確提高代價。
            reward -= 45.0
        return observation, float(reward), terminated, truncated, info


class HumanoidMotionTaskPhaseObservableEnv(HumanoidMotionTaskPathStopEnv):
    """v5：加入 signed command trend，區分相同速度下的 START 與 STOP。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.observation_space = spaces.Box(
            -np.inf, np.inf, (self.observation_space.shape[0] + 1,), np.float64,
        )

    def _obs(self) -> np.ndarray:
        base = super()._obs()
        phase = getattr(self, "command_phase", "INITIAL_STAND")
        trend = 1.0 if phase == "START" else -1.0 if phase == "STOP" else 0.0
        return np.concatenate([base, np.array([trend])])


class HumanoidMotionTaskSubstepSaturationEnv(HumanoidMotionTaskPhaseObservableEnv):
    """v6：以 500 Hz substep saturation 統計加入明示 actuator-load 代價。"""

    def step(self, action):
        observation, reward, terminated, truncated, info = super().step(action)
        duty_fraction = (
            float(info["saturation_substeps_over_threshold"])
            / max(float(info["saturation_substeps_total"]), 1.0)
        )
        # 這是 development profile 的 frozen objective；同時處罰越過 95%
        # 的時間比例與 80% 以上的超額幅度，直接對齊正式 500 Hz gate。
        reward -= (
            1.50 * duty_fraction
            + 0.75 * float(info["saturation_excess_sq_mean_500hz"])
        )
        info["saturation_duty_fraction_500hz"] = duty_fraction
        return observation, float(reward), terminated, truncated, info


class _HumanoidMotionTaskV7ActionInterfaceEnv(
    HumanoidMotionTaskSubstepSaturationEnv
):
    """Common v7 reward/observation with one frozen action transform."""

    PILOT_ARM_ID: str

    def __init__(self, **kwargs):
        from rl.action_interface_v7 import resolve_v7_action_interface

        self.v7_action_interface = resolve_v7_action_interface(self.PILOT_ARM_ID)
        super().__init__(**kwargs)
        self.action_interface_id = self.v7_action_interface.interface_id
        self.act_scale = np.asarray(
            self.v7_action_interface.action_scale_rad,
            dtype=np.float64,
        )

    def _process_action(self, action) -> tuple[np.ndarray, np.ndarray]:
        return self.v7_action_interface.transform(action, self.prev_action)

    def action_interface_contract(self) -> dict:
        return {
            "pilot_arm_id": self.v7_action_interface.arm_id,
            "action_interface_id": self.v7_action_interface.interface_id,
            "action_scale_rad": list(self.v7_action_interface.action_scale_rad),
            "low_pass_alpha": self.v7_action_interface.low_pass_alpha,
            "rate_limit_normalized_per_control_step": (
                self.v7_action_interface.rate_limit_per_step
            ),
            "previous_action_semantics": "PREVIOUS_APPLIED_NORMALIZED_ACTION",
        }


class HumanoidMotionTaskRewardOnlyV7Env(_HumanoidMotionTaskV7ActionInterfaceEnv):
    """V7A：v6 500 Hz reward with the unchanged direct action interface."""

    PILOT_ARM_ID = "V7A_REWARD_ONLY"


class HumanoidMotionTaskReducedJointEnvelopeV7Env(
    _HumanoidMotionTaskV7ActionInterfaceEnv
):
    """V7B：v6 reward plus the frozen reduced per-joint target envelope."""

    PILOT_ARM_ID = "V7B_REDUCED_JOINT_ENVELOPE"


class HumanoidMotionTaskFilteredActionV7Env(
    _HumanoidMotionTaskV7ActionInterfaceEnv
):
    """V7C：v6 reward plus observable low-pass and rate-limited action."""

    PILOT_ARM_ID = "V7C_FILTERED_ACTION"
