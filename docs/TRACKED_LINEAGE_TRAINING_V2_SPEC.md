# Tracked-Lineage Training Line V2：提高預算的續訓線

最後更新：2026-09-14 ｜ Protocol ID：`TRACKED-LINEAGE-TRAINING-V2` ｜ 對應 gate：`PUB-B2` ｜ 前身：[TRACKED-LINEAGE-TRAINING-V1](TRACKED_LINEAGE_TRAINING_SPEC.md)

狀態：`FROZEN_BEFORE_EXECUTION`（`CHECKPOINT_STORAGE_COST` 已於 2026-09-14 由專案負責人定案為選項 A，見 §5.3；本文件與其 protocol 在任何訓練、任何 driver 修改之前 commit 並 push）

證據等級：`DEVELOPMENT / SIM_ONLY_MUJOCO / NOT_EVIDENCE_UNTIL_EXECUTED`

---

## 0. 強制揭露：本規格是在已知 V1 結果的情況下設計的

[BLOCKER] **這是本文件最重要的一句，位置在最前面是刻意的。**

`TRACKED-LINEAGE-TRAINING-V1` 的 [§9](TRACKED_LINEAGE_TRAINING_SPEC.md) 與 [§14](TRACKED_LINEAGE_TRAINING_SPEC.md) 規定：`TL_BUDGET_EXHAUSTED` **不得**以「再多跑一點就到了」為由上調上限；要提高預算必須是**新的 protocol 版本**，並**揭露它是在已知何種結果的情況下設計的**。本文件就是那個新版本，而這一節就是那個揭露。

[BLOCKER] 具體而言，設計 V2 時**已經知道**：

1. V1 的五個 replicate 全部 `0/30` full exposure，全部在約 `2.5` s（任務長 `9.0` s）跌倒。
2. V1 的標籤是 `TL_BUDGET_EXHAUSTED`——五條訓練曲線在上限處**全部未收斂**，末四分位斜率仍有 `+7.309` 到 `+11.888`（每 `500,000` 步）。
3. 因此「預算不足」與「方法不對」兩種解釋中，V1 的證據**沒有排除前者**。

[BLOCKER] **知道這些之後才選的參數，其證據份量低於在無知情況下凍結的參數。** 本規格不假裝不是如此。讀者評估 V2 的任何結果時，都必須把這一節算進去。

### 0.1 本規格明確**不**宣稱的事

[BLOCKER] **不宣稱「再多跑就會達到 `30/30`」。** 曲線未收斂只說明訓練在被截斷時尚未停止進步；它**不**說明會收斂到哪裡，**不**說明會不會跨過門檻，也**不**說明跨過所需的步數。任何把 V1 的斜率外推到門檻的說法都沒有依據，本規格不做那件事，V2 的結果也不得被那樣解讀。

[BLOCKER] **不宣稱 V2 比 V1「更好」。** V2 是 V1 的續訓，不是獨立重跑；兩者的結果不是兩次獨立抽樣。

---

## 1. V2 改什麼、不改什麼

[RESULT] **只改一件事：預算。** 其餘一律沿用 V1，逐項對照如下。

| 項目 | V1 | V2 | 說明 |
|---|---|---|---|
| `FULL_EXPOSURE_THRESHOLD` | `30/30` | **`30/30`（不變）** | §2 |
| 起點 | scratch | **從 V1 保留 checkpoint 續訓** | §3 |
| 預算 | `2,000,000` planned | **增量 `2,000,000` planned** | §4 |
| Replicate 數 | `5` | `5`（同一批，續訓） | §3 |
| Training seeds | `9100/9112/9124/9136/9148` | 同上（續訓，不另取） | §3.2 |
| `parallel_envs` | `12` | `12` | — |
| 環境 | `motion_task_phase_observable_v5` | 同上 | — |
| `checkpoint_interval` | `500_000` | `500_000` | §5 |
| Evaluation seeds | `22000–22029` | 同上 | §6 |
| 每 replicate episodes | `30` | `30` | — |
| Analysis unit | training replicate，分母 `5` | 同上 | — |
| Forbidden denominators | `30`／`150`／`450` | 同上 | — |

