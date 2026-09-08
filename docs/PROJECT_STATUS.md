# 專案進度狀態報告

最後更新：2026-09-08 ｜ 對應 `STATUS.yaml` ｜ Development：`0.2.0-dev`

證據範圍：`SIM_ONLY_REDUCED_ORDER` / `NOT_PHYSICALLY_VALIDATED`

本文件是人類可讀的進度總覽。機器可讀的權威狀態在 [`STATUS.yaml`](../STATUS.yaml)；兩者不一致時以 `STATUS.yaml` 為準並修本文件。學術產出的規劃另見 [PUBLICATION_PLAN](PUBLICATION_PLAN.md)；工程路線另見 [ROADMAP](ROADMAP.md)。

## 0. 一頁摘要

- **`progress: 0`**。這不是筆誤：專案成熟度以 V&V gate 通過數計算，不以功能數計算。軟體與證據基礎設施做了很多，但**五道 V&V gate 一道都還沒過**，**九道 PDR gate 一道都不是 PASS**。
- **四個總開關全為 false**：`paper_data_ready`、`statistics_ready`、`method_level_power_ready`、`sample_size_decision_input_ready`。
- **量到一個站得住的方向性結果**：V7B（縮小 joint envelope）相對 V7A 的 500 Hz saturation duty，method-level identification bound `[-13.503408, -12.435259]` pp，排除 0、sign NEGATIVE、5/5 independent training replicates 方向可識別。**條件**：五個 replicate 共用同一個不可重建的 v5 warm start，此條件對 v7 line 永久成立。
- **推翻一個假結果**：V7C 原本看似 `-36` pp 的巨大改善，經 audit 量測確認為 exposure artifact（30/30 episode 在 horizon 的 35.4889% 早期跌倒），並跨 5 個獨立 seeds 完全重現。
- **下一個決策點在專案負責人手上**：是否授權 formal evaluation（見 [PUBLICATION_PLAN](PUBLICATION_PLAN.md) §5）。在授權之前，選擇規則不可執行、FORMAL seeds 不可存取、門檻不可調整。

## 1. V&V gates

| Gate | 狀態 | 已有 | 缺 |
|---|---|---|---|
| V0 Evidence & Provenance | `PARTIAL_IMPLEMENTED_NOT_PASS` | bounded fail-closed input contracts、`ANALYSIS_METRICS_V1`、run-level `PAPER_RUN_MANIFEST_V1`、artifact inventory/SHA-256、clean-source Git identity、`ENVIRONMENT-LOCK-V1` 可量測 environment identity（一份實測 record） | project-wide immutable artifact storage；**lock record 綁進每一條 pipeline 的 run manifest**；full raw artifact inventory；complete requirement registry；actual Study A matrix |
| V1 Plant & Numerical | `PARTIAL_IMPLEMENTED_NOT_PASS` | static double-support V4 16/14 exact；analytical fixture（passive single-support、centered 5 kg payload、4/2/1 ms grid）4/4 PASS，含 raw Jacobian stdlib-only replay | articulated dynamic、known pendulum、dynamic contact、energy balance、完整 solver／finite-difference convergence；receipts 皆 same-engine，fixture 非 articulated |
| V2 Actuator / Sensor / Estimator | `NOT_STARTED` | — | torque-speed/thermal envelope、joint limits、latency/noise、estimator |
| V3 Fair Benchmark & UQ | `FOUNDATION_SOFTWARE_PARTIAL` | experiment matrix validator、paired statistics/export contract、exposure-censoring audit、seed-variance contract（皆 synthetic + 部分實資料驗證） | actual Study A、binary paired CI（無 golden-case oracle）、external preregistration、formal authorization |
| V4 Subsystem Validation | `NOT_STARTED` | — | 任何 SIL/HIL/bench/robot evidence |

## 2. Paper Data Readiness gates

