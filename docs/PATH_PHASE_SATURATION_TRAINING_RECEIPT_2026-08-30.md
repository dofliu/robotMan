# Path、Phase 與 500 Hz Saturation 訓練回條

日期：2026-08-30  
證據範圍：`SOFTWARE_ONLY_MUJOCO_REALIZED_SIMULATION`  
結論：沒有 policy 通過全部 unchanged 500 Hz Motion Task criteria；所有失敗與 regression 均保留。

## 1. 版本化迭代

| 版本 | Observation / objective 變更 | 評估結果 | 判定 |
|---|---|---|---|
| v2 | 48-D：legacy state + speed command | Live drift `2.092011 m`、saturation `44.088889%` | FAIL |
| v3 2M | + lateral path、yaw；path/load reward | DEV lateral 11/30 pass | FAIL |
| v3 4M | 同 v3，full PPO resume | lateral 30/30 pass；2 falls near STOP | FAIL |
| v4 0.5M | 加強 STOP/final stability 與 fall penalty | 30/30 no-fall；seed 18028 stop `0.281222 m/s` | FAIL |
| v5 122,880 | + signed phase trend；由 v4 warm start | Live 10/11；saturation `38.422222%` | FAIL |
| v5 516,096 | 同 v5，較長 fine-tune | seed 18005 fall，stop/lateral regression | FAIL |
| v6 122,880 | 500 Hz substep saturation reward | DEV 1 fall；mean saturation `37.602434%` | FAIL |

## 2. v5 selected artifact 與 Live trace

- Policy ID：`stand_start_walk_stop_0p7_phase_observable_v5`
- Artifact：`backend/rl/ppo_stand_start_walk_stop_0p7_phase_observable_v5.zip`
- Bytes：`1,983,126`
- SHA-256：`c548867fbd17c736d54c1b1598d2abed1c7cb2dd28c7d310ea6e86ac3b36718c`
- Live run：`run-20260830t055847-rl_task_v5-b6c4781d`
- PASS：trace integrity、assist disabled、no fall、initial posture、steady speed `0.585712 m/s`、progress `2.345757 m`、stop speed `0.042144 m/s`、final posture/state、lateral drift `0.045858 m`。
- FAIL：saturation duty `38.422222% > 30%`。

500 Hz phase diagnosis：INITIAL `0%`、START `16.911%`、STEADY `67.15%`、STOP `34.533%`、FINAL `0%`。主要負載集中於 left/right knee，其次為 shoulder、elbow 與 ankle；不是只在 phase transition 發生。

## 3. Evaluator defect 與證據修正

舊 `eval_policy.py` 在每個 50 Hz control step 結束後只讀一次 actuator force；正式 Motion Task 則保存全部 500 Hz physics samples。此差異會漏掉 control step 內的 torque peaks。

修正後 `RL_TRAINING_ENV_EVALUATION_V3` 直接聚合每個 physics substep。v5 在 DEV seeds 18000–18029 的 500 Hz audit：

- 30/30 no-fall；speed、progress、stop、lateral 仍 PASS。
- mean saturation duty `37.571852%`。
- worst saturation duty `39.2%`。
- overall gate `FAIL`。

因此，原 50 Hz DEV/HOLDOUT saturation PASS 已撤銷。seeds 19000–19029 已被讀取，退役為 audit set，不再作為 future formal holdout。

## 4. v6 negative result

Run：`substep-saturation-v6-seed7700-from-v5-100k-run01`  
Artifact SHA-256：`48a2d791661882c42fdebdecf2bbd6f60bdf0da76ffb9729d98446df05a9d559`

v6 保留 v5 的 51-D observation 與 action contract，只加入直接對齊 500 Hz gate 的 duty/excess reward。DEV seeds 18000–18029 結果：completion `0.966667`、1 fall、mean/worst saturation `37.602434% / 39.450801%`，未改善主要問題，也造成 terminal stability regression。此 artifact 不提升到 policy registry。

## 5. 下一個 preregistered gate

v7 在寫 code 前先凍結三個 interface ablations：

1. v5 control interface + corrected 500 Hz evaluator（negative control）。
2. joint-specific action envelope，縮小高 saturation joints 的 target range。
3. action low-pass / rate-limit interface，測試 PD target discontinuity 的影響。

DEV/TUNE 固定使用 18000–18029。新的 sealed holdout 固定為 20000–20029，只能在單一候選通過 DEV 與 unchanged Live nominal task 後執行一次。WBC residual 組等待 V1/V2 gate，不與尚未驗證的 plant 混成 sim-to-real claim。

## 6. Claim boundary

這些結果可支持「在目前 MuJoCo model 與 frozen task 中，observation 與 action-interface design 會改變 failure mode」的研究假設；不能支持實體硬體 torque margin、熱安全、一般 controller superiority 或 sim-to-real performance。
