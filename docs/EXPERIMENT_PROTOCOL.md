# Experiment Protocol

## 1. Status

- Protocol family：HUMANOID-SIM-V0
- Current status：TEMPLATE / NOT YET AUTHORIZED FOR FORMAL CLAIMS
- Owner：project PI or designated experiment owner
- Applies to：analysis、live、controller comparison、RL training/evaluation、SIL/HIL/bench handoff

正式結果必須建立 versioned protocol instance。僅執行 script 或產生 Markdown report 不算 protocol completion。

`PAPER_RUN_MANIFEST_V1` 與 fail-closed artifact validator 已建立 run-level contract；V1 static/analytical suites可保存 raw relative Jacobians，並由不載入 MuJoCo/controller 的另一 process重建 generalized force。`EXPERIMENT_MATRIX_SPEC_V1`以 frozen spec/index hash、exact cell identity與 dedicated-root scan檢查 missing、duplicate、unexpected、unindexed及 status retention；`PAIRED_STATISTICS_SPEC_V1`另將 explicit pairing、outcome/failure semantics、continuous CI與 machine-readable paper inputs凍結，並由 stdlib-only process exact replay。這些仍只是 bounded software contracts；project-wide immutable storage、actual Study matrix、remaining dynamic coverage、binary paired CI、sample-size decision與 formal authorization仍未完成。完整架構見 [PAPER_DATA_READINESS](PAPER_DATA_READINESS.md)、[EXPERIMENT_MATRIX_CONTRACT](EXPERIMENT_MATRIX_CONTRACT.md)與 [PAIRED_STATISTICS_CONTRACT](PAIRED_STATISTICS_CONTRACT.md)。

## 2. Run classes

| Class | 用途 | 可否調參 | 可否形成正式結果 |
|---|---|---|---|
| DEVELOPMENT | 除錯、探索、選方法 | 可以，需留 log | 否 |
| CALIBRATION | 使用指定資料/情境定參 | 只依預定範圍 | 不可作 independent validation |
| FORMAL_EVALUATION | 凍結後評估 | 不可 | 是，前提為 gate 完整 |
| REGRESSION | 確認 frozen software output | 不可改 baseline 來過關 | 只支持 software identity |

Formal evaluation case 不得回流為 tuning data。若看過結果後修改方法，原 case 保留，後續使用新 protocol version。

## 3. 必填 manifest

每次 run 需保存 machine-readable manifest，至少包括：

### Identity

- protocol_id、protocol_version；
- experiment_id、run_id、scenario_id、replicate_id；
- run_class；
- timestamp、operator、host；
- source code Git SHA；若 checkout 無 Git，使用完整 source bundle SHA-256；
- resolved config SHA-256；
- generated MJCF SHA-256；
- controller/checkpoint SHA-256；
- environment lock SHA-256；
- Python、MuJoCo、NumPy、Gymnasium、Stable-Baselines3、PyTorch 與 OS versions。

### Randomness

- global seed；
- environment seed；
- training seed；
- policy/evaluation seed；
- Monte Carlo seed；
- deterministic flags；
- seed schedule artifact SHA-256。

若某 pipeline 無 randomness，明記 deterministic=true，而不是把相同 rerun 當 independent replicate。

### Plant and numerical settings

- geometry、mass/inertia、payload；
- joint limits；
- actuator/drive/transmission model IDs 與 provenance classes；
- sensor/estimator model IDs；
- contact/friction/solver parameters；
- physics step、control step、sample step；
- solver、tolerance、iteration limit；
- filtering/smoothing/window definitions。

### Intervention

- controller identity；
- startup assist、balance assist、external fixture/virtual support；
- disturbance type、force/impulse、direction、application point、start time、gait phase、duration；
- obstacle/terrain；
- initialization；
- termination and recovery criteria。

所有 assist 預設為 intervention，不屬於 robot capability。未記錄 assist 的 run 不可進入 formal comparison。

### Metrics

- metric names and versions；
- units；
- numerator/denominator；
- sampling/integration；
- transient/window/exclusion rules；
- missing/failure/censoring handling；
- aggregation and CI method；
- acceptance thresholds and rationale。

目前 analysis runtime 的具體公式與限制由 [METRIC_DEFINITIONS](METRIC_DEFINITIONS.md) 管理；formal protocol 必須引用 exact metric set version，不可只寫 UI label。

## 4. Freeze sequence

1. 建立 requirement IDs 與 claims。
2. 選定 scenario matrix 與 sample size。
3. 凍結 plant、controllers、assist、disturbances、seeds、metrics、oracle、thresholds。
4. 產生 manifest、config、model、environment 與 seed hashes。
5. 由獨立 validator readback。
6. 執行 formal runs。
7. 先封存 raw artifacts，再計算 metrics。
8. 產生 aggregate statistics 與 gate result。
9. 驗證 counts、hashes、links 與 failure retention。

任一 freeze/readback 失敗即停止。

## 5. Scenario design

### Nominal regression

一個固定 scenario 用於 software drift detection。它是 n=1 deterministic case，不估計 population performance。

### Formal scenario strata

至少涵蓋：

- initial gait phase；
- speed/step/duty and start/stop/turn；
- terrain/contact/friction；
- payload and mass/inertia variation；
- actuator strength/latency and drive saturation；
- sensor noise/bias/dropout；
- push point/direction/impulse/timing；
- assist off/on as separate declared strata；
- controller/checkpoint and training seed。

