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
| 最強的一個結果 | V7B 相對 V7A 的 saturation duty method-level bound `[-13.503408, -12.435259]` pp，排除 0，5/5 independent training replicates 方向可識別；**條件於一個不可重建的 warm start** | [PROJECT_STATUS §4](docs/PROJECT_STATUS.md) |
| 被推翻的一個結果 | V7C 表面上的 `-36` pp 改善經量測確認為 exposure artifact | [PROJECT_STATUS §4.2](docs/PROJECT_STATUS.md) |
| 學術產出 | 三條路線；Track A 於 2026-09-09 重構為「censoring regime 的評估效度研究」（`PUBLICATION-PLAN-V3`）：`PUB-A1a` PASS（Walker2d-v5 第二案例）、`PUB-A1b` CLOSED_NOT_ATTAINED（三個 budget probe 後停止）；`PUB-A0` 關鍵兩篇已原文核對、gap 仍成立，A-C5 補充 scan 完成後降為 artifact 級（其餘條目待核）；下一步 `PUB-A2` claim freeze，其輸入之一是 2026-09-11 凍結的 `R0` regime probe | [PUBLICATION_PLAN](docs/PUBLICATION_PLAN.md)、[TRACK_A_REFRAME](docs/TRACK_A_REFRAME_2026-09-09.md) |
| 動作任務範圍 | 2026-09-11 決定現在**不**新增跳躍／轉身；順序為先綁 lock record 與建有版控 lineage 的新訓練線，轉身需 `PUB-B2`、跳躍需 V1 PASS | [MOTION_SCOPE_DECISION](docs/MOTION_SCOPE_DECISION_2026-09-11.md) |
| 下一個決策 | formal evaluation 已於 2026-09-10 授權；剩兩個子問題：用現行 post-hoc 規則或先預註冊替代規則、唯一未檢視的 FORMAL seed 範圍花在 v7 線或新訓練線 | [PUBLICATION_PLAN §5](docs/PUBLICATION_PLAN.md)、[PUB_B0 receipt](docs/PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10.md) |
| 測試 | `backend/` 1 failed / 729 passed；那一個是在具名 environment lock 下記錄的 reduction-order 差異，未放寬 | [PROJECT_STATUS §9](docs/PROJECT_STATUS.md) |

## 兩種模式

| 模式 | 實際計算內容 | 目前可支持的用途 | 不可宣稱 |
|---|---|---|---|
| 分析模式 | prescribed kinematics → analytical GRF/contact schedule → MuJoCo inverse dynamics | 相對趨勢、敏感度、教學與早期 design screening | 已求得物理可行 contact wrench、硬體一定帶得動、實機穩定 |
| 即時互動 | MuJoCo forward dynamics + simulated contact + torque-limited controller | 觀察特定 simulated plant 中的接觸、跌倒與控制反應 | 「真實接觸動力學」、實測抗推力、sim-to-real 能力 |

分析模式沒有由 contact solver 求解腳底接觸；即時互動模式則使用 MuJoCo 的 forward contact simulation。兩者的 plant、能量定義與證據用途不同，不應把數字直接混成同一種 validation evidence。

第一模式提供兩個 analysis sources：`Reference 估算` 是原有 prescribed trajectory；`Dynamic Trace` 則讀取第二模式以 500 Hz physics-step 保存的 MuJoCo realized simulation。後者仍是 simulated output，不是實體量測。見 [DYNAMIC_RUN_TRACE_SPEC](docs/DYNAMIC_RUN_TRACE_SPEC.md)。

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
- RL Training Lab：顯示 fixed-speed／command-conditioned profiles、seed、training budget 與 evidence status
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

## Repository 內容

- Git 追蹤 source、tests、docs、frontend lockfile、registry 指定的三個 inference artifacts、小型 receipts 與 `backend/seed_variance_evidence/` 等已保留的證據 bundle。
- 不追蹤 `node_modules`、frontend build、runtime traces、historical RL checkpoints、training smoke artifacts、logs 或本機 debug files。**注意**：`backend/rl/artifacts/` 被 gitignore 這件事已經永久毀掉 v7 line 的 pretraining provenance（見 [pretraining infeasibility receipt](docs/V7_PRETRAINING_SEED_VARIANCE_INFEASIBILITY_RECEIPT_2026-09-08.md)）；任何新的訓練線都必須把 checkpoint lineage 放進版控或 immutable storage。
- Clone、驗證、artifact policy 與發布檢查見 [REPOSITORY_GUIDE](docs/REPOSITORY_GUIDE.md)。

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
| [MOTION_SCOPE_DECISION_2026-09-11](docs/MOTION_SCOPE_DECISION_2026-09-11.md) | 動作任務範圍決定：現在不新增跳躍／轉身，以及新增動作的凍結順序 |
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
| [V7_ACTION_INTERFACE_PILOT_SPEC](docs/V7_ACTION_INTERFACE_PILOT_SPEC.md) | v7 三臂 action math、seeds、acceptance、claim boundary |
| [V7_EXPOSURE_CENSORING_AUDIT_SPEC](docs/V7_EXPOSURE_CENSORING_AUDIT_SPEC.md) | read-only audit 的 horizon、censoring vocabulary、identification bounds |
| [TRAINING_SEED_VARIANCE_SPEC](docs/TRAINING_SEED_VARIANCE_SPEC.md) | independent training replicates、replicate-level analysis unit、禁止 selection |
| [V7_CANDIDATE_SELECTION_SPEC](docs/V7_CANDIDATE_SELECTION_SPEC.md) | 凍結的 selection 規則、post-hoc 揭露、sealed FORMAL、授權閘 |
| [SECOND_CASE_EXPOSURE_CENSORING_SPEC](docs/SECOND_CASE_EXPOSURE_CENSORING_SPEC.md) | PUB-A1 第二案例：Walker2d-v5 上 exposure-censoring 機制的凍結 protocol、預測與 falsifier |

