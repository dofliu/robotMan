# Run Manifest Lock Binding：把 `ENVIRONMENT-LOCK-V1` 綁進每一條 pipeline 的 run 身分

最後更新：2026-09-13 ｜ Contract ID：`RUN-MANIFEST-LOCK-BINDING-V1` ｜ 對應 blocker：[ROADMAP §9 第 1 項](ROADMAP.md)、[VV_PLAN](VV_PLAN.md) V0-R02

狀態：`FROZEN_BEFORE_IMPLEMENTATION`（本文件與其 protocol JSON 在任何 producer 被修改之前 commit 並 push；範圍、詞彙、記錄 schema、執行期規則與 fail-closed 標籤全部在寫任何實作之前固定）

證據等級：`INFRASTRUCTURE / NOT_EVIDENCE / SIM_ONLY_MUJOCO`

---

## 1. 這份規格要解決什麼

[SOURCE] V0 的具名 blocker：[ROADMAP §3 第 5、7 項](ROADMAP.md)與 [PROJECT_STATUS](PROJECT_STATUS.md) 的 V0 列都寫著同一句——**lock record 尚未綁進所有 pipelines 的 run manifest**。[ENVIRONMENT_LOCK_SPEC](ENVIRONMENT_LOCK_SPEC.md) 已把 software environment identity 從 `>=` floor 變成可量測、可重驗的 record，但一份沒有被任何 run 引用的 lock record，只證明「某台機器在某個時刻長這樣」，不證明「這份證據是在那台機器上產生的」。

[INFERENCE] 因此本規格要建立的**不是**一個新的量測，而是一個**關係**：retained run 與 lock record 之間必須有一條可重算、可 fail-closed 檢查的連結。缺少該連結時，正確的結果是「未綁定」，而不是「通過」。

---

## 2. 揭露：三件在設計之前量到的事實

[BLOCKER] 以下三件事在動手設計之前就量過。它們**直接決定**了 §3 的範圍與 §4 的詞彙；若不先揭露，本規格的取捨會看起來像偷懶。

### 2.1 同一個欄位名在兩份保留 bundle 裡是兩個不同的量

| 保留 bundle | `environment_lock_sha256` 的值 | 實際是什麼 | 產生處 |
|---|---|---|---|
| `backend/second_case_evidence/2026-09-08/bundle/raw_replicates.json` | `sha256:911b436231c8e0b1d7a3d07bca6894ce4c42c517c4a5cbbbdd0f9dff694ff631` | lock record **檔案位元組**的 digest | `backend/rl/second_case_runner.py:489`，`sha256_file(lock_src)` |
| `backend/seed_variance_evidence/2026-09-08/bundle/raw_replicates.json` | `sha256:93d23a2703adc86a1394eacf5dece8d7229fdf742857f1a271656aa1cfeac72d` | lock record 中 **`locked` 子樹**的 canonical digest | `backend/build_training_seed_variance_bundle.py:252`，`lock_status["environment_locked_sha256"]` |

[RESULT] 兩次執行所用的兩份 lock record，其 `locked_sha256` **完全相同**，都是 `sha256:93d23a2703…`——也就是說，**兩次執行確實在同一個 locked 環境裡**。但兩份 bundle 在同名欄位下保留了不同的值，差異**只來自兩條 pipeline 對該欄位的定義不同**：

| Lock record | 檔案位元組 SHA-256 | `locked_sha256` |
|---|---|---|
| `backend/environment_locks/lock-2026-09-08-second-case-execution.json` | `911b436231c8e0b1d7a3d07bca6894ce4c42c517c4a5cbbbdd0f9dff694ff631` | `sha256:93d23a2703…` |
| `backend/environment_locks/lock-2026-09-08-seedvar-execution.json` | `3a6fb310750dc84f46d65df72d9ea43663b24c97778f81312efdcea1dcfff604` | `sha256:93d23a2703…` |

[BLOCKER] 一個讀者比較 `911b4362` 與 `93d23a27`，會得到「兩份證據來自不同環境」這個**錯誤**結論。這是一個**現存的、活著的** provenance 缺陷，不是假想的風險。它決定了 §4：新綁定必須同時保留兩個 digest，且**永久禁用** `environment_lock_sha256` 這個名稱。

