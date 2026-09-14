# `TRACKED-LINEAGE-TRAINING-V1` 執行 receipt

執行日期：2026-09-14 ｜ Protocol ID：`TRACKED-LINEAGE-TRAINING-V1` ｜ 規格：[TRACKED_LINEAGE_TRAINING_SPEC](TRACKED_LINEAGE_TRAINING_SPEC.md)

> ## ⚠️ 更正（2026-09-14，本 receipt 首次發布之後）
>
> **本文件初版所報的標籤 `TL_REFERENCE_NOT_ATTAINED` 是錯的。正確標籤為 `TL_BUDGET_EXHAUSTED`。**
>
> 原因：§9 定義 `TL_BUDGET_EXHAUSTED` 為「未達門檻**且曲線未收斂**」，而我在第一次分析時**根本沒有量測收斂**——`classify()` 當時的簽章是 `budget_exhausted: bool = False`，我採用了預設值。事後量測五個 replicate 的訓練曲線：末四分位斜率仍有 `+7.3` 到 `+11.9`（每 500k 步），與首四分位的比值 `0.341`–`0.536`，遠高於 `0.10` 的收斂門檻，**沒有一個收斂**。
>
> **沒有任何量測數值改變**：`0/30` × 5、`fall_rate 1.0`、`2,015,232` 步、20 個 checkpoint 全部照舊。`PUB-B1` 仍達成，`PUB-B2` 在兩種標籤下**都是** `NOT_ATTAINED`。改變的只是描述它的標籤——以及隨之而來、**更嚴**的後續限制：§9 規定 `TL_BUDGET_EXHAUSTED` **不得以「再多跑一點就到了」為由上調上限**。
>
> 完整記錄見 [規格 §17](TRACKED_LINEAGE_TRAINING_SPEC.md)（`TRACKED-LINEAGE-AMENDMENT-03-LABEL-PRECEDENCE`）與本文件 §12。**以下 §0–§11 為初版原文，刻意不改寫**，以保留當時的判斷與其依據。

結果標籤：~~`TL_REFERENCE_NOT_ATTAINED`~~ → **`TL_BUDGET_EXHAUSTED`**（見上方更正）

證據等級：`DEVELOPMENT / SIM_ONLY_MUJOCO`

---

## 0. 一句話

[RESULT] 五個 scratch replicate 全部訓練完成、全部產出版控 checkpoint lineage，但**沒有任何一個** replicate 的 reference policy 達到 `30/30` full-exposure 門檻——`150` 個 evaluation episode **全部**早期跌倒。`PUB-B1` 的「有版控 lineage 的訓練線」達成；`PUB-B2` 的「可靠完成」**未**達成。

[BLOCKER] 這是**結果不是失敗**，且是**事先宣告**的結果。規格 §3、§4.2 與 §9 在看到任何訓練曲線之前就寫明：v5 是經 v1→v5 多輪 curriculum 才到 Live 10/11，單發 scratch 未必能到，`30/30` 是很高的門檻且**很可能**得到 `TL_REFERENCE_NOT_ATTAINED`。門檻**不得**因此下調。

---

## 1. 凍結身分與三層 digest

| 層 | 檔案 | digest |
|---|---|---|
| 規格 | `docs/TRACKED_LINEAGE_TRAINING_SPEC.md` | `sha256:96bbae557de189ab3c96f698447dbbe2c6630a405992b35b112075bb6bbee674`（amendment 02 後） |
| protocol | `backend/rl/tracked_lineage_training_protocol.json` | `sha256:9963a2b25ee1640186e721ba9b7e745126b593eb083454aa33a64a709765e2fa` |
| contract | `backend/tracked_lineage_contract.py` 的 `PROTOCOL_SHA256` | 釘住上列 protocol |
| training driver | `backend/rl/train_ppo.py` | `sha256:2a3f50c0bb64c5af720d406f4ace103fe8af19f0c17d65762d6815a52faaff59` |
| superseded driver | 同上檔案在 2026-09-08 的值 | `sha256:877da3b41e7c44ce73758877f40e257e45c6203b045eb9e2d3cd5aa6f606f6ce` |
| evaluation driver | `backend/rl/eval_policy.py` | `sha256:0cf274341a10a56fbf544d86eab4bfbfd6f630056689280af51aff111b0058d4`（**未修改**） |

[RESULT] 凍結 push（commit `ddf0ab7`）發生在**任何 driver 修改之前**，符合規格 §10 第 3 步；當時三個 driver／simulator 檔案逐位元等於凍結時宣告的值。

