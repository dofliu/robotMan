# 學術產出規劃

最後更新：2026-09-10 ｜ ID：`PUBLICATION-PLAN-V3`（V1：2026-09-08；V2：2026-09-09；版本紀錄見 §9）

狀態：`PLAN_REVISED_V3 / NO_MANUSCRIPT / paper_data_ready=false`

V2 的唯一實質變更是 Track A：專案負責人於 2026-09-09 決定停止第二案例 V2 線，Track A 依 [TRACK_A_REFRAME_2026-09-09](TRACK_A_REFRAME_2026-09-09.md) 重構為「censoring regime 的評估效度研究」；`PUB-A1` 拆為 A1a（PASS）與 A1b（CLOSED_NOT_ATTAINED）。

V3 的唯一實質變更是 Track B 的 `PUB-B0`：專案負責人於 2026-09-10 授權 formal evaluation（[PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10](PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10.md)）。授權**只解除凍結順序中的第一格**——`PUB-B4` 外部預註冊仍在解封 sealed seeds 之前，且該 receipt 量測出在 v7 線上 `SEL-C2` 幾乎確定不成立。§5 因此從「一個決定」改為「已授權 + 兩個尚未決定的子問題」。Track A、Track C 與 §6–§7 不變。

本文件規劃專案的學術產出：哪幾篇論文有可能、各自需要什麼證據、以什麼順序做、什麼不能宣稱。它與工程路線 [ROADMAP](ROADMAP.md) 平行；與研究問題設計 [RESEARCH_EXECUTION_PLAN](RESEARCH_EXECUTION_PLAN.md) 及資料架構 [PAPER_DATA_READINESS](PAPER_DATA_READINESS.md) 的關係是：那兩份定義**資料怎麼產生才可信**，本文件定義**哪些論文能從可信的資料寫出來**。

規則與其他 spec 相同：每個 gate 都是 fail-closed；未通過的 gate 不能靠敘述繞過；狀態只能由 receipt 推進。

## 0. 一句話結論

現在**寫得出一篇論文，但不是原本 §6 Study A 那篇**。手上最強的資產是評估效度與可重現性的方法論發現，不是機器人控制結果。建議先寫 Track A；它不浪費 Track B，反而讓 Track B 的資料成為它應有的角色 —— pilot。

V2 補一句：Track A 的論點不再是「在公開 benchmark 上重現 v7 的 artifact」，而是「comparative evaluation 落在哪一種 censoring regime 決定 bound 是否有資訊、artifact 是否可能出現，而該 regime 由 budget／recipe／plant 決定、通常不被控制也不被報告」。v7 的不對稱案例、Walker2d 的對稱案例、三個公開 benchmark 上的 pilot，合起來是五種 regime 的實例（[TRACK_A_REFRAME §3](TRACK_A_REFRAME_2026-09-09.md)）。

## 1. 為什麼原定的 Study A 現在寫不出來

[PAPER_DATA_READINESS §6](PAPER_DATA_READINESS.md) 的 primary RQ 是「action interface／observability 設計是否改善 `stand → start → steady walk → stop` 的成功率與 saturation behavior」。它卡在兩個**結構性**、不是算力的問題：

1. **Provenance 已永久損毀。** v5 warm start 來自 gitignored 的 v4 artifact，v3/v4 不存在於 repo 或磁碟，v5 profile 與 registry 對 warm start 和 budget 互相矛盾。因此 `CONDITIONAL_ON_FIXED_WARM_START` 對整條 v7 line 永久成立（[receipt](V7_PRETRAINING_SEED_VARIANCE_INFEASIBILITY_RECEIPT_2026-09-08.md)）。任何 method-level 優越性主張永遠附帶「條件於一個無法重建的起點」。
2. **變異被 censoring 封死。** `between_replicate_sd` 為 null，因為每個 replicate 都有 exposure censoring，sample SD 沒有定義在 interval 上。沒有變異就沒有 sample size，就沒有 formal design。而要點識別變異，連 reference arm 都必須穩定跑完 9 s 任務 —— v5 line 做不到（V7A 143/150 full exposure；Live saturation duty `38.42% > 30%`）。

[INFERENCE] 所以 Study A 的真正代價不是「3 arms × N seeds」的訓練時間，而是**一條全新、有版控 lineage、且 reference policy 可靠完成任務的訓練線**，加上 V1 plant credibility、actual matrix、binary paired CI 的 golden-case oracle、formal authorization 與 external preregistration。那是數個月等級，且結束後仍不能宣稱 sim-to-real。