[BLOCKER] **門檻一字不改，這是 V2 可信度的前提。** 在已知 V1 未達標之後下調門檻，會是本專案最嚴重的一種違規：先看結果再改判準。V2 提高的是**投入**，不是**及格線**。

---

## 2. 門檻不變（`30/30`）

[RESULT] `FULL_EXPOSURE_THRESHOLD = 30/30 = 1.000000`，逐 replicate 判定，與 V1 [§4.2](TRACKED_LINEAGE_TRAINING_SPEC.md) 逐字相同。理由也相同且未因 V1 的結果而改變：reference policy 只要還有任何一個 episode 早期終止，它就仍是 censored，而 v7 線 `between_replicate_sd` 為 null 正是這個原因。

[BLOCKER] V2 若仍未達標，**不得**在 V3 下調門檻。可以改的是投入、起點、reward 或環境；判準不行。

---

## 3. 起點：從 V1 的保留 checkpoint 續訓（tracked warm start）

### 3.1 為什麼這在 V1 時不合法、現在合法

[SOURCE] [ROADMAP §9 第 2 項](ROADMAP.md) 原文允許「scratch **或** tracked warm start」。V1 [§3](TRACKED_LINEAGE_TRAINING_SPEC.md) 把它收窄為 scratch，理由具體：當時版控內唯一的 warm start 候選是 v5 artifact，它的**檔案**可由 digest 重建但**訓練過程**不可重建，從它 warm start 會原封不動保留 `CONDITIONAL_ON_FIXED_WARM_START`。

[RESULT] **V1 的 checkpoint 沒有那個缺陷。** 它們的訓練過程完全可重建：seed 由 protocol 決定、driver digest 被釘住、環境 lock 逐位元記錄、每 `500,000` 步的中間 checkpoint 都在版控裡。這正是 `PUB-B1` 達成所解鎖的東西——**專案第一次擁有一個 provenance 可重建的 warm start**。

[INFERENCE] 因此 V2 採 tracked warm start 不是放寬 V1 的規則，而是使用 V1 的**產出**。V1 §3 禁止的是「從不可重建的起點出發」，而不是「從任何起點出發」。

### 3.2 續訓而非重跑：這是設計選擇，也是限制

[RESULT] V2 的五個 replicate 是 V1 五個 replicate 的**延續**，沿用同一組 training seed，各自從自己的 reference checkpoint 接續。

| replicate | seed | resume 來源（V1 保留 checkpoint，`1,999,968` 步） |
|---|---:|---|
| r0 | `9100` | `sha256:7df3fbae65cb73780a9278b78da7c597c77e54865ae5465d470d0f68e956e494` |
| r1 | `9112` | `sha256:9910b34aa0475e9416af534…`（完整值釘於 protocol） |
| r2 | `9124` | `sha256:25becd8d8d0017c30ccdeae…` |
| r3 | `9136` | `sha256:a08e606931410196f1f5e74…` |
| r4 | `9148` | `sha256:dd3eb73c78a61a988d32c76…` |

[BLOCKER] **resume 來源必須是 `TL-CK-04` 指定的 reference checkpoint（`1,999,968` 步），不得是 `policy.zip`。** 後者依 V1 [amendment 02](TRACKED_LINEAGE_TRAINING_SPEC.md) 是 unretained byproduct，比 reference 多訓練 `15,264` 步且不在版控內。用它會讓 V2 的起點無法離線重建。

[BLOCKER] **代價：V2 的 replicate 與 V1 的不是獨立樣本。** 兩者共用前 `1,999,968` 步。因此**不得**把 V1 與 V2 的結果並列當成兩次獨立量測，也不得由此估計 method variance。V2 回答的是「同一批 replicate 在更多預算下如何」，不是「這個方法的變異有多大」。

### 3.3 曾考慮並否決的替代方案

[RESULT] **另起五個 scratch replicate、直接給 `4,000,000` 步上限。** 否決理由有二：其一，它丟棄已完成且已進版控的 `2,015,232` × 5 步訓練，成本加倍而多得到的只有「獨立性」，而獨立性對 V2 要回答的問題並非必要；其二，歷史上唯一在本任務達成 Live 10/11 的 policy（v5）正是「訓練過的起點 + 一段約 `2,000,000` 步的最後階段」這個結構，V2 續訓與該結構同形，全新 scratch 則否。

