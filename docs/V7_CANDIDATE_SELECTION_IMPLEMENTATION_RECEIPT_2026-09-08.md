# V7 Candidate Selection Gate Implementation Receipt

日期：2026-09-08

Protocol：`SELECT-V7-CANDIDATE-FORMAL-V1`
（`sha256:b4e16370b5744c510fa11b06343dafb3c1893711639721a406504720bbe99b58`）
Spec：[`docs/V7_CANDIDATE_SELECTION_SPEC.md`](V7_CANDIDATE_SELECTION_SPEC.md)
（`sha256:bab998579bdb4f260d5c46405ad54dfc105dab975a9f78ea729aab71d3c8afb3`）

實作：

| 檔案 | SHA-256 |
| --- | --- |
| `backend/v7_candidate_selection_contract.py` | `65511b54d8d5ed29ee19016c6b6a03f72caf4eecc09bbbcdab163f8d411bed82` |
| `backend/test_v7_candidate_selection_contract.py` | `dfd60267ac01065e8de3602d4e82558064c3e849062180c3c5f635f383d50eb0` |

證據範圍：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`

## 1. 本次 milestone 的兩個分支，一個關掉、一個凍結

`STATUS.yaml` 排定的 next milestone 有兩個選項：估計 independent
**pretraining**-seed variance，或另立 selection protocol。

[RESULT] **第一個選項經查證關閉。** v5 warm start 自一個位於 gitignored
`backend/rl/artifacts/` 的 v4 local artifact，版本控制中只有 3 個 policy
artifact（無 v3、無 v4），v5 自己的 training profile 記錄
`warm_start_policy_id: null`，而其 `122,880`-step checkpoint 是在另一個
`516,096`-step run regressed 之後被選出來的。細節與逐項證據見
[pretraining infeasibility receipt](V7_PRETRAINING_SEED_VARIANCE_INFEASIBILITY_RECEIPT_2026-09-08.md)。

[BLOCKER] 因此 `training_replicate_scope = CONDITIONAL_ON_FIXED_WARM_START`
對 v7 line 是**永久的**。這是縮小可宣稱範圍，不是擴大。

[RESULT] **第二個選項已凍結並實作** —— 本 receipt 的主題。

## 2. 誠實面對一件事：本 protocol 不是 preregistered

[BLOCKER] 本 protocol 是在已看過 `SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1`
結果之後寫的。凍結時已知 V7B 相對 V7A 的 bound 為
`[-13.503408, -12.435259]` pp、排除 0、5/5 可識別。它**不得**被描述為
preregistered、blinded 或 confirmatory design。

`validate_protocol` 強制 `preregistered = false` 與四個 disclosure 欄位齊全；
少任何一項即 fail closed。一個把 `preregistered` 改成 true 的版本無法載入。

[INFERENCE] 在這種情況下唯一還能提供的保護，不是假裝沒看過，而是讓規則
**對已看過的資料不生效**。三層：只在未被檢視的 seeds 上決策、只套用一次、
以及——最關鍵的——把規則套在已看過的資料上必須選不出東西。

## 3. 實測：規則套在我看過的資料上，選不出任何 candidate

[RESULT] 對 `backend/seed_variance_evidence/2026-09-08/` 的真實 DEV evidence
執行 `rule-check`：

```text
outcome: SELECTION_COMPLETE_NO_CANDIDATE
V7B_REDUCED_JOINT_ENVELOPE  unblocked=False
   PASS         SEL-C1  450 terminal records over seeds 18000-18029
   FAIL         SEL-C2  comparable 120/150, reference V7A 143/150
   NOT_REACHED  SEL-C3 … SEL-C6
V7C_FILTERED_ACTION         unblocked=False
   PASS         SEL-C1  450 terminal records over seeds 18000-18029
   FAIL         SEL-C2  comparable 0/150, reference V7A 143/150
   NOT_REACHED  SEL-C3 … SEL-C6