### 2.2 改 `backend/rl/eval_policy.py` 會弄紅一個目前綠色的測試

[RESULT] `backend/test_v7_candidate_selection_contract.py:231-239` 的 `test_precondition_digests_match_the_pinned_sources` **對 `backend/rl/eval_policy.py` 重算 SHA-256**，並斷言它等於 `SELECT-V7-CANDIDATE-FORMAL-V1` 的 `execution_precondition_source_digests.evaluation_driver_source_sha256` = `sha256:0cf274341a10a56fbf544d86eab4bfbfd6f630056689280af51aff111b0058d4`。該值今日與磁碟相符。

[BLOCKER] 該 protocol（`sha256:b4e16370b5744c510fa11b06343dafb3c1893711639721a406504720bbe99b58`）**已於 2026-09-10 由專案 owner 針對該 digest 授權 formal evaluation**（[PUB_B0_AUTHORIZATION_RECEIPT](PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10.md)）。修改 protocol JSON 以重釘 driver digest，會讓那份授權不再指向活著的 protocol；這是 owner 的決定，不是本工作項的決定。

[BLOCKER] **更正一項先前的陳述。** 在設計討論中我說過「沒有東西會重算這些 driver digest」。那句話對 `SEEDVAR-...-V1` 的 `source_baseline` 為真，對 `SELECT-V7-CANDIDATE-FORMAL-V1` 的 `execution_precondition_source_digests` **為假**——後者有一個測試主動重算。範圍因此改變。

### 2.3 改 `backend/rl/train_ppo.py` 不會弄紅任何測試，但會讓一個**已執行** protocol 的 pin 悄悄變成假的

[RESULT] `backend/rl/training_seed_variance_protocol.json` 的 `source_baseline.training_driver_source_sha256` = `sha256:877da3b41e7c44ce73758877f40e257e45c6203b045eb9e2d3cd5aa6f606f6ce`，今日與磁碟相符。**沒有任何測試或 contract 在執行期重算它。**

[RESULT] 該 protocol JSON 本身被 `backend/test_training_seed_variance_contract.py:181`（`sha256_file(DEFAULT_PROTOCOL) == PROTOCOL_SHA256`）釘住，也被 `backend/rl/r0_regime_probe_protocol.json` 的 `parent_protocol_sha256` 釘住。它**不可修改**。

[INFERENCE] 所以改 `train_ppo.py` 的代價，是讓一份**已經執行完畢、證據已保留**的 protocol 的來源 pin 在無人察覺的情況下變假，且沒有任何機制會報警。這正是本專案存在的理由所要防的那一類衰變。

---

## 3. 凍結的範圍

### 3.1 逐 producer 的處置（凍結）

| # | Producer | Run 級身分記錄 | 目前 lock 狀態 | 本規格的處置 |
|---|---|---|---|---|
| 1 | `backend/rl/train_ppo.py` | `RL_TRAINING_RUN_V2`（`run_manifest.json`） | 無任何 lock 欄位 | **IN SCOPE**，`SIDECAR_ONLY`（理由：§2.3） |
| 2 | `backend/rl/eval_policy.py` | `RL_TRAINING_ENV_EVALUATION_V4`／`V3` | 無任何 lock 欄位 | **IN SCOPE**，`SIDECAR_ONLY`（理由：§2.2） |
| 3 | `backend/build_v1_paper_bundle.py` | `PAPER_RUN_MANIFEST_V1` | 無任何 lock 欄位 | **IN SCOPE**，`EMBEDDED_AND_SIDECAR`；schema 升 `PAPER_RUN_MANIFEST_V2` |
| 4 | `backend/build_v1_analytical_bundle.py` | `PAPER_RUN_MANIFEST_V1` | 無任何 lock 欄位 | **IN SCOPE**，同第 3 項 |
| 5 | `backend/rl/second_case_runner.py` | `SECONDCASE_EXPOSURE_RAW_*` | 已於 run **之前** `verify_lock_now`（:86-105，呼叫於 :390、:433） | **已綁定（格式不同）**，不改；見 §8.2 |
| 6 | `backend/rl/second_case_budget_probe.py` | probe result 的 `environment_lock` 區塊 | 已於 run **之前** `verify_lock_now`（:311） | **已綁定（格式不同）**，不改；見 §8.2 |
| 7 | `backend/run_r0_regime_probe.py` | `probe_result.json` 的 `execution` 區塊 | 已於分析**之前**驗 `MEASURED` + `FULL_LOCK`（:38-53） | **已綁定（格式不同）**，不改；見 §8.2 |
| 8 | `backend/simulator.py` | `meta.provenance` | 無任何 lock 欄位 | **OUT OF SCOPE**；見 §3.4 |

