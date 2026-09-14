# Tracked-Lineage Training Line：一條可重建 provenance 的訓練線

最後更新：2026-09-14 ｜ Protocol ID：`TRACKED-LINEAGE-TRAINING-V1` ｜ 對應 gate：`PUB-B1`、`PUB-B2`、[ROADMAP §9 第 2 項](ROADMAP.md)

狀態：`FROZEN_BEFORE_EXECUTION`（§4 的兩個欄位已於 2026-09-14 由專案負責人定案；本文件與其 protocol 在任何訓練、任何 driver 修改之前 commit 並 push）

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

1. **本線會修改 `backend/rl/train_ppo.py`。** 該檔案被已執行的 `SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1` 以 `source_baseline.training_driver_source_sha256 = sha256:877da3b41e7c44ce73758877f40e257e45c6203b045eb9e2d3cd5aa6f606f6ce` 釘住，而**執行期沒有任何東西重算該 pin**。修改之後，那個 pin 對活著的 repo 就不再為真。§6.2 規定本 protocol 必須同時保留兩個 digest 並具名揭露這件事——這是 [RUN_MANIFEST_LOCK_BINDING_SPEC §15.4](RUN_MANIFEST_LOCK_BINDING_SPEC.md) 指定的揭露位置。
2. **本線是 `DEVELOPMENT`。** 它不產生 `FORMAL_EVALUATION` 資料，不存取 sealed FORMAL seeds `20000–20029`，也不觸及 `SELECT-V7-CANDIDATE-FORMAL-V1`。
3. **本線可能得不到 reference policy。** v5 是經過 v1 → curriculum-v2 → v3 → v4 → v5 的多輪 curriculum 才達到 Live 10/11；單發 scratch run 未必能到同一水準。§9 預先宣告該結果的標籤，**它是結果不是失敗**。
4. **本線不產生 `control_step_trace`，因此不產生任何 saturation 或 regime 資料。** 原因與後果見 §6.4 與 §8.2：取得逐步 trace 需要修改 `backend/rl/eval_policy.py`，而那會弄紅一個綁在 owner 已授權 protocol 上的綠測試。本規格因此把範圍**收窄為 `PUB-B1` 與 `PUB-B2`**，`PUB-B3` 需要另一份 protocol。

---

## 3. 凍結的設計決定：必須 scratch，不得 warm start

[SOURCE] [ROADMAP §9 第 2 項](ROADMAP.md) 寫的是「scratch **或** tracked warm start」。本規格把它**收窄為 scratch**，理由如下。

[RESULT] 版本控制內唯一可用的 warm start 候選是 `backend/rl/ppo_stand_start_walk_stop_0p7_phase_observable_v5.zip`（已 tracked，`1,983,126` bytes）。它的**檔案**可由 digest 重建，但它的**訓練過程**不可重建——這正是 §1 所述的缺陷。

[INFERENCE] 從它 warm start，會得到一條起點 digest 可驗證、但 pretraining 仍然不可重建的線。那樣 `CONDITIONAL_ON_FIXED_WARM_START` 原封不動地保留下來，而那個標籤正是本線存在的理由。**用一條新線去複製它要移除的限制，等於沒做。**

[RESULT] 因此凍結：**每個 replicate 從 scratch 獨立訓練，`warm_start_policy_id` 與 `resume` 皆為 `null`**，5 個 replicate 因此擁有真正獨立的 pretraining seed。

[BLOCKER] 代價必須明說：scratch 比 fine-tune 難得多，§2 第 3 項的失敗可能性真實存在。本規格選擇承擔該風險，而不是選一條保證跑得完、但答不了原問題的路。

---

## 4. 兩個已定案欄位（專案負責人，2026-09-14）

[RESULT] 兩者皆**在看到任何訓練曲線之前**定案，這是本節唯一重要的時序事實。

| 欄位 | 定案值 |
|---|---|
| `CHECKPOINT_STORAGE` | **`GIT_DIRECT`**，`checkpoint_interval = 500_000` |
| `FULL_EXPOSURE_THRESHOLD` | **`30/30 = 1.000000`**，逐 replicate 判定 |

### 4.1 `CHECKPOINT_STORAGE`（`PUB-B1` 的核心要求）

