# V1 Physics Oracle — 第一階段規格

最後更新：2026-08-31

狀態：`V4 RAW JACOBIAN REPLAY IMPLEMENTED / V1 NOT PASS`

## 0. V4 bounded milestone freeze與結果（2026-08-31）

本次只處理 `raw Jacobian serialization + process-independent stdlib-only replay`，不加入
single-support、payload、time-step convergence、energy 或 controller comparison。

Frozen acceptance criteria：

1. Primary raw schema 升為 `V1_STATIC_DOUBLE_SUPPORT_ORACLE_V4`；每個 contact
   保存 contact point 上 `body2 - body1` 的 world-frame translational 與
   rotational Jacobian，各為 `3 × nv`，且 contract 明示 convention。每個
   contact 另保存 `condim`、`exclude`、`efc_address`、derived `active`
   與 `adhesion_n`；本 frozen gate 要求 `condim == 3`、active metadata 與
   MuJoCo contact state 一致，且 non-adhesive precondition 為
   `adhesion_n == 0`。
2. Raw contact 不再以 per-contact `generalized_force` 作 replay input。獨立
   replay 必須只以 serialized contact frame、6-D wrench 與兩個 relative
   Jacobian 計算
   `Jp_rel^T F_world + Jr_rel^T tau_world`，再與 `qfrc_constraint` 比較。
3. Replay process 只可使用 Python standard library，不匯入 MuJoCo、
   `LiveSession` 或 controller；primary/replay 的八個 contact metrics 最大差異
   必須維持 `<= 1e-12`，既有 frozen physics thresholds 不得改動。
4. 全部 1000 steps 都必須通過 raw-Jacobian closure 與 absolute time-grid
   檢查，且每步 state/force/solver、resolved-model、contact 與
   foot-support fields必須符合 frozen V4 key set、vector shape 與 finite
   semantics；不可只檢查最後 250-step scientific window。缺少 Jacobian、
   row/column shape 或 `nv` 不符、`condim` drift、active metadata 不一致、
   NaN/Infinity、非標準 JSON 或 nonzero adhesion 一律 raise
   `ReplayValidationError`，不得產生 PASS receipt；有限值 tamper 造成
   residual 超門檻時保留為 `FAIL`，不得 repair 或放寬 threshold。
5. 10-role regression bundle 必須通過 safe relative path、bytes、SHA-256
   readback；結果仍只能是 `REGRESSION_BUNDLE_VALID_ONLY`，不能升格為
   `PAPER_DATA_READY`。Primary exception、NaN/±Infinity、replay `FAIL` 或
   process/schema error 都必須保留為 `FAILED` bundle、error/failure receipt
   與 stdout/stderr artifact，不得在 manifest 前遺失或補成 PASS。
   Builder 必須以 exact 16/14 criterion ID/operator/limit/unit/metric mapping
   重算 `passed`，並綁定 primary compiled-model XML SHA-256與 run 前/後
   Git SHA/dirty identity；中途改變時 manifest必須 `FAILED`。

Frozen claim boundary：

- [SOURCE] Jacobian、contact frame 與 contact wrench 仍全部來自同一 MuJoCo
  simulated plant。
- [RESULT] 本 milestone 最多證明 serialized raw quantities 可由另一個
  process 重建相同 generalized-force/contact summary。
- [BLOCKER] 這不是獨立 contact-physics validation，也不支持實體機器人、
  sim-to-real、安全或 controller superiority；V1 gate 仍需後續 analytical、
  dynamic、convergence、constraint 與 energy cases。

Milestone result：`PASS`。Frozen physics thresholds未修改；finite Jacobian
tamper保留為 criterion `FAIL`，缺欄、shape/`nv` mismatch、`condim`
drift、active metadata mismatch、NaN與 nonzero adhesion negative tests皆 fail
closed。Regression bundle仍只回報
`REGRESSION_BUNDLE_VALID_ONLY / paper_data_ready=false`；synthetic primary
exception、NaN、±Infinity與 replay error tests皆保留為 `FAILED` 10-role
bundle；forged complete PASS、缺少 primary criteria、錯誤 claim、overflow、
source drift、model/step field缺失與 inactive nonzero wrench皆 fail closed。

## 1. 已實作 oracle

`v1_static_double_support_internal_v4` 執行 2 秒、500 Hz、assist OFF 的 static double-support reference case，最後 `(1.5, 2.0]` 共 250 個 samples 評估：

- finite qpos/qvel/qacc 與 solver outputs；
- MuJoCo forward–inverse joint-force residual；
- MuJoCo forward–inverse constraint-force residual；
- 逐 contact 讀取 6-D force/torque，轉換到 world frame；
- 保存 contact point的 `body2 - body1` world-aligned translational/rotational Jacobians，各為 `3 × nv`，並重建 `qfrc_constraint`；
- 保存每個 contact的 `condim`、`exclude`、`efc_address`、derived
  `active` 與 `adhesion_n`；本 case要求 active-state receipt一致、
  `condim == 3` 且 adhesion exact zero；
- 將 closure 分成 floating-base force、floating-base moment 與 joint torque；
- 每個 active contact 的 unilateral normal force；
- 依 compiled `PYRAMIDAL` cone、`condim=3` 與逐 contact coefficient 重算 friction utilization；
- 由每隻腳的 aggregate force/moment 在 foot-local sole plane 重算 CoP 與 box support margin；
- total vertical GRF 與 compiled model weight 的相對誤差；
- linear/angular staticity、posture 與 bilateral contact duty。

Threshold 在執行前固定於 `backend/vv_oracles.py`。命令：

```powershell
python -X utf8 backend/run_v1_oracles.py
```

