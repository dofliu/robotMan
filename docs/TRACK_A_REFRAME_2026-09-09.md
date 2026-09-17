# Track A 重構：從「第二案例重現 artifact」到「censoring regime 的評估效度研究」

日期：2026-09-09 ｜ ID：`TRACK-A-REFRAME-2026-09-09` ｜ 對應：[PUBLICATION_PLAN](PUBLICATION_PLAN.md) `PUBLICATION-PLAN-V2` ｜ 性質：**規劃文件 + `PUB-A2` claim freeze 草稿（未凍結）**

狀態：`TRACK_A_REFRAMED_V2 / PUB-A2_DRAFT_NOT_FROZEN / NO_MANUSCRIPT / paper_data_ready=false`

本文件記錄專案負責人於 2026-09-09 做出的決定（停止第二案例 V2 線、重構 Track A），並把重構後的論點、censoring regime 分類、每一條 claim 對應的 hash-bound evidence、不可宣稱清單、figure／table 計畫與剩餘 gate 寫成一份可以直接成為 `PUB-A2` claim freeze 輸入的草稿。規則與其他 spec 相同：每個數字都回指到一份 receipt 與 SHA-256；`[RESULT]`／`[INFERENCE]`／`[BLOCKER]` 標籤照用；pilot 永遠標為 pilot。

## 0. 決定

三個選項（詳見 [probe receipt §7](SECOND_CASE_V2_BUDGET_PROBE_RECEIPT_2026-09-08.md)）：(1) 照 probe V3 結果凍結並執行 Hopper protocol；(2) 加 reference-saturation 下限再開 probe V4；(3) 停止並重構 Track A。**專案負責人選擇 (3)。**

[INFERENCE] 選 (3) 的核心理由：原 `PUB-A1` 想在公開 benchmark 上「湊出」v7 那種不對稱 censoring 的形狀，但三次 probe 一起顯示，**一個比較落在哪一種 censoring regime，是 budget、recipe、plant 共同決定的、而標準評估流程既不控制也不報告的變數**。這件事本身就是 Track A 範圍內（量測程序）的發現，比再投入算力去達成某一個 regime 更誠實、也對讀者更有用。

## 1. 原 Track A 為什麼走不下去

[PUBLICATION_PLAN V1 §3.1](PUBLICATION_PLAN.md) 的 `PUB-A1` 出口條件是「在第二個 task／公開 benchmark 上，以凍結 protocol 重現 exposure-censoring artifact」。V1（Walker2d-v5）依凍結規則得到 `SECOND_CASE_ARTIFACT_REPRODUCED`，但當時的計畫在看到結果後**追加**了一個要求：reference 須近乎 full exposure，使 censoring 不對稱、與 v7 同構。為了滿足這個追加要求：

| 步驟 | 結果 | 出處 |
|---|---|---|
| Probe V1：Walker2d-v5、SB3 PPO 預設、上限 2,949,120 | `PROBE_NEGATIVE_MAX_BUDGET_REACHED`，360 個 probe episode 只有 1 個跑完 horizon | [probe receipt §1](SECOND_CASE_V2_BUDGET_PROBE_RECEIPT_2026-09-08.md) |
| Probe V2：同 plant、rl-zoo tuned recipe、上限 1,966,080 | `PROBE_NEGATIVE_MAX_BUDGET_REACHED`，240 個中 5 個，全在一個 checkpoint，之後退化 | [§3](SECOND_CASE_V2_BUDGET_PROBE_RECEIPT_2026-09-08.md) |
| Probe V3：Hopper-v5、tuned recipe、上限 1,966,080 | `PROBE_BUDGET_FOUND` 1,474,560；但 reference 是站立不動的 policy，saturation 2.71%（ck1／ck3 為 ≈ 0%） | [§4](SECOND_CASE_V2_BUDGET_PROBE_RECEIPT_2026-09-08.md) |

[RESULT] 三次 probe 都在 clean source、同一 `locked_sha256`（`sha256:93d23a27…`）下執行、0 mismatch；每一次的上限都在看到曲線前寫死，且**沒有一次被事後提高**。
[BLOCKER] Probe V3 暴露了凍結規則的缺口：adequacy 只檢查 exposure，不檢查 primary measurement 是否退化。若 ck2 也 ≥ 27/30，規則會在 491,520 就選出 saturation ≈ 0% 的 reference——對這種 reference，naive 與 bound 的 contrast **必然同號**，artifact 在數學上不可能出現（§3.6）。
[INFERENCE] 繼續走選項 (1) 等於明知規則不完整仍凍結；選項 (2) 是再一輪沒有成功保證的 pilot。兩者都在為一個**特定 regime** 付費，而不是在描述 regime 這件事。

## 2. 重構後的論點

**一句話：** 在 comparative evaluation 中，early termination 使 rate 型 outcome 成為 exposure-censored；naive per-step 估計條件於存活，可以主張 assumption-free full-horizon bound 不支持的方向；bound 是否有資訊、artifact 是否可能出現，取決於比較落在哪一種 **censoring regime**，而該 regime 由訓練 budget、recipe 與 plant 決定、通常不被控制也不被報告。本文提出 identification 框架、一個可移植的記錄層檢查（`OBSERVED ⇏ full exposure`）、一個必須同時檢查 exposure 與 metric 非退化的 reference-adequacy 前置條件，並以一個專案 plant 與一個公開 benchmark 上凍結 protocol 的量測、加上三個公開 benchmark 上的 pilot，給出五種 regime 的實例。