---

## 2. 環境

[RESULT] 全部 10 次執行（5 訓練 + 5 評估）皆經 `backend/rl/bind_run_lock.py`，gate 全部回 **`RUN_LOCK_BOUND`**（`TL-CK-05`）。

| 量 | 值 |
|---|---|
| `lock_class` | `MEASURED_ENVIRONMENT_LOCK` |
| `lock_completeness` | `FULL_LOCK` |
| `threading_determinism` | `AMBIENT_THREADING_PINNED`（`OMP`／`MKL`／`OPENBLAS`／`NUMEXPR` 皆為 `1`） |
| `environment_locked_sha256` | `sha256:93d23a2703adc86a1394eacf5dece8d7229fdf742857f1a271656aa1cfeac72d` |

[RESULT] 該 `locked_sha256` 與 2026-09-08 `SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1` 執行時保留的 lock record **逐位元相同**。本線因此與其前身跑在同一個可量測的環境上。這是執行時量到的事實，不是設計目標。

---

## 3. 訓練

| replicate | seed | realized timesteps | elapsed (s) |
|---|---:|---:|---:|
| r0 | `9100` | `2,015,232` | `1800.982` |
| r1 | `9112` | `2,015,232` | `1775.052` |
| r2 | `9124` | `2,015,232` | `1776.687` |
| r3 | `9136` | `2,015,232` | `1761.201` |
| r4 | `9148` | `2,015,232` | `1775.291` |

[RESULT] 五個 replicate 全部 `warm_start_policy_id = null`、`resume = null`（`TL-03`），全部 scratch。

[RESULT] realized `2,015,232` 與 amendment 01 §15.2 的預測**完全相同**，五次皆是。該預測是在執行前由 SB3 的 rollout 粒度推導、並以 seedvar 線 planned `100,000` → realized `122,880` 交叉驗證得到的。driver 內建的斷言每次都比對，任一不符即拒絕。

[RESULT] 實測吞吐 `1,133.5` steps/s，總訓練時間 `2.469` 小時。

[BLOCKER] **更正規格 §5 的一個估計**：§5 依 seedvar 實測寫「約 `1,683` steps/s、5 個 replicate ≈ `1.7` 小時」。實測為 `1,133.5` steps/s、`2.469` 小時。估計值不是凍結參數，沒有任何門檻或設計因此改變；記於此以免下一個人沿用那個偏樂觀的數字排程。

---

## 4. Checkpoint lineage（`PUB-B1`）

| 項目 | 值 |
|---|---|
| 保留位置 | `backend/tracked_lineage_evidence/2026-09-14/checkpoints/` |
| 每 replicate | `4` 個，落在 `499,992`／`999,984`／`1,499,976`／`1,999,968` |
| 合計 | `20` 個 |
| 實際大小 | `39,899,261` bytes（`38.0 MiB`） |
| 索引 | `checkpoint_index.json`，逐項記 `TL-CK-01` 的五個欄位 |
| gitignore | `git check-ignore` 對 20 個檔案與索引皆回「未忽略」 |

[RESULT] 落點是 amendment 01 §15.2 更正後的值，不是初凍結誤寫的 `500,000` 整數倍。**由磁碟上的檔案證實**，不是只由讀 SB3 原始碼推得。

[RESULT] `38.0 MiB` 與 §4.1 決定時估的 `38 MB` 相符。`.git` 由 `11 MB` 增為 `47 MB`，落在 §4.1 具名接受的「約 `49 MB`」之內。

[RESULT] `TL-06` 驗證：20 個 checkpoint 的 `sha256` 與 `bytes` 皆與磁碟上的位元組相符，每 replicate 序列嚴格遞增、無缺口、無重複。

---

## 5. 評估（`PUB-B2`）

[RESULT] 每個 replicate 評估其 `TL-CK-04` 指定的 reference policy——**最後一個保留的 checkpoint**（`1,999,968` 步），該規則在看到任何評估結果之前就凍結。evaluation seeds `22000–22029`，每 replicate `30` episodes。

| replicate | seed | full exposure | `fall_rate` | mean `duration_s` |
|---|---:|---:|---:|---:|
| r0 | `9100` | **`0/30`** | `1.0` | `2.477333` |
| r1 | `9112` | **`0/30`** | `1.0` | `2.680000` |
| r2 | `9124` | **`0/30`** | `1.0` | `2.520000` |
| r3 | `9136` | **`0/30`** | `1.0` | `2.811333` |
| r4 | `9148` | **`0/30`** | `1.0` | `2.440000` |