要保存每個 physics step 的 `q/qd/qdd`、control、`qfrc_inverse`、actuator/applied/passive/bias/constraint generalized force、contact frame、6-D wrench、relative Jacobian matrices、adhesion與 solver residual：

```powershell
python -X utf8 backend/run_v1_oracles.py --raw-output backend/run_traces/<unique-name>.json
```

Writer 使用 `exclusive create`；同名檔案存在時會直接失敗，不覆寫既有 evidence。大型 raw artifact 依 repository policy 保留在 Git 之外。

由獨立 process 讀取 raw JSON，不匯入 MuJoCo、`LiveSession` 或 controller：

```powershell
python -X utf8 backend/v1_replay.py backend/run_traces/<unique-name>.json
```

## 2. Frozen friction 與 CoP 定義

目前 compiled model 為 `PYRAMIDAL` cone、`condim=3`，因此單一 contact 的 utilization 固定為：

```text
u_friction = |f_t1| / (mu_1 f_n) + |f_t2| / (mu_2 f_n)
PASS when max(u_friction) <= 1 + 1e-9
```

不可改用 elliptic cone 的 L2 公式。若 active tangential load 存在但 normal force 接近零，utilization 以 fail value 處理。

本 case凍結為 non-adhesive contact。只有每個 contact皆保存
`adhesion_n == 0`時，才以 `wrench_local[0]`套用 unilateral與 friction gate；
缺失或非零 adhesion是 contract violation，不得以此解釋負 normal force或放寬
既有 tolerance。

MuJoCo 可在 `mjData.contact` 保留 inactive detected contacts。V4 raw trace
保留它們，但只有 `exclude == 0 && efc_address >= 0` 才標為
`active=true` 並納入 unilateral、friction 與 CoP metrics；inactive contact
必須是 zero wrench，metadata 矛盾時 replay fail closed。

每隻腳以 foot geom center 為 local origin、sole plane `z_s = -half_height`。由 aggregate local force `F` 與 moment `M` 計算：

```text
CoP_x = (z_s F_x - M_y) / F_z
CoP_y = (M_x + z_s F_y) / F_z
support_margin = min(half_length - |CoP_x|, half_width - |CoP_y|)
PASS when support_margin >= -1e-9 m and both feet have loaded CoP
```

## 3. V4 reference result

Clean-source implementation evidence 見
[V1 Raw-Jacobian V4 Implementation Receipt](V1_RAW_JACOBIAN_IMPLEMENTATION_RECEIPT_2026-08-31.md)。

Primary static oracle 通過 16/16 criteria：

- contact generalized-force 最大 component residual：`6.83e-16`（normalized）；
- base-force residual：`6.83e-16`（以 `Mg` normalization）；
- base-moment residual：`5.32e-17`（以 `Mg × 0.76 m` normalization）；
- joint-torque residual：`6.90e-17`（同 moment scale）；
- minimum active-contact normal force：`56.30 N`；
- maximum friction utilization：`0.0014199`；
- minimum foot-local CoP support margin：`0.045 m`；
- loaded foot count：`2`；
- forward/inverse residual、weight balance、staticity、posture與 bilateral contact 亦通過。

Stdlib-only process replay通過 14/14 criteria：1000-step count、500 Hz sample period、absolute time grid、250-step evaluation count、全 trace與 evaluation-window raw-Jacobian generalized-force closure、base force/moment、joint torque、unilateral force、friction、CoP、bilateral availability與 primary identity；對 primary八個 contact metrics的最大差異為 `0.0`。Redundant primary summary receipts只做 completeness/finite/shape檢查，不取代 replay對 raw frame/wrench/Jacobian/geometry的重算，因此有限值 tamper仍以 criterion `FAIL`保留。

## 4. 證據邊界

V4 primary evaluator不依賴 UI summary；raw replay也不匯入 MuJoCo/controller，會從 serialized relative Jacobians、contact frame與6-D wrench重建每個 contact的 generalized force，再從 friction、foot pose與 support geometry重算 friction與CoP。Raw contact已不保存或讀取 per-contact `generalized_force` receipt。

[RESULT] 本次 evidence class 是
`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`。
[INFERENCE] 這能檢出 serialization、contact-frame sign與 arithmetic drift。
[BLOCKER] Jacobian與contact wrench仍由同一 MuJoCo engine產生；官方也說明
dynamic contact forward model省略 contact Jacobian的 `Jdot*v`項，而該項會在
forward/inverse comparison中抵消。因此 `V1-R02` 至 `V1-R07`仍只能標為
PARTIAL，不能把 static identity寫成 dynamic contact、independent plant或
physical-foot validation。

## 5. 下一批 oracle

1. 新增 single support、known payload 與 time-step convergence cases。
2. 新增 known pendulum與 dynamic contact cases。
3. 新增 power/energy balance 與 solver-iteration evidence。
4. 將任何 NaN、solver failure 或 constraint violation保留為 case FAIL，不修補輸出。

## 6. MuJoCo 定義來源

- [MuJoCo Computation — Contact and friction cones](https://mujoco.readthedocs.io/en/stable/computation/index.html#contact)
- [MuJoCo API — `mj_jac`](https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html#mj-jac)
- [MuJoCo Simulation — contact frame and `mj_contactForce`](https://mujoco.readthedocs.io/en/stable/programming/simulation.html#contacts)
- [MuJoCo 3.11 adhesion semantics](https://mujoco.readthedocs.io/en/stable/changelog.html#version-3-11-0-july-27-2026)
- [Joseph and Dutta, contact-force validation in MuJoCo, 2026](https://doi.org/10.1177/09544062251407012)
- [Crotti et al., physical-bench SoftFoot model validation, 2025](https://doi.org/10.1109/ACCESS.2025.3608584)
