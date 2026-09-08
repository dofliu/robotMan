# Gate-first 工作規劃

最後更新：2026-09-08

專案成熟度改以 **evidence gate** 表示，不再以 UI 或 feature count 換算完成百分比。既有 M1–M6 代表 prototype feature inventory，並非 verification 或 physical validation 已完成。

## 1. 目前狀態

| Gate | 目的 | 狀態 | 解除條件 |
|---|---|---|---|
| V0 Evidence & Provenance | 凍結 requirements、metrics、scenario、hash、hardware evidence class 與 raw artifact schema | PARTIAL IMPLEMENTED / NOT PASS | bounded input contracts、metric semantics、partial runtime provenance、UI evidence state 與 `ENVIRONMENT-LOCK-V1` 的可量測 environment identity 已有；仍須 immutable bundle、把 lock record 綁進 run manifest、validator 與完整 hash readback |
| V1 Plant & Numerical Verification | 驗證 equations、base wrench closure、constraints 與 numerical convergence | BLOCKED BY V0 | 所有 V1 oracle 通過，失敗案例保留 |
| V2 Actuator / Sensor / Estimator Fidelity | 建立 torque-speed、thermal、joint limits、latency/noise 與 estimator models | NOT STARTED | 來源與參數不確定性可追溯 |
| V3 Fair Benchmark & UQ | 公平 controller comparison、scenario strata、Monte Carlo、CI | FOUNDATION SOFTWARE PARTIAL / FORMAL NOT STARTED | protocol frozen、raw traces 完整、統計 gate 通過 |
| V4 Subsystem Validation | 以 SIL/HIL/bench evidence 校準並驗證 bounded subsystem claims | NOT STARTED | 外部量測與 acceptance criteria 通過 |

任一上游 gate 未通過，下游結果一律標記 BLOCKED，不可用 feature demo、software smoke test 或單一 nominal run 代替。

## 2. 既有 M1–M6 的重新分類

| 舊里程碑 | 已有內容 | 新證據定位 |
|---|---|---|
| M1 分析模式 | prescribed gait、analytical GRF、inverse dynamics、示意 actuator screening | FEATURE PRESENT / V1 NOT PASSED |
| M2 3D 與圖表 | visualization、telemetry display | UI VERIFIED ONLY AFTER dedicated tests |
| M3 障礙處理 | ideal raycast、rule-based step-over/stop | TEACHING DEMO / SENSOR VALIDATION ABSENT |
| M4 ZMP | cart-table-derived CoM/ZMP 與 scheduled support polygon | TRAJECTORY CONSISTENCY INDICATOR, NOT INDEPENDENT STABILITY VALIDATION |
| M5 即時互動 | MuJoCo forward contact simulation 與 controller | SIL-LIKE SIMULATION ONLY |
| M6 controller/RL | deterministic nominal comparison 與 PPO checkpoint | SOFTWARE SNAPSHOT / V3 NOT PASSED |

既有 comparison_report.md 保留為 regression snapshot；不得把其中的跌倒率、CoT 或抗推力解讀成一般化或實測結果。

## 3. V0 — Evidence & Provenance

優先度：最高，早於 M7、M8、M9。

工作項目：

1. [PARTIAL] `/api/simulate` 已提供 versioned metric set、deterministic content hash contract、config/model/code hashes、run/scenario ID、engine、evidence scope 與 created_at；frontend 已有 frozen/stale-result/evidence states，但尚未獨立驗證 server config hash。
2. [PARTIAL] Current REST/Live simulation inputs 已有 bounded fail-closed schema、cross-field numerical-resolution gate 與 structured WebSocket errors；尚未等同 project-wide formal evidence validator。
3. [PARTIAL] `ANALYSIS_METRICS_V1` 已明定 sampled motion/energy/CoT、peak/P99.5、window 與 null semantics；尚缺獨立 raw evaluator。
4. [TODO] 為每個 claim 建立 requirement ID、metric definition、oracle、acceptance gate 與 owner。
5. [PARTIAL] `PAPER_RUN_MANIFEST_V1` 已凍結 run-level protocol/controller/plant/scenario/seed/artifact fields；`ENVIRONMENT-LOCK-V1` 已提供可量測、可重驗的 environment identity，但 training/checkpoint 與 lock record 尚未串入所有 pipelines 的 run manifest。
6. [PARTIAL] V1 static V4與 analytical fixture V1均可輸出含 raw relative Jacobians的 10-role regression bundle，由 stdlib-only process重建 generalized force並回指 raw trace；project-wide immutable storage尚未完成。
7. [PARTIAL] Artifact inventory/bytes/SHA-256/path、clean-source/content-sensitive Git identity、exact model-package、experiment matrix validator、paired statistics/export V1 aggregate inventory/replay與 `ENVIRONMENT-LOCK-V1` measured environment identity已實作；lock record綁進 run manifest、project-wide immutable storage與 actual Study matrix尚未完成。
8. [DONE-D0] 將 built-in hardware catalog 定位為 D0 representative demo data。
9. [TODO] 建立 DEVELOPMENT、CALIBRATION、FORMAL_EVALUATION 分區。

