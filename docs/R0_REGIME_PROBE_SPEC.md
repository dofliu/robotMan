# R0 Regime Probe：以截斷 horizon 尋找無 censoring 的比較

最後更新：2026-09-11 ｜ Protocol ID：`R0-REGIME-HORIZON-PROBE-V1` ｜ Publication gate：`PUB-A2`（Track A taxonomy 補格）

狀態：`FROZEN_BEFORE_EXECUTION`（本文件在任何 horizon 搜尋之前 commit；搜尋規則、grid、門檻與結果標籤全部在看到任何截斷值之前固定）

證據等級：`PILOT / DEVELOPMENT / SIM_ONLY_MUJOCO / NOT_PREREGISTERED_INTERNALLY_FROZEN`

---

## 1. 這份 probe 要回答什麼

[TRACK_A_REFRAME §3](TRACK_A_REFRAME_2026-09-09.md) 的 censoring regime taxonomy 有六格，其中五格已有量測實例，**只有 `R0`（兩臂皆 full exposure、點識別）是空的**，該列目前寫的是「未觀察到」。

一個空格對 A-C3 有兩種可能的意義，而目前無法分辨：

1. R0 只是還沒被量到——換一個較容易的設定就會出現；或
2. R0 在這類比較中**本來就難以達到**——因為讓兩臂都跑完全程的設定，往往同時讓 primary metric 退化成無法表達對比。

[INFERENCE] 這兩種意義對論文的結論完全不同。若是第 2 種，那正是 A-C3「censoring regime 是一個不受控的設計變數」最強的證據：regime 不是分析者可以自由選的。因此**這個 probe 的負面結果與正面結果一樣有資訊量**，這也是它值得做的理由。

### 1.1 核心張力（本 probe 的設計主軸）

R0 與 non-degeneracy 互相拉扯：

- 截得**夠早** → 沒有 episode 跌倒 → 滿足 full exposure，但該窗口幾乎全在 `INITIAL_STAND` / 起步暫態，reference 的 saturation 接近 0 → **metric 退化**，artifact 依定義不可能出現。這正是 Hopper probe 落入的 `R5`。
- 截得**夠晚** → metric 非退化，但早期終止回來 → 又變成 `R2`／`R3`。

[SOURCE] `SECONDCASE-V3-BUDGET-PROBE-HOPPER-V1` 的 adequacy rule **只檢查 exposure、不檢查 metric 非退化**，因而選中一個 saturation `2.712%` 的站立 reference；該缺口被記錄為 blocker 而非就地修補（[SECOND_CASE_V2_BUDGET_PROBE_RECEIPT §7](SECOND_CASE_V2_BUDGET_PROBE_RECEIPT_2026-09-08.md)）。本 probe 是**第一個實作 A-C3 兩段式 reference-adequacy 前置條件的 artifact**：exposure 與 metric 非退化必須同時成立。

---

## 2. 揭露

[BLOCKER] 本 probe **在已看過的 DEVELOPMENT 資料上執行**，據實揭露如下，不得在稿件中淡化：

1. 資料是 `SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1` 的 450 個 retained evaluation episodes。那批 seeds（`18000–18029`）已 `DEVELOPMENT_EXHAUSTED`，其全 horizon 結果已被本專案作者檢視過。
2. 因此本 probe 的任何產出都是 **pilot**，不是 evidence，也**不構成** `PUB-A1b` 的替代品。
3. 本 probe 不做訓練、不做新評估、不動任何 seed、不存取 `19000–19029` 或 `20000–20029`。它是對既有 trace 的**唯讀重算**。
4. v7 line 的 `CONDITIONAL_ON_FIXED_WARM_START` 對本 probe 的一切產出永久成立：5 個 replicate 共用同一個不可重建的 v5 warm start。
5. 規則（grid、門檻、選擇規則、結果標籤）在**看到任何截斷 horizon 的數值之前**寫定並 commit。唯一在凍結前執行的量測是 §4.2 的重算恆等式驗證，它不涉及任何截斷 horizon。