**論文對機器人什麼都不說。** 它不評 plant、不評 controller、不評 low-pass filter 的設計價值、不談 sim-to-real（[PUBLICATION_PLAN §6](PUBLICATION_PLAN.md) 的不可宣稱清單全部適用）。

## 3. Censoring regime 分類與已量測的實例

記號：`H` = frozen horizon；每個 episode 的 rate 型 outcome 在實現 exposure `h ≤ H` 上觀察；naive = 觀察到的 positive count／`h`；assumption-free full-horizon bound = `[positive／H, (positive + (H − h))／H]`（[V7_EXPOSURE_CENSORING_AUDIT_SPEC §4](V7_EXPOSURE_CENSORING_AUDIT_SPEC.md)）。引理：naive 恆落在 bound 內（`exposure_identification.py`，於 v7 450 個與 Walker2d 300 個 episode 上皆成立）。

| Regime | 定義（reference／candidate exposure；reference metric） | 已量測實例 | Bound 行為 | Naive 行為 | 對評估的意義 | 證據等級 |
|---|---|---|---|---|---|---|
| **R0** 無 censoring | 兩臂皆 full；reference metric 非退化 | **已觀察到（pilot，2026-09-11）**：[`R0-REGIME-HORIZON-PROBE-V1`](R0_REGIME_PROBE_RECEIPT_2026-09-11.md) 在**截斷 horizon** 上對兩個對比皆得 `R0_WINDOW_FOUND`——`C_B` 於 `H ≤ 414`（8.28 s，reference 平均 duty `40.262319` pp）、`C_C` 於 `H ≤ 152`（3.04 s，`22.089474` pp）。**不是第六個獨立實例**：同一批 450 個 episode 的重讀 | 點識別 | 與 bound 一致 | 標準統計即可 | PILOT，凍結規則，`python -I -S` replay bit-exact；`CONDITIONAL_ON_FIXED_WARM_START` |
| **R1** 不對稱 | reference 近乎 full；candidate 重度 censored；reference metric 非退化 | v7 `V7C − V7A`：pilot 30/30 vs 0/30（seed 8700）；seed-variance 143/150 vs 0/150 | 單側變寬；paired bound 含 0；pilot 0/30、seed-variance 0/5 sign-identified | 主張 `−36.2185185` pp（pilot）／θ `[−37.195407, +27.315704]` 含 0（seed-variance） | **artifact**：naive 偽造方向 | DEVELOPMENT，凍結 protocol，replay exact（×2） |
| **R2** 輕度 censoring、bound 有資訊 | 兩臂大多 full；candidate 少量 censored | v7 `V7B − V7A`：120/150 vs 143/150 | θ `[−13.503408, −12.435259]` pp 排除 0、寬 1.068149、5/5 sign-identified；**但** `between_replicate_sd` 無定義 | 一致 | bound **不是**永遠無資訊；**方向可識別 ≠ 變異可估計**，power／sample-size 被封鎖 | DEVELOPMENT，凍結 protocol，replay exact |
| **R3** 對稱重度 censoring | 兩臂皆重度 censored | Walker2d-v5 V1：300 個 episode 16 個 full；reference 4/5 replicates 30/30 早跌 | 兩側皆寬；θ `[−79.118, +55.913333]` pp 寬 135.031333、**構造上必含 0**、0/5 | 主張 `−28.795138` pp、95% t-interval `[−46.698919, −10.891357]` 排除 0 | **artifact**，但 bound 的無資訊是關於 reference 的事實、與 candidate 無關 | DEVELOPMENT，凍結 protocol，replay exact |
| **R4** 無可達的 adequate reference | 在凍結上限內 reference 從未達 adequacy | Probe V1（1/360 full 至 2.95M 步）、Probe V2（5/240 至 1.97M 步）——**pilot**；**`TRACKED-LINEAGE-TRAINING-V1`／`V2`（新增 2026-09-16）：0/30 × 5 replicate，於 `2,000,000` 與 realized `4,015,200` 兩個預算皆然——非 pilot，見 §3.7** | 任何在此 budget 下的比較都落在 R3 | 仍會產出數字 | 比較無法被設計成有資訊 | Probe 為 **pilot**（§6 第 2 條）；tracked lineage 為 **DEVELOPMENT，凍結 protocol，標籤由 contract runner 算出** |
| **R5** 退化 reference | reference full exposure，但 metric ≈ 0 | Probe V3 ck1／ck3（30/30、0.000–0.013%）、ck6（30/30、2.712%）——**pilot** | reference = 0 時 naive 與 bound 的 contrast 必同號（§3.6）；2.7% 時 artifact 需 candidate 的 naive 穩定低於 2.7 pp 才可能 | — | exposure-only 的 adequacy 規則會選出 artifact 不可能出現的 reference | **pilot** + 數學陳述 |

### 3.1 R1 的數字與出處

