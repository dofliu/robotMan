# 系統架構與證據邊界

本文件說明目前程式實際做了什麼，以及不同 pipeline 的輸出可支持到哪一層。Intended use 與 prohibited claims 由 [MODEL_CARD](MODEL_CARD.md) 定義；驗證 gate 由 [VV_PLAN](VV_PLAN.md) 定義。

## 1. 系統定位

目前系統是 SIM-only reduced-order humanoid prototype，包含：

- frontend：參數輸入、3D visualization、telemetry 與 live interaction；
- backend analysis pipeline：prescribed kinematics、analytical GRF/contact schedule、inverse dynamics；
- backend live pipeline：MuJoCo forward dynamics、simulated contact、torque command；
- controller/RL modules：trajectory tracking、Raibert、PPO policy；
- documentation/evidence layer：model card、V&V plan、experiment protocol 與 hardware provenance。

Visualization correctness、numerical verification 與 physical validation 是三個不同 claim，不能互相替代。

## 2. Analysis pipeline

資料流：

~~~text
RobotConfig + GaitParams + Obstacles
    → prescribed footsteps / pelvis / arm trajectories
    → analytical IK and qpos time series
    → finite-difference qvel / qacc
    → scheduled contact weights and analytical total GRF
    → MuJoCo inverse dynamics
    → subtract point-force Jacobian contribution
    → joint torque / motor-side screening / energy estimate
    → cart-table ZMP and support-polygon indicators
~~~

### 2.1 關鍵邊界

1. analysis model 關閉 collision/contact solve；腳底力不是 MuJoCo contact solver 的輸出。
2. GRF 由 whole-body CoM acceleration 與 prescribed contact weights 解析分配。
3. 現行 joint torque 由 generalized inverse force 扣除 analytical GRF 後取 actuated DOF；floating-base force/moment residual 尚未成為 fail-closed gate。
4. CoP 採 prescribed heel-to-toe path，尚未由 pressure/contact distribution 求得。
5. 矢狀 CoM trajectory 由 scheduled ZMP reference 反解，因此再以同一 scheduled support polygon 計算 ZMP margin，只能當 trajectory consistency indicator，不能當獨立 stability validation。
6. motor-side torque、power 與 warning 依 representative parameters 與簡化 efficiency model計算。

因此 analysis output 的正確稱呼是 **design screening estimate under prescribed motion and contact assumptions**。

## 3. Live pipeline

資料流：

~~~text
RobotConfig + controller + commands
    → MJCF dynamic plant
    → torque command with configured saturation
    → MuJoCo forward dynamics and simulated contact
    → contact/state/controller telemetry
    → WebSocket frame stream
~~~

### 3.1 關鍵邊界

- 物理步長目前為 2 ms；這是 numerical setting，不是實體控制器驗證。
- contact、friction、geometry、inertia 與 actuator limits 均來自模型假設。
- robot self-collision 目前停用。
- startup assist、balance assist 與 external push 都是 external interventions，必須在 experiment manifest 中顯式記錄。
- controller output 受 constant peak torque limit 截斷；尚無完整 torque-speed/current/voltage/thermal envelope。
- sensor/estimator 主要使用 simulator state 或 idealized signal，不能代表實體 latency、noise、bias 或 dropout。

因此「live」表示 interactive forward simulation，不表示 real-time HIL 或 physical robot test。

## 4. Analysis 與 Live 不可直接互換

| 項目 | Analysis | Live |
|---|---|---|
| Motion | prescribed | dynamics-emergent |
| Contact | analytical schedule/GRF | MuJoCo simulated contact |
| Primary use | relative screening | controller/plant behavior exploration |
| Energy | simplified motor/electrical estimate | existing benchmark uses sampled mechanical work |
| Stability | scheduled ZMP/support indicator | simulated fall/contact outcome |
| Current evidence level | software prototype | SIL-like prototype |

兩個 mode 必須分別定義 metric 與 oracle。現行 analysis 公式由 [METRIC_DEFINITIONS](METRIC_DEFINITIONS.md) 管理；跨 mode 比較 CoT、torque 或 stability 前，需先完成 definition reconciliation 與 V1/V3 gates。

## 5. Reduced-order robot model