---

## 3. 為什麼截斷 horizon 是合法的 regime 操作

[INFERENCE] 截斷 evaluation horizon 改變的是**估計目標（estimand）**，不是估計方法。在 horizon `H` 上，被估的量是「前 `H` 個 control step 內的 500 Hz saturation duty」，而不是 9 s 任務的 duty。這兩者是不同的量，**不可互相取代**。

這正是本 probe 對 A-C3 有用的原因：horizon 是評估設計者可以自由選擇、且標準文獻通常不報告的一個旋鈕，而它**直接決定比較落在哪一個 censoring regime**。能把同一批 policy、同一批 seed、只改 horizon 就在 regime 之間移動（或證明移不動），是 A-C3 最乾淨的示範。

[BLOCKER] 相對地，本 probe 的結果**永遠不可**寫成：v7 任何一臂在 9 s 任務上的表現、任何 task PASS、任何 controller 優越性、或對 `MOTION_TASK_SPEC` 的 11 項 criteria 的任何陳述。截斷 horizon 不產生任務通過，只產生另一個估計目標上的觀察。

---

## 4. 資料來源與重算恆等式

### 4.1 來源

| 項目 | 值 |
|---|---|
| 母 protocol | `SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1`，`sha256:9ab17c74ddb021f9b69b1df843f9fa49ea45ecf790837204270d8bc01046b359` |
| Retained summary | `backend/seed_variance_evidence/2026-09-08/analysis/seed_variance_summary.json`，`sha256:42b4cfac2ffff47b922c2ffe8f74492a7310e5cdb637bde1201084e365027965` |
| Arms | `V7A_REWARD_ONLY`（reference）、`V7B_REDUCED_JOINT_ENVELOPE`、`V7C_FILTERED_ACTION` |
| 規模 | 3 arms × 5 replicates × 30 evaluation seeds = 450 episodes |
| Control rate | 50 Hz；full horizon 9.0 s = **450 control steps** |
| Saturation sampling | 500 Hz，即每 control step **10 substeps** |

### 4.2 重算恆等式（已在凍結前驗證）

每個 control step 的 trace 記錄 `saturation_substeps_over_threshold` 與 `saturation_substeps_total`。任意 horizon `H` 的 duty 定義為：

```
duty_pct(H) = round( sum(over_threshold[0:H]) / sum(total[0:H]) * 100.0 , 6 )
```

[RESULT] 在 `H = 450`（全 horizon）時，此式對 **450/450 episodes 與凍結的 `metrics.saturation_duty_pct` 完全相等**（差 < `1e-9`，6 位小數後相同），零不符。這確立了截斷計算與既有凍結指標使用同一個定義，不是另一套近似。

[RESULT] 抽取時另外量到三件事，均寫入索引供日後核對：`saturation_substeps_total` 在全部 `158,338` 個 control step 上恆為 `10`，因此索引只需保留逐步的 `over_threshold`；450 個 episode 的 `terminal_record_state` 全為 `COMPLETED`；`frozen_full_horizon_duty_pct` 無一為 null，包含 `outcome_state` 為 `NULL` 的 V7C episodes——這與 audit 的發現一致：outcome 狀態與 metric 是否存在是兩件不同的事。

[BLOCKER] 此驗證**只在 `H = 450` 執行**，不涉及任何截斷值，因此不構成對結果的預先窺看。抽取與驗證均在本規格 §6 的規則寫定之後進行。

### 4.3 版本控制前置（`R0-PRE-01`，必須在搜尋之前完成）

[BLOCKER] `control_step_trace` 只存在於 **gitignored** 的 `backend/rl/artifacts/`，而本執行環境是可回收的暫時容器。若容器被回收，這批 trace 與其 `policy.zip` 將**永久消失**——與 v4 artifact 毀掉 v7 provenance 的機制完全相同，且因 warm start 不可重建而無法重跑復原。

