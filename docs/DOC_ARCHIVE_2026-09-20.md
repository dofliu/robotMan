# 把已結案研究線的文件搬進 `docs/archive/`

ID：任務 #98 ｜ 日期：2026-09-20
｜ 性質：**搬移記錄與量測**；不是 protocol、不是 receipt、不是新的契約

上游：[PROJECT_ASSESSMENT §4.2](PROJECT_ASSESSMENT_2026-09-16.md)
｜ 前一步：[RESEARCH_LINE_ARCHIVE_2026-09-19](RESEARCH_LINE_ARCHIVE_2026-09-19.md)（同一節的程式部分）
｜ 索引：[`docs/archive/`](archive/README.md)

---

## 0. 一句話

**17 份搬了，3 份搬不動，7 份必須在原路徑留轉址——而且搬不動的理由是執行過程才量到的，不是事前推理出來的。**

---

## 1. 一個被推翻的前提（先講，因為後面每個決定都建立在它上面）

規劃時我掃了 `grep -rn "specification_path" backend/**/*.py`，結果是空的，因此判斷
**「沒有任何程式在執行期解析文件路徑」**，並據此把「7 份被凍結證據指名的文件」描述成
「搬了只會讓 provenance 指標失效，不會壞掉任何東西」。

**那是錯的。** 契約用的是**模組常數** `SPECIFICATION_PATH`，小寫的 grep 掃不到：

```python
# backend/archive/tracked_lineage_v2_contract.py:73
spec = sha256_file(SPECIFICATION_PATH)
if payload.get("specification_sha256") != spec:
    _fail("TL2_SPECIFICATION_DIGEST_MISMATCH", spec)
```

契約**會讀那份文件、算 sha256、和凍結 protocol 裡的值比對**。
擋下我的是 `TL2_SPECIFICATION_DIGEST_MISMATCH`——在全套測試裡，不是在我的推理裡。

---

## 2. 真正的阻礙：改連結就是改位元組

搬一份文件必須改它的內部相對連結（`](../backend/…)` 要變 `](../../backend/…)`）。
**改連結就改位元組，改位元組就換 digest。** 對一份 digest 被釘住的文件，這兩件事不可兼得。

實測：我改過的文件裡有 **4 份**內容 digest 被釘住——

| 文件 | 釘它的（含不可改的凍結證據） |
|---|---|
| `TRACKED_LINEAGE_TRAINING_SPEC.md` | `rl/tracked_lineage_training_protocol.json` |
| `TRACKED_LINEAGE_TRAINING_V2_SPEC.md` | `rl/tracked_lineage_training_v2_protocol.json` |
| `R0_REGIME_PROBE_SPEC.md` | `rl/r0_regime_probe_protocol.json`、**`r0_probe_evidence/2026-09-11/probe_result.json`** |
| `RUN_MANIFEST_LOCK_BINDING_SPEC.md`（**本來就沒要搬**） | `toolkit/run_manifest_lock_binding_protocol.json`、`toolkit/run_manifest_lock.py` |

前三份**從 `docs/archive/` 退回 `docs/`，位元組還原成搬移前的原樣**（已逐一比對 sha256 相符）。
第四份是連帶傷害：它沒有要搬，但它連到了搬走的文件，我的連結改寫動了它——**已還原**。

> 第四份是這次唯一一個「我改壞了一個跟本次搬移無關的檔案」的例子。
> 抓到它的同樣是測試（`test_protocol_and_specification_digests_match_the_pins`），不是我的檢查清單。

---

## 3. 最終狀態

| | 份數 |
|---|---:|
| 搬進 `docs/archive/` | **17** |
| 其中在 `docs/` 原路徑留一行轉址 | **7** |
| 因 digest 被釘住而**留在 `docs/`、位元組未動** | **3** |
| `docs/` 的 md 總數 | **64**（原 73） |

### 那 7 個轉址，兩種不同的理由

**四份**：被**凍結、digest 被釘住的 JSON 以路徑指名**（`specification_path` 等）。
那些 JSON 一個位元都不能改，所以原路徑必須繼續解析得到東西。
（`TRAINING_SEED_VARIANCE_SPEC`、`V7_CANDIDATE_SELECTION_SPEC`、
`V7_ACTION_INTERFACE_PILOT_IMPLEMENTATION_RECEIPT`、`V7_PRETRAINING_SEED_VARIANCE_INFEASIBILITY_RECEIPT`）