驗收以 [VV_PLAN](VV_PLAN.md) 與 [EXPERIMENT_PROTOCOL](EXPERIMENT_PROTOCOL.md) 為準。

## 4. V1 — Plant & Numerical Verification

優先度：最高，早於 dynamic M7、WBC 與任何 RL paper。

最低範圍：

已開始：`v1_static_double_support_internal_v4` 通過 16/16 primary與 14/14 stdlib replay criteria；`EXP-V1-ANALYTICAL-FIXTURE-REGRESSION`另以 passive single-support、centered 5 kg simulated payload與 4/2/1 ms grid共 4/4 cases通過 primary/replay。Timestep QoI達 frozen stability gate，但差值進入 round-off區，observed order正確保留為 null。Jacobian、frame與wrench仍來自同一 MuJoCo engine，fixture也不是 articulated humanoid；known pendulum、dynamic contact、solver/finite-difference convergence與energy cases未完成，因此 V1仍未通過。

- constrained inverse dynamics 或等價 contact solve，滿足六個 floating-base equilibrium equations；
- base force/moment residual、joint torque residual 與 energy balance；
- unilateral normal force、friction cone、CoP in support area、contact schedule consistency；
- joint position/velocity/acceleration limits；
- solver convergence、time-step convergence、finite-difference sensitivity；
- analytical cases：static double support、single support、known pendulum、known payload；
- analysis result以 forward replay 做獨立 consistency check。

精確 tolerance 必須在正式執行前凍結，不可看結果後放寬。

## 5. V2 — Actuator、Sensor 與 Estimator

優先度：高，早於硬體 × strategy 結論。

- torque-speed-current-voltage envelope 與 continuous/peak duration；
- motor/drive efficiency map、thermal RC、regeneration policy；
- gearbox backlash、compliance、efficiency map、rated/peak load 與 lifetime boundary；
- joint hard/soft limits、self-collision 與 cable/routing constraints；
- encoder/IMU/LiDAR noise、bias、latency、dropout、quantization；
- state estimator 與 command/actuation delay。

所有參數依 [HARDWARE_DATA_PROVENANCE](HARDWARE_DATA_PROVENANCE.md) 分級；D0 不得產生 hardware feasibility claim。

## 6. V3 — Fair Benchmark & Uncertainty Quantification

優先度：高，早於 controller ranking、M9 paper 與 Pareto claim。

- controllers 使用同一 plant、initialization policy、assist policy、disturbance set 與 termination rules；
- energy 以 physics-step integration，明定 mechanical positive work、absolute work 或 electrical energy，不混用；
- 固定 nominal regression case，另設多 phase、terrain、friction、payload、delay、noise 與 disturbance strata；
- stochastic policy/training 使用 preregistered multi-seed design；
- 回報 raw episode values、effect size、confidence interval 與 censored/failed cases；
- push test 以 impulse、application point、gait phase、direction、duration 與 recovery criterion 完整定義。

Paired statistics/export V1已完成 synthetic software precursor：continuous paired effect/bootstrap CI、binary 2×2 counts/Wilson marginal descriptions、failure/null/censoring retention、hash-bound table/figure inputs與 stdlib-only exact replay均已驗證。v7 action-interface DEVELOPMENT pilot另完成 clean-source三臂/30 DEV seeds bundle與 raw-to-summary replay，但每臂只有一個 training seed；V7B有4個 negative，V7C有30個 early-fall NULL且 exposure不相等，沒有 selected candidate。`statistics_ready=false`、binary paired CI blocker與 `paper_data_ready=false`均保留，不構成 V3 PASS。接續的 exposure-censoring validity audit V1已實作並以 synthetic regression驗證：它把 method failure與 exposure censoring分開保留，對 exposure-censored primary outcome只輸出 assumption-free worst-case full-horizon與 paired identification bounds，並在30個 pair未全部 comparable時 blocked aggregate。Synthetic case顯示截斷臂的 paired bound包含 0、sign不可識別，因此截斷後的0% duty不可解讀為改善。frozen v7 bundle不在 clean checkout內，`audit_applies_to_frozen_v7_pilot=false`，仍不構成 V3 PASS。

