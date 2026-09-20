# 把已結案的研究線封存進 `backend/archive/`

ID：任務 #97 ｜ 日期：2026-09-19
｜ 性質：**封存記錄與量測**；不是 protocol、不是 receipt、不是新的契約

上游：[PROJECT_ASSESSMENT §4.2](PROJECT_ASSESSMENT_2026-09-16.md)
｜ 前一步：[TOOLKIT_MOVE_2026-09-19](TOOLKIT_MOVE_2026-09-19.md)（§4.1 產品 B）

---

## 0. 一句話

**封存了，但一個檢查都沒有少——而且 §4.2 的清單裡有一項搬不動，原因是它自己的 pin。**

擁有者 2026-09-19 選定的範圍：**只搬程式、文件不動**，而且**那 434 個測試要繼續跑**。
後者不是保守，是必要的：**三個沒有被封存的檔案，它們的位元組是由要被封存的測試釘住的**。

---

## 1. 為什麼測試必須跟著跑

| 被釘住的檔案（**留下**） | 釘它的測試（**已封存**） |
|---|---|
| `backend/config_schema.py`（教學閉包） | `test_v7_pilot_contract.py` |
| `backend/motion_tasks.py`（教學閉包） | `test_v7_pilot_contract.py` |
| `backend/rl/eval_policy.py`（`immutable_sources` ＋ `producers_in_scope`） | `test_tracked_lineage_v2_contract.py` |

§4.2 預期「測試會從 942 降到約 520」。照做的話，**上面三個仍在線上的檔案就沒有東西在檢查它們的不可變性了**，
而 `eval_policy.py` 正是 binding protocol 會在執行期解析的四個 producer 之一。

**實測：搬移前後測試總數都是 1,062。** 封存的是位置，不是檢查。

---

## 2. 搬不動的那一項：`v7_exposure_audit_contract.py`

`:2009`：

```python
path = Path(__file__).with_name(PurePosixPath(contract["motion_task_source"]).name)
```

`motion_task_source` 是 `backend/motion_tasks.py`——**一個留在原地的教學模組**。
把 audit contract 搬進 `backend/archive/`，這個查找就會指向
`backend/archive/motion_tasks.py`，直接丟 `frozen motion task source is missing`。

修它要改一行。但那一行所在的檔案，**位元組被 `training_seed_variance_contract.py:77` 釘住**，
而那個 pin 上方的註解寫得很清楚它為什麼存在：

> a drifted audit implementation would otherwise silently reclassify exposure under an unchanged protocol digest

**所以搬它＝重算一個「專門用來偵測它被改動」的 digest。** 那是動凍結值，是擁有者的決定，不是我的。

**處置：`v7_exposure_audit_contract.py`、`v7_exposure_audit_replay.py`、
`v7_exposure_audit_protocol.json` 與 `test_v7_exposure_audit_contract.py` 全部留在 `backend/`。**
連帶地，已封存的 `training_seed_variance_contract.py` 的 pin 路徑改指回 `backend/`（該檔未被釘，可改）。

`v7_pilot_contract.py` 同樣被釘住，但它只解析一個**跟著搬**的兄弟 replay，**不需要改任何一行**，
所以它連同 pin 一起進了 archive。

---

## 3. 搬了什麼

**22 個檔案進 `backend/archive/`**：11 個 contract／runner／builder 模組、
1 個 replay、3 個從 `backend/rl/` 搬出的 runner、1 個 retention 腳本，以及 6 個對應的測試檔。

| 線 | 模組 |
|---|---|
| v7 pilot／selection | `v7_pilot_contract`、`v7_pilot_replay`、`v7_candidate_selection_contract` |
| second case | `second_case_exposure_contract`、`second_case_runner`、`second_case_budget_probe` |
| seed variance | `training_seed_variance_contract`、`training_seed_variance_replay`、兩個 bundle builder |
| tracked lineage | `tracked_lineage_contract`、`tracked_lineage_v2_contract`、`retain_tracked_lineage_checkpoints`、`run_tracked_lineage_v2_contract` |
| R0 | `run_r0_regime_probe` |

**證據目錄一個都沒有動**，digest 一個都沒有變。**本次（2026-09-19）文件沒有搬**（擁有者當時選的範圍）——文件已於**隔日 2026-09-20** 由任務 #98 處理，見 [DOC_ARCHIVE](DOC_ARCHIVE_2026-09-20.md)。

