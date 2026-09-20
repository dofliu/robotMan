# V0 Implementation Receipt — 2026-08-26

Status：`DEVELOPMENT_RECEIPT / V0_PARTIAL_IMPLEMENTED_NOT_PASS`
Evidence scope：`SOFTWARE_ONLY / SIM_ONLY_REDUCED_ORDER`
Physical validation：`NOT_PHYSICALLY_VALIDATED`

本 receipt 記錄第一批 V0 hardening 的 source 與可重跑 checks。它不是 immutable
formal evidence bundle；workspace 沒有 `.git` identity，亦未封存 raw artifacts、
environment lock、stdout/stderr checksum 或 reviewer signature。

## 1. Implemented scope

- External simulation input：REST `SimRequest`、Live init/command 採 strict、bounded、
  finite、unknown-field-rejecting schema，並加入 meaningful numerical minima、gait
  numerical-resolution、Robot×Gait pelvis clearance、push direction 與 cumulative obstacle
  resource gates。
- Analysis metrics：`ANALYSIS_METRICS_V1` 使用 sampled trajectory/elapsed time；CoT
  zero-distance 回 `null`；peak 與 P99.5 分開；ZMP 無有效 sample 時 fail closed 為
  `UNAVAILABLE`，並回傳 coverage、P1 與 true minimum。
- Runtime identity：analysis response 回傳 config/model/code/content hashes、run/scenario
  ID、metric version、engine 與 evidence/calibration scope。
- Live consistency：structured errors、controller load failure no-mutation、assist/intervention
  readback、runtime gait synchronization、RL unsupported gait fail-closed、reset 恢復 init
  obstacles。
- Frontend evidence state：last-success frozen snapshot、request sequence race guard、STALE
  overlay、server-reported hash 標示、Live authoritative state/error/intervention display。
- Claim boundary：built-in actuator data 維持 D0 representative；legacy comparison report
  改標 SIM-only development snapshot。

明確未做：constrained contact solve、floating-base residual gate、WBC、RL retraining、
environment lock、immutable bundle、independent metric evaluator、HIL/bench/robot tests。

## 2. Acceptance audit

| Requirement | Source evidence | Runtime/test evidence | Database evidence | Outcome |
|---|---|---|---|---|
| V0-R02 run identity | `backend/simulator.py` provenance/content-hash contract | independent content-hash recomputation、config mutation、tamper regression | N/A：專案無 database | PARTIAL；缺 Git/environment/checkpoint identity 與 immutable bundle |
| V0-R05 fail-closed input | `backend/config_schema.py`、`backend/main.py`、`backend/live_sim.py` | REST 422、WebSocket error envelope、NaN/Inf/bool/numeric-string/unknown/pathological gait regressions | N/A | PARTIAL PASS for current REST/Live simulation surfaces；非 formal evidence validator |
| V0-R06 metric semantics | `backend/simulator.py`、`METRIC_DEFINITIONS.md` | sampled motion/energy/CoT、true peak/P99.5、short-window fallback、ZMP unavailable/coverage/P1/min regressions | N/A | PARTIAL；缺 independent raw evaluator 與 frozen gate receipt |
| V0-R07 result-input identity | `frontend/src/App.tsx`、`LiveView.tsx`、`SummaryBar.tsx` | request race、frozen reference、STALE、Live payload/state/error 與 ZMP UI behavior smoke | N/A | PARTIAL；client 未獨立驗證 server-reported config hash |
| Claim boundary | README、MODEL_CARD、comparison report、UI badges | bounded-language/link/YAML checks | N/A | SOFTWARE wording aligned；physical validation remains absent |
| V1 plant verification | VV_PLAN and ROADMAP only | none | N/A | NOT STARTED / BLOCKED BY V0 |

## 3. Development verification snapshot

Observed environment（未鎖定）：

- Python 3.12.5；FastAPI 0.139.2；Pydantic 2.13.4；HTTPX 0.28.1；
  pytest 8.3.0；NumPy 2.2.6；MuJoCo 3.12.0。
- Node.js 22.17.0；npm 10.9.2。
- Git checkout identity：absent；runtime `git_sha=null` 是預期的 honest output。

重跑 commands：

~~~powershell
python -X utf8 -m pytest -p no:cacheprovider backend/test_pipeline.py backend/test_p0_contract.py backend/test_live_contract.py -q
cd frontend
npm run check
~~~

本輪完成後的 observed results：

- Backend：68 tests passed；all-min config 已通過 REST/Live model construction 與 JSON-safe
  check，dynamic actuator ranges 保持 strictly positive；warnings 為既存
  `pytest-asyncio` fixture-loop-scope 與 FastAPI `ORJSONResponse` deprecation。
- Frontend：TypeScript typecheck 與 production build passed；bundle 約 704 kB，仍有
  Vite `>500 kB` chunk warning。
- Frontend behavior smoke：Live gait/obstacle init、authoritative speed/pause、assist
  intervention、structured error、out-of-order response、frozen torque reference、ZMP
  unavailable/coverage/P1/min branches passed；尚未封存為 immutable browser receipt。
- Markdown local links 與 `STATUS.yaml` parse checks passed；正式 bundle validator 尚未建立。

## 4. Next authorized work

V0 下一批應先建立 versioned manifest schema、resolved environment inventory、raw artifact
inventory/checksums、immutable development bundle writer 與 fail-closed readback validator。
只有 V0 gate 完成後，才開始 V1 的 floating-base/contact constraint residual baseline；
M7B、WBC 與正式 RL benchmark 仍保持 blocked。
