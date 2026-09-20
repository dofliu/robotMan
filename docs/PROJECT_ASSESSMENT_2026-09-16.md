# 專案評估：現況、價值與去向

最後更新：2026-09-17（新增 §4.3.1）｜ 性質：**給專案負責人的決策文件**，不是 receipt，不是 spec
｜ 依據：`main` 於 `095247c`（PR #21 合併後）的實測盤點

本文件回答三個問題：這個專案現在是什麼、它值不值得推廣、下一步該做什麼。每個數字都是從 repo
量出來的，來源寫在旁邊；每個判斷都標明是量測、推論還是建議。**它不替負責人做決定**——§5 列出的
是選項與代價，不是指令。

---

## 0. 一句話

**一個能跑、能教的 humanoid 模擬教具，加上一個真正可發表的評估效度發現，兩者合起來不到
一萬行，卻穿著一件三萬行、六十三份文件的研究基礎設施外衣。** 外衣本身品質很高——但它正在驗證一個
不會走路的機器人。

---

## 1. 實測盤點

### 1.1 程式碼：核心與外衣的比例

| 類別 | 行數 | 檔案 | 說明 |
|---|---:|---:|---|
| 核心 robotics + 應用 | **6,871** | 14 | `simulator`、`live_sim`、`gait`、三個 controller、`model_builder`、`humanoid_env`、`train_ppo`、`eval_policy`、`main`、`run_trace` |
| 前端 | **3,561** | 18 | React + Three.js，`tsc` 零錯誤，`vite build` 2.1 s 通過 |
| 證據契約／replay／bundle | **29,294** | 42 | 見 §1.2 |
| 測試 | 14,768 | 28 | 692 個測試函式，pytest 收集 942 個 case |

核心與外衣的比例是 **1 : 4.3**。這不是「有死碼」——我一開始這樣假設，查了之後**是錯的**：
21 個沒有任何非測試模組 import 的檔案，全部帶有 `__main__`，都是設計為命令列執行的合法入口，
整個後端**沒有一行不可達的程式**。真正的狀況比死碼更難處理：**一萬三千行活著、有測試、程式品質良好，
但它服務的研究線已經結案的工具碼。**

### 1.2 契約程式碼依研究線與該線的下場

| 研究線 | 契約行數 | 測試函式 | 該線在 `STATUS.yaml` 的下場 |
|---|---:|---:|---|
| v7 pilot / exposure audit / candidate selection | **8,638** | 145 | pilot 來源 `BROKEN_BY_DESIGN`；selection `NOT_EXECUTABLE`；pretraining variance `UNMEASURABLE` |
| V1 analytical / oracle / paper bundle | 6,005 | 61 | `PARTIAL_IMPLEMENTED_NOT_PASS`，gate 仍活著 |
| seed variance | 3,034 | 81 | 由證據結案（`UNMEASURABLE`） |
| paired statistics / experiment matrix | 2,939 | 46 | 軟體通過、科學未通過，gate 仍活著 |
| second case（Walker2d / Hopper） | 2,072 | 68 | 2026-09-09 由決定結案 |
| environment lock / run-manifest binding | 1,985 | 89 | **活的基礎設施** |
| tracked lineage V1 + V2 | 1,661 | 108 | 兩線皆 `NOT_ATTAINED`，線已完成 |
| exposure identification / paper-data contract | 1,402 | — | 活的（Track A 的核心量測工具） |
| R0 regime probe | 411 | 18 | 已執行，完成 |

**已結案或不可執行的線**（v7、second case、seed variance、tracked lineage、R0）合計約
**15,800 行契約碼、420 個測試函式**——佔契約碼的 54%、測試的 61%。它們沒有壞，只是任務結束了。

反過來看：**692 個測試函式裡，只有 76 個（11%）在測那個教學應用本身。**

### 1.3 機器人：能不能走

| 訓練線 | 結果 | 出處 |
|---|---|---|
| v5（2026-08-30） | **10/11 準則通過、無跌倒**、穩態 0.586 m/s、只有 saturation duty 38.4% > 30% 未過 | `motion_task_status` |
| v6、v7A/B/C | 全部退步；v7C 30/30 早跌 | `motion_task_training_status` |
| tracked lineage V1（5 × 2.0M 步，從零） | **0/30 × 5**，平均存活 2.44–2.81 s | [V1 receipt](archive/TRACKED_LINEAGE_TRAINING_RECEIPT_2026-09-14.md) |
| tracked lineage V2（各再 +2.0M 步） | **0/30 × 5**，平均存活 2.73–3.46 s；獎勵 +51–+66 | [V2 receipt](archive/TRACKED_LINEAGE_TRAINING_V2_RECEIPT_2026-09-14.md) |

