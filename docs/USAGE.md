# 使用說明

本系統適合教學、software regression、relative design screening 與 hypothesis generation。操作前先閱讀 [MODEL_CARD](MODEL_CARD.md)；若要形成正式比較結果，必須使用 [EXPERIMENT_PROTOCOL](EXPERIMENT_PROTOCOL.md)。

## 1. 安裝與啟動

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend/requirements-dev.txt -r backend/requirements-rl.txt

Set-Location frontend
npm ci
npm run build
Set-Location ..
python -X utf8 backend/main.py
~~~

開啟 http://127.0.0.1:8710。

`requirements-rl.txt` 提供現有 RL inference 所需的 dependency ranges，但尚未鎖定完整 training environment。analysis `/api/simulate` 會回傳 partial runtime provenance，但尚無 environment lock。重現 PPO training 前，仍須記錄 Python、MuJoCo、NumPy、Gymnasium、Stable-Baselines3、PyTorch、CUDA 與 checkpoint SHA-256；資訊不完整時只能做 exploratory run。

Repository clone、tracked/excluded artifacts 與發布驗證流程見 [REPOSITORY_GUIDE](REPOSITORY_GUIDE.md)。

## 2. 先選擇 evidence intent

### Exploratory / teaching

可直接操作 UI，觀察參數改變與 simulation behavior。結果標記：

- [SOURCE] 輸入設定、程式版本與引用資料；
- [SOURCE] 本次 simulation output，標記為 `DEVELOPMENT_SNAPSHOT`；
- [INFERENCE] 對 output 的 bounded interpretation；
- [HYPOTHESIS] 待後續測試的想法；
- [BLOCKER] 尚未完成的 verification/validation。

只有 frozen method、raw artifacts 與 acceptance receipt 完整時，才可依
[CONVENTIONS](CONVENTIONS.md) 將輸出升格為正式 `[RESULT]`。

### Formal software experiment

開始前必須：

1. 建立 experiment ID 與 scenario ID。
2. 凍結 resolved config、model/checkpoint/environment hashes。
3. 固定 seeds、assist、disturbance、termination 與 metric definitions。
4. 指定 oracle、gate 與 raw artifact paths。
5. 將 DEVELOPMENT 與 FORMAL_EVALUATION 完全分開。

任一項缺失即保持 BLOCKED。

## 3. Analysis mode

適合：

- prescribed motion 下的相對 torque/energy trend；
- 幾何、質量或 demo actuator parameter sensitivity；
- IK、CoM、ZMP/CoP 概念教學；
- 產生 V1 verification cases。

結果解讀：

- torque 是 analytical GRF/contact assumptions 下的 inverse-dynamics screening estimate；
- motor utilization 使用 catalog parameter，不等同實際 drive 可達能力；
- ZMP margin 是 scheduled trajectory consistency indicator，並非獨立穩定性證明；
- warning 是 rule-based screen，不是硬體 pass/fail certificate；
- run mode 含 flight phase 時，ZMP 不作為 validation criterion。
- frontend 的 stale-result/evidence badges 用來提醒 config/result identity 與 evidence scope；badge 顯示正常不等於 V0/V1 gate PASS。

不要用 analysis mode 單獨決定採購、連續工作熱容量、跌倒安全或實體 payload。

## 4. Live mode

Live mode 使用 MuJoCo forward dynamics 與 simulated contact，可用來觀察：

- controller response、contact transition 與 simulated fall；
- external push、obstacle 與 assist intervention；
- torque saturation 與 controller state；
- nominal regression behavior。

每次比較前確認：

- controller label 與實際載入 controller/checkpoint 一致；
- assist 與 startup assist 是否開啟；
- push direction、application point、force、duration、gait phase 一致；
- contact/friction/model configuration 相同；
- energy sampling 與 termination definition 相同。

介面顯示的 contact force/CoP 是 simulator output，不是 force plate measurement。

## 5. 常用教學流程

### A. Actuator parameter sensitivity