[RESULT] Frozen-bundle audit：V7C 30 個 episode 全部在 `159.7000 ± 2.7687` control steps（`3.08–3.30` s，horizon 的 `0.354889`）於 `STEADY_WALK` 終止；arm-level bound `[0.0, 64.511111]`% 與 V7A `36.2185185`% 重疊；paired bound `[−36.2185185, +28.2925927]` pp 含 0，30/30 pair sign 不可識別。→ [frozen bundle receipt](V7_EXPOSURE_CENSORING_AUDIT_FROZEN_BUNDLE_RECEIPT_2026-09-08.md)；`audit_summary.json` `sha256:74f6edfa7ed04615f2dff60bccc9f10e818ecdb4c12b8dfa480717f29dc0ce94`、`audit_receipt.json` `sha256:6da78e2856d6e9be7727ff0de91515ee40fd4717acd439215c220f3f2c8f4b97`、audit protocol `sha256:b15505b73f3745141c2dfa31cf57564b0863242949f5d1ad4d351dfb96dec6ce`。
[RESULT] Seed variance：V7C 在 5 個獨立 training seeds 上 150/150 early termination、150 NULL outcomes；θ `[−37.195407, +27.315704]` pp、寬 64.511111（與 pilot 的 full-horizon 寬度**相同**，因 exposure fraction 幾乎相同）。→ [execution receipt](TRAINING_SEED_VARIANCE_EXECUTION_RECEIPT_2026-09-08.md)；raw `sha256:0fe9c0b9e8cc81446f64c9522bb5c64ef5b1c4bc2ea054f3ef651ac859ff4535`、summary `sha256:42b4cfac2ffff47b922c2ffe8f74492a7310e5cdb637bde1201084e365027965`、receipt `sha256:bc8a5b059842df3c200e7498cc0e095beb713e10e3f6602e3734215545eec1a4`、protocol `sha256:9ab17c74ddb021f9b69b1df843f9fa49ea45ecf790837204270d8bc01046b359`、lock `sha256:93d23a2703adc86a1394eacf5dece8d7229fdf742857f1a271656aa1cfeac72d`、source `12bfddfc5143298d43db6b3a2e477c5e05e2856d`。
[BLOCKER] 兩份 v7 證據皆 `CONDITIONAL_ON_FIXED_WARM_START`（永久）；pilot 與 audit 的環境為 `ABSENT_UNRECOVERABLE`（lock contract 晚於它們）。R1 的 plant 是本專案的 reduced-order humanoid，不是公開 benchmark。

### 3.2 R2 的數字與出處

[RESULT] `V7B − V7A` 逐 replicate paired difference **下界** `−13.962963 / −12.630370 / −14.868148 / −11.750371 / −14.305186` pp（其平均即 θ 下界 `−13.503408`）；5 個上界皆 < 0（其平均即 θ 上界 `−12.435259`），故 5/5 sign-identified；`between_replicate_sd_pp = null`（`BLOCKED_PARTIALLY_IDENTIFIED_REPLICATE_DIFFERENCES`）。→ 同 §3.1 的 seed-variance receipt。
[RESULT] Pilot 的 3 個 V7B censored episode（seeds 18015／18021／18023）於 `FINAL_STAND` 終止（420／445／426 control steps），`outcome_state` 全為 `OBSERVED`、六項 required numeric 齊全。→ frozen bundle receipt。
[INFERENCE] R2 是對「bound 是否永遠無資訊」的直接回答：不是。它同時示範 partial identification 對 study design 的第二個後果——方向可識別時變異仍可能無定義，因此 formal sample size 無法規劃。

### 3.3 R3 的數字與出處

[RESULT] 300 個 episode：284 `EARLY_TERMINATED`、16 `FULL_EXPOSURE`；reference `W2D_A_DIRECT` median realized steps 178–376（8.0 s horizon 的 1.4–3.0 s）；5/5 replicates 的 naive paired diff 為負、bound 全部 `UNIDENTIFIED`；method-level naive mean `−28.795138` pp、SD `14.419184`、t-interval `[−46.698919, −10.891357]`；θ `[−79.118, +55.913333]`；outcome `SECOND_CASE_ARTIFACT_REPRODUCED`。**P3**：284/284 early episode 的 `outcome_state` 皆 `OBSERVED`。→ [execution receipt](SECOND_CASE_EXPOSURE_CENSORING_EXECUTION_RECEIPT_2026-09-08.md)；raw `sha256:0e9ceaf9a4c4defbe568e4849db48f5dfb2782c0c21b69a0039a36bca7bc143b`、summary `sha256:e6761b78644b0807bc18bf3791de679e2ebebb359d130d3d672ac063285d47ee`、receipt `sha256:3ceb8d1b20f435f327f5a6d201be7da86951d4ace93611cb2ee199ef3facd744`、protocol `sha256:45d1ec553a1124fd613f90a8034b27f10ef8f01f23a219cca216479fc4c5350c`、plant `walker2d_v5.xml` `sha256:6bed53a6cc3ca73c4fe8ac3486d3b4228927264a6454f4ef16d3eed3c58bc09d`、lock record `sha256:911b436231c8e0b1d7a3d07bca6894ce4c42c517c4a5cbbbdd0f9dff694ff631`、source `b683ddc363b1e040ba366c194430eba546e6ad22`。
[RESULT] Protocol 在任何 run 之前 commit 並 push（PR #7），不預測方向，中間無 amendment；CLI 無 override 旗標（測試固定）。
[INFERENCE] R3 是 R1 的鏡像：同樣的 estimator 分歧，但 bound 的寬度來自 reference 而非 candidate。兩者一起才完整描述 estimator——R1 說「naive 錯在哪」，R3 說「bound 在什麼條件下什麼都不能說、且那是正確的」。

### 3.4 R4（pilot）

