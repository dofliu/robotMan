# Controlled Stop、Motion Primitive 與 Training Lab 實作回條

日期：2026-08-30  
Evidence scope：`SOFTWARE_ONLY_MUJOCO_REALIZED_SIMULATION` / `SOFTWARE_TRAINING_PIPELINE_ONLY`

## 1. 已實作

- Controller state machine：`WALK → STOPPING → STAND`，1.5 s smooth command scale；跌倒仍進入 `FALLEN`。
- Track/Raibert：速度、gait clock、reference pose 依 stop scale 收斂。
- Legacy RL：policy target 平滑收斂，並加入 contact-aware ankle/hip braking layer；明示為 hybrid stop，不是假稱 policy 已學會 stop。
- Dynamic Run Trace：新增 `STOPPING = 3` state code；舊有 state codes 不變。
- Motion Task action dispatcher：既有 V1 phase 的 `mode` 正規化為 `set_mode`，並支援 `hold`；後續動作可在新 task ID 擴充 primitive。
- 可重跑 runner：`backend/run_motion_task.py` 可執行單一或三 controller frozen task。
- Training profile：`stand_start_walk_stop_0p7_v1`，48-D command-conditioned observation、相同 9 s phase schedule、50M planned timesteps、seed base 2700。
- UI：新增 `STOPPING` 狀態與「RL 訓練」頁；`/api/training/profiles` 為 read-only inventory，不會在瀏覽器中啟動 training。

## 2. 不變門檻重跑

Final group：`task-20260830t031712-0bec0cb8`。三組皆為 4500 samples、500 Hz、9.0 s、assist OFF；原 11 項 criteria 未修改。

| Controller | Overall | First fall | Stop speed | 主要判讀 |
|---|---|---:|---:|---|
| Track | FAIL | 2.952 s | 1.218 m/s | STOP 前已跌倒；起步/steady-walk blocker 未改善 |
| Raibert | FAIL | 3.282 s | 0.689 m/s | STOP 前已跌倒；steady progress 仍不足 |
| RL legacy | FAIL | 8.822 s | 0.85194 m/s | 較舊 baseline 7.212 s / 1.31 m/s 改善，但仍跌倒且未站穩 |

RL 的 lateral drift 為 1.322896 m、saturation duty 為 54.066667%，兩者均比舊 baseline 惡化。這是 mixed result：controlled transition 延後跌倒並降低速度，但沒有完成 motion task，因此保留 FAIL，不調整門檻。

Run IDs：

- `run-20260830t031712-track-a82b22b8`
- `run-20260830t031712-raibert-32dfa234`
- `run-20260830t031713-rl-c3222c75`

Runtime traces 位於 ignored `backend/run_traces/`，不作為 Git tracked formal evidence bundle。

## 3. Training outcome

同日後續正式 training 保留兩條結果：

- v1 從零開始 run 在 8M unseen-seed gate 顯示 steady speed -0.199 m/s、progress -0.830 m，early-stop 並標記 failed speed gate。
- `stand_start_walk_stop_0p7_curriculum_v2` 以 registry-verified gait warm start、47→48-D input expansion、active-balance command envelope 與 forward/reverse reward fine-tune。1,999,992-step candidate 在另一批 30 seeds 為 30/30 完成、0 fall、steady speed 0.543235 m/s、progress 2.166154 m、final stand speed 0.096662 m/s。

候選 artifact 尚未加入 policy registry。結果只屬 matching training environment；現有 Live/Compare 仍執行 `walk_0p7_legacy`。完整 receipt 見 `START_STOP_POLICY_TRAINING_RECEIPT_2026-08-30.md`。

## 4. Verification

- Backend：108 passed；只有既有 FastAPI `ORJSONResponse` deprecation warnings。
- Frontend：TypeScript + Vite production build passed；保留既有 bundle-size warning。
- Start/stop profile：256-step pipeline smoke passed。
- Actual same-contract Compare：三機 trace 完成並保存負結果。
- Local HTTP smoke：index/production asset/API 均為 HTTP 200；API 回傳 4 profiles，bundle 含 `RL Training Lab` 與 `受控停止中`。自動化 in-app browser control 無法建立連線，因此 browser visual receipt 維持 pending，未宣稱已通過。

## 5. 下一個工程工作

1. 建立候選 policy 的獨立 48-D Live controller adapter 與 registry schema record，不替換 legacy ID。
2. 跑未修改的 500 Hz Motion Task 11 項 criteria，保留 PASS/FAIL trace 與 manifest。
3. Track/Raibert 另開起步與 steady-walk 修正，不用 RL candidate 結果掩蓋其較早失敗。
4. 之後才新增 `raise_left_hand_v1` 與 `single_leg_raise_v1`。

本回條不是 physical validation、controller ranking 或 sim-to-real 證據。
