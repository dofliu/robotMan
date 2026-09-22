"""Capture-point（ICP／DCM）落腳法則行走控制器——Raibert 的單因子對照組。

與 RaibertController 的差異**只有兩個法則**；其餘（觸地相位重置、支撐腿
任務空間 IK、擺動軌跡、PD＋重力前饋、髖姿態修正、加速換步、所有落點
限制與末段鎖定）逐字沿用，透過 RaibertController 的三個 hook 覆寫：

1. 落腳點（_foot_placement）：不用「中性點 + k·(v − v_des)」啟發式，
   改放在瞬時 capture point ξ = c + ċ/ω0 後方一個固定 DCM 偏移 b 處——
       b_x = v_des·T / (e^{ω0·T} − 1)     LIPM 等速步行的解析解
       b_y = d_y  / (e^{ω0·T} + 1)        左右交替支撐的側向偏移
   下一步觸地時 CP 會回到同一個相對位置；步速由 b 決定，不靠回授增益。
2. 踝策略（_ankle_strategy）：不用速度誤差，改用 CP 相對支撐腳的偏差
       e = (ξ_x − p_stance_x) − v_des/ω0
   以 −k_a·e 驅動支撐踝（LIPM 等速時 CP 恆超前支撐腳 v/ω0）。

出處：capture point — Pratt, Carff, Drakunov, Goswami 2006；DCM 偏移解析式 —
Englsberger, Ott, Albu-Schäffer 2011／2015。**這不是新方法**：它是把教科書
上的模型式法則放進同一套堆疊，當 Raibert 啟發式的對照組。

c 以骨盆位置代替質心（與 RaibertController 的 cp 遙測同一近似）。
增益在第一次執行前寫死於 GAINS，未依任務結果調整；若日後調整，需另立
版本並揭露每一次迭代。
"""

import numpy as np

from controller_raibert import RaibertController

# 第一次執行前定死；Raibert 的踝增益是 70 N·m per (m/s) 速度誤差，
# CP 誤差的量綱是 m，等速時 e ≈ Δv/ω0（ω0 ≈ 3.4 s⁻¹），故 120 N·m/m
# 對應約 35 N·m per (m/s)——刻意比 Raibert 保守，不是等效換算。
GAINS = {
    "k_ankle_nm_per_m": 120.0,
    "ankle_clip_nm": 35.0,          # 與 RaibertController 相同
    "lateral_spacing_m": None,      # None → 2·hw（髖寬）
}


class CapturePointController(RaibertController):
    def __init__(self, model, cfg, gait, lean: float):
        super().__init__(model, cfg, gait, lean)
        self._cp_dbg = (np.zeros(2), 0.0, 0.0)

    def set_mode(self, mode: str, engine=None):
        if mode == "walk":
            # 與 RaibertController.set_mode 的狀態初始化逐項相同，只換訊息。
            self.state = "WALK"
            self._stop_start_t = None
            self._walk_start_t = self.t
            self.phase = 1.0
            self.n_steps = 0
            self.decide("mode", "🎯 Capture-point 落腳：ξ = c + ċ/ω0，偏移 b 取 LIPM 解析解", "mode", 0)
        else:
            super().set_mode(mode, engine)

    # ------------------------------------------------------------------

    def _dcm_offsets(self, v_des: float, omega0: float) -> tuple[float, float]:
        T = self.T_step
        e = float(np.exp(omega0 * T))
        b_x = v_des * T / max(e - 1.0, 1e-6)
        d_y = GAINS["lateral_spacing_m"] or 2.0 * self.hw
        b_y = d_y / (e + 1.0)
        return b_x, b_y

    def _foot_placement(self, *, pelvis, v, v_des, omega0, swing, sign_sw, hip_sw_y, neutral_x) -> np.ndarray:
        xi = pelvis[:2] + v[:2] / omega0
        b_x, b_y = self._dcm_offsets(v_des, omega0)
        self._cp_dbg = (xi.copy(), b_x, b_y)
        # 落點限制（可及範圍、最小左右間距、末段鎖定）在 compute() 內沿用 Raibert 的。
        return np.array([xi[0] - b_x, xi[1] + sign_sw * b_y, self.ankle_h])

    def _placement_note(self, *, adj, v, v_des, omega0) -> None:
        xi, b_x, _ = self._cp_dbg
        lead = xi[0] - self.stance_ankle[0]
        if abs(adj) > 0.06 or abs(v[1]) > 0.25:
            self.decide(
                "cp",
                f"🎯 CP 落點：ξ 超前支撐腳 {lead*100:+.0f} cm，b_x {b_x*100:.1f} cm，相對中性點 {adj*100:+.0f} cm",
                "strategy", 0.8,
            )

    def _ankle_strategy(self, *, pelvis, v, v_des, omega0) -> float:
        xi_x = pelvis[0] + v[0] / omega0
        e = (xi_x - self.stance_ankle[0]) - v_des / omega0
        lim = GAINS["ankle_clip_nm"]
        return float(np.clip(-GAINS["k_ankle_nm_per_m"] * e, -lim, lim))