[RESULT] Probe V1：`backend/rl/second_case_v2_budget_probe.json` `sha256:8f20535c43157169026ff26dcf7c825334e4889b8ed687b8e61477cc6bf01370`；結果 `sha256:76612f470c952501486efca32518d450424417406ab6553248e4496cff7ab021`；source `e11463482765aa774446a0aa59706bdc5d8a6700`；12 個 checkpoint、FULL/30 = 0 ×11、1 ×1；naive duty 44.6–62.9%。
[RESULT] Probe V2：`second_case_v2_budget_probe_v2.json` `sha256:70662db367b3dbaf8edbf18efa96a6e7faff4e6edfa43769ed0129728b7b36f7`；結果 `sha256:55a6220dce75f3ef2e788fe14889df7d5e8b1a4e042e9087038f399935f0bbad`；source `a6508ac3c292c6e4bec5dde56c1583460793c9a9`；8 個 checkpoint、FULL/30 = 0,0,0,**5**,0,0,0,0；naive duty 1.6–13.7%。
[BLOCKER] 兩個 probe 的凍結 claim boundary 是「只支持 V2 budget 的選擇」。稿件中可寫：「凍結的 budget-selection 程序在上限 X 內回傳 NEGATIVE」；**不可寫**「Walker2d-v5 的 PPO 站不穩」——那是關於 plant／recipe 的主張，需要新的凍結 protocol。Recipe 數值 `U_VERIFIED_FROM_MEMORY`。

### 3.5 R5（pilot）

[RESULT] Probe V3：`second_case_v3_budget_probe_hopper.json` `sha256:0e291db1bd4e3b8ebd16d9143d73a0a9b9c05580b965743f938b28bbd093a2ef`；結果 `sha256:dcc70c2407dbaa1a9cd50106d0a8b497572999b9f29ed541fa2d49654ae1c87e`；source `334efc391526d212c676960118a1379bed310732`；plant `hopper.xml` `sha256:3ce93a055ffdcd83c0c701d2400768e40d2cbb9532f3c4ae33377c27f8b39f9e`。曲線：FULL/30 = 30, 23, 30, 8, 30, 30；naive duty mean = 0.013, 0.000, 0.000, 6.968, 8.822, 2.712%；return median 1006–1014（≈ healthy reward × 1000，forward reward ≈ 0）。
[BLOCKER] 同 §3.4 的 claim boundary。可寫的是關於**規則**的事（§3.6），probe 只作說明。

### 3.6 R5 的數學陳述（不依賴資料）

設 reference 在每個 episode 皆 full exposure 且 positive count 為 0（rate = 0，點識別）。對任一 candidate episode：若其觀察到的 positive count > 0，則其 bound 下界 > 0，bound 與 naive 皆為 POSITIVE；若為 0，則 naive = 0（不主張方向）而 bound `[0, (H − h)／H]` 含 0。兩種情況下都不存在「naive 主張某方向而 bound 含 0」的組合。**因此 exposure-only 的 adequacy 規則可以選出一個 artifact 在數學上不可能出現的 reference**，而規則本身不會察覺。任何 reference-adequacy 前置條件必須同時要求 exposure 與 primary measurement 非退化（門檻須事先凍結）。

### 3.7 R4 的第二個實例：tracked lineage V1／V2（非 pilot，2026-09-16 併入）

原本 R4 只有兩個 probe 支撐，兩者都是 **pilot**——這是整張表裡證據最弱的一格。
`TRACKED-LINEAGE-TRAINING-V1`／`V2` 這條線是為了另一個目的（`PUB-B2`）執行的，但它量到的東西
**正好是 R4**，而且證據等級高得多：凍結 protocol、版控證據、標籤由 contract runner 在保留證據上算出。

[RESULT] **量測**（全部可由 repo 重算）：五個 scratch replicate（seeds `9100`／`9112`／`9124`／`9136`／`9148`），
在 `2,000,000` 步（V1）與續訓至 realized `4,015,200` 步（V2）兩個預算下，
**full exposure 一律 `0/30`，150 個 episode 一個都沒達到 `30/30` 門檻**。
V2 的 contract runner 輸出 `label = TL2_BUDGET_EXHAUSTED`、`replicates_attaining_threshold = 0`、
`threshold = 30/30`、`pub_b2_pass = false`、`curve_converged = false`。
→ [`tl2_contract_receipt.json`](../backend/tracked_lineage_evidence/2026-09-14/tl2_contract_receipt.json)
`sha256:0cd90e12a9ca4090c798c73c4699a18d7aebba3f1b6e686275b60a2ae3db9e15`（本次計算）；
protocol `sha256:a38662d99c6c6a25015e3ab5f8d642b0bc601be8b1d5d157d7f5e00b8d9292d0`；
spec `sha256:ea1a56f0809f5a588c420fb8c52104fbc2b0eb10567be1baae8c152a35662289`；
lock `sha256:93d23a27…`（與 seed-variance 執行逐位元相同）。
[V1 receipt](TRACKED_LINEAGE_TRAINING_RECEIPT_2026-09-14.md)、[V2 receipt](TRACKED_LINEAGE_TRAINING_V2_RECEIPT_2026-09-14.md)。

[RESULT] **預算加倍不改變 regime**：獎勵由 `226.9`–`231.6` 升到 `283.1`–`295.3`（`+51.5`–`+66.5`）、
平均存活由 `2.440`–`2.811` s 升到 `2.725`–`3.458` s，**而 full exposure 在五個 replicate 上仍然全是 `0/30`**。
上限在看到任何曲線之前就凍結，且**沒有事後提高**；V2 是一個揭露「設計時已知 V1 結果」的新 protocol 版本。

[RESULT] **為什麼 reference 到不了 adequacy，這次有機制而不只有標籤。**
[PROJECT_ASSESSMENT §1.4](PROJECT_ASSESSMENT_2026-09-16.md) 以獎勵拆解對上實測：
在該 reward 下站好每步約 `2.5`，站滿 `INITIAL_STAND` + `START` 的 2.5 s（125 步）約 `310`，
再吃 `−50` 的終止懲罰約 `260`——**與 V1 實測 `227`–`232`、V2 實測 `283`–`295` 吻合**。
十個 replicate 全部寧願吃 `−50` 也不嘗試 `START → STEADY_WALK` 的轉換，
代表嘗試的期望代價 > 50；而 v4 曾把該懲罰由 `−5` 提到 `−45` 並未改變結果，
故**綁住的是形塑結構，不是懲罰量值，也不是預算**。

