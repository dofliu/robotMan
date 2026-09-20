# Motion Task V1 實作回條

日期：2026-08-29

## 完成範圍

- Versioned registry：`stand_start_walk_stop_v1`。
- 固定初始化：reset、clear obstacles/push、0.7 m/s gait、assist OFF。
- Simulation-time phase runner：`INITIAL_STAND → START → STEADY_WALK → STOP → FINAL_STAND`。
- Live：啟動、進度、取消、結果 readback。
- Compare：三個獨立 plants 使用同一 task/group ID 同步執行。
- Dynamic Run Trace：manifest 保存 contract、phase events、逐項 evaluation。
- Analysis：顯示 overall PASS/FAIL/CANCELLED、phase 與 11 項 measured criteria。
- Fail-closed：任務期間拒絕 push、gait、controller、assist、obstacle、reset 與手動 recording mutation。

## Software verification

- Motion Task focused tests：6 passed，包含 frozen contract、synthetic PASS、Live execution、cancelled partial trace、Compare synchronization 與 WebSocket receipt。
- Backend full regression：101 passed；保留 3 個既有 deprecation warnings。
- Frontend production build：PASS；保留 Vite bundle-size warning，不影響本次功能正確性。

## 第一組 development baseline

Group ID：`task-20260829t054055-d9d2fc80`。每組 4500 samples、500 Hz、9.0 s、stop reason `task_complete`。這是本機 SIM-only development run，不是 V3 benchmark 或 physical validation。

| Controller | Result | First fall | Failed criteria | Run ID |
|---|---|---:|---|---|
| Track | FAIL | 2.952 s | NO_FALL、STEADY_SPEED、STEADY_PROGRESS、STOP_SPEED、FINAL_STAND_POSTURE、FINAL_STATE | `run-20260829t054056-track-09e6ff36` |
| Raibert | FAIL | 3.282 s | NO_FALL、STEADY_PROGRESS、STOP_SPEED、FINAL_STAND_POSTURE、FINAL_STATE | `run-20260829t054056-raibert-11cf75d6` |
| RL | FAIL | 7.212 s | NO_FALL、STOP_SPEED、FINAL_STAND_POSTURE、FINAL_STATE、LATERAL_DRIFT、SATURATION_DUTY | `run-20260829t054057-rl-b9ec9d07` |

Artifact SHA-256：

- Track：`sha256:879452aebe0cd1d8e4612d4112763c1d9886104dbfc4bd269472c1be3cc3d886`
- Raibert：`sha256:eafb3840da54bd74b474832e6508a084bfdcb520a0ce30a764d123456f4643cf`
- RL：`sha256:4528051199d9c286942371a7accf1f016dda1d0b3c3857923a2d41d4f5f352f7`

上述 raw runtime traces 保留於建立它們的本機 workspace，依 repository artifact policy 不提交 GitHub；本文件只保存 bounded development summary，不能替代 immutable evidence bundle。

## 判讀與下一步

這組結果確認「能進入 walk」與「能完成完整動作任務」是不同能力。RL 在 steady walk 後才於 stop phase 跌倒，明確指出下一個工程工作應是 controlled deceleration、步態相位收斂與 final stand transition，而不是放寬成功門檻。Track/Raibert 則還需要先改善起步與穩態可靠度。
