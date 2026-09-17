# 專案進度狀態報告

最後更新：2026-09-17 ｜ 對應 `STATUS.yaml` ｜ Development：`0.2.0-dev`

證據範圍：`SIM_ONLY_REDUCED_ORDER` / `NOT_PHYSICALLY_VALIDATED`

本文件是人類可讀的進度總覽。機器可讀的權威狀態在 [`STATUS.yaml`](../STATUS.yaml)；兩者不一致時以 `STATUS.yaml` 為準並修本文件。學術產出的規劃另見 [PUBLICATION_PLAN](PUBLICATION_PLAN.md)；工程路線另見 [ROADMAP](ROADMAP.md)。

## 0. 一頁摘要

- **`progress: 0`**。這不是筆誤：專案成熟度以 V&V gate 通過數計算，不以功能數計算。軟體與證據基礎設施做了很多，但**五道 V&V gate 一道都還沒過**，**九道 PDR gate 一道都不是 PASS**。
- **四個總開關全為 false**：`paper_data_ready`、`statistics_ready`、`method_level_power_ready`、`sample_size_decision_input_ready`。
- **量到一個站得住的方向性結果**：V7B（縮小 joint envelope）相對 V7A 的 500 Hz saturation duty，method-level identification bound `[-13.503408, -12.435259]` pp，排除 0、sign NEGATIVE、5/5 independent training replicates 方向可識別。**條件**：五個 replicate 共用同一個不可重建的 v5 warm start，此條件對 v7 line 永久成立。
- **推翻一個假結果**：V7C 原本看似 `-36` pp 的巨大改善，經 audit 量測確認為 exposure artifact（30/30 episode 在 horizon 的 35.4889% 早期跌倒），並跨 5 個獨立 seeds 完全重現。
- **Track A 已重構（2026-09-09）**：第二案例 V1（Walker2d-v5）依凍結規則重現 artifact，但兩臂皆 censored；三個 budget probe 沒有在公開 benchmark 上找到「reference 充分曝露且 metric 非退化」的設定，且暴露了 exposure-only adequacy 規則的缺口。專案負責人決定停止該線，Track A 改為「censoring regime 的評估效度研究」（[TRACK_A_REFRAME](TRACK_A_REFRAME_2026-09-09.md)）：`PUB-A1a` PASS、`PUB-A1b` CLOSED_NOT_ATTAINED、`PUB-A2` 草稿已有。
- **`PUB-A0` 關鍵兩篇已核對（2026-09-09）**：專案負責人提供 arXiv 1911.05728 與 2606.10229 的 PDF，全文核對後兩個「gap 縮小／消失」條件皆不成立（前者為 independent-censoring + imputation 的點估計，後者為 curation metric 的設計期 truncation）；A-C1／A-C2 的 gap 判定不再條件於它們。gate 仍未 PASS：其餘文獻條目仍為 `U`（[LITERATURE_MAP §7](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md)）。
- **A-C5 降為 artifact 級（2026-09-10）**：preregistration／multiverse 補充 scan 完成後判定縮小——「透明宣告 post hoc」已是 Hollenbeck & Wright (2017) 的 Tharking，「決策資料未被檢視」已由 Cawley & Talbot (2010) 與 Dwork et al. (2015) 建立，剩餘窄點的解讀又受「選不出東西可能只因 exposure 不足」混淆。A-C5 併入 A-C4，不再單獨作為主張（[LITERATURE_MAP §1.7、§4 第 5 點](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md)）。
- **`PUB-B0` 已授權（2026-09-10）**：專案負責人授權 formal evaluation（[PUB_B0_AUTHORIZATION_RECEIPT](PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10.md)）。授權**不使 protocol 可執行**：frozen protocol JSON 內 `EP-03` 仍硬寫 `BLOCKING`、`EP-01`／`EP-02` 未解除，且凍結順序要求 `PUB-B4` 外部預註冊在解封 sealed seeds `20000–20029` 之前，而預註冊只有專案負責人能做。當日**未存取** FORMAL seeds。
- **動作任務範圍已決定（2026-09-11）**：專案負責人採納建議，**現在不新增**跳躍或轉身任務（[MOTION_SCOPE_DECISION](MOTION_SCOPE_DECISION_2026-09-11.md)）。理由是量到的四件事：Motion Task V1 本身尚未通過、V1 plant credibility 四項全缺而跳躍恰好依賴那四項、更難的任務會把比較推入更重的 censoring regime、以及在版控 lineage 建立前新增訓練線會複製已發生過的 provenance 損毀。凍結順序：先做 [ROADMAP §9](ROADMAP.md) 第 1、2 項，轉身需 `PUB-B2` 出口條件，跳躍需 V1 PASS。
- **`R0` regime probe 已凍結（2026-09-11）**：taxonomy 六格中唯一空的 `R0` 不需要新增動作任務即可探測——retained 的 450 個 evaluation episode 每個 control step 都記有 `saturation_substeps_over_threshold`／`_total`（10 substeps = 500 Hz），任意截斷 horizon 的 duty 可精確重算，且在全 horizon 上對 **450/450 episode** 與凍結值完全相等。規格 [R0_REGIME_PROBE_SPEC](R0_REGIME_PROBE_SPEC.md) 於凍結並 push 後執行，[receipt](R0_REGIME_PROBE_RECEIPT_2026-09-11.md) 記錄結果：**兩個對比皆 `R0_WINDOW_FOUND`**。`C_B` 在 `H ≤ 414`（8.28 s）、`C_C` 在 `H ≤ 152`（3.04 s）。最有意義的一項：同一批 policy 與 seed，只改 evaluation horizon，`C_B` 就從 `R2` 變成 `R0`——而所需的只是放棄最後 `36` 個 control step（`0.72` s，不到 horizon 的 8%），因為 `V7A` 的 7 個與 `V7B` 的 30 個早期終止**全部落在 `FINAL_STAND` 階段**。`python -I -S` replay bit-exact，environment lock 與母證據逐位元相同。仍為 PILOT，不得讀成任何一臂在 9 s 任務上的陳述。
- **新訓練線已執行完成（2026-09-14）：`PUB-B1` 達成、`PUB-B2` `NOT_ATTAINED`**（[receipt](TRACKED_LINEAGE_TRAINING_RECEIPT_2026-09-14.md)）。五個 scratch replicate 全部訓練完成、20 個 checkpoint 進版控（`38.0 MiB`）、10 次執行 gate 皆 `RUN_LOCK_BOUND`，所以**一條 provenance 可重建的訓練線現在存在**。但**沒有任何一個 replicate 的 reference policy 達到 `30/30`**：五個皆 `0/30`，`150` 個 episode 全部早期跌倒（平均 `2.585733` s／`9.0` s、`fall_rate` 皆 `1.0`、`saturation_duty_pct` 為 `0.0`），跌倒集中在 `STEADY_WALK` 起點（`2.5` s）附近——學到站立，沒學到起步行走。標籤 **`TL_BUDGET_EXHAUSTED`**（amendment 03 更正——初次分析漏量了「曲線是否收斂」這個區分條件；實測五個 replicate 在上限處全部**未**收斂，末四分位斜率仍有 `+7.3`–`+11.9`／500k 步）。**是事先宣告的結果不是失敗**，門檻不得下調，且上限**不得**因「再多跑一點就到了」而上調。**沒有任何 contract 違反**，所以這是一次乾淨量測的否定結果而非 `TL_METHOD_FAILURE`。設計面：[`TRACKED-LINEAGE-TRAINING-V1`](TRACKED_LINEAGE_TRAINING_SPEC.md) 把 [ROADMAP §9](ROADMAP.md) 第 2 項收窄為 **scratch**——版控內唯一的 warm start 候選是 v5 artifact，它的檔案可由 digest 重建但訓練過程不可重建，從它 warm start 等於原封不動保留 `CONDITIONAL_ON_FIXED_WARM_START`。專案負責人於同日、**在看到任何訓練曲線之前**定案兩格：`CHECKPOINT_STORAGE = GIT_DIRECT` 配 `checkpoint_interval = 500_000`（唯一同時離線可驗且不需新基礎設施的組合；本容器無 `git lfs`），以及 `FULL_EXPOSURE_THRESHOLD = 30/30`（逐 replicate；`29/30` 會以較輕的形式複製 v7 線 `between_replicate_sd` 為 null 的成因）。兩項代價在定案時即已接受：repo 由 `11 MB` 增為約 `49 MB` 且每條新線再加；scratch 在 5 個 replicate 上全部 30/30 **很可能**得到 `TL_REFERENCE_NOT_ATTAINED`，而門檻凍結後不得因結果下調。**本線範圍只到 `PUB-B1`／`PUB-B2`**：取得逐控制步 trace 須修改 `backend/rl/eval_policy.py`，那會弄紅一個綁在 owner 已授權 protocol 上的綠測試，故本線不產生任何 saturation 或 censoring regime 資料，`PUB-B3` 需要另一份 protocol。
- **加倍預算的續訓線也已執行完成（2026-09-14）：`PUB-B2` 仍 `NOT_ATTAINED`，標籤 `TL2_BUDGET_EXHAUSTED`**（[V2 receipt](TRACKED_LINEAGE_TRAINING_V2_RECEIPT_2026-09-14.md)）。V1 的曲線在上限處全部未收斂，所以「預算是不是那個綁住結果的限制」是一個可以量的問題；[`TRACKED-LINEAGE-TRAINING-V2`](TRACKED_LINEAGE_TRAINING_V2_SPEC.md) 從每個 V1 replicate 保留的 `1,999,968` 步 checkpoint 續訓，各再加 `2,000,000` 步。**量到的答案是否定的**：獎勵由 `226.9`–`231.6` 升到 `283.1`–`295.3`（`+51.5`–`+66.5`），平均存活由 `2.440`–`2.811` s 升到 `2.725`–`3.458` s（`+0.145`–`+0.778` s），而**完整曝露仍是 `0/30`，五個 replicate 全部、`150` 個 episode 全部**，最長的單一 episode 只有 `4.0` s，門檻是 `9.0` s。**五個全部未收斂，而且五個裡有四個的末四分位斜率比首四分位還大**（V1 是 `+7.3`–`+11.9`／500k，V2 是 `+11.8`–`+22.2`）——跑到 `4,015,200` 步，曲線不是逼近天花板而是更陡，同時曝露完全沒動。**標籤是 contract runner 算出來的不是人寫的**：`backend/rl/run_tracked_lineage_v2_contract.py` 只讀版控內的保留證據，跑完 `TL2-01`..`TL2-09` 後輸出 [`tl2_contract_receipt.json`](../backend/tracked_lineage_evidence/2026-09-14/tl2_contract_receipt.json)，任何人可重跑並 diff。凍結前的算術五個全中：realized `4,015,200`、checkpoint 落在 `2499960/2999952/3499944/3999936`、10 次執行 gate 皆 `RUN_LOCK_BOUND`、`TL2-08` 五個精確成立。兩個會左右標籤的量測選擇在任何 V2 曲線存在之前就寫進程式碼（以 lineage 曲線而非只看增量、聚合取 `any` 而非 `all`），兩個都選了對「再加預算」更不利的方向，而**兩個都沒有改變結論**——這點照實記錄，不誇大成關鍵。依規格 `escalation_rule`，再次得到 `TL2_BUDGET_EXHAUSTED` 是**結果**，**不授權**單純再加預算；V3 需要自己的 protocol 版本並揭露它是在已知 V1 **和** V2 結果之後設計的。**要改的不是預算**：`2,000,000` 步買到不到 `0.8` s，而門檻還差 `5` s 以上。儲存實測 `.git` `83 MB`，落在規格 §5.3 事先預估的約 `85 MB` **之內**。本線補掉七個缺陷，全部同兩種形狀——主張為真但證據活不過容器，或程式跑過 fixture 沒跑過真正凍結的東西——其中一個是 **V1 的 `RUN_LOCK_BOUND` 從來無法離線重導**（gate 只印到 console，索引裡寫的是佔位字串），V1 五筆至今仍是如此。
- **專案評估已完成（2026-09-16）**（[PROJECT_ASSESSMENT](PROJECT_ASSESSMENT_2026-09-16.md)）：給專案負責人的**決策文件**，不是 receipt。實測：核心 robotics + 應用 `6,871` 行、前端 `3,561` 行，證據契約／replay／bundle `29,294` 行（**1 : 4.3**），其中約 `15,800` 行服務的研究線已結案；692 個測試函式只有 76 個測教學應用本身；**沒有任何不可達的程式**（21 個零 importer 模組全是合法 CLI 入口——這推翻了盤點初始的假設）。機器人：v5 會走（10/11）但 checkpoint 是看結果後挑的；所有可重建的線（10 replicate × 2 預算）全部在 `STEADY_WALK` 起點跌倒，獎勵結構的量化診斷指出「站好再跌」是穩定局部最優、跌倒懲罰已是 −50 而非綁住結果的項，槓桿在 curriculum／形塑不在預算。**價值判斷**：作為 robotics 研究弱；作為評估效度研究**真的有一篇**（Track A，證據已齊、**不需要 `PUB-B2`**）；作為教學工具有實質價值且**與研究契約完全解耦**（`main.py` 零 import、前端建置乾淨）。**關鍵觀察**：`PUB-B2` 的理由在 2026-09-09 Track A 重構那天就消失了，gate 卻留下來並又花了兩條線追它。三個去向選項與代價見該文件 §5；本次順手修正 REPOSITORY_GUIDE 兩處過期事實並加註 §4 的證據版控範圍。**負責人尚未決定**。
- **介面已改版（2026-09-16）**：依專案負責人要求整理前端，目標是簡潔、每頁不要同時放太多資訊。**功能一項都沒有移除**，改的是版面：常駐的 9 px 證據 badge 列改為一個結果狀態標籤加「證據狀態」抽屜（token 一個沒少）；分析頁一次只顯示一組參數與一張圖，14 條警告長文改為嚴重度計數＋致動器表格＋短標題，原文收在按鈕後；即時互動的決策日誌依後端節流 key 分六類、可過濾並合併連續同類；三機比較卡片改中文標題與四格門檻數值；兩個圖表頁改為**一個量一條 y 軸**（原本 deg 與 m/s、Nm 與 rad 與 % 共軸，把小單位序列壓成平線），並加上相位色帶（分析頁為支撐相、Dynamic Trace 為控制器狀態）、事件標記與 hover 讀數；關節配色改跟關節群組走、左右以線型區分。**證據語義、API 形狀與既有字串都沒有改**：後端只新增兩個唯讀欄位（`meta.warning_items` 與 decision 的 `kind`），皆與原資料一對一。操作說明見 [USAGE §3](USAGE.md)。

