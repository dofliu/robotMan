# Dynamic Run Trace V1 規格

最後更新：2026-08-29
狀態：BACKEND + FRONTEND IMPLEMENTED / BUILD PASS / BROWSER VISUAL PENDING / DEVELOPMENT ONLY

## 1. 目的

`Dynamic Run Trace V1` 是第二模式（Live／三機比較）與第一模式（工程分析）之間的資料橋接契約。它保存 MuJoCo forward simulation 實際走出的 realized trajectory，使第一模式可以比較 reference 與 realized simulation，而不是把 30 FPS WebSocket 畫面誤當完整工程資料。

本契約只代表 `SOFTWARE_ONLY / MUJOCO_REALIZED_SIMULATION`，不代表實體機器人量測或 physical validation。

## 2. 資料流

```text
Robot + Gait + Controller/Policy
              │
              ▼
       MuJoCo physics 500 Hz
              │
              ▼
      Dynamic Run Trace V1
        ├─ compressed NPZ raw arrays
        └─ JSON manifest + summary + SHA-256
              │
              ▼
     第一模式 Realized Trace Analysis
```

WebSocket frame 仍只負責視覺化；分析 API 必須由完成且 hash 可驗證的 trace artifact 讀取。

## 3. Capture contract

Live/Compare WebSocket 新增：

```json
{"type":"record_start","label":"walk-stop-01","max_duration_s":30.0}
```

```json
{"type":"record_stop"}
```

- `max_duration_s`：1–60 秒，預設 30 秒。
- 單一 LiveSession 同時只能有一個 active recording。
- Compare mode 以同一 `group_id` 同步啟動三個 controller traces。
- recording 期間禁止 controller 切換、runtime gait 修改、障礙物重建與 reset；stand/walk transition、push、assist、pause/step 仍可記錄。
- 到達 duration cap 時自動 finalize；不得無界累積記憶體。

## 4. Raw arrays

以 physics-step 500 Hz 記錄下列 fixed-shape arrays：

| Field | Unit / meaning |
|---|---|
| `time` | simulation seconds |
| `qpos`, `qvel`, `qacc` | MuJoCo generalized state |
| `ctrl`, `tau` | actuator command and realized actuator force |
| `q_ref`, `tracking_error` | common gait reference and realized joint error |
| `com`, `com_vel` | center of mass state |
| `pitch_deg`, `roll_deg` | trunk attitude |
| `grf_lr` | simulated left/right normal GRF |
| `cop_xy` | simulated contact CoP；missing 為 NaN |
| `contact_count` | active contact points |
| `saturation_pct` | actuator-group saturation |
| `positive_power_w`, `absolute_power_w` | joint mechanical power aggregates |
| `state_code` | STAND/WALK/FALLEN |

Manifest 保存 robot/gait/obstacles、controller、policy ID/evidence status、assist、group ID、run timestamps、field shapes/dtypes、summary 與 NPZ SHA-256。

## 5. Analysis API

- `GET /api/traces`：列出已完成 traces，不列 active/incomplete temporary files。
- `GET /api/traces/{run_id}?max_points=2000`：驗證 NPZ bytes/SHA-256 後回傳 manifest、summary 與 bounded decimated series。
- 不存在、path escape、hash mismatch、shape/count mismatch 一律 fail closed。

第一模式提供：

- `REFERENCE`：既有 prescribed trajectory analysis。
- `REALIZED_SIMULATION`：選擇已完成 Dynamic Run Trace。
- 第一版顯示 run identity、controller/policy、distance、fall、姿態、energy、tracking error、GRF、saturation 與時間趨勢。
- `REFERENCE_VS_REALIZED` overlay 待 reference identity 與 joint/time alignment contract 完成後再啟用，不以名稱相同直接對齊。

## 6. Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| TRACE-R01 | 每個 sample 來自 physics step，不由 30 FPS UI frame 回填 | PASS — 500 Hz recorder test |
| TRACE-R02 | max duration 有界；超限自動 finalize | PASS — 1 s / 500 samples boundary test |
| TRACE-R03 | manifest count/shape/dtype 與 NPZ 一致 | PASS — artifact validator test |
| TRACE-R04 | NPZ bytes 與 SHA-256 mismatch fail closed | PASS — tamper negative test |
| TRACE-R05 | recording 中 scenario/controller identity 不可漂移 | PASS — command contract test |
| TRACE-R06 | compare 三 traces 共用 group ID 且時間 skew 在 tolerance 內 | PASS — comparison integration test |
| TRACE-R07 | 第一模式可列出、選取並呈現 realized trace summary/series | PARTIAL — API + typecheck/build PASS；browser visual pending |
| TRACE-R08 | UI 固定標示 simulated realized output，不宣稱 physical measurement | PASS — source/document review |

## 7. 非本版範圍

- 實體 sensor/robot log ingestion。
- Immutable formal evidence bundle 與獨立 evaluator。
- Reference-vs-realized statistical ranking。
- HIL/bench/robot validation。