[RESULT] **這一點對 A-C3 的作用，比多一個實例更大，且其文獻依據已於 2026-09-16 原文核對。**
R4 原本讀起來像本專案 plant 的特例。但 `arXiv 2010.04304`（Reda, Tao, van de Panne）§9 的原文
以 TD3 對 survival bonus `0`／`1`／`5` 做 ablation，明言過大時「the algorithm exploits the survival bonus reward
while neglecting other reward terms. This results in a character that balances but never steps forward」，
Summary 並把過小與過大分別歸為前撲與站立不動兩個局部最優，且上溯至 Henderson 2018 與 Mania 2018——
**「shaping 讓靜止成為穩定局部最優」是 locomotion RL 已具名、已 ablate 的失敗模式，此判定現為 `S` 級**
（[訓練策略地圖 §1.1、§7](LITERATURE_MAP_2026-09-16_TRAINING_STRATEGY.md)）。
因此落進 R4 **不是意外，而是 shaped locomotion 任務上可預期的結果**——
於是「reference 是否可達 adequacy」就不只是算力問題，而是**由 reward 設計決定、且標準評估流程既不控制也不報告**的變數。
這正是 A-C3 要說的事，而且是它目前最強的一個支點。

[BLOCKER] **這條線不提供對比，只提供 reference adequacy 的判定。** tracked lineage 是單臂 budget 線，
不是 reference／candidate 比較，因此**不產生任何 paired bound**；它在本文中的角色只有一個：
證明「在凍結上限內 reference 從未達 adequacy」這件事可以在 pilot 以外的證據等級上被量到。
`not_independent_of_v1 = true`——V2 續訓自 V1，兩者**不是兩個獨立觀測**。
分析單位為 training replicate，method-level 分母恆為 `5`；`30`／`150`／`450` 為 enforced forbidden denominators。

## 4. 貢獻清單 V2（相對 V1 的變化）

| ID | 陳述 | V1 → V2 | 證據 regime |
|---|---|---|---|
| **A-C1（主）** | Early termination 使 rate 型 outcome 成為 exposure censoring；comparative evaluation 應報 assumption-free identification bound，拒絕 complete-case deletion 與 interval 補值，並把 method failure 與 exposure censoring 分開保留 | 不變；證據從一個 plant 擴為兩個 plant、兩個 policy 家族（fine-tuned humanoid PPO with project wrapper；from-scratch Walker2d PPO with generic wrapper）、三種 regime | R1、R2、R3 |
| **A-C2（主）** | `outcome_state == OBSERVED ⇏ full exposure`：所有 required outcome 有值、算術正常，exposure 仍可不足；可移植的檢查是由 trace 長度獨立重建 exposure | 不變；**第二個 plant 的證據已存在**（Walker2d 284/284） | R2（v7 三個 episode）、R3 |
| **A-C3（主，新增）** | Censoring regime 是 comparative evaluation 未被控制、未被報告的設計變數；bound 是否有資訊、artifact 是否可能出現由它決定；reference-adequacy 前置條件必須同時檢查 exposure 與 metric 非退化；方向可識別 ≠ 變異可估計 | **新增**：把原 `PUB-A1` 的「未達成」轉為方法論發現。**2026-09-16 補強**：R4 由 pilot-only 升為含一個凍結 protocol 實例（§3.7），且該實例的成因（shaping 造成的靜止局部最優）在文獻上是已具名、已 ablate 的失敗模式——**落進 R4 是可預期的，不是本專案 plant 的特例** | R1–R5 全部；§3.6、§3.7 |
| **A-C4（artifact）** | Statistical unit 的程式層強制（forbidden denominators）、`NOT_REACHED ≠ PASS`、`python -I -S` stdlib-only exact replay、freeze-before-execute、probe 作為 pilot 的紀律（上限不事後提高、seeds 對下游為禁區、pilot 不得為 evidence） | 擴充：加入 probe 紀律 | 全部 |
| ~~**A-C5（次）**~~ → **併入 A-C4（artifact 級，2026-09-10）** | 公開宣告非預註冊、且在啟發資料上必須失敗的 selection rule 自檢 | **降級**：補充 scan 完成（[LITERATURE_MAP §1.7](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md)）後判定縮小——透明宣告 post hoc 是 Hollenbeck & Wright (2017) 的 Tharking，決策資料隔離是 Cawley & Talbot (2010)／Dwork et al. (2015) 已建立；剩餘窄點的解讀受「選不出東西可能只因 exposure 不足」混淆 | `SELECT-V7-CANDIDATE-FORMAL-V1` |
| **A-M（動機）** | 同環境兩種 IEEE-conformant reduction order 給不同結果；版本 pin 不足以重驗數值 | 不變；SC'24、RepDL 已建立，只作動機 | environment lock receipt |

**被放棄的主張：** 「v7 的不對稱 censoring artifact 在公開 benchmark 上重現」。它成為稿件明文限制（§6 第 1 條）。

## 5. Claim → evidence 對照（`PUB-A2` 草稿）

每一列：稿件中可出現的陳述、支持它的 hash-bound artifact、evidence class、replay 狀態。任一列若在 `PUB-A0` 後被文獻推翻或縮小，只能刪列或收窄陳述，不得擴張。