| Gate | 狀態 | 一句話 |
|---|---|---|
| PDR-0 Claim | PARTIAL | RQ 與 claim boundary 有；primary outcomes 未對 formal study 凍結 |
| PDR-1 Model evidence | PARTIAL | 見 V1 |
| PDR-2 Run identity | IN PROGRESS | 各層 identity 都能量測；**lock record 尚未綁進任何 run manifest**；v7 retained bundles 的 environment 為 `ABSENT_UNRECOVERABLE` |
| PDR-3 Raw integrity | IN PROGRESS | path/bytes/SHA-256 readback PASS；failure/NULL/censoring 全數保留 |
| PDR-4 Matrix completeness | SOFTWARE ONLY | validator 有，**actual Study A matrix 未跑** |
| PDR-5 Independent metrics | PARTIAL | 每一層都有 `python -I -S` stdlib-only exact replay；Study A outcomes 未覆蓋 |
| PDR-6 Statistics | SOFTWARE PARTIAL | continuous paired CI 有；censoring → identification bounds 有；**binary paired CI blocked**；**between-replicate SD 為 null** |
| PDR-7 Reproduction | SOFTWARE PARTIAL | synthetic 與 v7 raw→summary exact 重建；formal clean-checkout reproduction 未做 |
| PDR-8 Paper export | SOFTWARE PARTIAL | machine-readable table/figure inputs 有；無 formal data |

## 3. 總開關

| Flag | 值 | 為什麼 |
|---|---|---|
| `paper_data_ready` | false | 無任何 FORMAL_EVALUATION run |
| `statistics_ready` | false | 無 Study A 資料；binary paired CI blocked |
| `method_level_power_ready` | false | `between_replicate_sd = null` |
| `sample_size_decision_input_ready` | false | 同上；每個 replicate 至少一臂被 exposure censored |
| `selected_candidate_arm_id` | null | 選擇規則已凍結但不可執行（EP-01/02/03） |
| `pilot_planning_ready` | false | 無 eligible candidate |
| `preregistered`（selection rule） | **false** | 規則在看過結果後才寫，由 contract 強制揭露 |

## 4. 已量測的科學結果

全部為 `DEVELOPMENT` evidence、`SIM_ONLY_MUJOCO`。每一項都有 hash-bound receipt 與獨立 replay。

### 4.1 Action-interface 三臂（v7 line）

| Arm | 定義 | Pilot（seed 8700，30 DEV seeds） | Seed-variance（5 replicates × 30 seeds） |
|---|---|---|---|
| V7A `REWARD_ONLY` | direct normalized action，原 12-D range | saturation `36.2185185 ± 1.0328300%`，30/30 full exposure | 143/150 full、7 early（r2/r3/r4） |
| V7B `REDUCED_JOINT_ENVELOPE` | knee/ankle/shoulder/elbow target-offset range 對稱縮小 | `23.3896264 ± 1.0044698%`，paired B−A `-12.8288921 ± 1.0720320` pp，**4 negative episodes → ineligible** | 120/150 full、30 early；method-level bound **`[-13.503408, -12.435259]` pp，排除 0，5/5 sign-identified** |
| V7C `FILTERED_ACTION` | 加 `alpha=0.25` 一階 low-pass | 30/30 early fall、30 NULL outcomes | 0/150 full、150 early、150 NULL；bound `[-37.195407, +27.315704]` pp 含 0、0/5 |

[RESULT] 450 個 seed-variance episodes 全為 `COMPARABLE`（263）或 `EXPOSURE_CENSORED`（187），**零 method failure**。
[RESULT] Pilot 那個乾淨的 V7A reference（30/30 full）是 **seed 8700 的性質**，不是 V7A 的性質。
[INFERENCE] V7B 方向跨獨立 seed 穩健；但**方向可識別 ≠ 變異可估計**。`between_replicate_sd` 為 null 是因為 5 個 paired difference 全是 interval，sample SD 沒有定義在 interval 上。
[BLOCKER] `CONDITIONAL_ON_FIXED_WARM_START` 永久：見 §6.1。

### 4.2 Exposure-censoring audit（對 frozen pilot bundle 的 read-only 量測）

[RESULT] V7C 30 個 episode 在 `159.7000 ± 2.7687` steps（`3.08–3.30` s，horizon 的 `0.354889`）於 `STEADY_WALK` 中終止；其 0% duty 的 assumption-free full-horizon bound 為 `[0.0, 64.511111]`%，與 V7A `36.2185185`% 重疊；paired bound `[-36.2185185, +28.2925927]` 含 0，0/30 sign-identified。
[RESULT] V7B 的 3 個 censored episode（seeds 18015/18021/18023）`outcome_state` 全為 `OBSERVED`、六項 required numeric 皆有值。**`OBSERVED` 不蘊含 full exposure** —— 這是 audit 揭露的實測盲點，之後成為 selection rule `SEL-C2` 的依據。
[RESULT] Audit 僅由 trace 長度獨立還原出與 pilot 紀錄一致的跌倒 seed 集合，並正確把 stop-only 失敗的 18011 留在 full exposure。
[RESULT] Validity finding：recorded `command_phase` 採 end-of-step convention，與 contract 的 start-of-step schedule 差一個 control step；原樣保留，未修改資料。

