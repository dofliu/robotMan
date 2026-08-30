# Motion Primitive 與 Controlled Stop 規格

最後更新：2026-08-30

## 1. 目的與範圍

本規格定義 Motion Task 如何呼叫 controller 能力，以及第一個正式 controller transition：`WALK → STOPPING → STAND`。目前證據範圍仍為 `SOFTWARE_ONLY_MUJOCO_REALIZED_SIMULATION`；這是 simulated plant 的控制功能，不代表實體人形機器人已可安全執行相同動作。

## 2. Action dispatcher

Motion Task runner 不直接寫死 session method，而是將 phase event 正規化後交給 action dispatcher。第一階段支援：

| Primitive | 必要欄位 | 行為 |
|---|---|---|
| `set_mode` | `mode: stand | walk` | 設定高階動作目標；`walk → stand` 必須由 controller 執行 controlled transition |
| `hold` | 無 | 保持前一個高階命令，不重設 controller state 或 gait phase |

`stand_start_walk_stop_v1` 的 frozen phase、gait 與 acceptance criteria 不變；既有 `mode` 欄位在 runner 內正規化為 `set_mode`。後續 task 才新增 bounded primitives，例如 `joint_pose`、`weight_shift`、`foot_target`、`turn_rate`，且每個新增 primitive 都必須先有輸入 schema、abort condition、trace 欄位與 evaluator。

## 3. Controlled stop state machine

```text
WALK -- stand command --> STOPPING -- duration reached --> STAND
  ^                         |
  +------- walk command ----+

WALK / STOPPING -- fall detector --> FALLEN
```

- `stand` command 不可瞬間把行走 reference 換成站姿。
- STOPPING 預設為 1.5 s，使用 smoothstep 將 locomotion command scale 從 1 降到 0。
- Track 與 Raibert controller 的目標速度、gait reference 與姿勢 reference 依 scale 收斂。
- RL controller 保留 frozen policy 推論，但其 action target 依 scale 混合至站姿；此為 hybrid stop transition，不是重新訓練後的 RL stop policy。
- STOPPING 期間持續執行 physics、contact 與 gait clock，不能凍結畫面或直接改寫 simulated state。
- transition 完成才進入 `STAND`；跌倒時維持 `FALLEN`，不得自動扶正。

Dynamic Run Trace 新增 `STOPPING` state code，讓 transition 可在 raw artifact 中辨識。歷史 trace 的既有 state code 不變。

## 4. 不變的驗收方式

Controlled stop 的成功與否仍由 `stand_start_walk_stop_v1` 的原 11 項 criteria 判定，尤其是：

- `NO_FALL`；
- 最後 0.5 s 平均 `|forward CoM speed| ≤ 0.15 m/s`；
- `FINAL_STAND_POSTURE ≤ 15°`；
- final state 必須為 `STAND`；
- saturation duty 不得超過原門檻。

不得因第一輪結果失敗而修改 phase timing 或門檻。Track/Raibert 若在 STOP 前已跌倒，仍保留為 controller 起步或 steady-walk 缺陷，不能以 controlled stop 宣稱修復。

## 5. 下一批基本動作的進入條件

依序新增，且每個動作用新的 versioned task ID：

1. `raise_left_hand_v1`：`stand → raise → hold → lower → stand`；
2. `single_leg_raise_v1`：`stand → weight shift → lift → hold → land → stand`；
3. `squat_v1`；
4. `turn_in_place_v1`；
5. `sit_to_stand_v1`。

舉手需要 joint tracking、trunk disturbance、雙腳 contact 與 final posture；抬腳還需要 support-foot contact、CoM/support polygon、foot clearance 與 landing impact。只有視覺姿勢、沒有 simulated dynamics 與 acceptance evaluator，不列為正式 Motion Task。
