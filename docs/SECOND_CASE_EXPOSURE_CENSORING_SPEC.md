# 第二案例：Exposure Censoring 在公開 benchmark 上的重現測試

最後更新：2026-09-08 ｜ Protocol ID：`SECONDCASE-EXPOSURE-CENSORING-WALKER2D-V1` ｜ Publication gate：`PUB-A1`

狀態：`FROZEN_BEFORE_EXECUTION`（本文件與 `backend/rl/second_case_exposure_protocol.json` 在任何 Walker2d 訓練或評估之前 commit）

證據等級：`DEVELOPMENT / SIM_ONLY_MUJOCO / NOT_PREREGISTERED_INTERNALLY_FROZEN`

## 1. 這份 protocol 要回答什麼

[PUBLICATION_PLAN](PUBLICATION_PLAN.md) Track A 的主貢獻 A-C1 是：early termination 是 rate 型 outcome 的 **exposure censoring**；naive 的 per-step 平均會條件於存活，可以主張一個 assumption-free 的 full-horizon identification bound 並不支持的方向。這件事在 v7 humanoid 上量到了（V7C 表面 `-36` pp 的「改善」，bound 含 0，跨 5 個獨立 seeds 重現）。

審稿人的第一個問題會是：**這是 v7 那條線的特例，還是機制本身？** 本 protocol 在一個公開 benchmark、不同 plant、from-scratch policy、零專案控制程式碼的環境下，測同一個機制。

它**不**測 Walker2d 走得好不好、**不**測 low-pass filter 是不是好設計、**不**對 v7 humanoid 做任何新主張。

## 2. 揭露

[BLOCKER] 本 protocol 是在 v7 的 exposure audit 與 seed-variance 結果**已知**之後寫的。它是 internal hash freeze，不是 OSF 預註冊。`preregistration.preregistered = false` 由 contract 強制，宣稱為 `true` 的版本無法載入。

freeze 的意義是：§5 的預測、§4 的所有門檻與常數，在任何一次 Walker2d run 之前固定；看到結果後不得調整。若需修改，只能以 narrowing-only、execution-before 的 amendment 記錄，與 [TRAINING_SEED_VARIANCE_SPEC](TRAINING_SEED_VARIANCE_SPEC.md) 的 Amendment 規則相同。

## 3. 設計

### 3.1 環境

| 項目 | 值 | 為什麼 |
|---|---|---|
| Env | Gymnasium `Walker2d-v5`，`make()` 不帶任何 kwargs | 公開、預設即有 `terminate_when_unhealthy=True`，early termination 是 benchmark 的**預設行為**，不是我們加的 |
| Horizon `H` | 1000 control steps（`max_episode_steps`） | Gymnasium 預設 |
| Control dt | 0.008 s（`frame_skip=4` × 0.002 s） | 預設 |
| Plant | `walker2d_v5.xml`，`sha256:6bed53a6…`，6 個 actuator，gear 100，ctrlrange `[-1, 1]` | 以檔案摘要 pin 住 plant；與 v7 的 MJCF-digest 作法一致 |
| Base obs | 17-D；wrapper 後 23-D | 見 3.2 |

### 3.2 兩臂與共用 action interface

兩臂跑**完全相同**的 wrapper 程式碼，唯一差別是一個常數 `alpha`：

```text
raw      = clip(policy_action, -1, 1)
applied  = alpha * raw + (1 - alpha) * previous_applied      # previous_applied = 0 on reset
obs_out  = concat(env_obs_17, previous_applied_6)            # 23-D, both arms
env.step(applied)
```

| Arm | `alpha` | 角色 |
|---|---|---|
| `W2D_A_DIRECT` | 1.0 | reference；`alpha = 1.0` 使 filter 退化為 identity |
| `W2D_C_FILTERED` | 0.25 | candidate；與 v7 `V7C_FILTERED_ACTION` 相同的 operator 與常數 |

兩臂都把 previous applied action 放進 observation，所以 observation 維度、network 形狀、程式路徑完全一致；這使「差別只在 alpha」成為可檢查的事實而不是敘述。

### 3.3 訓練

