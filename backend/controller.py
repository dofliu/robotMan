"""即時互動模式的平衡控制器。

分層架構（每一層的決策都寫入決策日誌，供介面顯示）：
1. 參考軌跡：站立姿勢（STAND）或步態引擎的關節模式（WALK）
2. 關節 PD 追蹤：剛度由致動器規格推得，出力受馬達峰值扭矩限制
3. 踝策略：質心位置/速度誤差 → 踝關節修正扭矩（小擾動）
4. 髖策略：軀幹姿態誤差 → 髖關節修正扭矩（中擾動）
5. 踏步策略（僅 WALK）：capture point 偏移 → 調整擺動腳落點（大擾動）
6. 跌倒偵測：傾角/骨盆高度超限 → 進入 FALLEN（僅剩阻尼，癱軟）
"""

import numpy as np
import mujoco
from config_schema import GaitParams, RobotConfig
from model_builder import JOINT_ORDER, JOINT_GROUP, joint_peak_torque, pelvis_height

G = 9.81
LOCOMOTION_STATES = frozenset({"WALK", "STOPPING"})


def quat_to_pitch_roll(q: np.ndarray) -> tuple[float, float]:
    """四元數 (w,x,y,z) → 軀幹前傾角 pitch、側傾角 roll（rad）。"""
    w, x, y, z = q
    # 取軀幹 z 軸在世界座標的方向
    zx = 2 * (x * z + w * y)
    zy = 2 * (y * z - w * x)
    zz = 1 - 2 * (x * x + y * y)
    pitch = np.arctan2(zx, zz)      # 前傾為正
    roll = np.arctan2(-zy, zz)      # 向左傾為正（+y 方向倒為負…以下取符號一致即可）
    return float(pitch), float(roll)


