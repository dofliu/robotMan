# 學術產出規劃

最後更新：2026-09-08 ｜ ID：`PUBLICATION-PLAN-V1`

狀態：`PLAN_FROZEN_V1 / NO_MANUSCRIPT / paper_data_ready=false`

本文件規劃專案的學術產出：哪幾篇論文有可能、各自需要什麼證據、以什麼順序做、什麼不能宣稱。它與工程路線 [ROADMAP](ROADMAP.md) 平行；與研究問題設計 [RESEARCH_EXECUTION_PLAN](RESEARCH_EXECUTION_PLAN.md) 及資料架構 [PAPER_DATA_READINESS](PAPER_DATA_READINESS.md) 的關係是：那兩份定義**資料怎麼產生才可信**，本文件定義**哪些論文能從可信的資料寫出來**。

規則與其他 spec 相同：每個 gate 都是 fail-closed；未通過的 gate 不能靠敘述繞過；狀態只能由 receipt 推進。

## 0. 一句話結論

現在**寫得出一篇論文，但不是原本 §6 Study A 那篇**。手上最強的資產是評估效度與可重現性的方法論發現，不是機器人控制結果。建議先寫 Track A；它不浪費 Track B，反而讓 Track B 的資料成為它應有的角色 —— pilot。

## 1. 為什麼原定的 Study A 現在寫不出來

[PAPER_DATA_READINESS §6](PAPER_DATA_READINESS.md) 的 primary RQ 是「action interface／observability 設計是否改善 `stand → start → steady walk → stop` 的成功率與 saturation behavior」。它卡在兩個**結構性**、不是算力的問題：

1. **Provenance 已永久損毀。** v5 warm start 來自 gitignored 的 v4 artifact，v3/v4 不存在於 repo 或磁碟，v5 profile 與 registry 對 warm start 和 budget 互相矛盾。因此 `CONDITIONAL_ON_FIXED_WARM_START` 對整條 v7 line 永久成立（[receipt](V7_PRETRAINING_SEED_VARIANCE_INFEASIBILITY_RECEIPT_2026-09-08.md)）。任何 method-level 優越性主張永遠附帶「條件於一個無法重建的起點」。
2. **變異被 censoring 封死。** `between_replicate_sd` 為 null，因為每個 replicate 都有 exposure censoring，sample SD 沒有定義在 interval 上。沒有變異就沒有 sample size，就沒有 formal design。而要點識別變異，連 reference arm 都必須穩定跑完 9 s 任務 —— v5 line 做不到（V7A 143/150 full exposure；Live saturation duty `38.42% > 30%`）。

[INFERENCE] 所以 Study A 的真正代價不是「3 arms × N seeds」的訓練時間，而是**一條全新、有版控 lineage、且 reference policy 可靠完成任務的訓練線**，加上 V1 plant credibility、actual matrix、binary paired CI 的 golden-case oracle、formal authorization 與 external preregistration。那是數個月等級，且結束後仍不能宣稱 sim-to-real。

## 2. 三條 track

| Track | 論文類型 | 主要證據來源 | 目前狀態 | 建議順序 |
|---|---|---|---|---|
| **A** | 評估效度／可重現性方法論 | 已有的 audit、seed-variance、environment-lock receipts | 證據齊備；novelty 待核實；缺第二案例 | **第一** |
| **B** | Study A：action-interface 方法比較 | 尚不存在的新訓練線 + FORMAL data | 結構性 blocked | 第二（前置在工程路線） |
| **C** | 教學／篩選工具 | 平台本身 + 尚不存在的學習成效資料 | UI 未驗證；無學生資料 | 視教學規劃另議 |

### 2.1 Track A —— 評估效度與可重現性方法論

**可主張的貢獻（依 [LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY §4](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md) 的暫定 gap 判定）：**

- **A-C1（主）** Early termination 作為 rate 型 outcome 的 **exposure censoring**：在 comparative evaluation 中以 assumption-free identification bounds 處理，拒絕 complete-case deletion 與 interval 補值，並把 method failure 與 exposure censoring 分開保留。實測案例：V7C 表面 `-36` pp 的「改善」，bound 含 0、0/30 與 0/5 sign-identified；跨 5 個獨立 seeds 重現。
- **A-C2（主）** 記錄層盲點：`outcome_state == OBSERVED` 不蘊含 full exposure。V7B 三個 censored episode 六項 required numeric 齊全、算術正常。可移植的檢查：由 trace 長度獨立重建 exposure，不信任 outcome flag。
- **A-C3（artifact）** Statistical unit 的程式層強制（forbidden denominators）、`NOT_REACHED ≠ PASS` 的 fail-closed 契約、`python -I -S` stdlib-only exact replay。
- **A-M（動機，不是貢獻）** 同環境兩種 IEEE-conformant reduction order 給不同結果；版本 pin 不足以重驗數值。文獻已建立此事（SC'24、RepDL），只作動機。
- **A-C4（次，待另做 scan）** 公開宣告非預註冊、且在啟發資料上必須失敗的 selection rule 自檢。

