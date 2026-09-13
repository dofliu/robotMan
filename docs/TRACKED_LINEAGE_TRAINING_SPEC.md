# Tracked-Lineage Training Line：一條可重建 provenance 的訓練線

最後更新：2026-09-13 ｜ Protocol ID：`TRACKED-LINEAGE-TRAINING-V1` ｜ 對應 gate：`PUB-B1`、`PUB-B2`、[ROADMAP §9 第 2 項](ROADMAP.md)

狀態：`DRAFT_TWO_DECISIONS_OPEN`（**尚未凍結**。§4 的兩個欄位由專案負責人填定後才 freeze、push、執行）

證據等級：`DEVELOPMENT / SIM_ONLY_MUJOCO / NOT_EVIDENCE_UNTIL_EXECUTED`

---

## 1. 這條線要解決什麼

[SOURCE] v7 line 量到的一切都帶著 `CONDITIONAL_ON_FIXED_WARM_START`，而且那個標籤對該線**永久成立**：v5 warm start 來自 gitignored `backend/rl/artifacts/` 下的 v4 local artifact，版本控制只有 3 個 policy artifact，v5 自己的 profile 記 `warm_start_policy_id: null`，其 checkpoint 又是在另一個 regressed run 之後被挑出來的（[infeasibility receipt](V7_PRETRAINING_SEED_VARIANCE_INFEASIBILITY_RECEIPT_2026-09-08.md)）。

[RESULT] 直接後果有兩個，兩個都擋在論文路徑上：

1. `SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1` 只能量 **fine-tuning** seed 的變異，量不到 method 的完整變異，因此 `between_replicate_sd` 之外還缺 pretraining 這一層。
2. 5 個 replicate 共用同一個不可重建的起點，所以量到的變異**系統性低估**真實的 method variance。

[INFERENCE] 因此本線的目的不是「再訓練一個更好的 policy」，而是**造出一個 provenance 可重建的起點**，讓 `PUB-B3` 的 point-valued between-replicate SD 在原則上成為可能。

---

## 2. 揭露

[BLOCKER] 以下三項在設計之前就成立，必須連同任何產出一起出現：

1. **本線會修改 `backend/rl/train_ppo.py`。** 該檔案被已執行的 `SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1` 以 `source_baseline.training_driver_source_sha256 = sha256:877da3b41e7c44ce73758877f40e257e45c6203b045eb9e2d3cd5aa6f606f6ce` 釘住，而**執行期沒有任何東西重算該 pin**。修改之後，那個 pin 對活著的 repo 就不再為真。§6.4 規定本 protocol 必須同時保留兩個 digest 並具名揭露這件事——這是 [RUN_MANIFEST_LOCK_BINDING_SPEC §15.4](RUN_MANIFEST_LOCK_BINDING_SPEC.md) 指定的揭露位置。
2. **本線是 `DEVELOPMENT`。** 它不產生 `FORMAL_EVALUATION` 資料，不存取 sealed FORMAL seeds `20000–20029`，也不觸及 `SELECT-V7-CANDIDATE-FORMAL-V1`。
3. **本線可能得不到 reference policy。** v5 是經過 v1 → curriculum-v2 → v3 → v4 → v5 的多輪 curriculum 才達到 Live 10/11；單發 scratch run 未必能到同一水準。§9 預先宣告該結果的標籤，**它是結果不是失敗**。

---

## 3. 凍結的設計決定：必須 scratch，不得 warm start

[SOURCE] [ROADMAP §9 第 2 項](ROADMAP.md) 寫的是「scratch **或** tracked warm start」。本規格把它**收窄為 scratch**，理由如下。

[RESULT] 版本控制內唯一可用的 warm start 候選是 `backend/rl/ppo_stand_start_walk_stop_0p7_phase_observable_v5.zip`（已 tracked，`1,983,126` bytes）。它的**檔案**可由 digest 重建，但它的**訓練過程**不可重建——這正是 §1 所述的缺陷。