因此執行順序的第一步**不是**搜尋，而是把分析所需的最小充分統計量抽出並納入版本控制：

- 產出 `backend/r0_probe_evidence/2026-09-11/horizon_trace_index.json`（`R0_HORIZON_TRACE_INDEX_V1`），對 450 個 episode 各保留：`arm_id`、`replicate_index`、`training_seed`、`evaluation_seed`、實現的 control step 數、逐 control step 的 `saturation_substeps_over_threshold[]`（共 `158,338` 個值），以及 `terminal_record_state`、`outcome_state` 與凍結的全 horizon duty。`saturation_substeps_total` 因恆為 `10`，以頂層純量 `substeps_per_control_step` 記錄一次，不逐步重複。
- 每個來源檔的 SHA-256 在抽取時與母 bundle `raw_replicates.json` 內retained 的 `evaluation_output_sha256` 逐一比對，並寫入索引供分析時再次比對。
- 保留原始 `terminal_record_state` 與 `outcome_state`，使 method failure 與 censoring 仍然可分離。

[RESULT] 抽取已於 2026-09-11 完成：15 個來源檔的 digest **全部命中**母 bundle 的 retained 值（15/15，零不符），涵蓋 450 個 episode、`158,338` 個 control step，索引 `1,272,160` bytes。

[INFERENCE] 保留逐步陣列**不等於選定 horizon**：它保存的是輸入，任何 horizon 規則都能事後從它精確重算。選擇規則另行凍結於 §6。

---

## 5. 定義

### 5.1 截斷曝露（不得與 audit 的標籤混用）

[BLOCKER] audit contract 的 `FULL_EXPOSURE` 是對 **9 s 任務**的判定。本 probe 使用**另一個名字**，避免兩個定義被混為一談：

> episode 在 horizon `H` 上為 `H_COVERED` ⟺ 其實現 control step 數 `≥ H`。

`H_COVERED` 只說明前 `H` 步被完整觀察到，**不主張**該 episode 完成了任務、也不主張其 9 s outcome 為 `OBSERVED`。

### 5.2 對比單位

分析單位維持母 protocol 的 **training replicate**（method-level 分母恆為 `5`）。`150` 與 `450` 為 **forbidden denominators**，與 `SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1` 一致。本 probe 為 pilot，不產生 method-level 估計；此條規範的是它所告知的未來 R0 protocol。

### 5.3 兩個獨立的對比

R0 是**成對**的性質，故兩個對比各自搜尋、各自出結果，不合併：

| 對比 | Reference | Candidate |
|---|---|---|
| `C_B` | `V7A_REWARD_ONLY` | `V7B_REDUCED_JOINT_ENVELOPE` |
| `C_C` | `V7A_REWARD_ONLY` | `V7C_FILTERED_ACTION` |

---

## 6. 凍結的搜尋規則

### 6.1 Horizon grid（凍結）

```
H ∈ {125, 126, ..., 450}   （control steps；共 326 個候選）
```

- **下界 `H = 125`（2.5 s）** 取自 [MOTION_TASK_SPEC](MOTION_TASK_SPEC.md) 的 phase 表：`STEADY_WALK` 自 2.5 s 起。`H < 125` 的窗口**完全不含任何 steady walk**，其 duty 由 stand→start 暫態主導，正是 reference 依構造接近退化的區域（即 R5 陷阱）。下界因此由設計常數決定，不由資料決定。
- **上界 `H = 450`（9.0 s）** 即完整任務 horizon。
- 下界亦滿足最小樣本要求：`125 × 10 = 1250 ≥ 500` 個 saturation substeps。

### 6.2 Adequacy rule `R0-P0`（兩段式，凍結）

對某個對比與某個 `H`，該 horizon 為 **adequate** ⟺ 下列兩項同時成立：

**`R0-P0a` 曝露（雙臂）**
> reference 的 150 個 episode **與** candidate 的 150 個 episode **全部** `H_COVERED`。