[RESULT] 第 5–7 項說明這個 blocker **比字面窄**：三條 pipeline 已經在 run 之前驗過 lock 並把結果寫進保留輸出。真正完全未綁定的，恰好是第 1–4 項。

### 3.2 為什麼不是「把欄位直接塞進既有 manifest」

[INFERENCE] 第 1、2、8 項若直接改寫，會讓某件**今天為真**的事變成假的：第 2 項弄紅一個綠測試（§2.2），第 1 項讓一個已執行 protocol 的 pin 變假（§2.3），第 8 項破壞 deterministic content hash（§3.4）。**為了修一個 provenance blocker 而讓兩個既有 pinned digest 變成假的，等於拿本專案存在的理由去換方便。**

因此綁定採 **sidecar record**：一個獨立的 `RUN_LOCK_BINDING_V1` 檔案，以 SHA-256 釘住它所綁的 manifest。

### 3.3 Sidecar 為什麼仍然算「綁進 run manifest」

[INFERENCE] 綁定是**密碼學關係**，不是實體巢狀。`RUN_LOCK_BINDING_V1` 釘住 manifest 檔案的 digest，因此：

- 對 manifest 的任何竄改 → 綁定失配（`RUN_LOCK_MISMATCH`）；
- 對綁定的任何竄改 → 不會讓 manifest 看起來合法，因為 gate 讀的是兩者的一致性而非其一。

這與本專案在所有 protocol JSON 之間已在使用的識別方式相同。

[BLOCKER] 代價必須明說：**sidecar 是另一個檔案，可以被遺漏。** 直接呼叫 `train_ppo.py` 或 `eval_policy.py` 仍會產生一個沒有綁定的 run。本規格**不宣稱**消除了這個可能，而是把它變成一個**有名字的結果**：§7 的 gate 把「找不到綁定」定義為結果標籤 `RUN_LOCK_UNBOUND`，而不是靜默通過。`NOT_REACHED` 不等於 `PASS`。

### 3.4 `backend/simulator.py` 明示排除（凍結）

[SOURCE] `backend/simulator.py:664` 之後注入的 `meta.provenance`，其 `result_hash` 由 `:651-662` 的 stable payload 算出，而 `content_hash_excluded_fields` 凍結為 `["meta.provenance", "run_id", "created_at"]`。`backend/test_p0_contract.py:56-68` 以**不呼叫 production helper** 的獨立重算比對該 hash。

[RESULT] 因此本規格把 `simulator.py` 的 response provenance **明示排除**，理由有二，兩者獨立成立：

1. 把 lock 欄位放進 stable payload 會改變 deterministic content hash 的定義，弄紅 `test_p0_contract.py`；放進 payload 之外則不受該 hash 保護，是假的綁定。
2. `/api/simulate` 是**無狀態的請求／回應**，不是保留的 run manifest。`backend/run_traces/` 已於 `.gitignore` 排除。

[BLOCKER] 這是「每一條 pipeline」在第一天就有的**一個明示例外**，不得在後續文件中被省略或被讀成「已全部覆蓋」。解除它需要 `/api/simulate` 先有保留的 run 身分，屬另一個工作項。

### 3.5 不得修改的三個檔案（凍結，供 `LB-12` 比對）

[RESULT] 下列三個檔案在本規格凍結之日的 SHA-256 如下。本工作項完成後必須逐位元相同；任何一個改變都表示範圍被悄悄擴大了。

