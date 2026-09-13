# `RUN-MANIFEST-LOCK-BINDING-V1` 實作 receipt

日期：2026-09-13 ｜ Contract：`RUN-MANIFEST-LOCK-BINDING-V1` ｜ 規格：[RUN_MANIFEST_LOCK_BINDING_SPEC](RUN_MANIFEST_LOCK_BINDING_SPEC.md)

狀態：`IMPLEMENTED / LB-01..LB-12 PASS / BLOCKER_NARROWED_NOT_CLEARED`

證據等級：`INFRASTRUCTURE / NOT_EVIDENCE`

---

## 1. 做了什麼

[RESULT] 建立 `RUN_LOCK_BINDING_V1`：一個以 SHA-256 釘住其 run manifest 的 sidecar 記錄，外加一個 fail-closed 的分析期 gate。在 manifest schema 是本專案可自行升版、且沒有任何 pinned digest 或綠色測試禁止的地方，同一份資訊也內嵌進 manifest（`PAPER_RUN_MANIFEST_V2`）。

| 檔案 | SHA-256 |
|---|---|
| `docs/RUN_MANIFEST_LOCK_BINDING_SPEC.md`（凍結） | `sha256:1b3a7b26cd1e86807a3de66c9177bc2159c2f58e6d87701f552360152993ffdf` |
| `backend/run_manifest_lock_binding_protocol.json`（凍結） | `sha256:2e3bde9ad8a691a3242f6afac6d6189f5084fc0d42d632581fb0e8fbd51364f1` |
| `backend/run_manifest_lock.py` | `sha256:a38a15f867bf83caf471f30be72cb243d7227b7f2bdefeb8d29fc872045d0a55` |
| `backend/rl/bind_run_lock.py` | `sha256:816b36782e77c8e74327d149398fd4c17a0591ae8be688da71f4e5b28966822d` |
| `backend/test_run_manifest_lock.py`（62 tests） | `sha256:c2e81eddb0e904200c1bf185e3270fbdd68402f20a39949f4f10c67cd7a80bd4` |

[RESULT] 凍結先於實作：規格與 protocol 於 commit `00f8e62` 推送，該 commit **不含任何程式碼改動**。本 receipt 所述的實作全部發生在其後。

## 2. 逐 producer 的結果

| Producer | 模式 | 結果 |
|---|---|---|
| `backend/build_v1_paper_bundle.py` | `EMBEDDED_AND_SIDECAR` | 產生 `PAPER_RUN_MANIFEST_V2`，11 個 artifact role（新增 `environment_lock`），`RUN_LOCK_BOUND` |
| `backend/build_v1_analytical_bundle.py` | `EMBEDDED_AND_SIDECAR` | 同上；builder 自身在回傳前要求 `RUN_LOCK_BOUND`，否則 raise |
| `backend/rl/train_ppo.py` | `SIDECAR_ONLY` | 由 `rl/bind_run_lock.py` 包覆執行；driver **一個位元未改** |
| `backend/rl/eval_policy.py` | `SIDECAR_ONLY` | 同上 |
| `backend/simulator.py` | 明示排除 | 見規格 §3.4；**一個位元未改** |

[RESULT] `rl/bind_run_lock.py` 的 `binding_mode` 與 `sidecar_reason` **不是自由文字**：它們由凍結的 protocol JSON 依 producer 路徑查出。包覆器因此無法宣稱一個比凍結時更弱的理由。

## 3. 量到的事：兩個 digest 確實是兩個量

[RESULT] 在真實保留的 lock record 上跑正控制，兩個 digest 在同一份記錄上不相等：

| Lock record | `lock_record_sha256`（檔案位元組） | `environment_locked_sha256`（`locked` 子樹） |
|---|---|---|
| `lock-2026-09-08-seedvar-execution.json` | `sha256:3a6fb310750dc84f46d65df72d9ea43663b24c97778f81312efdcea1dcfff604` | `sha256:93d23a2703adc86a1394eacf5dece8d7229fdf742857f1a271656aa1cfeac72d` |
| `lock-2026-09-08-second-case-execution.json` | `sha256:911b436231c8e0b1d7a3d07bca6894ce4c42c517c4a5cbbbdd0f9dff694ff631` | `sha256:93d23a2703adc86a1394eacf5dece8d7229fdf742857f1a271656aa1cfeac72d` |

