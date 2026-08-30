# Verification and Validation Plan

## 1. Purpose

本計畫把 humanoid simulation 的 requirement 連到 method、oracle、evidence、gate 與 status。任何 claim 若無對應 row 與 evidence bundle，預設為 BLOCKED。

## 2. Definitions

- Verification：程式與數值方法是否正確實作 specification。
- Validation：模型對指定 physical use case 是否足夠準確。
- SIL：software/controller 與 frozen simulated plant。
- HIL：real controller/drive interface 與 simulated plant。
- Bench：instrumented actuator/joint/leg/arm subsystem。
- Integrated robot：整機、safety-controlled physical experiment。

SIL PASS 不自動成為 HIL、bench 或 integrated robot PASS。

## 3. Requirement-to-evidence matrix

| Requirement | Method | Oracle | Required evidence | Gate | Status |
|---|---|---|---|---|---|
| V0-R01 每個 claim 有 owner 與 acceptance definition | 建立 requirement registry | schema + completeness check | registry、review record、hash | V0 | IN PROGRESS |
| V0-R02 每次 run identity 唯一 | hash code bundle/config/MJCF/checkpoint/environment | hash readback equality | manifest、files、checksums | V0 | PARTIAL: runtime hashes/IDs + PAPER_RUN_MANIFEST_V1 implemented; checkpoint/environment lock incomplete |
| V0-R03 hardware parameter provenance | 依 D0–D4 分級 | source/revision/page/unit completeness | provenance records | V0 | D0 ONLY |
| V0-R04 raw artifacts 可追溯 | summary-to-raw reference validation | zero missing/mismatch/path escape | inventory、hashes、gate receipt | V0 | PARTIAL: V1 regression bundle 10-role inventory/bytes/SHA/path readback implemented; immutable project storage/matrix linkage missing |
| V0-R05 外部輸入 fail closed | schema、cross-field 與 live command validation | invalid/NaN/unknown/inadequate-resolution case 全數拒絕 | contract tests、API/WebSocket receipt | V0 | PARTIAL PASS: current REST/Live simulation contracts covered; formal evidence validator and remaining external surfaces incomplete |
| V0-R06 runtime metric 定義固定 | versioned formula、window、unit 與 null semantics | independent recomputation equality | [METRIC_DEFINITIONS](METRIC_DEFINITIONS.md)、raw trace、oracle output | V0/V1 | PARTIAL: ANALYSIS_METRICS_V1 + regressions and bounded V1 contact raw replay implemented; project-wide independent evaluator/gate missing |
| V0-R07 result-input identity | frozen request snapshot + server hash readback | stale/race/mismatch case 不得顯示 CURRENT | frontend behavior receipt | V0 | PARTIAL: exact request snapshot/race/stale behavior implemented; server hash independently unverified |
| V1-R01 IK/FK correctness | analytical and MuJoCo round-trip cases | position/orientation tolerance frozen before run | per-case raw target/state/error | V1 | PARTIAL / NOT GATED |
| V1-R02 floating-base force equilibrium | constrained inverse dynamics / residual audit | normalized base force residual below preregistered tolerance | full generalized force/contact traces | V1 | PARTIAL: static contact-wrench/Jacobian reconstruction and process replay PASS; raw Jacobian/dynamic cases missing |
| V1-R03 floating-base moment equilibrium | full 6D contact wrench closure | normalized base moment residual below preregistered tolerance | wrench/Jacobian/residual traces | V1 | PARTIAL: static 6-D reconstruction and process replay PASS; independent contact model and dynamic cases missing |
| V1-R04 joint torque equation closure | recompute inverse dynamics with solved contacts | generalized equation residual and independent replay | q/qd/qdd/tau/contact/model traces | V1 | PARTIAL: static contact generalized-force closure and receipt replay PASS; raw Jacobian/full equation replay missing |
| V1-R05 unilateral contact | inspect each contact normal force | all active Fz nonnegative within tolerance | contact trace + violation list | V1 | PARTIAL: static case minimum active normal force gate PASS; scenario coverage missing |
| V1-R06 friction feasibility | friction cone/pyramid constraint | tangential force inside frozen friction model | friction params + per-contact ratios | V1 | PARTIAL: frozen PYRAMIDAL/condim=3 static utilization and process replay PASS; dynamic scenarios missing |
| V1-R07 CoP/support feasibility | derive CoP from full wrench/contact distribution | CoP inside active foot support; torsional constraint satisfied | wrench/pressure/contact geometry | V1 | PARTIAL: foot-local aggregate-wrench static CoP and process replay PASS; transitions/torsional cases missing |
| V1-R08 contact schedule consistency | compare prescribed and solved/forward contact | event matching tolerance and no unsupported flight/contact | event trace | V1 | NOT STARTED |
| V1-R09 joint limits | apply position/velocity/acceleration/hard-stop limits | zero unreported violations | limit source + time trace | V1 | BLOCKED |
| V1-R10 actuator torque-speed feasibility | evaluate motor/drive envelope at each time step | all operating points within D1+ envelope and duration rules | envelope source + operating trace | V1/V2 | BLOCKED |
| V1-R11 numerical convergence | time-step, solver tolerance and finite-difference study | metric/residual convergence under preregistered criterion | convergence table + raw runs | V1 | PARTIAL: one 500 Hz internal fwd/inv case; time-step study missing |
| V1-R12 solver convergence | log status, iterations, infeasibility, conditioning | zero hidden failure; declared handling of infeasible cases | solver trace | V1 | PARTIAL: fwd/inv force residual sampled; iterations/infeasibility bundle missing |
| V1-R13 energy consistency | power balance and physics-step integration | independent recomputation agreement | tau/omega/drive-loss trace | V1 | BLOCKED |
| V1-R14 analytical reference cases | static double support、single support、known pendulum、known payload | closed-form/reference solution | case bundle and error report | V1 | PARTIAL: bounded static double-support internal reference implemented; independent cases missing |
| V2-R01 actuator thermal fidelity | thermal RC or identified equivalent | bench/datasheet transient within tolerance | source/model/fit/validation split | V2 | NOT STARTED |
| V2-R02 transmission fidelity | backlash/compliance/efficiency map | bench or qualified source comparison | transmission records | V2 | NOT STARTED |
| V2-R03 sensor model | noise/bias/latency/dropout/quantization | match independent sensor characterization | raw sensor data + fit/holdout | V2 | NOT STARTED |
| V2-R04 state estimator | replay recorded or simulated sensor streams | preregistered state error/latency metrics | input/output traces | V2 | NOT STARTED |
| V3-R01 fair controller protocol | same plant/init/assist/disturbance/termination | manifest equality except controller fields | paired run manifests | V3 | FOUNDATION PARTIAL: paper run contract exists; paired matrix validator/orchestrator missing |
| V3-R02 deterministic regression | exact frozen nominal case | hash and tolerance comparison | baseline bundle + diff | V3 | SNAPSHOT EXISTS / UNGATED |
| V3-R03 scenario coverage | stratified phase/terrain/friction/payload/delay/noise/disturbance | all preregistered cells executed | scenario matrix + completeness receipt | V3 | NOT STARTED |
| V3-R04 Monte Carlo design | frozen distributions and seed list | seed/cell completeness, no cherry-pick | seed manifest + raw episodes | V3 | NOT STARTED |
| V3-R05 uncertainty reporting | paired effect size + suitable CI | preregistered method; failures/censoring retained | statistics code/output | V3 | NOT STARTED |
| V3-R06 RL reproducibility | multi training/evaluation seeds | checkpoint/config/environment identity + distribution of outcomes | training/eval bundles | V3 | BLOCKED |
| V3-R07 push robustness | phase/point/direction/impulse strata | recovery criterion and censored upper bounds | force/contact/state traces | V3 | NOT STARTED |
| DCOMP-R01 三 controller plant isolation | 三個獨立 LiveSession、固定 controller identity | session/model identity 與無 cross-contact state | contract/integration tests | DEVELOPMENT | SOFTWARE TEST PASS / NOT V3 EVIDENCE |
| DCOMP-R02 同輸入同步時間 | shared validated commands + identical bounded advance | 每 frame time skew 在 tolerance 內 | compare frame receipts/tests | DEVELOPMENT | SOFTWARE TEST PASS / BROWSER VISUAL PENDING / NOT V3 EVIDENCE |
| DCOMP-R03 intervention disclosure | assist default OFF + per-frame readback | 三組 intervention flags 一致且可見 | backend/frontend tests | DEVELOPMENT | SOURCE+BUILD PASS / BROWSER VISUAL PENDING / NOT V3 EVIDENCE |
| TRACE-R01 realized physics trace | 500 Hz bounded recorder + NPZ/manifest | sample count/rate/shape/dtype/hash equality | recorder/artifact/API tests | DEVELOPMENT | SOFTWARE TEST PASS / NOT PHYSICAL EVIDENCE |
| TRACE-R02 cross-mode analysis bridge | first-mode Dynamic Trace source | completed trace identity and bounded series visible | API contract + frontend build | DEVELOPMENT | SOURCE+BUILD PASS / BROWSER VISUAL PENDING |
| TRACE-R03 comparison trace pairing | shared group ID + independent controller traces | group/time equality | comparison integration test | DEVELOPMENT | SOFTWARE TEST PASS / NOT V3 EVIDENCE |
| TASK-R01 fixed motion-task contract | versioned task registry + fixed initialization/gait/phase timing | task manifest equals frozen specification | task spec、manifest、contract tests | DEVELOPMENT | SOFTWARE TEST PASS / BROWSER VISUAL PENDING |
| TASK-R02 measurable task outcome | independent evaluator over 500 Hz trace | all preregistered criteria have measured value and deterministic PASS/FAIL | raw trace、evaluation receipt、unit tests | DEVELOPMENT | SOFTWARE TEST PASS / FIRST BASELINE FAIL RETAINED |
| TASK-R03 synchronized controller task | shared task/group ID across isolated plants | phase timing and task contract equality | comparison traces + integration test | DEVELOPMENT | SOFTWARE TEST PASS / NOT V3 EVIDENCE |
| V4-R01 independent SIL replay | frozen model + independent evaluator | agreement with primary metrics and gates | independent receipt | V4-SIL | NOT STARTED |
| V4-R02 HIL timing/interface | real controller/drive communication | deadline, jitter, packet loss, command/feedback correctness | HIL logs | V4-HIL | NOT STARTED |
| V4-R03 actuator bench | torque-speed/thermal/efficiency/saturation | holdout bench agreement | calibration + validation datasets | V4-BENCH | NOT STARTED |
| V4-R04 leg/arm subsystem bench | tracking/load/contact/sensor behavior | preregistered bounded error | instrumented bench bundle | V4-BENCH | NOT STARTED |
| V4-R05 integrated robot | safety-controlled robot experiment | use-case-specific acceptance | safety plan + raw measurements | V4-ROBOT | OUT OF CURRENT SCOPE |

