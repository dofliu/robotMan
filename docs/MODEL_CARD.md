# Model Card

## 1. Identity

- Model family：reduced-order humanoid simulation prototype
- Evidence scope：SIM-only
- Current lifecycle：V0 evidence rebaseline
- Physical validation status：NOT PHYSICALLY VALIDATED
- Intended audience：大學教學、robotics/control 開發者、早期 design screening 使用者

此 model card 管理 claim boundary；它不替代 run-specific experiment manifest。

## 2. Intended use

目前允許：

1. 教學展示：IK、inverse dynamics、CoM、ZMP、contact、controller、RL 概念。
2. Software regression：在 frozen code/config 下確認 output 是否發生變化。
3. Relative screening：在同一 assumptions 與同一 pipeline 中比較參數敏感度。
4. Hypothesis generation：找出值得以更高 fidelity simulation 或 bench 檢查的機制。
5. V&V method development：建立 residual、constraint、scenario 與 evidence pipeline。

允許的結論格式：

> [RESULT] 在 experiment X、model/config hash Y、scenario Z 下，parameter A 的 simulation metric 由 B 變為 C。
> [INFERENCE] 在目前 model assumptions 下，A 可能是值得進一步驗證的 design factor。
> [BLOCKER] 尚無 torque-speed/bench/subsystem evidence，不能外推為實體 hardware feasibility。

## 3. Out of scope

目前禁止：

- 實體機器人安全、certification、跌倒風險或 human interaction 判定；
- validated motor/gearbox/drive/battery selection；
- 採購、保固、continuous duty、lifetime 或 thermal design sign-off；
- 實測 GRF、CoP、push recovery、payload、energy efficiency；
- controller 一般優越性或跨 robot generalization；
- sim-to-real、HIL、field/industrial performance claim；
- clinical、prosthetic 或 human biomechanics inference；
- 未經 V4 的整機或 subsystem validation claim。

## 4. Model components

### Analysis mode

- prescribed footsteps、pelvis 與 arm trajectories；
- analytical leg IK；
- finite-difference velocity/acceleration；
- analytical total GRF 與 scheduled left/right sharing；
- MuJoCo inverse dynamics；
- simplified motor/gear conversion；
- cart-table ZMP/support-polygon indicator。

Analysis mode 不使用 contact solver 來求腳底 wrench。Live plant 已有 bounded static base-wrench、friction、CoP 與 raw-Jacobian arithmetic replay，但尚未涵蓋 dynamic contact、independent contact model、analytical scenario coverage 或 solver/time-step convergence。

### Live mode

- MuJoCo forward dynamics；
- simulated environment contact；
- constant torque saturation；
- trajectory tracking、Raibert 或 PPO controller；
- optional startup/balance assist、external push 與 obstacle。

Live mode 是 SIL-like simulation，不是 HIL 或 physical test。

## 5. Inputs

- simplified geometry and segment masses；
- representative motor/gear parameters；
- gait speed、step length、duty、clearance、pelvis motion、torso lean；
- obstacle geometry；
- controller selection/checkpoint；
- assist、push 與 simulation timing。

Formal use 必須保存 resolved values，不可只保存 UI screenshot。

## 6. Outputs

- joint position/velocity/torque；
- motor-side torque/speed/utilization estimates；
- simplified power/energy/CoT；
- CoM、scheduled contact/GRF、ZMP/support margin；
- live state/contact/controller telemetry；
- warning、termination 與 nominal comparison summary。

所有 output 都是 model-derived。只有與 frozen manifest、raw trace、oracle 與 gate 綁定後，才可稱為 V&V evidence。

## 7. Core assumptions

1. Robot 由 primitive geometry 與 lumped masses 近似。
2. Inertia 尚未以完整 CAD/mass-property report 校準。
3. Built-in actuator catalog 是 D0 demo data。
4. Analysis contact 由 prescribed schedule/CoP/GRF 表示。
5. Live contact 由固定 MuJoCo model parameters 表示。
6. Self-collision、cable routing、structural flexibility 與 manufacturing tolerance 未完整建模。
7. Constant peak torque 不代表完整 drive envelope。
8. Sensor/estimator noise、bias、latency、dropout 未完整建模。
9. 現有 controller benchmark 是 deterministic nominal snapshot。
10. 沒有 physical subsystem 或 integrated robot validation。

