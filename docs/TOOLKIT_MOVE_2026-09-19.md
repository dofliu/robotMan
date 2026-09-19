# 把實驗工具組搬進 `backend/toolkit/`

ID：任務 #96 ｜ 日期：2026-09-19
｜ 性質：**搬移記錄與量測**；不是 protocol、不是 receipt、不是新的契約

上游：[PROJECT_ASSESSMENT §4.1](PROJECT_ASSESSMENT_2026-09-16.md)（產品 B）
｜ 邊界契約：[TOOLKIT_PORTABILITY](TOOLKIT_PORTABILITY.md)
｜ 對外說明書：[TOOLKIT_USAGE](TOOLKIT_USAGE.md)
｜ 決定記錄：[TOOLKIT_PORTABILITY_DECISIONS_2026-09-19](TOOLKIT_PORTABILITY_DECISIONS_2026-09-19.md)

---

## 0. 一句話

**§4.1 說「拆開不需要重構，只需要搬」。搬完之後可以說：那句話**幾乎**成立——
9 個檔案裡 8 個逐位元未動，但「只需要搬」漏掉了三件只有真的搬下去才會看到的事。**

三件事寫在 §3、§4、§5。範圍是**只有產品 B**：產品 A（教學模擬器）與產品 C（研究線封存）沒有動。

---

## 1. 搬了什麼

| 從 | 到 | 內容改動 |
|---|---|---|
| `backend/environment_lock.py` | `backend/toolkit/` | **0** |
| `backend/experiment_matrix_contract.py` | `backend/toolkit/` | **0** |
| `backend/exposure_identification.py` | `backend/toolkit/` | **0** |
| `backend/paired_statistics_contract.py` | `backend/toolkit/` | **0** |
| `backend/paper_data_contract.py` | `backend/toolkit/` | **0** |
| `backend/rl/bind_run_lock.py` | `backend/toolkit/` | **0** |
| `backend/run_manifest_lock_binding_protocol.json` | `backend/toolkit/` | **0**（digest 因此未動） |
| `backend/paired_statistics_replay.py` | `backend/toolkit/` | **0**（為什麼它也得搬，見 §4） |
| `backend/run_manifest_lock.py` | `backend/toolkit/` | **＋5 −1**：只有 docstring 裡那條指向 protocol 的路徑 |

**新增兩個檔案**（都不在工具組閉包內）：

- `backend/toolkit_path.py` — 唯一知道工具組目錄在哪的地方。
- `backend/conftest.py` — pytest 在收集前載入它，因此**整套 1,062 個測試沒有一個檔案需要為了這次搬移而改 import**。

`bind_run_lock` 的模組名從 `rl.bind_run_lock` 變成 `bind_run_lock`；**同一個檔案，同樣的位元組**。

---

## 2. 為什麼是 `sys.path` shim 而不是 package-relative import

這是 2026-09-19 擁有者決定的直接後果。工具組的 7 個模組**彼此用平坦名稱 import**，
而那不是待清理的髒東西，是 [TOOLKIT_USAGE §2](TOOLKIT_USAGE.md) 發布的安裝方式：
把三個檔案複製進同一個目錄就能用。改成 package-relative 已實測會**遲發**地弄壞它
（import 成功，第一次真的呼叫才丟 `ImportError`），詳見
[決定記錄 §2.3](TOOLKIT_PORTABILITY_DECISIONS_2026-09-19.md)。

平坦 import 只有在**放著那些檔案的目錄本身在 `sys.path` 上**時才解得開，
所以總得有人把它放上去。`backend/toolkit_path.py` 就是那個人，而且**只有它知道路徑**：

```python
import toolkit_path  # noqa: E402,F401
import environment_lock as el
```

13 個 repo 內的使用者各加**一行**這個 import；路徑本身只寫在一個地方。
測試那邊由 `backend/conftest.py` 代勞，它自己也是去 import `toolkit_path`，不重寫路徑。

---

## 3. 第一件沒預料到的事：邊界契約會**直接瞎掉**

`module_boundary_contract.module_path()` 原本把模組名對到 `package_root/<name>.py`。
檔案一進子目錄，工具組模組之間那些**平坦**的兄弟 import 就對不到任何檔案——
於是它們**不再被當成本地 import**，閉包會塌成 7 個沒有任何邊的進入點。

那不會變紅。**它會照樣印出 `MODULE_BOUNDARIES_CLEAN`**，而契約已經看不見
它唯一存在的理由：一個工具組模組伸進另一個產品。這與 2026-09-19 才關掉的
`node.level` 那個 fail-open **是同一類**，而且這次是搬移本身製造出來的。

**修法是讓登錄檔明講搜尋路徑**，而不是再多一個隱含假設：

```json
"package_root": "backend",
"module_search_path": ["", "toolkit"]
```

`module_path()` 依序試這些目錄——**這模型的就是真正的 `sys.path`**，
而不是「所有模組都直接躺在 `package_root` 下」這個已經不成立的假設。

