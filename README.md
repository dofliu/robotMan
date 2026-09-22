# 人形機器人設計篩選與教學模擬原型

> Humanoid Design Screening and Teaching Simulation Prototype

Repository：[github.com/dofliu/robotMan](https://github.com/dofliu/robotMan) ｜ Development：`0.2.0-dev` ｜ License：MIT

本專案是 **SIM-only、reduced-order** 的人形機器人設計篩選與教學原型，同時是一個 **verification-aware 的 humanoid control 研究測試平台**。它可用來探索幾何、質量、致動器示意參數、步態與控制策略之間的關係，並在凍結的 MuJoCo plant 上以可重現、可統計、可追溯的方式比較控制／訓練方法。它**尚未**完成足以支持實體硬體選型、採購、安全判定或效能保證的 physical validation。

## 目前可信邊界

- [SOURCE] 程式包含參數化步態、MuJoCo 模型、分析模式、即時 forward simulation、控制器、RL pipeline，以及一組 fail-closed 的證據契約（run manifest、artifact inventory、experiment matrix、paired statistics、exposure-censoring audit、environment lock、training-seed variance、candidate selection）。
- [INFERENCE] 所有既有數字都是特定程式版本與具名 protocol 下的 `DEVELOPMENT` evidence；沒有任何 `FORMAL_EVALUATION` run 存在。
- [BLOCKER] 五道 V&V gate（V0–V4）一道未通過；`paper_data_ready = false`。完整清單見 [PROJECT_STATUS](docs/PROJECT_STATUS.md)。

介面中的「通過」、「穩定」、「可行」只代表目前數值模型與規則下的 screening signal，不等同實體機器人驗證結果。Claim 邊界見 [MODEL_CARD](docs/MODEL_CARD.md)。

## 現況一覽

| 面向 | 狀態 | 細節 |
|---|---|---|
| 專案成熟度 | `progress: 0`（以 V&V gate 通過數計，不以功能數計） | [PROJECT_STATUS §0](docs/PROJECT_STATUS.md) |
| V&V gates | V0 PARTIAL、V1 PARTIAL、V2–V4 NOT STARTED | [PROJECT_STATUS §1](docs/PROJECT_STATUS.md) |
| Paper-data gates | PDR-0..8 無一 PASS；`paper_data_ready = false` | [PAPER_DATA_READINESS](docs/PAPER_DATA_READINESS.md) |
| Gate 狀態一致性 | 33 個 gate、54 個站點由 `GATE-STATUS-SINGLE-SOURCE-V1` fail-closed 比對；狀態改了沒同步到 mirror 即測試失敗 | [GATE_STATUS_SINGLE_SOURCE](docs/GATE_STATUS_SINGLE_SOURCE.md) |
| 教學／研究邊界 | `MODULE-BOUNDARY-V1`：教學應用 **16 個模組、5,066 行**（2026-09-22 重新量測；第 16 個是 Capture-point 開發對照組 `controller_cp`），**不 import 任何研究模組**；唯一的跨界 import 已於 2026-09-17 切斷，`train_ppo.py` 逐位元未動。**教學產品的檔案仍未搬動**（工具組已於 2026-09-19 搬出，見下一列） | [TEACHING_BOUNDARY](docs/TEACHING_BOUNDARY.md) |
| 工具組邊界與可攜性 | 同一個 `MODULE-BOUNDARY-V1` 契約：工具組閉包**恰好 7 個模組、5,508 行、本地相依為零**（已搬至 `backend/toolkit/`），而 13 個專案模組 import 它。**但邊界乾淨 ≠ 今天拿得走**——逐模組審計，**3 個**可原封不動使用 | [TOOLKIT_PORTABILITY](docs/TOOLKIT_PORTABILITY.md) |
| 工具組已搬出 | **產品 B 於 2026-09-19 搬進 `backend/toolkit/`**：9 個檔案 **8 個逐位元未動**，兩個邊界閉包前後相同。搬下去才看到三件事——邊界契約會**瞎掉但照印綠燈**、工具組有**第八個檔案**是 AST 看不到的子行程腳本、**五份凍結檔案**的路徑從此停在舊值 | [TOOLKIT_MOVE](docs/TOOLKIT_MOVE_2026-09-19.md) |
| 研究線已封存 | **§4.2 的封存已於 2026-09-19 執行**：22 個檔案進 `backend/archive/`，證據與 digest 未動。**但測試沒有變少（1,062 → 1,062）**——原文預期的「942 → 520」會停掉三個**仍在線上檔案**的不可變性 pin；另有一個 contract 因自己的 pin 而搬不動。**文件部分於 2026-09-20 補做**：17 份進 `docs/archive/`（`docs/` 73 → 64），**3 份因內容 digest 被凍結證據釘住而結構性搬不動**，7 份留轉址 | [RESEARCH_LINE_ARCHIVE](docs/RESEARCH_LINE_ARCHIVE_2026-09-19.md)、[DOC_ARCHIVE](docs/DOC_ARCHIVE_2026-09-20.md) |
| 可攜性六項決定 | §8 的六項逐項重新量測：**三項的前提被推翻**（決定 3 的代價是 **0 份**不是 41 份 lock record；決定 5 的可攜性問題早已解決；決定 6 的方向相反，照做會弄壞發布的安裝方式）。**四個真正的問題已於 2026-09-19 回答，皆為維持現狀** | [TOOLKIT_PORTABILITY_DECISIONS](docs/TOOLKIT_PORTABILITY_DECISIONS_2026-09-19.md) |
| 工具組對外使用 | 外部 RL 專案今天能拿走的是**三個檔案**（`exposure_identification`、`environment_lock`、`run_manifest_lock`），複製進同一個目錄即可；`rl.bind_run_lock` 用 31 行自寫取代。**無 site-packages 時 gate 回 `RUN_LOCK_INSUFFICIENT` 而非 `BOUND`，那是正確行為** | [TOOLKIT_USAGE](docs/TOOLKIT_USAGE.md) |
| 衍生 claim 一致性 | `DERIVED-CLAIM-CONSISTENCY-V1`：待核文獻清單與地圖的 `U`／`S` 等級綁定，10 篇論文、3 個站點；清單裡出現已核實的論文即測試失敗 | [DERIVED_CLAIM_CONSISTENCY](docs/DERIVED_CLAIM_CONSISTENCY.md) |
| 最強的一個結果 | V7B 相對 V7A 的 saturation duty method-level bound `[-13.503408, -12.435259]` pp，排除 0，5/5 independent training replicates 方向可識別；**條件於一個不可重建的 warm start** | [PROJECT_STATUS §4](docs/PROJECT_STATUS.md) |
| 被推翻的一個結果 | V7C 表面上的 `-36` pp 改善經量測確認為 exposure artifact | [PROJECT_STATUS §4.2](docs/PROJECT_STATUS.md) |
| 學術產出 | 三條路線；Track A 於 2026-09-09 重構為「censoring regime 的評估效度研究」（`PUBLICATION-PLAN-V3`）：`PUB-A1a` PASS（Walker2d-v5 第二案例）、`PUB-A1b` CLOSED_NOT_ATTAINED（三個 budget probe 後停止）；`PUB-A0` 關鍵兩篇已原文核對、gap 仍成立，A-C5 補充 scan 完成後降為 artifact 級（其餘條目待核）；下一步 `PUB-A2` claim freeze，其輸入之一是 2026-09-11 凍結的 `R0` regime probe | [PUBLICATION_PLAN](docs/PUBLICATION_PLAN.md)、[TRACK_A_REFRAME](docs/TRACK_A_REFRAME_2026-09-09.md) |
| 證據環境綁定 | `ENVIRONMENT-LOCK-V1` 量測環境身分；`RUN-MANIFEST-LOCK-BINDING-V1`（2026-09-13）以 SHA-256 把 lock record 綁進 run manifest，fail-closed。**前向**，V0 blocker 收窄未清除 | [RUN_MANIFEST_LOCK_BINDING_RECEIPT](docs/receipts/RUN_MANIFEST_LOCK_BINDING_RECEIPT_2026-09-13.md) |
| 新訓練線 | `TRACKED-LINEAGE-TRAINING-V1` 於 2026-09-14 **執行完成**：scratch、5 replicates、20 個 checkpoint 進版控（`38.0 MiB`）、10 次執行皆 `RUN_LOCK_BOUND`。**`PUB-B1` 達成**（provenance 可重建的訓練線存在）；**`PUB-B2` 未達成**——5 個 replicate 的 full exposure 皆 `0/30`，標籤 **`TL_BUDGET_EXHAUSTED`**（曲線在上限處仍未收斂，見 amendment 03 的更正）。**門檻不得下調，上限亦不得因「再多跑一點」而上調** | [receipt](docs/archive/TRACKED_LINEAGE_TRAINING_RECEIPT_2026-09-14.md) |
| 加倍預算的續訓線 | `TRACKED-LINEAGE-TRAINING-V2` 於 2026-09-14 **執行完成**：由 V1 各 replicate 保留的 `1,999,968` 步 checkpoint 續訓，各再加 `2,000,000` 步（realized `4,015,200`）。獎勵升到 `283.1`–`295.3`（`+51.5`–`+66.5`）、平均存活升到 `2.725`–`3.458` s，而**完整曝露仍是 `0/30`，五個全部**。五個皆未收斂，且**四個的末四分位斜率比首四分位還大**——曲線更陡了，曝露沒動。標籤 **`TL2_BUDGET_EXHAUSTED`**，由 contract runner 在保留證據上算出。**`PUB-B2` 仍未達成；規格禁止以此為由再加預算** | [V2 receipt](docs/archive/TRACKED_LINEAGE_TRAINING_V2_RECEIPT_2026-09-14.md) |
| **專案評估（2026-09-16）** | 給負責人的**決策文件**：核心 robotics + 應用 `6,871` 行、前端 `3,561` 行，證據契約 `29,294` 行（**1 : 4.3**），其中約 `15,800` 行服務的研究線已結案；**沒有不可達程式**。機器人：v5 會走（10/11）但 checkpoint 是看結果後挑的，所有可重建的線全在 `STEADY_WALK` 起點跌倒，量化診斷指向獎勵形塑而非預算。**價值**：robotics 研究弱；評估效度研究**真的有一篇**（Track A，證據已齊、**不需 `PUB-B2`**）；教學工具有實質價值且與研究契約**完全解耦**。**關鍵觀察：`PUB-B2` 的理由在 09-09 Track A 重構時就消失了。** 三個去向選項見 §5——**負責人尚未決定** | [PROJECT_ASSESSMENT](docs/PROJECT_ASSESSMENT_2026-09-16.md) |
| 動作任務範圍 | 2026-09-11 決定現在**不**新增跳躍／轉身；順序為先綁 lock record 與建有版控 lineage 的新訓練線，轉身需 `PUB-B2`、跳躍需 V1 PASS | [MOTION_SCOPE_DECISION](docs/MOTION_SCOPE_DECISION_2026-09-11.md) |
| 下一個決策 | formal evaluation 已於 2026-09-10 授權；剩兩個子問題：用現行 post-hoc 規則或先預註冊替代規則、唯一未檢視的 FORMAL seed 範圍花在 v7 線或新訓練線 | [PUBLICATION_PLAN §5](docs/PUBLICATION_PLAN.md)、[PUB_B0 receipt](docs/receipts/PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10.md) |
| 控制器比較（2026-09-22） | 四個行走控制器（含新加的 Capture-point 對照組 `cp`，**非新方法**）在凍結任務上**全部 FAIL**：5／6／5／5 of 11；**CP 沒有贏過 Raibert**（跌倒 2.906 s 對 3.282 s）。推力掃描：三個 deterministic 控制器連 0 N 都在 ~2 s 自行倒下，`rl` 至 160 N 站滿 3 s 窗。現有方法**沒有創新**，專案也未如此宣稱。`DEVELOPMENT_COMPARISON_ONLY` | [CONTROLLER_COMPARISON_2026-09-22](docs/CONTROLLER_COMPARISON_2026-09-22.md) |
| 測試 | `backend/` **1 failed / 1071 passed**（2026-09-22，`430.68` s，1,072 收集，工作樹 `0dca910`，`python3 -X utf8 -m pytest backend/ -p no:cacheprovider`；比前次多的 10 個全在 `test_controller_cp.py`）。那一個失敗是在具名 environment lock 下**記錄為量測結果、未放寬**的 reduction-order 差異——看到它不必修 | [PROJECT_STATUS §9](docs/PROJECT_STATUS.md)、`STATUS.yaml` 的 `test_suite_status` |

## 兩種模式

| 模式 | 實際計算內容 | 目前可支持的用途 | 不可宣稱 |
|---|---|---|---|
| 分析模式 | prescribed kinematics → analytical GRF/contact schedule → MuJoCo inverse dynamics | 相對趨勢、敏感度、教學與早期 design screening | 已求得物理可行 contact wrench、硬體一定帶得動、實機穩定 |
| 即時互動 | MuJoCo forward dynamics + simulated contact + torque-limited controller | 觀察特定 simulated plant 中的接觸、跌倒與控制反應 | 「真實接觸動力學」、實測抗推力、sim-to-real 能力 |

分析模式沒有由 contact solver 求解腳底接觸；即時互動模式則使用 MuJoCo 的 forward contact simulation。兩者的 plant、能量定義與證據用途不同，不應把數字直接混成同一種 validation evidence。

第一模式提供兩個 analysis sources：`Reference 估算` 是原有 prescribed trajectory；`Dynamic Trace` 則讀取第二模式以 500 Hz physics-step 保存的 MuJoCo realized simulation。後者仍是 simulated output，不是實體量測。見 [DYNAMIC_RUN_TRACE_SPEC](docs/DYNAMIC_RUN_TRACE_SPEC.md)。

介面於 2026-09-16 重新整理：四個分頁、每頁一次只看一件事，警告與決策日誌分類顯示，圖表一個量一條 y 軸並加上相位色帶與事件標記。**功能沒有移除，證據 token 也沒有減少**——完整 token 收在右上角「證據狀態」抽屜。逐頁說明見 [USAGE §3](docs/USAGE.md)。

## Verification 與 Validation

- **Verification**：程式是否正確實作已定義的 equations、units、constraints 與數值方法。
- **Validation**：以獨立的實體資料、bench、HIL 或整機量測，確認模型對真實系統是否足夠準確。

專案整體狀態為 **NOT PHYSICALLY VALIDATED**。Gate 與 evidence matrix 見 [VV_PLAN](docs/VV_PLAN.md)。

## 已有 prototype 能力

- 12 關節 reduced-order humanoid、走路／跑步 prescribed gait
- 馬達／減速機示意參數、質量配置與相對使用率 screening
- CoM、ZMP 與支撐多邊形視覺化
- 理想 LiDAR raycast 與規則式障礙處理
- MuJoCo 即時 forward simulation、推力輸入與控制器狀態顯示
- trajectory tracking、Raibert、PPO policy 的 nominal scenario 比較
- 三機同步比較模式：三個獨立 MuJoCo plants 接收相同命令，assist 預設關閉、跌倒不自動修復
- 正式動作任務 V1：`stand → start → steady walk → stop` 的固定 phase、500 Hz trace 與逐項 PASS/FAIL
- `WALK → STOPPING → STAND` controlled transition 與可擴充 Motion Primitive dispatcher
- RL 訓練頁：依家族分組顯示 fixed-speed／command-conditioned profiles、seed、training budget 與 evidence status
- Registry-gated Motion Task policies：48-D curriculum-v2 與 51-D phase-observable-v5
- V1 static contact oracle 與 analytical fixture：raw Jacobian／wrench 保存與 stdlib-only replay
- 證據契約層：experiment matrix、paired statistics/export、exposure-censoring audit、environment lock、training-seed variance、candidate selection，每一層皆可由 `python -I -S` 獨立 exact 重建

這些是 feature inventory，不代表 V&V gate 已通過。

## 快速啟動

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend/requirements-dev.txt -r backend/requirements-rl.txt

Set-Location frontend
npm ci
npm run build
Set-Location ..
python -X utf8 backend/main.py
~~~

開啟 http://127.0.0.1:8710。

`requirements-rl.txt` 提供執行既有 policy 所需的套件範圍，**不是** frozen training environment；`requirements.txt` 仍只宣告 `>=` floors。要重現任何數值結果，必須以 [ENVIRONMENT_LOCK_SPEC](docs/ENVIRONMENT_LOCK_SPEC.md) 的 lock record 比對 —— 版本號相同不保證數值相同（見 [PROJECT_STATUS §4.3](docs/PROJECT_STATUS.md)）。

只使用分析模式與非 RL controller 時，可僅安裝 `backend/requirements-dev.txt`。

測試：

~~~powershell
python -m pytest backend -q
~~~

以上是本專案安裝與測試指令的**唯一出處**；[USAGE](docs/USAGE.md) 與 [REPOSITORY_GUIDE](docs/REPOSITORY_GUIDE.md) 指回此處，不重複。

## Repository 內容

追蹤 source、tests、docs、frontend lockfile、registry 指定的三個 inference artifacts，以及已保留的證據 bundle（`backend/environment_locks/`、`second_case_evidence/`、`seed_variance_evidence/`、`r0_probe_evidence/`）。完整 tracked/excluded 清單、驗證與發布檢查見 [REPOSITORY_GUIDE](docs/REPOSITORY_GUIDE.md)。

[BLOCKER] `backend/rl/artifacts/` 被 gitignore 這件事**已經永久毀掉 v7 line 的 pretraining provenance**（見 [infeasibility receipt](docs/archive/V7_PRETRAINING_SEED_VARIANCE_INFEASIBILITY_RECEIPT_2026-09-08.md)）。任何新的訓練線都必須把 checkpoint lineage 放進版控或 immutable storage，並經 `backend/rl/bind_run_lock.py` 執行以取得 `RUN_LOCK_BOUND`。

## Nominal benchmark snapshot

`comparison_report.md` 保留既有 deterministic nominal snapshot，供回歸診斷與教學敘事參考。它不是多 seed、Monte Carlo 或獨立重複實驗，沒有 confidence interval，不能當成控制器普遍優劣、硬體能力或實機抗擾動證據。正式比較必須依 [EXPERIMENT_PROTOCOL](docs/EXPERIMENT_PROTOCOL.md)。

## 文件導覽

### 入口、狀態與規劃

| 文件 | 單一職責 |
|---|---|
| [PROJECT_STATUS](docs/PROJECT_STATUS.md) | 人類可讀的進度總覽：gates、flags、已量測結果、blockers、下一步 |
| [`STATUS.yaml`](STATUS.yaml) | 機器可讀的權威狀態 |
| [PUBLICATION_PLAN](docs/PUBLICATION_PLAN.md) | 學術產出規劃：三條 track、PUB gates、寫作規範、不可宣稱清單（V2） |
| [TRACK_A_REFRAME_2026-09-09](docs/TRACK_A_REFRAME_2026-09-09.md) | Track A 重構：censoring regime 分類、claim → evidence 對照、不可宣稱清單、figure／table 計畫、`PUB-A2` 草稿 |
| [R0_REGIME_PROBE_SPEC](docs/R0_REGIME_PROBE_SPEC.md) | 凍結的 `R0-REGIME-HORIZON-PROBE-V1`：以截斷 horizon 探測無 censoring 的比較是否可達；兩段式 reference-adequacy 規則 |
| [R0_REGIME_PROBE_RECEIPT_2026-09-11](docs/archive/R0_REGIME_PROBE_RECEIPT_2026-09-11.md) | probe 執行結果：兩個對比皆 `R0_WINDOW_FOUND`；同一批 policy 與 seed 只改 horizon 就跨 regime |
| [MOTION_SCOPE_DECISION_2026-09-11](docs/MOTION_SCOPE_DECISION_2026-09-11.md) | 動作任務範圍決定：現在不新增跳躍／轉身，以及新增動作的凍結順序 |
| [TRACKED_LINEAGE_TRAINING_SPEC](docs/TRACKED_LINEAGE_TRAINING_SPEC.md) | 凍結的 `TRACKED-LINEAGE-TRAINING-V1`：`PUB-B1`／`PUB-B2` 的新訓練線——scratch、5 replicates、版控 checkpoint lineage、`30/30` full-exposure 門檻；含三份 amendment |
| [TRACKED_LINEAGE_TRAINING_RECEIPT_2026-09-14](docs/archive/TRACKED_LINEAGE_TRAINING_RECEIPT_2026-09-14.md) | 執行結果：`PUB-B1` 達成、`PUB-B2` `NOT_ATTAINED`（`0/5` replicate 達標）、失敗型態量測、claim boundary，以及 §12 的標籤更正記錄 |
| [TRACKED_LINEAGE_TRAINING_V2_SPEC](docs/TRACKED_LINEAGE_TRAINING_V2_SPEC.md) | 凍結的 `TRACKED-LINEAGE-TRAINING-V2`：在已知 V1 結果之後設計並據實揭露的加倍預算續訓線 |
| [TRACKED_LINEAGE_TRAINING_V2_RECEIPT_2026-09-14](docs/archive/TRACKED_LINEAGE_TRAINING_V2_RECEIPT_2026-09-14.md) | 執行結果：`TL2_BUDGET_EXHAUSTED`、`0/5` replicate 達標、曲線在上限處更陡、七個缺陷的記錄，以及一個先立後撤的觀察 |
| [PROJECT_ASSESSMENT_2026-09-16](docs/PROJECT_ASSESSMENT_2026-09-16.md) | 專案評估（決策文件）：實測盤點、四面向價值判斷、獎勵結構診斷、可拆／可封存的架構、三個去向選項與代價 |
| [GATE_STATUS_SINGLE_SOURCE](docs/GATE_STATUS_SINGLE_SOURCE.md) | gate 狀態的單一權威來源：`GATE-STATUS-SINGLE-SOURCE-V1` 的規則、33 個 gate 與 54 個站點的 authority／mirror 關係、明確不涵蓋的範圍；由 `backend/gate_status_contract.py` fail-closed 檢查 |
| [TEACHING_BOUNDARY](docs/TEACHING_BOUNDARY.md) | 教學模擬器的邊界：`MODULE-BOUNDARY-V1` 的 teaching 邊界，教學進入點的遞移 import 閉包必須恰好等於登錄清單；研究模組跑進來或清單過期皆 fail closed |
| [TOOLKIT_PORTABILITY](docs/TOOLKIT_PORTABILITY.md) | 實驗工具組的邊界與**可攜性審計**：同一契約的 toolkit 邊界（函式庫不得反向碰專案），加上七個模組逐一的 blocking／friction 分類，以及三件需要擁有者決定的事 |
| [TEST_REPORT_2026-09-20](docs/TEST_REPORT_2026-09-20.md) | **全面測試報告**——1,062 測試（1,061 過／1 既有失敗）、三個契約、796 個連結、五個畫面的實際截圖與數據 |
| [CONTROLLER_COMPARISON_2026-09-22](docs/CONTROLLER_COMPARISON_2026-09-22.md) | **四控制器開發比較**——現有方法有沒有創新（沒有）、新加的 Capture-point 對照組（也不是新的、沒贏過 Raibert）、凍結任務 11 項判準、推力掃描、速度掃描，7 張圖與 `summary.json`；`DEVELOPMENT_COMPARISON_ONLY` |
| [`docs/receipts/`](docs/receipts/README.md) | **實作 receipt 索引**——14 份，2026-09-20 由 `docs/` 搬入；仍然有效，只是不是規劃文件 |
| [`docs/archive/`](docs/archive/README.md) | **已結案研究線的 receipt 與 spec 索引**——17 份，2026-09-20 搬入；另 **3 份 spec 因 digest 被凍結證據釘住而搬不動**（改連結就是改位元組），7 份在原路徑留轉址。記錄見 [DOC_ARCHIVE](docs/DOC_ARCHIVE_2026-09-20.md) |
| [RESEARCH_LINE_ARCHIVE](docs/RESEARCH_LINE_ARCHIVE_2026-09-19.md) | **封存記錄**：已結案研究線進 `backend/archive/` 的逐項改動、為什麼測試必須繼續跑、以及那個因自己的 pin 而搬不動的 contract |
| [TOOLKIT_MOVE](docs/TOOLKIT_MOVE_2026-09-19.md) | **搬移記錄**：產品 B 進 `backend/toolkit/` 的逐檔改動、`sys.path` shim 的設計、以及搬移過程中量到的三件事（契約 fail-open、第八個檔案、五份凍結檔案的舊路徑） |
| [TOOLKIT_PORTABILITY_DECISIONS](docs/TOOLKIT_PORTABILITY_DECISIONS_2026-09-19.md) | **六項可攜性決定的結案記錄**：哪三項的前提被量測推翻、哪四個問題真的還在等擁有者，每個都附量測過的代價與「不答＝維持現狀」的預設 |
| [TOOLKIT_USAGE](docs/TOOLKIT_USAGE.md) | **對外使用說明**：外部 RL 專案怎麼用這套工具組。只寫今天真的做得到的事——三個可攜模組、31 行取代 `bind_run_lock`、識別區間的完整流程、四個標籤的實測，以及四個擋死模組的原因 |
| [DERIVED_CLAIM_CONSISTENCY](docs/DERIVED_CLAIM_CONSISTENCY.md) | 衍生 claim 的一致性：`DERIVED-CLAIM-CONSISTENCY-V1`，把「從文獻核實等級算出來的待核清單」與地圖綁在一起；補上 gate 契約明寫不涵蓋的那一類失效 |
| [ROADMAP](docs/ROADMAP.md) | V0–V4 gate-first 工程工作順序 |
| [RESEARCH_EXECUTION_PLAN](docs/RESEARCH_EXECUTION_PLAN.md) | model validity 與 method effectiveness 雙證據鏈、RQ、P-stage gates |
| [PAPER_DATA_READINESS](docs/PAPER_DATA_READINESS.md) | paper-data-first 架構、run bundle、PDR gates、統計與文獻依據 |
| [CHANGELOG](CHANGELOG.md) | development release 變更紀錄 |

### 使用與規範

| 文件 | 單一職責 |
|---|---|
| [USAGE](docs/USAGE.md) | 安裝、操作與結果解讀 |
| [REPOSITORY_GUIDE](docs/REPOSITORY_GUIDE.md) | Clone/setup、tracked/excluded artifacts、驗證與發布規則 |
| [CONVENTIONS](docs/CONVENTIONS.md) | 開發與 evidence governance 規範、evidence labels |
| [MODEL_CARD](docs/MODEL_CARD.md) | intended use、out-of-scope、限制與 evidence labels |
| [HARDWARE_DATA_PROVENANCE](docs/HARDWARE_DATA_PROVENANCE.md) | datasheet、CAD/BOM、bench data 與 demo catalog 的分級 |

### 架構、任務與介面規格

| 文件 | 單一職責 |
|---|---|
| [ARCHITECTURE](docs/ARCHITECTURE.md) | 兩種 simulation pipeline 與資料邊界 |
| [METRIC_DEFINITIONS](docs/METRIC_DEFINITIONS.md) | analysis runtime 指標的公式、窗口、命名與限制 |
| [DYNAMIC_RUN_TRACE_SPEC](docs/DYNAMIC_RUN_TRACE_SPEC.md) | 500 Hz realized trace 到工程分析的 raw trace contract |
| [COMPARE_MODE_SPEC](docs/COMPARE_MODE_SPEC.md) | 三機同步比較的公平性、WebSocket contract、失敗語義 |
| [MOTION_TASK_SPEC](docs/MOTION_TASK_SPEC.md) | 正式動作任務、固定 phase/gait、可量測成功條件 |
| [MOTION_PRIMITIVE_SPEC](docs/MOTION_PRIMITIVE_SPEC.md) | action dispatcher、controlled stop state machine |
| [RL_POLICY_TRAINING](docs/RL_POLICY_TRAINING.md) | RL inference／training 邊界、policy registry、profiles |

### V&V 與證據契約

| 文件 | 單一職責 |
|---|---|
| [VV_PLAN](docs/VV_PLAN.md) | requirement-to-evidence matrix、gates 與 SIL/HIL/bench 邊界 |
| [EXPERIMENT_PROTOCOL](docs/EXPERIMENT_PROTOCOL.md) | run classes、frozen configuration、seed、hash、raw artifacts |
| [V1_ORACLE_SPEC](docs/V1_ORACLE_SPEC.md) | static double-support forward–inverse numerical oracle |
| [V1_ANALYTICAL_SUITE_SPEC](docs/V1_ANALYTICAL_SUITE_SPEC.md) | single-support、known-payload、time-step fixture contract |
| [EXPERIMENT_MATRIX_CONTRACT](docs/EXPERIMENT_MATRIX_CONTRACT.md) | controller × seed × scenario exact matrix 與 completeness receipt |
| [PAIRED_STATISTICS_CONTRACT](docs/PAIRED_STATISTICS_CONTRACT.md) | paired estimand、failure/null/censoring semantics、CI、paper input |
| [ENVIRONMENT_LOCK_SPEC](docs/ENVIRONMENT_LOCK_SPEC.md) | locked/observed 分界、behaviour fingerprints、verification semantics |
| [RUN_MANIFEST_LOCK_BINDING_SPEC](docs/RUN_MANIFEST_LOCK_BINDING_SPEC.md) | lock record 與 run manifest 之間的綁定：範圍、兩個 digest 的詞彙、五個 fail-closed 標籤 |
| [V7_ACTION_INTERFACE_PILOT_SPEC](docs/archive/V7_ACTION_INTERFACE_PILOT_SPEC.md) | v7 三臂 action math、seeds、acceptance、claim boundary |
| [V7_EXPOSURE_CENSORING_AUDIT_SPEC](docs/archive/V7_EXPOSURE_CENSORING_AUDIT_SPEC.md) | read-only audit 的 horizon、censoring vocabulary、identification bounds |
| [TRAINING_SEED_VARIANCE_SPEC](docs/archive/TRAINING_SEED_VARIANCE_SPEC.md) | independent training replicates、replicate-level analysis unit、禁止 selection |
| [V7_CANDIDATE_SELECTION_SPEC](docs/archive/V7_CANDIDATE_SELECTION_SPEC.md) | 凍結的 selection 規則、post-hoc 揭露、sealed FORMAL、授權閘 |
| [SECOND_CASE_EXPOSURE_CENSORING_SPEC](docs/archive/SECOND_CASE_EXPOSURE_CENSORING_SPEC.md) | PUB-A1 第二案例：Walker2d-v5 上 exposure-censoring 機制的凍結 protocol、預測與 falsifier |

### 文獻

| 文件 | 單一職責 |
|---|---|
| [LITERATURE_MAP_2026-08-30](docs/LITERATURE_MAP_2026-08-30.md) | humanoid locomotion、sim-to-real、residual/hybrid control 方向對照 |
| [LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY](docs/LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md) | exposure censoring、partial identification、statistical unit、numerical reproducibility 的既有工作與 Track A 的定位 |

### Receipts（依日期）

| 文件 | 內容 |
|---|---|
| [V0_IMPLEMENTATION_RECEIPT_2026-08-26](docs/receipts/V0_IMPLEMENTATION_RECEIPT_2026-08-26.md) | 第一批 V0 hardening |
| [COMPARE_RL_IMPLEMENTATION_RECEIPT_2026-08-26](docs/receipts/COMPARE_RL_IMPLEMENTATION_RECEIPT_2026-08-26.md) | 三機比較、registry、training smoke |
| [DYNAMIC_RUN_TRACE_IMPLEMENTATION_RECEIPT_2026-08-29](docs/receipts/DYNAMIC_RUN_TRACE_IMPLEMENTATION_RECEIPT_2026-08-29.md) | recorder、artifact/API、UI bridge |
| [MOTION_TASK_IMPLEMENTATION_RECEIPT_2026-08-29](docs/receipts/MOTION_TASK_IMPLEMENTATION_RECEIPT_2026-08-29.md) | Motion Task registry 與第一組負結果 |
| [CONTROLLED_STOP_TRAINING_IMPLEMENTATION_RECEIPT_2026-08-30](docs/receipts/CONTROLLED_STOP_TRAINING_IMPLEMENTATION_RECEIPT_2026-08-30.md) | controlled stop、Training Lab、curriculum |
| [START_STOP_POLICY_TRAINING_RECEIPT_2026-08-30](docs/receipts/START_STOP_POLICY_TRAINING_RECEIPT_2026-08-30.md) | v1 early stop、curriculum-v2 warm start |
| [PATH_PHASE_SATURATION_TRAINING_RECEIPT_2026-08-30](docs/receipts/PATH_PHASE_SATURATION_TRAINING_RECEIPT_2026-08-30.md) | v2–v6 iterations、500 Hz sampling defect |
| [V1_RAW_JACOBIAN_IMPLEMENTATION_RECEIPT_2026-08-31](docs/receipts/V1_RAW_JACOBIAN_IMPLEMENTATION_RECEIPT_2026-08-31.md) | raw relative Jacobian replay V4 |
| [V1_ANALYTICAL_SUITE_IMPLEMENTATION_RECEIPT_2026-09-02](docs/receipts/V1_ANALYTICAL_SUITE_IMPLEMENTATION_RECEIPT_2026-09-02.md) | analytical fixture clean-source bundle |
| [EXPERIMENT_MATRIX_IMPLEMENTATION_RECEIPT_2026-09-03](docs/receipts/EXPERIMENT_MATRIX_IMPLEMENTATION_RECEIPT_2026-09-03.md) | matrix validator synthetic receipt |
| [PAIRED_STATISTICS_IMPLEMENTATION_RECEIPT_2026-09-05](docs/receipts/PAIRED_STATISTICS_IMPLEMENTATION_RECEIPT_2026-09-05.md) | paired statistics/export regression receipt |
| [V7_ACTION_INTERFACE_PILOT_IMPLEMENTATION_RECEIPT_2026-09-06](docs/archive/V7_ACTION_INTERFACE_PILOT_IMPLEMENTATION_RECEIPT_2026-09-06.md) | v7 三臂 pilot bundle 與 conditional statistics |
| [V7_EXPOSURE_CENSORING_AUDIT_IMPLEMENTATION_RECEIPT_2026-09-08](docs/archive/V7_EXPOSURE_CENSORING_AUDIT_IMPLEMENTATION_RECEIPT_2026-09-08.md) | audit software synthetic receipt、phase-convention finding |
| [V7_EXPOSURE_CENSORING_AUDIT_FROZEN_BUNDLE_RECEIPT_2026-09-08](docs/archive/V7_EXPOSURE_CENSORING_AUDIT_FROZEN_BUNDLE_RECEIPT_2026-09-08.md) | 對 frozen pilot bundle 的 read-only audit run |
| [ENVIRONMENT_LOCK_IMPLEMENTATION_RECEIPT_2026-09-08](docs/receipts/ENVIRONMENT_LOCK_IMPLEMENTATION_RECEIPT_2026-09-08.md) | 實測 lock record、reduction-order 差異 |
| [RUN_MANIFEST_LOCK_BINDING_RECEIPT_2026-09-13](docs/receipts/RUN_MANIFEST_LOCK_BINDING_RECEIPT_2026-09-13.md) | `LB-01`..`LB-12`、兩個 digest 的正控制、三個承諾不碰的檔案逐位元未變、以及凍結 §12 的一個具名缺陷 |
| [TRAINING_SEED_VARIANCE_IMPLEMENTATION_RECEIPT_2026-09-08](docs/archive/TRAINING_SEED_VARIANCE_IMPLEMENTATION_RECEIPT_2026-09-08.md) | plant identity、結構性規則、synthetic regression |
| [TRAINING_SEED_VARIANCE_EXECUTION_RECEIPT_2026-09-08](docs/archive/TRAINING_SEED_VARIANCE_EXECUTION_RECEIPT_2026-09-08.md) | 1,843,200 timesteps 的實際執行與 method-level bounds |
| [V7_PRETRAINING_SEED_VARIANCE_INFEASIBILITY_RECEIPT_2026-09-08](docs/archive/V7_PRETRAINING_SEED_VARIANCE_INFEASIBILITY_RECEIPT_2026-09-08.md) | 為何 pretraining-seed variance 不可量測 |
| [V7_CANDIDATE_SELECTION_IMPLEMENTATION_RECEIPT_2026-09-08](docs/archive/V7_CANDIDATE_SELECTION_IMPLEMENTATION_RECEIPT_2026-09-08.md) | selection rule 自檢、三項執行前置條件 |
| [SECOND_CASE_EXPOSURE_CENSORING_EXECUTION_RECEIPT_2026-09-08](docs/archive/SECOND_CASE_EXPOSURE_CENSORING_EXECUTION_RECEIPT_2026-09-08.md) | 第二案例的 10 cells 執行、method-level 結果、兩臂皆 censored 的保留發現 |
| [SECOND_CASE_V2_BUDGET_PROBE_RECEIPT_2026-09-08](docs/archive/SECOND_CASE_V2_BUDGET_PROBE_RECEIPT_2026-09-08.md) | 三個 budget probe（pilot）、exposure-only adequacy 規則的缺口、2026-09-09 停止該線的決定 |
| [PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10](docs/receipts/PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10.md) | 2026-09-10 的 formal-evaluation 授權紀錄、仍存在的四項 blocker、v7 線上 `SEL-C2` 的可行性量測 |

## 下一階段

兩條軌道並行，互不阻擋。逐項理由與順序見 [PROJECT_STATUS §8](docs/PROJECT_STATUS.md)；此處只列標題。

| 軌道 | 下一件事 |
|---|---|
| 學術 | `PUB-A0` 其餘 `U` 條目原文核對（受限於 egress）→ `PUB-A2` claim freeze。第二案例線已關閉，不再開 probe 或 protocol。 |
| 工程 | 一條**有版控 checkpoint lineage** 的新訓練線（同時是 Track B 的硬前置）→ browser visual verification → V1 articulated dynamic／pendulum／energy oracles。 |
| 決策（僅專案負責人） | [PUBLICATION_PLAN §5](docs/PUBLICATION_PLAN.md) 的兩個子問題：用現行 post-hoc 規則或先預註冊替代規則；唯一未檢視的 FORMAL seed 範圍花在哪條訓練線。 |

[BLOCKER] formal evaluation 已於 2026-09-10 授權，但授權只解除凍結順序的第一格：`PUB-B4` 外部預註冊仍在解封之前，`EP-01`／`EP-02` 未解除，`EP-03` 在 frozen protocol JSON 內仍為 `BLOCKING`。因此目前仍：**不做 selection、不調 threshold、不存取 FORMAL seeds `20000–20029`**。

## 資料聲明

內建馬達與減速機型錄是 **representative demo data**，不是原廠 datasheet、CAD/BOM 或 bench evidence。更改介面數值不會自動提升證據等級。詳見 [HARDWARE_DATA_PROVENANCE](docs/HARDWARE_DATA_PROVENANCE.md)。
