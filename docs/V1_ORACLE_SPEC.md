# V1 Physics Oracle — 第一階段規格

最後更新：2026-08-30  
狀態：`V2 PARTIAL IMPLEMENTED / V1 NOT PASS`

## 1. 已實作 oracle

`v1_static_double_support_internal_v2` 執行 2 秒、500 Hz、assist OFF 的 static double-support reference case，最後 `(1.5, 2.0]` 共 250 個 samples 評估：

- finite qpos/qvel/qacc 與 solver outputs；
- MuJoCo forward–inverse joint-force residual；
- MuJoCo forward–inverse constraint-force residual；
- 逐 contact 讀取 6-D force/torque，轉換到 world frame；
- 以 contact point 的兩側 body translational/rotational Jacobian 重建 `qfrc_constraint`；
- 將 closure 分成 floating-base force、floating-base moment 與 joint torque；
- 每個 active contact 的 unilateral normal force；
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

## 2. V2 reference result

本次 frozen static reference case 通過 13/13 criteria：

- contact generalized-force 最大 component residual：`6.83e-16`（normalized）；
- base-force residual：`6.83e-16`（以 `Mg` normalization）；
- base-moment residual：`5.32e-17`（以 `Mg × 0.76 m` normalization）；
- joint-torque residual：`6.90e-17`（同 moment scale）；
- minimum active-contact normal force：`56.30 N`；
- forward/inverse residual、weight balance、staticity、posture與 bilateral contact 亦通過。

## 3. 證據邊界

V2 evaluator 已不依賴 UI summary：它自行把 MuJoCo 回報的 6-D contact wrench 經 Jacobian 聚合，並把 base force、base moment 與 joint torque 分開檢查。不過 wrench 與比較目標 `qfrc_constraint` 仍來自同一個 MuJoCo engine；這能驗證 frame/sign/Jacobian aggregation 與 instrumentation regression，但不是獨立 contact model validation。

因此 `V1-R02` 至 `V1-R05` 只能從 BLOCKED/NOT STARTED 提升為 PARTIAL，不能標為 PASS。V1 整體仍需 friction、CoP、dynamic/single-support、analytical reference、time-step convergence 與 energy checks。

## 4. 下一批 oracle

1. 在 frozen friction semantics 下重算 friction utilization 與 CoP/support polygon。
2. 從 raw bundle 建立 process-independent replay evaluator，不呼叫 UI/controller telemetry。
3. 新增 known pendulum、known payload、single support 與 time-step convergence cases。
4. 新增 power/energy balance 與 solver-iteration evidence。
5. 將任何 NaN、solver failure 或 constraint violation保留為 case FAIL，不修補輸出。