**機器人會走**——v5 的 policy artifact（1.9 MB）在版控裡、registry 選定、Live 模式可載入，10/11
準則通過。**機器人從零學不會走**——十個 replicate、兩種預算、300 個 episode，沒有一個撐過 9 秒，
全部在 2.5–3.5 秒、也就是 `STEADY_WALK` 起點附近跌倒。

v5 為什麼能而後面都不能？v5 的 checkpoint（122,880 步）是**在看過結果之後**從一個已退步的 run
裡挑出來的——這正是整個 tracked-lineage 線存在要移除的 provenance 缺陷。所以現況是：**唯一會走的
policy 是用不可重建的方式得到的；所有可重建的方式都不會走。**

### 1.4 為什麼加預算沒用：獎勵結構的量化診斷

`backend/rl/humanoid_env.py` 的獎勵（tracked-lineage 用的 `phase_observable_v5` 環境）：

```
每步：r_imitate(≤0.7) + r_vel(≤1.2) + r_alive(0.3) + r_upright(≤0.2) + r_stop(0.35，靜止時)
      − p_energy − p_rate − p_side − p_reverse
跌倒：−5（基底）−45（v4 起加重）= −50，且終止
控制步 0.02 s，9 秒任務 = 450 步
```

站著不動、姿態貼合參考時，每步約 **2.5**。站滿 `INITIAL_STAND` + `START` 的 2.5 秒 ≈ 125 步
≈ **310**，再吃 −50 的跌倒 ≈ **260**——**這就是 V1 實測 227–232、V2 實測 283–295 的來源**：
V2 多出來的獎勵，是站得更久（2.7–3.5 s）、站得更好，不是走了。

[INFERENCE] 「站好、在轉換點跌倒」是一個穩定的局部最優。要離開它，policy 得在 `START→STEADY_WALK`
時忍受 `pose_err`、`vel_err` 同時飆高（`r_imitate`、`r_vel` 一起掉）而且當下跌倒機率很高。**十個
replicate 全部寧願吃 −50 也不嘗試**，代表嘗試起步的期望代價 > 50。v4 把懲罰從 −5 加到 −45 後仍
留下 stop 失敗，說明**懲罰數值不是綁住結果的那一項**——綁住的是 imitation／velocity 形塑讓「站」
比「不完美地走」每步賺得多太多。

[INFERENCE] 因此 V2 receipt 的結論「要改的不是預算」是對的，而且現在能說出**為什麼**：可行的槓桿是
curriculum（從 v5 的行走狀態當作階段起點）、分階段的形塑（`START` 期間降低 imitation 權重、提高進度
權重）、或參考軌跡本身。任何一個都需要**新的 protocol 版本**並揭露它是在已知 V1、V2 結果之後設計的。

### 1.5 證據的版控狀況

| 證據 | 大小 | 在版控？ | 後果 |
|---|---:|---|---|
| tracked lineage V1+V2（40 個 checkpoint、manifest、lock、曲線、receipt） | 77 MB | **是** | 兩線的標籤可從 repo 重算（容器重啟時已實際驗證） |
| seed variance `raw_replicates.json` 等 | 360 KB | 是 | `[−13.5, −12.4]` pp 的 method-level bound 可重導 |
| second case、R0 probe、environment locks | 1.7 MB | 是 | 可重導 |
| **v7 pilot 原始 bundle**（seed 8700、14 個 artifact） | 109.5 MB | **否**（`run_traces/`，gitignored） | §4.1「Pilot」欄的每個數字**不能**從 repo 重導 |
| **v7 exposure audit 凍結 bundle** | 113 MB | **否**（同上） | §4.2 的 audit 發現**不能**從 repo 重導 |

這是 [REPOSITORY_GUIDE §3](REPOSITORY_GUIDE.md) **明文的政策**——`run_traces/` 「不是公開 immutable
evidence bundle」，正式 bundle 應放外部儲存——不是疏忽。但後果要說清楚：**專案自稱「最強結果」的那條
v7 線，是所有線裡從 repo 最不可重導的一條。** 較弱的線反而都進了版控。

### 1.6 文件