| # | 稿件陳述（草稿） | 支持 artifact | Class | Replay |
|---|---|---|---|---|
| 1 | 在 frozen v7 pilot bundle 上，V7C 的 `−36.2185185` pp 表面改善其 paired identification bound 為 `[−36.2185185, +28.2925927]` pp，含 0，30/30 pair sign 不可識別 | `audit_summary.json` `74f6edfa…`；audit protocol `b15505b7…` | DEVELOPMENT，read-only audit | stdlib exact |
| 2 | 同一 artifact 在 5 個獨立 training seeds 上重現：V7C 150/150 early termination；θ `[−37.195407, +27.315704]` pp、0/5 | seed-variance summary `42b4cfac…`、raw `0fe9c0b9…` | DEVELOPMENT，凍結 protocol | stdlib exact |
| 3 | 同一資料上 V7B 的 θ `[−13.503408, −12.435259]` pp 排除 0、5/5 sign-identified，顯示 bound 在輕度 censoring 下有資訊 | 同上 | 同上 | 同上 |
| 4 | 即使 5/5 方向可識別，`between_replicate_sd` 因每個 replicate 至少一臂被 censored 而無定義；sample size 不可規劃 | 同上（`BLOCKED_PARTIALLY_IDENTIFIED_REPLICATE_DIFFERENCES`） | 同上 | 同上 |
| 5 | v7 pilot 的 3 個 V7B censored episode 與 Walker2d 的 284 個 early episode，`outcome_state` 全為 `OBSERVED` | audit_summary `74f6edfa…`；second_case_summary `e6761b78…` | DEVELOPMENT | stdlib exact ×2 |
| 6 | 在 Gymnasium Walker2d-v5 預設、from-scratch PPO、凍結於任何 run 之前的 protocol 下：naive `−28.795138` pp、t-interval 排除 0；θ `[−79.118, +55.913333]` 含 0；`SECOND_CASE_ARTIFACT_REPRODUCED` | second_case_summary `e6761b78…`、raw `0e9ceaf9…`、protocol `45d1ec55…` | DEVELOPMENT，凍結 protocol | stdlib exact |
| 7 | 在該案例中兩臂皆重度 censored（16/300 full），bound 構造上必含 0 | 同上 | 同上 | 同上 |
| 8 | Naive 恆落在 bound 內（引理），於 450 + 300 個 episode 上成立 | `exposure_identification.py` 測試；兩份 summary | 軟體 + DEVELOPMENT | 測試固定 |
| 9 | Reference rate 為 0 且 full exposure 時，naive 與 bound 的 contrast 必同號（§3.6） | 數學陳述 | — | — |
| 10 | 凍結的 exposure-only budget-selection 程序：Walker2d 兩次於上限內回傳 NEGATIVE；Hopper 回傳 FOUND 但選出的 reference 在選定 checkpoint 的 saturation 為 2.712%、兩個更早 checkpoint 為 ≈ 0% | 三個 `probe_result.json`（`76612f47…`、`55a6220d…`、`dcc70c24…`） | **pilot** | 直接讀值 |
| 11 | 同環境 1000 個 reciprocal：stdlib 順序 `7.485470860550343`，`numpy.ndarray.sum` `7.485470860550345` | lock record `889efeb0…` | 量測 | — |
| 12 | Method-level 分母在每條路徑恆為 5（training replicate）；30／60／150／300（second case）與 150／450（seed variance）為 enforced forbidden denominators | contract 測試 | 軟體 | 測試固定 |
| 13 | 在 `TRACKED-LINEAGE-TRAINING-V1`／`V2` 的凍結 protocol 下，五個 replicate 於 `2,000,000` 與 realized `4,015,200` 兩個預算的 full exposure 皆為 `0/30`（`replicates_attaining_threshold = 0`、`threshold = 30/30`）——R4 的一個非 pilot 實例 | `tl2_contract_receipt.json` `0cd90e12…`；protocol `a38662d9…` | DEVELOPMENT，凍結 protocol，標籤由 contract runner 算出 | 由版控證據重算 |
| 14 | 該線的獎勵由 `226.9`–`231.6` 升至 `283.1`–`295.3`、平均存活由 `2.440`–`2.811` s 升至 `2.725`–`3.458` s，**而 regime 未改變**（仍 `0/30` × 5）：預算不是決定 reference 是否可達 adequacy 的那一項 | 同上；[V1](TRACKED_LINEAGE_TRAINING_RECEIPT_2026-09-14.md)／[V2 receipt](TRACKED_LINEAGE_TRAINING_V2_RECEIPT_2026-09-14.md) | 同上 | 同上 |

## 6. 不可宣稱與限制（凍結候選清單）

