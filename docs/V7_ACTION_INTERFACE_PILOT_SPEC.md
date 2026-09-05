# V7 Action-Interface DEVELOPMENT Pilot Specification

日期：2026-09-06

狀態：`FROZEN BEFORE IMPLEMENTATION / INTERNAL DEVELOPMENT ONLY`

Protocol：`PILOT-V7-ACTION-INTERFACE-DEV-V1`
Machine-readable contract：
[`backend/rl/v7_action_interface_pilot_protocol.json`](../backend/rl/v7_action_interface_pilot_protocol.json)

證據範圍：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`

## 1. 本次唯一 milestone

建立並執行一個三臂 action-interface DEVELOPMENT pilot，保存完整 training/evaluation
terminal records、artifact identity、conditional episode variance與另一個 stdlib-only
raw-episode replay。Milestone 是否完成只由 evidence completeness 決定；policy 是否通過
performance gate不是完成條件，負結果必須原樣保留。

本 spec 在任何 v7 source implementation 前凍結。2026-08-30 歷史 receipt 將 reference
寫為 v5 interface；2026-09-05 canonical plan改寫為 reward-only。此版本明示採後者：
三臂共同使用 v6 的 500 Hz saturation reward，只改 action interface，舊 receipt 保留不改。

## 2. 三個 frozen arms

所有 arms 從同一個 v5 checkpoint warm start，使用相同 PPO hyperparameters、training
seed與 evaluation seeds。

1. `V7A_REWARD_ONLY`：direct normalized action，沿用原 12-D target range。
2. `V7B_REDUCED_JOINT_ENVELOPE`：現行介面本來就有 per-joint scale；此 arm
   相對 V7A 只把 knee、ankle、shoulder、elbow 的 target-offset range對稱縮小
   25%，hip roll/pitch不變，不宣稱首次引入 joint-specific control。
3. `V7C_FILTERED_ACTION`：相對 V7A 只加入 `alpha=0.25` 的一階 low-pass candidate，
   再套用每個 20 ms control step `±0.10` normalized-action hard rate limit。

Joint order固定為：

```text
hip_roll_l, hip_pitch_l, knee_l, ankle_l,
hip_roll_r, hip_pitch_r, knee_r, ankle_r,
shoulder_l, elbow_l, shoulder_r, elbow_r
```

V7A/V7C action scale為：

```text
[0.5, 0.8, 0.9, 0.6, 0.5, 0.8, 0.9, 0.6, 0.6, 0.6, 0.6, 0.6] rad
```

V7B action scale為：

```text
[0.5, 0.8, 0.675, 0.45, 0.5, 0.8, 0.675, 0.45, 0.45, 0.45, 0.45, 0.45] rad
```

V7C operator order固定為：raw policy action clip至 `[-1,1]` → low-pass candidate →
rate limit → per-joint scale →既有 command envelope → PD torque與既有 torque clamp。
Filter在 reset設為全零，現有 observation最後 12 維改存上一個 applied action，使這個
一階介面的內部 state對 policy可見。MuJoCo actuator filter保持關閉，不做 double filtering。

[HYPOTHESIS] 上述 25%、`alpha=0.25`與 `0.10/20 ms`只是 pre-pilot simulation
design，並非 datasheet、identified actuator dynamics或 physical safety limit。結果後不得
回改這些值或 Motion Task thresholds來讓本 protocol通過。

## 3. Frozen training and evaluation design

- Warm start：`stand_start_walk_stop_0p7_phase_observable_v5`，bytes `1,983,126`，
  SHA-256 `c548867fbd17c736d54c1b1598d2abed1c7cb2dd28c7d310ea6e86ac3b36718c`。
- 每臂只執行一個 common agent seed `8700`，12 個 vector environments對應
  `8700–8711`。
- Requested budget `100,000` timesteps；因 `2048 × 12` rollout geometry，expected
  realized budget固定為 `122,880` timesteps。
- 每臂 deterministic evaluation固定 30 episodes，paired environment seeds為
  `18000–18029`。
- `19000–19029`已退役；`20000–20029`是 sealed FORMAL range。本 pilot任何讀取都
  是 structural failure。
- 所有 run class均為 `DEVELOPMENT`；不執行 FORMAL/HOLDOUT，不修改 registry或
  Live adapter。

因每臂只有一個 training replicate，本 pilot只能估計「固定 checkpoint條件下的
evaluation-seed variation」。`method_level_power_ready=false`與
`formal_sample_size_decision=BLOCKED_INDEPENDENT_TRAINING_SEED_VARIANCE_NOT_ESTIMATED`
是 frozen outcome，不得以 30 個 evaluation seeds冒充 30 個 training replicates。

## 4. Metrics、estimand and selection

Primary outcome是每 episode的 `saturation_duty_pct`。Pair由相同 evaluation seed建立，
contrast固定為 `candidate - V7A_REWARD_ONLY`。輸出每臂 mean/sample SD，以及 paired
difference mean/sample SD；不計 p-value或 confirmatory CI。

Training-environment pilot evaluator沿用 Motion Task V1數值，不調整：

- no fall；
- steady speed `0.35–1.05 m/s`；
- steady progress `≥1.40 m`；
- final stop speed `≤0.15 m/s`；
- lateral drift `≤0.30 m`；
- 500 Hz saturation threshold `95%`、duty `≤30%`。

這六項只是 training-environment pilot subset，不等同完整 11-criterion Live Motion Task。
任一候選只有在 30/30 terminal records存在、所有六項逐 episode通過且沒有 required
null/non-finite時才 eligible。若兩個候選都 eligible，選 mean saturation duty較低者；
完全相同則不選。沒有 eligible candidate時輸出
`PILOT_COMPLETE_NEGATIVE_RESULT_NO_CANDIDATE`，不得放寬 threshold。

## 5. Acceptance criteria

- `AP-01`：strict protocol、三臂與 operator identity exact。
- `AP-02`：execution前後 Git SHA相同且 tracked worktree clean。
- `AP-03`：warm-start path/bytes/SHA、common seed、profile與 requested/realized budget exact。
- `AP-04`：每臂恰有 `18000–18029` 共30個 paired terminal records；無 missing、duplicate、
  unexpected、retired或sealed seed。
- `AP-05`：`FAILED`、`CANCELLED`、negative、`NULL`、`NONFINITE`皆保留，不做
  complete-case deletion、imputation或不利 case重跑。
- `AP-06`：逐 episode明列 frozen six-gate subset結果，數值門檻與 source contract一致。
- `AP-07`：輸出 conditional variance與paired differences，同時保留 training-level power
  blocker。
- `AP-08`：所有 bundle artifact使用安全 relative path，bytes與SHA-256 readback exact；
  missing/tamper/path escape均 fail closed。
- `AP-09`：另一個 `python -I -S` stdlib-only process由 raw episode rows exact重建summary。
- `AP-10`：receipt維持 `paper_data_ready=false`與本 spec claim boundary。

只有 `AP-01..AP-10`全部通過才是完整 pilot evidence。Performance FAIL可構成完整負結果，
不會被改寫成 structural failure。

## 6. Failure semantics

- Structural failure：invalid/duplicate-key/non-finite JSON、identity drift、missing/duplicate/
  unexpected arm或seed、forbidden seed access、path escape、bytes/SHA mismatch、replay mismatch。
  CLI exit `2`，不得信任 partial summary。
- Semantic blocker：training/evaluation被中斷、取消，或 required outcome明示未觀測。
  保留 terminal record與reason，`pilot_planning_ready=false`，CLI exit `1`。
- Complete evidence：三臂與90個 episode records完整、identity/replay通過。即使全部
  performance FAIL仍 exit `0`，並輸出 negative-result status。
- 任何 NaN/Infinity不得寫成 JSON number；以 typed `NONFINITE` state與reason保留。

## 7. Claim boundary and theory check

[SOURCE] Gymnasium official `RescaleAction`與 Stable-Baselines3 official RL guidance支持
continuous action先維持 normalized symmetric range，再由 environment做有界映射；MuJoCo
official actuation model則把 filter描述為具 activation state的動態系統。

[SOURCE] Patterson et al.（JMLR 2024）區分 agent/environment RNG並建議 fully specified
methods使用 paired differences；Agarwal et al.（NeurIPS 2021）指出少量 runs只報 point
estimate會低估 statistical uncertainty。

[INFERENCE] Stateful low-pass/rate-limit若不公開 previous applied action，會引入 policy
不可見 state；因此 V7C沿用 observation中的 previous-action slots保存 applied state。

[RESULT] 本節只凍結 protocol，尚無 v7 performance result。

[BLOCKER] 沒有 independent training-seed variance、full 500 Hz Live traces、actual Study A、
formal authorization、HIL、bench或 robot evidence。

因此允許的結論只到：在此 frozen MuJoCo plant、v5 warm start、task、training seed與
DEV evaluation seeds下，action-interface variant呈現何種 conditional simulated outcome。
不得宣稱 controller superiority、sample-size adequacy、paper readiness、physical torque/
thermal margin、安全、sim-to-real或實體機器人效能。

Primary/official sources：

- [Gymnasium Action Wrappers](https://gymnasium.farama.org/main/api/wrappers/action_wrappers/)
- [Stable-Baselines3 RL Tips](https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html)
- [MuJoCo Actuation Model](https://mujoco.readthedocs.io/en/stable/computation/index.html#actuation-model)
- [Empirical Design in Reinforcement Learning, JMLR 2024](https://www.jmlr.org/papers/v25/23-0183.html)
- [Deep RL at the Edge of the Statistical Precipice, NeurIPS 2021](https://proceedings.neurips.cc/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html)
- [Benchmarking Actor-Critic Deep RL Algorithms for Robotics Control with Action Constraints, RA-L 2023](https://doi.org/10.1109/LRA.2023.3284378)
