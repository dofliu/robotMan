# 人形機器人控制與訓練方法研究執行計畫

最後更新：2026-09-03

本次 V1 evidence 範圍：`SIM_ONLY_MUJOCO` / `NOT_PHYSICALLY_VALIDATED`

## 1. 研究目標與證據邊界

本專案的研究目標是建立一個 verification-aware humanoid control testbed，讓 model-based、learning-based 與 hybrid controller 能在相同 plant、task、scenario、seed 與 evaluator 下比較。

研究證據拆成兩條獨立鏈：

1. `MODEL_VALIDITY`：動態方程、contact、actuator、sensor 與 numerical behavior 是否通過獨立驗證。
2. `METHOD_EFFECTIVENESS`：controller／training method 是否在凍結條件下有可重現、具統計不確定性的差異。

Policy 在同一 simulator 與 reward 中表現良好，不等於 model validation，也不等於 sim-to-real。V4 外部證據完成前，所有方法比較皆限縮為 simulation study。

## 2. 第一階段研究問題

- `RQ1 — Observation / observability`：加入 heading 與 lateral path error 後，能否降低 lateral drift，而不犧牲 no-fall、前進與停止能力？
- `RQ2 — Training strategy`：scratch PPO、warm-start PPO、curriculum PPO 與 path-conditioned PPO 的 task success、sample efficiency 與 failure mode 有何差異？
- `RQ3 — Control architecture`：verified WBC、pure PPO 與 WBC + Residual PPO 在 constraint compliance、robustness 與 energy 上有何差異？
- `RQ4 — Generalization`：friction、payload、latency、sensor noise、push phase 與 terrain 改變時，各方法的 performance degradation 是否不同？

`RQ1` 先執行；`RQ3` 必須等待 V1 contact/constraint gate 與 frozen WBC baseline。

## 3. 執行順序與 gate

| 階段 | 工作 | Exit gate | 狀態 |
|---|---|---|---|
| P0 | curriculum-v2 48-D Live adapter、registry identity、500 Hz task trace | observation/action contract tests；未修改 11 項 criteria | DONE / task FAIL retained |
| P0B | v3–v6 observation、terminal、phase 與 500 Hz load iteration | DEV + unchanged Live gates；失敗與 evaluator defects 保留 | DONE / no deployable PASS |
| P1 | V1 plant/contact/numerical oracle | residual、contact、friction、CoP、convergence、energy 全部可獨立重算 | IN PROGRESS / static replay與 passive single-support/payload/4–2–1 ms fixture PASS；articulated dynamic、pendulum、energy/full solver studies仍缺，gate not pass |
| P2 | QP/WBC baseline | constraint-feasible、failure-retaining baseline bundle | BLOCKED BY P1 |
| P3 | Experiment orchestrator | controller × training seed × eval seed × scenario 完整 manifest | VALIDATOR IMPLEMENTED / RUNNER + ACTUAL MATRIX MISSING：strict matrix spec/index、bundle identity與 missing/duplicate/unexpected/unindexed/status retention covered |
| P4 | Study A formal benchmark | protocol frozen、paired statistics、CI、failures/censoring retained | BLOCKED BY P1–P3 |
| P5 | Motion primitives / imitation | raise hand、single-leg raise、squat、turn 等各有獨立 task contract | AFTER STUDY A |
| P6 | SIL/HIL/bench/robot validation | 只在實際完成的外部 evidence 層級建立 bounded claim | FUTURE |

### P1 bounded result：raw Jacobian replay V4