[BLOCKER] 但這個否決**有代價且必須記著**：V2 無法區分「更多總步數有效」與「續訓這個特定結構有效」。要分離兩者需要 scratch 對照組，本規格**不含**該對照組，因此**不得**宣稱已分離。

---

## 4. 預算與它的錨點

### 4.1 錨點：v5 的最後階段，而非 V1 的曲線

[BLOCKER] 預算**不是**由 V1 的斜率外推得出的——那正是 §0.1 禁止的推論。錨點取自一個**早於 V1、與 V1 結果無關**的事實。

[RESULT] 量測自 `backend/rl/training_profiles.json`：

| profile | `planned_timesteps` | status |
|---|---:|---|
| `stand_start_walk_stop_0p7_v1` | `50,000,000` | `EARLY_STOPPED_FAILED_SPEED_GATE` |
| `..._curriculum_v2` | `20,000,000` | `LIVE_500HZ_EVALUATED_FAIL_LATERAL_SATURATION` |
| `..._path_efficiency_v3` | `10,000,000` | `DEVELOPMENT_4M_FAIL_NOFALL_STOP` |
| `..._path_stop_v4` | `2,000,000` | `DEVELOPMENT_0P5M_FAIL_ONE_STOP_SEED` |
| `..._phase_observable_v5` | `2,000,000` | `LIVE_500HZ_FAIL_SATURATION_DUTY_38P422` |

[BLOCKER] **這些是 planned 不是 realized**，`EARLY_STOPPED`、`DEVELOPMENT_4M`、`DEVELOPMENT_0P5M` 三個 status 明確指出實際步數低於 planned。因此其總和 `84,000,000` **不得**被當成「歷史上足夠的預算」——本規格不那樣使用它。

[RESULT] 可用的是**最後一階段**的量：v5 的 `planned_timesteps = 2,000,000`，在一個已訓練的起點之上，達到 Live 10/11。V1 以同樣的 `2,000,000` **從 scratch** 出發，在 `2.5` s 跌倒。同樣的量、不同的起點、不同的結果。

[RESULT] **定案：增量 `planned_timesteps = 2,000,000`**，即在 V1 的起點上再加一個「v5 最後階段」大小的預算。

[INFERENCE] 理由是結構對應而非數值外推：V2 = 可重建的起點 + 一段 v5 尺寸的最後階段。這是本專案唯一有過成功先例的結構。

[BLOCKER] 這個錨點的弱點必須明說：v5 的起點是經 v1→v4 多輪 curriculum 的，V1 的起點只有一輪 `2,015,232` 步 scratch。兩者**不等價**。所以 V2 的結構只是「與 v5 同形」，不是「與 v5 等價」。

### 4.2 已驗證的步數算式

[RESULT] SB3 在 `reset_num_timesteps=False` 時於 `_setup_learn` 執行 `total_timesteps += self.num_timesteps`，故增量語義成立。實際驗證後的數字：

| 量 | 值 |
|---|---:|
| resume 起點 | `1,999,968` |
| 增量 planned | `2,000,000` |
| 停止條件 | `num_timesteps >= 3,999,968` |
| 增量 realized | `2,015,232`（`82` 個 rollout × `24,576`） |
| **總 realized** | **`4,015,200`** |

[BLOCKER] `4,015,200 > 3,999,968` 與 V1 相同，是 rollout 粒度的既有行為，**不是**上限被上調。`TL2_BUDGET_EXHAUSTED` 仍以凍結的增量 `2,000,000` 判定。

[RESULT] 本算式在凍結前先驗證，與 V1 [amendment 01 §15.2](TRACKED_LINEAGE_TRAINING_SPEC.md) 的教訓一致：**不寫下機制產生不出來的數字**。

---

## 5. Checkpoint lineage

### 5.1 落點（已驗證）

[RESULT] `checkpoint_interval = 500_000`，`save_freq = 500_000 // 12 = 41_666`，callback 於每次 `learn()` 重新計數，故落點為 `1,999,968 + 499,992k`：

