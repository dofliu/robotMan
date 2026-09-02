# V1 Analytical Fixture Suite — Frozen V1

最後更新：2026-09-02

狀態：`IMPLEMENTED AND REGRESSION PASS / V1 PARTIAL / SIM_ONLY_MUJOCO`

## 1. 本次唯一 milestone

新增一個不經 `LiveSession`、controller 或 assist 的 passive analytical fixture，
一次建立四個 exact raw cases：nominal single support 的 `4/2/1 ms` grid，及
`2 ms + 5 kg` centered known-payload case。`2 ms` nominal case同時是
single-support、payload baseline與 timestep-medium；它是同一 raw identity的明示
alias，不是第二個 independent replicate。

Fixture 是具有 free joint、20 kg carrier、單一 rectangular support geom與零外力的
剛體。Known payload是 fixture中心線上的 simulated lumped mass，不代表手持物、
偏心 inertia、實體負載介面或 actuator capacity。

## 2. Frozen acceptance criteria

- Exact case/model inventory，不允許 missing、duplicate、unexpected或未執行 cell。
- 每 case保存 exact config/MJCF SHA-256、compiled timestep/model mass、完整 raw
  state、applied force、solver、contact frame/wrench與 `body2 - body1` relative
  Jacobians。
- Duration固定 `1.2 s`，science window固定 `(0.8, 1.2]`；absolute time grid
  誤差 `<= 1e-12 s`。
- Raw `J^T wrench` 對 `qfrc_constraint` closure `<= 1e-9`；MuJoCo
  forward/inverse兩個 diagnostics各 `<= 1e-8`。
- Evaluation window每步只能由 `support_foot` 對 `floor`承載；不得有其他 support、
  hidden `qfrc_applied/xfrc_applied`、adhesion或 controller/assist。
- Normal force `>= -1e-8 N`、pyramidal friction utilization `<= 1+1e-9`、
  CoP margin `>= -1e-9 m`、mean linear/angular speed各 `<= 1e-3`，且
  mean GRF 對 frozen `Mg`相對誤差 `<= 2%`。
- Compiled payload mass increment對 `5 kg`誤差 `<= 1e-12 kg`；paired mean GRF
  increment對 `5g`相對誤差 `<= 2%`。
- Timestep QoI固定為 evaluation-window `mean vertical GRF / model weight`。
  `|Q_2ms-Q_1ms| <= 5e-4`，且不得大於
  `max(|Q_4ms-Q_2ms|, 1e-10)`。非 timestep config必須完全一致。
- Observed order只有兩個 successive differences皆大於 `1e-10`、同號且可估時才
  回報；round-off limited或 non-monotonic時保存 `null`與 diagnostic status，不產生
  NaN，也不把 null補成 order PASS。

上述 threshold凍結於
`backend/v1_analytical_suite.py::ANALYTICAL_SUITE_CONTRACT`，不得依首輪結果放寬。

## 3. Failure semantics

- 任一 finite criterion失敗：case/suite為 `FAIL`，raw不刪除、不補值、不 repair。
- Schema、hash、case identity、compiled setting或 non-finite mismatch：fail closed，
  bundle保留 `FAILED`、stdout/stderr與 failure record。
- `KeyboardInterrupt`/`SystemExit`：bundle保留 `CANCELLED`與 diagnostic，不冒充
  completed case。
- Independent replay在另一 process只用 Python standard library，從 raw
  frame/wrench/Jacobian與 model package重算；不讀 primary自報 PASS。
- Bundle僅可回報 `REGRESSION_BUNDLE_VALID_ONLY / paper_data_ready=false`。

## 4. Claim boundary與學理依據

- [SOURCE] MuJoCo的 continuous equations使用 `M vdot + c = tau + J^T f`，
  timestep只作用於後續 integration；`solver_fwdinv`是 solver accuracy diagnostic，
  不能取代 timestep study：
  [MuJoCo Computation](https://mujoco.readthedocs.io/en/3.12.0/computation/)。
- [SOURCE] Rectangular surface contact的 admissibility同時涉及 Coulomb friction、
  ZMP/CoP在 support area內與 yaw-torque bounds：
  [Caron, Pham & Nakamura, ICRA 2015](https://arxiv.org/abs/1501.04719)。
- [SOURCE] NASA-STD-7009B要求保存 discretization、iterative convergence與
  finite-precision等 numerical-error evidence，並明示未完成 verification/validation的
  面向：
  [NASA-STD-7009B](https://standards.nasa.gov/sites/default/files/standards/NASA/B/1/NASA-STD-7009B-Final-3-5-2024.pdf)。
- [INFERENCE] Nonsmooth contact不保證穩定 observed order，因此本 milestone以
  三層 grid-refinement stability為 gate，order只作可為 null的 diagnostic。
- [RESULT] Contract先於首次執行凍結，首個 clean-source bundle在未調整 threshold下通過 4/4 primary cases與 stdlib-only replay；exact evidence見下節。
- [BLOCKER] Fixture不是 articulated humanoid、external physical referent或獨立
  contact model。即使全部 PASS，V1仍保持 partial。

固定 evidence boundary：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`。不得外推為
實體機器人平衡、payload能力、sim-to-real、安全性或 controller superiority。

## 5. Clean-source bounded result

完整 receipt見 [V1 Analytical Suite Implementation Receipt](V1_ANALYTICAL_SUITE_IMPLEMENTATION_RECEIPT_2026-09-02.md)。

- [RESULT] Source Git SHA為 `b39a5ea2524a10189959d4968a9a7e15747fbf59`；
  run前後 worktree皆 clean且 source identity stable。
- [RESULT] Primary/replay皆 `PASS`，4/4 exact cases通過；payload mass delta error
  `0 kg`，payload GRF delta relative error `1.303748139009358e-15`。
- [RESULT] 4/2/1 ms QoI依序為 `1.0000000000000078`、
  `1.0000000000000016`、`1.0000000000000007`；coarse/fine differences為
  `6.217248937900877e-15`與 `8.881784197001252e-16`。
- [RESULT] `timestep_order_status=ROUND_OFF_LIMITED`、
  `timestep_observed_order=null`；null是 frozen failure semantics允許的誠實
  diagnostic，不是遺失或事後修補。
- [RESULT] 10-role artifact inventory共 `41,034,195 bytes`，manifest SHA-256為
  `97197f0a68a83e18bc12fc743ba7192d8b8e23626e0579c0c2ecc274de5350ff`；
  bundle仍明示 `REGRESSION_BUNDLE_VALID_ONLY / paper_data_ready=false`。
- [BLOCKER] 這只完成本 bounded milestone；experiment matrix、statistics與完整
  V1 articulated/dynamic/energy coverage仍未完成。