### 4.3 Environment identity

[RESULT] 同一環境、同 1000 個 reciprocal：stdlib 順序相加得 `7.485470860550343`，`numpy.ndarray.sum` 得 `7.485470860550345`。兩者皆符合 IEEE 754。**這是「pin 版本號不足以重驗數值」的直接證據**，也是 `test_v1_analytical_suite.py::test_stdlib_replay_passes_exact_synthetic_fixture` 在此 lock 下記錄為失敗而非放寬的原因。

### 4.4 Motion task（v5 Live 500 Hz）

[RESULT] run `run-20260830t055847-rl_task_v5-b6c4781d` 通過 10/11 criteria，無跌倒；唯一失敗為 saturation duty `38.422222% > 30%`。門檻未放寬。

## 5. 已完成的證據基礎設施

| Contract | ID | 驗證程度 |
|---|---|---|
| Run manifest | `PAPER_RUN_MANIFEST_V1` | static/analytical/v7 bundle readback PASS |
| Experiment matrix | `EXPERIMENT_MATRIX_SPEC_V1` | synthetic 3/3 cells，FAILED/CANCELLED retention |
| Paired statistics/export | `PAIRED_STATISTICS_SPEC_V1` | synthetic 191 artifacts，exact replay；binary paired CI blocked |
| Action-interface pilot | `PILOT-V7-ACTION-INTERFACE-DEV-V1` | 實資料，14 artifacts / 109,520,182 bytes |
| Exposure-censoring audit | `AUDIT-V7-EXPOSURE-CENSORING-V1` | 實資料 + synthetic，AX-01..AX-12 |
| Environment lock | `ENVIRONMENT-LOCK-V1` | 一份實測 record，EL-01..EL-10，60 tests |
| Training-seed variance | `SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1` | **已執行**：1,843,200 timesteps、450 records、replay exact；SV-01..SV-12 |
| Candidate selection | `SELECT-V7-CANDIDATE-FORMAL-V1` | 凍結，rule self-check 通過，SEL-01..SEL-09，47 tests；**不可執行** |

共同性質：fail-closed；`NOT_REACHED`／`NOT_APPLICABLE` 永不等於 PASS；禁止 complete-case deletion；禁止 interval 補值；episode-level 分母為 enforced forbidden denominators；每層皆可由 `python -I -S` stdlib-only process exact 重建。

## 6. 開放 blockers（依根因分類）

### 6.1 Provenance（不可逆）

- v5 warm start 自 gitignored `backend/rl/artifacts/` 下的 v4 artifact（`.gitignore:31`）；v3/v4 在 repo 與磁碟皆不存在；v5 profile 記 `warm_start_policy_id: null` / `planned_timesteps: 2000000`，與 registry 的 `122880` 矛盾；選定 checkpoint 是在另一個 516,096-step run regressed 後選出。→ **`CONDITIONAL_ON_FIXED_WARM_START` 對 v7 line 永久成立**。矛盾刻意記錄不修（`training_profiles.json` 被 `SEEDVAR-AMENDMENT-01` pin 在已 merge 證據之後）。
- v7 兩個 retained bundle 的 environment 為 `ABSENT_UNRECOVERABLE` → `cross_protocol_comparability = NON_VERIFIABLE_ENVIRONMENT`：seed-variance 數值不得與 pilot 數值相減或並排成趨勢。

### 6.2 Exposure censoring（可解，但需要更好的 policy）

- 連 reference arm V7A 都只有 143/150 full exposure。要點識別 between-replicate variance，需要**能穩定跑完 9 s 任務的 policy**。v5 line 做不到（saturation duty 38.42%，v6 reward-only 無改善）。

### 6.3 Statistics

- binary paired CI：無 published golden-case oracle → `PAIRED_BINARY_CI_NOT_IMPLEMENTED_V1`。
- sample size：無 point-valued variance 可算。