[INFERENCE] 從它 warm start，會得到一條起點 digest 可驗證、但 pretraining 仍然不可重建的線。那樣 `CONDITIONAL_ON_FIXED_WARM_START` 原封不動地保留下來，而那個標籤正是本線存在的理由。**用一條新線去複製它要移除的限制，等於沒做。**

[RESULT] 因此凍結：**每個 replicate 從 scratch 獨立訓練，`warm_start_policy_id` 與 `resume` 皆為 `null`**，5 個 replicate 因此擁有真正獨立的 pretraining seed。

[BLOCKER] 代價必須明說：scratch 比 fine-tune 難得多，§2 第 3 項的失敗可能性真實存在。本規格選擇承擔該風險，而不是選一條保證跑得完、但答不了原問題的路。

---

## 4. 兩個待決欄位（專案負責人）

[BLOCKER] 本規格在這兩格填定之前**不得凍結、不得執行**。兩者都必須在看到任何訓練曲線之前固定。

### 4.1 `CHECKPOINT_STORAGE`（`PUB-B1` 的核心要求）

「每個 checkpoint 進版控或 immutable storage」目前**沒有可用的機制**：

| 量測 | 值 |
|---|---|
| 現行 repo `.git` 大小 | `11 MB` |
| 單一 policy artifact | `1.9 MB` |
| `git lfs` 是否可用 | **否**（`git: 'lfs' is not a git command`） |
| 現行全量 run 的 `checkpoint_interval`（`backend/rl/train_ppo.py:705`） | `2_000_000` —— 2M 以下的 run **不存任何中間 checkpoint** |
| 本線若每 `250,000` 步存一次、`2,000,000` 步 × 5 replicates | `40` 個 checkpoint ≈ `76 MB` |

選項（未排序，成本與可攜性各異）：`GIT_DIRECT`（直接進 repo）／`GIT_LFS`（需先啟用）／`RELEASE_ASSETS`（GitHub release）／`EXTERNAL_IMMUTABLE`（外部儲存，需 URL 與 digest 清單）。

[BLOCKER] 選定後本規格 §7 必須寫入**具體的保留規則與驗證方式**；`RELEASE_ASSETS` 與 `EXTERNAL_IMMUTABLE` 另需一條「離線也能重驗 digest」的路徑，否則證據會依賴一個可能消失的外部服務。

### 4.2 `FULL_EXPOSURE_THRESHOLD`（`PUB-B2` 的出口條件）

[SOURCE] `PUB-B2` 的 exit condition 是「reference policy 在 DEV seeds 上達到**事先凍結**的 full-exposure 比例」。該比例目前**沒有值**。

[RESULT] 可用來定位的既有量測：

| Arm | full-exposure 比例 | 出處 |
|---|---|---|
| `V7A_REWARD_ONLY`（v7 的 reference） | `143/150 = 0.953333` | seedvar 執行 |
| `V7B_REDUCED_JOINT_ENVELOPE` | `120/150 = 0.800000` | 同上 |
| `V7C_FILTERED_ACTION` | `0/150` | 同上 |

[INFERENCE] `PUB-B2` 的用途是讓後續比較落在 `R0`／`R1` 而非 `R3`／`R4` regime，所以門檻必須**高於** v7 reference 的 `0.953333`——否則新線不比舊線好，`PUB-B3` 仍會被 censoring 擋住。建議值 `1.0`（全部 150 個 episode 皆 full exposure），退一步為 `0.98`。

[BLOCKER] 門檻一旦凍結，**不得因為結果而下調**。未達門檻是 `PUB-B2` `NOT_ATTAINED`，是一項結果。

---

## 5. 凍結的訓練設計

