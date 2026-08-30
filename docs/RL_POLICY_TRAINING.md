# RL Policy 與再訓練操作說明

最後更新：2026-08-30

## 1. 現行 live 行為

目前 `RLWalkController` 在 live/compare mode 只執行 deterministic inference：每 20 ms 建立 observation，呼叫已載入 PPO policy 的 `predict(..., deterministic=True)`，再以 PD 轉成 torque command。它不在畫面操作期間呼叫 `learn()`、不更新 network weights，也不把 live episode 寫回 replay/training data。

因此，目前 RL 是「先前離線訓練完成的策略在模擬中執行」，不是每次開啟頁面即時學習。

## 2. 既有 policy 身分

`backend/rl/policy_registry.json` 是 `RL_POLICY_REGISTRY_V1`。預設 policy：

- ID：`walk_0p7_legacy`
- Artifact：`ppo_walk_final.zip`
- Training contract：0.7 m/s、step length 0.35 m、duty 0.62、clearance 0.07、PPO、30M steps
- 載入 gate：relative path confinement、file existence、bytes、SHA-256
- Evidence status：`LEGACY_RECONSTRUCTED_LOCAL_LOG_NO_FROZEN_ENVIRONMENT`

這個 evidence status 表示 checkpoint、舊 training code 與 log 還在，但當時沒有保留 immutable source/environment bundle；不可把 registry 補登誤解為完整重現。

## 3. Training profiles

`backend/rl/training_profiles.json` 使用 `RL_TRAINING_PROFILES_V3`，目前有三組 fixed-speed 與六組 Motion Task development profiles：

| Profile | Speed | Step length | Seed base | Current status |
|---|---:|---:|---:|---|
| `walk_0p4_fixed_v1` | 0.4 m/s | 0.20 m | 1400 | profile only / not trained |
| `walk_0p7_fixed_v1` | 0.7 m/s | 0.35 m | 1700 | profile only / not trained |
| `walk_1p0_fixed_v1` | 1.0 m/s | 0.50 m | 2000 | profile only / not trained |
| `stand_start_walk_stop_0p7_v1` | 0.7 m/s | 0.35 m | 2700 | 8M early-stop / failed speed-direction gate |
| `stand_start_walk_stop_0p7_curriculum_v2` | 0.7 m/s | 0.35 m | 3700 | registry + Live / lateral and saturation fail |
| `stand_start_walk_stop_0p7_path_efficiency_v3` | 0.7 m/s | 0.35 m | 4700 | 4M / lateral pass / 2 DEV falls |
| `stand_start_walk_stop_0p7_path_stop_v4` | 0.7 m/s | 0.35 m | 5700 | 0.5M fine-tune / 30 no-fall / 1 stop failure |
| `stand_start_walk_stop_0p7_phase_observable_v5` | 0.7 m/s | 0.35 m | 6700 | selected 122,880 steps / Live 10 of 11 / saturation fail |
| `stand_start_walk_stop_0p7_substep_saturation_v6` | 0.7 m/s | 0.35 m | 7700 | 122,880-step reward-only negative result |

所有新 environment 先經 256-step pipeline smoke。Smoke artifacts 的 status 固定為 `PIPELINE_SMOKE_NOT_POLICY_EVIDENCE`，不可放入 policy registry、不可用來比較穩定性。

`stand_start_walk_stop_0p7_v1` 使用 `HumanoidMotionTaskEnv`：episode 依 frozen 9 秒 task schedule 產生 stand、smooth start、steady walk、smooth stop 與 final stand command，並把 normalized forward-speed command 加入 observation。其 observation 為 48-D，與 legacy 47-D policy 不相容。

v1 從零開始的 run 在 unseen seeds 上收斂到向後移動，因此於 8M early-stop。v2 改用 registry-verified legacy gait warm start、47→48-D fail-closed input expansion、active-balance command envelope、forward progress reward 與 reverse penalty。v2 的 1,999,992-step checkpoint 已通過另一批 30 個 seeds：30/30 完成、steady speed 0.543235 m/s、steady progress 2.166154 m、final stand speed 0.096662 m/s。這仍只是 training-env development evaluation。

## 4. 執行新訓練

正式 development training 範例：

```powershell
python backend/rl/train_ppo.py --profile walk_0p4_fixed_v1 --run-id walk-0p4-seed1400-run01

python backend/rl/train_ppo.py --profile stand_start_walk_stop_0p7_curriculum_v2 --run-id start-stop-curriculum-seed3700-run02
```

快速 pipeline smoke：

```powershell
python backend/rl/train_ppo.py --profile walk_0p4_fixed_v1 --run-id smoke-walk-0p4-001 --smoke
```

每個 run 只寫入 `backend/rl/artifacts/<run-id>/`，包含 checkpoint、`policy.zip` 與 `run_manifest.json`。已存在的 run directory 會直接失敗，不覆寫；現有 `ppo_walk_final.zip` 也不再是 training output target。

完成 training 後仍不能直接升格為 deployable policy。至少要做 artifact validation、multi-seed evaluation、scenario coverage、failure retention，再由人工審查將候選 artifact 加入 policy registry。

## 5. Training Lab 與部署邊界

介面的「RL 訓練」頁只讀取 `/api/training/profiles` inventory，不會啟動 subprocess 或更新 policy。這避免誤觸長時間 GPU/CPU 工作，也讓每次 training 必須明確指定不重複的 run ID。

Live 目前可選 registry-gated v2 與 v5，兩者都是 deterministic inference，不會即時學習。v2 的 unchanged task 失敗於 lateral drift 與 saturation；v5 通過其他 10 項、失敗於 saturation duty。v6 artifact 因 DEV gate 失敗，未加入 registry。

原 evaluator 曾每 20 ms 只取一次 saturation，而正式 Motion Task 每 2 ms 取樣。現在 `RL_TRAINING_ENV_EVALUATION_V3` 會聚合所有 500 Hz physics substeps；舊的 50 Hz saturation PASS 已撤銷。完整數值與 seed reuse 規則見 [PATH_PHASE_SATURATION_TRAINING_RECEIPT_2026-08-30](PATH_PHASE_SATURATION_TRAINING_RECEIPT_2026-08-30.md)。

## 6. 下一個 policy 形式

目前 start/stop curriculum 已建立 48-D command-conditioned 與 51-D path/heading/phase-observable contracts。下一個 v7 將研究 torque-aware action interface；multi-speed policy、turn、terrain 與其他 primitive 仍需另立 profile/protocol version，不可改 label 冒充。v2 以前的完整數值見 [START_STOP_POLICY_TRAINING_RECEIPT_2026-08-30](START_STOP_POLICY_TRAINING_RECEIPT_2026-08-30.md)。