```

[RESULT] 實際擋下兩者的是 `SEL-C2`（全數 full exposure）。另外從 summary 直接
讀出、未進入條件鏈的事實：V7B 的 bound 排除 0（`SEL-C3` 本會 PASS），其
`between_replicate_sd` 為 `null`（`SEL-C4` 本會 FAIL）。

[INFERENCE] 擋下 V7B 的兩條（`SEL-C2` 與本會生效的 `SEL-C4`）都直接來自上游
exposure audit 與 seed-variance 的既有發現，不是為本 protocol 新造的。如果
規則是為了讓 V7B 通過而設計，它在我唯一看過的資料上就會讓 V7B 通過。

## 4. 一個我自己寫壞、被測試抓到的洞

[RESULT] 第一版的 self-check **在任何輸入上都不可能通過**：它把 `SEL-C5`
（frozen gate subset）當成必須提供的輸入，而 self-check 從不提供，所以
`SEL-C5` 恆為 FAIL。

[INFERENCE] 那使第 3 節的論證變成空話：一個「無論資料如何都會擋下」的檢查，
對規則本身沒有提供任何證據。它擋下 V7B 不是因為 V7B 有問題，而是因為它擋下
一切。

修正：`SEL-C5` 與 `SEL-C6` 在 self-check scope 下標為 `NOT_APPLICABLE`
（兩者都不區分 candidate，也都不可由 seed-variance summary 導出），因此一份
乾淨的 summary **真的會通過** self-check —— 這才使它在真實資料上的拒絕成為
證據。`test_the_self_check_could_have_passed_which_is_what_makes_it_evidence`
同時斷言兩個方向。

[RESULT] `NOT_APPLICABLE` 與 `NOT_REACHED` 都**永遠不等於 PASS**：selection
需要六個明確的 PASS，所以缺輸入只能擋下 selection，不能放行。

## 5. 執行前置條件：這次在凍結前先量

`SEEDVAR-AMENDMENT-01-DRIVER-IDENTITY` 的代價是：凍結時把 driver 以 digest
pin 住，卻沒檢查它們跑不跑得動。本次先查，並把結果寫進 protocol。

[RESULT] **今天的 pipeline 無法執行本 protocol，即使取得授權**，三項皆
`BLOCKING`：

| ID | 實測發現 |
| --- | --- |
| `EP-01` | `v7_exposure_audit_contract._episode_exposure` 對落在 `SEALED_SEED_RANGE = range(20000, 20030)` 的 seed 直接 raise；exposure 分類是 `SEL-C2` 的輸入 |
| `EP-02` | `rl/eval_policy.py` 兩個 branch 都把 evaluation seed schedule 釘死，沒有路徑接受 `20000–20029` |
| `EP-03` | formal authorization 尚未取得 |

`assert_executable` 在任一項未解除時拒絕執行並具名列出；
`test_measured_preconditions_still_match_the_code` 直接對 code 重驗這些
斷言——一個過期的 precondition 比沒有更糟，它會宣告一個已不存在的 blocker，
或藏起一個新出現的。

[INFERENCE] 解除順序很重要：授權在前，解封在後。在授權仍不存在時先拆掉
sealed-seed 的門，順序是反的，protocol 的 `ordering_rule` 明文禁止。

## 6. Acceptance criteria

| ID | 要求 | 結果 |
| --- | --- | --- |
| `SEL-01` | `preregistered=false` 與 disclosure 齊全，缺項 fail closed | PASS |
| `SEL-02` | 只接受 `SEALED_FORMAL` seeds；DEV／retired 即 structural failure | PASS（兩個 class 各自 parametrized） |
| `SEL-03` | 無 authorization evidence 時拒絕輸出任何 selection | PASS（且在計算任何 verdict **之前**檢查） |
| `SEL-04` | `SEL-C1..SEL-C6` 任一不成立即無 candidate | PASS（六條各自可獨立擋下） |
| `SEL-05` | exact tie 不選 | PASS |
| `SEL-06` | precondition 未解除即拒絕執行並具名 | PASS |
| `SEL-07` | 套在 DEV evidence 上必須無 candidate | PASS |
| `SEL-08` | 一次性；同一份 FORMAL evidence 重複套用即 structural failure | PASS |
| `SEL-09` | receipt 維持 `paper_data_ready=false` 與 claim boundary | PASS |

[RESULT] `backend/test_v7_candidate_selection_contract.py`：**47 passed**。

另有一項防漂移檢查：
`test_the_protocols_documented_self_check_matches_what_the_code_reports` 逐條
比對 protocol 內記載的 self-check 表格與 contract 實際輸出的 condition
chain。若兩者分歧，frozen 文件就會在描述一個沒人在跑的規則。

## 7. Claim boundary

[BLOCKER] 本次沒有執行 selection、沒有存取 `20000–20029`、沒有產生任何
FORMAL 資料、沒有選出任何 candidate。`selected_candidate_arm_id` 維持
`null`，`method_level_power_ready`、`statistics_ready`、`paper_data_ready`
全部維持 `false`。

[BLOCKER] 即使日後取得授權並執行，結論最多只能是「在此 frozen plant、此 warm
start、此 task 與 FORMAL evaluation seeds 下，哪一個 candidate 通過凍結的
eligibility」，且**永遠附帶**那一個 provenance 不可回溯的 v5 warm start 條件。
不支持 controller superiority、sample-size adequacy、paper readiness、physical
margin、安全或 sim-to-real 宣稱。