| k | `realized_timesteps` |
|---:|---:|
| 1 | `2,499,960` |
| 2 | `2,999,952` |
| 3 | `3,499,944` |
| 4 | `3,999,936` |

[RESULT] 每 replicate `4` 個，合計 `20` 個。與 V1 的 20 個合起來，`0` 到 `4,015,200` 的 lineage 粒度一致。

### 5.2 保留規則

[RESULT] 沿用 V1 §7：`GIT_DIRECT`，根目錄 `backend/tracked_lineage_evidence/<執行日期>/checkpoints/`，檔名 `r<idx>-<步數補 7 位>.zip`，索引記 `TL-CK-01` 的五個欄位。

[BLOCKER] **V1 的 20 個 checkpoint 不得刪除。** 它們是 V2 起點的唯一可重建來源；刪掉它們會讓 V2 的 provenance 立刻斷掉，也會摧毀 `PUB-B1` 的產出。

### 5.3 儲存成本（專案負責人已定案：選項 A）

[RESULT] **定案：選項 A，`checkpoint_interval = 500_000`**（專案負責人，2026-09-14，在看到任何 V2 訓練曲線之前）。

| 量 | 值 |
|---|---:|
| V2 新增 checkpoint | `20` 個，約 `38 MB` |
| 現行 `.git` | `47 MB` |
| V2 之後 `.git` | **約 `85 MB`** |

[BLOCKER] V1 [§4.1](TRACKED_LINEAGE_TRAINING_SPEC.md) 具名接受的是「約 `49 MB`」，並寫明「**第三條線之前應重新評估是否改用外部 immutable storage**」。V2 是第二條線，`85 MB` **超出** V1 決定時所接受的範圍，因此需要一次新的確認而不是沿用。

[RESULT] 曾提供的兩個選項與定案：

| 選項 | `checkpoint_interval` | V2 checkpoint 數 | 新增 | `.git` 之後 | |
|---|---:|---:|---:|---:|---|
| **A** | `500_000` | `20` | `38 MB` | `85 MB` | **定案** |
| B | `1_000_000` | `10` | `19 MB` | `66 MB` | 未採用 |

[INFERENCE] 選 A 的理由：與 V1 粒度一致，使 `0`–`4,015,200` 的完整 lineage 均勻，較易辯護也較易推論。B 以一半的 lineage 解析度換約 `19 MB`。

[BLOCKER] **`85 MB` 是已具名接受的代價，不得事後當成意外。** 且 V1 §4.1 的「第三條線之前應重新評估外部 immutable storage」在本次**並未被取消**——它只是被判定尚未到期。第三條線之前仍須做該評估。

[BLOCKER] **不得**為了省空間刪除任何已保留的 checkpoint，V1 的 20 個與 V2 的 20 個皆然。

---

## 6. 評估

[RESULT] 沿用 V1 §8：走 `backend/rl/eval_policy.py` 的 generic path（**本線同樣不修改該檔案**），evaluation seeds `22000–22029`，每 replicate `30` episodes，full exposure 判定為 `duration_s == 9.0 AND outcome_state == 'OBSERVED'`，兩訊號不一致即 `TL2_METHOD_FAILURE`。

[BLOCKER] **`22000–22029` 在 V1 已使用過一次，V2 是第二次使用。** 這必須揭露：該範圍對本任務不再是「未檢視」的。V2 沿用它是為了與 V1 可比——換新範圍會讓兩者的差異混入 seed 差異。代價是這組 seed 在 V2 之後應視為 `DEVELOPMENT_EXHAUSTED`。

[BLOCKER] generic path 沒有 driver 端的 seed schedule 保護，故沿用 V1 的 `TL-01b`：保留輸出的 `evaluation_seeds` 必須恰為 `22000..22029`，不符即 `TL2_METHOD_FAILURE`。

[RESULT] 評估對象為 V2 每個 replicate 的**最後一個保留 checkpoint**（`3,999,936` 步），選擇規則在看到任何評估結果之前凍結，與 V1 `TL-CK-04` 同。

---

## 7. Driver 修改與揭露

[RESULT] V2 需要對 `backend/rl/train_ppo.py` 做兩項修改：

