# RL Policy 與再訓練操作說明

最後更新：2026-08-26

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

## 3. 固定速度 profiles

`backend/rl/training_profiles.json` 已定義三組 development profiles：

| Profile | Speed | Step length | Seed base | Current status |
|---|---:|---:|---:|---|
| `walk_0p4_fixed_v1` | 0.4 m/s | 0.20 m | 1400 | profile only / not trained |
| `walk_0p7_fixed_v1` | 0.7 m/s | 0.35 m | 1700 | profile only / not trained |
| `walk_1p0_fixed_v1` | 1.0 m/s | 0.50 m | 2000 | profile only / not trained |

三組已各完成 256-step pipeline smoke。Smoke artifacts 的 status 固定為 `PIPELINE_SMOKE_NOT_POLICY_EVIDENCE`，不可放入 policy registry、不可用來比較穩定性。

## 4. 執行新訓練

正式 development training 範例：

```powershell
python backend/rl/train_ppo.py --profile walk_0p4_fixed_v1 --run-id walk-0p4-seed1400-run01
```

快速 pipeline smoke：

```powershell
python backend/rl/train_ppo.py --profile walk_0p4_fixed_v1 --run-id smoke-walk-0p4-001 --smoke
```

每個 run 只寫入 `backend/rl/artifacts/<run-id>/`，包含 checkpoint、`policy.zip` 與 `run_manifest.json`。已存在的 run directory 會直接失敗，不覆寫；現有 `ppo_walk_final.zip` 也不再是 training output target。

完成 training 後仍不能直接升格為 deployable policy。至少要做 artifact validation、multi-seed evaluation、scenario coverage、failure retention，再由人工審查將候選 artifact 加入 policy registry。

## 5. 下一個 policy 形式

Command-conditioned multi-speed policy 會把目標速度加入 observation，並在 episode/curriculum 中抽樣 speed command。因 observation contract 與現有 47-D fixed-speed policy 不同，必須使用新的 policy type、registry schema fields 與 controller adapter；不可用改 label 的方式把舊 checkpoint 當成 multi-speed policy。