### 文獻

| 文件 | 單一職責 |
|---|---|
| [LITERATURE_MAP_2026-08-30](docs/LITERATURE_MAP_2026-08-30.md) | humanoid locomotion、sim-to-real、residual/hybrid control 方向對照 |
| [LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY](docs/LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md) | exposure censoring、partial identification、statistical unit、numerical reproducibility 的既有工作與 Track A 的定位 |

### Receipts（依日期）

| 文件 | 內容 |
|---|---|
| [V0_IMPLEMENTATION_RECEIPT_2026-08-26](docs/V0_IMPLEMENTATION_RECEIPT_2026-08-26.md) | 第一批 V0 hardening |
| [COMPARE_RL_IMPLEMENTATION_RECEIPT_2026-08-26](docs/COMPARE_RL_IMPLEMENTATION_RECEIPT_2026-08-26.md) | 三機比較、registry、training smoke |
| [DYNAMIC_RUN_TRACE_IMPLEMENTATION_RECEIPT_2026-08-29](docs/DYNAMIC_RUN_TRACE_IMPLEMENTATION_RECEIPT_2026-08-29.md) | recorder、artifact/API、UI bridge |
| [MOTION_TASK_IMPLEMENTATION_RECEIPT_2026-08-29](docs/MOTION_TASK_IMPLEMENTATION_RECEIPT_2026-08-29.md) | Motion Task registry 與第一組負結果 |
| [CONTROLLED_STOP_TRAINING_IMPLEMENTATION_RECEIPT_2026-08-30](docs/CONTROLLED_STOP_TRAINING_IMPLEMENTATION_RECEIPT_2026-08-30.md) | controlled stop、Training Lab、curriculum |
| [START_STOP_POLICY_TRAINING_RECEIPT_2026-08-30](docs/START_STOP_POLICY_TRAINING_RECEIPT_2026-08-30.md) | v1 early stop、curriculum-v2 warm start |
| [PATH_PHASE_SATURATION_TRAINING_RECEIPT_2026-08-30](docs/PATH_PHASE_SATURATION_TRAINING_RECEIPT_2026-08-30.md) | v2–v6 iterations、500 Hz sampling defect |
| [V1_RAW_JACOBIAN_IMPLEMENTATION_RECEIPT_2026-08-31](docs/V1_RAW_JACOBIAN_IMPLEMENTATION_RECEIPT_2026-08-31.md) | raw relative Jacobian replay V4 |
| [V1_ANALYTICAL_SUITE_IMPLEMENTATION_RECEIPT_2026-09-02](docs/V1_ANALYTICAL_SUITE_IMPLEMENTATION_RECEIPT_2026-09-02.md) | analytical fixture clean-source bundle |
| [EXPERIMENT_MATRIX_IMPLEMENTATION_RECEIPT_2026-09-03](docs/EXPERIMENT_MATRIX_IMPLEMENTATION_RECEIPT_2026-09-03.md) | matrix validator synthetic receipt |
| [PAIRED_STATISTICS_IMPLEMENTATION_RECEIPT_2026-09-05](docs/PAIRED_STATISTICS_IMPLEMENTATION_RECEIPT_2026-09-05.md) | paired statistics/export regression receipt |
| [V7_ACTION_INTERFACE_PILOT_IMPLEMENTATION_RECEIPT_2026-09-06](docs/V7_ACTION_INTERFACE_PILOT_IMPLEMENTATION_RECEIPT_2026-09-06.md) | v7 三臂 pilot bundle 與 conditional statistics |
| [V7_EXPOSURE_CENSORING_AUDIT_IMPLEMENTATION_RECEIPT_2026-09-08](docs/V7_EXPOSURE_CENSORING_AUDIT_IMPLEMENTATION_RECEIPT_2026-09-08.md) | audit software synthetic receipt、phase-convention finding |
| [V7_EXPOSURE_CENSORING_AUDIT_FROZEN_BUNDLE_RECEIPT_2026-09-08](docs/V7_EXPOSURE_CENSORING_AUDIT_FROZEN_BUNDLE_RECEIPT_2026-09-08.md) | 對 frozen pilot bundle 的 read-only audit run |
| [ENVIRONMENT_LOCK_IMPLEMENTATION_RECEIPT_2026-09-08](docs/ENVIRONMENT_LOCK_IMPLEMENTATION_RECEIPT_2026-09-08.md) | 實測 lock record、reduction-order 差異 |
| [TRAINING_SEED_VARIANCE_IMPLEMENTATION_RECEIPT_2026-09-08](docs/TRAINING_SEED_VARIANCE_IMPLEMENTATION_RECEIPT_2026-09-08.md) | plant identity、結構性規則、synthetic regression |
| [TRAINING_SEED_VARIANCE_EXECUTION_RECEIPT_2026-09-08](docs/TRAINING_SEED_VARIANCE_EXECUTION_RECEIPT_2026-09-08.md) | 1,843,200 timesteps 的實際執行與 method-level bounds |
| [V7_PRETRAINING_SEED_VARIANCE_INFEASIBILITY_RECEIPT_2026-09-08](docs/V7_PRETRAINING_SEED_VARIANCE_INFEASIBILITY_RECEIPT_2026-09-08.md) | 為何 pretraining-seed variance 不可量測 |
| [V7_CANDIDATE_SELECTION_IMPLEMENTATION_RECEIPT_2026-09-08](docs/V7_CANDIDATE_SELECTION_IMPLEMENTATION_RECEIPT_2026-09-08.md) | selection rule 自檢、三項執行前置條件 |
| [SECOND_CASE_EXPOSURE_CENSORING_EXECUTION_RECEIPT_2026-09-08](docs/SECOND_CASE_EXPOSURE_CENSORING_EXECUTION_RECEIPT_2026-09-08.md) | 第二案例的 10 cells 執行、method-level 結果、兩臂皆 censored 的保留發現 |
| [SECOND_CASE_V2_BUDGET_PROBE_RECEIPT_2026-09-08](docs/SECOND_CASE_V2_BUDGET_PROBE_RECEIPT_2026-09-08.md) | 三個 budget probe（pilot）、exposure-only adequacy 規則的缺口、2026-09-09 停止該線的決定 |
| [PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10](docs/PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10.md) | 2026-09-10 的 formal-evaluation 授權紀錄、仍存在的四項 blocker、v7 線上 `SEL-C2` 的可行性量測 |

