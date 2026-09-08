# 人形機器人設計篩選與教學模擬原型

> Humanoid Design Screening and Teaching Simulation Prototype

Repository：[github.com/dofliu/robotMan](https://github.com/dofliu/robotMan) ｜ Development：`0.2.0-dev` ｜ License：MIT

本專案目前定位為 **SIM-only、reduced-order** 的人形機器人設計篩選與教學原型。它可用來探索幾何、質量、致動器示意參數、步態與控制策略之間的關係，但尚未完成足以支持實體硬體選型、採購、安全判定或效能保證的 physical validation。

## 目前可信邊界

- [SOURCE] 程式包含參數化步態、MuJoCo 模型、分析模式、即時 forward simulation、控制器與 RL pipeline；analysis `/api/simulate` 已開始提供 versioned metrics 與 partial runtime provenance，現行 REST/Live simulation inputs 採 bounded fail-closed schema，frontend 已顯示 frozen/stale-result、evidence 與 intervention/error states。
- [INFERENCE] 既有數字目前只能視為特定程式版本、單一 nominal configuration 下的 development snapshot；缺少 immutable raw bundle 時不升格為正式 [RESULT] evidence。
- [BLOCKER] 現有 runtime provenance 尚不是 project-wide immutable artifact storage；`ENVIRONMENT-LOCK-V1` 已能量測並重驗 software environment identity 且保留一份實測 record，但還沒有任何 pipeline 把 lock record 綁進自己的 run manifest，因此 environment lock 仍未完整；static contact raw-Jacobian replay，以及 passive single-support／centered known-payload／4–2–1 ms analytical fixture 已完成 bounded arithmetic identity，但 articulated dynamic/pendulum/energy cases、torque-speed envelope、joint limits、完整 solver convergence、fair benchmark、uncertainty quantification與實體 subsystem validation 尚未形成完整證據鏈。

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
- `WALK → STOPPING → STAND` controlled transition、可擴充 Motion Primitive dispatcher 與 trace-visible STOPPING state
- RL Training Lab：顯示 fixed-speed／command-conditioned profiles、seed、training budget 與 evidence status；即時模式仍只做 inference
- Registry-gated Motion Task policies：48-D curriculum-v2 與 51-D phase-observable-v5 可在 Live 選用；v2/v5 的失敗 trace 均保留
- V1 static contact oracle V4：500 Hz raw trace、serialized relative Jacobians、6-D wrench closure、pyramidal friction utilization、foot-local CoP，以及不載入 MuJoCo/controller 的 stdlib-only process replay；僅為 static SIM evidence
- V1 analytical fixture：passive single-support、centered 5 kg simulated payload與 4/2/1 ms grid-refinement；exact MJCF/model package、raw frame/wrench/Jacobian與 stdlib-only replay皆 fail closed，僅為 `SIM_ONLY_MUJOCO`
- Experiment matrix completeness V1：strict JSON frozen spec/index、expected-to-observed exact cell matching、run bundle path/bytes/SHA-256 readback，以及 missing/duplicate/unexpected/unindexed/identity drift與 FAILED/CANCELLED retention；只驗 software inventory identity
- Paired statistics/export V1：frozen explicit pair map、continuous paired mean/median/Cohen dz、deterministic paired bootstrap CI、binary 2×2 counts/Wilson marginal descriptions、failure/null/non-finite/censoring retention，以及 `python -I -S` raw-to-summary/table/figure exact replay；paired binary CI 仍 fail-closed blocked

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

- Git 追蹤 source、tests、docs、frontend lockfile，以及 registry 指定的 legacy、curriculum-v2 與 phase-observable-v5 inference artifacts。
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
| [V1_ORACLE_SPEC](docs/V1_ORACLE_SPEC.md) | 第一個 static double-support / forward–inverse numerical oracle、threshold 與證據邊界 |
| [V1_ANALYTICAL_SUITE_SPEC](docs/V1_ANALYTICAL_SUITE_SPEC.md) | single-support、known-payload、time-step fixture 的 frozen contract、failure semantics 與 claim boundary |
| [EXPERIMENT_MATRIX_CONTRACT](docs/EXPERIMENT_MATRIX_CONTRACT.md) | controller × seed × scenario exact matrix、status retention與 completeness receipt contract |
| [PAIRED_STATISTICS_CONTRACT](docs/PAIRED_STATISTICS_CONTRACT.md) | paired estimand、failure/null/censoring semantics、CI與 machine-readable paper input contract |
| [EXPERIMENT_PROTOCOL](docs/EXPERIMENT_PROTOCOL.md) | frozen configuration、seed、hash、metrics 與 raw artifacts |
| [PAPER_DATA_READINESS](docs/PAPER_DATA_READINESS.md) | paper-data-first 架構、run bundle、PDR gates、統計與文獻依據 |
| [METRIC_DEFINITIONS](docs/METRIC_DEFINITIONS.md) | analysis runtime 指標的公式、窗口、命名與限制 |
| [COMPARE_MODE_SPEC](docs/COMPARE_MODE_SPEC.md) | 三機同步比較的公平性、WebSocket contract、失敗語義與驗收條件 |
| [RL_POLICY_TRAINING](docs/RL_POLICY_TRAINING.md) | RL inference／training 邊界、policy registry、固定速度 profiles 與不覆寫再訓練流程 |
| [RESEARCH_EXECUTION_PLAN](docs/RESEARCH_EXECUTION_PLAN.md) | model validity 與 method effectiveness 雙證據鏈、RQ、gate 與公平比較設計 |
| [LITERATURE_MAP_2026-08-30](docs/LITERATURE_MAP_2026-08-30.md) | 近期 humanoid locomotion、sim-to-real、residual/hybrid control 與研究方向對照 |
| [DYNAMIC_RUN_TRACE_SPEC](docs/DYNAMIC_RUN_TRACE_SPEC.md) | 第二模式 realized simulation 到第一模式工程分析的 raw trace contract 與驗收條件 |
| [MOTION_TASK_SPEC](docs/MOTION_TASK_SPEC.md) | 第一個正式動作任務、固定 phase/gait、可量測成功條件與後續動作 registry |
| [MOTION_PRIMITIVE_SPEC](docs/MOTION_PRIMITIVE_SPEC.md) | action dispatcher、controlled stop state machine 與後續基本動作進入條件 |
| [DYNAMIC_RUN_TRACE_IMPLEMENTATION_RECEIPT_2026-08-29](docs/DYNAMIC_RUN_TRACE_IMPLEMENTATION_RECEIPT_2026-08-29.md) | recorder、artifact/API、UI bridge、測試與 development sample 回條 |
| [MOTION_TASK_IMPLEMENTATION_RECEIPT_2026-08-29](docs/MOTION_TASK_IMPLEMENTATION_RECEIPT_2026-08-29.md) | Motion Task registry、Live/Compare/Analysis 整合、測試與第一組負結果 baseline |
| [CONTROLLED_STOP_TRAINING_IMPLEMENTATION_RECEIPT_2026-08-30](docs/CONTROLLED_STOP_TRAINING_IMPLEMENTATION_RECEIPT_2026-08-30.md) | controlled stop、Motion Primitive、Training Lab、start/stop curriculum 與同門檻重跑結果 |
| [START_STOP_POLICY_TRAINING_RECEIPT_2026-08-30](docs/START_STOP_POLICY_TRAINING_RECEIPT_2026-08-30.md) | v1 failed-speed early stop、curriculum-v2 warm start、30-seed training-env gate 與候選 artifact 邊界 |
| [PATH_PHASE_SATURATION_TRAINING_RECEIPT_2026-08-30](docs/PATH_PHASE_SATURATION_TRAINING_RECEIPT_2026-08-30.md) | v2–v6 observation/reward iterations、500 Hz sampling defect、Live failure 與下一輪研究 gate |
| [COMPARE_RL_IMPLEMENTATION_RECEIPT_2026-08-26](docs/COMPARE_RL_IMPLEMENTATION_RECEIPT_2026-08-26.md) | 三機比較、registry、training smoke 的 source/test receipt 與未解 blockers |
| [V0_IMPLEMENTATION_RECEIPT_2026-08-26](docs/V0_IMPLEMENTATION_RECEIPT_2026-08-26.md) | 第一批 V0 hardening 的 source/test audit 與未解 blockers |
| [V1_ANALYTICAL_SUITE_IMPLEMENTATION_RECEIPT_2026-09-02](docs/V1_ANALYTICAL_SUITE_IMPLEMENTATION_RECEIPT_2026-09-02.md) | analytical fixture 的 clean-source bundle、independent replay、tests 與 bounded result |
| [EXPERIMENT_MATRIX_IMPLEMENTATION_RECEIPT_2026-09-03](docs/EXPERIMENT_MATRIX_IMPLEMENTATION_RECEIPT_2026-09-03.md) | matrix validator 的 clean-source synthetic receipt、negative/null retention與 fail-closed tests |
| [PAIRED_STATISTICS_IMPLEMENTATION_RECEIPT_2026-09-05](docs/PAIRED_STATISTICS_IMPLEMENTATION_RECEIPT_2026-09-05.md) | paired statistics/export 的 clean-source regression receipt、independent replay與保留狀態驗證 |
| [V7_ACTION_INTERFACE_PILOT_SPEC](docs/V7_ACTION_INTERFACE_PILOT_SPEC.md) | v7 三臂 DEVELOPMENT pilot 的 frozen action math、seeds、acceptance、failure semantics與 claim boundary |
| [V7_ACTION_INTERFACE_PILOT_IMPLEMENTATION_RECEIPT_2026-09-06](docs/V7_ACTION_INTERFACE_PILOT_IMPLEMENTATION_RECEIPT_2026-09-06.md) | v7 clean-source training/evaluation bundle、retained NULL、conditional statistics與 stdlib-only replay |
| [ENVIRONMENT_LOCK_SPEC](docs/ENVIRONMENT_LOCK_SPEC.md) | locked/observed 分界、behaviour fingerprints、缺失 lock 的表述與 verification semantics |
| [ENVIRONMENT_LOCK_IMPLEMENTATION_RECEIPT_2026-09-08](docs/ENVIRONMENT_LOCK_IMPLEMENTATION_RECEIPT_2026-09-08.md) | 實測 lock record、reduction-order 差異、v7 的 ABSENT_UNRECOVERABLE 判定與 EL-01..EL-10 |
| [TRAINING_SEED_VARIANCE_SPEC](docs/TRAINING_SEED_VARIANCE_SPEC.md) | independent training replicates、replicate-level analysis unit、censoring 向上組合、禁止 selection 與 SV-01..SV-12 |
| [TRAINING_SEED_VARIANCE_EXECUTION_RECEIPT_2026-09-08](docs/TRAINING_SEED_VARIANCE_EXECUTION_RECEIPT_2026-09-08.md) | 實際執行的 1,843,200 timesteps、450 records、method-level bounds、保留的 16 個 blockers 與過程中的自我修正 |
| [TRAINING_SEED_VARIANCE_IMPLEMENTATION_RECEIPT_2026-09-08](docs/TRAINING_SEED_VARIANCE_IMPLEMENTATION_RECEIPT_2026-09-08.md) | plant identity 量測、三條結構性規則的實作、synthetic regression 結果與未執行訓練的邊界 |
| [V7_EXPOSURE_CENSORING_AUDIT_SPEC](docs/V7_EXPOSURE_CENSORING_AUDIT_SPEC.md) | read-only exposure-censoring audit的 frozen horizon、phase conventions、censoring vocabulary、identification bounds與 acceptance |
| [V7_EXPOSURE_CENSORING_AUDIT_IMPLEMENTATION_RECEIPT_2026-09-08](docs/V7_EXPOSURE_CENSORING_AUDIT_IMPLEMENTATION_RECEIPT_2026-09-08.md) | audit software的 clean-source synthetic receipt、phase-convention finding、identification bounds與 frozen-bundle範圍邊界 |
| [V7_EXPOSURE_CENSORING_AUDIT_FROZEN_BUNDLE_RECEIPT_2026-09-08](docs/V7_EXPOSURE_CENSORING_AUDIT_FROZEN_BUNDLE_RECEIPT_2026-09-08.md) | 對 frozen v7 pilot bundle的 read-only audit run：實測 exposure分布、identification bounds、phase-convention finding與保留的 censoring blockers |
| [HARDWARE_DATA_PROVENANCE](docs/HARDWARE_DATA_PROVENANCE.md) | datasheet、CAD/BOM、bench data 與 demo catalog 的分級 |
| [ROADMAP](docs/ROADMAP.md) | V0–V4 gate-first 工作順序 |
| [CONVENTIONS](docs/CONVENTIONS.md) | 開發與 evidence governance 規範 |
| [CHANGELOG](CHANGELOG.md) | 對外 development release 變更紀錄 |

## 下一階段

目前不以「功能完成百分比」表示成熟度。V7 early-termination／exposure-censoring validity audit V1 已完成：software 在 clean-source synthetic regression 通過，並已對 2026-09-06 保存的 `V7_PILOT_DEVELOPMENT_BUNDLE` 執行一次 read-only run（`audit_applies_to_frozen_v7_pilot=true`、`AX-01..AX-12` 全通過、前後 readback 一致、保留 35 個 censoring blocker）。

實測 exposure：V7A 30/30 full exposure（恰 450 control steps）；V7B 27 full + 3 early（420–445 steps，全落在 `FINAL_STAND`，且六項 required outcome 仍為 `OBSERVED`）；V7C 30/30 early（`159.7000 ± 2.7687` steps、`3.08–3.30` s、占 horizon `0.354889`，全落在 `STEADY_WALK`）。

因此：V7C 的 0% duty 其 full-horizon bound 為 `[0.0, 64.511111]`%，與 V7A 的 `36.2185185`% 重疊，paired bound `[-36.2185185, +28.2925927]` 包含 0，`0/30` pair 方向可識別 —— pilot 報出的 `-36.2185185` pp 已被量測確認為 exposure artifact。V7B 的 paired bound 在 `30/30` pair 排除 0 且皆為 NEGATIVE，但 aggregate 仍為 `NULL`（3 個 censored pair，禁止 complete-case deletion），且 V7B 在 pilot 中仍不 eligible。

**Independent training-seed variance 已實際執行完成。** `SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1` 在 clean source `12bfddf` 上以具名 `MEASURED_ENVIRONMENT_LOCK`（`FULL_LOCK`／`AMBIENT_THREADING_PINNED`，共 30 次驗證）跑完 `3 arms × 5 replicates × 122,880 = 1,843,200` realized timesteps，**450 個 terminal records、0 失敗**，獨立 `python -I -S` replay exact。

實測結果：

- **V7B 相對 V7A 的方向跨獨立 seed 成立**：method-level bound `[-13.503408, -12.435259]` pp **排除 0**，sign `NEGATIVE`，`5/5` replicates 方向可識別。
- **但 `between_replicate_sd` 仍是 `null`**：每個 replicate 至少有一臂被 exposure censored，5 個 paired difference 全是 interval，sample SD 沒有定義在 interval 上。`sample_size_decision_input_ready = false`，**sample-size 決策仍然 blocked**。方向可識別與變異可估計是兩件事。
- **Pilot 那個乾淨的 reference 是 seed 的性質，不是 arm 的性質**：pilot 的 V7A 在 seed `8700` 上 30/30 full exposure、sd `0`；在 5 個獨立 seeds 上 V7A 有 3 個 replicate 出現 early termination（共 `7`/150）。
- **V7C 的崩潰跨 seed 完全重現**：5 個獨立 seeds 全部 30/30 early termination、30/30 `NULL`，bound `[-37.195407, +27.315704]` pp 含 0、`0/5` 可識別。它表面上的 `-37` pp 再次被量測確認為 exposure artifact。
- 450 個 episodes 全部是 `COMPARABLE`（`263`）或 `EXPOSURE_CENSORED`（`187`），**零 method failure**。

前置的 `ENVIRONMENT-LOCK-V1` 量測行為而非相信 version string（含實跑 `500` 步的 MuJoCo contact state digest 與實際執行的 torch optimiser step），並實測到同一組 1000 個 reciprocal 在同一環境下依 stdlib 順序相加得 `7.485470860550343`、交給 `numpy.ndarray.sum` 得 `7.485470860550345` —— 兩者都符合 IEEE 754。v7 的兩個 retained bundle 都在此 contract 之前產生，其 environment 狀態為 `ABSENT_UNRECOVERABLE`，因此
`cross_protocol_comparability = NON_VERIFIABLE_ENVIRONMENT`：seed-variance 的數值不得與 pilot receipt 的數值相減或並排成趨勢。

**下一個唯一優先目標是 independent pretraining-seed variance，或另立 selection protocol。** 5 個 replicate 共用同一個 v5 warm start，所以量到的是 fine-tuning 階段的 seed 變異，系統性**低估**完整 method variance。`selected_candidate_arm_id` 維持 `null`：V7B 的方向穩健性**不構成 selection** —— 用同一批資料先估變異再據以選擇，會把選擇條件建立在被選中的雜訊上；且本結果已公開，任何新 selection protocol 都必須明示它是在已知 V7B 為負的情況下設計的。`pilot_planning_ready`、`method_level_power_ready`、`statistics_ready`、`paper_data_ready` 全部維持 false。Study A actual matrix、binary paired CI、lock record 綁進 run manifest、immutable storage 與 formal authorization 仍未完成；這些 development evidence 不解除 V0/V1/V3 gate。

## 資料聲明

內建馬達與減速機型錄是 **representative demo data**，不是原廠 datasheet、CAD/BOM 或 bench evidence。更改介面數值不會自動提升證據等級。詳見 [HARDWARE_DATA_PROVENANCE](docs/HARDWARE_DATA_PROVENANCE.md)。