63 份 `docs/*.md`（約 700 KB，**不含本文件**；量測基準 `main@095247c`），加 `CHANGELOG.md` 110 KB、`STATUS.yaml` 78 KB。`STATUS.yaml`
裡單一欄位的字串長達數千字元。107 個 commit 中 67 個（63%）集中在兩天（09-08 有 34 個、09-14 有 33
個）——這是 AI 工作階段驅動的節奏，每個階段產出一份 spec、一份 protocol、一個 contract、一份
receipt、再更新六份規劃文件。**新人無法從這裡上手**；REPOSITORY_GUIDE 在本次盤點前還寫著
tracked_lineage_evidence「尚未建立」、測試數 923——兩處都已過期。

---

## 2. 它值不值得推廣——分四個面向

| 面向 | 判斷 | 依據 |
|---|---|---|
| **作為 robotics 研究** | **弱** | 沒有新的控制方法；reduced-order 12 關節 + prescribed gait + PPO 是標準做法；沒有實體驗證；專案自己的 `progress: 0`；可重建的訓練線全部不會走 |
| **作為評估效度（evaluation-validity）研究** | **真的有一篇** | V7C 表面 −36 pp 的「改善」被量測證明是 exposure artifact；`OBSERVED ⇏ full exposure` 這個盲點；在 Walker2d-v5 第二個 plant 上重現（`PUB-A1a` PASS）；censoring regime 分類；R0 probe。這是 Track A，2026-09-09 已重構成這個題目，**證據已經在手上** |
| **作為教學工具** | **有實質價值，但被埋住** | 教學應用**完全不依賴**任何研究契約模組（`main.py` 零 import）；前端建置乾淨；USAGE §6 的四條教學流程（致動器敏感度、穩定性概念、控制器行為、手臂示範）在教學上成立；v5 policy 提供可示範的行走 |
| **作為「可重現 RL 實驗」的工程範例** | **比多數已發表的 RL 工作嚴謹** | freeze-before-execute、digest 連鎖、fail-closed、narrowing-only amendment、事先宣告量測選擇、負結果據實報告、撤回的觀察留在記錄裡。這本身可以是研究方法課的教材——**但它目前在驗證一個不會走的機器人** |

[INFERENCE] 誠實的總結：**這裡有兩個好東西和一個大問題。** 好東西是教具與 Track A 那篇論文；問題是它們
被一個為了「把不會走的機器人量得非常嚴謹」而長出來的基礎設施包住，而那個基礎設施的大部分現在服務的
是已經結案的線。

---

## 3. 一個 gate 的理由消失了

`PUB-B2`（reference policy 在 DEV seeds 達到 30/30）是為了 `PUB-B3`（between-replicate variance
需要一個不被 exposure censoring 截斷的 reference）而設的。這在 Track A 還是「比較控制方法」時成立。

**2026-09-09 Track A 重構為「censoring regime 的評估效度研究」之後，論文不再需要一個會走的
reference policy**——它需要的是被 censoring 截斷的例子，而那正是 v7、Walker2d、tracked lineage
全部已經提供的。`PUB-B2` 的**理由**在重構那天就消失了，但 gate 留了下來，之後又花了兩條線
（V1、V2，各五個 replicate）去追它。

[INFERENCE] 這不是誰的錯——每一步在當時都是合理的下一步。但它是本文件最重要的一個觀察：**繼續追
30/30，除了工程上的完整感之外，已經沒有一個研究目標在等它。**

---

## 4. 架構上可以改的、可以拆的

### 4.1 可以拆成兩個產品，今天就可以

教學應用與研究基礎設施**在程式碼層面已經完全解耦**：`main.py` 不 import 任何契約模組；前端只打
7 個 endpoint，全部與契約無關。拆開不需要重構，只需要搬。

[BLOCKER] **2026-09-17 更正：上一段少算了一行。** 實測 `main.py` 的遞移閉包，13 個模組裡 12 個成立、**1 行不成立**——`main.py` 從 `rl/train_ppo.py` 取 `public_training_inventory`，於是「列出訓練 profile」這個唯讀端點拉進一個 **1,292 行的訓練驅動**，再經由它拉進 `stable_baselines3` 與該 schema 所驗證的**每一個凍結研究 protocol**。原句說的「不 import 任何契約模組」對 12 個模組為真，對這一行為假。原句依先立後撤保留在上方。