| 項目 | 值 | 理由 |
|---|---|---|
| Replicate 數 | `5` | 與 seedvar 相同，使兩條線的 method-level 分母可比 |
| 起點 | **scratch**（`warm_start_policy_id: null`、`resume: null`） | §3 |
| Training seed（每 replicate） | `9100`、`9112`、`9124`、`9136`、`9148` | 與既有 11 個 training seed 全部不相交；stride `12` = `parallel_envs`，使 environment seed block 互不重疊 |
| `parallel_envs` | `12` | 與 v5／v7 相同 |
| Environment seed block（每 replicate） | `[seed, seed + 11]` | 同上 |
| `planned_timesteps`（每 replicate） | `2_000_000` | 與 v5 的 `planned_timesteps` 相同；為**上限**，在看到任何曲線之前固定，且**永不上調**（沿用三個 budget probe 的紀律） |
| Task | `stand_start_walk_stop_v1`，9.0 s、500 Hz physics、50 Hz control、assist OFF | [MOTION_TASK_SPEC](MOTION_TASK_SPEC.md)；**不得修改** |
| Profile id | `stand_start_walk_stop_0p7_tracked_lineage_b1_r<0..4>` | 新 profile，不重用任何既有 id |
| Protocol 欄位 | `tracked_lineage_protocol_id`（第三個互斥身分） | 與 `pilot_protocol_id`／`seedvar_protocol_id` 互斥，沿用 `SEEDVAR-AMENDMENT-01` 的作法 |

[RESULT] 依 seedvar 實測吞吐（`122,880` steps ≈ `73` s，4 cores、`OMP_NUM_THREADS=1`，約 `1,683` steps/s），`2,000,000` steps ≈ `20` 分鐘／replicate，5 個 ≈ `1.7` 小時。

[BLOCKER] 執行環境是 **ephemeral container**。未 commit／push 的產出會與容器一起消失，因此 §10 的執行順序要求逐 replicate 保留，而非全部跑完才保留。

---

## 6. Driver 身分與揭露

### 6.1 本線要對 `train_ppo.py` 做的修改（凍結範圍）

1. 新增第三個互斥的 protocol 身分 `tracked_lineage_protocol_id`，以及由 replicate index 解析 training seed 的路徑（不得由命令列指定 seed）。
2. 讓 `checkpoint_interval` 可由 protocol 決定，使 lineage 成為可能（現行 `:705` 的 `2_000_000` 使 2M 以下的 run 不存中間 checkpoint）。

[BLOCKER] **不得**修改既有的 pilot 與 seedvar 分支的檢查順序。哪一個 rejection 先觸發本身是可觀察行為，`SEEDVAR-AMENDMENT-01` 已就同一理由保留原順序。

### 6.2 兩個 digest 並存（`TL-D` 規則）

[RESULT] 本 protocol 必須同時保留：

| 欄位 | 意義 |
|---|---|
| `training_driver_source_sha256` | 本線執行時 `backend/rl/train_ppo.py` 的 digest |
| `superseded_training_driver_source_sha256` | `sha256:877da3b41e7c44ce73758877f40e257e45c6203b045eb9e2d3cd5aa6f606f6ce`，即 2026-09-08 保留證據所用的 driver |

[BLOCKER] 並存不是形式：保留的 seed-variance 證據是在**另一份 driver** 上產生的，任何把兩條線並排比較的敘述都必須帶著這件事。本 protocol 是該事實的具名揭露處（[RUN_MANIFEST_LOCK_BINDING_SPEC §15.4](RUN_MANIFEST_LOCK_BINDING_SPEC.md) 指定）。

### 6.3 執行期重算

[RESULT] 本 contract 於執行前重算 `train_ppo.py` 與 `eval_policy.py` 的 digest 並比對本 protocol 的 pin，不符即拒絕執行。這補上了 seedvar protocol **沒有**的那道檢查。

---

## 7. Checkpoint lineage（`CHECKPOINT_STORAGE` 填定後補完）

[RESULT] 不論選哪個儲存方式，下列規則凍結：