## 4. Gate definitions

### V0 Evidence & Provenance

PASS requires：

- requirement registry complete；
- model/run identity scheme operational；
- manifest and raw artifact schemas frozen；
- hardware records classified；
- DEVELOPMENT/CALIBRATION/FORMAL partitions defined；
- fail-closed validator rejects missing or mismatched evidence。

### V1 Plant & Numerical Verification

PASS requires：

- six floating-base equilibrium components close within preregistered normalized tolerances；
- joint dynamics residuals close；
- unilateral/friction/CoP/contact constraints satisfied；
- joint and actuator constraints evaluated；
- solver/time-step/finite-difference convergence documented；
- energy metric independently recomputable；
- analytical reference suite complete。

### V2 Actuator / Sensor / Estimator

PASS is subsystem-specific。Actuator PASS、sensor PASS 與 estimator PASS 分開記錄，不合併成整機 validation。

### V3 Fair Benchmark & UQ

PASS requires：

- paired/fair manifests；
- complete scenario and seed matrix；
- physics-step metrics；
- failures and censoring retained；
- effect sizes and CI；
- no formal-to-development feedback。

### V4 Subsystem Validation

PASS 必須標註 SIL、HIL、actuator bench、leg/arm bench 或 integrated robot level。不可用上游 simulation 自我確認 physical adequacy。