| 檔案 | 凍結時 SHA-256 | 不可修改的理由 |
|---|---|---|
| `backend/rl/train_ppo.py` | `sha256:877da3b41e7c44ce73758877f40e257e45c6203b045eb9e2d3cd5aa6f606f6ce` | §2.3 |
| `backend/rl/eval_policy.py` | `sha256:0cf274341a10a56fbf544d86eab4bfbfd6f630056689280af51aff111b0058d4` | §2.2 |
| `backend/simulator.py` | `sha256:c27e00a0e59b13e9e8b9c4c7fd17d885008287cdde8d8bdab68250cb17ec4cc5` | §3.4 |

[INFERENCE] 這三個 digest 同時也是本規格的自我約束：它們把「我承諾不碰哪些東西」變成一個可機器檢查的斷言，而不是一句話。

---

## 4. 詞彙（凍結）

### 4.1 兩個 digest，兩個名字

| 欄位 | 量的是什麼 | 取自 |
|---|---|---|
| `environment_locked_sha256` | lock record 中 `locked` 子樹的 canonical digest | `environment_lock.validate_lock_record(record)["locked_sha256"]` |
| `lock_record_sha256` | lock record **檔案位元組**的 SHA-256 | 對 `lock_record_path` 逐位元計算 |

[BLOCKER] 名稱 `environment_lock_sha256` **永久禁止**出現在 `RUN_LOCK_BINDING_V1` 的任何欄位名中（理由：§2.1）。實作必須有一個測試直接斷言該名稱不存在。

### 4.2 完整性門檻

[RESULT] 綁定必須記錄 `environment_lock_class`、`environment_lock_completeness`、`environment_lock_threading_determinism` 三者的**實測值**，並另外記錄 `satisfies_full_lock_requirement`，其值恰為 `environment_lock.satisfies_full_lock_requirement(record)`，亦即 `MEASURED_ENVIRONMENT_LOCK` **且** `FULL_LOCK`。

[BLOCKER] Gate **不得**只看 `lock_class`。一份 `MEASURED_ENVIRONMENT_LOCK` 但 `PARTIAL_LOCK` 的 record，意思是某個 fingerprint 量不到——那是 `RUN_LOCK_INSUFFICIENT`，不是通過。

---

## 5. `RUN_LOCK_BINDING_V1` 記錄（凍結，key set 精確）

[RESULT] 綁定記錄是一個 UTF-8 JSON object，key set **恰為**下表，多一個或少一個都 fail closed：

| 欄位 | 型別 | 規則 |
|---|---|---|
| `schema_version` | str | 恆為 `"RUN_LOCK_BINDING_V1"` |
| `contract_id` | str | 恆為 `"RUN-MANIFEST-LOCK-BINDING-V1"` |
| `binding_mode` | str | `"EMBEDDED_AND_SIDECAR"` 或 `"SIDECAR_ONLY"` |
| `sidecar_reason` | str \| null | `SIDECAR_ONLY` 時**必須**為非空字串，並具名指出禁止內嵌的 pinned digest 或測試；`EMBEDDED_AND_SIDECAR` 時必須為 `null` |
| `bound_manifest_path` | str | canonical safe relative POSIX path；不得絕對、不得含 `..` |
| `bound_manifest_schema_version` | str | 被綁 manifest 自身的 `schema_version` |
| `bound_manifest_sha256` | str | `^sha256:[0-9a-f]{64}$`，對 manifest 檔案逐位元計算 |
| `lock_record_path` | str | canonical safe relative POSIX path |
| `lock_record_sha256` | str | `^sha256:[0-9a-f]{64}$`（§4.1） |
| `environment_locked_sha256` | str | `^sha256:[0-9a-f]{64}$`（§4.1） |
| `environment_lock_class` | str | 實測值 |
| `environment_lock_completeness` | str | 實測值 |
| `environment_lock_threading_determinism` | str | 實測值 |
| `satisfies_full_lock_requirement` | bool | §4.2 |
| `verified_before_run` | bool | §6.1 |
| `lock_verified_at_utc` | str | `YYYY-MM-DDTHH:MM:SSZ` |
| `bound_at_utc` | str | `YYYY-MM-DDTHH:MM:SSZ` |
| `claim_boundary` | str | 本 contract 的 claim boundary（§9） |

[RESULT] 檔名凍結為 `run_lock_binding.json`，與被綁的 manifest **同目錄**。序列化凍結為 `json.dumps(payload, indent=1, sort_keys=True) + "\n"`，與本專案既有保留檔一致。

