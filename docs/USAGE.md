# 使用說明

本系統適合教學、software regression、relative design screening 與 hypothesis generation。操作前先閱讀 [MODEL_CARD](MODEL_CARD.md)；若要形成正式比較結果，必須使用 [EXPERIMENT_PROTOCOL](EXPERIMENT_PROTOCOL.md)。

## 1. 安裝與啟動

安裝與啟動指令見 [README 快速啟動](../README.md)，那是唯一出處，本手冊不重複。Repository clone、tracked/excluded artifacts 與發布驗證流程見 [REPOSITORY_GUIDE](REPOSITORY_GUIDE.md)。

關於**環境身分**，只有一點必須在動手前知道：`requirements-rl.txt` 只給 dependency ranges，`requirements.txt` 只宣告 `>=` floors，兩者都**不是** frozen training environment。版本號相同不保證數值相同——本專案實測過同一環境下 stdlib 逐項求和與 `numpy` 求和會在末位不同。

自 2026-09-08 起，環境身分由 [`ENVIRONMENT-LOCK-V1`](ENVIRONMENT_LOCK_SPEC.md) 實測並可重驗；自 2026-09-13 起，[`RUN-MANIFEST-LOCK-BINDING-V1`](RUN_MANIFEST_LOCK_BINDING_SPEC.md) 以 SHA-256 把 lock record 綁進 run manifest。要產生**可引用**的 run，用 §7 的 wrapper；直接呼叫 driver 產生的 run 會被 gate 判為 `RUN_LOCK_UNBOUND`，那是一個具名結果，不是通過。

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

### 7.1 產生可引用的 run：綁定 environment lock

上面兩個命令是 **development pipeline**，它們不寫綁定記錄，所以產出的 run 在分析期會被判為 `RUN_LOCK_UNBOUND`。要產生可引用的 run，改用 wrapper——它先量測環境、再原封不動地以 subprocess 執行 driver、最後把 lock record 與綁定記錄寫進 run 目錄：

```powershell
python backend/rl/bind_run_lock.py `
    --producer backend/rl/train_ppo.py `
    --run-dir backend/rl/artifacts/<run_id> `
    --manifest run_manifest.json `
    --require-full-lock `
    -- python rl/train_ppo.py --profile <profile> --run-id <run_id>
```

- `--producer` 必須是凍結 protocol 內列出的 producer 路徑；wrapper 從該 protocol 讀出 `binding_mode` 與 `sidecar_reason`，不接受自由文字。
- `--lock-record <path>`（可選）把環境**釘死**：本機若與該 record 不一致，run 拒絕開始。
- `--require-full-lock` 是受凍結 protocol 管轄之 run 的規則：未達 `MEASURED_ENVIRONMENT_LOCK` + `FULL_LOCK` 就拒絕開始。smoke／本機開發可省略，此時仍會據實記錄實測的 class 與 completeness。
- Evaluation 用同一個 wrapper，只是把 `--producer` 換成 `backend/rl/eval_policy.py`、`--manifest` 換成該次 evaluation 的輸出檔名。

成功時會印出 `RUN_LOCK_BOUND` 與三個 digest（lock 檔案位元組、`locked` 子樹、被綁 manifest）。這三者是**三個不同的量**，不可互相替換。

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
4. v2 在 Live 失敗於 lateral drift/saturation；v5 通過其他 10 項、失敗於 saturation duty `38.422222%` > `30%`。v6 reward-only fine-tune 未降低 saturation；v7 三臂 pilot 與其後的 5-replicate seed-variance 執行皆**未選出 candidate**。
5. training evaluator 現以 500 Hz substeps 計算 saturation；舊 50 Hz saturation PASS 已撤銷。
6. [BLOCKER] v7 line 的 warm start provenance 不可重建，所有由它衍生的結果永久帶 `CONDITIONAL_ON_FIXED_WARM_START`。新訓練線必須把 checkpoint lineage 進版控，並用 §7.1 的 wrapper 執行。

```powershell
python backend/rl/train_ppo.py --profile stand_start_walk_stop_0p7_curriculum_v2 --run-id start-stop-curriculum-seed3700-run02
```

Dynamic Trace 顯示的是 `SOFTWARE_ONLY_MUJOCO_REALIZED_SIMULATION`，不是實體機器人量測；Reference 與 realized 的正式 overlay 尚未完成 identity/alignment contract。

## 11. Software checks

完整測試套件的指令見 [README](../README.md)。本節只列它**不包含**的兩個窄範圍診斷：

~~~powershell
python -X utf8 -m pytest -p no:cacheprovider backend/test_pipeline.py backend/test_p0_contract.py backend/test_live_contract.py
python -X utf8 -B backend/test_pipeline.py
~~~

第一個只跑 REST/WebSocket schema、actual metric 與 provenance；第二個保留可直接閱讀的 legacy diagnostics。兩者都不代表 V1 已通過。執行後須保留 command、environment、stdout/stderr、exit code 與 code hash。新增 physics 功能時，優先加入 residual、conservation、constraint 與 convergence oracle。

[RESULT] 完整套件目前為 **1 failed / 816 passed**，那一個失敗是在具名 environment lock 下**記錄為量測結果、未放寬**的 reduction-order 差異。看到它不必修；理由見 [PROJECT_STATUS §9](PROJECT_STATUS.md)。

## 12. 結果記錄最低要求

Exploratory note 至少包含：

- date/time、operator、purpose；
- resolved robot/gait/obstacle config；
- mode 與 controller/checkpoint；
- assist、disturbance 與 termination；
- environment versions；
- observed result、limitations、blockers。

Formal run 使用 [EXPERIMENT_PROTOCOL](EXPERIMENT_PROTOCOL.md) 的完整 manifest，並須在 run 目錄留下 `environment_lock.json` 與 `run_lock_binding.json`（由 §7.1 的 wrapper 產生）。`/api/simulate` 的 `meta.provenance` 可作初始 identity evidence，但它**明示不在** lock 綁定範圍內（見 [RUN_MANIFEST_LOCK_BINDING_SPEC §3.4](RUN_MANIFEST_LOCK_BINDING_SPEC.md)），且仍須補 immutable raw bundle、artifact inventory 與 validator receipt。

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