## 下一階段

專案同時推進兩條軌道，互不阻擋：

- **學術**：先做 Track A（評估效度／可重現性方法論，2026-09-09 起以 censoring regime 為論點，見 [TRACK_A_REFRAME](docs/TRACK_A_REFRAME_2026-09-09.md)）。剩餘前置是 `PUB-A0` 其餘 `U` 條目的原文核對（關鍵兩篇已於 2026-09-09 核對，gap 仍成立）與 `PUB-A2` claim freeze；第二案例線已關閉，不再開 probe 或 protocol。2026-09-11 另凍結 `R0` regime probe（唯讀重算既有 450 個 episode，不訓練、不動 seed），用於補 taxonomy 的 `R0` 格。Track B（原定 Study A 方法比較）的 formal authorization 已於 2026-09-10 取得，但仍需 `PUB-B4` 外部預註冊與三項 execution precondition 的 amendment，且量測顯示 v7 線上 `SEL-C2` 幾乎確定不成立，故仍需一條有版控 artifact 的新訓練線；Track C（教學工具）需要另立學習成效研究設計。
- **工程**：把 environment lock record 綁進每一條 pipeline 的 run manifest、Compare／Dynamic trace 的 browser visual verification、V1 articulated dynamic／pendulum／energy oracles、以及一條有版控 artifact 的新訓練線。順序見 [ROADMAP §9](docs/ROADMAP.md)。

formal evaluation 已於 2026-09-10 授權，但授權只解除凍結順序的第一格：`PUB-B4` 外部預註冊仍在解封之前，`EP-01`／`EP-02` 未解除，`EP-03` 在 frozen protocol JSON 內仍為 `BLOCKING`。因此目前仍：不做 selection、不調 threshold、不存取 FORMAL seeds `20000–20029`。詳細狀態與理由見 [PROJECT_STATUS](docs/PROJECT_STATUS.md) 與 [PUB_B0 receipt](docs/PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10.md)。

## 資料聲明

內建馬達與減速機型錄是 **representative demo data**，不是原廠 datasheet、CAD/BOM 或 bench evidence。更改介面數值不會自動提升證據等級。詳見 [HARDWARE_DATA_PROVENANCE](docs/HARDWARE_DATA_PROVENANCE.md)。