**`R0-P0b` 非退化（僅 reference）**
> reference 在 `H` 上的 150 個 episode duty 平均值 `μ_ref(H)` 滿足 `5.0 ≤ μ_ref(H) ≤ 95.0`（百分點）。

[INFERENCE] **`R0-P0b` 刻意只約束 reference，不約束 candidate。** 理由是 A-C3 的前置條件是關於「參照臂是否有能力表達對比」，不是關於對比是否存在。若對 candidate 也設下界，等於在結果上做選擇——candidate 的 duty 很低正是可能要被觀察到的**結果**，把它排除掉會製造選擇偏誤。這是 Hopper probe 缺口的正確修法，不是它的翻版。

**門檻取值的理由（凍結前寫定）：** 下界 `5.0` pp 嚴格高於被判定為退化的 Hopper reference（`2.712%`），又遠低於 v7 reference 的全 horizon 值（約 `36–38` pp），因此不預設答案。上界 `95.0` pp 確保「減少」不會被天花板截斷。

### 6.3 選擇規則（凍結）

> 在所有 adequate 的 `H` 之中，取**最大**的 `H`。

[INFERENCE] 取最大而非取「最好看」的，是為了讓規則與結果無關：最大的 adequate horizon 保留最多任務內容，且由 grid 唯一決定，不存在平手。

### 6.4 結果標籤（凍結、fail-closed）

| 標籤 | 條件 | 對 A-C3 的意義 |
|---|---|---|
| `R0_WINDOW_FOUND` | 至少一個 `H` 同時滿足 `R0-P0a` 與 `R0-P0b` | taxonomy 的 R0 格有了候選設定（仍為 pilot） |
| `R0_EXPOSURE_ONLY` | 存在滿足 `R0-P0a` 的 `H`，但其中**沒有任何一個**滿足 `R0-P0b` | R5 的形狀在 horizon 維度上重現：能讓兩臂都跑完，就必然讓 reference 退化 |
| `R0_NOT_REACHABLE` | 沒有任何 `H` 滿足 `R0-P0a` | 在此資料上 R0 完全不可達 |
| `R0_PROBE_METHOD_FAILURE` | 任一 contract 違反：trace 缺漏、digest 不符、`terminal_record_state` 非 `COMPLETED`、substep 總數與 control step 數不一致、或出現 method failure | 不是結果，是失敗；不得以任何方式降級為上面三者 |

[BLOCKER] `R0_EXPOSURE_ONLY` 與 `R0_NOT_REACHABLE` **是結果，不是失敗**，必須照登並寫進 Track A 的 taxonomy 討論。不得因為「沒找到」而重開一次放寬門檻的 probe——任何門檻變更都需要新的 protocol version，且該版本必須揭露它是在已知本次結果的情況下設計的。

---

## 7. Claim boundary

本 probe 的產出**只**支持：

1. 未來一份凍結 R0 protocol 的 horizon 選擇；
2. 一項關於「censoring regime 在 horizon 維度上是否可達」的觀察，用於 A-C3。

本 probe 的產出**不**支持（逐條，與 `STATUS.yaml.prohibited_claims` 並存）：

- v7 任一臂在 9 s 任務上的表現、優劣或 task PASS；
- 任何 controller superiority 或 method-level 結論；
- 任何 physical feasibility、safety、sim-to-real 或 actuator 陳述；
- 對 `MOTION_TASK_SPEC` 11 項 criteria 的任何判定；
- 把截斷 horizon 的 duty 與 9 s 的 duty 相比或混用。

---

## 8. 執行順序（順序不可反）

1. **`R0-PRE-01`**：抽出並納入版本控制 `horizon_trace_index.json`（§4.3），以 SHA-256 綁定。此步**不做任何截斷計算**。
2. **凍結**：本文件與機器可讀的 `backend/rl/r0_regime_probe_protocol.json` commit 並 **push**。
3. **執行**：在 clean source、且 `ENVIRONMENT-LOCK-V1` 驗證為 `MEASURED_ENVIRONMENT_LOCK` + `FULL_LOCK` 的前提下，對兩個對比各跑一次 §6 的搜尋。
4. **獨立重算**：以 `python -I -S`（stdlib-only、無 site packages）從 `horizon_trace_index.json` 重算並比對 bit-exact。
5. **Receipt**：記錄兩個對比的標籤、adequate horizon 集合的大小、選中的 `H`（若有）、以及所有 blocker。