1. **R1 只在本專案 humanoid plant 上量到。** 在公開 benchmark 上沒有得到不對稱 regime 的實例；三次嘗試記錄為 pilot。稿件的 Limitations 第一條。
2. **Probe 資料的 claim boundary。** 只能陳述凍結程序的 outcome label 與關於規則的觀察；任何關於 Walker2d／Hopper／PPO recipe 能力的陳述都在 boundary 之外。
3. **不是 preregistration。** 全部為 internal hash freeze；第二案例 protocol 在 v7 結果已知後寫成；`SELECT-V7-CANDIDATE-FORMAL-V1` 為 post hoc、disclosed。
4. **v7 line 永久 `CONDITIONAL_ON_FIXED_WARM_START`**；pilot 與 audit 的環境 `ABSENT_UNRECOVERABLE`；`cross_protocol_comparability = NON_VERIFIABLE_ENVIRONMENT`——pilot 與 seed-variance 的數值不得相減或並排成趨勢。
5. **Recipe 數值 `U_VERIFIED_FROM_MEMORY`**（rl-zoo Walker2d／Hopper PPO），投稿前須對照已發表檔案。
6. **文獻條目多數仍 `U`**；§4 點名的兩篇關鍵文獻（arXiv 1911.05728、2606.10229）已於 2026-09-09 由專案負責人提供 PDF 全文核對（[LITERATURE_MAP §7](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md)），兩個「gap 縮小／消失」條件皆不成立，A-C1／A-C2 的 gap 判定不再條件於它們，但仍條件於其餘 `U` 條目；novelty 主張條件於 `PUB-A0` 完成。A-C5 的補充 scan 已於 2026-09-10 完成，結果是**縮小**：該項降為 artifact 級併入 A-C4（見 §4 表與 [LITERATURE_MAP §4 第 5 點](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md)）。
7. **只用最弱的 Manski 型 bound**；本專案刻意拒絕 monotonicity 等收窄假設，稿件須主動說明理由。
8. **不對 plant、controller、action interface、low-pass filter、sim-to-real、physical actuator 做任何主張**；`direction_claim_permitted = false` 於每一份 summary。
9. **n = 5 training replicates**／line；無 power；`paper_data_ready` 等四個 flag 皆 false 且本重構不改變它們。
10. **NPZ trace 與 policy checkpoint 不在版控**（digest 保留於 raw bundle）；每一條 claim 只依賴 raw JSON 中的 counts。
11. **§3.7 的 tracked lineage 實例是單臂 budget 線，不是比較。** 它**不產生任何 paired bound**，在本文中只支持「reference 在凍結上限內未達 adequacy」這一件事。`not_independent_of_v1 = true`——V2 續訓自 V1，**不得視為兩個獨立觀測**。它與 v7、Walker2d 的數值**不得相減或並排成趨勢**（`cross_protocol_comparability` 限制照舊適用）。**不支持**「再多跑一些步數就會到 `30/30`」——曲線仍在上升正是 `TL2_BUDGET_EXHAUSTED` 的定義，不是它會成功的證據。§3.7 的獎勵拆解是對**該 reward 函數**的算術說明，**不是**對 plant、controller 或任何 locomotion 方法的主張（§6 第 8 條照舊）。

## 7. Figure／table 計畫（草稿；`PUB-A2` 時凍結）

| ID | 內容 | 輸入 artifact | 重建方式 |
|---|---|---|---|
| T1 | Regime 分類（本文 §3 表） | — | 文字 |
| T2 | 每個 regime 的量測實例：exposure counts、naive、bound、sign-identified 數 | audit_summary、seed-variance summary、second_case_summary | `python -I -S` 由 raw + protocol 重算 |
| T3 | `OBSERVED` 但 censored 的 episode 數（v7 pilot 3／90；Walker2d 284／300） | 同上 | 同上 |
| F1 | Realized exposure 分布（per arm、per case）：v7 V7C `159.7 ± 2.77` steps；Walker2d 各 cell median | 同上 | 同上 |
| F2 | Forest plot：逐 replicate 的 naive 點 vs bound 區間（v7 V7B ×5、V7C ×5、Walker2d ×5） | seed-variance summary、second_case_summary | 同上 |
| F3（pilot，方法／限制節） | 三條 probe 曲線：FULL/30 與 naive duty vs 累計 steps | 三個 `probe_result.json` | 直接讀值；標示 pilot |
| T5 | R4 的非 pilot 實例：兩個預算 × 5 replicate 的 full exposure（全 `0/30`）與同期的 reward／duration 變化 | `tl2_contract_receipt.json`、兩份 tracked lineage receipt | 由版控證據重算 |
| T4（附錄） | 所有 receipt 與 artifact 的 SHA-256 清單 | 本文 §3、§5 | — |

## 8. `PUB-A` gates V2

> **本表是 mirror，不是權威來源**（`GATE-STATUS-SINGLE-SOURCE-V1`）。權威在 [PUBLICATION_PLAN §5](PUBLICATION_PLAN.md)；兩邊不一致時以權威為準，且 `backend/gate_status_contract.py` 會讓測試失敗。規則見 [GATE_STATUS_SINGLE_SOURCE](GATE_STATUS_SINGLE_SOURCE.md)。

| Gate | 出口條件 | 狀態 | 依據 |
|---|---|---|---|
| `PUB-A0` Novelty | 文獻地圖所有 `U` 經原文核對；§4 gap 判定重寫並仍成立 | `IN_PROGRESS` — `FOUR_VERIFIED_REMAINING_U`（2026-09-16） | 關鍵兩篇已核對（2026-09-09）：1911.05728 為 independent-censoring + imputation 的點估計，2606.10229 為 curation metric 的設計期 truncation。A-C5 補充 scan 已完成（2026-09-10）並使該項降級。其餘 `U` 條目需可存取出版方的環境（2026-09-10 重新量測 `arxiv.org` 仍封鎖）。**2026-09-16 再核兩篇**：`1712.00378`（Pardo）與 `2010.04304`（Learning to Locomote）皆確認為 learning 端、不涉量測端 identification，§1.1 兩列升為 `S`，A-C1／A-C2 的 gap 判定不變 |
| `PUB-A1a` 第二 plant 的機制證據 | 至少一條主貢獻在非專案 plant 上有凍結 protocol + receipt + stdlib replay | **`PASS`** | Walker2d V1 receipt：A-C1（R3）、A-C2（284/284） |
| `PUB-A1b` 公開 benchmark 上的不對稱 regime | 在公開 benchmark 上以凍結 protocol 量到 R1 | **`CLOSED_NOT_ATTAINED`**（2026-09-09） | 三次 probe；寫入限制第 1 條；不是 PASS、不是放寬 |
| `PUB-A2` Claim freeze | §5 每列可只由 hash-bound receipt 推出；§6、§7 凍結；限制段落先寫 | `IN_PROGRESS` — 本文件為草稿 | 凍結須在 A0 之後 |
| `PUB-A3` Reproduction | clean checkout 以 `python -I -S` 重建 T2／T3／F1／F2 輸入；受 `ENVIRONMENT-LOCK-V1` 比對 | `NOT_STARTED` | 現有 replay 已覆蓋每一層；缺一次正式 clean-checkout 執行 |
| `PUB-A4` Internal review | 一輪對抗式內部審查（統計 + RL 評估兩視角） | `NOT_STARTED` | |
| `PUB-A5` Submission | venue、preprint、code／receipt archive 帶 DOI | `NOT_STARTED` | |