[RESULT] **該行已於 2026-09-17 切斷**，並把邊界變成**被檢查的事實**：[`TEACHING-BOUNDARY-V1`](TEACHING_BOUNDARY.md)（登錄檔 `backend/teaching_boundary_registry.json`、契約 `backend/teaching_boundary_contract.py`）。規則是一條等式——教學進入點的遞移本地 import 閉包**必須恰好等於**已登錄的模組清單，兩個方向都失敗：研究模組跑進來會紅，登錄清單過期也會紅。現況 **15 個模組、4,943 行**，`train_ppo` 不在其中。`train_ppo.py` **逐位元未動**。（**2026-09-17 更正**：本段原寫契約 ID 為 `TEACHING-BOUNDARY-V1`、登錄檔 `backend/teaching_boundary_registry.json`、契約 `backend/teaching_boundary_contract.py`，原措辭依先立後撤保留。拆下方產品 B 時發現工具組邊界的規則與此**逐字相同**，因此改為多邊界的 [`MODULE-BOUNDARY-V1`](TEACHING_BOUNDARY.md)（[登錄檔](../backend/module_boundary_registry.json)、[契約](../backend/module_boundary_contract.py)），**程式只留一份**——再寫一份幾乎相同的契約，正是 §4.3 那個「同一個事實多份副本」的型態。教學邊界的規則、模組清單與上述量測結果一字未改。原路徑保留在上方，但已由連結改為純文字，因為指向的檔案不再存在。）

[RESULT] **產品 B 的邊界也已於 2026-09-17 變成被檢查的事實**，由**同一個契約**檢查：[TOOLKIT_PORTABILITY](TOOLKIT_PORTABILITY.md)。量到的是一個**不對稱**——工具組閉包**恰好是它自己那 7 個模組、5,300 行、本地相依為零**，而**13 個非測試專案模組 import 它**。它已經坐在相依圖的最底層，那正是函式庫該待的位置；契約的作用是讓它留在那裡。

[BLOCKER] **但「邊界乾淨」不等於「別人拿得走」，而下表把這兩件事混在同一格。** 2026-09-17 逐模組審計：7 個模組裡**只有 `exposure_identification` 今天可以原封不動使用**；`environment_lock` 可用但功能退化（三個重套件的 import **全部是惰性且包在 `try/except` 裡**，在 `python3 -I -S` 下實測可載入）；其餘 5 個被**平坦兄弟 import**、**封閉 `Literal` 詞彙**與**凍結的 producer 登錄檔**擋住。其中 `evidence_scope: Literal["SIM_ONLY_MUJOCO"]` 與 `FROZEN_CLAIM_BOUNDARY` 的逐字比對**不是疏忽，是這個專案不誇大主張的機制**，放寬它們是擁有者的決定，本次一個字都沒有動。逐項與建議見 [TOOLKIT_PORTABILITY §4–§8](TOOLKIT_PORTABILITY.md)。

[BLOCKER] **下表產品 B 的「~6.4k 行」與實測不符。** 2026-09-17 對表中列出的同一組 7 個檔案實測 `wc -l` 為 **5,300 行**。原數字依先立後撤保留在表中，本行為更正；產生原數字的計算方式未知，因此這裡只記錄重新量到的值與方法。

[BLOCKER] **本次沒有搬任何檔案。** §4.1 表格描述的「搬」仍未執行；本次做的是切斷耦合並讓邊界可驗證，使日後的搬移變成機械動作。仍未涵蓋的範圍見 [TEACHING_BOUNDARY §6](TEACHING_BOUNDARY.md)。

[RESULT] **產品 B 已於 2026-09-19 搬進 `backend/toolkit/`**（任務 #96，記錄見 [TOOLKIT_MOVE_2026-09-19](TOOLKIT_MOVE_2026-09-19.md)）。9 個檔案裡 **8 個逐位元未動**，`run_manifest_lock.py` 只改了 docstring 裡一條路徑；兩個邊界的閉包搬移前後**完全相同**。**產品 A 與產品 C 仍未搬。**

[BLOCKER] **「拆開不需要重構，只需要搬」這句話在搬下去之後要修正。** 真的搬了才看到三件事：（a）`module_boundary_contract` 把模組名對到 `package_root/<name>.py`，檔案一進子目錄，工具組內部的平坦兄弟 import 就不再被認成本地 import，**契約會照樣印綠燈而實際上已經瞎掉**——登錄檔因此新增 `module_search_path` 明講搜尋路徑；（b）`paired_statistics_contract.py:62` 以**子行程**啟動兄弟腳本 `paired_statistics_replay.py`，那是 AST 閉包**結構上看不到**的第八個檔案，搬移後 18 個測試立刻紅；（c）**五份凍結且 digest 釘死的檔案**（其中一份在保留證據裡）寫著工具組的舊路徑，改它們就等於破壞自己的 pin，因此那些路徑**永久停在舊值**。逐項見該記錄 §3–§5。