- **量測到 v7 線上 `SEL-C2` 幾乎確定不成立**：retained seed-variance evidence 上 reference `V7A` 自己只有 143/150 episode `COMPARABLE`，`V7B` 120/150，`V7C` 0/150；FORMAL 用同一批已訓練 policy、只換 evaluation seed。iid 外推的聯合通過機率為 reference + `V7B` `2.2 × 10⁻¹⁸`、reference + `V7C` `0`。因 FORMAL 資料只套用一次，在 v7 線上執行會用掉唯一未檢視的 seed 範圍換一個 `NO_CANDIDATE`。**下一個決策點**因此是兩個子問題（[PUBLICATION_PLAN §5](PUBLICATION_PLAN.md)）：用現行規則或先預註冊替代規則；以及 FORMAL 範圍花在 v7 線或保留給 `PUB-B1`／`PUB-B2` 的新訓練線。

## 1. V&V gates

> **本表是這些 gate 狀態的唯一權威來源**（`GATE-STATUS-SINGLE-SOURCE-V1`）。其他文件中陳述同一狀態的地方都登錄為 mirror，由 `backend/gate_status_contract.py` 逐一比對，不一致即測試失敗。改狀態的步驟見 [GATE_STATUS_SINGLE_SOURCE](GATE_STATUS_SINGLE_SOURCE.md) §7。