| 項目 | 值 |
|---|---|
| 演算法 | Stable-Baselines3 `PPO("MlpPolicy")`，CPU，`DummyVecEnv` × 1 |
| 超參數 | SB3 預設：lr `3e-4`、`n_steps 2048`、`batch 64`、`n_epochs 10`、γ `0.99`、λ `0.95`、clip `0.2`、ent `0.0`、vf `0.5`、max_grad_norm `0.5`；全數寫進 protocol，不依賴「預設」二字 |
| Budget | `301,056` timesteps = 147 × 2048；requested 等於 realized，contract 要求**精確相等** |
| Replicates | 5 個 independent training seeds `40000–40004` |
| Warm start | 無；from scratch |
| Checkpoint | 只用最終 checkpoint；沒有 selection |
| Threads | `torch_threads = 1`；environment lock 要求 `AMBIENT_THREADING_PINNED` |

Budget 的選擇理由：`301,056` steps 的 Walker2d PPO **尚未收斂**，policy 仍會跌倒。這是刻意的 —— 我們要的是「訓練中期、會 early terminate 的 policy」，而不是好 policy。若 P1（§5）不成立，代表 budget 選錯，結案為 uninformative，不得回頭調 budget 重跑當同一 protocol。

### 3.4 評估

| 項目 | 值 |
|---|---|
| Policy | deterministic |
| Seeds | `41000–41029`，30 個，**跨兩臂、跨 5 個 replicate 配對** |
| Trace | 每 control step 記 `raw_action(6)`、`applied_action(6)`、`saturated_joint_flags(6)`、`reward`、`terminated`、`truncated`；NPZ 保存並記 SHA-256 |
| Saturation | `|applied_j| ≥ 0.99` |
| Exposure | **只由 trace 長度決定**：`realized_steps == 1000 → FULL_EXPOSURE`，否則 `EARLY_TERMINATED`。不信任 `terminated` flag 單獨判定 |
| Outcome state | 所有 numeric 有限 → `OBSERVED`；否則 `NONFINITE`。**`OBSERVED` 不蘊含 full exposure** |

Seed 禁區（不得重疊）：v7 DEV `18000–18029`、retired HOLDOUT `19000–19029`、sealed FORMAL `20000–20029`、pilot training seed `8700`、seedvar training seeds `8720–8724`。

## 4. Estimands

Primary measurement：`saturation_duty_pct`。單位為 (control step, joint) pair；`H·J = 6000`。

對每個 episode `e`，realized steps `n_e`，saturated pairs `s_e`：

| 名稱 | 定義 | 性質 |
|---|---|---|
| naive rate | `100 · s_e / (n_e · 6)` | per-step 平均會報的數字；條件於存活 |
| full-horizon bound | `[100 · s_e / 6000, 100 · (s_e + (1000 − n_e)·6) / 6000]` | assumption-free；`n_e = 1000` 時退化為點且等於 naive |

**引理（在 [exposure_identification](../backend/exposure_identification.py) 以測試斷言）**：naive rate 永遠落在 full-horizon bound 內。所以 bound 排除 0 時 naive 差必同號；反之不成立 —— 這正是 artifact 的空間。

聚合（analysis unit = **training replicate**；分母 5；`30`／`60`／`150`／`300` 為 enforced forbidden denominators）：

1. **Cell**（arm × replicate）：30 個 episode bound 依 seed 升冪做 interval mean，lower/upper 各自 round 到 6 位。全 point 時才有 level SD。
2. **Replicate paired difference**：`[C.lower − A.upper, C.upper − A.lower]`，round 6 位；sign 只在整個區間同側時 identified。
3. **Method-level bound θ**：5 個 replicate difference 依 index 升冪 interval mean。
4. **Naive method-level**：5 個 replicate 的 naive paired mean（點值）→ mean、sample SD、雙尾 95% t-interval（df=4，`t = 2.776445`）。naive「**主張方向**」的定義：t-interval 排除 0。

Reduction order 與 rounding 階段與 `SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1` **完全相同**；`test_exposure_identification.py` 以 v7 retained evidence 做 bit-exact cross-check。

## 5. 預測與 falsifier（凍結）

**不預測 `C − A` 的方向。** 兩種方向都與假說一致；假說是關於 naive estimator，不是關於兩臂。