| 產品 | 內容 | 規模 | 對象 |
|---|---|---:|---|
| **A. 教學模擬器** | 核心 14 檔 + 前端 + v5/v2/legacy policy + `USAGE` 教學流程 + `MODEL_CARD` | ~10.4k 行 | 修課學生、教師 |
| **B. 可重現實驗工具組** | `environment_lock`、`run_manifest_lock`、`bind_run_lock`、`exposure_identification`、`paired_statistics_contract`、`experiment_matrix_contract`、`paper_data_contract` | ~6.4k 行 | 做 RL 評估的研究者 |
| **C. 研究線封存** | 已結案各線的 spec／protocol／contract／replay／bundle／receipt／evidence | ~15.8k 行 + 證據 | 論文附錄、審稿人 |

### 4.2 建議封存（不是刪除）的東西

證據規則不變：**任何已保留的證據不得刪除**。以下建議的是把**程式與文件**搬進 `archive/`（或獨立
repo），證據目錄原地不動、digest 不變。

| 搬什麼 | 行數 | 理由 |
|---|---:|---|
| v7 pilot／audit／selection 全套 | 8,638 | 來源不可重建、selection 永不可執行、pretraining variance 不可量測；三個下場都是終局 |
| second case runner／budget probe | 2,072 | 2026-09-09 由決定結案，兩個 protocol id 已撤回 |
| seed variance contract／replay／bundle builder | 3,034 | 由證據結案；結論（`UNMEASURABLE`）已寫進 receipt |
| tracked lineage V1／V2 contract／retention／runner | 1,661 | 兩線完成，標籤已由 runner 算出並保留為 JSON |
| R0 probe | 411 | 已執行 |
| 對應的 receipt／spec（約 25 份 md） | — | 移至 `docs/archive/`，README 只留一個索引連結 |

[RESULT] **文件部分已於 2026-09-20 執行（任務 #98），記錄見 [DOC_ARCHIVE](DOC_ARCHIVE_2026-09-20.md)。** 對應五條線的實際是 **20 份**（非 25）；**17 份搬入 `docs/archive/`，3 份搬不動**，`docs/` 由 73 降到 64。

[BLOCKER] **3 份 spec 結構性地搬不動。** 搬移必須改內部相對連結，改連結就改位元組，而 `TRACKED_LINEAGE_TRAINING_SPEC`、`TRACKED_LINEAGE_TRAINING_V2_SPEC`、`R0_REGIME_PROBE_SPEC` 的**內容 digest 被凍結 protocol 與凍結證據釘住**（`r0_probe_evidence/probe_result.json` 即為一例）。兩者不可兼得，因此退回原地、位元組還原。另有 7 份雖已搬，但原路徑必須留轉址。

[RESULT] **已於 2026-09-19 執行（任務 #97），記錄見 [RESEARCH_LINE_ARCHIVE](RESEARCH_LINE_ARCHIVE_2026-09-19.md)。** 22 個檔案進 `backend/archive/`，證據目錄與 digest 一個都沒動，文件依擁有者選的範圍留在 `docs/`。

[BLOCKER] **下面「測試會從 942 降到約 520」這個預期被刻意推翻了。** 實測：**搬移前後都是 1,062 個測試**。照原文讓測試停跑會停掉 **434** 個檢查，其中包含**三個沒有被封存的檔案**的不可變性 pin——`config_schema.py`、`motion_tasks.py`（皆教學閉包）與 `rl/eval_policy.py`（`immutable_sources` ＋ binding protocol 執行期解析的 producer）。封存的是位置，不是檢查。

[BLOCKER] **`v7_exposure_audit_contract.py` 搬不動。** 它 `:2009` 以 `with_name` 把 `motion_tasks.py` 當成自己的兄弟解析，而那是留下來的教學模組；改那一行就得重算 `training_seed_variance_contract.py:77` 的 pin，而那個 pin 存在的理由正是偵測它被改動。該組四個檔案因此留在 `backend/`，屬擁有者決定。

原文保留於下：

搬走後全套測試會從 942 降到約 **520**（移除 ~420 個測試函式對應的 case）。這不是損失——那些測試
測的是已經不會再改的程式。

### 4.3 建議修的東西