## 2. 三條 track

| Track | 論文類型 | 主要證據來源 | 目前狀態 | 建議順序 |
|---|---|---|---|---|
| **A** | 評估效度／可重現性方法論（V2：censoring regime） | audit、seed-variance、environment-lock、Walker2d 第二案例 receipts；三個 budget probe（pilot） | 證據齊備於兩個 plant；`PUB-A1a` PASS、`PUB-A1b` CLOSED_NOT_ATTAINED；novelty 待核實 | **第一** |
| **B** | Study A：action-interface 方法比較 | 尚不存在的新訓練線 + FORMAL data | 結構性 blocked | 第二（前置在工程路線） |
| **C** | 教學／篩選工具 | 平台本身 + 尚不存在的學習成效資料 | UI 未驗證；無學生資料 | 視教學規劃另議 |

### 2.1 Track A —— 評估效度與可重現性方法論（V2：censoring regime）

完整的論點、regime 分類、claim → evidence 對照與 figure／table 計畫見 [TRACK_A_REFRAME_2026-09-09](TRACK_A_REFRAME_2026-09-09.md)；本節只列貢獻與邊界。

**可主張的貢獻（依 [LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY §4](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md) 的暫定 gap 判定）：**

- **A-C1（主）** Early termination 作為 rate 型 outcome 的 **exposure censoring**：在 comparative evaluation 中以 assumption-free identification bounds 處理，拒絕 complete-case deletion 與 interval 補值，並把 method failure 與 exposure censoring 分開保留。實測案例：v7 V7C 表面 `-36` pp 的「改善」，bound 含 0、0/30 與 0/5 sign-identified，跨 5 個獨立 seeds 重現（regime R1）；Walker2d-v5 上 naive `−28.795138` pp、t-interval 排除 0，θ `[−79.118, +55.913333]` 含 0（regime R3）；v7 V7B 的 θ `[−13.503408, −12.435259]` 排除 0、5/5 可識別，顯示 bound 在輕度 censoring 下**有資訊**（regime R2）。兩個 plant、兩個 policy 家族、三種 regime。
- **A-C2（主）** 記錄層盲點：`outcome_state == OBSERVED` 不蘊含 full exposure。v7 pilot 三個 censored episode 六項 required numeric 齊全；Walker2d 284/284 early-terminated episode 皆 `OBSERVED`。可移植的檢查：由 trace 長度獨立重建 exposure，不信任 outcome flag。**已有第二個 plant 的證據。**
- **A-C3（主，V2 新增）** Censoring regime 是 comparative evaluation 未被控制、未被報告的設計變數：bound 是否有資訊、artifact 是否可能出現由它決定；reference-adequacy 前置條件必須同時檢查 exposure 與 primary measurement 非退化（exposure-only 規則可選出 artifact 在數學上不可能出現的 reference，[TRACK_A_REFRAME §3.6](TRACK_A_REFRAME_2026-09-09.md)）；方向可識別 ≠ 變異可估計。證據：R1–R3 的凍結 protocol 量測 + 三個 probe（**pilot**，只陳述程序 outcome 與規則觀察）。
- **A-C4（artifact）** Statistical unit 的程式層強制（forbidden denominators）、`NOT_REACHED ≠ PASS` 的 fail-closed 契約、`python -I -S` stdlib-only exact replay、freeze-before-execute、probe 作為 pilot 的紀律（上限不事後提高、seeds 對下游為禁區、pilot 不得為 evidence）。
- **A-C5（2026-09-10 降為 artifact 級，併入 A-C4）** 公開宣告非預註冊、且在啟發資料上必須失敗的 selection rule 自檢。補充 scan 完成後判定縮小（[LITERATURE_MAP §1.7、§4 第 5 點](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md)）：「透明宣告 post hoc」是 Hollenbeck & Wright (2017) 的 **Tharking**，「決策資料未被檢視」是 Cawley & Talbot (2010) 與 Dwork et al. (2015) 已建立的事；剩下只有「把 negative-control falsification test 套在 **selection rule** 上」這一窄點，且其解讀受「規則選不出東西可能只因該資料 exposure 不足」的混淆。**不再單獨作為主張**，改為 A-C4 的一項 artifact 並如實寫出解讀限制。
- **A-M（動機，不是貢獻）** 同環境兩種 IEEE-conformant reduction order 給不同結果；版本 pin 不足以重驗數值。文獻已建立此事（SC'24、RepDL），只作動機。