[RESULT] 兩份記錄的 `locked_sha256` **相同**——兩次執行確實在同一個 locked 環境；但兩份保留 bundle 在同名欄位 `environment_lock_sha256` 下存了 `911b4362…` 與 `93d23a27…` 兩個不同的值，差異**只來自兩條 pipeline 對該欄位的定義不同**。

[BLOCKER] 一個讀者比較這兩個值會得到「證據來自不同環境」這個錯誤結論。新記錄以兩個名字保留兩個量，並在 `validate_binding_record` 與 `PAPER_RUN_MANIFEST_V2` 兩處都拒絕 `environment_lock_sha256` 這個名稱。舊的保留 bundle **未被改寫**（其 digest 已被釘住），此缺陷在此具名記錄，而非就地修補。

## 4. 自我約束：三個承諾不碰的檔案，逐位元未變

[RESULT] `LB-12` 由測試比對 protocol 的 `immutable_sources`，全部相符：

| 檔案 | 凍結時與完成時的 SHA-256 | 不可修改的理由 |
|---|---|---|
| `backend/rl/train_ppo.py` | `sha256:877da3b41e7c44ce73758877f40e257e45c6203b045eb9e2d3cd5aa6f606f6ce` | 已執行的 `SEEDVAR-...-V1` 釘住它，且**執行期無人重算** |
| `backend/rl/eval_policy.py` | `sha256:0cf274341a10a56fbf544d86eab4bfbfd6f630056689280af51aff111b0058d4` | `test_v7_candidate_selection_contract.py:237` **主動重算**並比對 owner 已授權 protocol 的 pin |
| `backend/simulator.py` | `sha256:c27e00a0e59b13e9e8b9c4c7fd17d885008287cdde8d8bdab68250cb17ec4cc5` | deterministic content hash，由 `test_p0_contract.py` 獨立重算 |

[RESULT] 因此**沒有任何 pinned digest 變成假的、沒有任何既有綠色測試變紅、不需要任何 protocol amendment**，`v7_candidate_selection_contract.PROTOCOL_SHA256` 也不需重釘，2026-09-10 的 formal authorization 仍指向同一份 protocol。

## 5. 驗收 `LB-01` .. `LB-12`

| ID | 結果 |
|---|---|
| `LB-01` | PASS —— key set 雙向精確；12 個 malformed 欄位各自 fail closed |
| `LB-02` | PASS —— manifest 翻動一個位元得 `RUN_LOCK_MISMATCH`；綁定指向別的 manifest 亦然 |
| `LB-03` | PASS —— 兩個 digest 在兩份真實保留記錄上各自不相等，且 `locked_sha256` 相同而檔案位元組不同 |
| `LB-04` | PASS —— `environment_lock_sha256` 不在 `RECORD_FIELDS`／`EMBEDDED_LOCK_FIELDS`；帶了就 raise |
| `LB-05` | PASS —— `MEASURED` + `PARTIAL_LOCK` 得 `RUN_LOCK_INSUFFICIENT`；`satisfies_full_lock_requirement` 為**推得**而非宣告；受 protocol 管轄的 run 在未達 FULL_LOCK 時拒絕啟動，smoke run 則據實記錄 |
| `LB-06` | PASS —— 無綁定得 `RUN_LOCK_UNBOUND`；`require_bound_run` 只接受 `RUN_LOCK_BOUND` |
| `LB-07` | PASS —— mode 與 reason 兩個方向都 fail closed；凍結 protocol 的四個 producer 全部一致 |
| `LB-08` | PASS —— 絕對路徑、`..`、反斜線、非 canonical、空字串與 run root 外的 lock record 全部 fail closed |
| `LB-09` | PASS —— 五個標籤各有正控制；五種 contract 違反全部落到 `RUN_LOCK_BINDING_METHOD_FAILURE`，未降級 |
| `LB-10` | PASS —— `V2` 缺區塊 fail closed；`V1` 帶區塊 fail closed；既有 V1 fixture 全部維持通過；V2 區塊同樣拒絕模糊欄位名 |
| `LB-11` | PASS —— 以 AST 解析確認 module scope 僅 import stdlib；`python -I -S` 子行程實跑 gate 得 `RUN_LOCK_BOUND` |
| `LB-12` | PASS —— 三個檔案逐位元未變（§4） |