---

## 6. 執行期規則（凍結）

### 6.1 先量後跑，不是事後補記

[BLOCKER] Lock 必須在**產生任何被綁資料之前**量測並驗證，且 `verified_before_run` 只有在該順序成立時才可為 `true`。在 manifest 組裝時才量測，記錄的是「寫檔那一刻的環境」，不是「產生資料的環境」——兩者可以不同，而差別正是這份 lock 要偵測的東西。

[SOURCE] 既有的正確樣板是 `backend/rl/second_case_runner.py:86-105` 的 `verify_lock_now`：載入 pinned record → `check_environment_lock` → `capture_environment_lock` → `verify_environment_lock` → 要求 `environment_lock_match is True`，並在 run **之前**（:390、:433）呼叫。

### 6.2 證據等級決定是否 fail closed

| Run 類別 | 規則 |
|---|---|
| 受凍結 protocol 管轄的 run（manifest 帶 `seedvar_protocol`／`pilot_protocol`，或 `run_class` 為 `FORMAL_EVALUATION`） | **執行期 fail closed**：`satisfies_full_lock_requirement` 為 false 時拒絕開始 |
| 其他 run（smoke、preflight、本機開發） | **據實記錄**：照樣產生綁定記錄並寫入實測的 class／completeness，不阻擋執行 |

[INFERENCE] 這條分界是刻意的。對 smoke run 強制 `FULL_LOCK`（需要 `OMP_NUM_THREADS=1` 等）只會讓人繞過整個機制；而讓 evidence run 在未鎖環境下靜默通過，才是真正的危害。分界的另一半由 §7 的分析期 gate 承擔。

### 6.3 Clean-source 規則不變

[RESULT] 本規格**不改變**既有的 `source_git_pre` / `source_git_post` 檢查。綁定記錄與它們並存，回答的是不同的問題：git identity 回答「哪一份原始碼」，lock 回答「哪一個環境」。

---

## 7. 分析期 gate（凍結、fail-closed）

### 7.1 結果標籤

| 標籤 | 條件 |
|---|---|
| `RUN_LOCK_BOUND` | 綁定記錄存在且 schema 合法；`bound_manifest_sha256` 與該 manifest 逐位元相符；`satisfies_full_lock_requirement` 為 true |
| `RUN_LOCK_UNBOUND` | 該 run 目錄沒有綁定記錄 |
| `RUN_LOCK_INSUFFICIENT` | 綁定記錄存在且一致，但 `satisfies_full_lock_requirement` 為 false |
| `RUN_LOCK_MISMATCH` | 綁定記錄存在，但 `bound_manifest_sha256` 與該 manifest 不符，或 `bound_manifest_path` 指向別的檔案 |
| `RUN_LOCK_BINDING_METHOD_FAILURE` | 任何 contract 違反：未知 schema、key set 不符、digest 格式非法、路徑逃逸、`sidecar_reason` 與 `binding_mode` 不一致、lock record 讀不到或 `validate_lock_record` 失敗 |

### 7.2 語意（凍結）

[BLOCKER] `RUN_LOCK_UNBOUND` 與 `RUN_LOCK_INSUFFICIENT` 是**結果**，不是失敗，必須據實報告；但兩者**都不是 PASS**，不得被任何上游 contract 當成「已綁定」。

[BLOCKER] `RUN_LOCK_BINDING_METHOD_FAILURE` **永遠不得**被降級為其他四個標籤中的任何一個。

[BLOCKER] 門檻不得因結果而放寬。若某次執行得到 `RUN_LOCK_INSUFFICIENT`，正確的動作是修環境或據實記錄，**不是**改門檻重跑。任何門檻變更需要新的 contract 版本，並在其中揭露該變更是在已知結果的情況下設計的。

### 7.3 fail-closed 只加在新 schema 上

[RESULT] 強制要求 `RUN_LOCK_BOUND` 的，**只有**本規格新建立的 schema：`RUN_LOCK_BINDING_V1` 與 `PAPER_RUN_MANIFEST_V2`。