- [SOURCE] MuJoCo [`mj_jac`](https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html#mj-jac)
  提供 world-aligned `3 × nv` translational/rotational Jacobians；官方
  [contact computation](https://mujoco.readthedocs.io/en/stable/computation/index.html#contact)
  使用 `body2 - body1` relative spatial Jacobian與 contact-frame wrench。
- [RESULT] `v1_static_double_support_internal_v4` 逐 contact保存兩個
  relative Jacobians與 `adhesion_n == 0`，stdlib-only replay不讀 MuJoCo、
  controller或 per-contact generalized-force receipt，仍與 primary八個 metrics
  完全一致。
- [INFERENCE] 這能檢出 serialization、frame/sign與 arithmetic drift，但不能
  驗證 MuJoCo contact model的 physical fidelity。
- [BLOCKER] Dynamic contact、known pendulum、energy、完整 solver/finite-difference
  convergence與外部 force/bench evidence仍未完成；P1/V1保持未通過。

### P1 bounded result：analytical fixture V1

- [SOURCE] MuJoCo continuous dynamics採 `M vdot + c = tau + J^T f`；integration
  timestep與 `solver_fwdinv` residual是不同 diagnostics。NASA-STD-7009B亦要求
  分別保留 discretization、iteration與 finite-precision evidence。
- [RESULT] Passive free-body fixture在 exact single support、centered 5 kg simulated
  payload及 4/2/1 ms grid共 4/4 cases PASS；另一 stdlib-only process由 raw
  frame/wrench/Jacobian與 exact model package重算後亦 PASS。Payload mass error為
  `0 kg`，GRF increment relative error為 `1.303748139009358e-15`。
- [RESULT] Normalized mean-GRF QoI為 `1.0000000000000078`、
  `1.0000000000000016`、`1.0000000000000007`；fine-grid difference
  `8.881784197001252e-16`未超過 coarse difference `6.217248937900877e-15`。
  Successive differences低於 `1e-10`，故 observed order依 frozen semantics為
  `null / ROUND_OFF_LIMITED`，未補值。
- [INFERENCE] 此 fixture可檢查單支撐靜力、中心質量增量、serialized contact
  arithmetic與選定 QoI的 grid stability；不能代表 articulated humanoid dynamics、
  controller performance或 physical payload capacity。
- [BLOCKER] Clean bundle只能是 `REGRESSION_BUNDLE_VALID_ONLY`；analytical fixture
  之後的 matrix completeness software contract已完成，但 actual Study A matrix、statistics
  與 formal authorization仍不存在。

### P3 bounded result：matrix completeness V1

- [SOURCE] Patterson et al.（JMLR 2024）建議 paired algorithm comparison、interval
  reporting與 agent/environment RNG分離；Agarwal et al.（NeurIPS 2021）要求在少量
  runs情境保留 uncertainty與 run distributions。
- [RESULT] `EXPERIMENT_MATRIX_SPEC_V1`與 run index以 spec hash綁定 explicit cells；
  validator逐 run重驗 `PAPER_RUN_MANIFEST_V1` artifact path/bytes/SHA-256，並 exact
  比對 source、protocol/environment/model/controller/config、seed與scenario identity。
- [RESULT] Seed schedule digest由 sorted expected cells重算；scenario numeric
  canonicalization避免 `0`/`0.0`/`-0.0`與 boolean/number equality繞過，dedicated root
  採 bounded no-follow scan。
- [RESULT] Missing、duplicate、unexpected、unindexed、tamper與 identity drift均
  fail closed；FAILED/CANCELLED分開保留。CANCELLED可維持 inventory complete，但
  `statistics_input_ready=false`。
- [RESULT] Clean-source synthetic receipt（Git `b8aea995eca0f3a3eff36ff04137ea3dd163f017`）
  驗證 3/3 identity-valid cells，並保留 `COMPLETED=1`、`FAILED=1`、`CANCELLED=1`；
  receipt SHA-256為 `8ebe7aa2509135143371774147dc85cc35fd5072c046522d1aabf90a74eb4691`。
- [INFERENCE] 這可降低 supplied matrix root內的漏報與 cherry-pick風險；不能證明
  explicit cells已涵蓋所有科學上必要 strata、sample size充分或 controller較優。
- [BLOCKER] `PAPER_RUN_MANIFEST_V1`尚無 native `scenario_id/replicate_id`；V1以
  matrix labels加 exact fingerprint cross-check，不宣稱 self-binding。外部 preregistration、
  immutable storage、actual matrix與 paired statistics仍缺。

## 4. P0 結果與 P0B 設計

### curriculum-v2 Live 結果

Frozen run：`run-20260830t051225-rl_task_v2-a04424f3`

- PASS：trace integrity、assist disabled、no fall、initial posture、steady speed、steady progress、stop speed、final posture、final state。
- FAIL：lateral drift `2.092011 m > 0.30 m`。
- FAIL：saturation duty `44.088889% > 30%`。
- heading 在 START 已偏離約 `-32 deg`，STEADY 最大約 `60 deg`。

這個結果顯示 v2 的 48-D observation 缺少 world-frame heading error 與 lateral path error。P0B 因此不是放寬門檻，而是建立新的 50-D observation contract：

```text
legacy gait state 47-D
  + normalized forward-speed command 1-D
  + normalized lateral path error 1-D
  + normalized yaw error 1-D
  = 50-D
```

v3 由 v2 做 fail-closed input expansion；新增輸入權重從零開始，其他 tensor 必須完全一致。Reward 另加入 lateral position、heading、lateral velocity、yaw rate 與 actuator saturation penalty。

### v3–v6 結果摘要

- v3 50-D 在 4M 後把 30 個 DEV seeds 的 lateral drift 全數壓入門檻，但新增兩次接近 STOP 的跌倒。
- v4 terminal-stability fine-tune 恢復 30/30 no-fall，但 seed 18028 的 final stop speed 仍失敗。
- v5 新增 signed phase trend（START `+1`、STOP `-1`）。選定的 122,880-step checkpoint 修復 seed 18028，並在 unchanged Live task 通過 10/11 criteria；唯一失敗為 saturation duty `38.422222%`。
- 檢查後發現原 training evaluator 只在 50 Hz control step 末端取樣 saturation，正式 task 則以 500 Hz physics trace 計算。修正後 v5 DEV mean/worst saturation 為 `37.571852% / 39.2%`，因此先前 saturation PASS 已撤銷。
- v6 保留 51-D observation，加入 500 Hz substep saturation reward；122,880-step DEV run 未降低 saturation，且新增一次末段跌倒。此負結果不進入 registry。

下一個 learning study 不再只堆疊 reward。v7 應 preregister `reward-only`、`joint-specific action envelope`、`action low-pass/rate limit` 與後續 `WBC residual` 的 interface ablation。DEV 使用 18000–18029；19000–19029 已因 evaluator defect audit 而退役。新的 formal holdout 預先凍結為 20000–20029，只能在選定單一候選後執行一次。

## 5. Study A 的方法組與公平比較

正式 Study A 暫定比較：

1. `WBC_BASELINE_V1`：P1 通過後凍結。
2. `PPO_SCRATCH_V1`：保留已知 backward-motion failure。
3. `PPO_CURRICULUM_V2`：保留 Live lateral/saturation failure。
4. `PPO_PHASE_OBSERVABLE_V5`：Live 10/11、saturation FAIL。
5. `PPO_SUBSTEP_SATURATION_V6`：reward-only negative control。
6. `WBC_RESIDUAL_PPO_V1`：P2 後實作。

Track 與 Raibert 保留為 engineering/teaching baselines；在 plant/contact gate 通過且 controller contract 凍結前，不拿來做正式 ranking。

共同條件：

- 相同 robot model、actuator limits、initialization、assist OFF 與 termination。
- 每個 learning method 使用多個獨立 training seeds；evaluation seeds 不能代替 training seeds。
- `DEV/TUNE` 與 `HOLDOUT` 分離；HOLDOUT 執行後不依結果修改 reward 或 controller。
- 正式 sample size 由 pilot variance 與 power analysis 決定，不以單一成功 seed 取代。
- evaluator 只讀 raw realized trace，不讀 training return。

## 6. Scenario 與 metrics

Scenario matrix 至少包含：

- nominal stand/start/walk/stop；
- friction、payload/inertia、actuator strength、latency；
- IMU/encoder noise、dropout；
- push phase、point、direction、impulse；
- terrain height/slope/compliance；
- controller/checkpoint/training seed/evaluation seed。

Primary outcomes 在 protocol freeze 時只選少數主指標，例如 task success rate、fall rate 與 steady-path tracking。Secondary outcomes 保存：stop error、lateral drift、yaw error、torque saturation、joint/contact violations、positive/absolute work、action smoothness、inference latency、sample efficiency 與 generalization gap。

## 7. Evidence bundle

每一個可引用結果需包含：

- immutable model/controller/checkpoint identity；
- source、environment、package、seed 與 scenario manifest；
- raw 500 Hz trace 與 hash；
- raw contact frame、6-D wrench與 relative translational/rotational Jacobians；
- independent evaluator version 與 output；
- failure/null/censored episodes；
- statistics code/output、effect size 與 confidence interval；
- frozen experiment matrix spec/index、completeness receipt與每個 status的分母歸屬；
- claim boundary：simulation、SIL、HIL、bench 或 robot。

Git 只保存 source、contract、small receipts 與 selected inference artifact。大量 raw traces、checkpoints 與 training logs 使用獨立 versioned experiment storage，不直接取消 `.gitignore` 批次提交。