1. 在 analysis mode 固定 gait 與 mass。
2. 每次只改一個 demo actuator parameter。
3. 比較 torque/speed/energy curves。
4. 將結論寫成「在此 model assumptions 下的相對變化」。

此流程不提供 validated motor selection。若使用實際型號，先依 [HARDWARE_DATA_PROVENANCE](HARDWARE_DATA_PROVENANCE.md) 登錄來源。

### B. Stability concept demonstration

1. 改變 speed、step length、foot size 或 pelvis sway。
2. 觀察 scheduled support polygon 與 ZMP/CoM indicator。
3. 到 live mode 觀察同一 nominal config 的 simulated outcome。
4. 把兩者差異記為 model discrepancy，不把一致視為 physical validation。

### C. Controller behavior demonstration

1. 固定同一 resolved plant config。
2. 明確關閉或固定所有 assist。
3. 固定 initialization 與 disturbance。
4. 比較 raw traces，而非只看單一 summary。

正式 ranking 仍須 V3。

### D. Arm teaching demo

M7A 完成後可用於 end-effector IK、workspace 與 payload parameter visualization。M7B/V1/V2 未通過前，不解讀為 dynamic feasibility。

## 6. Nominal comparison script

~~~powershell
python backend/compare.py
~~~

此命令會更新 comparison_report.md。現行結果是 deterministic nominal software snapshot，不是 formal benchmark。它沒有完整 raw bundle、multi-seed UQ、confidence interval 或 physical validation。

正式執行前應先完成：

- physics-step energy integration；
- identical intervention policy；
- gait-phase-stratified push cases；
- raw per-episode artifacts；
- code/config/model/checkpoint/environment hashes；
- preregistered statistics。

## 7. RL training/evaluation

~~~powershell
python backend/rl/train_ppo.py --profile walk_0p7_fixed_v1 --run-id walk-0p7-seed1700-run01
python backend/rl/eval_policy.py backend/rl/ppo_walk_final.zip --profile walk_0p7_fixed_v1 --episodes 20 --seed-base 10000
~~~

這些命令是 development pipeline。正式 RL study 還需：

- 全域 training seed 與每個 environment seed；
- training config、source tree、dependency lock 與 checkpoint hash；
- independent evaluation scenarios；
- multiple training/evaluation seeds；
- failed/censored episodes；
- confidence interval 與 predeclared stopping rule；
- WBC baseline 與相同 plant/intervention policy。

失敗後修改 reward、network、plant 或 metric，必須建立新的 protocol version；不得混入原 formal result。

## 8. Dynamic Run Trace：從第二模式回到第一模式分析

1. 進入「即時互動」或「三機同步比較」。
2. 選定 controller、assist 與動作條件後，按「開始記錄 Trace」；單次最長 60 秒，UI 預設 30 秒。
3. 執行 stand/walk、push 等測試，再按「停止並保存 Trace」。
4. 回到「分析模式」，選擇「Dynamic Trace」。
5. 選擇 run，查看 realized distance、fall、attitude、GRF、joint reference/error、torque、saturation、power/work。

Recording active 時不得更換 controller、runtime gait、obstacles 或 reset，避免同一 artifact 的 identity 漂移。三機比較會產生共用 `group_id` 的三筆獨立 traces。

## 9. 正式動作任務：stand → start → steady walk → stop

1. 在「即時互動」選定 controller，按「執行正式任務」；或在「三機同步比較」按「三機執行正式任務」。
2. 系統會重設機器人、清除障礙物與外力、套用 0.7 m/s 固定 gait，並將 assist 關閉。
3. 依序觀察 `INITIAL_STAND → START → STEADY_WALK → STOP → FINAL_STAND`；可調整 simulation speed、pause 或 single-step，但不可在任務中加入 push 或改 controller/gait。
4. 9 秒任務完成後，畫面顯示 PASS/FAIL；切到「分析模式 → Dynamic Trace」可查看 11 項 criterion 的 measured value 與 limit。

第一次三機 development baseline 的三組結果皆為 FAIL，表示現有 controller 尚不能在固定 protocol 下完整完成「行走後停止並重新站穩」。這不是 V3 ranking，也不可解讀為實機結果。完整契約見 [MOTION_TASK_SPEC](MOTION_TASK_SPEC.md)。

