# 人形機器人設計篩選與教學模擬原型

> Humanoid Design Screening and Teaching Simulation Prototype

Repository：[github.com/dofliu/robotMan](https://github.com/dofliu/robotMan) ｜ Release：`0.1.0` ｜ License：MIT

本專案目前定位為 **SIM-only、reduced-order** 的人形機器人設計篩選與教學原型。它可用來探索幾何、質量、致動器示意參數、步態與控制策略之間的關係，但尚未完成足以支持實體硬體選型、採購、安全判定或效能保證的 physical validation。

## 目前可信邊界

- [SOURCE] 程式包含參數化步態、MuJoCo 模型、分析模式、即時 forward simulation、控制器與 RL pipeline；analysis `/api/simulate` 已開始提供 versioned metrics 與 partial runtime provenance，現行 REST/Live simulation inputs 採 bounded fail-closed schema，frontend 已顯示 frozen/stale-result、evidence 與 intervention/error states。
- [INFERENCE] 既有數字目前只能視為特定程式版本、單一 nominal configuration 下的 development snapshot；缺少 immutable raw bundle 時不升格為正式 [RESULT] evidence。
- [BLOCKER] 現有 runtime provenance 尚不是 immutable artifact bundle，也沒有 environment lock；contact wrench closure、torque-speed envelope、joint limits、contact/friction/CoP feasibility、solver convergence、fair benchmark、uncertainty quantification 與實體 subsystem validation 尚未形成完整證據鏈。

因此，介面中的「通過」、「穩定」、「可行」或「最大可承受」只代表目前數值模型與規則下的 screening signal，不等同實體機器人驗證結果。完整證據邊界見 [MODEL_CARD](docs/MODEL_CARD.md)。

## 兩種模式

| 模式 | 實際計算內容 | 目前可支持的用途 | 不可宣稱 |
|---|---|---|---|
| 分析模式 | prescribed kinematics → analytical GRF/contact schedule → MuJoCo inverse dynamics | 相對趨勢、敏感度、教學與早期 design screening | 已求得物理可行 contact wrench、硬體一定帶得動、實機穩定 |
| 即時互動 | MuJoCo forward dynamics + simulated contact + torque-limited controller | 觀察特定 simulated plant 中的接觸、跌倒與控制反應 | 「真實接觸動力學」、實測抗推力、sim-to-real 能力 |

分析模式沒有由 contact solver 求解腳底接觸；即時互動模式則使用 MuJoCo 的 forward contact simulation。兩者的 plant、能量定義與證據用途不同，不應把數字直接混成同一種 validation evidence。

目前第一模式提供兩個 analysis sources：`Reference 估算` 是原有 prescribed trajectory；`Dynamic Trace` 則讀取第二模式以 500 Hz physics-step 保存的 MuJoCo realized simulation。後者仍是 simulated output，不是實體量測。操作與欄位定義見 [DYNAMIC_RUN_TRACE_SPEC](docs/DYNAMIC_RUN_TRACE_SPEC.md)。

## Verification 與 Validation

- **Verification**：確認程式是否正確實作已定義的 equations、units、constraints 與數值方法。
- **Validation**：以獨立的實體資料、bench、HIL 或整機量測，確認模型對真實系統是否足夠準確。

目前僅有少量 software checks；專案整體狀態為 **NOT PHYSICALLY VALIDATED**。後續 gate 與 evidence matrix 見 [VV_PLAN](docs/VV_PLAN.md)。

## 已有 prototype 能力

- 12 關節 reduced-order humanoid、走路／跑步 prescribed gait
- 馬達／減速機示意參數、質量配置與相對使用率 screening
- CoM、ZMP 與支撐多邊形視覺化
- 理想 LiDAR raycast 與規則式障礙處理
- MuJoCo 即時 forward simulation、推力輸入與控制器狀態顯示
- trajectory tracking、Raibert、PPO policy 的 nominal scenario 比較
- 三機同步比較模式：三個獨立 MuJoCo plants 接收相同命令，assist 預設關閉、跌倒不自動修復；僅供 development observation
- 正式動作任務 V1：`stand → start → steady walk → stop` 的固定 phase、500 Hz trace 與逐項 PASS/FAIL；可在 Live 或三機 Compare 執行

這些是 feature inventory，不代表 M1–M6 已通過 V&V gate。

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

`requirements-rl.txt` 可安裝執行既有 policy 所需的套件範圍，但仍不是完整 frozen training environment。若要重現 PPO training，必須另行鎖定 Stable-Baselines3、Gymnasium、PyTorch、MuJoCo、NumPy、Python、CUDA 與 checkpoint SHA-256。`/api/simulate` 的 runtime provenance 也不能替代 environment reproducibility 或 immutable evidence bundle。

只使用分析模式與非 RL controller 時，可僅安裝 `backend/requirements-dev.txt`。完整三機比較會載入 RL policy，因此建議使用上方完整安裝流程。

## Repository 內容

- Git 追蹤 source、tests、docs、frontend lockfile，以及 registry 指定的 `backend/rl/ppo_walk_final.zip`。
- 不追蹤 `node_modules`、frontend build、runtime traces、historical RL checkpoints、training smoke artifacts、logs、cache 或本機 debug files。
- Clone、驗證、artifact policy 與發布檢查見 [REPOSITORY_GUIDE](docs/REPOSITORY_GUIDE.md)。

## Nominal benchmark snapshot

comparison_report.md 保留既有 deterministic nominal snapshot，供回歸診斷與教學敘事參考。該檔案：

- 不是多 seed、Monte Carlo 或獨立重複實驗；
- 沒有 confidence interval 或 uncertainty budget；
- 使用特定 assist、disturbance timing、energy integration 與 termination rule；
- 不能當成控制器普遍優劣、硬體能力或實機抗擾動證據。

正式比較必須依 [EXPERIMENT_PROTOCOL](docs/EXPERIMENT_PROTOCOL.md) 產生 frozen manifest、raw traces、hashes 與統計報告。

## 文件導覽

| 文件 | 單一職責 |
|---|---|
| [USAGE](docs/USAGE.md) | 安裝、操作與結果解讀 |
| [REPOSITORY_GUIDE](docs/REPOSITORY_GUIDE.md) | Clone/setup、Git tracked/excluded artifacts、驗證與發布規則 |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | 兩種 simulation pipeline 與資料邊界 |
| [MODEL_CARD](docs/MODEL_CARD.md) | intended use、out-of-scope、限制與 evidence labels |
| [VV_PLAN](docs/VV_PLAN.md) | requirement-to-evidence matrix、gates 與 SIL/HIL/bench 邊界 |
| [EXPERIMENT_PROTOCOL](docs/EXPERIMENT_PROTOCOL.md) | frozen configuration、seed、hash、metrics 與 raw artifacts |
| [METRIC_DEFINITIONS](docs/METRIC_DEFINITIONS.md) | analysis runtime 指標的公式、窗口、命名與限制 |
| [COMPARE_MODE_SPEC](docs/COMPARE_MODE_SPEC.md) | 三機同步比較的公平性、WebSocket contract、失敗語義與驗收條件 |
| [RL_POLICY_TRAINING](docs/RL_POLICY_TRAINING.md) | RL inference／training 邊界、policy registry、固定速度 profiles 與不覆寫再訓練流程 |
| [DYNAMIC_RUN_TRACE_SPEC](docs/DYNAMIC_RUN_TRACE_SPEC.md) | 第二模式 realized simulation 到第一模式工程分析的 raw trace contract 與驗收條件 |
| [MOTION_TASK_SPEC](docs/MOTION_TASK_SPEC.md) | 第一個正式動作任務、固定 phase/gait、可量測成功條件與後續動作 registry |
| [DYNAMIC_RUN_TRACE_IMPLEMENTATION_RECEIPT_2026-08-29](docs/DYNAMIC_RUN_TRACE_IMPLEMENTATION_RECEIPT_2026-08-29.md) | recorder、artifact/API、UI bridge、測試與 development sample 回條 |
| [MOTION_TASK_IMPLEMENTATION_RECEIPT_2026-08-29](docs/MOTION_TASK_IMPLEMENTATION_RECEIPT_2026-08-29.md) | Motion Task registry、Live/Compare/Analysis 整合、測試與第一組負結果 baseline |
| [COMPARE_RL_IMPLEMENTATION_RECEIPT_2026-08-26](docs/COMPARE_RL_IMPLEMENTATION_RECEIPT_2026-08-26.md) | 三機比較、registry、training smoke 的 source/test receipt 與未解 blockers |
| [V0_IMPLEMENTATION_RECEIPT_2026-08-26](docs/V0_IMPLEMENTATION_RECEIPT_2026-08-26.md) | 第一批 V0 hardening 的 source/test audit 與未解 blockers |
| [HARDWARE_DATA_PROVENANCE](docs/HARDWARE_DATA_PROVENANCE.md) | datasheet、CAD/BOM、bench data 與 demo catalog 的分級 |
| [ROADMAP](docs/ROADMAP.md) | V0–V4 gate-first 工作順序 |
| [CONVENTIONS](docs/CONVENTIONS.md) | 開發與 evidence governance 規範 |
| [CHANGELOG](CHANGELOG.md) | 對外 development release 變更紀錄 |

## 下一階段

目前不以「功能完成百分比」表示成熟度。第一個正式 Motion Task 已能量測 `stand → start → steady walk → stop`，第一組三 controller baseline 均誠實判定 FAIL；下一步是改善 controlled deceleration/stop phase，並用不變的 criteria 重跑。這項 development 能力不解除 V0/V1/V3 gate；Evidence 主線仍須補齊 environment lock、immutable raw artifact bundle、validator 與完整 requirement registry。

## 資料聲明

內建馬達與減速機型錄是 **representative demo data**，不是原廠 datasheet、CAD/BOM 或 bench evidence。更改介面數值不會自動提升證據等級。詳見 [HARDWARE_DATA_PROVENANCE](docs/HARDWARE_DATA_PROVENANCE.md)。
