# Dynamic Run Trace V1 實作回條

日期：2026-08-29
Evidence scope：SOFTWARE_ONLY / MUJOCO_REALIZED_SIMULATION / DEVELOPMENT
Project gate：V0 NOT PASS；V3 NOT PASS

## 完成項目

- `RunTraceRecorder`：以 MuJoCo physics step 500 Hz、float32 preallocation、1–60 s duration cap 記錄 realized states。
- Raw artifact：compressed NPZ；manifest：config/gait/controller/policy/assist、array contract、summary、bytes、SHA-256。
- Identity lock：recording 中拒絕 controller switch、runtime gait、obstacle rebuild 與 reset。
- Live WebSocket：`record_start`、`record_stop`、recording/frame readback、`trace_ready` receipt。
- Compare WebSocket：三 controller 共用 `group_id`，產生三筆 independent traces。
- REST：`GET /api/traces`、`GET /api/traces/{run_id}`；detail load 驗證 bytes/hash/shape/dtype/sample count。
- 第一模式：`Reference 估算`／`Dynamic Trace` source switch；顯示 identity、summary、attitude、GRF、joint realized/reference、torque、tracking error、saturation 與 power。

## Verification

| Check | Result |
|---|---|
| Trace-specific tests | 8 passed |
| Backend full regression | 95 passed；3 dependency deprecation warnings |
| Frontend typecheck + production build | PASS；existing >500 kB chunk warning remains |
| 1 s duration cap | PASS：500 samples then auto-finalize |
| Hash tamper | PASS：detail load fail closed |
| Compare grouping/time | PASS：shared group ID and identical time series |
| Browser visual smoke | PENDING：尚未於本回合完成互動式目視驗證 |

## Development sample

- Run ID：`run-20260829t051739-raibert-1efe305a`
- Label：`development-raibert-walk-sample`
- Controller：Raibert；assist OFF
- Duration/sample count：2.0 s / 1000 samples
- Artifact SHA-256：`c4c5bd8c1b13ef726d24676109a9533d6e5b8dffa1e125a522c647663dc68b2e`
- Observed simulation snapshot：final state WALK、distance 0.766878 m；此單一 development run 不支援 controller ranking 或 physical claim。

## Remaining work

- Reference-vs-realized overlay 尚需 reference identity、time/phase alignment 與 metric compatibility contract。
- Trace artifact 尚不是 immutable V0 evidence bundle，也沒有獨立 evaluator。
- 下一個 motion task 應先凍結 `stand → start → steady walk → stop` acceptance，再擴展 speed change、push recovery、turn、squat、step-over 與 run。