| ID | 陳述 | 若成立 | 若不成立 |
|---|---|---|---|
| **P1** censoring present | 至少 3/5 replicates 中，至少一臂的 FULL_EXPOSURE episode 數 < 30 | 進入 P2 | `SECOND_CASE_UNINFORMATIVE_NO_CENSORING`：全 full exposure 時 bound ≡ naive，什麼都不可能 disagree；本案例對 artifact 無話可說，照實記錄 |
| **P2** naive–bound disagreement（primary） | 給定 P1，method-level 上 naive t-interval 排除 0 **且** θ 含 0 | `SECOND_CASE_ARTIFACT_REPRODUCED` | 兩者同號且皆排除 0，或皆含 0 → `SECOND_CASE_NAIVE_AND_BOUND_AGREE`（artifact 在此 budget 沒有咬到；是 Track A generalizability 的**負結果**，照登）。θ 排除 0 而 naive 不排除 → `SECOND_CASE_BOUND_IDENTIFIED_NAIVE_UNCERTAIN` |
| — method failure | 任一 cell 訓練 FAILED 或任一 episode `NONFINITE` | — | `SECOND_CASE_BLOCKED_METHOD_FAILURE`：該 replicate 的 paired difference 為 `NULL`，replicate 保留、分母仍為 5、不發 method-level 決定 |
| **P3** OBSERVED ⇏ full exposure | 每個 EARLY_TERMINATED episode 的 `outcome_state` 都是 `OBSERVED` | A-C2 的描述性支持 | 只記錄；不是 gate |

另附描述性輸出（不進入決策）：每 replicate 的 naive sign 與 bound sign 對照表；兩臂各自的 exposure 分布。

## 6. 執行與證據契約

- **Clean git**：pre／post SHA 相同且 working tree 乾淨，否則 `SECONDCASE_SOURCE_GIT_NOT_CLEAN` 拒跑。
- **Environment lock**：每個 cell 執行前以 `ENVIRONMENT-LOCK-V1` 驗證 `MEASURED / FULL_LOCK / AMBIENT_THREADING_PINNED`，lock 的 `locked_sha256` 寫進 cell manifest。
- **Override 禁止**：budget、seeds、alpha、threshold 皆由 protocol 解析，CLI 不接受覆寫。
- **Bundle**：`raw_replicates.json`（canonical rows，不含 numpy 依賴）＋ per-episode NPZ ＋ `protocol` 副本 ＋ lock record；`summary.json` 由 stdlib-only 的 `python -I -S` replay 精確重建。
- **Fail-closed**：`NOT_REACHED` 不等於任何結論；method failure（`NONFINITE`、訓練或評估 exception）與 exposure censoring 分開保留；任一 cell 有 method failure 則該 replicate 的 paired difference 為 `NULL`，不刪 case、不補值。

## 7. Claim boundary

- 只支持：在 Walker2d-v5 預設 early termination 下，naive per-step saturation estimator 與 assumption-free bound 是否 disagree。
- 不支持：Walker2d 行走品質、low-pass filter 作為設計選擇的優劣、v7 humanoid 的任何新結論、physical actuator。
- DEVELOPMENT evidence；`paper_data_ready` 不因本 protocol 改變。

## 8. 驗收（SC-01..SC-08）

| ID | 條件 |
|---|---|
| SC-01 | protocol 載入即驗證：exact keys、`preregistered=false`、seeds 不落禁區、`requested == expected_realized` |
| SC-02 | raw bundle：5 replicates × 2 arms × 30 seeds，realized timesteps 精確相等，lock verified 旗標為 true |
| SC-03 | 每 episode bound 由 `(s_e, n_e, 6000)` 重算一致；naive 落在 bound 內 |
| SC-04 | method-level 分母恆為 5；任何 episode 分母 raise |
| SC-05 | P1/P2/P3 由 summary 決定，且 outcome label 只能是 §5 列出的五個之一 |
| SC-06 | `python -I -S` replay 與 summary bit-exact |
| SC-07 | 對 v7 retained evidence 的 cross-check bit-exact（`test_exposure_identification`） |
| SC-08 | 任一 cell method failure → 該 replicate difference `NULL` 並列入 retained blockers，method-level 不因缺 replicate 而改分母 |