**三份**：被 §2 那些**留在原地、位元組不能動的 spec 連到**。
它們的連結改不了，所以被連到的目標必須在原路徑留下轉址。
（`V7_EXPOSURE_CENSORING_AUDIT_SPEC`、`SECOND_CASE_V2_BUDGET_PROBE_RECEIPT`、
`TRACKED_LINEAGE_TRAINING_RECEIPT`）

---

## 4. 一個 fail-closed gate 擋在正確的位置

`gate_status_registry.json` 的 `evidence` 欄有 **5 筆**指向要搬的 receipt，
而 `gate_status_contract.py:279` 逐筆驗證檔案存在，不存在就 `evidence file does not exist`。
這 5 筆非改不可，漏改會被當場擋下。已全部改為 `docs/archive/…`。

其餘約 190 處連結**沒有任何機制會在漏改時報錯**——正是 PROJECT_ASSESSMENT §4.3.1 說的型態，
只能靠連結檢查器逐一掃。

---

## 5. 改了幾處

| 位置 | 份數／處數 |
|---|---|
| 已搬文件內部（`../` → `../../`；指向留下文件的同層連結加 `../`） | 15 份 |
| 留在 `docs/` 的文件指向已搬文件 | 16 份 |
| 根目錄 md（README、CHANGELOG） | 2 份 |
| `STATUS.yaml` | 20 處 |
| `gate_status_registry.json` 的 evidence | 5 筆 |
| `test_gate_status_contract.py` 的 fixture | 1 處（見 §6） |

---

## 6. 測試 fixture 假設文件是平的

`test_gate_status_contract.py` 的 `tree` fixture 只建 `docs/`，然後把每個 evidence
複製進去——文件一進子目錄就 `FileNotFoundError`。修法是一行：依每個檔案自己的深度建父目錄。
**這不是放寬檢查**，是讓合成 repo 能反映真實的目錄結構。

---

## 7. 量測

| | 搬移前 | 搬移後 |
|---|---|---|
| `docs/` 的 md | 73 | **64** |
| `docs/archive/` | — | **17** |
| 壞掉的連結 | 0 | **0** |
| 全套測試 | 1 failed / 1061 passed | **1 failed / 1061 passed**（同一個未放寬的 `PRIMARY_CASE_RECEIPT_IDENTITY`） |
| 三個文件契約 | 全過 | **全過**（33 gates／54 sites、1 claim／3 sites／10 papers、兩個閉包不變） |

---

## 8. 後續：§4.3 的 receipt 分流（同日，任務 #99）

擁有者要求把 §4.3 的「活文件約 12 份」也做掉。**先量到的結論是那個數字達不到**：

`docs/` 裡已經有 **11 份結構性搬不動**——§2 的 4 份 digest 被釘住的 spec，
加上 §3 為了保住那些 pin 而留下的 7 份轉址。
「12 份留在 `docs/`」等於只剩 **1 個名額**給真正的規劃文件。
這和 §4.2 的「942 → 520」是同一類估計：寫下時合理，遇到不變量就不成立。

**擁有者選了保守做法：只搬 receipt。**
14 份實作 receipt 進 `docs/receipts/`，索引為 `docs/receipts/README.md`，
所有 spec、計畫文件、文獻地圖留在原地。

| | 前 | 後 |
|---|---:|---:|
| `docs/` 的 md | 64 | **51** |
| `docs/receipts/` | — | **14** |
| `docs/archive/` | 17 | 17 |

**這次沒有重演位元組事故**：搬移前先檢查了「哪些 receipt 被那 4 份位元組不能動的 spec 連到」，
只有 `PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10` 一份，已在原路徑留轉址。
四份被釘住的 spec 搬移後逐一比對 sha256，與 `HEAD` 完全相同。

`gate_status_registry.json` 的 `PUB_B0` evidence 路徑同步改為 `docs/receipts/…`。

量測：**1 failed / 1061 passed**，0 個壞連結，三個文件契約全過。

---

## 9. 明確不在範圍內

| 沒做 | 為什麼 |
|---|---|
| **沒有改任何凍結證據** | 一個位元都沒動；搬不動的就退回原地 |
| **3 份 spec 沒有搬** | §2——搬移與 digest 不可兼得，屬結構性限制而非選擇 |
| **§4.3 的「約 12 份」沒有達成，也達不到** | 見 §8：11 個名額已被搬不動的檔案佔掉。已改為只搬 receipt，`docs/` 降到 51 |
| **spec 與計畫文件沒有搬** | 擁有者選的保守範圍（§8）；只有 receipt 分流 |
| **文件內容一個字都沒改** | 只改路徑與連結 |
