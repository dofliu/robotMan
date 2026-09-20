# Start–Stop RL Policy Training Receipt

> 後續 v2 Live、v3–v6 與 500 Hz saturation evaluator 修正，見 [PATH_PHASE_SATURATION_TRAINING_RECEIPT_2026-08-30](PATH_PHASE_SATURATION_TRAINING_RECEIPT_2026-08-30.md)。本文件保留當時 training-env 結果，不代表後續 Live PASS。

日期：2026-08-30  
Evidence scope：`SOFTWARE_TRAINING_ENV_DEVELOPMENT_EVALUATION_ONLY`  
Physical validation：`NOT_PHYSICALLY_VALIDATED`

## 1. 訓練目標

任務固定為 `stand_start_walk_stop_v1`：1.0 s stand、1.5 s smooth start、4.0 s steady walk、1.5 s smooth stop、1.0 s final stand，目標速度 0.7 m/s。Legacy `walk_0p7_legacy` 保持不變，新的 policy 使用 48-D observation，最後一維為 normalized forward-speed command。

## 2. v1 失敗 run 與保留結果

`start-stop-seed2700-run01` 從零開始訓練，原規劃 50M steps。依預先設定的 unseen-seed gate 於 8M checkpoint early-stop：

| Checkpoint | Completion | Fall | Steady speed | Steady progress | Final stand speed |
|---:|---:|---:|---:|---:|---:|
| 2M | 100% | 0% | -0.089 m/s | -0.367 m | 0.099 m/s |
| 4M | 100% | 0% | -0.069 m/s | -0.291 m | 0.173 m/s |
| 6M | 100% | 0% | -0.090 m/s | -0.378 m | 0.217 m/s |
| 8M | 100% | 0% | -0.199 m/s | -0.830 m | 0.214 m/s |

v1 學到「不跌倒但向後移動」的局部策略。其 checkpoints、CSV log、evaluation JSON 與 `run_manifest.json` 均保留於 ignored runtime artifact directory；manifest status 為 `TRAINING_EARLY_STOPPED_FAILED_SPEED_GATE`，不可部署。

## 3. curriculum v2

新增 `stand_start_walk_stop_0p7_curriculum_v2`：

- 由 registry 驗證的 `walk_0p7_legacy` warm start；47→48-D input expansion 的新增 command 欄位以零權重初始化，其餘 tensor 必須完全同形，否則 fail closed。
- command action envelope 在 stand 使用對稱微蹲與 ankle/hip active balance，在 full command 保留既有 gait policy，在 start/stop 之間連續混合。
- velocity reward 由 0.6 提高為 1.2，新增 forward progress reward 0.35 與 reverse-motion penalty 0.8。
- planned budget 20M steps、12 environments、seed base 3700；實際因成功 gate 於 2M checkpoint early-stop。

65,536-step preflight 已把 final-stage speed 從未 fine-tune 的 1.366 m/s 降至 1.116 m/s，同時 steady speed 0.658 m/s、steady progress 2.626 m，證明學習方向正確但尚未停住。

## 4. 候選 policy 與 30-seed gate

Run：`start-stop-curriculum-seed3700-run01`  
Selected checkpoint：1,999,992 steps  
Candidate SHA-256：`d3e1fc41be570d19cabaa86a760f11e631f5a9970eb3844e481a983b20e3e8ad`  
Candidate bytes：1,964,161  
Evaluation seeds：17000–17029，deterministic inference

| Metric | Result | Frozen task threshold | Training-env gate |
|---|---:|---:|---|
| Completion rate | 100% (30/30) | complete 9.0 s | PASS |
| Fall rate | 0% | no fall | PASS |
| Mean steady speed | 0.543235 m/s | 0.35–1.05 m/s | PASS |
| Mean steady progress | 2.166154 m | ≥1.40 m | PASS |
| Mean final-stand speed | 0.096662 m/s | ≤0.15 m/s | PASS |
| Mean absolute command error | 0.120019 m/s | diagnostic | recorded |

30 seeds 均完成 9.0 s。可見最低個案仍為 steady speed 0.386024 m/s、steady progress 1.537300 m，沒有跌破相應門檻。

## 5. 證據邊界與下一步

上述是 matching Gymnasium/MuJoCo training environment 的 50 Hz deterministic development evaluation。它尚未經過 Live controller adapter、500 Hz Dynamic Run Trace、完整 11 項 Motion Task evaluator、disturbance/terrain/domain-randomization、independent training seeds 或實機測試。

因此候選狀態為 `TRAINED_CANDIDATE_AWAITING_LIVE_ADAPTER_2026_08_30`，未加入 `RL_POLICY_REGISTRY_V1`，也未替換 `walk_0p7_legacy`。下一步是建立獨立 48-D controller adapter 與 registry identity，然後用未修改的 `stand_start_walk_stop_v1` criteria 產生 failure-retaining 500 Hz trace receipt。