| 項目 | 現況 | 建議 |
|---|---|---|
| `STATUS.yaml` | 78 KB，單欄位數千字元的敘事字串 | 拆成結構化欄位；敘事移到 receipt |
| `CHANGELOG.md` | 110 KB，每個工作階段一條長條目 | 保留，但改為每個 PR 一段摘要；細節在 receipt |
| 文件數 | 63 份 | 活的規劃文件約 12 份留在 `docs/`，其餘進 `docs/archive/` 與 `docs/receipts/` |

[BLOCKER] **「約 12 份」達不到，這是量出來的。** 2026-09-20 執行時 `docs/` 裡已有 **11 份結構性搬不動**——4 份內容 digest 被凍結證據釘住的 spec，加上 §4.2 執行時為保住那些 pin 而留下的 7 份轉址。「12 份留在 `docs/`」等於只剩 1 個名額給真正的規劃文件。與「942 → 520」同類。

[RESULT] **已改為保守分流並執行（任務 #99）**：14 份實作 receipt 進 `docs/receipts/`，`docs/` 由 64 降到 **51**，spec 與計畫文件留在原地。記錄見 [DOC_ARCHIVE §8](DOC_ARCHIVE_2026-09-20.md)。
| v7 證據 | 222 MB 只在本容器 | **二選一**：依 REPOSITORY_GUIDE §3 放外部 immutable storage 並在 §4.1 註記；或在 PROJECT_STATUS 明寫「Pilot 欄不可從 repo 重導」（本次已加註後者） |
| V1 evaluations 的 `run_lock_label` | 五筆仍是佔位字串 `"see gate output"` | 用 `evaluate_relocated_run` 重導並回填，或維持並在 receipt 註明（現為後者） |
| **同一事實的多份副本** | 一個 gate 狀態散在 **8 份文件、24 處**；三天內量到 **4 次「改了一部分」**，第 4 次是寫本節時才量到的 | **已實作**（2026-09-17，`GATE-STATUS-SINGLE-SOURCE-V1`）：33 個 gate 各有唯一權威來源，54 個站點由 [`gate_status_contract`](../backend/gate_status_contract.py) fail-closed 比對。規範見 [GATE_STATUS_SINGLE_SOURCE](GATE_STATUS_SINGLE_SOURCE.md)；仍未涵蓋的見該文件 §5、§6 |

#### 4.3.1 文件副本不同步——這是量到的，不是推測

[RESULT] §1.6 說文件太多，當時的理由是「新人無法上手」。2026-09-14 至 09-16 的三次更新給了第二個、更硬的理由：**同一個事實在多份文件各有一份副本，更新時只會改到其中幾份。**

| # | 事實 | 已更新 | 漏掉 | 落差 | 修於 |
|---|---|---|---|---|---|
| 1 | tracked-lineage 兩線已於 2026-09-14 執行完畢 | V1／V2 兩份 receipt | `RESEARCH_EXECUTION_PLAN` 的 `P-NEW` 列仍寫 `NOT STARTED` | 2 天 | `ab4ac12` |
| 2 | **同 #1**（第二份副本） | 同上 | `PUBLICATION_PLAN` §5 仍寫「**尚未執行**」 | 2 天 | `0d43096` |
| 3 | `PUB-A0` 升為 `FOUR_VERIFIED_REMAINING_U` | 兩份文獻地圖、`TRACK_A_REFRAME` §8 gate 表 | `PUBLICATION_PLAN` §5 gate 表沒改 | 同日 | `0d43096` |
| 4 | Pardo 2018（`1712.00378`）已核對、`U` → `S` | `TRACK_A_REFRAME` §8、`LITERATURE_MAP_2026-09-08` §7／§1.1 | **三份文件的「優先四篇」清單仍把它列為待核對**：`TRACK_A_REFRAME` §10、`PROJECT_STATUS`、`PUBLICATION_PLAN` | 1 天 | PR #34 |

三件事讓這個型態比「文件過期」更嚴重：

- **#2 是 #1 的第二份副本。** 修掉第一份的那次更新沒有去找第二份，隔一次才發現。一個錯誤被修了兩次。
- **#3 是 AI 協作者自己漏的。** 同一批改動更新了兩個檔案、漏了第三個——即使當時正在做的就是「更新這個狀態」。
- **#4 是同一份文件內部互相矛盾。** `TRACK_A_REFRAME` §8 的 gate 列寫 `FOUR_VERIFIED`（Pardo 已核對），同一份文件 §10 的「唯一剩餘工作」卻仍把 Pardo 列為待讀。**一份文件對同一件事給出兩個答案。**

