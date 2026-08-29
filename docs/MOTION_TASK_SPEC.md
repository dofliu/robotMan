# Motion Task V1：stand → start → steady walk → stop

最後更新：2026-08-29

## 1. 目的與證據邊界

`stand_start_walk_stop_v1` 是第一個可重複執行、可由 Dynamic Run Trace 量測的正式動作任務。它用相同初始狀態、相同 gait、相同 phase timing 與相同 acceptance criteria 比較 controller；結果仍屬 `SOFTWARE_ONLY_MUJOCO_REALIZED_SIMULATION`，不是實機驗證，也不構成 V3 controller ranking。

## 2. 固定任務契約

任務啟動會重設該 session、清除障礙物與外力、關閉外加 balance/startup assist，並套用固定 gait。這些動作是任務初始化的一部分，會寫入 trace manifest。

| 項目 | 固定值 |
|---|---:|
| Task ID | `stand_start_walk_stop_v1` |
| Physics trace | 500 Hz |
| 總長 | 9.0 s |
| Gait mode | walk |
| Target speed | 0.7 m/s |
| Step length | 0.35 m |
| Duty factor | 0.62 |
| Foot clearance | 0.07 m |
| External assist | OFF |

| Phase | 相對時間 | 內部事件 |
|---|---:|---|
| `INITIAL_STAND` | 0.0–1.0 s | 維持 stand |
| `START` | 1.0–2.5 s | 1.0 s 切換 walk |
| `STEADY_WALK` | 2.5–6.5 s | 維持 walk |
| `STOP` | 6.5–8.0 s | 6.5 s 切換 stand |
| `FINAL_STAND` | 8.0–9.0 s | 維持 stand |

任務進行中鎖定會改變測試身份或施加干擾的指令；僅允許 pause、simulation speed、single-step 與 task cancel。

## 3. Acceptance criteria

門檻在執行前固定，不能看完結果再放寬。每項 criterion 都保存 measured value、operator、limit、unit 與 PASS/FAIL。

| ID | 成功條件 |
|---|---|
| `TRACE_INTEGRITY` | trace 正常完成並通過 artifact hash/shape/dtype 驗證 |
| `ASSIST_DISABLED` | 任務全程外加 assist 為 OFF |
| `NO_FALL` | 不得出現 `FALLEN` sample |
| `INITIAL_STAND_POSTURE` | initial stand 的 max(|pitch|, |roll|) ≤ 15° |
| `STEADY_SPEED` | steady phase 平均 forward CoM speed 在 0.35–1.05 m/s |
| `STEADY_PROGRESS` | steady phase forward progress ≥ 1.40 m |
| `STOP_SPEED` | 最後 0.5 s 平均 |forward CoM speed| ≤ 0.15 m/s |
| `FINAL_STAND_POSTURE` | 最後 0.5 s 的 max(|pitch|, |roll|) ≤ 15° |
| `FINAL_STATE` | 最後 sample 為 `STAND` |
| `LATERAL_DRIFT` | |final base y − initial base y| ≤ 0.30 m |
| `SATURATION_DUTY` | 任一 actuator group ≥ 95% saturation 的 sample 比例 ≤ 30% |

Overall status 只有三種：全部 criteria 通過為 `PASS`；任一 criterion 失敗為 `FAIL`；人為取消為 `CANCELLED`。跌倒仍繼續保留 trace，不自動扶正或改寫為成功。

## 4. Live、Compare 與 Analysis

- Live：針對目前選定 controller 執行一次完整任務。
- Compare：以共用 `group_id` 同步啟動 Track、Raibert、RL 三個獨立 plants；每台各自產生 trace 與判定。
- Analysis：顯示任務 overall status、phase contract 與逐項 criterion，並保留原始姿態、速度、GRF、torque、tracking 與 saturation 圖。

## 5. 後續基本動作擴充

Motion Task registry 以 task ID、phase events、initialization contract 與 evaluator 分離。後續可新增：

- `raise_left_hand_v1`：站立、抬左手、保持、放下；量測 shoulder/elbow tracking、軀幹擾動與 foot contact。
- `single_leg_raise_v1`：站立、重心轉移、單腳抬起、保持、落腳；量測 foot clearance、support contact、姿態與是否跌倒。
- `squat_v1`、`turn_in_place_v1`、`sit_to_stand_v1`。

手部動作可沿用目前 shoulder/elbow joints；抬腳則必須先定義支撐腳、重心轉移與接觸條件，不能只把 leg joint 播成動畫後宣稱平衡成功。