1. 新增第四個互斥 protocol 身分 `TRACKED-LINEAGE-TRAINING-V2`，其 request guard **要求** `--resume-from` 指向本 protocol 釘住的 reference checkpoint（V1 的 guard 逐行不動，仍拒絕 resume）。
2. 放行 resume 來源位於 `backend/tracked_lineage_evidence/`。

[RESULT] 第 2 項是**加強而非放寬**：現行 guard 要求 resume artifact 位於 `backend/rl/artifacts/`，而該目錄是 gitignored 的；改為允許版控內的證據目錄，等於允許一個**可離線重建**的來源，比原本的更可信。原有的 `artifacts/` 路徑仍然接受，既有行為不變。

[BLOCKER] 本線會再次修改 `train_ppo.py`，使 V1 protocol 的 `training_driver_source_sha256`（`sha256:2a3f50c0…`）對活著的 repo 不再為真——與 V1 對 seedvar 造成的情況同型。V2 的 protocol 必須**同時保留**新舊兩個 digest 並具名揭露，位置與理由見 [RUN_MANIFEST_LOCK_BINDING_SPEC §15.4](RUN_MANIFEST_LOCK_BINDING_SPEC.md)。

[BLOCKER] **`backend/rl/eval_policy.py` 仍然不修改**，理由與 V1 [§6.4](TRACKED_LINEAGE_TRAINING_SPEC.md) 相同：修改它會弄紅一個綁在專案負責人 2026-09-10 授權之 protocol 上的綠測試。因此 V2 同樣**不產生** `control_step_trace`，同樣**不**涵蓋 `PUB-B3`。

---

## 8. 結果標籤（凍結、fail-closed）

| 標籤 | 條件 |
|---|---|
| `TL2_REFERENCE_ATTAINED` | 5 個 replicate 的 full-exposure 比例**全部**達 `30/30` |
| `TL2_REFERENCE_PARTIAL` | 至少一個、但非全部達標 |
| `TL2_REFERENCE_NOT_ATTAINED` | 沒有任何 replicate 達標，**且**曲線已收斂 |
| `TL2_BUDGET_EXHAUSTED` | 沒有任何 replicate 達標，**且**曲線未收斂 |
| `TL2_METHOD_FAILURE` | 任何 contract 違反 |

[RESULT] **標籤定義已依 V1 [amendment 03](TRACKED_LINEAGE_TRAINING_SPEC.md) 修正為互斥**：`TL2_REFERENCE_NOT_ATTAINED` 加上「曲線已收斂」條件，兩者不再可能同時成立。V1 的缺陷不在 V2 重演。

[BLOCKER] 收斂判定沿用 `backend/rl/retain_tracked_lineage_curves.py` **既有且已宣告**的規則（末四分位斜率 ≤ 首四分位的 `10%` **且**絕對值 ≤ `1.0`，單位每 `500,000` 步）。該規則在 V1 就已宣告並套用，**V2 不得為了得到想要的標籤而調整它**。

[BLOCKER] 判定收斂的參數**必填無預設**，沿用 V1 amendment 03 對 `classify()` 的加嚴。

[BLOCKER] **若 V2 再次得到 `TL2_BUDGET_EXHAUSTED`**：那是結果，必須據實報告。它**不**授權直接再加預算——V3 仍須是新的 protocol 版本，並揭露它是在已知 V1 與 V2 兩次結果的情況下設計的。每一次加碼都必須付這個揭露成本，這正是防止無限加碼直到「贏」的機制。

---

## 9. 執行順序（順序不可反）

1. [DONE 2026-09-14] 專案負責人確認 §5.3 的儲存成本：選項 A。
2. 凍結本規格與 `backend/rl/tracked_lineage_training_v2_protocol.json`，commit 並 **push**。此步之前不得修改 `train_ppo.py`。
3. 依 §7 修改 driver，實作 contract 與驗收準則，補釘 digest。
4. 逐 replicate 執行：續訓 → 保留 checkpoint → 評估 → 立即 commit／push（容器為 ephemeral）。
5. 量測收斂、指派標籤、寫 receipt、對齊文件。

---

## 10. 驗收（`TL2-01` .. `TL2-09`）