**不能主張：** 任何關於 plant 真實性、controller 優劣、action interface 或 low-pass filter 的一般性效果、sim-to-real。**也不能主張 v7 的不對稱 artifact 在公開 benchmark 上重現**——這是 V2 明文放棄的主張，成為稿件 Limitations 第一條。Probe 資料不得用於任何關於 Walker2d／Hopper／PPO recipe 能力的陳述（其凍結 claim boundary 只支持 budget 選擇）。Track A 對機器人**什麼都不說**，只對量測程序說話。

**已知弱點：**

- R1（不對稱 regime）只在本專案 humanoid plant 上量到，且該 line 永久 `CONDITIONAL_ON_FIXED_WARM_START`；公開 benchmark 上只有 R3 的凍結量測與 R4／R5 的 pilot。
- Novelty：§4 點名的兩篇關鍵文獻已於 2026-09-09 全文核對，gap 仍成立（[LITERATURE_MAP §7](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md)）；其餘條目未經原文核對（執行環境封鎖出版方 host）。→ `PUB-A0` 未通過。
- Manski 型 bound 只用了最弱版本；審稿人可能要求討論 monotonicity 等收窄假設 —— 應主動說明為何本專案**拒絕**加假設。
- 沒有 external preregistration；只能稱 internal hash freeze。第二案例 protocol 是在 v7 結果已知後寫的。
- rl-zoo recipe 數值 `U_VERIFIED_FROM_MEMORY`。

**Venue 類別（不指定期刊）：** RL／ML 評估與可重現性 workshop；robotics 評估方法論；simulation credibility／V&V（NASA-STD-7009B 系）；統計方法在 ML 中的應用。

### 2.2 Track B —— Study A 方法比較

**可主張（在全部 gate 通過後）：** 在凍結 MuJoCo plant 與固定 motion task 下，指定 action-interface 設計對 saturation duty、task success、fall rate 的 simulation-only 效果，附 paired interval、run-level distribution 與 failure strata。

**硬前置：** 有版控 lineage 的新訓練線；reference policy 在 DEV seeds 上達到凍結的 full-exposure 比例；pilot variance → preregistered N；V1 plant credibility；OSF preregistration；binary paired CI golden-case oracle；actual matrix —— 以上皆未完成。formal authorization 已於 2026-09-10 取得（§5），但 protocol 仍不可執行。

**現有 v7 證據在 Track B 中的角色：** pilot。不得重新標記為 formal replicates；不得與新線的數值相減或並排成趨勢（`cross_protocol_comparability = NON_VERIFIABLE_ENVIRONMENT`）。

### 2.3 Track C —— 教學／篩選工具

**可主張（在 gate 通過後）：** 平台作為 SIM-only 教學工具在指定學習目標上的效果。

**硬前置：** UI 的 browser visual verification 與 dedicated tests（目前 `BROWSER_VISUAL_PENDING`、`PROTOTYPE_FEATURES_PRESENT_UNVERIFIED`）；學習成效研究設計；研究倫理審查；學生資料。**沒有學生資料就沒有教學論文**，只有 tool description。

## 3. Publication gates

狀態值：`NOT_STARTED`、`IN_PROGRESS`、`BLOCKED`、`PASS`。任一 gate 非 `PASS`，其下游 gate 不得開始寫作以外的動作；寫作可提前，投稿不可。

### 3.1 Track A