| Gate | 狀態 | 已有 | 缺 |
|---|---|---|---|
| V0 Evidence & Provenance | `PARTIAL_IMPLEMENTED_NOT_PASS` | bounded fail-closed input contracts、`ANALYSIS_METRICS_V1`、run-level `PAPER_RUN_MANIFEST_V2`、artifact inventory/SHA-256、clean-source Git identity、`ENVIRONMENT-LOCK-V1` 可量測 environment identity（一份實測 record）、`RUN-MANIFEST-LOCK-BINDING-V1` fail-closed 綁定（2026-09-13，前向） | project-wide immutable artifact storage；lock 綁定的三項殘餘缺口（sidecar 可被遺漏、`simulator.py` 明示排除、2026-09-08 bundle 的兩個斷言不可重驗）；full raw artifact inventory；complete requirement registry；actual Study A matrix |
| V1 Plant & Numerical | `PARTIAL_IMPLEMENTED_NOT_PASS` | static double-support V4 16/14 exact；analytical fixture（passive single-support、centered 5 kg payload、4/2/1 ms grid）4/4 PASS，含 raw Jacobian stdlib-only replay | articulated dynamic、known pendulum、dynamic contact、energy balance、完整 solver／finite-difference convergence；receipts 皆 same-engine，fixture 非 articulated |
| V2 Actuator / Sensor / Estimator | `NOT_STARTED` | — | torque-speed/thermal envelope、joint limits、latency/noise、estimator |
| V3 Fair Benchmark & UQ | `FOUNDATION_SOFTWARE_PARTIAL` | experiment matrix validator、paired statistics/export contract、exposure-censoring audit、seed-variance contract（皆 synthetic + 部分實資料驗證） | actual Study A、binary paired CI（無 golden-case oracle）、external preregistration；formal authorization 已於 2026-09-10 取得但 protocol 仍不可執行 |
| V4 Subsystem Validation | `NOT_STARTED` | — | 任何 SIL/HIL/bench/robot evidence |