## 5. Fail-closed rules

1. Missing requirement/oracle/tolerance → 不執行 formal run。
2. Identity drift → 停止並保留已有 artifacts。
3. Solver failure、NaN、constraint violation、residual failure → case FAIL，不 repair output。
4. Formal result 失敗後修改 config/code/metric/threshold → 新 protocol version、新 experiment ID。
5. 不刪除 negative/null/censored cases。
6. 不以 TEST/holdout case 選擇修正方法。
7. Summary 與 raw count/hash 不一致 → entire bundle FAIL。
8. Physical evidence 不足 → claim 保持 SIM-only。

## 6. Residual and constraint reporting

每個 dynamics case 至少回報：

- base force residual norm，並以 Mg 正規化；
- base moment residual norm，並以 Mg × characteristic length 正規化；
- actuated joint equation residual；
- per-foot 6D wrench；
- minimum normal force、maximum friction utilization；
- CoP distance to support boundary；
- joint limit/velocity/acceleration utilization；
- torque-speed/current/thermal utilization；
- solver status、iterations、conditioning；
- energy balance residual。

報告 p50/p95/max 之外，保留完整 time trace 與所有 violation timestamps。

## 7. Scenario plan

最低 scenario dimensions：

- gait：stand、start、steady walk、stop、turn、run/flight；
- speed/step/duty；
- contact phase；
- terrain slope/height/roughness；
- friction；
- payload and mass/inertia uncertainty；
- actuator strength/latency；
- sensor noise/bias/dropout；
- push direction/point/impulse/timing；
- controller/checkpoint；
- assist policy。

