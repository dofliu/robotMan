# V1 Physics Oracle — 第一階段規格

最後更新：2026-08-30  
狀態：`V3 PARTIAL IMPLEMENTED / V1 NOT PASS`

## 1. 已實作 oracle

`v1_static_double_support_internal_v3` 執行 2 秒、500 Hz、assist OFF 的 static double-support reference case，最後 `(1.5, 2.0]` 共 250 個 samples 評估：

- finite qpos/qvel/qacc 與 solver outputs；
- MuJoCo forward–inverse joint-force residual；
- MuJoCo forward–inverse constraint-force residual；
- 逐 contact 讀取 6-D force/torque，轉換到 world frame；
- 以 contact point 的兩側 body translational/rotational Jacobian 重建 `qfrc_constraint`；
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

要保存每個 physics step 的 `q/qd/qdd`、control、`qfrc_inverse`、actuator/applied/passive/bias/constraint generalized force、contact frame、6-D wrench、Jacobian reconstruction 與 solver residual：

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

每隻腳以 foot geom center 為 local origin、sole plane `z_s = -half_height`。由 aggregate local force `F` 與 moment `M` 計算：

```text
CoP_x = (z_s F_x - M_y) / F_z
CoP_y = (M_x + z_s F_y) / F_z
support_margin = min(half_length - |CoP_x|, half_width - |CoP_y|)
PASS when support_margin >= -1e-9 m and both feet have loaded CoP
```

## 3. V3 reference result

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

Process-independent raw replay 通過 11/11 criteria：1000-step count、500 Hz sample period、contact generalized-force aggregation、base force/moment、joint torque、unilateral force、friction、CoP與 bilateral availability；對 primary metrics 的最大差異為 `0.0`。

## 4. 證據邊界

V3 primary evaluator 不依賴 UI summary；raw replay 也不匯入 MuJoCo/controller，會從 serialized contact frame、wrench、friction、foot pose與 support geometry重算 friction 與 CoP。不過每個 contact 的 `generalized_force` 仍是 primary evaluator receipt，因 raw bundle 尚未保存完整 Jacobian matrices；contact wrench 本身也仍由 MuJoCo 產生。

因此 `V1-R02` 至 `V1-R07` 只能標為 PARTIAL，不能標為 PASS。這套結果能證明 static instrumentation 與 raw receipt 可重算，但不能證明 contact model 對真實腳底接觸正確。

## 5. 下一批 oracle

1. 將 relative translational/rotational Jacobian matrices納入 raw bundle，讓 replay 不再依賴 primary `generalized_force` receipt。
2. 新增 known pendulum、known payload、single support 與 time-step convergence cases。
3. 新增 power/energy balance 與 solver-iteration evidence。
4. 將任何 NaN、solver failure 或 constraint violation保留為 case FAIL，不修補輸出。

## 6. MuJoCo 定義來源

- [Computation — Contact and friction cones](https://mujoco.readthedocs.io/en/latest/computation/)
- [API types — mjContact frame and friction order](https://mujoco.readthedocs.io/en/latest/APIreference/APItypes.html)
