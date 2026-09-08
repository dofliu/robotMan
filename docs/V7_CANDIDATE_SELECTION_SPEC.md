# V7 Candidate Selection Specification

日期：2026-09-08

狀態：`FROZEN / NOT PREREGISTERED / EXECUTION BLOCKED PENDING FORMAL AUTHORIZATION`

Protocol：`SELECT-V7-CANDIDATE-FORMAL-V1`
Machine-readable contract：
[`backend/rl/v7_candidate_selection_protocol.json`](../backend/rl/v7_candidate_selection_protocol.json)
實作：[`backend/v7_candidate_selection_contract.py`](../backend/v7_candidate_selection_contract.py)

上游：`PILOT-V7-ACTION-INTERFACE-DEV-V1`、
`AUDIT-V7-EXPOSURE-CENSORING-V1`、
`SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1`、`ENVIRONMENT-LOCK-V1`

證據範圍：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`

## 1. 必須先講的事：本 protocol 不是 preregistered

[BLOCKER] **本 protocol 是在已經看過結果之後寫的。**

作者在凍結本 protocol 時已經知道：`SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1` 在
DEV seeds `18000–18029` 上量到 V7B 相對 V7A 的 method-level identification
bound 為 `[-13.503408, -12.435259]` pp，排除 0，sign `NEGATIVE`，5/5
replicates 方向可識別；V7C 為 `[-37.195407, +27.315704]` pp，含 0，0/5 可識別。

因此本 protocol **不得**被描述為 preregistered、blinded 或 confirmatory
design。任何引用它的文件都必須一併引用本節。

[INFERENCE] 在這種情況下，唯一還能提供的保護不是假裝沒看過，而是**讓規則
對已看過的資料不生效**：

1. 決策只能在**從未被此對比檢視過**的 evaluation seeds 上進行（第 3 節）；
2. 規則必須在凍結後**一次性**套用，不得重跑、不得調整（第 5 節）；
3. 而且——最重要的——**把本規則套用在我已經看過的 DEV 資料上，選不出任何
   candidate**（第 6 節）。規則若是為了讓 V7B 通過而設計，它就不會擋下 V7B。

## 2. 本 protocol 要回答的唯一問題

在 frozen v7 三臂中，是否有一個 candidate 可以被指定為
`selected_candidate_arm_id`，作為後續 formal planning 的對象？

預設答案是 **no**。只有第 4 節的全部條件同時成立，答案才會變成某一個 arm。

## 3. 資料：只有 sealed FORMAL 還沒被看過

| Seed range | 狀態 | 為什麼不能用來 select |
| --- | --- | --- |
| `18000–18029` | `DEVELOPMENT_EXHAUSTED` | v7 pilot、exposure audit 與 seed-variance 都已檢視；本 protocol 的作者也已看過其結果 |
| `19000–19030` | `RETIRED` | v7 protocol 已退役；且 v5 registry 記載它曾作為 HOLDOUT 使用 |
| `20000–20029` | `SEALED_FORMAL` | **唯一未被檢視的範圍** |

[INFERENCE] 因此 selection 只能在 `20000–20029` 上決定。這不是偏好，是**唯一
剩下的選項**：在已看過的資料上做 selection，等於用被選中的雜訊決定選擇條件。

[BLOCKER] 開啟 `20000–20029` 需要 **formal authorization**，而它是本專案
明列尚未取得的 blocker（見 `docs/EXPERIMENT_PROTOCOL.md` 與
`STATUS.yaml` 的 `v0_remaining_blockers`）。因此本 protocol **凍結但不可
執行**。凍結的目的正是：在授權出現之前，先把規則釘死，讓它不能事後被改成
剛好讓某一臂通過的樣子。

## 4. 決策規則（凍結）

Reference arm 固定為 `V7A_REWARD_ONLY`。Candidates 為
`V7B_REDUCED_JOINT_ENVELOPE` 與 `V7C_FILTERED_ACTION`。

一個 candidate 只有在**同時**滿足下列全部條件時才 eligible：

- `SEL-C1` **完整 inventory**：`replicate_count × 30` 個 FORMAL terminal
  records 齊全，沒有 missing、duplicate、unexpected、DEV 或 retired seed。
- `SEL-C2` **全數 full exposure**：該 candidate 與 reference 的**每一個**
  episode 的 `comparability_state` 都是 `COMPARABLE`。任何
  `EXPOSURE_CENSORED` 或 `METHOD_FAILURE_NOT_CENSORING` 即不 eligible。
- `SEL-C3` **方向可識別**：method-level paired identification bound 完全排除
  0 且為 negative（duty 越低越好，故 negative 才是改善）。
- `SEL-C4` **變異可估計**：`between_replicate_sd` 是 point value，不是
  `null`。
- `SEL-C5` **frozen gate subset 全通過**：沿用 pilot 的六項門檻，逐 episode
  通過，且沒有 required null 或 non-finite。門檻數值不得調整。
- `SEL-C6` **environment lock**：`MEASURED_ENVIRONMENT_LOCK` +
  `FULL_LOCK` + `AMBIENT_THREADING_PINNED`，且每個 run 前皆 verify 通過。

若兩個 candidate 都 eligible，選 method-level bound 上界較低者（即改善較大
者）。**完全相同則不選**。若沒有 candidate eligible，輸出
`SELECTION_COMPLETE_NO_CANDIDATE`，且不得放寬任何條件重試。

### 4.1 為什麼 `SEL-C2` 要求全數 full exposure

[SOURCE] `AUDIT-V7-EXPOSURE-CENSORING-V1` 在 frozen pilot bundle 上量測確認：
V7B 那 3 個 censored episode 的 `outcome_state` 全部是 `OBSERVED`——它們在
`FINAL_STAND` 內才終止，六項 required numeric 皆有值、`reason` 為 null，
**算術上看不出異常**。

[INFERENCE] 因此「required outcomes 都 observed」不蘊含 full exposure。
Pilot 原本的 eligibility 規則只檢查前者，會把 exposure-censored episode 當成
正常 episode。本 protocol 把 audit 的這個發現寫進 selection gate：selection
必須建立在點識別的量上，而 censored exposure 下的 duty 不是點識別的。

### 4.2 為什麼 `SEL-C4` 要求變異可估計

[INFERENCE] Selection 的用途是啟動 formal planning，而 formal planning 需要
sample size，sample size 需要 between-replicate variance。方向可識別而變異
不可估計時，選出來的 candidate 無法被用來規劃任何東西——那樣的 selection 只是
提前承諾，不是決策。因此變異可估計是 selection 的前提，不是後續工作。

## 5. 一次性與禁止事項

- 本 protocol 對 FORMAL 資料**只套用一次**。看過 FORMAL 結果之後：不得重跑、
  不得調整門檻、不得改變 `replicate_count`、不得改變 arm 定義、不得改變
  primary outcome。
- 任何上述改動都需要**新的 protocol version**，且新版本必須明示它是在已知
  FORMAL 結果的情況下設計的——與本 protocol 第 1 節同樣的揭露義務。
- 不得以 DEV 或 retired seeds 的結果補足或替代 FORMAL 結果。
- 不得因為「方向已經很清楚」而略過 `SEL-C2`／`SEL-C4`。

## 6. 把本規則套用在已看過的 DEV 資料上：選不出任何 candidate

[RESULT] 用 `SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1` 已保留的 DEV evidence
（`backend/seed_variance_evidence/2026-09-08/`）逐條檢查：

條件依序評估，**一旦有條件 FAIL，其餘標為 `NOT_REACHED`**（`NOT_REACHED`
永遠不等於 PASS；eligible 需要六個明確的 PASS）。Self-check 只停用 `SEL-C1`
的 seed-class 子句——否則它會停在「DEV seeds 不是 FORMAL」這種恆真的地方，
完全不檢驗實質條件。

| 條件 | V7B | V7C |
| --- | --- | --- |
| `SEL-C1` | PASS（450 records、seeds `18000–18029`；seed-class 子句於 self-check 不適用） | PASS（同上） |
| `SEL-C2` 全數 full exposure | **FAIL**：comparable `120/150`（reference V7A `143/150`） | **FAIL**：comparable `0/150` |
| `SEL-C3` … `SEL-C6` | `NOT_REACHED` | `NOT_REACHED` |

[RESULT] 兩個 candidate 都不 eligible，結果為
`SELECTION_COMPLETE_NO_CANDIDATE`。**實際擋下兩者的是 `SEL-C2`。**

[RESULT] 與條件鏈無關、直接從 summary 讀出的事實：V7B 的 method-level bound
`[-13.503408, -12.435259]` 排除 0（故 `SEL-C3` 本會 PASS），而其
`between_replicate_sd` 為 `null`（故 `SEL-C4` 本會 FAIL）。因為 `SEL-C2` 先
FAIL，這兩條在鏈中並未被評估。

[INFERENCE] 這是本 protocol 抵抗 post-hoc 設計偏誤的**最強證據**：如果規則是
為了讓 V7B 通過而寫的，它在我唯一看過的資料上就會讓 V7B 通過。它沒有。
擋下 V7B 的 `SEL-C2`（以及本會擋下它的 `SEL-C4`）都直接來自上游 audit 與
seed-variance 的既有發現，不是為本 protocol 新造的。

[BLOCKER] 第 6 節**不是** selection 的執行。它是對已看過資料的規則檢查，
用途只在於檢驗規則本身。`selected_candidate_arm_id` 維持 `null`。

## 7. 執行前置條件（凍結前已實測，不是預期）

`SEEDVAR-AMENDMENT-01-DRIVER-IDENTITY` 的教訓是：凍結時把 driver 以 digest
pin 住，卻沒有檢查它們跑不跑得動。本次在凍結前先查，結果如下。

[RESULT] **今天的 pipeline 無法執行本 protocol，即使取得授權。** 兩處
fail-closed：

1. `backend/v7_exposure_audit_contract.py` 的 `_episode_exposure` 對任何落在
   `SEALED_SEED_RANGE = range(20000, 20030)` 的 seed 直接 raise
   （`observed sealed FORMAL/HOLDOUT seed`）。Exposure 分類是 `SEL-C2` 的
   輸入，所以 FORMAL episodes 現在連分類都不可能。
2. `backend/rl/eval_policy.py` 的兩個 branch 都把 evaluation seed schedule
   釘死（`V7_EVALUATION_SEED_SCHEDULE_OVERRIDE_FORBIDDEN` 與
   `SEEDVAR_EVALUATION_SEED_SCHEDULE_OVERRIDE_FORBIDDEN`），沒有任何路徑會
   接受 `20000–20029`。

[INFERENCE] 因此執行本 protocol 需要（a）第三個互斥的 evaluation identity，
以及（b）對已 merge 的 audit contract 做一次 amendment 以允許 FORMAL seeds
在**授權存在時**被分類。(b) 觸及有下游 pins 的 frozen contract，因此不在本次
範圍內，也**不應該**在沒有授權的情況下先做——先解開 sealed-seed 的門，再等
授權，順序是反的。

[RESULT] 這兩項作為本 protocol 的 `execution_preconditions` 記錄在
machine-readable contract 內，並由 contract 的 `SEL-06` 檢查。

## 8. Acceptance criteria

- `SEL-01`：protocol 明示 `preregistered = false` 且載明第 1 節的揭露；缺任一
  即 fail closed。
- `SEL-02`：selection 只接受 `SEALED_FORMAL` 範圍的 evaluation seeds；出現
  DEV 或 retired seed 即 structural failure。
- `SEL-03`：沒有 `formal_authorization` evidence 時，contract 拒絕輸出任何
  selection。
- `SEL-04`：`SEL-C1..SEL-C6` 任一不成立即輸出
  `SELECTION_COMPLETE_NO_CANDIDATE`，且不得回報 candidate。
- `SEL-05`：兩個 candidate 完全相同時不選；exact tie 不得任意破。
- `SEL-06`：`execution_preconditions` 未全部解除時，contract 拒絕執行
  selection，並具名列出未解除項。
- `SEL-07`：套用在 DEV evidence 上必須得到
  `SELECTION_COMPLETE_NO_CANDIDATE`（第 6 節的規則自檢，由測試固定）。
- `SEL-08`：一次性；receipt 記錄 `applied_once = true`，重複套用同一份
  FORMAL evidence 即 structural failure。
- `SEL-09`：receipt 維持 `paper_data_ready = false` 與本 spec 的 claim
  boundary。

## 9. Claim boundary

[BLOCKER] 本 protocol 沒有執行、沒有存取 `20000–20029`、沒有產生任何 FORMAL
資料，也沒有選出任何 candidate。它不解除 formal authorization、immutable
storage、binary paired CI、actual Study A matrix、V0/V1/V3 gate 中的任何一項。

[BLOCKER] 即使日後取得授權並執行，本 protocol 的結論最多只能是「在此 frozen
plant、此 warm start、此 task 與 FORMAL evaluation seeds 下，哪一個
action-interface candidate 通過凍結的 eligibility」。它**不**支持 controller
superiority、sample-size adequacy、paper readiness、physical margin、安全或
sim-to-real 宣稱。

[BLOCKER] `training_replicate_scope = CONDITIONAL_ON_FIXED_WARM_START` 對 v7
line 是永久的（見
[pretraining infeasibility receipt](V7_PRETRAINING_SEED_VARIANCE_INFEASIBILITY_RECEIPT_2026-09-08.md)），
所以任何 selection 結果都永遠附帶那個條件。

Primary/official sources：

- [Empirical Design in Reinforcement Learning, JMLR 2024](https://www.jmlr.org/papers/v25/23-0183.html)
- [Deep RL at the Edge of the Statistical Precipice, NeurIPS 2021](https://proceedings.neurips.cc/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html)
- [Partial Identification of Probability Distributions, Manski 2003](https://link.springer.com/book/10.1007/b97478)
