# Independent Training-Seed Variance DEVELOPMENT Specification

日期：2026-09-08

狀態：`FROZEN BEFORE IMPLEMENTATION / INTERNAL DEVELOPMENT ONLY`

Protocol：`SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1`
Machine-readable contract：
[`backend/rl/training_seed_variance_protocol.json`](../backend/rl/training_seed_variance_protocol.json)

前置 contract：`ENVIRONMENT-LOCK-V1`（[spec](ENVIRONMENT_LOCK_SPEC.md)）、
`AUDIT-V7-EXPOSURE-CENSORING-V1`（[spec](V7_EXPOSURE_CENSORING_AUDIT_SPEC.md)）

證據範圍：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`

## 1. 本次唯一 milestone

凍結一個 fresh DEVELOPMENT protocol，用**獨立 training replicates**估計 v7
action-interface 對比的 method-level variance。

`PILOT-V7-ACTION-INTERFACE-DEV-V1` 每臂只有一個 training seed（`8700`）。它
量到的是「固定 checkpoint 下的 evaluation-seed 變異」。
`AUDIT-V7-EXPOSURE-CENSORING-V1` 進一步證明 V7C 的 `0%` duty 是 exposure
artifact，而 V7B 的 paired bound 雖然 30/30 排除 0，aggregate 仍為 `NULL`。

這兩件事都不回答 method-level 問題：**換一個 training seed 重跑，同一個
action interface 還會給出同方向的效果嗎**？在本 protocol 執行前，V7B 的
sign 穩健性不得讀成 candidate selection，也不得當作 sample-size 依據。

本 spec 在任何 seed-variance source implementation 前凍結。

## 2. Frozen design

### 2.1 Arms

沿用 `PILOT-V7-ACTION-INTERFACE-DEV-V1` 的三臂與其 action math，不改任何常數：

1. `V7A_REWARD_ONLY`（reference）
2. `V7B_REDUCED_JOINT_ENVELOPE`
3. `V7C_FILTERED_ACTION`

V7C 已被 audit 判定 30/30 early-terminated、outcome 全 `NULL`。它仍必須執行：
把已知會截斷的 arm 移出設計，等於用結果決定樣本，屬於 selection on outcome。
它的 exposure censoring 由第 4 節的 identification bounds 原樣承接。

### 2.2 Independent training replicates

- `replicate_count = 5`（frozen）。
- Training seeds（frozen，與 v7 的 `8700` 及其 env range `8700–8711` 不重疊）：
  `8720`、`8740`、`8760`、`8780`、`8800`。
- 每個 replicate 的 12 個 vector environments 使用 `seed .. seed+11`，因此
  env blocks 為 `8720–8731`、`8740–8751`、`8760–8771`、`8780–8791`、
  `8800–8811`，兩兩不重疊。
- 三臂在同一個 `replicate_index` 使用同一個 training seed，形成 replicate-level
  paired design。

[HYPOTHESIS] 共用 training seed 只是 variance-reduction **design device**。不同
action interface 的 trajectory 會立刻分歧，所以配對是否真的降低變異未知。
執行後不得宣稱已達成 variance reduction，也不得因為配對無效就改成 unpaired
再重報。Primary analysis 是 paired；unpaired 只能作為 secondary description。

- Requested budget 每 run `100,000` timesteps；因 `2048 × 12` rollout geometry，
  expected realized budget固定為 `122,880`，與 v7 相同。
- 總計算量為 `3 arms × 5 replicates × 122,880 = 1,843,200` timesteps，是 v7
  pilot（`368,640`）的 5 倍。此數字凍結於此，執行時不得以「算力不足」為由
  減少 replicate 數。

### 2.3 Warm start 與 conditional scope

所有 replicates 都從同一個 v5 checkpoint
`stand_start_walk_stop_0p7_phase_observable_v5`（bytes `1,983,126`，
SHA-256 `c548867fbd17c736d54c1b1598d2abed1c7cb2dd28c7d310ea6e86ac3b36718c`）
warm start，以維持與 v7 的可比性。

[BLOCKER] 因此本 protocol 估到的是
`training_replicate_scope = CONDITIONAL_ON_FIXED_WARM_START`：**在固定 v5
warm start 條件下，fine-tuning 階段 training seed 造成的變異**。它不包含
pretraining 本身的 seed 變異，因此**低估**完整 method-level variance。任何
sample-size 計算若使用本 protocol 的 between-replicate SD，必須同時標註此
低估方向。

### 2.4 Plant identity 與 model_builder 的 file drift

`backend/model_builder.py` 在 `geom_render_list` 修正後 SHA-256 由
`0beabfa2...` 變為 `09163a81...`，而 v7 protocol 仍 pin 舊值。本 protocol
因此改 pin **plant 本身**而非只 pin source file：

- `model_builder.build_mjcf(default_robot(), [], dynamic=True)` 產生
  `7594` bytes，SHA-256
  `fd0a191f35a7c50d186a104b3378a92acdb794e82606d7f0c9aca902c7eac9df`。

[RESULT] 用 v7 所 pin 的那一份舊 `model_builder.py` 重建同一個 MJCF，得到
**完全相同**的 `7594` bytes 與 `fd0a191f...`。那次修改只動到
`geom_render_list`，沒有觸及 `build_mjcf` 或 `make_model`。因此 plant 與
pilot 的 plant byte-identical，即使 source file identity 不同。

[BLOCKER] Plant identity 只建立在 MJCF content 層。它不證明 pilot 當時的
solver 行為相同，因為 pilot 沒有 environment lock record。

### 2.5 Evaluation

- 每個 `(arm, replicate)` 執行 deterministic evaluation 30 episodes。
- Paired evaluation seeds `18000–18029`（frozen），三臂與五個 replicates 共用。
- 因此 pair key 是 `(replicate_index, evaluation_seed)`，共
  `5 × 30 = 150` pairs per candidate。
- Terminal records 總數為 `3 × 5 × 30 = 450`。

[BLOCKER] `18000–18029` 在 v7 pilot 與 exposure audit 中都已被檢視過，本
protocol 再次使用它們。這組 seeds 自此為 `DEVELOPMENT_EXHAUSTED`，永遠不得
再充當 holdout。`19000–19029` 維持 retired，`20000–20029` 維持 sealed
FORMAL；本 protocol 任何讀取都是 structural failure。

### 2.6 Environment lock

- 第一個 training run 之前必須 capture 一份 `ENVIRONMENT-LOCK-V1` record，
  且 `lock_class = MEASURED_ENVIRONMENT_LOCK`、`lock_completeness = FULL_LOCK`。
- 之後每一個 training 與 evaluation run 之前都必須以該 record verify；任一
  `LOCK_MISMATCH` finding 即 structural failure，不得續跑或補跑。
- `threading_determinism` 必須為 `AMBIENT_THREADING_PINNED`（即
  `OMP_NUM_THREADS=1`）。Thread 數改變 floating-point reduction order，會把
  「seed 造成的變異」與「thread 造成的變異」混在一起，那正是本 protocol 要
  分離的東西。

[BLOCKER] `PILOT-V7-ACTION-INTERFACE-DEV-V1` 沒有 lock record，其
environment 狀態是 `ABSENT_UNRECOVERABLE`。因此本 protocol 的數值與 v7
receipt 的數值之間是
`cross_protocol_comparability = NON_VERIFIABLE_ENVIRONMENT`：兩者不得直接相
減、不得畫在同一條趨勢上，也不得用本 protocol 的結果「確認」或「推翻」v7 的
點估計。

## 3. Estimand 與 analysis unit

Primary outcome 沿用 `saturation_duty_pct`。

Method-level estimand：

```text
theta = E_replicate[ E_evaluation[ Y_candidate - Y_reference ] ]
```

外層 expectation 取在 independent training replicates 上，內層取在 evaluation
seeds 上。v7 pilot 只估了內層。

**Analysis unit 是 training replicate，不是 episode。** 這是本 protocol 最重要
的 frozen 約束：

1. 每個 `(replicate, arm)` 先聚合成一個 replicate-level 統計量。
2. Paired difference `d[r]` 定義在 replicate 上。
3. Method-level 統計量的分母是 `replicate_count = 5`，**不是**
   `5 × 30 = 150`，也不是 `450`。

把 150 個 episode-level pairs 當成 150 個獨立單位是 pseudo-replication：它會
把 evaluation-seed 變異冒充成 training-seed 變異，並讓標準誤縮小約
`sqrt(30)` 倍。任何路徑上出現 episode-level 分母即 structural failure
（`PSEUDO_REPLICATION_FORBIDDEN`）。

輸出的 variance components：

- `between_replicate_sd`：`d[r]` 在 `r = 1..5` 上的 sample SD（`df = 4`）。
  這是未來 sample-size 決策唯一需要的量。
- `within_replicate_sd`：每個 `(replicate, arm)` 內 episode-level sample SD，
  逐 replicate 保留並另報平均。
- `variance_ratio_between_over_within`：描述性比值。

[BLOCKER] `n = 5` 的 SD 本身有很大的不確定性，本 protocol 不量化它。若
`between_replicate_sd < within_replicate_sd`，那**不是**「training seed 不重要」
的證據，只是 5 個 replicate 下的一個觀測值。

本 protocol 不計 p-value，也不計 confirmatory confidence interval，與
`PILOT-V7-ACTION-INTERFACE-DEV-V1` 的 `NOT_COMPUTED_DEVELOPMENT_PILOT` 一致。

## 4. Exposure censoring 沿 replicate 向上組合

`AUDIT-V7-EXPOSURE-CENSORING-V1` 的語意原樣繼承，並且**必須逐層向上組合**，
不得在 replicate 層退回點估計。

1. Episode 層：沿用 audit 的 `COMPARABLE` /
   `EXPOSURE_CENSORED` / `METHOD_FAILURE_NOT_CENSORING` 三分類與其判準。
   Method failure（NaN、solver error、cancelled、required outcome 未觀測）
   **不是** censoring。
2. Replicate 層：若某個 `(replicate, arm)` 的 30 個 episodes 全部 comparable，
   `m[r][a]` 是 point value；只要有任一 episode 為 `EXPOSURE_CENSORED`，
   `m[r][a]` 變成 assumption-free worst-case bound `[lo, hi]`，用 audit 的
   full-horizon bound 定義計算。不做 complete-case deletion、不做 imputation。
3. Paired 層：`d[r] = [lo_candidate - hi_reference, hi_candidate - lo_reference]`。
4. Method 層：`theta_bound = [mean_r(lo_d), mean_r(hi_d)]`。Sign 只有在
   `theta_bound` 完全排除 0 時才 identified。

Fail-closed 規則：

- 只要有任一 `d[r]` 不是 point-identified，`between_replicate_sd` 輸出 `null`，
  reason `BLOCKED_PARTIALLY_IDENTIFIED_REPLICATE_DIFFERENCES`，且
  `sample_size_decision_input_ready = false`。SD 沒有定義在 interval 上，
  用區間中點代替就是 imputation。
- `sample_size_decision_input_ready = true` 需要同時成立：450 個 terminal
  records 齊全、該 candidate 的 150 個 pairs 全部 comparable、
  `between_replicate_sd` 為 point value、environment lock verify 通過。
- 以 v7 的實測結果推論，V7C 幾乎確定會落在 blocked 分支。那是**正確**輸出，
  不是失敗；不得為了讓 V7C 產生點估計而放寬 exposure 判準。

## 5. Selection：本 protocol 不做

`selected_candidate_arm_id` 在本 protocol 內恆為 `null`。

理由：本 protocol 的目的是**估計變異**，不是比較。用同一批資料先估變異再據以
選擇，會把選擇條件建立在被選中的雜訊上。Candidate selection 與 sample-size
decision 必須另立 protocol version，並在看到本 protocol 結果**之前**凍結其
決策規則。

`replicate_count = 5` 不得在看到結果後上調。看到結果再加 seed 是 optional
stopping；要加必須另立新 protocol version，並且新舊 replicates 不得混算。

## 6. Acceptance criteria

- `SV-01`：strict protocol identity；三臂 action math、warm start path/bytes/SHA
  與 v7 protocol exact 相同。
- `SV-02`：execution 前後 Git SHA 相同且 tracked worktree clean。
- `SV-03`：恰好 5 個 training seeds `{8720, 8740, 8760, 8780, 8800}`，env blocks
  兩兩不重疊，且與 v7 的 `8700–8711` 不重疊。
- `SV-04`：每個 `(arm, replicate)` 恰有 `18000–18029` 共 30 個 paired terminal
  records；總數 exact `450`；無 missing、duplicate、unexpected、retired 或
  sealed seed。
- `SV-05`：`ENVIRONMENT-LOCK-V1` record 為 `MEASURED_ENVIRONMENT_LOCK` +
  `FULL_LOCK` + `AMBIENT_THREADING_PINNED`，且每個 run 皆 verify 通過。
- `SV-06`：method-level 統計量的分母 exact 等於 `replicate_count`；任何
  episode-level 分母 fail closed。
- `SV-07`：`FAILED`、`CANCELLED`、negative、`NULL`、`NONFINITE`、`CENSORED`
  皆保留；無 complete-case deletion、無 imputation、無不利 case 重跑。
- `SV-08`：exposure censoring 依第 4 節逐層組合；partially identified 的
  replicate difference 使 `between_replicate_sd` 為 `null`。
- `SV-09`：輸出 between/within variance components 與 `theta_bound`，並保留
  `CONDITIONAL_ON_FIXED_WARM_START` 與 `NON_VERIFIABLE_ENVIRONMENT` 標註。
- `SV-10`：所有 bundle artifact 使用安全 relative path，bytes 與 SHA-256
  readback exact；missing/tamper/path escape 均 fail closed。
- `SV-11`：另一個 `python -I -S` stdlib-only process 由 raw replicate/episode
  rows exact 重建 summary。
- `SV-12`：receipt 維持 `selected_candidate_arm_id=null`、
  `method_level_power_ready=false`、`paper_data_ready=false` 與本 spec
  claim boundary。

`SV-01..SV-12` 全部通過才是完整 seed-variance evidence。全部 arms 都
performance FAIL 或全部 blocked 仍可構成完整負結果。

## 6.1 Amendment 01：driver identity（執行前）

日期：2026-09-08　狀態：`APPLIED_BEFORE_ANY_EXECUTION / NARROWING_ONLY`
ID：`SEEDVAR-AMENDMENT-01-DRIVER-IDENTITY`

[BLOCKER] **本 protocol 凍結時是無法執行的。** 凍結後首次嘗試執行才發現：

- `backend/rl/train_ppo.py` 對任何 v7 profile 硬性要求 `seed_base == 8700`
  （`V7_TRAINING_SEED_OR_ENV_COUNT_MISMATCH`），所以一個 v7 arm 永遠只能用
  pilot 那一個 training seed 訓練；
- `backend/rl/eval_policy.py` 只在 pilot evaluation 路徑上輸出
  `control_step_trace`，而該路徑又強制使用 pilot 自己的 artifact 目錄。

Freeze 當時把兩個 driver 都以 digest pin 住，卻沒有檢查它們**能不能**跑本
設計。這是 freeze 程序本身的缺陷，記錄於此而非事後淡化。

修正方式：兩個 driver 各增加一個**互斥**的 frozen identity。

- v7 training profile 必須且只能宣告一個 governing protocol
  （`pilot_protocol_id` 或 `seedvar_protocol_id`）；兩者皆宣告即
  `V7_PROFILE_AMBIGUOUS_PROTOCOL_IDENTITY`。因此沒有任何 profile 能同時滿足
  兩者而被任意一方回報。
- Replicate 的 training seed 由本 protocol 依 replicate index 解析，**永遠不能**
  由 command line 提供（`SEEDVAR_SEED_OVERRIDE_FORBIDDEN`）。
- Pilot branch 的檢查順序原樣保留：哪一個 rejection 先觸發本身就是可觀測行為。

新增的 frozen identifiers：profile 後綴 `_seedvar`、profile 欄位
`seedvar_protocol_id`、run id 形式 `<profile_id>-r<replicate_index>`、
CLI `--replicate-index`（training）與 `--seedvar-replicate-index`（evaluation）。

[INFERENCE] 另一個選項是另寫一支 seed-variance driver，完全不動 pilot 的
guard。但那會複製 PPO geometry、warm-start transplant 與 artifact 寫入；本
protocol 與 pilot 的可比性建立在這些**完全相同**而非「相似」之上，兩份副本
無聲分歧的風險更大。

本 amendment **不改變**：arms 與 action math、warm start identity、training
seed schedule 與 environment seed blocks、evaluation seed range、replicate
count、analysis unit 與 forbidden denominators、exposure censoring 組合規則、
以及禁止 selection。

被取代的 pin 值原樣記錄在 protocol JSON 的
`amendment.superseded_pins` 內。

## 7. Failure semantics

- Structural failure：invalid/duplicate-key/non-finite JSON、identity drift、
  environment lock mismatch、missing/duplicate/unexpected arm/replicate/seed、
  forbidden seed access、episode-level method-level 分母、path escape、
  bytes/SHA mismatch、replay mismatch。CLI exit `2`。
- Semantic blocker：training/evaluation 被中斷或取消、required outcome 明示
  未觀測、或 `between_replicate_sd` 因 partial identification 為 `null`。保留
  記錄與 reason，`sample_size_decision_input_ready=false`，CLI exit `1`。
- Complete evidence：450 個 records 齊全、identity/lock/replay 通過。即使
  全部 blocked 仍 exit `0` 並輸出 negative-result status。
- 任何 NaN/Infinity 不得寫成 JSON number；以 typed `NONFINITE` state 保留。

## 8. Claim boundary and theory check

[SOURCE] Patterson et al.（JMLR 2024）指出 agent RNG 與 environment RNG 是
不同的變異來源，method-level 結論必須在 independent runs 上取 expectation。
[SOURCE] Agarwal et al.（NeurIPS 2021）指出少量 runs 只報點估計會低估
statistical uncertainty。[SOURCE] Henderson et al.（AAAI 2018）與 Colas et al.
顯示 deep RL 的 seed 變異足以翻轉方向結論。[SOURCE] Manski 的 partial
identification 框架給出在缺失機制未知時的 assumption-free worst-case bounds。

[INFERENCE] 因此把 30 個 evaluation seeds 當成 30 個 training replicates 會
系統性低估 method-level 變異；而在 exposure 不等時，把 censored replicate 用
區間中點代入 SD 計算，等於用一個未經證成的 missing-at-random 假設換取一個
點估計。本 protocol 兩者都拒絕。

[RESULT] 本節只凍結 protocol，尚無 seed-variance result。

[BLOCKER] 沒有 independent pretraining-seed variance、full 11-criterion Live
evidence、actual Study A matrix、binary paired CI、project-wide immutable
storage、formal authorization、HIL、bench 或 robot evidence。

因此允許的結論只到：在此 frozen MuJoCo plant、固定 v5 warm start、frozen
task、5 個 independent fine-tuning training seeds 與 DEV evaluation seeds 下，
action-interface 對比的 replicate-level 變異呈現何種 conditional simulated
量級。不得宣稱 controller superiority、candidate selection、sample-size
adequacy、paper readiness、physical torque/thermal margin、安全、sim-to-real
或實體機器人效能。

Primary/official sources：

- [Empirical Design in Reinforcement Learning, JMLR 2024](https://www.jmlr.org/papers/v25/23-0183.html)
- [Deep RL at the Edge of the Statistical Precipice, NeurIPS 2021](https://proceedings.neurips.cc/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html)
- [Deep Reinforcement Learning that Matters, AAAI 2018](https://doi.org/10.1609/aaai.v32i1.11694)
- [How Many Random Seeds?](https://arxiv.org/abs/1806.08295)
- [Partial Identification of Probability Distributions, Manski 2003](https://link.springer.com/book/10.1007/b97478)
- [Stable-Baselines3 RL Tips](https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html)
