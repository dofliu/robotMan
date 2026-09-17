# Gate 狀態的單一權威來源

ID：`GATE-STATUS-SINGLE-SOURCE-V1` ｜ 日期：2026-09-17 ｜ 性質：**工程規範與 fail-closed 契約**，不是 protocol、不是 receipt

登錄檔：[`backend/gate_status_registry.json`](../backend/gate_status_registry.json)
｜ 檢查程式：[`backend/gate_status_contract.py`](../backend/gate_status_contract.py)
｜ 測試：`backend/test_gate_status_contract.py`

```
python3 -I -S backend/gate_status_contract.py          # 檢查，不一致則 exit 1
python3 -I -S backend/gate_status_contract.py --list   # 列出每個 gate 的權威狀態
```

---

## 1. 為什麼要有這個東西

**這不是預防性設計，是對已量到的失效的回應。**

2026-09-14 至 09-16 之間，同一個事實在四個地方過期
（完整紀錄見 [PROJECT_ASSESSMENT §4.3.1](PROJECT_ASSESSMENT_2026-09-16.md)）：

| # | 事實 | 漏掉的地方 |
|---|---|---|
| 1 | tracked-lineage 兩線 09-14 已執行完畢 | `RESEARCH_EXECUTION_PLAN` 的 `P-NEW` 仍寫 `NOT STARTED` |
| 2 | 同 #1 | `PUBLICATION_PLAN` §5 仍寫「尚未執行」 |
| 3 | `PUB-A0` 升為 `FOUR_VERIFIED_REMAINING_U` | `PUBLICATION_PLAN` gate 表沒改 |
| 4 | Pardo 2018 已核對、`U` → `S` | 三份文件的「優先四篇」清單仍列它 |

量到的規模：`PUB-A0` **一個** gate 的狀態有 **24 份副本、散在 8 個檔案**。

**四個都不是被機制抓到的，是有人回頭看才發現的。** 契約程式碼有 fail-closed gate，文件沒有——
本文件補上文件這一側。

## 2. 規則

1. **每個 gate 恰有一個 `AUTHORITY` 站點。** 它是該 gate 狀態的唯一權威來源。
2. 其他任何**陳述該 gate 狀態**的地方登錄為 `MIRROR`，由契約逐一比對。
3. 契約**失敗即為錯誤**，不是警告。狀態變更沒同步到某個 mirror → 測試紅。
4. 新增一個陳述該狀態的地方，**必須**登錄；未登錄的新副本不受保護。

| 族 | AUTHORITY |
|---|---|
| `PUB-A*`／`PUB-B*`／`PUB-C*` | [PUBLICATION_PLAN](PUBLICATION_PLAN.md) §5 的三張 gate 表 |
| `PDR-0`–`PDR-8` | [PAPER_DATA_READINESS](PAPER_DATA_READINESS.md) 的 gate 表 |
| `V0`–`V4` | [PROJECT_STATUS](PROJECT_STATUS.md) §1 的 gate 表 |

共 **33 個 gate、54 個站點**（21 個 AUTHORITY 之外的 mirror）。

## 3. 狀態怎麼被讀出來

**狀態是它自己那一格的開頭，不是整列。** 這一點是量出來的：11 列在鄰欄寫著
`readback PASS`、`16/14 exact`，而 gate 本身是 `IN PROGRESS`——那些 `PASS` 說的是子項，
不是 gate。以整列比對會產生 11 個假陽性。

讀法：去掉強調與反引號 → 取**最早位置**能匹配的 accepted form，同位置取**最長**的 →
其後全部視為描述性尾巴。

- `IN PROGRESS / content-sensitive Git identity PASS` → `IN_PROGRESS`
- `PARTIAL IMPLEMENTED / NOT PASS` → `PARTIAL_IMPLEMENTED_NOT_PASS`（不是 `PARTIAL`）
- `仍 BLOCKED by B2` → `BLOCKED`（容許少量前置助詞）