「每個 checkpoint 進版控或 immutable storage」目前**沒有可用的機制**：

| 量測 | 值 |
|---|---|
| 現行 repo `.git` 大小 | `11 MB` |
| 單一 policy artifact | `1.9 MB` |
| `git lfs` 是否可用 | **否**（`git: 'lfs' is not a git command`） |
| 現行全量 run 的 `checkpoint_interval`（`backend/rl/train_ppo.py:705`） | `2_000_000` —— 2M 以下的 run **不存任何中間 checkpoint** |
| 本線若每 `250,000` 步存一次、`2,000,000` 步 × 5 replicates | `40` 個 checkpoint ≈ `76 MB` |

選項與其實質差別：

| 選項 | 離線可驗 | 需要新基礎設施 | 代價 |
|---|---|---|---|
| `GIT_DIRECT` | **是** | 否 | repo 由 11 MB 變 49–87 MB，且每條新線再加 |
| `GIT_LFS` | 否（需 lfs client） | **是**（本容器未裝、repo 未啟用） | 每個協作者都須裝 lfs |
| `RELEASE_ASSETS` | 否（需網路） | 否 | assets **可被有寫入權者刪改**；可信度只來自 protocol 內釘的 digest |
| `EXTERNAL_IMMUTABLE` | 否（需網路） | 是（帳號、手動步驟） | 真正不可變、可給 DOI；發表時最理想，對 DEVELOPMENT 線偏重 |

[RESULT] 儲存間隔直接決定成本，故與本決定一併固定：

| `checkpoint_interval` | 每 replicate | 5 replicates 合計 | 約略大小 |
|---|---:|---:|---:|
| `250,000` | `8` | `40` | `76 MB` |
| `500,000` | `4` | `20` | `38 MB` |

[RESULT] **定案：`GIT_DIRECT`，`checkpoint_interval = 500_000`**（每 replicate `4` 個、合計 `20` 個 ≈ `38 MB`）。

[INFERENCE] 理由：它是唯一同時滿足「離線可驗」與「不需新基礎設施」的組合，與本專案 `python -I -S` 離線 exact 重算的一貫做法一致，而 `38 MB` 是一條線可接受的一次性成本。

[BLOCKER] 已知代價，不得事後當成意外：repo 由 `11 MB` 增為約 `49 MB`，且**每條新訓練線都會再加**。第三條線之前應重新評估是否改用外部 immutable storage；本 protocol 不預先承諾該轉換。

[BLOCKER] 發表時把最終 artifact 上傳外部 immutable storage 取 DOI 是**另一個步驟**，不在本 protocol 範圍內，也不由本 protocol 的任何驗收準則涵蓋。

### 4.2 `FULL_EXPOSURE_THRESHOLD`（`PUB-B2` 的出口條件）

[SOURCE] `PUB-B2` 的 exit condition 是「reference policy 在 DEV seeds 上達到**事先凍結**的 full-exposure 比例」。該比例目前**沒有值**。

[RESULT] 可用來定位的既有量測：

| Arm | full-exposure 比例 | 出處 |
|---|---|---|
| `V7A_REWARD_ONLY`（v7 的 reference） | `143/150 = 0.953333` | seedvar 執行 |
| `V7B_REDUCED_JOINT_ENVELOPE` | `120/150 = 0.800000` | 同上 |
| `V7C_FILTERED_ACTION` | `0/150` | 同上 |

[BLOCKER] **本節初稿的一個精度錯誤，在此更正。** 初稿寫「建議 `1.0`，退一步 `0.98`」，但 `0.98` 在本設計下**不存在**：§9 的 `TL_REFERENCE_ATTAINED` 是**逐 replicate** 判定，而 §8 訂每個 replicate 只有 `30` 個 episode，所以可達的比例只有 30 分之幾。`0.98` 會被進位成 `30/30`，與 `1.0` 是同一條規則。

[RESULT] 真正可選的門檻只有三個，且其中一個不可取：

| 門檻 | 每 replicate 允許的早期終止 | 與 v7 reference（`0.953333`）比較 |
|---|---|---|
| `30/30 = 1.000000` | `0` | 明顯更嚴 |
| `29/30 = 0.966667` | `1` | 略嚴 |
| ~~`28/30 = 0.933333`~~ | `2` | **比 v7 還鬆**，不可取 |