[BLOCKER] `PUB-A1a` 的 PASS 依據是**已存在**的 V1 receipt 與其凍結規則下的 outcome，不是新的敘述；`PUB-A1b` 不是被放寬，而是被明確標為未達成並寫進 claim boundary。這是 V1 → V2 唯一的 gate 語義變更，在此揭露。

## 9. 對第二案例 pipeline 的處置

- `SECONDCASE-EXPOSURE-CENSORING-WALKER2D-V2` 與 `SECONDCASE-EXPOSURE-CENSORING-HOPPER-V1`：**撤回**。兩者從未被 pin、從未載入。`second_case_exposure_contract.py` 新增 `WITHDRAWN_PROTOCOLS`；`load_protocol` 在任何路徑對兩者以 `SECONDCASE_PROTOCOL_WITHDRAWN` 拒絕；import 時斷言撤回 id 不得有 pinned digest；測試固定。
- V2 schema（P0 reference adequacy、candidate-scoped P1、第六個 label、`normalizer_sha256`）與 probe runner（recipe／environment override）**保留為軟體**並持續測試；V1 retained evidence 的 bytes 與 replay 不變（測試固定）。
- 三個 probe 結果保留於 `backend/second_case_evidence/2026-09-08-v*-budget-probe*/`，性質為 pilot；其 seeds（42000／43000–43029、46000／47000–47029、48000／49000–49029）對任何後續 protocol 為禁區。
- 任何未來的第二案例嘗試：新 protocol id；budget probe 的 adequacy 規則同時要求 exposure（≥ 27/30、連續兩個 checkpoint）與事先凍結的 reference-saturation 下限；先行寫入 [PUBLICATION_PLAN](PUBLICATION_PLAN.md) 作為新 gate，不重開 `PUB-A1b`。
- 沒有任何 threshold、seed、budget 被調整；沒有新的訓練或評估被執行。

## 10. 立即下一步

1. `PUB-A0`：關鍵兩篇已核對（2026-09-09，gap 仍成立，[LITERATURE_MAP §7](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md)）、A-C5 補充 scan 已完成（2026-09-10，該項降級）、**再兩篇已核對**（2026-09-16：Pardo `1712.00378`、Learning to Locomote `2010.04304`，§1.1 兩列升為 `S`）。**唯一剩餘工作**是在可存取出版方的環境讀 §1.1 剩餘條目、§1.3–§1.5、§1.7 與 §2 的 `U` 條目原文；**優先三篇**：Colas 2019、Manski 1990／Tamer 2010、Hollenbeck & Wright 2017。
   [BLOCKER] **2026-09-17 更正**：本列原寫「優先四篇」並把 **Pardo 2018 列為待核對**，但同一份文件 §8 的 gate 列早已寫 `FOUR_VERIFIED_REMAINING_U`（Pardo 已核對）——**同一份文件對同一件事給出兩個答案**。原措辭記於此以供對照（原清單四篇為 Pardo 2018、Colas 2019、Manski 1990／Tamer 2010、Hollenbeck & Wright 2017），判定以 §8 與 [LITERATURE_MAP §1.1／§7](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md) 為準。此錯誤的成因與規模記於 [PROJECT_ASSESSMENT §4.3.1](PROJECT_ASSESSMENT_2026-09-16.md)。
2. Recipe 數值核對（rl-baselines3-zoo `hyperparams/ppo.yml` Walker2d／Hopper 條目）——影響 §6 第 5 條的措辭。
3. `PUB-A2`：A0 完成後，把本文 §5–§7 凍結為 claim freeze receipt。
4. `PUB-A3`：一次正式 clean-checkout reproduction 執行並記錄。
5. 工程軌道不變（[ROADMAP §9](ROADMAP.md)）。

## 11. 對其他文件的影響

- [PUBLICATION_PLAN](PUBLICATION_PLAN.md)：升版 `PUBLICATION-PLAN-V2`；Track A §2.1 與 §3.1 依本文改寫；Track B／C 不動。
- [probe receipt](SECOND_CASE_V2_BUDGET_PROBE_RECEIPT_2026-09-08.md) §7：決定紀錄。
- `STATUS.yaml`：`publication_plan_status`、`second_case_exposure_status`、`next_milestone`、新增 `track_a_reframe`；[PROJECT_STATUS](PROJECT_STATUS.md)、[README](../README.md)、[CHANGELOG](../CHANGELOG.md)、[ROADMAP §10](ROADMAP.md)、[RESEARCH_EXECUTION_PLAN](RESEARCH_EXECUTION_PLAN.md) `PUB-A` 列同步。