**不能主張：** 任何關於 plant 真實性、controller 優劣、action interface 的一般性效果、sim-to-real。Track A 對機器人**什麼都不說**，只對量測程序說話。

**已知弱點：**

- n=1 case study：單一 plant、單一 task。→ `PUB-A1` 第二案例是硬需求。
- Novelty 未經原文核對（執行環境封鎖出版方 host）。→ `PUB-A0` 未通過。
- Manski 型 bound 只用了最弱版本；審稿人可能要求討論 monotonicity 等收窄假設 —— 應主動說明為何本專案**拒絕**加假設。
- 沒有 external preregistration；只能稱 internal hash freeze。

**Venue 類別（不指定期刊）：** RL／ML 評估與可重現性 workshop；robotics 評估方法論；simulation credibility／V&V（NASA-STD-7009B 系）；統計方法在 ML 中的應用。

### 2.2 Track B —— Study A 方法比較

**可主張（在全部 gate 通過後）：** 在凍結 MuJoCo plant 與固定 motion task 下，指定 action-interface 設計對 saturation duty、task success、fall rate 的 simulation-only 效果，附 paired interval、run-level distribution 與 failure strata。

**硬前置（皆未完成）：** 有版控 lineage 的新訓練線；reference policy 在 DEV seeds 上達到凍結的 full-exposure 比例；pilot variance → preregistered N；V1 plant credibility；formal authorization；OSF preregistration；binary paired CI golden-case oracle；actual matrix。

**現有 v7 證據在 Track B 中的角色：** pilot。不得重新標記為 formal replicates；不得與新線的數值相減或並排成趨勢（`cross_protocol_comparability = NON_VERIFIABLE_ENVIRONMENT`）。

### 2.3 Track C —— 教學／篩選工具

**可主張（在 gate 通過後）：** 平台作為 SIM-only 教學工具在指定學習目標上的效果。

**硬前置：** UI 的 browser visual verification 與 dedicated tests（目前 `BROWSER_VISUAL_PENDING`、`PROTOTYPE_FEATURES_PRESENT_UNVERIFIED`）；學習成效研究設計；研究倫理審查；學生資料。**沒有學生資料就沒有教學論文**，只有 tool description。

## 3. Publication gates

狀態值：`NOT_STARTED`、`IN_PROGRESS`、`BLOCKED`、`PASS`。任一 gate 非 `PASS`，其下游 gate 不得開始寫作以外的動作；寫作可提前，投稿不可。

### 3.1 Track A

| Gate | Exit condition | 狀態 | 備註 |
|---|---|---|---|
| `PUB-A0` Novelty | 文獻地圖中所有 `U` 條目經原文核對改為 `[SOURCE]` 或刪除；§4 gap 判定重寫並仍成立 | `IN_PROGRESS` — `SCAN_COMPLETE / PRIMARY_SOURCES_UNVERIFIED` | 需可存取出版方的環境。關鍵兩篇：arXiv 2606.10229、1911.05728 |
| `PUB-A1` Second case | 在第二個 task／公開 benchmark 上，以**凍結的** protocol 重現 exposure-censoring artifact，含 receipt 與 stdlib-only replay | `NOT_STARTED` | 候選：Gymnasium MuJoCo Humanoid／Walker2d + SB3 PPO；protocol 必須在跑之前凍結並記錄預期 |
| `PUB-A2` Claim freeze | A-C1..A-C4 每一條都能只由 hash-bound receipts 推出；figure／table 清單凍結；不可宣稱清單寫入稿件 | `NOT_STARTED` | 依賴 A0、A1 |
| `PUB-A3` Reproduction | clean checkout 以 `python -I -S` 重建稿件每一張 table／figure 的輸入；受 `ENVIRONMENT-LOCK-V1` record 比對 | `NOT_STARTED` | 現有 replay 已覆蓋大部分；缺 formal clean-checkout 一次性執行 |
| `PUB-A4` Internal review | 至少一輪對抗式內部審查（含統計與 RL 評估兩個視角），所有 blocking 意見有回應 | `NOT_STARTED` | |
| `PUB-A5` Submission | venue 選定；preprint 與 code／receipt archive 帶 DOI | `NOT_STARTED` | |

### 3.2 Track B

| Gate | Exit condition | 狀態 |
|---|---|---|
| `PUB-B0` Authorization decision | 專案負責人書面決定：授權 formal evaluation 於現行 `SELECT-V7-CANDIDATE-FORMAL-V1`，或改為 preregister 新規則 | `BLOCKED` — 等決策 |
| `PUB-B1` Tracked training line | 新線每個 checkpoint 與 warm start 進版控或 immutable storage；lock record 綁進 run manifest | `NOT_STARTED` |
| `PUB-B2` Reliable-completion baseline | reference policy 在 DEV seeds 上達到**事先凍結**的 full-exposure 比例 | `NOT_STARTED` |
| `PUB-B3` Pilot variance → N | point-valued between-replicate SD；N 由 power analysis 決定並寫進 preregistration；不得事後上調 | `BLOCKED` by B2 |
| `PUB-B4` External preregistration | OSF（或同級）time-stamped、read-only 登錄；**在解封 FORMAL seeds 之前** | `NOT_STARTED` |
| `PUB-B5` Plant credibility | V1 articulated dynamic／pendulum／energy／solver convergence PASS | `IN_PROGRESS`（見 ROADMAP §4） |
| `PUB-B6` Study execution | actual matrix；binary paired CI 有 golden-case oracle；所有 FAILED／CENSORED 保留 | `BLOCKED` |
| `PUB-B7` Manuscript | 同 A2–A5 | `NOT_STARTED` |