[RESULT] **定案：`30/30 = 1.000000`**，逐 replicate 判定。

[INFERENCE] 理由：`PUB-B2` 的用途是讓後續比較落在 `R0`／`R1` 而非 `R3`／`R4` regime。只要 reference 還有任何一個 episode 早期終止，它就仍然是 censored，而 v7 線的 `between_replicate_sd` 為 null 正是這個原因。`29/30` 會以較輕的形式複製同一個問題，`PUB-B3` 仍會被擋住。

[BLOCKER] `30/30` 的代價明載於此：scratch policy 在 5 個 replicate 上都做到 30/30 是很高的門檻，**很可能**得到 `TL_REFERENCE_NOT_ATTAINED`。這是在定案時已知並接受的，不得在事後被當成「門檻訂得不合理」的理由。

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
| `checkpoint_interval` | `500_000` | §4.1 定案；每 replicate 保留 `4` 個 checkpoint |
| `planned_timesteps`（每 replicate） | `2_000_000` | 與 v5 的 `planned_timesteps` 相同；為**上限**，在看到任何曲線之前固定，且**永不上調**（沿用三個 budget probe 的紀律） |
| Task | `stand_start_walk_stop_v1`，9.0 s、500 Hz physics、50 Hz control、assist OFF | [MOTION_TASK_SPEC](MOTION_TASK_SPEC.md)；**不得修改** |
| Profile id | `stand_start_walk_stop_0p7_tracked_lineage_b1_r<0..4>` | 新 profile，不重用任何既有 id |
| Protocol 欄位 | `tracked_lineage_protocol_id`（第三個互斥身分） | 與 `pilot_protocol_id`／`seedvar_protocol_id` 互斥，沿用 `SEEDVAR-AMENDMENT-01` 的作法 |

[RESULT] 依 seedvar 實測吞吐（`122,880` steps ≈ `73` s，4 cores、`OMP_NUM_THREADS=1`，約 `1,683` steps/s），`2,000,000` steps ≈ `20` 分鐘／replicate，5 個 ≈ `1.7` 小時。

[BLOCKER] 執行環境是 **ephemeral container**。未 commit／push 的產出會與容器一起消失，因此 §10 的執行順序要求逐 replicate 保留，而非全部跑完才保留。

---

## 6. Driver 身分與揭露

### 6.1 只改 `train_ppo.py`（凍結範圍）

1. 新增第三個互斥的 protocol 身分 `tracked_lineage_protocol_id`，以及由 replicate index 解析 training seed 的路徑（不得由命令列指定 seed）。
2. 讓 `checkpoint_interval` 可由 protocol 決定，使 lineage 成為可能（現行 `:705` 的 `2_000_000` 使 2M 以下的 run 不存中間 checkpoint）。

[BLOCKER] **不得**修改既有的 pilot 與 seedvar 分支的檢查順序。哪一個 rejection 先觸發本身是可觀察行為，`SEEDVAR-AMENDMENT-01` 已就同一理由保留原順序。

### 6.4 `backend/rl/eval_policy.py` 明示不修改——以及那付出的代價

[BLOCKER] **更正本規格初稿的一項錯誤陳述。** 初稿 §6.1 寫「本線要對 `train_ppo.py` 做的修改」，暗示只有該檔案會變。量測後為假：

[RESULT] `rl/eval_policy.py:391` 只在 `pilot_interface is not None` 時才把 `control_step_trace` 寫進 episode record，而 `pilot_interface` 只在 v7 pilot 或 seedvar 兩條路徑上非 `None`。一條新線若走既有的 generic path，**拿不到逐控制步 trace**；要拿到就得加第三個互斥身分，也就是修改該檔案。

[BLOCKER] 而修改該檔案會弄紅 `backend/test_v7_candidate_selection_contract.py` 的 `test_precondition_digests_match_the_pinned_sources`：它重算該檔 digest 並比對 `SELECT-V7-CANDIDATE-FORMAL-V1` 的 `evaluation_driver_source_sha256`，而該 protocol 正是專案負責人於 2026-09-10 針對 `sha256:b4e16370…` 授權的那一份。要合法修改，必須同時修訂該 protocol 並重釘 `v7_candidate_selection_contract.PROTOCOL_SHA256`——那會讓那份授權不再指向活著的 protocol，**是 owner 的決定，不是本規格能代為做的**。

