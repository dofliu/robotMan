# V1 Physics Oracle — 第一階段規格

最後更新：2026-08-30  
狀態：`PARTIAL IMPLEMENTED / V1 NOT PASS`

## 1. 已實作 oracle

`v1_static_double_support_internal_v1` 執行 2 秒、500 Hz、assist OFF 的 static double-support reference case，最後 0.5 秒評估：

- finite qpos/qvel/qacc 與 solver outputs；
- MuJoCo forward–inverse joint-force residual；
- MuJoCo forward–inverse constraint-force residual；
- total vertical GRF 與 compiled model weight 的相對誤差；
- linear/angular staticity、posture 與 bilateral contact duty。

Threshold 在執行前固定於 `backend/vv_oracles.py`。命令：

```powershell
python -X utf8 backend/run_v1_oracles.py
```

## 2. 證據邊界

MuJoCo `mj_inverse` 與 `solver_fwdinv` 是同一 engine 內的 forward/inverse consistency check。它可揭露 numerical/solver regression，但不是獨立 contact model validation，也未把 base force與 moment 六個分量分開重算。

因此即使本 oracle PASS，`V1-R02` 到 `V1-R04` 仍不可標為 PASS；V1 整體狀態保持 blocked/partial。

## 3. 下一批 oracle

1. 將 contact point、full 6-D contact wrench、qfrc terms 與 solver settings 加入 immutable raw bundle。
2. 由獨立 evaluator 重算 floating-base force/moment closure、joint equation residual、unilateral force、friction與 CoP。
3. 新增 known pendulum、known payload、single support 與 time-step convergence cases。
4. 將任何 NaN、solver failure 或 constraint violation保留為 case FAIL，不修補輸出。