[RESULT] 五個 replicate 平均值的平均為 `2.585733` s，全距 `2.440000`–`2.811333` s，任務長度為 `9.0` s。

[BLOCKER] **不得**把上表讀成 `0/150`。`150` 是 §8 明列的 forbidden denominator：判定是**逐 replicate**，method-level 分母恆為 `5`。本線的 method-level 結果是 **`0/5` 個 replicate 達到門檻**。

### 5.1 失敗型態（量測，非推測）

[RESULT] 全部 `150` 個 episode 的 `outcome_state` 皆為 `NULL`（`EARLY_TERMINATION_REQUIRED_OUTCOME_UNOBSERVED`），`fall_rate` 五個 replicate 皆為 `1.0`。

[RESULT] 跌倒時點集中在 `2.44`–`2.81` s，而凍結 phase 表中 `STEADY_WALK` 起於 `2.5` s。也就是說 policy 大致撐過初始 stand，在**進入行走的轉換處**跌倒。

[RESULT] r0 的 `mean_saturation_duty_pct = 0.0`、`worst = 0.0`：它不是把致動器推到極限而失敗，是根本沒推。`mean_lateral_drift_m = 0.219598`，跌倒方向為側向。

[INFERENCE] 合起來看，`2,015,232` 步的單發 scratch 學到了站立，沒學到起步行走。這與規格 §3 事先寫下的理由一致——v5 是經多輪 curriculum 才達成的——但本 receipt **不**宣稱「curriculum 是必要的」：那需要一個本線沒做的對照。

### 5.2 兩個曝露訊號一致

[RESULT] `TL_EXPOSURE_SIGNALS_DISAGREE` 在 150 個 episode 上**都沒有**觸發：短 `duration_s` 與非 `OBSERVED` 的 `outcome_state` 每次同時成立。量測本身是自洽的，不是兩個訊號各說各話。

---

## 6. 驗收（`TL-01` .. `TL-08`、`TL-01b`、`TL-CK-01`..`TL-CK-06`）

| ID | 結果 |
|---|---|
| `TL-01` | **PASS** — 執行前重算兩個 driver digest 並比對 protocol pin；`eval_policy.py` 等於未修改值 |
| `TL-01b` | **PASS** — 五個保留輸出的 `evaluation_seeds` 皆恰為 `22000..22029` |
| `TL-02` | **PASS** — protocol 同時保留現行與 superseded 的 training driver digest |
| `TL-03` | **PASS** — 五個 manifest 的 `warm_start_policy_id` 與 `resume` 皆 null |
| `TL-04` | **PASS** — 五個 seed 為 `9100/9112/9124/9136/9148`，與既有 11 個不相交，environment seed block 互不重疊 |
| `TL-05` | **PASS** — 無任何 seed 落入 `18000–18029`／`19000–19029`／`20000–20029` |
| `TL-06` | **PASS** — `TL-CK-01`..`TL-CK-03` 全部滿足；20 個 checkpoint digest 與大小皆與磁碟相符 |
| `TL-07` | **PASS** — 10 次執行的 gate 皆回 `RUN_LOCK_BOUND` |
| `TL-08` | **PASS** — 五個標籤各有正控制測試；一個測試證明 `TL_METHOD_FAILURE` 不被降級 |
| `TL-CK-04` | **PASS** — reference 選擇規則在看到任何評估結果之前凍結，且五次皆取最後一個 checkpoint |
| `TL-CK-05` | **PASS** — 見 `TL-07` |
| `TL-CK-06` | **PASS** — 五個被評估 policy 的 digest 皆等於該 replicate 的保留 reference checkpoint |

[RESULT] **沒有任何一項 contract 違反**，因此本次結果**不是** `TL_METHOD_FAILURE`。這一點必須明說：`TL_REFERENCE_NOT_ATTAINED` 是一次乾淨的量測得到的否定結果，不是量測壞掉。

---

## 7. 三份 amendment：我在本線留下並更正的缺陷

[BLOCKER] 三份全部在**執行前或評估前**套用，全部不使任何已保留證據失效，全部**不是門檻放寬**。