Nominal case 用於 deterministic regression；不得代表 scenario coverage。

## 8. Monte Carlo and confidence intervals

- distributions、bounds、correlations、sample size、seed list 在 formal run 前凍結；
- paired scenarios 優先使用 paired effect；
- continuous metrics 回報 effect size 與 preregistered bootstrap或 parametric CI；
- fall/recovery 等 binary metrics 使用適合小樣本的 interval；
- time-to-fall/threshold search 保留 censoring；
- 多重 metrics/strata 的 inference policy 預先定義；
- 如果 sample size不足，只報 descriptive result 與 BLOCKER，不包裝成顯著性。

## 9. SIL / HIL / Bench boundaries

| Level | Real component | Simulated component | Allowed claim |
|---|---|---|---|
| Software check | none | all | code requirement only |
| SIL | controller software | robot/drive/sensor/terrain | frozen simulation behavior |
| HIL | controller/communication, optionally drive electronics | mechanical plant/environment | interface/timing and bounded controller behavior |
| Actuator bench | motor/gear/drive/load fixture | rest of robot | actuator subsystem |
| Limb bench | actuator、structure、sensor、contact fixture | remaining robot/tasks | bounded limb subsystem |
| Integrated robot | whole robot | scripted environment may remain | only tested conditions with safety controls |

## 10. Evidence bundle requirements

每個 gate result 必須包含：

- requirement IDs；
- protocol/experiment/scenario IDs；
- resolved configuration；
- code/config/model/checkpoint/environment identities；
- raw state/control/contact/solver/event traces；
- metric and statistics outputs；
- stdout/stderr/exit code；
- artifact inventory and SHA-256；
- pass/fail/blocker summary；
- reviewer and timestamp。

## 11. Immediate blockers

- code checkout 缺少可引用的 version identity；
- runtime config/model/code/result hashes 與 run/scenario IDs 已 partial implemented，但尚未形成 immutable source/run identity；
- dependencies 未完整 pin，environment lock 缺失；
- run-level paper manifest與 V1 regression bundle inventory/validator已有；project-wide immutable storage與 matrix validator尚未實作；
- base wrench、friction 與 CoP 已進入 bounded static oracle及 process replay；raw Jacobian與 dynamic gate 尚未完成；
- joint/actuator/contact/solver constraints 不完整；
- benchmark energy/fairness/UQ 未 gate；
- built-in hardware 仍為 D0；
- 無 HIL 或 bench evidence。
