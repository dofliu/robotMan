# 行走控制器比較報告

> **LEGACY DEVELOPMENT SNAPSHOT / SIM-ONLY / NOT FORMAL EVIDENCE**
> 本檔保留 2026-08-25 的單一 nominal simulated protocol 輸出，未使用 frozen
> manifest、immutable raw bundle、multi-seed design、confidence interval 或實體量測。
> 下列數字只能用於 software regression 與教學敘事，不支持控制器普遍優劣、
> 實體 actuator 能力、實測抗推力或 sim-to-real claim。

- 測試條件：速度目標 0.7 m/s、步長 0.35 m、總重 50.9 kg、輔助平衡關閉
- 平地 simulated run 3 回合 × 10 s；抗推撞 = 行走 3 s 後施加 0.2 s simulated push，二分搜尋此特定 protocol 的 observed recovery threshold，不是硬體額定或實測最大推力
- 產生時間：2026-08-25 21:56

| 控制器 | 前進距離 | 存活時間 | 平均速度 | 跌倒率 | CoT | 抗推:後方 | 抗推:前方 | 抗推:側向 |
|---|---|---|---|---|---|---|---|---|
| 軌跡追蹤（開環） | 0.35 m | 1.6/10 s | 0.22 m/s | 100% | 1.30 | — | — | — |
| Raibert 閉環 | 0.95 m | 2.3/10 s | 0.41 m/s | 100% | 2.78 | — | — | — |
| RL 學習策略（PPO） | 7.40 m | 10.0/10 s | 0.74 m/s | 0% | 5.94 | 275 N | 338 N | 250 N |

## 解讀

- **軌跡追蹤（開環）**：時序開環、無落腳調整，為對照組 — 展示「為什麼需要閉環」。
- **Raibert 閉環**：觸地相位重置 + 線上落腳法則 + 世界座標腿方位控制。
  手調參數，姿態扭矩與支撐腿力耦合未解（需 QP/WBC 才能完全解耦）。
- **RL（PPO）**：以分析模式的運動學步態為模仿參考（DeepMimic-lite）+
  速度追蹤獎勵 + RSI 初始化；訓練環境使用目前模型的 D0 representative
  constant torque saturation，未以實體 motor torque-speed/thermal curve 校準。

RL 模型：`ppo_walk_final.zip`。本 legacy report 未記錄 checkpoint SHA-256、
environment lock 或完整 run identity，因此不可升格為正式 `[RESULT]`。