[INFERENCE] 理由：既有保留 contract（`SECONDCASE_EXPOSURE_RAW_*`、`SEEDVAR_*` 的 `CELL_FIELDS`／`RAW_FIELDS`、`RL_TRAINING_RUN_V2`）的 key set 是**精確比對**的，加一個新欄位等於改變 schema，而它們的保留證據 digest 已被釘住。在不升版的情況下加欄位，會讓保留證據無法通過自己的 contract。

### 7.4 `PAPER_RUN_MANIFEST` 的升版規則（凍結）

[RESULT] `paper_data_contract.PaperRunManifest.schema_version` 由 `Literal["PAPER_RUN_MANIFEST_V1"]` 擴為 `Literal["PAPER_RUN_MANIFEST_V1", "PAPER_RUN_MANIFEST_V2"]`，並新增一個 model validator：

- `V2` **必須**帶 `environment_lock` 區塊，其內容為 §5 記錄的子集（`environment_lock_class`、`environment_lock_completeness`、`environment_lock_threading_determinism`、`environment_locked_sha256`、`lock_record_sha256`、`satisfies_full_lock_requirement`、`verified_before_run`）；
- `V1` **必須不**帶該區塊（`extra="forbid"` 已保證）；
- `backend/build_v1_paper_bundle.py` 與 `backend/build_v1_analytical_bundle.py` 自本規格實作後**一律產生 `V2`**。

[RESULT] `ArtifactRecord.role` 的 `Literal` 增加一個值 `environment_lock`，使 lock record 本身可以作為 bundle 內的 artifact 保留（含 path／bytes／SHA-256 readback）。`REQUIRED_ARTIFACT_ROLES` 的 10 個必要 role **不變**——新 role 是可選的，否則舊 V1 bundle 會失效。

[BLOCKER] `V1` 保留為可讀，是為了不讓任何既有 bundle 失效。但 `V1` **永遠不可能**滿足本 gate 的 `RUN_LOCK_BOUND`：它沒有那個區塊。這正是預期行為，不是缺口。

---

## 8. 前向立場（凍結）

### 8.1 2026-09-08 的 seed-variance bundle 不重建

[SOURCE] `backend/build_training_seed_variance_bundle.py:204` 與 `:208` 把 `evaluation_environment_lock_verified` 與 `training_environment_lock_verified` **寫死為 `True`**，而非從 manifest 讀取。這兩個欄位被 `backend/training_seed_variance_contract.py:176-178` 的 `CELL_LOCK_FIELDS` 檢查。

[BLOCKER] 這兩個值是**無法從保留證據重新驗證的斷言**。保留的 15 份 `run_manifest.json` 沒有任何 lock 欄位（§3.1 第 1 項），所以沒有任何東西可以支持或反駁它們。本規格把這件事**記錄為已知缺口**，並且：

1. **不修改** `:204`／`:208`——改成從 manifest 讀取會使兩者變成 `False`，令 `CELL_LOCK_FIELDS` fail closed；
2. **不重建** 2026-09-08 的 bundle——重建會改變 `raw_replicates.json` 的 digest，而該 digest 已被 `seed_variance_evidence/2026-09-08/analysis/` 與 `backend/rl/r0_regime_probe_protocol.json` 的 `parent_summary_sha256` 釘住；
3. 那 15 次訓練**無法重新執行**（v5 warm start 的 provenance 不可重建，見 [V7_PRETRAINING_SEED_VARIANCE_INFEASIBILITY_RECEIPT](V7_PRETRAINING_SEED_VARIANCE_INFEASIBILITY_RECEIPT_2026-09-08.md)）。

[INFERENCE] 因此立場是**純前向**：新的綁定只約束本規格實作之後產生的 run。舊證據的 lock 斷言維持原狀，但在此具名為不可重驗，稿件引用時必須帶著這個限制。

### 8.2 三條已綁定 pipeline 不 retrofit

[RESULT] §3.1 第 5–7 項已在 run 之前驗過 lock，且把結果寫進各自的保留輸出。本規格**不**為它們的既有保留輸出補建綁定記錄——補建的記錄會是事後產生的，`verified_before_run` 無法誠實地宣稱為 `true`。