## 2. Paper Data Readiness gates

> **本表是 mirror，不是權威來源**（`GATE-STATUS-SINGLE-SOURCE-V1`）。權威在 [PAPER_DATA_READINESS](PAPER_DATA_READINESS.md)；兩邊不一致時以權威為準，且 `backend/gate_status_contract.py` 會讓測試失敗。規則見 [GATE_STATUS_SINGLE_SOURCE](GATE_STATUS_SINGLE_SOURCE.md)。

| Gate | 狀態 | 一句話 |
|---|---|---|
| PDR-0 Claim | PARTIAL | RQ 與 claim boundary 有；primary outcomes 未對 formal study 凍結 |
| PDR-1 Model evidence | PARTIAL | 見 V1 |
| PDR-2 Run identity | IN PROGRESS | 各層 identity 都能量測；`RUN-MANIFEST-LOCK-BINDING-V1`（2026-09-13）已把 lock record **前向**綁進 run manifest 並提供 fail-closed gate；v7 retained bundles 的 environment 仍為 `ABSENT_UNRECOVERABLE` |
| PDR-3 Raw integrity | IN PROGRESS | path/bytes/SHA-256 readback PASS；failure/NULL/censoring 全數保留 |
| PDR-4 Matrix completeness | SOFTWARE ONLY | validator 有，**actual Study A matrix 未跑** |
| PDR-5 Independent metrics | PARTIAL | 每一層都有 `python -I -S` stdlib-only exact replay；Study A outcomes 未覆蓋 |
| PDR-6 Statistics | SOFTWARE PARTIAL | continuous paired CI 有；censoring → identification bounds 有；**binary paired CI blocked**；**between-replicate SD 為 null** |
| PDR-7 Reproduction | SOFTWARE PARTIAL | synthetic 與 v7 raw→summary exact 重建；formal clean-checkout reproduction 未做 |
| PDR-8 Paper export | SOFTWARE PARTIAL | machine-readable table/figure inputs 有；無 formal data |

## 3. 總開關

| Flag | 值 | 為什麼 |
|---|---|---|
| `paper_data_ready` | false | 無任何 FORMAL_EVALUATION run |
| `statistics_ready` | false | 無 Study A 資料；binary paired CI blocked |
| `method_level_power_ready` | false | `between_replicate_sd = null` |
| `sample_size_decision_input_ready` | false | 同上；每個 replicate 至少一臂被 exposure censored |
| `selected_candidate_arm_id` | null | 選擇規則已凍結但不可執行（EP-01/02/03） |
| `pilot_planning_ready` | false | 無 eligible candidate |
| `preregistered`（selection rule） | **false** | 規則在看過結果後才寫，由 contract 強制揭露 |

## 4. 已量測的科學結果

全部為 `DEVELOPMENT` evidence、`SIM_ONLY_MUJOCO`。每一項都有 hash-bound receipt 與獨立 replay。

[BLOCKER] **可從 repo 重導的範圍（2026-09-16 盤點）**：§4.1 的 **Seed-variance 欄**與其 method-level bound `[-13.503408, -12.435259]` pp 可由已進版控的 `backend/seed_variance_evidence/2026-09-08/bundle/raw_replicates.json`（276 KB）重算；§4.4、§4.5 與兩條 tracked-lineage 線亦可。但 §4.1 的 **Pilot 欄**（seed 8700、14 個 artifact、109.5 MB）與 §4.2 **exposure audit 的凍結 bundle**（113 MB）位於 gitignored 的 `backend/run_traces/`，**不在版控內**，只存在於產生它們的容器——這是 [REPOSITORY_GUIDE §3](REPOSITORY_GUIDE.md) 明文的政策（`run_traces/` 不是 immutable evidence bundle；正式 bundle 應用外部儲存），不是疏忽，但後果是：專案自稱「最強結果」的 v7 線，其 pilot 層數字與 audit 發現是**所有線裡從 repo 最不可重導的**。處置選項見 [PROJECT_ASSESSMENT §4.3](PROJECT_ASSESSMENT_2026-09-16.md)。

### 4.1 Action-interface 三臂（v7 line）

| Arm | 定義 | Pilot（seed 8700，30 DEV seeds） | Seed-variance（5 replicates × 30 seeds） |
|---|---|---|---|
| V7A `REWARD_ONLY` | direct normalized action，原 12-D range | saturation `36.2185185 ± 1.0328300%`，30/30 full exposure | 143/150 full、7 early（r2/r3/r4） |
| V7B `REDUCED_JOINT_ENVELOPE` | knee/ankle/shoulder/elbow target-offset range 對稱縮小 | `23.3896264 ± 1.0044698%`，paired B−A `-12.8288921 ± 1.0720320` pp，**4 negative episodes → ineligible** | 120/150 full、30 early；method-level bound **`[-13.503408, -12.435259]` pp，排除 0，5/5 sign-identified** |
| V7C `FILTERED_ACTION` | 加 `alpha=0.25` 一階 low-pass | 30/30 early fall、30 NULL outcomes | 0/150 full、150 early、150 NULL；bound `[-37.195407, +27.315704]` pp 含 0、0/5 |

[RESULT] 450 個 seed-variance episodes 全為 `COMPARABLE`（263）或 `EXPOSURE_CENSORED`（187），**零 method failure**。
[RESULT] Pilot 那個乾淨的 V7A reference（30/30 full）是 **seed 8700 的性質**，不是 V7A 的性質。
[INFERENCE] V7B 方向跨獨立 seed 穩健；但**方向可識別 ≠ 變異可估計**。`between_replicate_sd` 為 null 是因為 5 個 paired difference 全是 interval，sample SD 沒有定義在 interval 上。
[BLOCKER] `CONDITIONAL_ON_FIXED_WARM_START` 永久：見 §6.1。

### 4.2 Exposure-censoring audit（對 frozen pilot bundle 的 read-only 量測）