**量測：兩個邊界的閉包在搬移前後完全相同**——teaching 15 個模組／4,943 行、
toolkit 7 個模組／5,508 行（5,505 ＋ 上面那 3 行 docstring）。

---

## 4. 第二件：工具組有**第八個檔案**，而 import 閉包看不到它

`paired_statistics_contract.py:62`：

```python
REPLAY_SCRIPT = Path(__file__).with_name("paired_statistics_replay.py")
```

那是一個**以子行程啟動的兄弟腳本**，不是 import。契約用 AST 讀 import，
所以這個相依**結構上**不可能出現在閉包裡——登錄檔說工具組是 7 個模組，
執行期其實需要 8 個檔案。

搬移前沒有人會發現，因為兩個檔案本來就在同一個目錄。搬移後
18 個 `paired_statistics` 測試立刻以 `independent replay script is missing` 失敗。

**處置**：`paired_statistics_replay.py` 一起搬進 `backend/toolkit/`（逐位元未動），
**但不登錄**——它不是閉包成員，硬登錄會變成 `STALE_REGISTRY_ENTRY`。
這個「有一個檔案在契約視野外」的事實記在這裡，**沒有做自動檢查**。
全工具組掃過一遍，這是**唯一**一處兄弟檔案相依
（`environment_lock.py:1211` 用 `__file__` 重跑它自己，`run_manifest_lock.py:62` 指向的
protocol JSON 已經跟著搬）。

---

## 5. 第三件：五份**凍結且 digest 釘死**的檔案從此指著不存在的路徑

這是這次搬移**付出而無法收回**的代價，明寫在這裡而不是藏起來。

| 凍結檔案 | 它寫著的路徑 | 為什麼不能改 |
|---|---|---|
| `backend/toolkit/run_manifest_lock_binding_protocol.json` | `backend/environment_lock.py`、`backend/run_manifest_lock.py`、`backend/paper_data_contract.py` | 由 `run_manifest_lock.py:58` 的 `PROTOCOL_SHA256` 釘住，`:360` 執行期強制 |
| [`docs/RUN_MANIFEST_LOCK_BINDING_SPEC.md`](RUN_MANIFEST_LOCK_BINDING_SPEC.md) | `backend/run_manifest_lock.py`（×2）、`backend/paper_data_contract.py` | 由 `:59` 的 `SPECIFICATION_SHA256` 釘住 |
| `backend/rl/tracked_lineage_training_protocol.json` | `backend/rl/bind_run_lock.py` | `tracked_lineage_contract.py:40` 釘住 |
| `backend/rl/training_seed_variance_protocol.json` | `backend/environment_lock.py` | `training_seed_variance_contract.py:58` 釘住 |
| `backend/seed_variance_evidence/2026-09-08/bundle/training_seed_variance_protocol.json` | `backend/environment_lock.py` | **保留證據**，規則是永不更動 |

**先確認過的事：沒有任何一條會在執行期被解析成檔案路徑。** 它們全都落在
`enforcement_scope`、`execution_order`、`forward_only_posture` 這些**敘述性**欄位裡。
唯一真的被解析的是 `producers_in_scope[*].producer`，而那四個都是產品 C 的檔案，**這次沒有搬**。

所以**沒有任何程式因此壞掉**，壞掉的是可讀性：一份凍結文件寫著一條走不到的路。
更正只能放在這裡與其他非凍結文件裡，**凍結的位元組一個都沒有動**——這正是先立後撤
在這個專案裡的做法。

---

## 6. 量測

| | 搬移前 | 搬移後 |
|---|---|---|
| teaching 閉包 | 15 模組／4,943 行 | **15 模組／4,943 行** |
| toolkit 閉包 | 7 模組／5,505 行 | **7 模組／5,508 行**（＋3 行 docstring） |
| 三個文件契約 | 全過 | **全過** |
| 工具組的 9 個檔案 | — | **8 個逐位元未動** |
| `PROTOCOL_SHA256`／`SPECIFICATION_SHA256` | 相符 | **相符**（protocol 跟著搬，位元組未動） |

外部使用者的安裝方式**沒有變**，只有來源路徑換了目錄：
`backend/toolkit/` 裡的那三個檔案複製進同一個目錄即可，平坦 import 照舊。
`test_the_toolkit_modules_stay_flat_vendorable` 仍然守著這件事。

---

## 7. 明確不在範圍內

| 沒做 | 為什麼 |
|---|---|
| **產品 A（教學模擬器）沒有搬** | 本次範圍由擁有者選定為只做產品 B |
| **產品 C（研究線封存）沒有搬** | 同上；[§4.2](PROJECT_ASSESSMENT_2026-09-16.md) 的封存清單仍未執行 |
| **沒有做成可安裝的套件** | 沒有 `pyproject.toml`、沒有 `__init__.py`；平坦 vendoring 是刻意保留的安裝方式 |
| **§4 那個第八個檔案沒有自動檢查** | AST 閉包結構上看不到子行程腳本；需要另一個裝置，本次沒有做 |
| **五份凍結檔案的路徑沒有更正** | 改它們等於破壞自己的 pin，見 §5 |