Scenario cells 在執行前凍結；缺 cell、重複 cell、unexpected cell或 dedicated root內未索引 manifest都是 completeness failure。V1 exact semantics見 [EXPERIMENT_MATRIX_CONTRACT](EXPERIMENT_MATRIX_CONTRACT.md)。

## 6. Fair controller comparison

除 controller-specific identity 外，下列欄位必須相同或由 paired design 明確控制：

- plant and model hashes；
- initialization and gait phase；
- assist and startup intervention；
- disturbance and terrain；
- control/physics/sample timing；
- termination and recovery criteria；
- metric implementation；
- scenario and seed list。

Controller load/fallback mismatch必須 FAIL CLOSED。不得以 requested label 取代 actual controller identity。

WBC 作為 model-based baseline 時，需先通過 V1 contact/constraint gate，並在 RL formal comparison 前凍結。

## 7. Metrics

### Dynamics and feasibility

- base force/moment residual；
- joint equation residual；
- unilateral/friction/CoP utilization；
- joint position/velocity/acceleration utilization；
- torque-speed/current/thermal utilization；
- solver convergence and infeasibility。

### Locomotion/control

- forward/lateral velocity tracking；
- pose/foot tracking；
- survival/time-to-fall；
- distance；
- recovery time；
- saturation duration；
- contact/slip events。

### Push robustness

「maximum force」不足以獨立定義 robustness。正式 metric 必須包含：

- force-time profile and impulse；
- application point；
- direction；
- gait phase/contact state；
- recovery horizon and acceptance；
- upper search bound and censoring。

### Energy

每項 study 只能選擇並清楚命名：

- positive joint mechanical work；
- absolute joint mechanical work；
- electrical energy with drive/efficiency model；
- net electrical energy with regeneration。

以 physics step 積分，並用 independent recomputation oracle。不同定義的 CoT 不可直接比較。

### Stability

- analysis ZMP/support 指標標記為 trajectory-consistency metric；
- live fall/contact outcome標記為 simulated-plant metric；
- physical validation 使用外部 force/pose/contact instrumentation。

三者不能合併成單一「穩定度」。

## 8. Statistics and UQ

- nominal deterministic run 不計 confidence interval。
- stochastic/uncertain study 使用 preregistered seeds/distributions。
- paired controller study回報 paired differences。
- continuous metrics回報 raw values、effect size、CI。
- binary fall/recovery回報 count、denominator與適當 interval。
- threshold search回報 resolution、bounds與censoring。
- failures、NaN、solver infeasible、early termination一律保留並依 protocol處理。
- 不以只剩成功 cases 的平均值作性能結論。
- V1 aggregate contract對 continuous metrics使用 pair-level candidate-minus-reference mean、median、Cohen dz與 deterministic paired percentile bootstrap；CI只對應 mean difference。
- Binary outcome保留 paired 2×2 counts與 marginal Wilson descriptions；在 matched-pair CI 尚未通過 published golden-case oracle前，paired CI必須為 null/blocker，不得以 marginal intervals取代。
- `NULL`、`NONFINITE`、`CENSORED`阻擋對應 outcome inference；`FAILED`仍在 denominator內，只有事先定義的 terminal-failure binary outcome才能明示寫為 observed false。

## 9. Raw artifacts

最低保存：

- manifest and resolved config；
- exact MJCF/model；
- controller/checkpoint identity；
- environment/system information；
- q、qd、qdd；
- command/torque/actuator state；
- contact points/forces/wrenches；
- contact frame與 `body2 - body1` relative translational/rotational Jacobians；
- CoM/base state；
- sensor/estimator streams；
- assist/disturbance/event/termination log；
- solver trace；
- per-step energy terms；
- per-run metrics；
- aggregate statistics；
- stdout/stderr/exit code；
- checksums and artifact inventory。

圖表、UI screenshot、comparison_report.md 或 console summary 不是 raw artifact substitute。

## 10. Formal failure and change control

正式 run 出現 failure 後：

1. 立即保存 raw output、trace、manifest、exit code 與 failure reason。
2. 不 repair、刪除、重標、補值或只重跑不利 case。
3. 不放寬 threshold、換 metric、改 window/filter 或縮小 scenario matrix。
4. 不使用 holdout/formal cases選擇 reward、controller、solver 或 model 修正。
5. 若需修改，建立新 hypothesis、protocol version、experiment ID 與完整 frozen matrix。
6. 舊 failure 永久保留並在後續 report 說明。

## 11. SIL / HIL / Bench execution

- SIL：保存 frozen simulated plant 與 independent metric evaluator。
- HIL：另存 command/feedback timing、jitter、packet loss、clock synchronization 與 safety interlock。
- Bench：保存 instrument calibration、sampling rate、fixture、load cell/encoder traces、uncertainty、calibration/validation split。
- Integrated robot：必須有安全負責人、risk assessment、E-stop、exclusion zone、test progression 與 abort criteria。

沒有相應 artifact 時，不得提升 evidence level。

## 12. Result package

Formal result package 至少回答：

1. 哪一個 requirement？
2. 哪一個 model/plant/controller identity？
3. 哪些 scenario/seeds？
4. 哪個 metric/oracle/gate？
5. 哪些 raw artifacts？
6. 哪些 failure/censoring？
7. uncertainty 多大？
8. claim 可以到哪個 SIL/HIL/bench boundary？
9. 哪些 blocker 仍存在？

## 13. Legacy snapshot

目前 comparison_report.md 是 legacy deterministic nominal snapshot。保留作 software regression/teaching reference，但不納入 formal V3 result，除非依本 protocol 重新執行並產生完整 evidence bundle。
