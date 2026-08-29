# Gate-first 工作規劃

最後更新：2026-08-26

專案成熟度改以 **evidence gate** 表示，不再以 UI 或 feature count 換算完成百分比。既有 M1–M6 代表 prototype feature inventory，並非 verification 或 physical validation 已完成。

## 1. 目前狀態

| Gate | 目的 | 狀態 | 解除條件 |
|---|---|---|---|
| V0 Evidence & Provenance | 凍結 requirements、metrics、scenario、hash、hardware evidence class 與 raw artifact schema | PARTIAL IMPLEMENTED / NOT PASS | bounded input contracts、metric semantics、partial runtime provenance 與 UI evidence state 已有；仍須 immutable bundle、environment lock、validator 與完整 hash readback |
| V1 Plant & Numerical Verification | 驗證 equations、base wrench closure、constraints 與 numerical convergence | BLOCKED BY V0 | 所有 V1 oracle 通過，失敗案例保留 |
| V2 Actuator / Sensor / Estimator Fidelity | 建立 torque-speed、thermal、joint limits、latency/noise 與 estimator models | NOT STARTED | 來源與參數不確定性可追溯 |
| V3 Fair Benchmark & UQ | 公平 controller comparison、scenario strata、Monte Carlo、CI | NOT STARTED | protocol frozen、raw traces 完整、統計 gate 通過 |
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
5. [TODO] 擴充並凍結 experiment manifest：checkpoint/environment SHA-256、seed、assist、disturbance、contact/solver parameters。
6. [TODO] 定義 raw artifacts 與 immutable result bundle；summary 必須可回指 raw trace。
7. [TODO] 建立 environment lock、artifact inventory/checksum 與 fail-closed validator。
8. [DONE-D0] 將 built-in hardware catalog 定位為 D0 representative demo data。
9. [TODO] 建立 DEVELOPMENT、CALIBRATION、FORMAL_EVALUATION 分區。

驗收以 [VV_PLAN](VV_PLAN.md) 與 [EXPERIMENT_PROTOCOL](EXPERIMENT_PROTOCOL.md) 為準。

## 4. V1 — Plant & Numerical Verification

優先度：最高，早於 dynamic M7、WBC 與任何 RL paper。

最低範圍：

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

狀態：IMPLEMENTED / BACKEND TEST PASS / FRONTEND BUILD PASS / BROWSER VISUAL PENDING / DEVELOPMENT ONLY。依 [MOTION_TASK_SPEC](MOTION_TASK_SPEC.md) 固定 9 秒 phase、0.7 m/s gait、assist OFF、session reset 與逐項 acceptance criteria。Live 執行單一 controller；Compare 以同一 contract 同步執行三個獨立 plants；Dynamic Trace Analysis 顯示每項 measured value 與 PASS/FAIL。第一組三 controller baseline 均為 FAIL，負結果已保留，下一輪須改善 stop/deceleration control，不調整既定門檻。

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

Development 實作順序為：先建立 versioned policy registry，再建立 0.4/0.7/1.0 m/s 不覆寫的 training profiles，之後才做 command-conditioned multi-speed 與 run/turn/terrain/disturbance curriculum。Training smoke 只驗證 pipeline，不是 policy performance evidence。

## 9. 建議執行順序

1. 完成 V0 documents、manifest schema 與 evidence inventory。
2. 完成 V1 contact/plant/numerical verification。
3. M7A 可作為教學支線；M7B 保持 blocked。
4. 完成 V2 actuator/sensor/estimator fidelity。
5. 建立 M8 WBC verified baseline。
6. 完成 V3 fair benchmark/UQ。
7. 進行 M7B 與 V4 subsystem validation。
8. 最後才啟動 M9 正式研究矩陣與 paper claim review。

## 10. 研究產出 gate

- 教學展示：V0 後可用，但必須保留 SIM-only 標示。
- 工具方法論：至少 V1 + V3。
- 硬體 × strategy 論文：至少 V1 + V2 + V3；沒有 V4 時限縮為 simulation study。
- sim-to-real、實體抗擾動或安全 claim：V4 仍不足時一律禁止。