| ID | 準則 |
|---|---|
| `TL2-01` | 執行前重算 `train_ppo.py` 與 `eval_policy.py` digest 並比對 pin；`eval_policy.py` 必須等於未修改值 |
| `TL2-02` | protocol 同時保留 V2 與 V1（superseded）的 training driver digest |
| `TL2-03` | 每個 run 的 `resume` 非 null，且其 `sha256` 恰等於本 protocol 釘住的該 replicate V1 reference checkpoint；`warm_start` 必須為 null |
| `TL2-04` | resume 來源路徑位於 `backend/tracked_lineage_evidence/`，非 gitignored 目錄 |
| `TL2-05` | 5 個 training seed 與 V1 相同且順序對應；evaluation seeds 恰為 `22000..22029` |
| `TL2-06` | checkpoint 落點恰為 `2,499,960`／`2,999,952`／`3,499,944`／`3,999,936`（選項 A）；缺口、重複或 digest 不符即 fail closed |
| `TL2-07` | 每個 run 的 gate 判為 `RUN_LOCK_BOUND` |
| `TL2-08` | 被評估 policy 的 digest 等於某個 V2 保留 checkpoint（沿用 V1 `TL-CK-06`） |
| `TL2-09` | 五個標籤各有正控制測試；`TL2_METHOD_FAILURE` 有測試證明不被降級；收斂參數無預設值 |

---

## 11. Claim boundary

本線**只**可能支持：V1 的五個 replicate 在額外 `2,015,232` 步之後，其 reference policy 在 `22000–22029` 上的 full-exposure 比例。

本線**不**支持：

- 「更多步數會達到 `30/30`」——見 §0.1；
- V1 與 V2 的獨立比較或任何 method variance 估計（同一批 replicate 的續訓，非獨立樣本，§3.2）；
- 「續訓優於 scratch」或「總步數是關鍵因素」——無對照組，§3.3；
- 任何 controller superiority、`FORMAL_EVALUATION` 結論、saturation／censoring regime 分析；
- 任何 physical feasibility、safety 或 sim-to-real 陳述。

[BLOCKER] 本線是 `DEVELOPMENT`：**不**解封 `20000–20029`，**不**觸及 `SELECT-V7-CANDIDATE-FORMAL-V1`，**不**改變 `paper_data_ready` 等四個 flag。

---

## 12. 與其他文件的關係

| 文件 | 關係 |
|---|---|
| [TRACKED_LINEAGE_TRAINING_SPEC](TRACKED_LINEAGE_TRAINING_SPEC.md) | V1。本規格的起點、預算錨點的對照、以及 §0 揭露義務的來源（其 §9、§14）。 |
| [TRACKED_LINEAGE_TRAINING_RECEIPT_2026-09-14](TRACKED_LINEAGE_TRAINING_RECEIPT_2026-09-14.md) | V1 的執行結果與 §12 的標籤更正。本規格存在的理由。 |
| [ROADMAP §9 第 2 項](ROADMAP.md) | 其原文允許的「tracked warm start」在 V1 達成 `PUB-B1` 之後才真正可用（§3.1）。 |
| [PUBLICATION_PLAN](PUBLICATION_PLAN.md) | `PUB-B2` 的第二次嘗試；`PUB-B1` 已達成不受本線影響。 |
| [RUN_MANIFEST_LOCK_BINDING_SPEC §15.4](RUN_MANIFEST_LOCK_BINDING_SPEC.md) | 指定本 protocol 為 driver drift 的揭露處（§7）。 |
| [MOTION_TASK_SPEC](MOTION_TASK_SPEC.md) | task、phase 表與 11 項 criteria，**不得修改**。 |

---

## 13. 凍結身分

[RESULT] 本文件於 §5.3 確認後凍結，並於**任何 driver 修改之前** commit 並 push。三層互釘方式與 V1 相同：protocol 釘規格、contract 模組釘 protocol、protocol 的 `source_baseline` 釘執行時的 driver digest。

[BLOCKER] 凍結後，門檻、seed、budget、起點定義、收斂規則或選擇規則的任何變更都需要**再一個新的 protocol 版本**，並揭露它是在已知 V1 與 V2 結果的情況下設計的。