[RESULT] 這三條 pipeline 的**未來**執行應改用統一記錄。第 5、6 項所屬的 second-case 線已關閉（[SECOND_CASE_V2_BUDGET_PROBE_RECEIPT §7](SECOND_CASE_V2_BUDGET_PROBE_RECEIPT_2026-09-08.md)），第 7 項的 R0 probe 已執行完畢，故實務上不會有新執行；此條為規則完整性而列。

### 8.3 兩個 pinned driver digest 維持為真

[RESULT] 因為第 1、2 項採 `SIDECAR_ONLY`，`backend/rl/train_ppo.py` 與 `backend/rl/eval_policy.py` **不被修改**，所以：

| Pin | 位置 | 本規格實作後 |
|---|---|---|
| `training_driver_source_sha256` = `sha256:877da3b4…` | `backend/rl/training_seed_variance_protocol.json`（**已執行**） | **維持為真** |
| `evaluation_driver_source_sha256` = `sha256:0cf27434…` | 同上；另見 `backend/rl/v7_candidate_selection_protocol.json`（**已凍結、owner 已授權**） | **維持為真** |

[RESULT] 因此本規格**不需要任何 protocol 修訂（amendment）**，也不需要重釘 `v7_candidate_selection_contract.PROTOCOL_SHA256`。這是 §3.2 取捨的直接收益。

---

## 9. Claim boundary

[BLOCKER] 通過本 contract **只**建立一件事：某個 retained run 的 manifest 與某份 `ENVIRONMENT-LOCK-V1` record 之間存在一條可重算的連結，且該 record 是 `MEASURED` 且 `FULL_LOCK`。

本 contract **不**支持：任何數值結果的正確性；任何 task PASS；任何 controller superiority；`paper_data_ready`／`statistics_ready`／`method_level_power_ready` 的任何改變；任何 physical feasibility、safety、sim-to-real 或 actuator 陳述；以及「該 run 可在另一台機器上重現」——lock 偵測環境差異，不保證跨環境數值相同。

[BLOCKER] 本 contract 是 **infrastructure，不是 evidence**。它不產生任何可引用的量測。

---

## 10. 驗收（`LB-01` .. `LB-12`）

| ID | 準則 |
|---|---|
| `LB-01` | 綁定記錄的 key set 與 §5 精確相符；多、少或型別不符皆 `RUN_LOCK_BINDING_METHOD_FAILURE` |
| `LB-02` | `bound_manifest_sha256` 與被綁 manifest 逐位元相符；竄改 manifest 一個位元得 `RUN_LOCK_MISMATCH` |
| `LB-03` | `lock_record_sha256` 與 `environment_locked_sha256` 是**兩個不同的量**，並各有一個正控制測試證明兩者在同一份 record 上不相等 |
| `LB-04` | `RUN_LOCK_BINDING_V1` 的任何欄位名都不是 `environment_lock_sha256`（§4.1），由測試直接斷言 |
| `LB-05` | `MEASURED` + `PARTIAL_LOCK` 得 `RUN_LOCK_INSUFFICIENT`，不得為 `RUN_LOCK_BOUND`；只看 `lock_class` 會通過的輸入必須被擋下 |
| `LB-06` | 沒有綁定記錄的 run 目錄得 `RUN_LOCK_UNBOUND`，且該標籤不得被任何上游當成 PASS |
| `LB-07` | `binding_mode` 為 `SIDECAR_ONLY` 而 `sidecar_reason` 為 null，或為 `EMBEDDED_AND_SIDECAR` 而 `sidecar_reason` 非 null，皆 fail closed |
| `LB-08` | `bound_manifest_path` 或 `lock_record_path` 若為絕對路徑、含 `..`、或非 canonical POSIX，皆 fail closed |
| `LB-09` | 五個標籤各有一個正控制測試；`RUN_LOCK_BINDING_METHOD_FAILURE` 有一個測試證明它不會被降級 |
| `LB-10` | `PAPER_RUN_MANIFEST_V2` 缺 `environment_lock` 區塊 fail closed；`PAPER_RUN_MANIFEST_V1` 帶該區塊亦 fail closed；既有 V1 fixture 全部維持通過 |
| `LB-11` | 分析模組為 stdlib-only（無第三方 import），由一個解析 AST 的測試證明，使其可在 `python -I -S` 下重跑 |
| `LB-12` | 本規格實作後，`backend/rl/train_ppo.py`、`backend/rl/eval_policy.py`、`backend/simulator.py` 三個檔案的 SHA-256 **與實作前相同**，由 §11 的執行順序第 1 步所記錄的值比對 |