目前模型有 floating base、簡化 trunk/head、雙腿與雙臂，共 12 個 actuated joints。各 segment 由簡化 primitive geometry 與 lumped mass 表示；actuator mass 與 reflected rotor inertia 被加入模型。

尚未完成的 plant fidelity 包含：

- documented joint hard/soft limits；
- complete wrist/hand/gripper model；
- self-collision 與 cable/routing constraints；
- measured inertia tensor/CAD correlation；
- foot sole compliance、pressure distribution 與 contact parameter identification；
- actuator drive、battery、thermal、backlash/compliance；
- sensor and state-estimator dynamics。

這些項目依 V1/V2/V4 逐級處理。

## 6. Controller 與 RL boundary

trajectory tracking、Raibert 與 PPO policy 共用同一 live plant interface，但不代表現有 comparison 已公平：

- assist policy、initialization、gait phase、disturbance、termination 與 energy integration 必須由 frozen protocol 統一；
- controller 載入失敗必須 fail closed，不能靜默 fallback 後仍使用原 label；
- PPO checkpoint 必須由 checkpoint SHA-256、training config、environment versions、seed schedule 與 evaluation manifest 唯一識別；
- WBC baseline 必須在正式 RL paper comparison 前建立，且 contact constraints 需通過 V1。

詳細規則見 [EXPERIMENT_PROTOCOL](EXPERIMENT_PROTOCOL.md)。

## 7. API surface

現有主要介面：

- GET /api/defaults：回傳 default robot/gait 與 demo hardware catalog。
- POST /api/simulate：執行 analysis pipeline，回傳 trajectory、telemetry、sensor、stability indicators 與 partial runtime provenance。現行 provenance 只涵蓋此 analysis response，包含 config/model/code/result hashes、run/scenario ID、engine、metric set、evidence scope 與 created_at。
- WebSocket `/ws/live`：建立 live session，以 typed fail-closed contract 接受 mode、controller、push、obstacle、speed、pause、step、gait、assist 與 reset commands；validation/controller-load failure 回傳 structured error，frame 回讀 authoritative controller/intervention state。

Analysis API response 已具有 partial runtime provenance，可用於 stale-result/evidence-state 顯示與初步 identity readback；live WebSocket 已有 typed command errors 與 controller/intervention state readback，但仍無完整 run identity。Frontend 的 request freshness 目前也未獨立驗證 server config hash。兩種 mode 都不是正式 immutable evidence bundle，尚缺 environment lock、完整 raw artifact inventory、checksums、validator receipt 與 failure-preserving storage。正式 run 仍須依 [EXPERIMENT_PROTOCOL](EXPERIMENT_PROTOCOL.md) 補齊。

## 8. Evidence architecture

正式 evidence bundle 最低結構：

~~~text
experiment/
  manifest.json
  resolved_config.json
  model.mjcf
  environment.json
  raw/
    state_trace
    control_trace
    contact_trace
    solver_trace
    event_trace
  metrics/
    episode_metrics
    aggregate_statistics
  checksums.sha256
  gate_result.json
~~~

目前 /api/simulate metadata 是此架構的 partial precursor。summary、frontend evidence badge、圖表或 Markdown report 只能引用正式 bundle，不能取代 raw artifacts。

## 9. Verification / Validation 分層

- Unit/software checks：function、schema、units、serialization。
- Numerical verification：conservation/residual、constraint feasibility、time-step/solver convergence。
- SIL：frozen simulated plant 與 independent oracle。
- HIL：real controller/drive interface + simulated plant。
- Bench validation：actuator、joint、leg/arm subsystem measurement。
- Integrated robot validation：另立 safety/instrumentation protocol。

每層 evidence 僅支持該層 bounded claim。

## 10. 主要模組契約

| 模組 | 職責 | 不得隱含的 claim |
|---|---|---|
| config_schema.py | API data structure/defaults | defaults 已有 physical provenance |
| hardware_db.py | D0 demo catalog | datasheet/bench validated hardware |
| model_builder.py | RobotConfig → MJCF | CAD-correlated plant |
| gait.py | prescribed trajectory/IK | dynamically feasible gait |
| simulator.py | analysis orchestration | independent contact/stability validation |
| live_sim.py | forward simulation session | HIL/real robot behavior |
| controller modules | simulated control policies | controller safety/performance in hardware |
| frontend | visualization/interaction | rendered signal is verified physical evidence |