規模是可以量的：`PUB-A0` 這**一個** gate 的狀態出現在 **8 份文件、24 處**（`grep -o "PUB-A0" docs/*.md STATUS.yaml | wc -l`，量測於 `main@653f82d`，不含本文件）。任何一次狀態變更都要同步 24 處，而**沒有任何機制會在漏改時報錯**——契約程式碼有 fail-closed gate，文件沒有。

[INFERENCE] 這讓文件精簡從「可讀性建議」變成**正確性問題**：63 份文件不只是難讀，它們**會彼此矛盾，而矛盾不會被任何測試抓到**。最小處置不是刪文件，而是讓每個 gate 狀態只有一個權威來源，其餘文件放連結而不放狀態字串；這樣一次變更只有一處要改，漏改在結構上就不可能發生。

[RESULT] **2026-09-17 已實作**，`GATE-STATUS-SINGLE-SOURCE-V1`（[規範](GATE_STATUS_SINGLE_SOURCE.md)、[登錄檔](../backend/gate_status_registry.json)、[契約](../backend/gate_status_contract.py)）。33 個 gate、54 個站點：`PUB-*` 的權威是 [PUBLICATION_PLAN](PUBLICATION_PLAN.md) §5、`PDR-*` 是 [PAPER_DATA_READINESS](PAPER_DATA_READINESS.md)、`V0`–`V4` 是 [PROJECT_STATUS §1](PROJECT_STATUS.md)；其餘 21 處登錄為 mirror 並逐一比對，不一致即測試失敗。**上面四個實例都已在測試中重演並確認會被擋下。**

[BLOCKER] **實作過程推翻了本節原本的建議措辭。** 原文寫「其餘文件只放連結與一句話摘要，不複製狀態字串」——實際量測後改為**保留各文件自己的措辭、改為登錄與比對**，理由有二：（a）同一狀態在不同文件本來就有不同但正確的寫法（`PARTIAL_IMPLEMENTED_NOT_PASS` 對 `PARTIAL IMPLEMENTED / NOT PASS`、`SOFTWARE CONTRACT PARTIAL` 對 `SOFTWARE PARTIAL`），強制統一等於為了工具去改本來就正確的文件；（b）以整列比對會產生 **11 個假陽性**——鄰欄的 `readback PASS`、`16/14 exact` 說的是子項而非 gate。契約因此改讀「狀態格開頭」。原措辭依先立後撤留在上一段。

[BLOCKER] **涵蓋範圍不是全部，缺口逐項寫在 [GATE_STATUS_SINGLE_SOURCE §5、§6](GATE_STATUS_SINGLE_SOURCE.md)**：`VV_PLAN` 的逐項 requirement 列（單一來源，無副本）、receipt-bound 的凍結判準（不得改寫）、以及**上表第 4 例那一類**——「Pardo 已核對」不是 gate 狀態而是衍生清單與文獻等級的一致性，需要另一個裝置，**目前沒有做**。

[RESULT] **2026-09-17 第 4 例那一類也做了**：[`DERIVED-CLAIM-CONSISTENCY-V1`](DERIVED_CLAIM_CONSISTENCY.md)。上一段的「目前沒有做」依先立後撤留在原處。追蹤 10 篇論文的核實等級、1 個衍生 claim、3 個站點，六條規則中最有力的是 `NO_VERIFIED_PAPER_NAMED`——清單裡出現**任何**已核實的論文即失敗，**不依賴有人記得更新成員名單**；另有 scan 規則擋下「第五份副本長出來」。上表四個實例現在**全部**有機制擋著。

[BLOCKER] 仍未涵蓋的，寫在 [DERIVED_CLAIM_CONSISTENCY §6](DERIVED_CLAIM_CONSISTENCY.md)：地圖 §4 的 gap 判定與 claim→evidence 對照表。那是對整份地圖的**判斷**，不是一條規則能重算的清單；等級變動時仍須重新論證。

[RESULT] **#4 已於 2026-09-17 由專案負責人指示修掉**（PR #34）：三份文件的清單改為「優先三篇」，各自以 `[BLOCKER]` 保留原清單供對照並指出矛盾所在；`PROJECT_STATUS` 另補上它從未記錄的 `FOUR_VERIFIED_REMAINING_U` 狀態與 2026-09-16 那一列時間線。**本節初稿寫的是「本次不修」**——那個判斷（改 gate 狀態屬規劃文件職權）在提出時是保守的預設，負責人決定後即執行；依先立後撤，原判斷留在此處。