---

## 11. 執行順序（順序不可反）

1. **量測並記錄**三個不得被修改的檔案今日的 SHA-256（供 `LB-12` 比對），連同 §2 的三項事實一併寫入本規格與 protocol JSON。
2. **凍結**本文件與 `backend/run_manifest_lock_binding_protocol.json`，commit 並 **push**。此步之前不得修改任何 producer。
3. 實作 `backend/run_manifest_lock.py`（記錄產生 + fail-closed gate，stdlib-only）。
4. 實作 `backend/test_run_manifest_lock.py`，覆蓋 `LB-01` .. `LB-12`。
5. 修改 `backend/paper_data_contract.py`（§7.4）與兩個 bundle builder（§3.1 第 3、4 項）。
6. 為第 1、2 項提供 sidecar 綁定的執行入口（不修改 driver 本體）。
7. 跑 gate（§12），全綠後才寫 receipt。

[BLOCKER] 第 2 步的 push 是硬前置。本規格的可信度來自「範圍與門檻在寫任何實作之前就固定」，事後補 commit 不具同等效力。

---

## 12. 驗收 gate 的精確指令（本 repo 無 CI）

[BLOCKER] 本 repo **沒有 `.github/` 目錄，沒有任何 CI**。因此 gate 就是下列兩條指令，於 repo root 執行，兩條都必須全綠：

```bash
# (a) 直接相關的 contract 與所有可能被本次修改影響的既有 contract
python -m pytest backend/test_run_manifest_lock.py \
                 backend/test_paper_data_contract.py \
                 backend/test_v1_analytical_bundle.py \
                 backend/test_paired_statistics_contract.py \
                 backend/test_experiment_matrix_contract.py \
                 backend/test_v7_candidate_selection_contract.py \
                 backend/test_training_seed_variance_contract.py \
                 backend/test_p0_contract.py -q

# (b) 全套 backend suite
python -m pytest backend -q
```

[RESULT] (a) 之所以逐一列出，是因為它們各自釘住了本次修改可能碰到的東西：`test_v7_candidate_selection_contract.py` 釘 `eval_policy.py` 的 digest（§2.2），`test_training_seed_variance_contract.py` 釘 seedvar protocol JSON（§2.3），`test_p0_contract.py` 釘 simulator 的 content hash（§3.4），其餘三者建構 `PAPER_RUN_MANIFEST_V1` payload（§7.4）。

---

## 13. 與其他文件的關係

| 文件 | 關係 |
|---|---|
| [ENVIRONMENT_LOCK_SPEC](ENVIRONMENT_LOCK_SPEC.md) | 本規格的上游。lock record 的 schema、digest 與驗證規則全部沿用，**不修改**。 |
| [VV_PLAN](VV_PLAN.md) | V0-R02 要求 run identity 綁定 code、config、MJCF、checkpoint 與 environment。本規格處理第五項。 |
| [ROADMAP §9](ROADMAP.md) | 第 1 項的前半。後半（actual matrix execution、immutable evidence storage）不在本規格範圍。 |
| [PAPER_DATA_READINESS](PAPER_DATA_READINESS.md) | `PAPER_RUN_MANIFEST` 升版後需同步其 schema 說明。 |
| [PUB_B0_AUTHORIZATION_RECEIPT](PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10.md) | 本規格刻意不動 `v7_candidate_selection_protocol.json`，以免該授權失去指涉對象（§2.2、§8.3）。 |
| [MOTION_SCOPE_DECISION §2](MOTION_SCOPE_DECISION_2026-09-11.md) | 凍結的順序表把本項排在新增動作任務之前。 |

---

## 14. 凍結身分

本規格於實作開始前 commit。其 SHA-256 由 `backend/run_manifest_lock_binding_protocol.json` 的 `specification_sha256` 釘住；該 protocol 的 SHA-256 再由 `backend/run_manifest_lock.py` 的 `PROTOCOL_SHA256` 釘住，並由測試比對。任何一層不符即 `RUN_LOCK_BINDING_METHOD_FAILURE`。
