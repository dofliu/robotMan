"""參數化步態生成引擎。

流程：步態參數（速度/步長/支撐期占比…）→ 骨盆與雙腳的世界座標軌跡
→ 解析腿部 IK → 全身 qpos 時間序列。

為何用運動學步態而非動態控制器：analysis mode 需要可重現、可比較的
關節扭矩 screening curve；運動學軌跡 + 逆動力學可隔離平衡控制器調參
的影響，但只能回答目前 prescribed motion/contact assumptions 下的相對
需求，不能單獨判定實體馬達／減速機是否可行。
"""

import numpy as np
from config_schema import RobotConfig, GaitParams, Obstacle
from model_builder import JOINT_ORDER, pelvis_height


class GaitEngine:
    def __init__(self, cfg: RobotConfig, gait: GaitParams, obstacles: list[Obstacle]):
        self.cfg = cfg
        self.g = gait
        self.obstacles = obstacles
        d = cfg.dims

        self.l1 = d.thigh_len
        self.l2 = d.shin_len
        self.hw = d.hip_width / 2
        self.ankle_h = d.foot_height          # 踝關節離地高（腳掌貼地時）
        self.z_nom = pelvis_height(cfg, gait.crouch)
        self.lean = np.deg2rad(gait.torso_lean_deg)

        # 週期參數：T_step = 單步時間，T = 完整週期（左右各一步）
        self.T_step = gait.step_length / max(gait.speed, 0.05)
        self.T = 2 * self.T_step
        self.duty = np.clip(gait.duty, 0.25, 0.85)
        self.stride = gait.speed * self.T     # 每週期前進距離（= 2 步長）

        self.ik_clamped = False               # IK 超出腿長時記錄警告
        # 質心等速修正（由 simulator 迭代求解後設定）：
        # 骨盆前後微調使全身質心維持等速，否則擺動腿慣性會造成
        # 不真實的巨大水平地面反力
        self._corr_t: np.ndarray | None = None
        self._corr_x: np.ndarray | None = None
        # 即時互動模式的踏步策略落點偏移（[dx, dy]，僅影響擺動段）
        self._step_offset = {"l": np.zeros(2), "r": np.zeros(2)}

        # 腳掌幾何：踝關節到腳尖/腳跟的水平距離（落點迴避需含整個腳掌）
        foot_cx = d.foot_len / 2 - 0.06
        self.toe = foot_cx + d.foot_len / 2   # 踝 → 腳尖
        self.heel = d.foot_len / 2 - foot_cx  # 踝 → 腳跟
        self.RAMP = 0.10                      # 抬腳罩形曲線坡道寬 m
        self.PLANT_MARGIN = 0.16              # 落點與障礙物的額外餘裕（> RAMP）

        # 可跨越性判定與「跨越下蹲」計算：
        # 跨越障礙物時，跨越步的雙支撐兩腳距離 = 禁踩區寬度（span），
        # 骨盆高度 h 必須滿足 sqrt(L² - (span/2)²) ≥ h 才搆得到兩腳。
        # 不足時骨盆在跨越窗內自動下蹲 dip；dip 超過極限或障礙物太高
        # → 不可跨越，於障礙物前停止。
        self.h_max = 0.35 * (self.l1 + self.l2)
        L_eff = self.l1 + self.l2 - 0.005
        h_nom = self.z_nom - self.ankle_h
        self.max_dip = 0.12
        span_max = 2 * np.sqrt(max(L_eff**2 - (h_nom - self.max_dip + 0.015) ** 2, 1e-4))
        self.depth_max = span_max - self.toe - self.heel - 2 * self.PLANT_MARGIN
        self._L_eff = L_eff
        self._h_nom = h_nom

        self._dips: list[tuple[float, float, float]] = []  # (zone_lo, zone_hi, dip)
        self.stop_foot_x: float | None = None  # 不可跨越時，腳掌停止線（踝 x）
        self.blocking_obstacle: Obstacle | None = None
        blocked = []
        for ob in obstacles:
            if ob.x <= 0:
                continue
            span = ob.depth + self.toe + self.heel + 2 * self.PLANT_MARGIN
            h_need = np.sqrt(max(L_eff**2 - (span / 2) ** 2, 1e-4))
            dip = max(0.0, h_nom - h_need + 0.015)
            if ob.height > self.h_max or dip > self.max_dip:
                blocked.append(ob)
            elif dip > 0:
                zone_lo = ob.x - ob.depth / 2 - self.toe - self.PLANT_MARGIN
                zone_hi = ob.x + ob.depth / 2 + self.heel + self.PLANT_MARGIN
                self._dips.append((zone_lo, zone_hi, dip))
        if blocked:
            nearest = min(blocked, key=lambda ob: ob.x)
            self.blocking_obstacle = nearest
            self.stop_foot_x = nearest.x - nearest.depth / 2 - self.toe - 0.08

        self._plan_footsteps()

    def set_x_correction(self, t: np.ndarray, dx: np.ndarray):
        self._corr_t = t
        self._corr_x = dx

    def set_step_offset(self, side: str, dx: float, dy: float):
        """即時互動模式的踏步策略：對當前擺動腳的落點加上偏移
        （偏移量隨擺動進度漸入，起點不變、落點平移）。"""
        self._step_offset[side][0] = dx
        self._step_offset[side][1] = dy

    # ---------------- 落腳點規劃（含障礙物迴避） ----------------

    def _adjust_for_obstacles(self, x_plant: float) -> tuple[float, float]:
        """回傳 (修正後落腳點, 該步所需額外離地高度)。

        規則：落點若在障礙物範圍內 → 移到障礙物後緣外；
        擺動路徑若跨過障礙物 → 抬腳高度需超過障礙物。
        """
        for ob in self.obstacles:
            if self.blocking_obstacle is ob:
                continue                      # 不可跨越者由停止線處理
            # 禁踩區間需涵蓋整個腳掌（踝到腳尖/腳跟）再加安全餘裕；
            # 餘裕必須大於抬腳罩形曲線的坡道寬度，落點才會在罩形之外
            lo = ob.x - ob.depth / 2 - self.toe - self.PLANT_MARGIN
            hi = ob.x + ob.depth / 2 + self.heel + self.PLANT_MARGIN
            if lo < x_plant < hi:
                # 前移量小就跨到障礙物後方；否則退到障礙物前方，下一步再跨
                if hi - x_plant <= 0.35:
                    x_plant = hi
                else:
                    x_plant = lo
        return x_plant, 0.0

    def _obstacle_req_z(self, x: float) -> float:
        """腳掌位於 x 時，為避開障礙物所需的踝關節抬升高度（平滑罩形）。

        以腳掌前後緣是否與障礙物重疊為準，罩形兩側各有 RAMP 寬的
        smoothstep 坡道，確保高度需求隨 x 連續變化（速度連續）。
        """
        req = 0.0
        for ob in self.obstacles:
            lo = ob.x - ob.depth / 2 - self.toe
            hi = ob.x + ob.depth / 2 + self.heel
            a0, b1 = lo - self.RAMP, hi + self.RAMP
            if a0 < x < b1:
                t_in = np.clip((x - a0) / self.RAMP, 0.0, 1.0)
                t_out = np.clip((b1 - x) / self.RAMP, 0.0, 1.0)
                t = min(t_in, t_out)
                s = t * t * (3 - 2 * t)       # smoothstep
                req = max(req, (ob.height + 0.07) * s)
        return req

    def _plan_footsteps(self):
        """預先計算整段模擬中每一步的落腳點（世界座標 x）。

        名目排程：左腳在 t = nT 觸地、右腳在 t = (n+0.5)T 觸地，
        落點在觸地瞬間骨盆前方 (v·D·T)/2 處（使腳掌於支撐中期位於骨盆正下方）。
        """
        v = self.g.speed
        lead = v * self.duty * self.T / 2
        n_cycles = int(np.ceil(self.g.duration / self.T)) + 2

        self.plants = {"l": [], "r": []}      # 每步觸地：(t_strike, x_plant)
        events: list[tuple[float, float]] = []  # 合併排序的 (t_strike, x_plant)
        for n in range(-2, n_cycles + 2):
            for side, off in (("l", 0.0), ("r", 0.5)):
                t_strike = (n + off) * self.T
                x_nom = v * t_strike + lead
                x_adj, _ = self._adjust_for_obstacles(x_nom)
                if self.stop_foot_x is not None:
                    # 不可跨越的障礙物：落點不得超過停止線（左右微錯開成自然站姿）
                    stagger = 0.0 if side == "l" else 0.09
                    x_adj = min(x_adj, self.stop_foot_x - stagger)
                self.plants[side].append((t_strike, x_adj))
                events.append((t_strike, x_adj))

        # ---- 骨盆基準軌跡：跟隨落腳計畫 ----
        # 觸地瞬間骨盆應位於落點後方 lead 處（前進中）；落點因障礙物
        # 推移或停止時，骨盆隨之減速/停下，確保腳始終在腿長可及範圍。
        # lead 依「局部前進速度」比例縮放：原地踏步時骨盆停在腳正上方。
        events.sort()
        te = np.array([e[0] for e in events])
        xe = np.array([e[1] for e in events])
        xref = np.zeros(len(events))
        for k in range(len(events)):
            k0, k1 = max(k - 1, 0), min(k + 1, len(events) - 1)
            v_loc = (xe[k1] - xe[k0]) / max(te[k1] - te[k0], 1e-6)
            xref[k] = xe[k] - lead * np.clip(v_loc / max(v, 1e-6), 0.0, 1.0)
        # 事件間線性內插 + 高斯平滑：等速段維持直線，變速處圓滑過渡
        grid = np.arange(te[0], te[-1], 0.02)
        x_lin = np.interp(grid, te, xref)
        sigma = max(0.10 * self.T, 0.04)
        n_k = max(int(3 * sigma / 0.02) | 1, 3)
        kk = np.exp(-0.5 * ((np.arange(n_k) - n_k // 2) * 0.02 / sigma) ** 2)
        kk /= kk.sum()
        x_smooth = np.convolve(x_lin, kk, mode="same")

        # ---- 跨越下蹲曲線（沿時間軸）----
        # 骨盆通過禁踩區附近時平滑下蹲 dip，增加腿的水平可及範圍
        dip_arr = np.zeros_like(grid)
        for zone_lo, zone_hi, dip in self._dips:
            a0, b1 = zone_lo - 0.40, zone_hi + 0.40
            ramp = 0.25
            t_in = np.clip((x_smooth - a0) / ramp, 0.0, 1.0)
            t_out = np.clip((b1 - x_smooth) / ramp, 0.0, 1.0)
            tt = np.minimum(t_in, t_out)
            dip_arr = np.maximum(dip_arr, dip * tt * tt * (3 - 2 * tt))

        # ---- 可及性夾制 ----
        # 骨盆任何時刻都必須在「所有支撐腳」的水平可及半徑 R 內，
        # 否則 IK 飽和會使腳偏離規劃軌跡（視覺上就是腳插進障礙物）
        h_eff = self._h_nom - dip_arr
        R = np.sqrt(np.maximum(self._L_eff**2 - h_eff**2, 0.01))
        D = self.duty
        x_c = x_smooth.copy()
        kk_s = np.exp(-0.5 * ((np.arange(9) - 4) * 0.02 / max(0.05 * self.T, 0.03)) ** 2)
        kk_s /= kk_s.sum()
        def clamp_pass(xs: np.ndarray) -> np.ndarray:
            out = xs.copy()
            for i, t in enumerate(grid):
                lo_b, hi_b = -np.inf, np.inf
                for side in ("l", "r"):
                    idx = self._plant_index(side, t)
                    ts, xp = self.plants[side][idx]
                    if ts <= t <= ts + D * self.T:      # 該腳處於支撐期
                        hi_b = min(hi_b, xp + R[i])
                        lo_b = max(lo_b, xp - R[i])
                if lo_b > hi_b:
                    out[i] = 0.5 * (lo_b + hi_b)
                elif np.isfinite(lo_b) or np.isfinite(hi_b):
                    out[i] = np.clip(out[i], lo_b, hi_b)
            return out

        # 多次「夾制→平滑」迭代：收斂後同時近似滿足可及性與 C¹ 平滑
        # （硬夾制收尾會產生速度轉折 → 逆動力學出現巨大加速度尖峰）
        for _ in range(6):
            x_c = np.convolve(clamp_pass(x_c), kk_s, mode="same")

        self._base_t = grid
        self._base_x_arr = x_c
        self._dip_arr = dip_arr

    def _plant_index(self, side: str, t: float) -> int:
        """找出時間 t 所屬的步（最後一個 t_strike <= t）。"""
        arr = self.plants[side]
        # 排程等間隔，直接計算索引（+2 因為從 n=-2 開始存）
        off = 0.0 if side == "l" else 0.5
        idx = int(np.floor(t / self.T - off)) + 2
        return int(np.clip(idx, 0, len(arr) - 2))

    # ---------------- 單腳軌跡 ----------------

    def foot_target(self, side: str, t: float) -> tuple[np.ndarray, bool]:
        """回傳 (踝關節世界座標目標, 是否處於支撐期)。"""
        idx = self._plant_index(side, t)
        t_strike, x_plant = self.plants[side][idx]
        t_next, x_next = self.plants[side][idx + 1]
        y = self.hw if side == "l" else -self.hw

        t_stance_end = t_strike + self.duty * self.T
        if t <= t_stance_end:
            # 支撐期：腳掌固定於落點
            return np.array([x_plant, y, self.ankle_h]), True

        # 擺動期：由當前落點平滑移動到下一落點
        T_swing = t_next - t_stance_end
        u = np.clip((t - t_stance_end) / max(T_swing, 1e-6), 0.0, 1.0)
        # min-jerk 位移曲線：端點速度與加速度皆為零（C² 連續），
        # 避免起落瞬間的加速度跳變造成逆動力學扭矩尖峰
        s = 10 * u**3 - 15 * u**4 + 6 * u**5
        x = x_plant + (x_next - x_plant) * s
        # 踏步策略偏移：隨擺動進度漸入（起點連續、落點平移）
        off = self._step_offset[side]
        x += off[0] * s
        y += off[1] * s
        z_base = self.g.clearance * np.sin(np.pi * u) ** 3

        # 擺動目標的可及性軟飽和：長跨步時骨盆可能已前進，早期擺動
        # 目標若超出腿長水平可及範圍，先朝骨盆方向收斂（平滑 tanh），
        # 否則 IK 飽和會讓腳偏離規劃高度而掃到障礙物
        pel_x = self.base_x(t)
        pel_z = self.z_nom - float(np.interp(t, self._base_t, self._dip_arr))
        dz = pel_z - (self.ankle_h + z_base)
        Rh = np.sqrt(max(self._L_eff**2 - dz * dz, 4e-4))
        dx = x - pel_x
        Rs, w = Rh - 0.03, 0.04
        if abs(dx) > Rs:
            dx = np.sign(dx) * (Rs + w * np.tanh((abs(dx) - Rs) / w))
            x = pel_x + dx

        # 基本抬腳（sin³：端點斜率與二階導數皆為零）與障礙物罩形高度取大值；
        # 罩形依「飽和後」的實際 x 計算，確保腳掌所在位置一定有足夠高度
        z_req = self._obstacle_req_z(x)
        z = self.ankle_h + max(z_base, z_req)
        return np.array([x, y, z]), False

    def stance_progress(self, side: str, t: float) -> float | None:
        """支撐期進度 0..1（非支撐期回傳 None），供 CoP 前移計算。"""
        idx = self._plant_index(side, t)
        t_strike, _ = self.plants[side][idx]
        dur = self.duty * self.T
        p = (t - t_strike) / dur
        return float(np.clip(p, 0.0, 1.0)) if 0.0 <= p <= 1.0 else None

    def contact_weight(self, side: str, t: float) -> float:
        """該腳承重比例（雙支撐期線性轉移；跑步短暫過渡避免不連續）。"""
        idx = self._plant_index(side, t)
        t_strike, _ = self.plants[side][idx]
        phase_in = (t - t_strike) / self.T    # 進入本步後的週期相位
        D = self.duty
        if phase_in >= D:
            return 0.0
        # 承重轉移窗：走路至少 0.12 週期（過短會讓 ZMP 轉移追不上支撐面
        # 切換）；跑步無雙支撐，僅留極短過渡避免不連續
        ds = max(D - 0.5, 0.12) if D > 0.5 else 0.03
        if phase_in < ds:                     # 觸地初期：承重漸增
            return phase_in / ds
        if phase_in > D - ds:                 # 離地前：承重漸減
            return (D - phase_in) / ds
        return 1.0

    # ---------------- 骨盆軌跡 ----------------

    def base_x(self, t: float) -> float:
        """骨盆名目前進位置（未含質心修正）：跟隨落腳計畫的平滑軌跡。"""
        return float(np.interp(t, self._base_t, self._base_x_arr))

    def pelvis_state(self, t: float) -> tuple[np.ndarray, float]:
        """回傳 (骨盆位置, 前傾角)。"""
        g = self.g
        phi = (t / self.T) % 1.0
        x = self.base_x(t)
        if self._corr_x is not None:
            x -= float(np.interp(t, self._corr_t, self._corr_x))
        # tanh 整形的側擺：比正弦多出「平頂」段（近似 LIPM 橫向解），
        # 單支撐期間重心穩定停留在支撐腳上方，換腳時快速轉移
        theta = 2 * np.pi * phi - np.pi * self.duty
        y = g.pelvis_sway * np.tanh(1.6 * np.cos(theta)) / np.tanh(1.6)
        if g.mode == "run":
            # 跑步：支撐中期最低（吸震）、騰空期最高
            z = self.z_nom - g.pelvis_bounce * np.cos(4 * np.pi * phi - 2 * np.pi * self.duty)
        else:
            # 走路：單支撐中期最高（倒單擺）
            z = self.z_nom + g.pelvis_bounce * np.cos(4 * np.pi * phi - 2 * np.pi * self.duty)
        # 跨越障礙時的自動下蹲
        z -= float(np.interp(t, self._base_t, self._dip_arr))
        return np.array([x, y, z]), self.lean

    # ---------------- 腿部解析 IK ----------------

    def leg_ik(self, hip_world: np.ndarray, ankle_world: np.ndarray, lean: float):
        """解 (hip_roll, hip_pitch, knee, ankle_pitch)，腳掌保持水平。"""
        v = ankle_world - hip_world
        # 轉到軀幹座標（軀幹僅有 pitch 前傾）
        c, s = np.cos(-lean), np.sin(-lean)
        vx = c * v[0] + s * v[2]
        vy = v[1]
        vz = -s * v[0] + c * v[2]

        # roll：先繞 x 軸轉，使目標落在腿平面
        roll = np.arctan2(vy, -vz)
        cr, sr = np.cos(roll), np.sin(roll)
        # 移除 roll 後的平面座標（前向 px、向下 pz）
        px = vx
        pz = -(sr * vy + cr * vz)             # 向下為正

        d = np.hypot(px, pz)
        d_max = self.l1 + self.l2 - 1e-4
        # 軟飽和：接近腿長極限時平滑收斂，避免硬截斷造成速度跳變
        d_soft = d_max - 0.015
        if d > d_soft:
            over = (d - d_soft) / (d_max - d_soft)
            if over > 1.8:
                self.ik_clamped = True        # 明顯超出可及範圍（>1.2cm）才警告
            d = d_soft + (d_max - d_soft) * np.tanh(over)
        d = max(d, abs(self.l1 - self.l2) + 1e-4)

        cos_inner = (self.l1**2 + self.l2**2 - d**2) / (2 * self.l1 * self.l2)
        knee = np.pi - np.arccos(np.clip(cos_inner, -1.0, 1.0))   # 屈膝角（0=打直）
        beta = np.arctan2(px, pz)                                  # 髖→踝連線前傾角
        cos_g = (self.l1**2 + d**2 - self.l2**2) / (2 * self.l1 * d)
        gamma = np.arccos(np.clip(cos_g, -1.0, 1.0))
        hip_pitch = beta + gamma

        # 腳掌水平：抵銷大腿/小腿與軀幹前傾的總轉角
        ankle_pitch = -(hip_pitch - knee) - lean
        return roll, hip_pitch, knee, ankle_pitch

    # ---------------- 全身 qpos ----------------

    def qpos_at(self, t: float, nq: int) -> np.ndarray:
        g = self.g
        pelvis, lean = self.pelvis_state(t)
        phi = (t / self.T) % 1.0

        q = np.zeros(nq)
        q[0:3] = pelvis
        q[3:7] = [np.cos(lean / 2), 0.0, np.sin(lean / 2), 0.0]   # 繞 y 軸前傾

        joints = {}
        for side, sign in (("l", +1), ("r", -1)):
            hip = pelvis + np.array([0.0, sign * self.hw, 0.0])
            target, _ = self.foot_target(side, t)
            roll, hp, kn, ap = self.leg_ik(hip, target, lean)
            joints[f"hip_roll_{side}"] = roll
            joints[f"hip_pitch_{side}"] = hp
            joints[f"knee_{side}"] = kn
            joints[f"ankle_{side}"] = ap

        # 手臂：與同側腿反相擺動
        amp = np.deg2rad(g.arm_swing_deg)
        joints["shoulder_l"] = -amp * np.cos(2 * np.pi * phi)
        joints["shoulder_r"] = +amp * np.cos(2 * np.pi * phi)
        elbow_base = 0.5 if g.mode == "walk" else 1.2   # 跑步時手肘彎更多
        joints["elbow_l"] = elbow_base + 0.15 * np.cos(2 * np.pi * phi)
        joints["elbow_r"] = elbow_base - 0.15 * np.cos(2 * np.pi * phi)

        for i, name in enumerate(JOINT_ORDER):
            q[7 + i] = joints[name]
        return q