### 6.4 Plant credibility

- V1 缺 articulated dynamic、pendulum、energy、solver convergence；V2 全缺。任何 controller 結論的 plant 可信度尚未建立。

### 6.5 Authorization 與 preregistration

- `EP-03` formal authorization 未取得。
- 只有 internal hash freeze，**無 external（OSF）preregistration**。
- 解除順序：**授權在前、解封在後**（`EP-01`/`EP-02` 的 sealed-seed guard 在授權前不得移除）。

### 6.6 工程

- UI：`development_compare_mode` 與 `dynamic_run_trace` 皆 `BROWSER_VISUAL_PENDING`；frontend 不獨立驗證 server config hash。
- Live：immutable live run identity 與 raw bundle 未實作。
- `requirements.txt` 仍只宣告 `>=` floors。
- 測試：1 failed / 640 passed；那一個是 `PRIMARY_CASE_RECEIPT_IDENTITY`，在具名 lock 下記錄為量測結果，未放寬。

## 7. Milestone 歷史

| 日期 | Milestone | 結果 |
|---|---|---|
| 2026-08-26 | V0 hardening、三機 Compare、RL registry | software receipts；blockers 保留 |
| 2026-08-29 | Dynamic run trace、Motion Task V1 | 500 Hz trace bridge；v1 task FAIL 保留 |
| 2026-08-30 | controlled stop、start/stop curriculum、v2–v6 iteration | v5 Live 10/11；saturation FAIL 保留；v6 negative control |
| 2026-08-31 / 09-02 | V1 raw Jacobian replay、analytical fixture | 16/14、4/4 exact；V1 仍 NOT PASS |
| 2026-09-03 / 09-05 | Experiment matrix、paired statistics contracts | synthetic PASS；不構成 scientific PASS |
| 2026-09-06 | v7 action-interface pilot | 3 arms × 30 DEV seeds；no candidate |
| 2026-09-08 | Exposure-censoring audit（frozen bundle） | V7C `-36` pp 確認為 artifact |
| 2026-09-08 | `ENVIRONMENT-LOCK-V1` | 實測 record；reduction-order 證據 |
| 2026-09-08 | `SEEDVAR` 凍結 → Amendment 01 → **執行完成** | V7B 方向 5/5；variance null |
| 2026-09-08 | Pretraining-seed variance 結案（不可量測）；`SELECT` 凍結 | 授權成為唯一前置 |
| 2026-09-08 | 文件重整；[PUBLICATION_PLAN](PUBLICATION_PLAN.md) 建立 | 學術產出路線凍結 V1 |
| 2026-09-08 | `PUB-A1` 第二案例凍結 → push → **執行完成** | `SECOND_CASE_ARTIFACT_REPRODUCED`；兩臂皆 censored，gate 未 PASS，需 V2 |

## 8. 下一步

兩條軌道並行，互不阻擋：

**學術（見 [PUBLICATION_PLAN](PUBLICATION_PLAN.md)）**

1. `PUB-A0` 文獻 novelty check：exposure censoring／partial identification 在 RL 評估中的既有工作。
2. `PUB-A1` V1 已執行（Walker2d-v5，見 [receipt](SECOND_CASE_EXPOSURE_CENSORING_EXECUTION_RECEIPT_2026-09-08.md)）；下一步凍結 V2：budget 提高到 reference 近乎 full exposure，使 censoring 不對稱。
3. 專案負責人決定 Track B 的 formal authorization 與 OSF preregistration。

**工程（見 [ROADMAP](ROADMAP.md) §9）**

1. 把 `ENVIRONMENT-LOCK-V1` lock record 綁進每一條 pipeline 的 run manifest（V0 具名 blocker）。
2. Compare / Dynamic trace 的 browser visual verification（Playwright）。
3. V1 articulated dynamic／pendulum／energy oracles。
4. 一條**有版控 artifact** 的新訓練線（Track B 的前置；同時是 §6.2 的解法）。

## 9. 測試現況

`backend/`：**1 failed / 640 passed**（2026-09-08，292.68 s）。失敗項為 `test_v1_analytical_suite.py::test_stdlib_replay_passes_exact_synthetic_fixture`（`PRIMARY_CASE_RECEIPT_IDENTITY`），與 §4.3 的 reduction-order 差異同源，記錄為量測結果、未放寬。