class BalanceController:
    def __init__(self, model: mujoco.MjModel, cfg: RobotConfig, engine, lean: float):
        self.model = model
        self.cfg = cfg
        self.engine = engine            # WALK 模式使用；STAND 可為 None
        self.lean = lean
        self.state = "STAND"            # STAND | WALK | STOPPING | FALLEN
        self.decisions: list[dict] = []
        self._decide_last: dict[str, float] = {}
        self.t = 0.0

        # --- PD 增益：由關節端額定扭矩推得（硬體越大越剛） ---
        self.kp = np.zeros(len(JOINT_ORDER))
        self.kd = np.zeros(len(JOINT_ORDER))
        self.tau_lim = np.zeros(len(JOINT_ORDER))
        for j, name in enumerate(JOINT_ORDER):
            a = cfg.actuators[JOINT_GROUP[name]]
            rated = a.motor.rated_torque * a.gear.ratio * a.gear.efficiency
            self.kp[j] = np.clip(rated * 12.0, 60.0, 900.0)
            self.kd[j] = self.kp[j] * 0.06
            self.tau_lim[j] = joint_peak_torque(cfg, name)

        # --- 站立參考姿勢 ---
        self.z_nom = pelvis_height(cfg, 0.10)
        self.stand_q = self._stand_pose()
        self._q_ref_prev: np.ndarray | None = None
        self.M_total = float(np.sum(model.body_mass))
        self._jacp = np.zeros((3, model.nv))

        # 策略輸出（遙測用）
        self.ankle_corr = 0.0
        self.roll_corr = 0.0
        self.hip_corr = 0.0
        self.step_offset = np.zeros(2)
        self._cp_prev: np.ndarray | None = None

        # 質心速度低通（原始速度含腳步衝擊雜訊）
        self._v_filt = np.zeros(3)
        self._stop_start_t: float | None = None
        self._stop_duration = 1.5

    def _stand_pose(self) -> np.ndarray:
        """對稱站立姿勢的關節角（微蹲，膝蓋避開奇異點）。"""
        from gait import GaitEngine
        from config_schema import GaitParams
        eng = GaitEngine(self.cfg, GaitParams(crouch=0.10), [])
        hip = np.array([0.0, eng.hw, self.z_nom])
        ankle = np.array([0.0, eng.hw, eng.ankle_h])
        roll, hp, kn, ap = eng.leg_ik(hip, ankle, 0.0)
        q = np.zeros(len(JOINT_ORDER))
        for side in ("l", "r"):
            q[JOINT_ORDER.index(f"hip_roll_{side}")] = 0.0
            q[JOINT_ORDER.index(f"hip_pitch_{side}")] = hp
            q[JOINT_ORDER.index(f"knee_{side}")] = kn
            q[JOINT_ORDER.index(f"ankle_{side}")] = ap
            q[JOINT_ORDER.index(f"shoulder_{side}")] = 0.05
            q[JOINT_ORDER.index(f"elbow_{side}")] = 0.35
        return q

    def decide(self, key: str, text: str, level: str = "info", min_interval: float = 0.6):
        """寫入決策日誌（同類事件節流，避免洗版）。"""
        last = self._decide_last.get(key, -1e9)
        if self.t - last >= min_interval:
            self._decide_last[key] = self.t
            self.decisions.append({"t": round(self.t, 2), "text": text, "level": level})
            if len(self.decisions) > 200:
                self.decisions = self.decisions[-200:]

    blend_T = 1.5   # 站立→行走混合時間（閉環控制器可覆寫為更短）

    def is_locomoting(self) -> bool:
        return self.state in LOCOMOTION_STATES

    def stop_scale(self) -> float:
        """Controlled stop 的 locomotion command scale，1→0。"""
        if self.state == "WALK":
            return 1.0
        if self.state != "STOPPING" or self._stop_start_t is None:
            return 0.0
        u = float(np.clip((self.t - self._stop_start_t) / self._stop_duration, 0.0, 1.0))
        smooth = u * u * (3.0 - 2.0 * u)
        return 1.0 - smooth

    def request_stop(self, duration_s: float = 1.5) -> None:
        """要求受控停止；不改寫 plant state，也不在同一 tick 瞬切站姿。"""
        if self.state == "FALLEN":
            return
        if not self.is_locomoting():
            self.state = "STAND"
            return
        if self.state == "STOPPING":
            return
        self._stop_duration = max(float(duration_s), 0.1)
        self._stop_start_t = self.t
        self.state = "STOPPING"
        self.decide(
            "mode",
            f"🛑 受控停止：{self._stop_duration:.1f}s 內降低速度與步態幅度，再進入站立平衡",
            "mode",
            0,
        )

    def _complete_stop_if_due(self) -> None:
        if (
            self.state == "STOPPING"
            and self._stop_start_t is not None
            and self.t - self._stop_start_t + 1e-9 >= self._stop_duration
        ):
            self.state = "STAND"
            self._stop_start_t = None
            self._q_ref_prev = None
            self.decide("stop_complete", "🧍 受控停止完成：進入站立平衡", "mode", 0)

    def walk_alpha(self) -> float:
        """站立→行走混合進度 0..1（步態時鐘與速度目標皆以此縮放）。"""
        if not self.is_locomoting():
            return 0.0
        a = np.clip((self.t - getattr(self, "_walk_start_t", self.t)) / self.blend_T, 0.0, 1.0)
        startup = a * a * (3 - 2 * a)
        return float(startup * self.stop_scale())

    def gait_clock_rate(self) -> float:
        """步態時鐘推進速率（相對即時）。

        速度回授：實際前進速度落後參考時，步態時鐘放慢，
        避免參考軌跡「跑掉」造成越追越遠的正回授跌倒。
        """
        a = self.walk_alpha()
        if a <= 0 or self.engine is None:
            return a
        v_des = self.engine.g.speed * a
        if v_des < 0.05:
            return a
        ratio = np.clip(self._v_filt[0] / v_des, 0.35, 1.02)
        return float(a * (0.4 + 0.6 * ratio))

    def set_mode(self, mode: str, engine=None):
        if mode == "walk":
            self.engine = engine if engine is not None else self.engine
            self.state = "WALK"
            self._stop_start_t = None
            self._walk_start_t = self.t       # 站立→行走平滑混合的起點
            self.decide("mode", "🚶 切換至行走模式：1.5s 內從站姿平滑混入步態軌跡", "mode", 0)
        else:
            if self.is_locomoting():
                self.request_stop()
            else:
                self.state = "STAND"
                self.decide("mode", "🧍 切換至站立平衡模式：踝/髖策略維持重心", "mode", 0)

    def update_gait(self, gait: GaitParams, engine) -> None:
        """原位同步 runtime gait，保留 controller identity/state/timing history。"""
        self.engine = engine
        self.lean = float(np.deg2rad(gait.torso_lean_deg))
        # 新舊 reference 不可跨設定做 finite difference，否則產生人為速度尖峰。
        self._q_ref_prev = None

    # ------------------------------------------------------------------

    def compute(self, data: mujoco.MjData, t_gait: float, dt: float) -> np.ndarray:
        """回傳 12 維關節扭矩命令（MuJoCo 會再以 ctrlrange 截斷）。"""
        self.t += dt
        self._complete_stop_if_due()
        q = data.qpos[7:]
        qd = data.qvel[6:]
        trunk_quat = data.qpos[3:7]
        pitch, roll = quat_to_pitch_roll(trunk_quat)
        pelvis_z = data.qpos[2]

        # --- 跌倒偵測 ---
        if self.state != "FALLEN":
            if abs(pitch) > 0.95 or abs(roll) > 0.95 or pelvis_z < 0.45 * self.z_nom:
                self.state = "FALLEN"
                self.decide("fall", f"💥 跌倒！軀幹傾角 pitch {np.degrees(pitch):.0f}° / roll {np.degrees(roll):.0f}°，骨盆高度 {pelvis_z:.2f} m — 各關節進入阻尼癱軟", "fall", 0)
        if self.state == "FALLEN":
            return -1.5 * qd    # 癱軟：僅阻尼

        # --- 質心狀態 ---
        mujoco.mj_comPos(self.model, data)          # 確保 subtree_com 最新
        com = data.subtree_com[0].copy()
        # 全身質心速度（用 subtree 動量較精確，這裡以骨盆速度低通近似）
        v_raw = data.qvel[0:3]
        self._v_filt += 0.15 * (v_raw - self._v_filt)
        v = self._v_filt
        omega0 = np.sqrt(G / max(com[2], 0.3))
        capture_pt = com[:2] + v[:2] / omega0        # capture point（LIPM）

        # 突發擾動偵測（capture point 突跳）
        if self._cp_prev is not None:
            jump = np.linalg.norm(capture_pt - self._cp_prev) / max(dt, 1e-4)
            if jump > 2.0:
                self.decide("impact", f"⚡ 偵測到外部擾動：capture point 速率 {jump:.1f} m/s", "impact", 0.8)
        self._cp_prev = capture_pt.copy()

        # --- 參考姿勢 ---
        if self.is_locomoting() and self.engine is not None:
            q_full = self.engine.qpos_at(t_gait, self.model.nq)
            q_gait = q_full[7:]
            if self._q_ref_prev is None:
                qd_gait = np.zeros_like(q_gait)
            else:
                qd_gait = np.clip((q_gait - self._q_ref_prev) / dt, -20, 20)
            self._q_ref_prev = q_gait.copy()
            # 站立→行走平滑混合（smoothstep）：避免參考突變把機器人拉倒
            a = self.walk_alpha()
            q_ref = (1 - a) * self.stand_q + a * q_gait
            qd_ref = a * qd_gait
        else:
            q_ref = self.stand_q
            qd_ref = np.zeros_like(q_ref)
            self._q_ref_prev = None

        # --- 關節 PD + 重力/科氏前饋（改善擺動腿追蹤與姿勢下垂） ---
        tau = self.kp * (q_ref - q) + self.kd * (qd_ref - qd) + 0.8 * data.qfrc_bias[6:]

        # --- 支撐腿重力前饋：預期地面反力經 Jacobian 轉成關節扭矩 ---
        # 沒有這一項，全身重量的重力矩會讓支撐膝在 PD 下明顯塌陷
        # （骨盆下沉 → 擺動腳搆不到地 → 單支撐拖長 → 側向發散跌倒）
        if self.is_locomoting() and self.engine is not None:
            w_l = self.engine.contact_weight("l", t_gait)
            w_r = self.engine.contact_weight("r", t_gait)
        else:
            w_l = w_r = 0.5
        w_sum = w_l + w_r
        if w_sum > 1e-6:
            for side, w in (("l", w_l), ("r", w_r)):
                if w > 1e-6:
                    F = np.array([0.0, 0.0, (w / w_sum) * self.M_total * G])
                    mujoco.mj_jacSite(self.model, data, self._jacp, None, self._site(f"sole_{side}"))
                    tau -= 0.9 * (self._jacp.T @ F)[6:]

        # --- 支撐腳判定（接觸力） ---
        contact_l, contact_r = self._foot_contacts(data)
        in_contact = contact_l or contact_r

        # --- 踝策略：質心前後誤差 → 踝 pitch 修正 ---
        if in_contact:
            if self.state == "STAND":
                sole_mid_x = 0.5 * (data.site_xpos[self._site("sole_l")][0]
                                    + data.site_xpos[self._site("sole_r")][0]) + 0.02
                e_x = com[0] - sole_mid_x
                self.ankle_corr = float(np.clip(-(420.0 * e_x + 110.0 * v[0]), -45.0, 45.0))
            else:
                # 行走時僅做速度阻尼（位置誤差由步態本身處理）；
                # 混合期間速度目標隨 α 漸增
                v_des = self.engine.g.speed * self.walk_alpha()
                self.ankle_corr = float(np.clip(-70.0 * (v[0] - v_des), -30.0, 30.0))
            for side, c in (("l", contact_l), ("r", contact_r)):
                if c:
                    tau[JOINT_ORDER.index(f"ankle_{side}")] += self.ankle_corr
            if abs(self.ankle_corr) > 20:
                self.decide("ankle", f"🦶 踝策略介入：修正扭矩 {self.ankle_corr:+.0f} Nm（質心速度 {v[0]:+.2f} m/s）", "strategy", 1.0)

            # --- 側向：髖 roll 修正（質心 y 誤差 + 軀幹 roll 姿態） ---
            feet_mid_y = 0.5 * (data.site_xpos[self._site("sole_l")][1]
                                + data.site_xpos[self._site("sole_r")][1])
            e_y = com[1] - feet_mid_y
            # roll 正 = 向 −y 傾，姿態項需負號才是回正方向
            self.roll_corr = float(np.clip(220.0 * e_y + 60.0 * v[1] - 150.0 * roll, -60.0, 60.0))
            for side, c in (("l", contact_l), ("r", contact_r)):
                if c:
                    tau[JOINT_ORDER.index(f"hip_roll_{side}")] += self.roll_corr
            if abs(self.roll_corr) > 30:
                self.decide("roll", f"🫸 側向髖策略介入：{self.roll_corr:+.0f} Nm（質心側偏 {e_y*100:+.1f} cm）", "strategy", 1.0)

            # --- 髖策略：軀幹 pitch 姿態 ---
            # 行走時以「前傾角」做速度控制：落後 → 多前傾（重力加速），
            # 過快 → 直立減速。這是人類行走速度調節的核心機制
            lean_target = self.lean
            if self.is_locomoting() and self.engine is not None:
                v_des = self.engine.g.speed * self.walk_alpha()
                lean_target = self.lean + float(np.clip(0.45 * (v_des - v[0]), -0.12, 0.15))
            pitch_err = pitch - lean_target
            if self.is_locomoting():
                # 行走時姿態修正與 PD 參考會互相干擾：小比例、大阻尼
                self.hip_corr = float(np.clip(140.0 * pitch_err + 120.0 * data.qvel[4], -50.0, 50.0))
            else:
                self.hip_corr = float(np.clip(280.0 * pitch_err + 60.0 * data.qvel[4], -80.0, 80.0))
            for side, c in (("l", contact_l), ("r", contact_r)):
                if c:
                    tau[JOINT_ORDER.index(f"hip_pitch_{side}")] += self.hip_corr
            if abs(self.hip_corr) > 40:
                self.decide("hip", f"🫁 髖策略介入：{self.hip_corr:+.0f} Nm（軀幹前傾 {np.degrees(pitch):.1f}°）", "strategy", 1.0)

        # --- 踏步策略（WALK）：capture point 誤差 → 調整落點 ---
        if self.is_locomoting() and self.engine is not None:
            v_err = np.array([v[0] - self.engine.g.speed * self.walk_alpha(), v[1]])
            dp = np.clip(v_err / omega0, -0.28, 0.28)
            self.step_offset = dp
            # 側向（y）：橫向倒立擺發散極快（τ≈0.27s），capture point
            # 落點修正必須「連續」進行，不能等大偏差才動作；
            # 前後（x）：小偏差交給前傾速度控制，踏步只處理大擾動
            dx = float(dp[0]) if abs(dp[0]) > 0.10 else 0.0
            dy = float(np.clip(v[1] / omega0, -0.15, 0.15))
            for side in ("l", "r"):
                _, stance = self.engine.foot_target(side, t_gait)
                if not stance:
                    self.engine.set_step_offset(side, dx, dy)
                else:
                    self.engine.set_step_offset(side, 0.0, 0.0)
            if abs(dx) > 0 or abs(dy) > 0.06:
                self.decide("step", f"👣 踏步策略：落點調整 ({dx*100:+.0f}, {dy*100:+.0f}) cm（質心速度偏差 {np.linalg.norm(v_err):.2f} m/s）", "strategy", 0.7)

        return np.clip(tau, -self.tau_lim, self.tau_lim)

    # ------------------------------------------------------------------

    def _site(self, name: str) -> int:
        return mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, name)

    def _foot_contacts(self, data: mujoco.MjData) -> tuple[bool, bool]:
        gl = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "foot_l")
        gr = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "foot_r")
        cl = cr = False
        for i in range(data.ncon):
            c = data.contact[i]
            if c.geom1 == gl or c.geom2 == gl:
                cl = True
            if c.geom1 == gr or c.geom2 == gr:
                cr = True
        return cl, cr

    def telemetry(self, data: mujoco.MjData) -> dict:
        """前端狀態面板用的控制器內部狀態。"""
        pitch, roll = quat_to_pitch_roll(data.qpos[3:7])
        com = data.subtree_com[0]
        v = self._v_filt
        omega0 = np.sqrt(G / max(com[2], 0.3))
        cp = com[:2] + v[:2] / omega0

        # MuJoCo contact-derived CoP 與各腳法向力；這是模擬器輸出，不是實體量測。
        gl = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "foot_l")
        gr = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "foot_r")
        f6 = np.zeros(6)
        cop_num = np.zeros(2)
        fz_sum = 0.0
        fz = {"l": 0.0, "r": 0.0}
        contact_pts = []
        for i in range(data.ncon):
            c = data.contact[i]
            side = "l" if gl in (c.geom1, c.geom2) else ("r" if gr in (c.geom1, c.geom2) else None)
            if side is None:
                continue
            mujoco.mj_contactForce(self.model, data, i, f6)
            fn = f6[0]                       # 接觸座標系第一軸為法向
            fz[side] += fn
            fz_sum += fn
            cop_num += c.pos[:2] * fn
            contact_pts.append([round(float(c.pos[0]), 3), round(float(c.pos[1]), 3)])
        cop = (cop_num / fz_sum).tolist() if fz_sum > 1.0 else None

        sat = {}
        for grp in self.cfg.actuators:
            idxs = [j for j, n in enumerate(JOINT_ORDER) if JOINT_GROUP[n] == grp]
            f = np.abs(data.actuator_force[idxs])
            lim = self.tau_lim[idxs[0]]
            sat[grp] = round(float(f.max() / max(lim, 1e-6)) * 100, 0)

        return {
            "state": self.state,
            "pitch_deg": round(np.degrees(pitch), 1),
            "roll_deg": round(np.degrees(roll), 1),
            "com": [round(float(x), 3) for x in com],
            "com_vel": [round(float(x), 3) for x in v],
            "capture_point": [round(float(cp[0]), 3), round(float(cp[1]), 3)],
            "cop": cop,
            "grf": {"l": round(fz["l"], 0), "r": round(fz["r"], 0)},
            "contacts": contact_pts,
            "ankle_corr": round(self.ankle_corr, 1),
            "roll_corr": round(self.roll_corr, 1),
            "hip_corr": round(self.hip_corr, 1),
            "step_offset": [round(float(self.step_offset[0]), 3), round(float(self.step_offset[1]), 3)],
            "saturation": sat,
        }