[RESULT] V7C 30 個 episode 在 `159.7000 ± 2.7687` steps（`3.08–3.30` s，horizon 的 `0.354889`）於 `STEADY_WALK` 中終止；其 0% duty 的 assumption-free full-horizon bound 為 `[0.0, 64.511111]`%，與 V7A `36.2185185`% 重疊；paired bound `[-36.2185185, +28.2925927]` 含 0，0/30 sign-identified。
[RESULT] V7B 的 3 個 censored episode（seeds 18015/18021/18023）`outcome_state` 全為 `OBSERVED`、六項 required numeric 皆有值。**`OBSERVED` 不蘊含 full exposure** —— 這是 audit 揭露的實測盲點，之後成為 selection rule `SEL-C2` 的依據。
[RESULT] Audit 僅由 trace 長度獨立還原出與 pilot 紀錄一致的跌倒 seed 集合，並正確把 stop-only 失敗的 18011 留在 full exposure。
[RESULT] Validity finding：recorded `command_phase` 採 end-of-step convention，與 contract 的 start-of-step schedule 差一個 control step；原樣保留，未修改資料。

### 4.3 Environment identity

[RESULT] 同一環境、同 1000 個 reciprocal：stdlib 順序相加得 `7.485470860550343`，`numpy.ndarray.sum` 得 `7.485470860550345`。兩者皆符合 IEEE 754。**這是「pin 版本號不足以重驗數值」的直接證據**，也是 `test_v1_analytical_suite.py::test_stdlib_replay_passes_exact_synthetic_fixture` 在此 lock 下記錄為失敗而非放寬的原因。

### 4.4 第二案例（Walker2d-v5，`SECONDCASE-EXPOSURE-CENSORING-WALKER2D-V1`）與三個 budget probe

| 項目 | 結果 | 性質 |
|---|---|---|
| V1 執行（2 arms × 5 replicates × 301,056 steps） | 300 episodes、284 EARLY／16 FULL；reference 4/5 replicates 30/30 早跌；naive `W2D_C − W2D_A` `−28.795138` pp、t-interval `[−46.698919, −10.891357]` 排除 0；θ `[−79.118, +55.913333]` 含 0、0/5；`SECOND_CASE_ARTIFACT_REPRODUCED`；P3 284/284 `OBSERVED` | DEVELOPMENT，凍結 protocol，replay exact（[receipt](SECOND_CASE_EXPOSURE_CENSORING_EXECUTION_RECEIPT_2026-09-08.md)） |
| Probe V1（Walker2d，SB3 預設，上限 2,949,120） | `PROBE_NEGATIVE_MAX_BUDGET_REACHED`，1/360 full | **pilot** |
| Probe V2（Walker2d，rl-zoo tuned，上限 1,966,080） | `PROBE_NEGATIVE_MAX_BUDGET_REACHED`，5/240 full | **pilot** |
| Probe V3（Hopper-v5，tuned，上限 1,966,080） | `PROBE_BUDGET_FOUND` 1,474,560；reference 站立不動、saturation 2.712%（兩個更早 30/30 checkpoint ≈ 0%） | **pilot**；規則缺口記錄為 blocker |

[RESULT] V1 是 Track A regime R3（對稱重度 censoring）的凍結量測實例，也是 A-C2（`OBSERVED ⇏ full exposure`）第二個 plant 的證據。
[BLOCKER] Probe 的凍結 claim boundary 只支持 budget 選擇；不得用於任何關於 Walker2d／Hopper／PPO recipe 能力的陳述。2026-09-09 起 `…-WALKER2D-V2`／`…-HOPPER-V1` 兩個 protocol id 撤回（從未 pin、從未載入），詳見 [probe receipt §7](SECOND_CASE_V2_BUDGET_PROBE_RECEIPT_2026-09-08.md)。

### 4.5 Motion task（v5 Live 500 Hz）

[RESULT] run `run-20260830t055847-rl_task_v5-b6c4781d` 通過 10/11 criteria，無跌倒；唯一失敗為 saturation duty `38.422222% > 30%`。門檻未放寬。

## 5. 已完成的證據基礎設施

| Contract | ID | 驗證程度 |
|---|---|---|
| Run manifest | `PAPER_RUN_MANIFEST_V2` | static/analytical bundle readback PASS，11 roles、內嵌 lock block；`V1` 仍可讀但永不滿足綁定 gate |
| Run lock binding | `RUN-MANIFEST-LOCK-BINDING-V1` | `LB-01`..`LB-12` PASS（62 tests）；`python -I -S` gate 重跑相符 |
| Experiment matrix | `EXPERIMENT_MATRIX_SPEC_V1` | synthetic 3/3 cells，FAILED/CANCELLED retention |
| Paired statistics/export | `PAIRED_STATISTICS_SPEC_V1` | synthetic 191 artifacts，exact replay；binary paired CI blocked |
| Action-interface pilot | `PILOT-V7-ACTION-INTERFACE-DEV-V1` | 實資料，14 artifacts / 109,520,182 bytes |
| Exposure-censoring audit | `AUDIT-V7-EXPOSURE-CENSORING-V1` | 實資料 + synthetic，AX-01..AX-12 |
| Environment lock | `ENVIRONMENT-LOCK-V1` | 一份實測 record，EL-01..EL-10，60 tests |
| Training-seed variance | `SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1` | **已執行**：1,843,200 timesteps、450 records、replay exact；SV-01..SV-12 |
| Candidate selection | `SELECT-V7-CANDIDATE-FORMAL-V1` | 凍結，rule self-check 通過，SEL-01..SEL-09，47 tests；**不可執行** |
| Second-case exposure censoring | `SECONDCASE-EXPOSURE-CENSORING-WALKER2D-V1` | **已執行**：10 cells、300 records、replay exact；generic `exposure_identification.py` 對 v7 retained evidence bit-exact；V2 schema（P0 reference adequacy）與 budget-probe runner 為已測試軟體；`…-WALKER2D-V2`／`…-HOPPER-V1` 兩個 id 於 2026-09-09 撤回（從未 pin） |