更新後 `stand` command 會顯示 `STOPPING`，並在 1.5 秒內逐步降低 locomotion command；不會瞬間凍結 simulated state。可用以下 runner 重複執行同一三機任務並產生 trace：

```powershell
python backend/run_motion_task.py
python backend/run_motion_task.py --controller rl
```

## 10. RL Training Lab

1. 切換至「RL 訓練」查看 versioned profiles、seed、planned timesteps 與目前 status。
2. 頁面只顯示 inventory，不會在瀏覽器內即時更新 weights；Live/Compare 仍執行 registry 中的 frozen policy。
3. `stand_start_walk_stop_0p7_v1` 保留為 failed-speed run；v2 與 v5 已有各自的 registry identity 與 Live adapter。
4. v2 在 Live 失敗於 lateral drift/saturation；v5 通過其他 10 項、失敗於 saturation duty。v6 reward-only fine-tune也未通過 DEV gate。
5. training evaluator 現以 500 Hz substeps 計算 saturation；舊 50 Hz saturation PASS 已撤銷。

```powershell
python backend/rl/train_ppo.py --profile stand_start_walk_stop_0p7_curriculum_v2 --run-id start-stop-curriculum-seed3700-run02
```

Dynamic Trace 顯示的是 `SOFTWARE_ONLY_MUJOCO_REALIZED_SIMULATION`，不是實體機器人量測；Reference 與 realized 的正式 overlay 尚未完成 identity/alignment contract。

## 11. Software checks

~~~powershell
pip install -r backend/requirements-dev.txt
python -X utf8 -m pytest -p no:cacheprovider backend/test_pipeline.py backend/test_p0_contract.py backend/test_live_contract.py
python -X utf8 -B backend/test_pipeline.py
~~~

第一個命令執行 REST/WebSocket schema、actual metric、provenance 與既有 pipeline tests；第二個保留可直接閱讀的 legacy diagnostics。這些 checks 不代表 V1 已通過。執行後須保留 command、environment、stdout/stderr、exit code 與 code hash。新增 physics 功能時，優先加入 residual、conservation、constraint 與 convergence oracle。

## 12. 結果記錄最低要求

Exploratory note 至少包含：

- date/time、operator、purpose；
- resolved robot/gait/obstacle config；
- mode 與 controller/checkpoint；
- assist、disturbance 與 termination；
- environment versions；
- observed result、limitations、blockers。

Formal run 使用 [EXPERIMENT_PROTOCOL](EXPERIMENT_PROTOCOL.md) 的完整 manifest。/api/simulate meta.provenance 可作初始 identity evidence，但仍須補 environment lock、immutable raw bundle、artifact inventory 與 validator receipt。

## 13. 常見誤解

| 誤解 | 正確解讀 |
|---|---|
| UI 顯示 100% stable | scheduled indicator 在目前 tolerance 下未觸發，不是實體穩定率 |
| 0% fall | 特定 deterministic nominal runs 未觸發 fall condition，不是 population estimate |
| peak torque 未超限 | 只通過簡化 constant limit screen，未驗證 torque-speed/thermal/drive |
| live contact 是真實接觸 | 是 MuJoCo simulated contact under assumed parameters |
| 換成 datasheet 數字就完成 validation | 仍缺 CAD/BOM、drive integration、bench 與 subsystem evidence |
| software test PASS | 只支持對應 software requirement，不支持 physical validation |

## 14. 疑難排解

- RL 選項回到 Raibert：視為 controller identity failure；正式 run 必須停止，不得以 RL label 繼續。
- PowerShell 中文或勾號輸出失敗：使用 Python UTF-8 mode；仍須保留非零 exit code。
- torque spike：不要直接刪除或改 percentile；先檢查 trajectory continuity、time step、finite difference 與 contact transition。
- simulation 與文件數字不同：以 frozen bundle 為準，舊 summary 標記 stale，不手動覆寫成一致。