| Gate | Exit condition | 狀態 | 備註 |
|---|---|---|---|
| `PUB-A0` Novelty | 文獻地圖中所有 `U` 條目經原文核對改為 `S` 或刪除；§4 gap 判定重寫並仍成立 | `IN_PROGRESS` — `KEY_TWO_VERIFIED_AND_A_C5_SCANNED / REMAINING_U` | 關鍵兩篇 arXiv 1911.05728、2606.10229 已由專案負責人提供 PDF 並全文核對（2026-09-09，[LITERATURE_MAP §7](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md)）：前者為 conditionally independent censoring + imputation 的點估計（bounds 為 regret／rate），後者為 curation metric 的設計期 common-prefix truncation、未涉及 policy evaluation——兩個「gap 縮小／消失」條件皆不成立。A-C5 的 preregistration／multiverse 補充 scan 已於 2026-09-10 完成（[§1.7](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md)），結果是**縮小主張**：A-C5 降為 artifact 級併入 A-C4。其餘 `U` 條目需可存取出版方的環境（2026-09-10 重新量測 `arxiv.org` 仍封鎖） |
| `PUB-A1a` 第二 plant 的機制證據 | 至少一條主貢獻在非專案 plant 上以**凍結的** protocol 取得 receipt 與 stdlib-only replay | **`PASS`** | [execution receipt](SECOND_CASE_EXPOSURE_CENSORING_EXECUTION_RECEIPT_2026-09-08.md)：10/10 cells、300 episodes、replay exact；A-C1 的 R3 實例、A-C2 的 284/284。依據是已存在的 receipt 與其凍結規則下的 outcome |
| `PUB-A1b` 公開 benchmark 上的不對稱 regime | 在公開 benchmark 上以凍結 protocol 量到 R1 | **`CLOSED_NOT_ATTAINED`**（2026-09-09） | 三個 budget probe（[probe receipt](SECOND_CASE_V2_BUDGET_PROBE_RECEIPT_2026-09-08.md)）後由專案負責人決定停止；寫入 Limitations 第一條。**不是 PASS、不是放寬**；重開需新 protocol id 與含 saturation 下限的 probe 規則 |
| `PUB-A2` Claim freeze | [TRACK_A_REFRAME §5](TRACK_A_REFRAME_2026-09-09.md) 每列可只由 hash-bound receipts 推出；§6 不可宣稱清單與 §7 figure／table 清單凍結；Limitations 先寫 | `IN_PROGRESS` — 草稿即 TRACK_A_REFRAME；2026-09-11 凍結並執行 [`R0-REGIME-HORIZON-PROBE-V1`](R0_REGIME_PROBE_RECEIPT_2026-09-11.md)：兩個對比皆 `R0_WINDOW_FOUND`，taxonomy 的 `R0` 格已由「未觀察到」改為 pilot 實例 | 凍結須在 A0 之後 |
| `PUB-A3` Reproduction | clean checkout 以 `python -I -S` 重建稿件每一張 table／figure 的輸入；受 `ENVIRONMENT-LOCK-V1` record 比對 | `NOT_STARTED` | 現有 replay 已覆蓋每一層；缺 formal clean-checkout 一次性執行 |
| `PUB-A4` Internal review | 至少一輪對抗式內部審查（含統計與 RL 評估兩個視角），所有 blocking 意見有回應 | `NOT_STARTED` | |
| `PUB-A5` Submission | venue 選定；preprint 與 code／receipt archive 帶 DOI | `NOT_STARTED` | |

### 3.2 Track B

| Gate | Exit condition | 狀態 |
|---|---|---|
| `PUB-B0` Authorization decision | 專案負責人書面決定：授權 formal evaluation 於現行 `SELECT-V7-CANDIDATE-FORMAL-V1`，或改為 preregister 新規則 | `AUTHORIZED_2026-09-10 / SUB_OPTION_OPEN` — 授權已取得（[receipt](PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10.md)）；用哪條規則、FORMAL seeds 花在哪條訓練線兩問未決；protocol 仍不可執行（`EP-01`／`EP-02` 未解除，`EP-03` 待 narrowing amendment），且 `PUB-B4` 仍在解封之前 |
| `PUB-B1` Tracked training line | 新線每個 checkpoint 與 warm start 進版控或 immutable storage；每個 run 以 `RUN-MANIFEST-LOCK-BINDING-V1` 綁定 lock record（經 `backend/rl/bind_run_lock.py`，否則 gate 判為 `RUN_LOCK_UNBOUND`） | `NOT_STARTED`；綁定機制已於 2026-09-13 就緒 |
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
     ├─► PUB-A1a PASS（Walker2d V1）；PUB-A1b CLOSED_NOT_ATTAINED（2026-09-09）
     │        └─► PUB-A2 claim freeze（草稿已有，A0 後凍結）→ A3 → A4 → A5   ← Track A 投稿
     │
     ├─► PUB-B0 授權（2026-09-10 已取得；子選項未決）
     │        └─► PUB-B4 OSF preregistration ──┐
     │                                          ├─► 解封 EP-01/EP-02 ──► PUB-B6
     ├─► PUB-B1 新訓練線（工程 ROADMAP §9 第 2 項）│
     │        └─► PUB-B2 → PUB-B3 ─────────────┘
     └─► PUB-B5 V1（工程 ROADMAP §9 第 4 項）