---

## 4. 「只需要搬」在這裡更不成立——四類必要的改動

與 §4.1 的工具組（9 個檔案裡 8 個逐位元未動）相反，這次**只有 5 個檔案逐位元未動**，
22 個要改。原因全都是 `__file__` 相對路徑：

**一、祖先運算位移。** 從 `backend/X` 搬到 `backend/archive/X` 深了一層，
所以 `parent.parent`（repo root）要變 `parents[2]`、`parent`（backend）要變 `parents[1]`。
從 `backend/rl/X` 搬來的深度不變，但 `parent` 不再是 `rl/`——
`second_case_runner` 與 `second_case_budget_probe` 的 `RL_DIR` 因此改成 `BACKEND_DIR / "rl"`。

**二、指向留下來的東西的路徑。** 封存模組仍要讀 `backend/rl/` 底下的凍結 protocol JSON、
`backend/environment_locks/`、`backend/seed_variance_evidence/`——全部改成 `parents[1] / ...`。

**三、當成子行程跑的 CLI 會找不到 `backend/`。** 以 `python3 backend/archive/X.py` 執行時
`sys.path[0]` 是 archive，不是 backend，於是 `import toolkit_path` 直接 `ModuleNotFoundError`。
5 個 CLI 補上三行 bootstrap；`second_case_exposure_contract` 在 `-I -S` 下跑，
它原本只插入自己的目錄，改成同時插入 `backend/`。

**四之前還有一個只有跑過才看得到的：封存把 3 個通過的檢查變成了沉默的 skip。**
`test_second_case_runner.py` 有三個測試寫著
`path = HERE / "rl" / "second_case_v2_budget_probe_v2.json"`，`if not path.exists(): pytest.skip("probe V2 not written yet")`。
搬移後 `HERE` 是 archive，那兩份 probe JSON 在 `backend/rl/`，於是三個測試**安靜地跳過**——
而跳過訊息說「尚未寫出」，**那是假的，檔案一直都在**。
總數不會變（skip 也算一個收集到的測試），所以**只看總數看不出來**；
是比對 `1061 passed` 與 `1058 passed, 3 skipped` 才發現的。
**「檔案不存在就 skip」在重構把檔案搬走時就是一個 fail-open。** 已修為 `HERE.parent / "rl"`，三個測試恢復通過，全檔 17 passed、0 skipped。

**四、`from rl import X` 不再成立。** 兩個模組離開了 `rl/` 套件，
`test_tracked_lineage_v2_contract.py` 的 7 處 import 改成平坦名稱。

登錄檔的 `module_search_path` 從 `["", "toolkit"]` 擴為 **`["", "toolkit", "archive"]`**——
這正是 §4.1 為了同一個理由加的機制，第二次用上。

---

## 5. 量測

| | 封存前 | 封存後 |
|---|---|---|
| 測試總數 | 1,062 | **1,062** |
| 通過／跳過 | 1,061 passed／0 skipped | **1,061 passed／0 skipped**（中途一度是 1,058／3，見 §4） |
| 失敗 | 1（`PRIMARY_CASE_RECEIPT_IDENTITY`） | **1（同一個，未放寬）** |
| teaching 閉包 | 15 模組／4,943 行 | **15 模組／4,943 行** |
| toolkit 閉包 | 7 模組／5,508 行 | **7 模組／5,508 行** |
| 三個文件契約 | 全過 | **全過** |

---

## 6. 明確不在範圍內

| 沒做 | 為什麼 |
|---|---|
| **v7 audit 那一組沒有封存** | 搬它要改一個被 pin 釘住的檔案，見 §2——擁有者的決定 |
| **本次文件沒有搬** | 擁有者當時選的範圍是只搬程式。**已於 2026-09-20 補做**（任務 #98）：17 份進 `docs/archive/`，3 份因內容 digest 被凍結證據釘住而搬不動，見 [DOC_ARCHIVE](DOC_ARCHIVE_2026-09-20.md) |
| **產品 A（教學模擬器）沒有搬** | 不在 §4.2 範圍 |
| **測試沒有變少** | 見 §1：變少會停掉三個仍在線上檔案的 pin |
| **沒有搬成獨立 repo** | §4.2 提的另一個選項；本次選 repo 內目錄，維持單一測試指令 |