共同性質：fail-closed；`NOT_REACHED`／`NOT_APPLICABLE` 永不等於 PASS；禁止 complete-case deletion；禁止 interval 補值；episode-level 分母為 enforced forbidden denominators；每層皆可由 `python -I -S` stdlib-only process exact 重建。

## 6. 開放 blockers（依根因分類）

### 6.1 Provenance（不可逆）

- v5 warm start 自 gitignored `backend/rl/artifacts/` 下的 v4 artifact（`.gitignore:31`）；v3/v4 在 repo 與磁碟皆不存在；v5 profile 記 `warm_start_policy_id: null` / `planned_timesteps: 2000000`，與 registry 的 `122880` 矛盾；選定 checkpoint 是在另一個 516,096-step run regressed 後選出。→ **`CONDITIONAL_ON_FIXED_WARM_START` 對 v7 line 永久成立**。矛盾刻意記錄不修（`training_profiles.json` 被 `SEEDVAR-AMENDMENT-01` pin 在已 merge 證據之後）。
- v7 兩個 retained bundle 的 environment 為 `ABSENT_UNRECOVERABLE` → `cross_protocol_comparability = NON_VERIFIABLE_ENVIRONMENT`：seed-variance 數值不得與 pilot 數值相減或並排成趨勢。

### 6.2 Exposure censoring（可解，但需要更好的 policy）

- 連 reference arm V7A 都只有 143/150 full exposure。要點識別 between-replicate variance，需要**能穩定跑完 9 s 任務的 policy**。v5 line 做不到（saturation duty 38.42%，v6 reward-only 無改善）。

### 6.3 Statistics

- binary paired CI：無 published golden-case oracle → `PAIRED_BINARY_CI_NOT_IMPLEMENTED_V1`。
- sample size：無 point-valued variance 可算。

### 6.4 Plant credibility

- V1 缺 articulated dynamic、pendulum、energy、solver convergence；V2 全缺。任何 controller 結論的 plant 可信度尚未建立。

### 6.5 Authorization 與 preregistration

- `EP-03` formal authorization **決定已於 2026-09-10 取得**（[receipt](PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10.md)），但 frozen protocol JSON 內該項仍硬寫 `BLOCKING`，而 `assert_executable()` 讀的是該 JSON；改為 `RESOLVED` 需要一次 narrowing-only、execution-before 的 amendment 並重新 pin contract 內的 `PROTOCOL_SHA256`。
- 機器可讀的 authorization evidence **刻意尚未鑄造**：`_require_authorization` 要求 `protocol_sha256` 等於現行 digest，鑄造它等於選定「用現行 post-hoc 規則」這個尚未決定的子選項。
- 只有 internal hash freeze，**無 external（OSF）preregistration**；`PUB-B4` 仍在解封之前，只有專案負責人能做。
- 解除順序：**授權在前、預註冊在中、解封在後**（`EP-01`/`EP-02` 的 sealed-seed guard 在 `PUB-B4` 完成前不得移除）。

### 6.6 工程

- UI：`development_compare_mode` 與 `dynamic_run_trace` 皆 `BROWSER_VISUAL_PENDING`；frontend 不獨立驗證 server config hash。2026-09-16 的介面改版**沒有改變這兩點**——它只動版面與呈現，證據語義、API 與 token 集合都沒動。
- Live：immutable live run identity 與 raw bundle 未實作。
- `requirements.txt` 仍只宣告 `>=` floors。
- Lock 綁定：`RUN-MANIFEST-LOCK-BINDING-V1` 是前向的——sidecar 可被遺漏、`backend/simulator.py` 明示排除、2026-09-08 bundle 未重建。
- 測試現況見 §9（不在此重述）。

## 7. Milestone 歷史