[BLOCKER] 第 3 步之前不得執行任何截斷 horizon 的計算。若在第 1–2 步之間發現 trace 不足以支持本規格，正確處理是**記錄並停止**，不是就地放寬規格。

---

## 9. 驗收（`R0-01` .. `R0-08`）

| ID | 條件 |
|---|---|
| `R0-01` | `horizon_trace_index.json` 涵蓋全部 450 個 episode，且每個 episode 的 `sum(total[])` 等於 `10 ×` 其 control step 數 |
| `R0-02` | 每個來源 evaluation 檔的 `evaluation_output_sha256` 在分析時重新比對且相符 |
| `R0-03` | `H = 450` 的重算 duty 對所有 `terminal_record_state == COMPLETED` 且 duty 非 null 的 episode，與凍結的 `metrics.saturation_duty_pct` 6 位小數相等 |
| `R0-04` | grid、兩段式 adequacy 門檻與選擇規則的數值，與本文件 §6 及 protocol JSON 完全一致，且 JSON digest 已 pin |
| `R0-05` | 兩個對比各自輸出恰好一個 §6.4 的標籤；`R0_PROBE_METHOD_FAILURE` 不可與其他標籤併存 |
| `R0-06` | `python -I -S` 獨立重算與主分析 bit-exact |
| `R0-07` | 產出中不存在 `150` 或 `450` 作為 method-level 分母 |
| `R0-08` | receipt 明載 pilot 等級、`CONDITIONAL_ON_FIXED_WARM_START`、以及 §7 的 claim boundary |

---

## 10. 與其他文件的關係

- [TRACK_A_REFRAME §3](TRACK_A_REFRAME_2026-09-09.md)：本 probe 的目標是該表 `R0` 那一列；無論結果為何，該列都會由「未觀察到」改為有依據的陳述。
- [PUBLICATION_PLAN](PUBLICATION_PLAN.md)：屬 Track A，`PUB-A2` claim freeze 的輸入之一。不影響 Track B 的任何 gate。
- [MOTION_SCOPE_DECISION_2026-09-11](MOTION_SCOPE_DECISION_2026-09-11.md)：本 probe 是該決定中「唯一對學術軌道有直接幫助的加動作版本」的具體化——而它最終**不需要新增任何動作任務**，只需要重新解讀既有資料。
- [SECOND_CASE_V2_BUDGET_PROBE_RECEIPT §7](SECOND_CASE_V2_BUDGET_PROBE_RECEIPT_2026-09-08.md)：本 probe 沿用其 probe-as-pilot 紀律（cap／規則先凍、結果只能當 pilot、seeds 下游禁用）。

---

## 11. 凍結身分

| 項目 | 值 |
|---|---|
| 機器可讀 protocol | `backend/rl/r0_regime_probe_protocol.json`（`R0_REGIME_PROBE_PROTOCOL_V1`） |
| Horizon trace index | `backend/r0_probe_evidence/2026-09-11/horizon_trace_index.json`，`sha256:6ad44934232e110741a69879027ccc1f84c10ae4c63b0acf2877756af0d330c7`（`1,272,160` bytes、450 episodes、`158,338` control steps） |
| 母 protocol | `SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1`，`sha256:9ab17c74ddb021f9b69b1df843f9fa49ea45ecf790837204270d8bc01046b359` |

[BLOCKER] 本規格與 protocol JSON 的 digest 一旦 push 即為凍結基準。任何對 grid、門檻、選擇規則或結果標籤的變更都需要新的 protocol version，且新版本必須揭露它是在已知既有結果的情況下設計的。