**狀態是 token，不是字串。** 同一個狀態在 `PROJECT_STATUS` 寫 `PARTIAL_IMPLEMENTED_NOT_PASS`、
在 `ROADMAP` 寫 `PARTIAL IMPLEMENTED / NOT PASS`；`PDR-6` 一邊寫 `SOFTWARE CONTRACT PARTIAL`、
一邊寫 `SOFTWARE PARTIAL`。強制單一拼法等於為了工具去改本來就正確的文件；放任任何拼法等於沒檢查。
因此登錄檔對每個 token 列出 **accepted forms**，**新增一種寫法是一次刻意的登錄檔修改**。

**更正註記是歷史，不是現況。** 依先立後撤，`（**<日期> 更正` 之後的文字保留被取代的原措辭；
契約在讀狀態前先把它剝掉。否則 `ROADMAP` 的 V1 格（其中引用了原本的 `BLOCKED BY V0`）會被誤讀。

## 4. 站點怎麼被定位——為什麼是列舉而不是比對

**`V1` 在本 repo 同時是 V&V gate 與版本號**：`analytical fixture V1`、`PAPER_RUN_MANIFEST_V2`、
`PUBLICATION-PLAN-V3`、`Motion Task V1`、`第二案例 V1`。任何掃 `V\d` 的做法都會把兩者混在一起；
而為了避開誤判把 pattern 調嚴，會**安靜地**不再涵蓋那個 gate——比誤判更糟。

所以每個站點**列舉**它的檔案與一個 **anchor**：識別該列的首格或特徵片語，且 anchor 本身不含狀態。

- anchor 找不到 → **失敗**（列被改名／搬走／刪除，必須重新登錄，而不是讓檢查安靜地停止覆蓋）
- anchor 命中多列 → **失敗**（anchor 必須唯一識別一列）

## 5. 明確不在範圍內

不涵蓋的部分逐項寫下來，避免它變成一個安靜的缺口：

| 不涵蓋 | 為什麼 |
|---|---|
| `VV_PLAN` 的 `V0-R01`–`V3-R09`、`DCOMP`／`TRACE`／`TASK` 各列 | 每列的狀態只在一份文件裡陳述，**沒有副本可以走樣** |
| spec／receipt 內的 `TL-*`、`TL-CK-*`、`LB-*`、`SEL-*`、`EP-*` 判準 | **receipt-bound**：執行當下凍結，永不得改寫 |
| 只提及 gate 而不陳述其狀態的句子（如「等 `PUB-B2`」） | 不帶狀態，不會過期 |
| 掃描自由文字中的 `V0`–`V4` | 見 §4 的歧義 |

## 6. 這個契約不做什麼

**它不判斷狀態是不是真的。** 它判斷專案是不是到處都說同一件事。

狀態與 receipt 是否相符，是 [CHANGELOG](../CHANGELOG.md) 條目 (ah) 那次逐列盤點的工作。
本契約的用處是：**讓那次盤點不必再用手做一遍。**

它也不涵蓋 §1 表中的第 4 例那一類失效——「Pardo 已核對」不是 gate 狀態，而是一個
**衍生清單**（待核對優先清單）與文獻地圖 `U`／`S` 等級之間的一致性。那需要另一個裝置。

[RESULT] **2026-09-17 已補上**：[`DERIVED-CLAIM-CONSISTENCY-V1`](DERIVED_CLAIM_CONSISTENCY.md)
（[登錄檔](../backend/derived_claim_registry.json)、[契約](../backend/derived_claim_contract.py)）。
本段原寫「目前沒有做」，依先立後撤保留在上方。兩個契約的分工見該文件 §2：
gate 契約比對**被複製的狀態字串**，衍生 claim 契約比對**被重述的集合**——Pardo 過期時
哪一個 gate 狀態都沒有錯，所以 gate 契約看不到它。

## 7. 改一個 gate 狀態的步驟

1. 改 `backend/gate_status_registry.json` 裡該 gate 的 `status`／`detail`／`as_of`／`evidence`。
2. 跑 `python3 -I -S backend/gate_status_contract.py`——它會**列出每一個還沒跟上的 mirror**。
3. 逐一改掉，直到輸出 `GATE_STATUS_SINGLE_SOURCE_CONSISTENT`。

漏改不再需要有人回頭看才會發現：它在測試裡就是紅的。