## 6. 驗收 gate 的實測結果，以及規格 §12 的一個缺陷

[RESULT] 規格 §12 指令 (a)（逐一列出、釘住本次可能碰到之物的 contract）：**362 passed，全綠**。

[RESULT] 規格 §12 指令 (b)（`python -m pytest backend -q`）：**1 failed / 816 passed**（405.58 s）。

[BLOCKER] **規格 §12 寫「兩條都必須全綠」，這句話是錯的，而且在我凍結它之前就已經是錯的。** 本 repo 的 suite 並非全綠：`test_v1_analytical_suite.py::test_stdlib_replay_passes_exact_synthetic_fixture`（`PRIMARY_CASE_RECEIPT_IDENTITY`）自 2026-09-08 起就被**記錄為量測結果而非放寬**，見 [PROJECT_STATUS §4.3、§9](PROJECT_STATUS.md)。我在凍結 §12 時沒有先核對本專案自己記錄的 suite 狀態。

[RESULT] 本次工作的實際影響是可量的，且為零新增失敗：

| | 失敗 | 通過 |
|---|---:|---:|
| 凍結父 commit `501a7ee`（專案自己記錄於 `d4d5c09`） | 1 | 754 |
| 本次完成後 | 1 | 816 |

[RESULT] 唯一失敗是同一項，已就地重現並定位：fixture 由 `v1_analytical_suite.py:640` 的 `float(np.mean([...]))` 產生，replay 由 `v1_analytical_replay.py:952` 的 `sum(...) / len(...)` 重算，`mean_vertical_grf_n` 為 `196.2` 對 `196.19999999999854`，差 `1.46e-12`，略高於 `1.0e-12` 的 exactness 門檻。另實測：把四個執行緒環境變數 pin 回 `1`（seedvar 執行時的設定）**不會**改變結果，所以它不是 thread-count drift，而是 §4.3 已記錄的 reduction-order 差異本身。

[BLOCKER] 依規格 §7.2「門檻不得因結果而放寬」，本 receipt **不修改凍結的 §12**，也不放寬那個 1e-12 門檻。正確的 gate 措辭應為「相對於專案記錄的基線不得新增任何失敗」，這留給下一個 contract 版本，並在此具名為本次凍結的缺陷。

## 7. 沒有清除的東西（blocker 只是變窄）

[BLOCKER] 下列三項仍然成立，不得被讀成「已全部覆蓋」：

1. **Sidecar 可以被遺漏。** 直接呼叫 `rl/train_ppo.py` 或 `rl/eval_policy.py`（不經 `rl/bind_run_lock.py`）仍會產生一個沒有綁定的 run。規格 §3.3 把這一點定為已知代價，gate 把它報成 `RUN_LOCK_UNBOUND` 而非靜默通過。
2. **`backend/simulator.py` 明示排除。** 這是「每一條 pipeline」在第一天就有的一個例外（規格 §3.4）。
3. **2026-09-08 的 seed-variance bundle 未重建。** `build_training_seed_variance_bundle.py:204`／`:208` 的兩個寫死 `True` 仍是**無法重新驗證的斷言**：保留的 15 份 `run_manifest.json` 沒有任何 lock 欄位，bundle digest 已被釘住，那 15 次訓練也無法重跑。稿件引用該 bundle 時必須帶著這項限制。

[RESULT] 另有三條 pipeline（`second_case_runner.py`、`second_case_budget_probe.py`、`run_r0_regime_probe.py`）本來就在 run 之前驗過 lock 並寫進保留輸出，格式不同但實質已綁定；規格 §8.2 明定**不**為其既有保留輸出補建綁定記錄，因為事後產生的記錄無法誠實宣稱 `verified_before_run`。

## 8. 沒有改變的事

`paper_data_ready`、`statistics_ready`、`method_level_power_ready`、`sample_size_decision_input_ready` 皆為 false 不變。沒有訓練、沒有評估、沒有動任何 seed、沒有存取 `19000–19029` 或 `20000–20029`。沒有修改任何既有 protocol、門檻、arm 定義或 claim。`SELECT-V7-CANDIDATE-FORMAL-V1` 的三個 execution precondition 與其 `PROTOCOL_SHA256` 逐位元不變；`PUB-A`／`PUB-B` 所有 gate 狀態不變。