### 3.3 Track C

| Gate | Exit condition | 狀態 |
|---|---|---|
| `PUB-C0` UI verified | browser visual verification + dedicated UI tests PASS | `NOT_STARTED` |
| `PUB-C1` Study design + ethics | 學習目標、量測工具、對照設計、倫理審查 | `NOT_STARTED` |
| `PUB-C2` Data | 學生資料收集完成 | `NOT_STARTED` |
| `PUB-C3` Manuscript | 同 A2–A5 | `NOT_STARTED` |

## 4. 執行順序與相依

```text
現在 ──► PUB-A0 原文核對（需校內網路）
     ├─► PUB-A1 凍結第二案例 protocol → 執行 → receipt
     │        └─► PUB-A2 → A3 → A4 → A5          ← Track A 投稿
     │
     ├─► PUB-B0 授權決策（專案負責人）
     │        └─► PUB-B4 OSF preregistration ──┐
     │                                          ├─► 解封 EP-01/EP-02 ──► PUB-B6
     ├─► PUB-B1 新訓練線（工程 ROADMAP §9 第 2 項）│
     │        └─► PUB-B2 → PUB-B3 ─────────────┘
     └─► PUB-B5 V1（工程 ROADMAP §9 第 4 項）
```

**Track A 不浪費 Track B：** A1 的第二案例 protocol 就是 B 的 exposure audit 在新 task 上的第一次演練；A 的 reproduction package 就是 B 的。

**順序不可反：** `PUB-B4` 必須在解封 sealed seeds `20000–20029` 之前。授權在前、預註冊在中、解封在後。

## 5. 專案負責人需要做的決定

只有一個，且只有負責人能做：

> **是否授權 formal evaluation？若是，用現行的、公開宣告非預註冊的 `SELECT-V7-CANDIDATE-FORMAL-V1`，還是先在 OSF 預註冊一條替代規則？**

- 用現行規則：較快；論文必須寫明規則是在看過 DEV 結果後設計的，並附 [rule self-check](V7_CANDIDATE_SELECTION_IMPLEMENTATION_RECEIPT_2026-09-08.md) 的失敗證據。
- 先預註冊替代規則：較慢；換來一條不需要揭露段落就能站住的規則。

本計畫的建議是後者，前提是時程允許。但這是研究策略決定，不是技術決定。

## 6. 寫作規範

1. **Evidence labels 進稿件。** 每個數字必須能回指到一個 receipt SHA-256；稿件附錄列出 receipt 清單與 hash。
2. **不可宣稱清單**（來自 `STATUS.yaml.prohibited_claims`，任一 track 皆適用）：physical hardware feasibility、safety or certification、validated actuator selection、measured push recovery、sim-to-real performance、general controller superiority。
3. **Preregistration 用語。** 只有 OSF（或同級 registry）登錄才可寫 "preregistered"；repo 內的 hash freeze 只可寫 "internally frozen before execution"；`SELECT-V7-CANDIDATE-FORMAL-V1` 必須寫 "post hoc, disclosed"。
4. **DEVELOPMENT 資料的用語。** v2–v7 的一切都是 development evidence；稿件中不得稱為 experiment、trial 或 replicate（除 seed-variance 的 5 個 training replicates，且須附 `CONDITIONAL_ON_FIXED_WARM_START`）。
5. **Interval 不是點。** 任何 partially identified 的量只報 bound，不報 midpoint，不報 "approximately"。
6. **失敗照登。** V7C 的崩潰、V7B 的 negatives、v6 的 negative control、`PRIMARY_CASE_RECEIPT_IDENTITY` 的紅測試都是結果，不是附錄註腳。
7. **限制段落先寫。** 每篇稿件的 Limitations 在 Introduction 之前起草，並在 claim freeze 時凍結。

## 7. 與工程路線的交會點

| 工程項目（ROADMAP §9） | 同時解除的 PUB gate |
|---|---|
| lock record 綁進 run manifest | A3、B1 |
| 有版控 lineage 的新訓練線 | B1、B2 |
| browser visual verification | C0 |
| V1 dynamic／pendulum／energy | B5 |
| binary paired CI golden-case oracle | B6 |

## 8. 立即下一步

1. **`PUB-A0`**：在可存取出版方的環境讀 [LITERATURE_MAP §4](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md) 點名的兩篇與 §1.2–§1.4 的 `U` 條目；更新地圖。
2. **`PUB-A1`**：凍結第二案例 protocol（task、policy、seeds、rate 型 outcome、預期的 artifact 方向、acceptance）；凍結後才跑。
3. **`PUB-B0`**：專案負責人決策（§5）。
4. 工程：ROADMAP §9 第 1、2 項並行。
