# Track B formal evaluation：兩個子問題的決定——延後，seeds 保持封存

日期：2026-09-22 ｜ ID：`TRACK-B-DEFERRAL-DECISION-2026-09-22` ｜ 決定者：專案負責人（委託採納助理建議，見 §0）

狀態：`DECIDED / TRACK_B_FORMAL_EVALUATION_DEFERRED / SEEDS_20000-20029_SEALED / NO_PROTOCOL_CHANGE`

證據等級：本文件是**決策紀錄**，不是 evidence。沒有鑄造 authorization evidence、沒有解封任何 seed、
沒有改任何 protocol JSON 或 contract、沒有新增訓練或評估。

---

## 0. 決定與它的來源

[PUBLICATION_PLAN §5](PUBLICATION_PLAN.md) 自 2026-09-10 授權 formal evaluation 後，留下兩個只有負責人能做的子問題：

> (a) 用現行的、公開宣告非預註冊的 `SELECT-V7-CANDIDATE-FORMAL-V1`，還是先在 OSF 預註冊一條替代規則？
> (b) 唯一未被檢視的 FORMAL seed 範圍 `20000–20029` 要花在哪條訓練線？

專案負責人於 2026-09-22 詢問「接下來有什麼重要的工作要推進」，助理把這兩個子問題列為第一項並說明只有負責人能決定；
負責人回覆：**「第一點 請你建議後 開始就好」**——即委託助理提出建議並據以推進。以下是助理的建議，負責人以上述文字採納。
負責人可隨時撤銷；撤銷時本文件保留、另立新紀錄。

**決定：**

| 子問題 | 決定 |
|---|---|
| (a) 規則 | **若日後執行，先預註冊替代規則**，不用現行的 post-hoc 規則。這是 [PUBLICATION_PLAN §5](PUBLICATION_PLAN.md) 原本的建議（「後者，前提是時程允許」）。 |
| (b) seed 範圍 | **兩條線都不花。`20000–20029` 保持封存**，保留給一條 reference policy 達到 `PUB-B2` 出口條件（DEV seeds 上事先凍結的 full-exposure 比例）的訓練線——這樣的線今天不存在。 |
| 整體 | **Track B formal evaluation 延後（DEFERRED）**；`PUB-B4` OSF 預註冊一併延後——沒有執行對象的預註冊沒有意義。 |

---

## 1. 理由（全部是已量到的事實，出處在括號裡）

1. **在 v7 線上執行幾乎確定得到 `SELECTION_COMPLETE_NO_CANDIDATE`。** `SEL-C2` 要求 reference 與 candidate 每個 episode 都
   `COMPARABLE`；retained seed-variance evidence 上 `V7A` 143/150、`V7B` 120/150、`V7C` 0/150；iid 外推下 reference＋`V7B` 的聯合
   通過機率 `2.2 × 10⁻¹⁸`、reference＋`V7C` 為 `0`。FORMAL 資料只能套用一次，不得重跑。
   （[PUB_B0 receipt §3](receipts/PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10.md)、[V7_CANDIDATE_SELECTION_SPEC §5](archive/V7_CANDIDATE_SELECTION_SPEC.md)）
2. **在新訓練線上執行同樣浪費。** `TRACKED-LINEAGE-TRAINING-V1`／`V2` 兩線各 5 replicate 全部完成、lineage 進版控（`PUB-B1` 達成），
   但 full-exposure 在 `2,000,000` 與 realized `4,015,200` 步兩個預算下皆 **`0/30 × 5`**（`PUB-B2` 未達成）。reference 自己都跑不完任務，
   花掉唯一的 FORMAL 範圍換不到任何可識別的量。
   （[V1 receipt](archive/TRACKED_LINEAGE_TRAINING_RECEIPT_2026-09-14.md)、[V2 receipt](archive/TRACKED_LINEAGE_TRAINING_V2_RECEIPT_2026-09-14.md)）
3. **沒有研究目標在等這個結果。** Track A 於 2026-09-09 重構為「censoring regime 的評估效度研究」後，論文需要的是被 censoring
   截斷的例子（v7、Walker2d、tracked lineage 已全部提供），不需要一個會走的 reference policy。`PUB-B2` 的理由在那天就消失了。
   （[PROJECT_ASSESSMENT §3](PROJECT_ASSESSMENT_2026-09-16.md)、[TRACK_A_REFRAME](TRACK_A_REFRAME_2026-09-09.md)）
4. **加預算不會改變 2。** V2 是 V1 的加倍預算續訓，曲線在上限處更陡但仍 0/30；獎勵結構的量化診斷指出瓶頸不在步數。
   （[PROJECT_ASSESSMENT §1.4](PROJECT_ASSESSMENT_2026-09-16.md)）
5. **既有規則已寫了一半答案。** 凍結順序是「授權在前、預註冊在中、解封在後」；在 (a)(b) 未決前不鑄造 authorization evidence、
   不解封 `20000–20029`。本決定把「未決」變成「決定延後」，順序與禁令都不變。
   （[PUBLICATION_PLAN §6](PUBLICATION_PLAN.md)）

---

## 2. 這個決定改變了什麼、沒改變什麼

| | 內容 |
|---|---|
| 改變 | `PUB-B0` 的描述由「兩問未決」變為「兩問已決：延後」；[PUBLICATION_PLAN §5](PUBLICATION_PLAN.md)、[PROJECT_STATUS §8](PROJECT_STATUS.md)、README「下一個決策」列、`STATUS.yaml` 同步 |
| 不變 | `PUB-B0` 狀態 token 仍是 `AUTHORIZED`（授權沒有撤銷，只是不現在用）；`PUB-B4` 仍 `NOT_STARTED`；`PUB-B2` 仍 `NOT_ATTAINED`；`EP-01`／`EP-02`／`EP-03` 不動；protocol JSON 一個位元都沒動；`20000–20029` 未被存取 |
| 解除條件 | 出現一條 reference policy 達到 `PUB-B2` 出口條件的訓練線 → 依 (a) 先在 OSF 預註冊替代規則（`PUB-B4`）→ `SELECT-AMENDMENT-01`（`EP-03` narrowing）→ `EP-01`／`EP-02` amendment → 解封 |

---

## 3. 這騰出了什麼

負責人端：Track B 現在沒有待做事項。**唯一還在等負責人的是 Track A**：`PUB-A0` 剩餘 `U` 條目的原文 PDF
（優先 Colas 2019、Manski／Tamer、Hollenbeck & Wright），這個環境連不到出版方。

工程端：依 2026-09-22 的排序，先做 [ROADMAP §9](ROADMAP.md) 第 3 項（browser visual verification）與 Raibert 堆疊瓶頸的定位
（[RAIBERT_STACK_DIAGNOSIS_2026-09-22](RAIBERT_STACK_DIAGNOSIS_2026-09-22.md)），再是第 4 項 V1 oracle。

---

## 4. 不能拿這份紀錄說什麼

- 不是 `PUB-B0` 的撤銷；授權仍在。
- 不是「Track B 永久關閉」；是有明確解除條件的延後。
- 不代表 v7 或 tracked-lineage 任何一條線的結論改變；它們的 receipt 一字未動。