### Development precursor：三機同步觀察

狀態：IMPLEMENTED / FRONTEND BUILD PASS / BROWSER VISUAL PENDING / DEVELOPMENT ONLY。依 [COMPARE_MODE_SPEC](COMPARE_MODE_SPEC.md) 建立三個獨立 MuJoCo sessions、相同輸入、同步 sim time、assist 預設關閉與跌倒保留。此功能用來暴露 controller 差異與改善實驗設計，不產生 V3 PASS 或 ranking evidence。

## 7. V4 — Subsystem Validation

V4 不等於整機認證。依風險逐級增加外部 evidence：

1. SIL：獨立 oracle 與 frozen simulation bundle。
2. HIL：real controller/drive interface，plant 仍為模擬。
3. Actuator bench：torque-speed、thermal、efficiency 與 saturation。
4. Leg/arm subsystem bench：joint tracking、load、contact、sensor/estimator。
5. Integrated robot experiment：另立 safety plan、instrumentation 與 acceptance protocol。

任何一級只能支持該級 bounded claim，不自動外推到整機安全或 sim-to-real。

## 8. Feature 路線重新排序

### Dynamic Run Trace Bridge

狀態：IMPLEMENTED / BUILD PASS / BROWSER VISUAL PENDING / DEVELOPMENT ONLY。依 [DYNAMIC_RUN_TRACE_SPEC](DYNAMIC_RUN_TRACE_SPEC.md) 將 Live/Compare 的 500 Hz realized simulation state 保存為 bounded NPZ + manifest，並由第一模式讀取。這是控制器技能開發與工程輸出分析之間的必要橋接，但不是 physical validation 或 V3 benchmark evidence。

### Motion Task V1：stand → start → steady walk → stop

狀態：V5 LIVE 10/11 CRITERIA / FAIL RETAINED / DEVELOPMENT ONLY。依 [MOTION_TASK_SPEC](MOTION_TASK_SPEC.md) 固定 9 秒 phase、0.7 m/s gait、assist OFF、session reset 與逐項 acceptance criteria。51-D phase-observable-v5 在 run `run-20260830t055847-rl_task_v5-b6c4781d` 無跌倒並完成 start/walk/stop，steady speed `0.585712 m/s`、progress `2.345757 m`、stop speed `0.042144 m/s`、lateral drift `0.045858 m`；唯一失敗為 saturation duty `38.422222% > 30%`。門檻未放寬，結果不可寫成 task PASS。

完成此 task framework 後，再以 registry 新增舉手、抬腳、深蹲與原地轉身。抬腳等平衡動作必須定義 contact/support acceptance，不能只新增視覺動畫。

### M7A — Arm pick-and-place teaching demo

可在 V0 後進行，但限定為 kinematic/visual teaching demo：

- target placement、end-effector IK、payload parameter visualization；
- UI 明示 prescribed motion 與 D0 hardware data；
- 不輸出「致動器可行」或「節拍驗證」結論。

### M7B — Arm dynamic design V&V

須等待 V1/V2：

- wrist/end-effector DOF、gripper/object contact、payload inertia；
- joint limits、collision、contact wrench 與 torque-speed/thermal constraints；
- independent forward replay 與後續 subsystem bench。

### M8 — QP/WBC baseline

WBC 必須早於 RL paper 與硬體 × strategy 正式比較。開始條件為 V1 contact feasibility gate 通過；驗收不能只用「走滿 10 秒」或單一推力門檻，必須同時檢查 constraints、residual、tracking、energy、failure strata 與 uncertainty。

### M9 — RL advanced study

多速度、domain randomization、能耗與硬體 × strategy 可在 V3 protocol frozen 後執行。若 V4 尚未通過，論文只能宣稱 SIM-only results，不可宣稱實體硬體效益或 sim-to-real。