| 日期 | Milestone | 結果 |
|---|---|---|
| 2026-08-26 | V0 hardening、三機 Compare、RL registry | software receipts；blockers 保留 |
| 2026-08-29 | Dynamic run trace、Motion Task V1 | 500 Hz trace bridge；v1 task FAIL 保留 |
| 2026-08-30 | controlled stop、start/stop curriculum、v2–v6 iteration | v5 Live 10/11；saturation FAIL 保留；v6 negative control |
| 2026-08-31 / 09-02 | V1 raw Jacobian replay、analytical fixture | 16/14、4/4 exact；V1 仍 NOT PASS |
| 2026-09-03 / 09-05 | Experiment matrix、paired statistics contracts | synthetic PASS；不構成 scientific PASS |
| 2026-09-06 | v7 action-interface pilot | 3 arms × 30 DEV seeds；no candidate |
| 2026-09-08 | Exposure-censoring audit（frozen bundle） | V7C `-36` pp 確認為 artifact |
| 2026-09-08 | `ENVIRONMENT-LOCK-V1` | 實測 record；reduction-order 證據 |
| 2026-09-08 | `SEEDVAR` 凍結 → Amendment 01 → **執行完成** | V7B 方向 5/5；variance null |
| 2026-09-08 | Pretraining-seed variance 結案（不可量測）；`SELECT` 凍結 | 授權成為唯一前置 |
| 2026-09-08 | 文件重整；[PUBLICATION_PLAN](PUBLICATION_PLAN.md) 建立 | 學術產出路線凍結 V1 |
| 2026-09-08 | `PUB-A1` 第二案例凍結 → push → **執行完成** | `SECOND_CASE_ARTIFACT_REPRODUCED`；兩臂皆 censored（regime R3） |
| 2026-09-08 | 三個 V2 budget probe（pilot） | Walker2d ×2 NEGATIVE；Hopper FOUND 但 reference 退化；exposure-only 規則缺口 |
| 2026-09-09 | 專案負責人決定停止第二案例 V2 線；Track A 重構；[PUBLICATION_PLAN](PUBLICATION_PLAN.md) 升版 V2 | `PUB-A1a` PASS、`PUB-A1b` CLOSED_NOT_ATTAINED；兩個未 pin 的 protocol id 撤回；[TRACK_A_REFRAME](TRACK_A_REFRAME_2026-09-09.md) 為 `PUB-A2` 草稿 |
| 2026-09-09 | `PUB-A0` 關鍵兩篇原文核對（PDF 由專案負責人提供） | 1911.05728、2606.10229 皆不推翻 gap；`KEY_TWO_VERIFIED_GAP_STANDS / REMAINING_U`；gate 未 PASS |
| 2026-09-10 | `PUB-A0` A-C5 補充 scan（preregistration／multiverse） | A-C5 降為 artifact 級併入 A-C4；`KEY_TWO_VERIFIED_AND_A_C5_SCANNED / REMAINING_U`；gate 未 PASS |
| 2026-09-10 | 專案負責人授權 formal evaluation；[PUBLICATION_PLAN](PUBLICATION_PLAN.md) 升版 V3 | `PUB-B0` `AUTHORIZED / SUB_OPTION_OPEN`；protocol 仍不可執行；量測 `SEL-C2` 在 v7 線上幾乎確定不成立；FORMAL seeds 未存取 |
| 2026-09-11 | 動作任務範圍決定；凍結並執行 `R0-REGIME-HORIZON-PROBE-V1` | 不新增跳躍／轉身；`R0` probe 凍結後執行，兩個對比皆 `R0_WINDOW_FOUND`，taxonomy 六格全部有實例；replay bit-exact |
| 2026-09-13 | 凍結並實作 `RUN-MANIFEST-LOCK-BINDING-V1` | lock record 前向綁進 run manifest；`LB-01`..`LB-12` 通過；三個被釘住的 driver／simulator 檔案逐位元未變；V0 blocker 再收窄一次仍未解除 |
| 2026-09-14 | **執行 `TRACKED-LINEAGE-TRAINING-V1`**（[receipt](TRACKED_LINEAGE_TRAINING_RECEIPT_2026-09-14.md)） | 5 replicates × `2,015,232` steps、20 個版控 checkpoint、10 次執行皆 `RUN_LOCK_BOUND`。`PUB-B1` 達成；`PUB-B2` `NOT_ATTAINED`（`0/5` replicate 達 `30/30`，標籤經 amendment 03 更正為 `TL_BUDGET_EXHAUSTED`）。`TL-01`..`TL-08`、`TL-01b`、`TL-CK-01`..`TL-CK-06` 全數通過，故非 `TL_METHOD_FAILURE`。amendment 02 更正 `TL-CK-03` 並加嚴為 `TL-CK-06` |
| 2026-09-14 | `TRACKED-LINEAGE-AMENDMENT-01` + driver／contract 實作 | 更正我自己凍結裡的兩個缺陷（`environment_id` 未指定、`500_000` 整數倍 checkpoint 不可達），皆在任何訓練之前、皆非門檻放寬。`train_ppo.py` 加第三個互斥身分與 protocol 決定的 `checkpoint_interval`；新增 contract 與 65 個雙向測試；三層 digest 補齊。全套 1 failed / 882 passed，無新增失敗 |
| 2026-09-14 | 凍結 `TRACKED-LINEAGE-TRAINING-V1`（[spec](TRACKED_LINEAGE_TRAINING_SPEC.md)） | 兩格由負責人在看到任何曲線之前定案：`GIT_DIRECT` + `500_000`、`30/30`。ROADMAP §9 第 2 項收窄為 scratch。凍結 push 時三個 driver／simulator 檔案逐位元未變；範圍收窄為 `PUB-B1`／`PUB-B2`，`PUB-B3` 另需 protocol。**尚未執行、未產生任何證據** |
| 2026-09-13 | `LOCKBIND-AMENDMENT-01-LB12-SCOPE` | `LB-12` 原本以工作樹比對，等於永久凍結三個檔案；改以 git 讀取本 contract 自己的兩個 commit 比對。非放寬：主張未改、量測更正，且更強。解除了新訓練線必須修改 `train_ppo.py` 的阻礙 |
| 2026-09-16 | `PUB-A0` 再兩篇原文核對（PDF 由專案負責人提供） | `1712.00378`（Pardo）與 `2010.04304`（Learning to Locomote）皆確認為 **learning 端**、不涉量測端 identification；[LITERATURE_MAP §1.1](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md) 兩列由 `U` 升為 `S`，A-C1／A-C2 的 gap 判定不變。狀態 `FOUR_VERIFIED_REMAINING_U`；**gate 仍未 PASS** |

## 8. 下一步

兩條軌道並行，互不阻擋：

**學術（見 [PUBLICATION_PLAN](PUBLICATION_PLAN.md)）**

1. `PUB-A0`：狀態為 **`FOUR_VERIFIED_REMAINING_U`**（2026-09-16）——關鍵兩篇已核對（2026-09-09）、A-C5 補充 scan 已完成（2026-09-10，該項降級）、Pardo `1712.00378` 與 Learning to Locomote `2010.04304` 已核對（2026-09-16，[LITERATURE_MAP §1.1／§7](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md) 兩列升為 `S`）。**唯一剩餘工作**是讀其餘 `U` 條目原文（§1.1 剩餘條目、§1.3–§1.5、§1.7、§2 的 Manski／Tamer 線），需可存取出版方的環境——2026-09-10 重新量測 `arxiv.org` 仍封鎖。**優先三篇**：Colas 2019、Manski 1990／Tamer 2010、Hollenbeck & Wright 2017。另需核對 rl-zoo recipe 數值。
   [BLOCKER] **2026-09-17 更正**：本列原寫「優先四篇」並把 **Pardo 2018 列為待核對**，漏掉 2026-09-16 的核對結果；gate 狀態標籤也未寫進本文件。原措辭記於此以供對照（原清單四篇為 Pardo 2018、Colas 2019、Manski 1990／Tamer 2010、Hollenbeck & Wright 2017），判定以 [LITERATURE_MAP §1.1／§7](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md) 為準。成因見 [PROJECT_ASSESSMENT §4.3.1](PROJECT_ASSESSMENT_2026-09-16.md)。