[RESULT] 因此凍結：**本線不修改 `backend/rl/eval_policy.py`**，改走 generic evaluation path，並把範圍收窄為 `PUB-B1` 與 `PUB-B2`（見 §8.2 的可行性量測與 §11 的 claim boundary）。曾考慮並否決的替代方案：另寫一個專用 evaluation driver——`SEEDVAR-AMENDMENT-01` 已就同一提案記載否決理由（可比性建立在「同一份程式」而非「相似的兩份」，兩份副本的無聲分歧是更大的風險）。

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

## 7. Checkpoint lineage（`GIT_DIRECT`，已依 §4.1 補完）

### 7.1 保留位置與方式（凍結）

[RESULT] `CHECKPOINT_STORAGE = GIT_DIRECT`，因此：

| 項目 | 規則 |
|---|---|
| 保留根目錄 | `backend/tracked_lineage_evidence/<執行日期>/checkpoints/` —— **不是** gitignored 的 `backend/rl/artifacts/` |
| `.gitignore` | 必須確認上述路徑**未被**任何既有規則排除；被排除即 `TL_METHOD_FAILURE` |
| 檔名 | `r<replicate_index>-<realized_timesteps>.zip`，零填補至 `7` 位（例：`r0-0500000.zip`） |
| 每 replicate 個數 | `4`（`500_000`／`1_000_000`／`1_500_000`／`2_000_000`） |
| 合計 | `20` 個 ≈ `38 MB` |
| 索引 | `backend/tracked_lineage_evidence/<日期>/checkpoint_index.json`，逐項記 `TL-CK-01` 的五個欄位 |

[BLOCKER] `GIT_DIRECT` 的可信度來自「內容就在版本控制裡」，因此 `checkpoint_index.json` 的 digest 是**輔助**而非來源：任何人都能直接對 repo 內的檔案重算 SHA-256，不需要網路，也不需要相信索引。這正是選它的理由。

[BLOCKER] repo 體積的代價已於 §4.1 具名接受。**不得**為了省空間而事後刪除任何已保留的 checkpoint；刪除即摧毀本線唯一的產出。

### 7.2 規則（凍結）

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

### 8.1 凍結參數

| 項目 | 值 |
|---|---|
| Evaluation driver | `backend/rl/eval_policy.py` 的 **generic path**（不帶 `--pilot-arm`／`--seedvar-replicate-index`），**不修改該檔案**（§6.4） |
| 輸出 schema | `RL_TRAINING_ENV_EVALUATION_V3` |
| Evaluation seed 範圍 | `22000–22029`（30 seeds，全新、未被任何既有 protocol 宣告） |
| 每 replicate episode 數 | `30` |
| 總 episode 數 | `5 × 30 = 150` |
| Horizon | `450` control steps（9.0 s 全程） |
| Reference checkpoint 選擇規則 | 每 replicate 取**最後一個** checkpoint（`2_000_000` 步那個）；不得依評估結果挑選（`TL-CK-04`） |

[BLOCKER] `18000–18029` 為 `DEVELOPMENT_EXHAUSTED`、`19000–19029` 為 `retired_seed_range`、`20000–20029` 為 sealed FORMAL。三者**皆不得**用於本線。

### 8.2 Full exposure 如何判定（generic path 的可行性量測）

[RESULT] generic path 雖不寫 `control_step_trace`，但 `rl/eval_policy.py:325` 的 `raw_scalars` 帶有 `duration_s = round(len(rewards) * 0.02, 3)`，而 `0.02 s` 正是一個 control step。實測：`450` 步 → `9.0`，`449` 步 → `8.98`。兩者在 3 位小數下可清楚分辨。

[RESULT] 因此凍結判定規則：

| 判定 | 條件 |
|---|---|
| `FULL_EXPOSURE` | `duration_s == 9.0` **且** `outcome_state == "OBSERVED"` |
| 非 full | 其餘一切 |