## 8. Known limitations and impact

| Limitation | Direct impact | Current evidence boundary |
|---|---|---|
| Floating-base wrench closure 僅完成 static MuJoCo case | dynamic joint torque 仍可能依賴未揭露或未驗證的 contact behavior | actuator sizing blocked |
| ZMP reference 與 indicator 共用 prescribed support assumptions | 矢狀 stability metric 非獨立 oracle | teaching/consistency only |
| 無 torque-speed/current/thermal model | high-speed/continuous feasibility 不可信 | D0 screening only |
| joint limits/self-collision 不完整 | motion may be mechanically unrealizable | workspace/gait feasibility blocked |
| contact/friction/CoP 僅完成 static internal/replay checks | slip/rotation/contact transition 不可信 | contact claim blocked |
| energy definitions/integration 未統一 | CoT 跨 mode/controller 可偏差 | ranking blocked |
| deterministic nominal repetitions | 沒有 population uncertainty | fall rate/generalization blocked |
| unpinned environment/checkpoint identity | reproduction 可能 drift | formal result blocked |
| ideal/simulator state sensing | estimator robustness 未測 | sensor claim blocked |
| 無 bench/HIL | physical adequacy 未知 | validation blocked |

## 9. Evidence labels

- [SOURCE]：可定位、可校驗的 source artifact。
- [RESULT]：由凍結方法產生並保留 raw data 的 outcome。
- [INFERENCE]：bounded interpretation，需列 assumptions。
- [HYPOTHESIS]：尚待 test 的預期。
- [BLOCKER]：阻止 claim 的缺口。

「程式存在」是 SOURCE；「software check 通過」可成為對應 requirement 的 RESULT；兩者都不是 physical validation。

## 10. Current evidence assessment

- [SOURCE] Analysis 與 live pipelines、controller、RL checkpoint、UI 和 software contract tests 已存在；analysis `/api/simulate` 已有 `ANALYSIS_METRICS_V1` 與 partial runtime provenance，current REST/Live simulation inputs 已做第一批 fail-closed hardening，frontend 已有 frozen/stale-result、evidence 與 intervention/error states。
- [SOURCE] comparison_report.md 保存一份 legacy nominal summary，但沒有對應 immutable raw bundle。
- [SOURCE] 現有 IK/GRF/smoke tests 編碼了 development checks；一次 console PASS 尚不是 formal [RESULT] receipt。
- [BLOCKER] Partial runtime metadata 尚缺 environment lock、immutable run bundle、raw artifact inventory 與 fail-closed validator；另無完整 requirement registry、base wrench gate、numerical convergence、fair benchmark/UQ 或 physical reference。
- [INFERENCE] 現階段最合理定位是 teaching/screening prototype，而非 humanoid design verification platform。

## 11. Risk controls

- 所有 UI 與文件維持 SIM-only 標示。
- Built-in hardware 維持 D0 demo class。
- Formal failure fail closed，不允許修改後混入同一 result set。
- Summary 必須回指 raw artifacts 與 hashes。
- SIL/HIL/bench/integrated robot claims 分層管理。
- 安全相關 physical experiment 需另立 risk assessment、test fixture、E-stop、instrumentation 與 institutional authorization。

## 12. M7/M8/M9 boundary

- M7A：可作 arm kinematic teaching demo。
- M7B：dynamic payload/contact claim 等待 V1/V2/V4。
- M8：WBC 在 V1 contact feasibility 後執行，並作為正式 RL comparison 前的 verified model-based baseline。
- M9：advanced RL 只在 V3 protocol 下形成正式 SIM-only result；physical claim 等待 V4。

## 13. Change control

下列修改會建立新的 model identity：

- geometry、mass/inertia、joint order/limits；
- contact/friction/solver/time step；
- actuator/sensor/estimator model；
- gait/contact schedule；
- controller、observation/action/reward；
- checkpoint 或 dependency environment；
- metric、filter、window、termination 或 acceptance threshold。

新 identity 不可沿用舊 gate result，除非 protocol 明確定義相容性並有 regression evidence。