```

**Track A 不浪費 Track B：** A1a 的第二案例 protocol 就是 B 的 exposure audit 在新 task 上的第一次演練；A-C3 的 reference-adequacy 前置條件（exposure + 非退化）就是 `PUB-B2` 的出口條件應有的形狀；A 的 reproduction package 就是 B 的。

**順序不可反：** `PUB-B4` 必須在解封 sealed seeds `20000–20029` 之前。授權在前、預註冊在中、解封在後。2026-09-10 的授權填上第一格；第二格（`PUB-B4`，只有專案負責人能做）與 `EP-01`／`EP-02` 的 amendment 都尚未完成，故 `20000–20029` 於當日未被存取，也不應被存取。

## 5. 專案負責人需要做的決定

**已決定（2026-09-10）：** 授權 formal evaluation。紀錄與當下的 protocol 身分見 [PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10](PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10.md)。授權是一項決定，不是一項技術狀態變更：frozen protocol JSON 內 `EP-03` 仍硬寫 `BLOCKING`，`assert_executable()` 讀的是該 JSON，因此 protocol 仍不可執行。

**尚未決定的兩個子問題**，都只有負責人能做：

> **(a) 用現行的、公開宣告非預註冊的 `SELECT-V7-CANDIDATE-FORMAL-V1`，還是先在 OSF 預註冊一條替代規則？**

- 用現行規則：較快；論文必須寫明規則是在看過 DEV 結果後設計的，並附 [rule self-check](V7_CANDIDATE_SELECTION_IMPLEMENTATION_RECEIPT_2026-09-08.md) 的失敗證據。
- 先預註冊替代規則：較慢；換來一條不需要揭露段落就能站住的規則。

本計畫的建議是後者，前提是時程允許。但這是研究策略決定，不是技術決定。

> **(b) 唯一未被檢視的 FORMAL seed 範圍 `20000–20029` 要花在哪條訓練線？**

[RESULT] 這個子問題是授權之後才成為首要問題的，依據是 receipt §3 的量測：`SEL-C2` 要求 reference 與 candidate 的每一個 episode 都 `COMPARABLE`，而 retained seed-variance evidence 上 reference `V7A` 本身只有 143/150，`V7B` 120/150，`V7C` 0/150；FORMAL 用的是同一批已訓練的 policy，只換 evaluation seed。iid 外推下 reference + `V7B` 的聯合通過機率是 `2.2 × 10⁻¹⁸`、reference + `V7C` 是 `0`。

[BLOCKER] [V7_CANDIDATE_SELECTION_SPEC §5](V7_CANDIDATE_SELECTION_SPEC.md) 規定 FORMAL 資料只套用一次，事後不得重跑、調門檻、改 `replicate_count` 或改 arm 定義。因此在 v7 線上執行會用掉唯一剩下的未檢視範圍，換得一個機率接近 1 的 `SELECTION_COMPLETE_NO_CANDIDATE`。

[INFERENCE] 本計畫的建議是保留該範圍給 `PUB-B1`／`PUB-B2` 的新訓練線（reference policy 能穩定跑完任務、且有版控 lineage），理由是上述量測。若決定仍在 v7 線上執行，工作順序已寫在 receipt §5，不必重新推導。

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
| ~~lock record 綁進 run manifest~~ → 2026-09-13 前向完成 | A3、B1（機制已就緒；實際綁定隨新訓練線產生） |
| 有版控 lineage 的新訓練線 | B1、B2 |
| browser visual verification | C0 |
| V1 dynamic／pendulum／energy | B5 |
| binary paired CI golden-case oracle | B6 |

## 8. 立即下一步

1. **`PUB-A0`**：關鍵兩篇已核對（2026-09-09，gap 仍成立）、A-C5 補充 scan 已完成（2026-09-10，A-C5 降級）。**唯一剩餘工作**：在可存取出版方的環境讀 §1.1、§1.3–§1.5、§1.7 與 §2 的 `U` 條目原文，逐條改為 `S` 或刪除，並把 §4 重寫為非條件式。優先四篇：Pardo 2018（termination／truncation 語義）、Colas 2019（statistical unit）、Manski 1990 與 Tamer 2010（bound 的方法出處）、Hollenbeck & Wright 2017（Tharking，A-C5 的定位依據）。
2. **`PUB-A2`**：`PUB-A1a` 已 PASS、`PUB-A1b` 已關閉；下一步是在 A0 之後把 [TRACK_A_REFRAME §5–§7](TRACK_A_REFRAME_2026-09-09.md) 凍結為 claim freeze receipt。同時核對 rl-zoo recipe 數值（影響限制清單第 5 條的措辭）。**不再開任何第二案例 probe 或 protocol**；2026-09-11 的 [`R0-REGIME-HORIZON-PROBE-V1`](R0_REGIME_PROBE_RECEIPT_2026-09-11.md) 不是第二案例線——它不訓練、不評估、不動 seed，只對既有 450 個 retained episode 做唯讀重算。它已執行完成，兩個對比皆 `R0_WINDOW_FOUND`，並量到同一批 policy 與 seed 只改 horizon 就在 `R0`／`R1`／`R2` 之間移動，應寫入 §3 taxonomy 與 A-C3 的論述。
3. **`PUB-B0`**：授權已於 2026-09-10 取得（[receipt](PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10.md)）。剩餘工作依序是 §5 的子問題 (a)(b) 決定 → `PUB-B4` 外部預註冊（負責人）→ `SELECT-AMENDMENT-01`（`EP-03` narrowing amendment 並重新 pin digest）→ `EP-01`／`EP-02` amendment。在 (a)(b) 未決之前**不鑄造機器可讀的 authorization evidence**，因為該證據 pin 現行 `protocol_sha256`，鑄造它等於選定 (a) 的前者。
4. 工程：ROADMAP §9 第 1、2 項並行。

## 9. 版本紀錄

| 版本 | 日期 | 變更 |
|---|---|---|
| `PUBLICATION-PLAN-V1` | 2026-09-08 | 建立三條 track、PUB gates、寫作規範、不可宣稱清單 |
| `PUBLICATION-PLAN-V3` | 2026-09-10 | 專案負責人授權 formal evaluation（[PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10](PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10.md)）。`PUB-B0` 由 `BLOCKED` 改為 `AUTHORIZED_2026-09-10 / SUB_OPTION_OPEN`；§5 由「一個決定」改為「已授權 + 兩個子問題」，新增子問題 (b)：唯一未檢視的 FORMAL seed 範圍要花在哪條訓練線，附 `SEL-C2` 的可行性量測。授權**不**使 protocol 可執行、**不**解封 seeds、**不**改任何門檻或 arm 定義；`PUB-B4` 仍在解封之前。Track A、Track C、§6–§7 與四個總開關不變 |
| `PUBLICATION-PLAN-V2` | 2026-09-09 | 專案負責人決定停止第二案例 V2 線（三個 budget probe 後）。Track A 重構為 censoring regime 的評估效度研究（[TRACK_A_REFRAME_2026-09-09](TRACK_A_REFRAME_2026-09-09.md)）；新增主貢獻 A-C3；`PUB-A1` 拆為 A1a（`PASS`，依既有 Walker2d V1 receipt）與 A1b（`CLOSED_NOT_ATTAINED`，寫入 Limitations）；`PUB-A2` 進入 `IN_PROGRESS`（草稿）。`SECONDCASE-EXPOSURE-CENSORING-WALKER2D-V2`／`-HOPPER-V1` 兩個從未 pin 的 protocol id 在 contract 中撤回。Track B、Track C、§5–§7 不變；四個總開關不變 |
| `PUBLICATION-PLAN-V2`（狀態更新） | 2026-09-09 | `PUB-A0`：§4 點名的兩篇關鍵文獻由專案負責人提供 PDF 並全文核對；兩個「gap 縮小／消失」條件皆不成立，A-C1／A-C2 的 gap 判定不再條件於它們；狀態 `KEY_TWO_VERIFIED_GAP_STANDS / REMAINING_U`，gate 仍未 PASS。計畫本體無變更 |
| `PUBLICATION-PLAN-V2`（狀態更新 2） | 2026-09-10 | `PUB-A0`：A-C5 的 preregistration／multiverse 補充 scan 完成（[LITERATURE_MAP §1.7](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md)）。判定**縮小主張**：A-C5 由「次貢獻」降為 artifact 級並併入 A-C4，理由是 Tharking（2017）已涵蓋透明宣告、Cawley & Talbot（2010）與 Dwork et al.（2015）已涵蓋決策資料隔離，剩餘窄點的解讀又受 exposure 混淆。gate 狀態 `KEY_TWO_VERIFIED_AND_A_C5_SCANNED / REMAINING_U`，仍未 PASS。Track A 的主貢獻仍為 A-C1／A-C2／A-C3。計畫本體與 Track B／C 無變更 |