| ID | 規則 |
|---|---|
| `TL-CK-01` | 每個保留的 checkpoint 記錄 `relative_path`、`bytes`、`sha256`、`realized_timesteps`、`replicate_index` |
| `TL-CK-02` | 每個 replicate 的 checkpoint 依 `realized_timesteps` 嚴格遞增，無缺口、無重複 |
| `TL-CK-03` | 最終 policy artifact 必須是某個保留 checkpoint 的逐位元副本，或自身即為最後一個 checkpoint |
| `TL-CK-04` | 選用哪個 checkpoint 作為 reference policy，規則必須**在看到評估結果之前**凍結（§8） |
| `TL-CK-05` | 每個 run 經 `backend/rl/bind_run_lock.py` 執行，gate 必須回 `RUN_LOCK_BOUND`；`RUN_LOCK_UNBOUND` 的 run 不得作為本線證據 |

[BLOCKER] `TL-CK-04` 是本線最容易出事的地方。v5 的 checkpoint 是**在看過結果之後**從一個 regressed run 裡挑出來的，那正是它的 provenance 說不清楚的原因之一。本線不得重演。

---

## 8. 評估設計

| 項目 | 值 |
|---|---|
| Evaluation seed 範圍 | `22000–22029`（30 seeds，全新、未被任何既有 protocol 宣告） |
| 每 replicate episode 數 | `30` |
| 總 episode 數 | `5 × 30 = 150` |
| Horizon | `450` control steps（9.0 s 全程） |
| Exposure 分類 | 沿用 [V7_EXPOSURE_CENSORING_AUDIT_SPEC](V7_EXPOSURE_CENSORING_AUDIT_SPEC.md) 的詞彙，不得新增或改寫 |
| Reference checkpoint 選擇規則 | 每 replicate 取**最後一個** checkpoint；不得依評估結果挑選（`TL-CK-04`） |

[BLOCKER] `18000–18029` 為 `DEVELOPMENT_EXHAUSTED`、`19000–19029` 為 `retired_seed_range`、`20000–20029` 為 sealed FORMAL。三者**皆不得**用於本線。

---

## 9. 結果標籤（凍結、fail-closed）

| 標籤 | 條件 |
|---|---|
| `TL_REFERENCE_ATTAINED` | 5 個 replicate 的 full-exposure 比例**全部**達到 §4.2 的門檻 |
| `TL_REFERENCE_PARTIAL` | 至少一個、但非全部 replicate 達到門檻 |
| `TL_REFERENCE_NOT_ATTAINED` | 沒有任何 replicate 達到門檻 |
| `TL_BUDGET_EXHAUSTED` | 在 `2,000,000` 步上限內未達門檻且曲線未收斂 |
| `TL_METHOD_FAILURE` | 任何 contract 違反：driver digest 不符、checkpoint 序列有缺口、`RUN_LOCK_UNBOUND`、seed 越界、任何 run 崩潰 |

[BLOCKER] 前四個都是**結果**，必須據實報告；只有 `TL_REFERENCE_ATTAINED` 讓 `PUB-B2` PASS。`TL_METHOD_FAILURE` **永不降級**。

[BLOCKER] `TL_BUDGET_EXHAUSTED` 不得以「再多跑一點就到了」為由上調上限。上限在看到曲線之前已固定；要改必須是新的 protocol 版本，並揭露它是在已知結果的情況下設計的。

---

## 10. 執行順序（順序不可反）

1. 專案負責人填定 §4.1 與 §4.2。
2. 依 §4.1 補完 §7 的儲存規則。
3. 凍結本規格與 `backend/rl/tracked_lineage_training_protocol.json`，commit 並 **push**。此步之前不得修改 `train_ppo.py`。
4. 依 §6.1 修改 driver，實作 contract 與測試。
5. 逐 replicate 執行：訓練 → 保留 checkpoint → 評估 → 立即 commit／push（§5 的 ephemeral container 風險）。
6. 分析、寫 receipt、對齊文件。