2. `PUB-A2` claim freeze：A0 之後，把 [TRACK_A_REFRAME §5–§7](TRACK_A_REFRAME_2026-09-09.md) 凍結。**不再開任何第二案例 probe 或 protocol**；`PUB-A1b` 已關閉並寫入 Limitations。輸入之一是 [`R0` regime probe](R0_REGIME_PROBE_RECEIPT_2026-09-11.md)，已於 2026-09-11 執行完成（兩個對比皆 `R0_WINDOW_FOUND`）；其「regime 由 horizon 決定」的量測應寫入 §3 taxonomy 與 A-C3 論述。
3. `PUB-B0` 授權已取得（2026-09-10）。剩餘依序：專案負責人決定 [PUBLICATION_PLAN §5](PUBLICATION_PLAN.md) 的兩個子問題（規則、FORMAL 範圍花在哪條線）→ `PUB-B4` OSF preregistration（只有負責人能做）→ `SELECT-AMENDMENT-01`（`EP-03` narrowing amendment 並重新 pin digest）→ `EP-01`／`EP-02` amendment。在子問題未決前不鑄造 authorization evidence、不解封 `20000–20029`。

**工程（見 [ROADMAP](ROADMAP.md) §9）**

1. [DONE 2026-09-14] [`TRACKED-LINEAGE-TRAINING-V1`](TRACKED_LINEAGE_TRAINING_SPEC.md) 已執行完成（[receipt](TRACKED_LINEAGE_TRAINING_RECEIPT_2026-09-14.md)）。**下一個決定是 receipt §10 的四條路線之一**（提高 budget／引入 curriculum／改 reward 或環境／改以其他方式解 `PUB-B3`），全部需要**新的 protocol 版本**並揭露它是在已知本結果的情況下設計的；`2,000,000` 步上限不得事後上調，20 個已保留 checkpoint 不得刪除。

2. Compare / Dynamic trace 的 browser visual verification（Playwright）。
3. V1 articulated dynamic／pendulum／energy oracles。
4. Lock 綁定的三項殘餘缺口。**第一項（sidecar 可被遺漏）在本線上已實際示範關閉**：`TRACKED-LINEAGE-TRAINING-V1` 的 10 次執行（5 訓練 + 5 評估）全部經 `bind_run_lock.py`，gate 全部回 `RUN_LOCK_BOUND`，且 `TL-CK-05` 把這件事寫成驗收條件而非慣例。缺口本身仍在——直接呼叫 driver 依然會產生 `RUN_LOCK_UNBOUND` 的 run——但現在有一條線證明了走 wrapper 是可行且不需要修改 driver 的。後兩項（`simulator.py` 明示排除、2026-09-08 bundle 不可重驗）各自仍需獨立的 contract。

## 9. 測試現況

`backend/`：**1 failed / 1003 passed**（2026-09-17，`315.31` s，工作樹為 `70b8db3` 加上本次變更）。數字逐步對得起來：2026-09-14 的 `941` ＋7（介面改版的兩支測試檔：`test_warning_items.py` 5 個、`test_decision_kind.py` 2 個）＝ `948`（`9f871ac`）；＋2（PR #25 補上的 `record_start` 時長邊界與預設值回歸測試，均在 `test_run_trace.py`）＝ `950`（`979e73b`）；＋27（`GATE-STATUS-SINGLE-SOURCE-V1` 的 `test_gate_status_contract.py`）＝ `977`（`01afa60`）；＋26（`DERIVED-CLAIM-CONSISTENCY-V1` 的 `test_derived_claim_contract.py`）＝ **`1003`**。失敗項仍是同一個、未放寬的 reduction-order 差異——已於 2026-09-17 以 `git stash` 在合併基底上重跑確認**該失敗先於這一系列變更存在**，無新增失敗。

2026-09-14 那一輪的逐 commit 實測記錄保留於此：`5b707cb`（V2 contract 之前的 main）收集 `892`；＋`32`（`TRACKED-LINEAGE-TRAINING-V2` contract）＝ `924`，即先前記錄的 1 failed / 923 passed；＋`2`（guard dispatch）＋`2`（resume 路徑）＋`8`（保留線）＝ `936`，即 PR #20 合併後的 main；＋`6`（V2 執行線：replicate 數推導、relocated lock、標籤）＝ **`942`** ＝ 1 failed / 941 passed。更早的記錄為 1 failed / 882 passed、1 failed / 816 passed 與 1 failed / 754 passed。

[BLOCKER] **一次自造的假 regression，記於此以免重演。** 該次全套曾出現第二個失敗 `test_paper_data_contract.py::test_v1_oracle_builds_integrity_validated_regression_bundle`（`manifest["status"] == 'FAILED'`）。原因不是程式：`build_v1_paper_bundle` 以 `source_before == source_after` 比對建置前後的 git 身分，而我在那次 runner 執行期間執行了 `git commit`，HEAD 於 bundle 建置中途改變。在完全不碰 repo 的情況下重跑即回到 1 failed。**那道 clean-git guard 沒有壞，它正確地抓到了我**——「runner 執行期間不得改動 tracked 檔案」這條規則適用於全套測試，不只訓練。失敗項仍是同一個 `test_v1_analytical_suite.py::test_stdlib_replay_passes_exact_synthetic_fixture`（`PRIMARY_CASE_RECEIPT_IDENTITY`），與 §4.3 的 reduction-order 差異同源，記錄為量測結果、未放寬。

[RESULT] 2026-09-13 就地定位：fixture 由 `v1_analytical_suite.py:640` 的 `float(np.mean([...]))` 產生，replay 由 `v1_analytical_replay.py:952` 的 `sum(...) / len(...)` 重算，`mean_vertical_grf_n` 為 `196.2` 對 `196.19999999999854`，差 `1.46e-12`，略高於 `1.0e-12` 門檻。把四個 thread-count 環境變數 pin 回 `1` **不會**改變結果，故不是 thread drift，而是 §4.3 的 reduction-order 差異本身。門檻未放寬。