| Amendment | 缺陷 | 更正 |
|---|---|---|
| §15.1 | §5 自稱「凍結的訓練設計」卻未指定 `environment_id`、`step_length_m`、`duty`、`clearance_m`——照凍結文字**寫不出合法 profile** | 收窄為 `motion_task_phase_observable_v5` 與 v5 的 gait |
| §15.2 | §7.1 的 `500,000` 整數倍 checkpoint 在 `n_envs = 12` 下**不可達** | 更正為 `499,992`／`999,984`／`1,499,976`／`1,999,968`；realized 更正為 `2,015,232` |
| §16 | `TL-CK-03` 要求最終 artifact 是保留 checkpoint 的副本或最後一個，兩者**皆不可能**（`policy.zip` 比最後 checkpoint 多 `15,264` 步） | 「最終 policy artifact」指 `TL-CK-04` 已指定的 reference policy；另**加嚴**新增機器檢查的 `TL-CK-06` |

[RESULT] 三者皆與 §4.2 初稿的 `0.98` 同一家族：**我寫下了機制產生不出來的數字或規則**。本次執行證實了前兩項的更正值（checkpoint 落點與 realized 步數五次皆符），第三項則由 `TL-CK-06` 在五個 replicate 上實際檢查。

[BLOCKER] 一項**刻意不改**的已知瑕疵：規格 §6 小節順序為 `6.1 → 6.4 → 6.2 → 6.3`。重編號會動到 §2 與 §11 目前全部正確的交叉引用，為純版面問題改動 digest 釘住的文件代價大於收益。記於 §15.3。

---

## 8. Gate 狀態

| Gate | 之前 | 現在 | 依據 |
|---|---|---|---|
| `PUB-B1` Tracked training line | `NOT_STARTED` | **`ATTAINED`** | 20 個 checkpoint 進版控、digest 可離線重算、10 次執行皆 `RUN_LOCK_BOUND`；本線的 pretraining provenance 可重建 |
| `PUB-B2` Reliable-completion baseline | `NOT_STARTED` | **`NOT_ATTAINED`** | `0/5` replicate 達到事先凍結的 `30/30` |
| `PUB-B3` Pilot variance → N | `BLOCKED` by B2 | **仍 `BLOCKED`** | B2 未過；且本線不產生 `control_step_trace`（§6.4），另需 protocol |

[RESULT] 這個不對稱是本次最重要的結論：**本線達成了它存在的主要目的**（造出一條 provenance 可重建的訓練線），**但沒有**產出一個可靠完成任務的 reference policy。兩者是不同的事，不可互相代替。

[BLOCKER] `paper_data_ready`、`statistics_ready`、`method_level_power_ready`、`sample_size_decision_input_ready` 四個 flag **全部不變**，仍為 `false`。

---

## 9. Claim boundary

本 receipt **只**支持：

1. 一條 pretraining provenance 可重建的 `DEVELOPMENT` 訓練線存在，其 20 個 checkpoint 在版本控制內、可離線以 SHA-256 重算。
2. 該線五個 replicate 的 reference policy 在 DEV seeds `22000–22029` 上的 full-exposure 比例皆為 `0/30`。

本 receipt **不**支持：

- 任何 controller superiority 或 method 比較；
- 任何與 v7 線的直接數值比較（不同 driver、不同起點、不同 seed、不同環境）；
- 「scratch 訓練不可行」或「curriculum 是必要的」——本線只跑了一個 recipe、一個 budget，沒有對照；
- 任何 saturation、censoring regime 或 exposure 分析（§8.3：本線不產生 `control_step_trace`）；
- 任何 `FORMAL_EVALUATION` 結論。本線是 `DEVELOPMENT`，**不**解封 `20000–20029`，**不**觸及 `SELECT-V7-CANDIDATE-FORMAL-V1`；
- 任何 physical feasibility、safety 或 sim-to-real 陳述。

---

## 10. 下一步（本 receipt 不代為決定）

[BLOCKER] `TL_REFERENCE_NOT_ATTAINED` 之後有數條路，全部需要**新的 protocol 版本**，且該 protocol 必須揭露它是在已知本結果的情況下設計的：

1. **提高 budget**：本線 `2,000,000` 步的上限在看到曲線前固定，**不得**事後上調。要更多步數就是新 protocol。
2. **引入 curriculum**：與 v5 的路徑類似，但需要把每一階段的 checkpoint 都納入 lineage，否則會重演 v5 provenance 不可重建的問題。
3. **改 reward 或環境**：那是另一條線，不是本線的延長。
4. **接受現況並改以其他方式解 `PUB-B3`**。

[BLOCKER] 無論走哪條，本線的 20 個 checkpoint **不得刪除**——它們是 `PUB-B1` 的唯一產出，也是任何後續線的可重建起點。§4.1 已具名：不得為了省空間刪除已保留的 checkpoint。

[RESULT] §4.1 另記：第三條訓練線之前應重新評估是否改用外部 immutable storage。本線用掉 `38 MiB`，`.git` 現為 `47 MB`。