---

## 11. Claim boundary

本線**只**可能支持：一條 pretraining provenance 可重建的 DEVELOPMENT 訓練線存在，以及該線 reference policy 在 `22000–22029` 上的 full-exposure 比例。

本線**不**支持：任何 controller superiority；任何 `FORMAL_EVALUATION` 結論；`paper_data_ready` 等四個 flag 的任何改變；與 v7 線的直接數值比較（不同 driver、不同起點、不同 seed）；任何 physical feasibility、safety 或 sim-to-real 陳述。

[BLOCKER] 即使 `TL_REFERENCE_ATTAINED`，`PUB-B3` 仍需另一次 point-valued variance 量測，`PUB-B4` 外部預註冊仍在解封之前。本線**不**解封 `20000–20029`。

---

## 12. 驗收（`TL-01` .. `TL-08`）

| ID | 準則 |
|---|---|
| `TL-01` | 執行前重算 `train_ppo.py`／`eval_policy.py` digest 並比對 protocol pin，不符即拒絕執行 |
| `TL-02` | protocol 同時保留現行與 superseded 的 driver digest，缺一即 fail closed |
| `TL-03` | 每個 profile 的 `warm_start_policy_id` 與 `resume` 皆為 `null`；非 null 即 fail closed（§3） |
| `TL-04` | 5 個 training seed 與既有 11 個不相交，environment seed block 互不重疊；違反即 fail closed |
| `TL-05` | evaluation seed 全部落在 `22000–22029`；碰到 `18000–18029`／`19000–19029`／`20000–20029` 即 fail closed |
| `TL-06` | checkpoint 序列滿足 `TL-CK-01`..`TL-CK-03`；缺口、重複或 digest 不符即 fail closed |
| `TL-07` | 每個 run 的 `run_lock_binding.json` 經 gate 判為 `RUN_LOCK_BOUND` |
| `TL-08` | 五個標籤各有一個正控制測試；`TL_METHOD_FAILURE` 有一個測試證明它不會被降級 |

---

## 13. 與其他文件的關係

| 文件 | 關係 |
|---|---|
| [ROADMAP §9](ROADMAP.md) | 第 2 項。本規格把「scratch 或 tracked warm start」收窄為 scratch（§3）。 |
| [PUBLICATION_PLAN](PUBLICATION_PLAN.md) | `PUB-B1`、`PUB-B2` 的執行文件；`PUB-B3` 在其後。 |
| [RUN_MANIFEST_LOCK_BINDING_SPEC](RUN_MANIFEST_LOCK_BINDING_SPEC.md) | §15.4 指定本 protocol 為 driver drift 的揭露處（§6.2）；每個 run 經其 wrapper 綁定（`TL-CK-05`）。 |
| [TRAINING_SEED_VARIANCE_SPEC](TRAINING_SEED_VARIANCE_SPEC.md) | 本線的前身。analysis unit 與 forbidden denominators 沿用，**不得**與其數值直接比較（§11）。 |
| [V7_PRETRAINING_SEED_VARIANCE_INFEASIBILITY_RECEIPT](V7_PRETRAINING_SEED_VARIANCE_INFEASIBILITY_RECEIPT_2026-09-08.md) | 本線存在的理由。 |
| [MOTION_TASK_SPEC](MOTION_TASK_SPEC.md) | task、phase 表與 11 項 criteria，**不得修改**。 |
| [MOTION_SCOPE_DECISION §2](MOTION_SCOPE_DECISION_2026-09-11.md) | 凍結順序把新增動作任務排在本項之後。 |

---

## 14. 凍結身分

[BLOCKER] 本文件目前為 `DRAFT_TWO_DECISIONS_OPEN`，**沒有** digest 被任何東西釘住。§4 填定後才產生 protocol JSON、計算並互釘三層 digest，然後才 push、才執行。在那之前本文件不是凍結規格，不得據以執行任何訓練。
