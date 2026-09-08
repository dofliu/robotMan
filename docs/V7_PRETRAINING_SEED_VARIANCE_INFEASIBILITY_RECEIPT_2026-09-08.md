# V7 Pretraining-Seed Variance Infeasibility Receipt

日期：2026-09-08

主題：`SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1` 的
`training_replicate_scope = CONDITIONAL_ON_FIXED_WARM_START` 能不能被解除？

結論：**不能。對 v7 這條 line 而言，independent pretraining-seed variance
不可量測**，而且原因不是算力，是 provenance。

證據範圍：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`

## 1. 為什麼會問這個問題

`SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1` 的 5 個 replicate 共用同一個 v5 warm
start，因此它量到的是 **fine-tuning 階段** 的 seed 變異，並在 spec 第 2.3 節
明示這會系統性低估完整 method-level variance。

要解除該限制，需要用**多個獨立 pretraining seed** 各自產生一個 v5-等價的
warm start，再對每個 warm start 跑三臂 fine-tuning。算力上完全可行：
`5 pretraining + 15 fine-tuning = 20 × 122,880 = 2,457,600` timesteps，約是本
容器 25 分鐘。因此本次先檢查 provenance，而不是先跑。

## 2. 實際查到的事實

[SOURCE] `backend/rl/policy_registry.json` 對
`stand_start_walk_stop_0p7_phase_observable_v5` 的記載：

- `training_contract.algorithm = "PPO_PATH_STOP_PHASE_WARM_START"`
- `training_contract.total_timesteps = 122880`
- notes：「**Warm-started from the v4 local development artifact** with
  fail-closed 50-to-51D input expansion. The selected 122,880-step checkpoint
  passed DEV seeds 18000-18029 and HOLDOUT seeds 19000-19029 under the original
  50 Hz saturation sampler. … **A separate 516,096-step run regressed and
  failed DEV** due to one fall, stop, and lateral drift.」

[SOURCE] `.gitignore:31` 為 `backend/rl/artifacts/`。所有 training run 目錄
（含 v3/v4 的 local development artifacts）都不在版本控制內。

[RESULT] 版本控制中只有 3 個 policy artifact：

```text
backend/rl/ppo_walk_final.zip                                    (walk_0p7_legacy)
backend/rl/ppo_stand_start_walk_stop_0p7_curriculum_v2.zip       (curriculum v2)
backend/rl/ppo_stand_start_walk_stop_0p7_phase_observable_v5.zip (v5)
```

**沒有 v3，沒有 v4。** 本機磁碟上除了本次 seed-variance 的 15 個 replicate
policy 之外，也沒有任何 v3/v4 artifact。

[RESULT] `backend/rl/training_profiles.json` 對 v5 的記載與 registry **互相
矛盾**：

| 欄位 | training_profiles.json | policy_registry.json |
| --- | --- | --- |
| warm start | `warm_start_policy_id: null` | 「warm-started from the v4 local development artifact」 |
| budget | `planned_timesteps: 2000000` | `total_timesteps: 122880` |

Profile 完全沒有記錄那次 warm start —— 它是用當時的 `--warm-start-from` CLI
指向一個 local artifact 路徑完成的，而該路徑屬於 gitignored 範圍。

## 3. 為什麼這使 pretraining-seed variance 不可量測

[INFERENCE] 要在不同 pretraining seed 上重建「v5-等價的 warm start」，必須先
能重建 v5 自己的起點。三件事同時擋住：

1. **起點不存在。** v5 warm start 自 v4 的 local artifact，該檔從未進版本
   控制，現在也不在磁碟上。v4 本身 warm start 自 tracked 的 curriculum v2，
   所以 v1→v2→v4 的**形式**可重跑；但重跑出來的 v4 不是 v5 當初用的那一個
   v4，而沒有任何 frozen 記錄指出當初用的是 v4 的哪一個 checkpoint。
2. **Profile 不記錄它。** v5 的 profile 說 `warm_start_policy_id: null`。
   單看 frozen 的 training contract，v5 看起來是從零訓練的；那與 registry
   的敘述不符，而 profile 才是 driver 實際讀取的東西。
3. **停止點本身是一次 selection。** 被採用的是 `122,880`-step checkpoint，
   而同一條 line 另一個 `516,096`-step run **regressed 並且 DEV 失敗**。
   因此「跑到 122,880 步」不是一個 frozen budget，而是在看過多個 checkpoint
   之後選出來的。在新 seed 上照抄「取第 122,880 步」，等於把一次在舊 seed 上
   做過的 selection 當成一條規則。

[RESULT] 綜合以上：v5 artifact 的 SHA-256
`c548867fbd17c736d54c1b1598d2abed1c7cb2dd28c7d310ea6e86ac3b36718c` 無法從本
repository 重建，也無法證明任何新產生的 checkpoint 與它同源。

## 4. 這件事的後果，明確寫下來

[BLOCKER] `SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1` 的
`training_replicate_scope = CONDITIONAL_ON_FIXED_WARM_START` 對 v7 這條 line
是**永久的**，不是暫時的缺口。V7B 相對 V7A 的方向在 5 個獨立 fine-tuning
seed 上可識別，這個結論**永遠附帶「條件於那一個 v5 warm start」**，因為那個
warm start 的來源已不可回溯。

[INFERENCE] 唯一能量測 pretraining-seed variance 的做法，是另立一條**全程都
在版本控制內**的 pretraining line：從 tracked artifact 出發、frozen budget、
不做 checkpoint selection。但那樣得到的 warm start 不是 v5，其 fine-tuning
結果與 v7 pilot 及 `SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1` 都**不可比**，
`cross_protocol_comparability` 會是另一個 `NON_VERIFIABLE` 類別。那是一條新
line（v8 級）的工作，不是本 milestone 的延伸，因此本次不啟動。

## 5. 記錄而不修改 pinned contract

第 2 節的 profile/registry 矛盾是一個真實缺陷。本次**刻意不修改**
`backend/rl/training_profiles.json`：

[SOURCE] `SEEDVAR-AMENDMENT-01-DRIVER-IDENTITY` 已把
`training_profiles_source_sha256` pin 進
`backend/rl/training_seed_variance_protocol.json`，而該 protocol 的 digest 又
被 `backend/training_seed_variance_contract.py` pin 住，其下游是 2026-09-08 已
保留並已 merge 的 seed-variance evidence。

[INFERENCE] 改動 profile 會使那個 pin 失效，需要再一次 amendment，而且會讓
一份**已完成執行**的 evidence 的 source identity 需要重新解釋。用「修正
metadata」換「動搖已保留證據的 identity」不划算。因此把矛盾記錄在此、記錄在
`STATUS.yaml` 的 `v7_pretraining_reproducibility`，並把修正留給下一個會動到
training contract 的 protocol version 一併處理。

## 6. Claim boundary

[RESULT] 本 receipt 只陳述可重現性事實，沒有執行任何訓練，沒有產生任何新的
performance 數值，也沒有改變任何既有結論。

[BLOCKER] 它**不**解除、也不改變：`selected_candidate_arm_id=null`、
`sample_size_decision_input_ready=false`、`method_level_power_ready=false`、
`statistics_ready=false`、`paper_data_ready=false`。它使
`CONDITIONAL_ON_FIXED_WARM_START` 由「待補」變成「已知不可補」，這是**縮小**
可宣稱範圍，不是擴大。
