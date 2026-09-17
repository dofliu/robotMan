# 衍生claim 的一致性

ID：`DERIVED-CLAIM-CONSISTENCY-V1` ｜ 日期：2026-09-17 ｜ 性質：**工程規範與 fail-closed 契約**，不是 protocol、不是 receipt

登錄檔：[`backend/derived_claim_registry.json`](../backend/derived_claim_registry.json)
｜ 檢查程式：[`backend/derived_claim_contract.py`](../backend/derived_claim_contract.py)
｜ 測試：`backend/test_derived_claim_contract.py`

```
python3 -I -S backend/derived_claim_contract.py          # 不一致則 exit 1
python3 -I -S backend/derived_claim_contract.py --list   # 列出每篇論文的核實等級
```

---

## 1. 這補的是哪一個洞

[GATE_STATUS_SINGLE_SOURCE §6](GATE_STATUS_SINGLE_SOURCE.md) 明寫它**不涵蓋**一類失效，並把它記為已知缺口：

> 「Pardo 已核對」不是 gate 狀態，而是一個**衍生清單**與文獻地圖 `U`／`S` 等級之間的一致性。
> 那需要另一個裝置，目前沒有做。

本文件就是那個裝置。

**衍生 claim**＝用散文重述一件「從某個權威來源算出來」的事。
「還沒讀的是 Colas 2019、Manski／Tamer、Hollenbeck & Wright」這句話，
是從兩份文獻地圖裡十列的核實等級算出來的。**來源變了而散文沒變，它就過期。**

## 2. 為什麼不能沿用 gate 那一套

| | `GATE-STATUS-SINGLE-SOURCE-V1` | 本契約 |
|---|---|---|
| 失效形狀 | 文件**複製**了一個狀態字串 | 文件**重述**一個從多列算出來的集合 |
| 檢查方式 | 與權威格相等 | 與來源重新計算的結果相符 |
| 過期時的樣子 | 兩處狀態不一致 | **哪裡的狀態都沒有不一致**——只是清單裡多了一篇已核對的論文 |

第三列是關鍵：Pardo 過期時，沒有任何一個 gate 狀態是錯的。
`TRACK_A_REFRAME` §8 寫著 `FOUR_VERIFIED_REMAINING_U`（正確），§10 的清單仍列 Pardo（錯誤）。
gate 契約看不到它，因為那裡沒有狀態可比。

## 3. 已量到的實例

2026-09-16 `arXiv 1712.00378`（Pardo）原文核對完畢，地圖中由 `U` 升為 `S`。
**三份文件繼續把它列在待核對清單裡**：`PUBLICATION_PLAN` §8、`PROJECT_STATUS` §8、`TRACK_A_REFRAME` §10。
其中第三份**自己跟自己矛盾**——§8 已寫 `FOUR_VERIFIED`。

2026-09-17 才被發現，而且是在**讀「描述這個問題的那一節」時**順手發現的。
完整紀錄見 [PROJECT_ASSESSMENT §4.3.1](PROJECT_ASSESSMENT_2026-09-16.md) 第 4 例。

## 4. 規則

來源：兩份文獻地圖的核實等級欄（`U`／`R`／`S`），`U` 為「未核實」。追蹤 10 篇論文。

claim：`pub_a0_priority_to_verify`，成員 Colas 2019、Manski 1990／Tamer 2010、Hollenbeck & Wright 2017，三個站點。

| 規則 | 擋下什麼 |
|---|---|
| `MEMBERS_STILL_UNVERIFIED` | 登錄的成員在來源已升為 `S`／`R` |
| **`NO_VERIFIED_PAPER_NAMED`** | **清單裡出現任何已核實的論文**——這是上面那個實例 |
| `ALL_MEMBERS_NAMED` | 某個成員在某一份文件裡被悄悄拿掉 |
| `COUNT_WORD_MATCHES_MEMBERS` | 少了一篇但「優先三篇」沒改 |
| `CLAIM_RETIRES_WHEN_SOURCE_EMPTY` | 全部核實完了，清單卻還在 |
| `UNREGISTERED_COPY`（scan） | **第五份副本長出來** |

`NO_VERIFIED_PAPER_NAMED` 是最有力的一條：它**不依賴有人記得去更新 `members`**。
只要清單裡出現任何一篇來源已標為已核實的論文，就失敗。

## 5. 三件實作上非做不可的事

**一篇論文有兩組互不重疊的身分，兩組都要登錄。**
地圖那一列寫「Colas, Sigaud, Oudeyer, *A Hitchhiker's Guide to Statistical Comparisons*」，
claim 那一句寫「Colas 2019」——**兩個字串在對方那裡都不出現**。
因此：以 arXiv id 定位地圖列（沒有 id 的以登錄的 `row_match`，例如 Manski、Tamer、Hollenbeck & Wright），
散文中的寫法另外登錄為 `claim_names`。

**只讀清單片段，不讀整行。** 三個站點的句子都是**先報告已核對了哪些**、再說剩下什麼：

> 再兩篇已核對（2026-09-16：Pardo `1712.00378`、Learning to Locomote `2010.04304`）。**優先三篇**：…

那個前言**本來就該提到已核實的論文**。以整行比對會把前言誤判成清單——實作時確實先撞到這個假陽性。
清單片段＝從數量詞到該句句號為止。

（這與 gate 契約「讀狀態格開頭而非整列」是同一個教訓的第二次出現。）

**更正註記全程跳過。** 依先立後撤，「本列原寫『優先四篇』並把 Pardo 2018 列為待核對」這句
**必須留在文件裡**——而它正好會觸發 `NO_VERIFIED_PAPER_NAMED`。帶 `更正` 標記的行不算活的 claim。

## 6. 明確不在範圍內

| 不涵蓋 | 為什麼 |
|---|---|
| gate 狀態的跨文件副本 | 由 [`GATE-STATUS-SINGLE-SOURCE-V1`](GATE_STATUS_SINGLE_SOURCE.md) 涵蓋 |
| 地圖 §4 的 gap 判定、claim→evidence 對照表 | 那是對整份地圖的**判斷**，不是一條規則能重算的清單；等級變動時要重新論證，`TRACK_A_REFRAME` 記錄該過程 |
| 沒有任何 claim 提到的地圖列 | 沒有東西重述它，就不會過期；要納入只需補一個 `claim_names` |

## 7. 改一個核實等級的步驟

1. 改文獻地圖那一列的 `U`／`R`／`S`，並依 §7 寫下核對紀錄。
2. 跑 `python3 -I -S backend/derived_claim_contract.py`——它會列出**每一個還在提它的清單**。
3. 從 `members` 移除該篇、更新三個站點的清單與數量詞，依先立後撤把原措辭記在 `[BLOCKER]` 註記裡。
4. 直到輸出 `DERIVED_CLAIMS_CONSISTENT`。

Pardo 那一次花了一天才被人發現；現在它在測試裡就是紅的。