[INFERENCE] 兩個條件互為交叉檢查：早期終止同時使 `duration_s < 9.0` 並使 `outcome_state` 成為 `NULL`（`EARLY_TERMINATION_REQUIRED_OUTCOME_UNOBSERVED`）。兩者不一致即表示對 driver 行為的理解有誤，應視為 `TL_METHOD_FAILURE` 而非擇一採信。

[BLOCKER] **generic path 不釘 seed schedule。** v7 與 seedvar 兩條路徑各有 `*_EVALUATION_SEED_SCHEDULE_OVERRIDE_FORBIDDEN`，generic path 沒有。因此「確實用了 `22000–22029`」只能在**分析期**由 contract 比對保留輸出的 `evaluation_seeds` 來強制，不符即 `TL_METHOD_FAILURE`。這比 driver 層的強制**弱**，明載於此而非留給讀者發現。

### 8.3 本線量不到的東西

[BLOCKER] 沒有 `control_step_trace` 就沒有逐控制步的 saturation substeps，因此本線**不產生**：

- 任何 `saturation_duty_pct` 的逐步重算或截斷 horizon 分析；
- 任何 censoring regime（`R0`..`R5`）分類；
- 任何可與 [V7_EXPOSURE_CENSORING_AUDIT_SPEC](V7_EXPOSURE_CENSORING_AUDIT_SPEC.md) 或 [R0_REGIME_PROBE_SPEC](R0_REGIME_PROBE_SPEC.md) 並列的 exposure 分析。

[RESULT] 本線只回答 `PUB-B2` 的出口條件：**reference policy 的 full-exposure 比例**。`PUB-B3` 的 point-valued between-replicate SD 需要 saturation 資料，因此需要另一份 protocol，而那份 protocol 必須先解決 §6.4 的 `eval_policy.py` 問題——那是 owner 的決定。

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

本線**只**可能支持：一條 pretraining provenance 可重建的 DEVELOPMENT 訓練線存在，以及該線 reference policy 在 `22000–22029` 上的 full-exposure 比例（`PUB-B1`、`PUB-B2`）。

本線**不**支持：任何 controller superiority；任何 `FORMAL_EVALUATION` 結論；`paper_data_ready` 等四個 flag 的任何改變；與 v7 線的直接數值比較（不同 driver、不同起點、不同 seed）；任何 saturation、censoring regime 或 exposure 分析（§8.3）；任何 physical feasibility、safety 或 sim-to-real 陳述。

[BLOCKER] 即使 `TL_REFERENCE_ATTAINED`，`PUB-B3` 仍需另一次 point-valued variance 量測，`PUB-B4` 外部預註冊仍在解封之前。本線**不**解封 `20000–20029`。

---

## 12. 驗收（`TL-01` .. `TL-08`，含 `TL-01b`）

| ID | 準則 |
|---|---|
| `TL-01` | 執行前重算 `train_ppo.py` 與 `eval_policy.py` 的 digest 並比對 protocol pin；`eval_policy.py` 必須**等於 2026-09-14 的未修改值**（§6.4），`train_ppo.py` 必須等於本線宣告的新值。任一不符即拒絕執行 |
| `TL-01b` | 保留的 evaluation 輸出其 `evaluation_seeds` 必須恰為 `22000..22029`；不符即 `TL_METHOD_FAILURE`（§8.2 的分析期強制） |
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

[RESULT] 本文件於 2026-09-14 §4 定案後凍結，並於**任何訓練、任何 `train_ppo.py` 修改之前** commit 並 push。三層互釘：

| 層 | 釘住的對象 |
|---|---|
| `backend/rl/tracked_lineage_training_protocol.json` 的 `specification_sha256` | 本文件 |
| 本線 contract 模組的 `PROTOCOL_SHA256` | 上述 protocol JSON |
| protocol 的 `source_baseline` | 執行時的 driver digest（§6.2、§6.3） |

[BLOCKER] contract 模組於 §10 第 4 步才建立，因此本次凍結 push 時只有前兩層的**第一層**已完成互釘；第二層在實作 commit 中補上並由測試比對。這與 `R0-REGIME-HORIZON-PROBE-V1` 的凍結順序相同：先 push 規則，再寫讀規則的程式。

[BLOCKER] 本文件凍結後，任何門檻、seed、budget、arm 定義或選擇規則的變更都需要**新的 protocol 版本**，並在其中揭露該變更是在已知何種結果的情況下做的。