[BLOCKER] **修掉 #4 並不使這一節失效，反而是它的第一個驗證**：四個實例裡，沒有任何一個是被機制抓到的——#1／#2 是下一次更新順手發現、#3 是事後盤點、#4 是寫這一節查證時才量到。**三個都靠人（或 AI）碰巧回頭看。** 只要狀態字串還有 24 份副本，第 5 次就只是時間問題。

### 4.4 不建議動的東西

- **任何 protocol JSON、spec 的凍結內容、已保留的證據。** 這是專案最值錢的紀律，拆封存不是重寫。
- **`environment_lock` + `run_manifest_lock`。** 這是活的、可重用的、而且是本專案對其他人最有用的一件東西。
- **v5 policy artifact。** 它是唯一會走的 policy，教學示範靠它。
- **30/30 的門檻與 2,000,000 步的上限。** 凍結後不得因結果調整，這條規則本身就是成果的一部分。

---

## 5. 下一步：三個選項，代價寫清楚

這三個選項**不互斥**，但順序有意義。

### 選項 一：收斂——把兩個好東西各自做完

1. 拆出教學模擬器（§4.1 A），清一份 30 分鐘能上手的 README。
2. 拆出實驗工具組（§4.1 B），補一份「如何在你自己的 RL 專案用 environment lock + run manifest binding」。
3. 寫 Track A 那篇論文：`PUB-A2` claim freeze 的輸入全部在手（v7 audit、Walker2d、R0 probe、tracked lineage 兩線都是 censoring 的實例）。**不需要 `PUB-B2`。**
4. 其餘封存（§4.2）。

代價：放下「機器人從零學會走」這個目標。收穫：三個月內有一個可用教具、一個可重用工具、一篇投得出去的論文。

### 選項 二：修機器人——但換槓桿，不加預算

依 §1.4 的診斷開新 protocol（V3），揭露它知道 V1、V2 的結果，且**改變的是獎勵結構或 curriculum，
不是預算**。最直接的候選：以 v5 的行走 checkpoint 為 curriculum 階段起點（tracked warm start，V1 §3
當初排除它是因為 v5 的訓練過程不可重建——但 v5 的**檔案**可由 digest 重建，作為「起點」而非「證據」
是可以據實揭露的）。

代價：再一輪 5 replicate × 訓練 + 評估（約 3 小時），且結果可能仍是 `NOT_ATTAINED`。收穫：若成功，
`PUB-B2` 達成、V1 §3 的 `CONDITIONAL_ON_FIXED_WARM_START` 有了可重建的替代。**但請先問 §3 的問題：
有哪個研究目標在等這個結果？**

### 選項 三：維持現狀

繼續每條線一套 spec／protocol／contract／receipt。這是唯一**不建議**的選項：外衣會繼續以核心 4 倍的
速度長大，而每次新的工作階段要先讀 700 KB 文件才能開始。

---

## 6. 本次盤點順手修正的事實

- REPOSITORY_GUIDE：`tracked_lineage_evidence` 由「尚未建立」改為實測 40 個 checkpoint、77 MB；測試數 923 → 941。
- PROJECT_STATUS §4：加註 v7 pilot 欄與 audit 發現的資料**不在版控**（依 REPOSITORY_GUIDE §3 政策），seedvar 欄可重導。
- 本文件的兩個工作假設在查核後被推翻並照實記錄：「有死碼」（沒有）、「跌倒懲罰只有 −5」（是 −50）。

---

## 7. 相關文件

| 文件 | 關係 |
|---|---|
| [PROJECT_STATUS](PROJECT_STATUS.md) | 逐 gate 的現況；本文件是它的**判斷層** |
| [PUBLICATION_PLAN](PUBLICATION_PLAN.md)、[TRACK_A_REFRAME](TRACK_A_REFRAME_2026-09-09.md) | §3 的論證依據 |
| [TRACKED_LINEAGE_TRAINING_V2_RECEIPT](archive/TRACKED_LINEAGE_TRAINING_V2_RECEIPT_2026-09-14.md) | §1.3、§1.4 的量測來源 |
| [REPOSITORY_GUIDE](REPOSITORY_GUIDE.md) | §1.5 引用的證據儲存政策 |
| [USAGE §6](USAGE.md) | 教學流程，§2 教學價值的依據 |