Development 已完成 v1–v7 failure-retaining iteration：v2 解決前進與停止但 Live path/saturation 失敗；v3/v4/v5 依序加入 path/heading、terminal stability與 phase trend；v5在 Live達到10/11；v6證明單純加入500 Hz saturation reward不足。v7先凍結三臂 action-interface protocol，再於 clean source完成各 `122880` training steps及DEV `18000–18029`：V7A saturation `36.2185185%`；V7B `23.3896264%`但有4個 negative episodes；V7C 30/30 early fall、required outcomes為 NULL。Bundle/replay完整但 `selected_candidate_arm_id=null`、`pilot_planning_ready=false`。**V7 early-termination / exposure-censoring validity audit V1** 已在 frozen bundle 上完成，並量測確認 V7C 的 `-36.2185185` pp 是 exposure artifact。接續的 **`SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1`** 已凍結：5 個 independent fine-tuning training seeds、analysis unit 固定在 training replicate（method-level 分母恆為 `5`；`150`／`450` 為 forbidden denominators）、censoring 逐層組合為 interval、partial identification 直接封鎖 `between_replicate_sd`、selection 永久禁止。其 evidence contract、獨立 `python -I -S` replay 與 synthetic regression 均已驗證，且**已實際執行完成**：`1,843,200` realized timesteps、450 個 terminal records、0 失敗、replay exact。V7B 相對 V7A 的 method-level bound 為 `[-13.503408, -12.435259]` pp（排除 0、sign NEGATIVE、5/5 replicates 可識別），但 `between_replicate_sd` 因每個 replicate 都有 exposure censoring 而為 `null`，故 sample-size 決策仍 blocked；V7C 為 `[-37.195407, +27.315704]` pp 含 0、0/5 可識別。Independent **pretraining**-seed variance 經查證不可量測，`SELECT-V7-CANDIDATE-FORMAL-V1` 已凍結但不可執行，因此下一個唯一優先目標是取得 formal authorization；5 個 replicate 共用同一個 v5 warm start，量到的變異系統性低估完整 method variance。Actual Study matrix、paired binary CI、P1/P2/WBC與V3仍未通過；training-env result不是 Live trace、V3或實機證據。

## 9. 建議執行順序

工程軌道與學術軌道並行（學術軌道見 [PUBLICATION_PLAN](PUBLICATION_PLAN.md)）。工程順序：

0. [DONE] 執行 `SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1`：`1,843,200` realized timesteps、450 records、replay exact；V7B 方向 5/5 可識別，`between_replicate_sd` 因 exposure censoring 為 null。
1. 把 `ENVIRONMENT-LOCK-V1` 的 lock record 綁進每一條 pipeline 的 run manifest（V0 具名 blocker），再完成 actual matrix execution 與 immutable evidence storage。Environment identity 量測、run-level manifest/inventory 與 matrix completeness validators 均已 bounded implemented。
2. 建立一條**有版控 checkpoint lineage** 的新訓練線（scratch 或 tracked warm start，每個 checkpoint 進版控或 immutable storage）。這同時是 Track B 的硬前置，也是解除 exposure-censoring 對 between-replicate variance 封鎖的唯一途徑：需要一個能穩定跑完 9 s 任務的 reference policy。v7 line 因 provenance 不可重建，不能再作為這條線的起點。
3. Compare／Dynamic trace 的 browser visual verification（Playwright），解除兩個 `BROWSER_VISUAL_PENDING`。
4. 完成 V1 contact/plant/numerical verification（articulated dynamic、pendulum、energy、solver convergence）。
5. M7A 可作為教學支線；M7B 保持 blocked。
6. 完成 V2 actuator/sensor/estimator fidelity。
7. 建立 M8 WBC verified baseline。
8. 完成 V3 fair benchmark/UQ。
9. 進行 M7B 與 V4 subsystem validation。
10. 最後才啟動 M9 正式研究矩陣與 paper claim review。

## 10. 研究產出 gate

細節、PUB-* gate 與寫作規範以 [PUBLICATION_PLAN](PUBLICATION_PLAN.md) 為準；本節只定 V&V gate 與各類 claim 的對應：

- 教學展示（Track C 的前身）：V0 後可用，但必須保留 SIM-only 標示；要成為教學研究論文需另立學習成效研究設計。
- 評估效度／可重現性方法論（Track A）：**不要求 V1/V3 PASS**，因為它不對 plant 或 controller 做任何 claim，只對量測程序做 claim；但要求 PUB-A gates（novelty、第二案例 generalization、clean-checkout reproduction）全部通過。
- 工具方法論（把本平台本身當成 validated tool）：至少 V1 + V3。
- 方法比較論文（Track B／Study A）：至少 V1 + V3，且 formal authorization、external preregistration 與有版控 lineage 的訓練線齊備；沒有 V2 時不得對 actuator feasibility 做 claim，沒有 V4 時限縮為 simulation study。
- 硬體 × strategy 論文：至少 V1 + V2 + V3；沒有 V4 時限縮為 simulation study。
- sim-to-real、實體抗擾動或安全 claim：V4 仍不足時一律禁止。