---

## 11. 保留物清單

| 路徑 | 內容 |
|---|---|
| `backend/tracked_lineage_evidence/2026-09-14/checkpoints/` | 20 個 checkpoint，`r<idx>-<步數補 7 位>.zip` |
| `backend/tracked_lineage_evidence/2026-09-14/checkpoint_index.json` | `TL-CK-01` 五欄位、每 replicate 的 reference digest 與 unretained byproduct digest、每 replicate 的評估摘要 |
| `backend/tracked_lineage_evidence/2026-09-14/evaluations/r<0..4>/` | 每 replicate 的 evaluation 輸出、`environment_lock.json`、`run_lock_binding.json` |

[BLOCKER] `backend/rl/artifacts/` 下的 run 目錄（含 `policy.zip`）是 **gitignored 且不是證據**。`policy.zip` 依 amendment 02 為 unretained byproduct：比 reference 多訓練 `15,264` 步、未被評估、不得作為本線產出呈現；其 digest 記在索引內，使日後若被偷換可被偵測。


---

## 12. 更正記錄：標籤由 `TL_REFERENCE_NOT_ATTAINED` 改為 `TL_BUDGET_EXHAUSTED`

日期：2026-09-14，於本 receipt 首次發布並隨 PR #17 合併**之後**。

### 12.1 錯在哪裡

[BLOCKER] §9 的兩個標籤條件是包含關係：`TL_BUDGET_EXHAUSTED` = `TL_REFERENCE_NOT_ATTAINED` 的條件 **+「曲線未收斂」**。我在 §6 宣稱所有驗收準則通過、並在 §0 指派 `TL_REFERENCE_NOT_ATTAINED` 時，**沒有量測那個附加條件**。`tracked_lineage_contract.classify()` 當時的簽章讓 `budget_exhausted` 有預設值 `False`，我就這樣拿到了標籤。

[BLOCKER] 這是我的疏失，不是工具的問題——但工具讓它變得容易發生，所以兩者都已修正：**一個可以被靜默跳過的判定，就會被跳過**。

### 12.2 量測

[RESULT] 收斂規則在套用**之前**宣告於 `backend/rl/retain_tracked_lineage_curves.py`（末四分位斜率 ≤ 首四分位的 `10%` **且**絕對值 ≤ `1.0`，單位為每 `500,000` 步的 reward 增幅）：

| replicate | 首四分位 | 末四分位 | 比值 | 收斂？ |
|---|---:|---:|---:|---|
| r0 | `+19.396` | `+7.309` | `0.377` | 否 |
| r1 | `+21.079` | `+8.497` | `0.403` | 否 |
| r2 | `+14.493` | `+7.766` | `0.536` | 否 |
| r3 | `+25.040` | `+11.888` | `0.475` | 否 |
| r4 | `+24.721` | `+8.433` | `0.341` | 否 |

[RESULT] 五個全部未收斂。訓練在被上限截斷時仍在進步，速率約為初期的三分之一到二分之一。可於 `python -I -S` 下離線重算。

### 12.3 修正了什麼

| 對象 | 修正 |
|---|---|
| 規格 | 新增 §17（amendment 03）：兩標籤同時成立時報較具體的 `TL_BUDGET_EXHAUSTED` |
| contract | `classify()` 的 `curve_converged` 改為**必填且無預設值** |
| 證據 | 訓練曲線由 gitignored 的 `artifacts/` 搶救進 `tracked_lineage_evidence/2026-09-14/training_curves/`，附 digest |

### 12.4 這個更正對本線不利

[BLOCKER] 新標籤帶著一條舊標籤沒有的限制：§9 明文規定 `TL_BUDGET_EXHAUSTED` **不得以「再多跑一點就到了」為由上調上限**。曲線未收斂正是最會誘發那個念頭的情形，而 §9 在看到任何曲線之前就封住了這條路。因此本次更正**縮小**了後續可做的事，不是放寬。

[RESULT] §10 的四條路線因此要重新排序：證據現在指向**預算不足而非方法撞牆**，但正因如此，「加 budget」必須走**新的 protocol 版本**並揭露它是在已知本結果的情況下設計的。這不是繞過 §9，而是 §9 指定的唯一合法途徑。

[BLOCKER] 仍然**不能**宣稱「再多跑就會達標」。曲線未收斂只說明訓練尚未停止進步，**不**說明它會收斂到哪裡，更不說明它會跨過 `30/30`。要回答那個問題需要實際執行，而那需要新的 protocol。
