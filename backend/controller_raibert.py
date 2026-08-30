"""Raibert 式閉環行走控制器（路線一：模型式設計）。

與原「軌跡追蹤」控制器的根本差異：
1. 觸地相位重置：步態相位由「實際接觸事件」驅動，不是開環時鐘 —
   每次擺動腳觸地即切換支撐腳並歸零相位，時序誤差不會累積。
2. Raibert 落腳法則（線上計算）：
   落點 = 髖正下方 + v·T/2（中性點）+ k·(v − v_des)（速度誤差回饋）
   側向同理（橫向穩定的關鍵）。
3. 支撐腿任務空間控制：以「量測到的支撐腳位置」為錨點，反解支撐腿
   關節角使骨盆維持目標高度並依目標速度前移 — 姿勢閉環於實際接觸。
"""

import numpy as np
import mujoco
from config_schema import RobotConfig, GaitParams
from model_builder import JOINT_ORDER
from controller import BalanceController, quat_to_pitch_roll, G
from gait import GaitEngine


class RaibertController(BalanceController):
    blend_T = 0.5   # 閉環控制器不需長混合：從站立小步起步本身就自洽

    def __init__(self, model, cfg: RobotConfig, gait: GaitParams, lean: float):
        super().__init__(model, cfg, None, lean)
        self.gait = gait
        # IK 幾何（沿用步態引擎的解析 IK）
        self.ik = GaitEngine(cfg, GaitParams(crouch=0.10), [])
        self.hw = self.ik.hw
        self.ankle_h = self.ik.ankle_h

        # 步態 FSM
        self.T_step = gait.step_length / max(gait.speed, 0.1)
        self.DS = 0.15                      # 觸地後雙支撐占比
        self.stance = "l"
        self.phase = 1.0                    # 進入 WALK 時立即開始第一步
        self.stance_ankle = np.zeros(3)
        self.swing_start = np.zeros(3)
        self.p_land = np.zeros(3)
        self.pelvis_y_ref = 0.0
        self._land_locked: np.ndarray | None = None
        self.kR = 0.30                      # Raibert 速度回饋增益
        self.n_steps = 0
        self._body = {s: mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f"foot_{s}")
                      for s in ("l", "r")}

    # ------------------------------------------------------------------

    def set_mode(self, mode: str, engine=None):
        if mode == "walk":
            self.state = "WALK"
            self._stop_start_t = None
            self._walk_start_t = self.t
            self.phase = 1.0                # 觸發立即跨出第一步
            self.n_steps = 0
            self.decide("mode", "🚶 Raibert 閉環行走：觸地相位重置 + 線上落腳法則", "mode", 0)
        else:
            super().set_mode("stand")

    def update_gait(self, gait: GaitParams, engine) -> None:
        """更新 Raibert-owned gait/T_step；保留目前 FSM state 與相位。"""
        super().update_gait(gait, engine)
        self.gait = gait
        self.T_step = gait.step_length / max(gait.speed, 0.1)

    def _ankle_pos(self, side: str, data) -> np.ndarray:
        return data.xpos[self._body[side]].copy()

    def compute(self, data: mujoco.MjData, t_gait: float, dt: float) -> np.ndarray:
        # 站立 / 跌倒沿用基底控制器
        self._complete_stop_if_due()
        if not self.is_locomoting():
            return super().compute(data, t_gait, dt)

        self.t += dt
        q = data.qpos[7:]
        qd = data.qvel[6:]
        pitch, roll = quat_to_pitch_roll(data.qpos[3:7])
        pelvis = data.qpos[0:3]
        pelvis_z = pelvis[2]

        # --- 跌倒偵測 ---
        if abs(pitch) > 0.95 or abs(roll) > 0.95 or pelvis_z < 0.45 * self.z_nom:
            self.state = "FALLEN"
            self.decide("fall", f"💥 跌倒！pitch {np.degrees(pitch):.0f}° / roll {np.degrees(roll):.0f}° — 進入阻尼癱軟", "fall", 0)
            return -1.5 * qd

        # --- 質心速度（低通） ---
        self._v_filt += 0.2 * (data.qvel[0:3] - self._v_filt)
        v = self._v_filt
        a = self.walk_alpha()
        v_des = self.gait.speed * a
        omega0 = np.sqrt(G / max(pelvis_z, 0.3))

        # --- 相位推進與觸地事件 ---
        # 危急加速換步：capture point 跑出支撐腳太遠時，擺動腳加速落地
        cp_ahead = (pelvis[0] + v[0] / omega0) - self.stance_ankle[0]
        rate = 1.0
        if self.phase > self.DS and cp_ahead > 0.20:
            rate = 1.0 + np.clip((cp_ahead - 0.20) / 0.15, 0.0, 1.2)
            self.decide("hurry", f"⏩ 加速換步：capture point 超前支撐腳 {cp_ahead*100:.0f} cm", "strategy", 0.8)
        self.phase += rate * dt / self.T_step
        swing = "r" if self.stance == "l" else "l"
        cl, cr = self._foot_contacts(data)
        contact = {"l": cl, "r": cr}
        if self.phase >= 1.0 and self.n_steps == 0:
            # 第一步初始化：phase 從負值開始 → 先有 ~0.5s 的重心橫移
            # （雙腳著地、骨盆移到支撐腳上方），再抬起擺動腳
            self.stance = "l" if v[1] <= 0 else "r"
            swing = "r" if self.stance == "l" else "l"
            self.stance_ankle = self._ankle_pos(self.stance, data)
            self.swing_start = self._ankle_pos(swing, data)
            self.phase = self.DS - 0.8 / self.T_step
            self.n_steps = 1
            self.decide("first", f"🦵 起步：重心先橫移至 {self.stance.upper()} 腳，再跨出第一步", "strategy", 0)
        elif contact[swing] and self.phase > 0.45:
            # 觸地！相位重置、支撐腳交換
            timing_err = (self.phase - 1.0) * self.T_step * 1000
            self.n_steps += 1
            self.stance = swing
            swing = "r" if self.stance == "l" else "l"
            self.stance_ankle = self._ankle_pos(self.stance, data)
            self.swing_start = self._ankle_pos(swing, data)
            self.phase = 0.0
            self.decide("td", f"👟 第 {self.n_steps} 步觸地（{self.stance.upper()} 腳，時序誤差 {timing_err:+.0f} ms）→ 相位重置", "strategy", 0.4)
        phi = self.phase

        # --- Raibert 落腳點（每 tick 連續更新） ---
        sign_sw = +1.0 if swing == "l" else -1.0
        hip_sw_y = pelvis[1] + sign_sw * self.hw
        neutral_x = pelvis[0] + v[0] * self.T_step * 0.5
        self.p_land = np.array([
            neutral_x + self.kR * (v[0] - v_des),
            hip_sw_y + v[1] * self.T_step * 0.5 + self.kR * v[1],
            self.ankle_h,
        ])
        # 落點限制：至少要能接住前衝動量（後移量上限 6cm）+ 可及範圍
        self.p_land[0] = np.clip(self.p_land[0], neutral_x - 0.06, pelvis[0] + 0.45)
        min_sep = 0.13
        if swing == "l":
            self.p_land[1] = max(self.p_land[1], self.stance_ankle[1] + min_sep)
        else:
            self.p_land[1] = min(self.p_land[1], self.stance_ankle[1] - min_sep)
        # 末段鎖定落點：觸地前持續改目標會讓擺動腳永遠追不上
        if self.phase > 0.85:
            if self._land_locked is None:
                self._land_locked = self.p_land.copy()
            self.p_land = self._land_locked
        else:
            self._land_locked = None
        adj = self.p_land[0] - neutral_x
        if abs(self.kR * (v[0] - v_des)) > 0.06 or abs(v[1]) > 0.25:
            self.decide("raibert", f"👣 Raibert 落點修正 ({adj*100:+.0f}, {(v[1]*self.T_step*0.5)*100:+.0f}) cm（速度誤差 {v[0]-v_des:+.2f} m/s）", "strategy", 0.8)

        # --- 支撐腿目標：骨盆相對支撐腳前移 + 速度伺服 ---
        # 速度伺服項：實際速度落後時骨盆目標前移 → 支撐腿主動推進
        # （沒有這一項，擺動腿的反作用會把身體越推越後）
        v_servo = float(np.clip(0.25 * (v_des - v[0]) * self.T_step, -0.10, 0.12))
        if self.n_steps == 1 and phi < self.DS:
            x_rel = 0.0          # 起步重心橫移期間骨盆不前後移動
        else:
            x_rel = np.clip((phi - 0.5) * v_des * self.T_step + v_servo, -0.32, 0.32)
        hip_des_x = self.stance_ankle[0] + x_rel
        sign_st = +1.0 if self.stance == "l" else -1.0
        # 骨盆側向目標幾乎在支撐腳正上方（單支撐的靜態必要條件）
        pelvis_y_target = self.stance_ankle[1] - sign_st * 0.015
        # 側向目標限速：起步用準靜態緩移（快了會引發動力學對抗而失速），
        # 行走中換腳用較快速率
        rate = 0.15 if self.n_steps == 1 else 0.5
        dy = np.clip(pelvis_y_target - self.pelvis_y_ref, -rate * dt, rate * dt)
        self.pelvis_y_ref += dy
        pelvis_des = np.array([hip_des_x, self.pelvis_y_ref, self.z_nom])

        lean_target = self.lean + float(np.clip(0.20 * (v_des - v[0]), -0.10, 0.10))

        # --- 擺動腳軌跡 ---
        if phi < self.DS:
            swing_target = self.swing_start.copy()   # 雙支撐：留在原地
        else:
            u = np.clip((phi - self.DS) / (1.0 - self.DS), 0.0, 1.0)
            s = 10 * u**3 - 15 * u**4 + 6 * u**5
            swing_target = self.swing_start + (self.p_land - self.swing_start) * s
            z_lift = self.gait.clearance * np.sin(np.pi * min(u, 1.0)) ** 3
            if self.phase > 0.92:
                # 末段主動下探：確保準時觸地（骨盆高度誤差會讓名目軌跡懸空）
                z_lift -= 0.35 * (self.phase - 0.92)
            swing_target[2] = self.ankle_h + max(z_lift, -0.05)

        # --- 反解關節角 ---
        # 統一原則（在目前 simulated plant 的側向 case 有效）：IK 以目標姿態
        # 解幾何，再把 MuJoCo state 中的軀幹傾斜從髖關節參考扣除
        # （骨盆位置對支撐腳剛性閉環），軀幹姿態由獨立的髖修正扭矩回正。
        q_ref = self.stand_q.copy()
        # 支撐腿：以「期望骨盆」解 IK → 關節 PD 把骨盆伺服到期望位置
        hip_st = pelvis_des + np.array([0.0, sign_st * self.hw, 0.0])
        r0, hp0, kn0, ap0 = self.ik.leg_ik(hip_st, self.stance_ankle, lean_target)
        # 擺動腿：以 MuJoCo state 的骨盆位置解 IK → 腳掌落在世界座標的目標點，
        # 不受骨盆伺服誤差影響（否則骨盆一偏，落點就永遠搆不到）
        hip_sw = np.array([pelvis[0], pelvis[1], min(pelvis[2], self.z_nom + 0.02)]) \
            + np.array([0.0, sign_sw * self.hw, 0.0])
        r1, hp1, kn1, ap1 = self.ik.leg_ik(hip_sw, swing_target, lean_target)
        pitch_full = float(np.clip(pitch, -0.6, 0.6))
        roll_full = float(np.clip(roll, -0.4, 0.4))
        dp = float(np.clip(pitch - lean_target, -0.5, 0.5))
        for side, (rr, hh, kk, aa) in ((self.stance, (r0, hp0, kn0, ap0)),
                                       (swing, (r1, hp1, kn1, ap1))):
            # 軀幹後仰（dp<0）→ 髖伸展 → 閉鏈反作用把骨盆推回前方（負回授）
            hip_p = hh + dp
            q_ref[JOINT_ORDER.index(f"hip_roll_{side}")] = rr - roll_full
            q_ref[JOINT_ORDER.index(f"hip_pitch_{side}")] = hip_p
            q_ref[JOINT_ORDER.index(f"knee_{side}")] = kk
            # 腳掌永遠貼地（世界座標水平）
            q_ref[JOINT_ORDER.index(f"ankle_{side}")] = -(hip_p - kk) - pitch_full
        # 手臂與支撐腳反相擺動
        arm = np.deg2rad(self.gait.arm_swing_deg) * (phi - 0.5) * 2.0
        arm_sign = +1.0 if self.stance == "l" else -1.0
        q_ref[JOINT_ORDER.index("shoulder_l")] = 0.05 - arm_sign * arm
        q_ref[JOINT_ORDER.index("shoulder_r")] = 0.05 + arm_sign * arm
        q_ref[JOINT_ORDER.index("elbow_l")] = 0.4
        q_ref[JOINT_ORDER.index("elbow_r")] = 0.4

        # 站立→行走混合
        if a < 1.0:
            q_ref = (1 - a) * self.stand_q + a * q_ref

        # --- PD + 前饋 ---
        tau = self.kp * (q_ref - q) - self.kd * qd + 0.8 * data.qfrc_bias[6:]

        # 支撐腿重力前饋（觸地後 DS 期間新舊腳線性轉移）
        if phi < self.DS:
            if self.n_steps == 1:
                # 起步重心橫移：由 50/50 緩慢移到支撐腳
                phi0 = self.DS - 0.8 / self.T_step
                w_new = 0.5 + 0.5 * float(np.clip((phi - phi0) / (self.DS - phi0), 0.0, 1.0))
            else:
                w_new = float(np.clip(phi / self.DS, 0.0, 1.0))
            weights = {self.stance: w_new, swing: 1.0 - w_new}
        else:
            weights = {self.stance: 1.0, swing: 0.0}
        for side, w in weights.items():
            if w > 1e-3:
                F = np.array([0.0, 0.0, w * self.M_total * G])
                mujoco.mj_jacSite(self.model, data, self._jacp, None, self._site(f"sole_{side}"))
                tau -= 0.9 * (self._jacp.T @ F)[6:]

        # --- 姿態修正（作用於支撐髖） ---
        pitch_err = pitch - lean_target
        self.hip_corr = float(np.clip(260.0 * pitch_err + 120.0 * data.qvel[4], -110.0, 110.0))
        tau[JOINT_ORDER.index(f"hip_pitch_{self.stance}")] += self.hip_corr
        # 符號：roll 正 = 向右（−y）傾 → 需負向 hip_roll 扭矩把軀幹推回 +y
        self.roll_corr = float(np.clip(-220.0 * roll - 55.0 * data.qvel[3], -70.0, 70.0))
        tau[JOINT_ORDER.index(f"hip_roll_{self.stance}")] += self.roll_corr
        if abs(self.hip_corr) > 40:
            self.decide("hip", f"🫁 髖策略介入：{self.hip_corr:+.0f} Nm（軀幹前傾 {np.degrees(pitch):.1f}°）", "strategy", 1.0)

        # --- 踝策略：支撐踝速度阻尼 ---
        self.ankle_corr = float(np.clip(-70.0 * (v[0] - v_des), -35.0, 35.0))
        tau[JOINT_ORDER.index(f"ankle_{self.stance}")] += self.ankle_corr

        # 遙測
        self.step_offset = np.array([adj, self.p_land[1] - hip_sw_y])
        cp = pelvis[:2] + v[:2] / omega0
        self._cp_prev = cp.copy()

        return np.clip(tau, -self.tau_lim, self.tau_lim)
