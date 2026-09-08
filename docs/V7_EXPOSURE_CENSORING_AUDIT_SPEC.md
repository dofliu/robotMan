# V7 Early-Termination / Exposure-Censoring Validity Audit V1 Specification

日期：2026-09-08

狀態：`FROZEN BEFORE IMPLEMENTATION / INTERNAL DEVELOPMENT ONLY`

Protocol：`AUDIT-V7-EXPOSURE-CENSORING-V1`
Machine-readable contract：
[`backend/v7_exposure_audit_protocol.json`](../backend/v7_exposure_audit_protocol.json)

證據範圍：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`

## 1. 本次唯一 milestone

只讀 [V7 Action-Interface DEVELOPMENT Pilot](V7_ACTION_INTERFACE_PILOT_SPEC.md) 已保存的 bundle，
重建每個 episode 的 termination control step、termination sim time與 termination phase，
再由這些量導出 realized exposure，並明示：哪些 primary-outcome值可比較、哪些是
exposure-censored、哪些是保留的 method failure。

Milestone 是否完成只由 audit evidence completeness決定。audit的結論若是「pilot的
paired contrast不可比較」，那是有效的 audit result，不是 software failure，也不會被改寫成
pilot結果的修正。

本 audit 不重訓、不新增 training/evaluation seed、不調整 `alpha`、joint envelope、rate limit
或任何 Motion Task threshold、不選 candidate、不算 confidence interval或 p-value、不開啟
FORMAL/HOLDOUT partition。2026-09-06 的 pilot receipt原文保留，不回改。

本 spec 在任何 audit source implementation前凍結。

## 2. Frozen audit inputs 與 read-only contract

被 audit 的對象是 protocol `PILOT-V7-ACTION-INTERFACE-DEV-V1`，其 frozen artifact identity為
`backend/rl/v7_action_interface_pilot_protocol.json`、bytes `9753`、SHA-256
`719b70a2bdf8d23af5f4ec5dff51a6099e88d6de4e2221fa74f6f7464cdfcb96`。retained pilot receipt
的 SHA-256為 `ed3e3eaa7c86f2b855d24aca68b09ce45bce61ac2fb6e573328b12157d758435`，
source Git為 `058657dd43d28a9175e54362cf4d0a0618507c38`。

Read-only由以下四項強制，任一項失敗即 structural failure：

1. audit output root不得等於或位於 source bundle root之內；
2. 每個被讀取的 source artifact在 audit前後各做一次 bytes與SHA-256 readback，前後必須相同；
3. audit process只以 read mode開啟 source artifact，所有輸出寫入獨立 output root且禁止覆寫；
4. source bundle的 receipt SHA-256決定 bundle class。

Bundle class為 fail-closed binding：receipt SHA-256等於上述 frozen pilot receipt hash者
必須宣告 `V7_PILOT_DEVELOPMENT_BUNDLE`；其他一律必須宣告
`SYNTHETIC_REGRESSION_BUNDLE`。任一方向不符即 structural failure。只有
`V7_PILOT_DEVELOPMENT_BUNDLE`才能讓 `audit_applies_to_frozen_v7_pilot=true`；
synthetic bundle只用來驗證 audit software，永遠不支持任何關於 v7 pilot的敘述。

## 3. Frozen exposure 與 phase reconstruction

Exposure horizon不是本 audit新訂的門檻，而是由既有 frozen task contract導出：

```text
control_period_s                    = 1 / control_rate_hz              = 0.02 s
physics_substeps_per_control_step   = physics_rate_hz / control_rate_hz = 10
full_exposure_control_steps         = duration_s * control_rate_hz     = 450
full_exposure_physics_substeps      = 450 * 10                         = 4500
```

`duration_s=9.0`、`physics_rate_hz=500.0`與 `control_rate_hz=50.0`來自 pilot protocol的
`task_contract`；`backend/motion_tasks.py`必須維持 SHA-256
`3dd9a47b6798a2fba713eda3654b428377f3a75e825105b233a1da375d4215af`。上述每個商與積都
必須是 exact integer，否則 fail closed。

Frozen phase schedule同樣由既有 contract導出，並以 half-open control-step interval表示：

| Phase | start_s | end_s | control steps |
|---|---:|---:|---|
| `INITIAL_STAND` | 0.0 | 1.0 | 0–49 |
| `START` | 1.0 | 2.5 | 50–124 |
| `STEADY_WALK` | 2.5 | 6.5 | 125–324 |
| `STOP` | 6.5 | 8.0 | 325–399 |
| `FINAL_STAND` | 8.0 | 9.0 | 400–449 |

每個 episode由 retained `control_step_trace`重建：

- `observed_control_steps` = trace length；
- `observed_physics_substeps` = 逐 step `saturation_substeps_total`之和，且必須等於
  `observed_control_steps * 10`；
- `termination_control_step` = `observed_control_steps - 1`，空 trace為 null；
- `termination_sim_time_s` = `observed_control_steps * control_period_s`；
- `termination_phase_id` = frozen schedule中包含 `termination_control_step`的 phase；
- `recorded_termination_command_phase` = trace最後一筆的 `command_phase`。

每一筆 control-step record的 `command_phase`都必須等於 frozen schedule對該 index的 phase。
任何 phase drift、未知 phase identifier或非 exact control-step的 phase boundary都是
structural failure。`exposure_class`為 `FULL_EXPOSURE`、`EARLY_TERMINATED`或
`NO_EXPOSURE`；超過 450 steps是 `OVER_EXPOSURE`且 fail closed。

## 4. Censoring、identification bounds 與 comparability

Primary outcome維持 pilot的 `saturation_duty_pct`，其 denominator是該 episode retained control
steps的 `saturation_substeps_total`之和，因此與 realized exposure成正比。target estimand是
`FULL_HORIZON_SATURATION_DUTY_PCT`，以 4500個 physics substeps為分母。

`comparability_state`依固定順序判定：

1. `METHOD_FAILURE_NOT_CENSORING`：primary outcome為 `NULL`或 `NONFINITE`、
   `terminal_record_state`不是 `COMPLETED`，或 `NO_EXPOSURE`；
2. `EXPOSURE_CENSORED`：primary outcome算術上 `OBSERVED`，但 episode為 `EARLY_TERMINATED`；
3. `COMPARABLE`：primary outcome `OBSERVED`且 `FULL_EXPOSURE`。

[SOURCE] Wünsch et al.（Statistics in Medicine 2025）指出 comparison study的 method failure
通常形成 undefined performance，silent deletion與一般 missing-data imputation都不適當。
[SOURCE] NIST/SEMATECH的 censoring定義只涵蓋「只知 bound或interval」的觀察機制。
[RESULT] 因此本 audit沿用本 repo已凍結的立場：non-finite、solver/process error、terminal
failure與 cancellation是 method failure，不是 censoring；它們保留 frequency與reason，不轉成
observed value，也不取得 bound。

對 `COMPARABLE`與 `EXPOSURE_CENSORED` episode輸出 assumption-free worst-case identification
bounds：

```text
lower_pct = 100 * observed_over_threshold_substeps / 4500
upper_pct = 100 * (observed_over_threshold_substeps + 4500 - observed_substeps) / 4500
```

lower假設所有未觀測 substep都未超過 threshold，upper假設全部超過。`FULL_EXPOSURE`時
`observed_substeps = 4500`，上下界收斂到 recorded value。paired bound為

```text
paired_lower = candidate_lower - reference_upper
paired_upper = candidate_upper - reference_lower
```

只有當 paired bound不含 0時，contrast的 sign才算 identified；bound含 0代表在沒有另外凍結
censoring assumption的情況下，effect方向不可識別。

[SOURCE] 本 repo [Paired Statistics and Paper Export Contract V1](PAIRED_STATISTICS_CONTRACT.md)
已凍結「未凍結 censored estimator前只保存 bound並阻擋一般 mean/bootstrap」的規則。
[RESULT] 本 audit因此報 bound，不報 censored point estimate，也不做 CI、p-value或
hypothesis test。

Pair層級：`COMPARABLE`只在兩側皆 `COMPARABLE`時成立。非 comparable pair保留其
`retained_arithmetic_difference`（兩側 primary outcome皆 `OBSERVED`時），但明示為
「不是有效 contrast」。audited paired mean與 sample SD只在 30個 pair全部 `COMPARABLE`時
輸出，否則為 null並記
`BLOCKED_EXPOSURE_CENSORED_PAIRS_RETAINED_NO_COMPLETE_CASE_DELETION`。禁止只取
comparable subset做 aggregate，因為 censoring indicator由該臂自身的 early-termination行為
產生，與 outcome不獨立。

另輸出一個 `DESCRIPTIVE_ONLY`的 exposure-matched sensitivity：每個 seed取
`k = min(reference observed_control_steps, candidate observed_control_steps)`，再由 retained
per-control-step counts重算兩側前 `k`步的 duty。它只用來顯示 candidate的 0%或近 0%在
reference同樣被截斷時是否還存在；`k=0`輸出 null。

[INFERENCE] Truncation matching只讓 measurement denominator相等，不移除 informative
censoring，因為截斷點由該臂自身的 early termination產生，也無法回復 full-horizon estimand。
因此它不得用於 candidate selection、CI、p-value、hypothesis test、恢復 comparability或
sample-size決策。

## 5. Acceptance criteria

- `AX-01`：source bundle在 audit前後 bytes/SHA-256完全相同；output root不在 source bundle內。
- `AX-02`：frozen task horizon與 rate quotient均為 exact integer，且 `motion_tasks.py` SHA-256 exact。
- `AX-03`：逐 episode重建 exposure、termination control step/sim time/phase，且
  `observed_physics_substeps == observed_control_steps * 10`。
- `AX-04`：每一筆 recorded `command_phase`等於 frozen schedule對該 control-step index的 phase。
- `AX-05`：`EXPOSURE_CENSORED`與 `METHOD_FAILURE_NOT_CENSORING`分開分類，兩者皆保留
  frequency與reason，不做 complete-case deletion或 imputation。
- `AX-06`：輸出 assumption-free full-horizon與 paired identification bounds，並明示 sign是否 identified。
- `AX-07`：pair層級 comparability、retained arithmetic difference與 blocked aggregate皆輸出。
- `AX-08`：輸出 exposure-matched descriptive sensitivity，同時保留 informative-censoring blocker。
- `AX-09`：原 pilot receipt SHA-256與 `selected_candidate_arm_id=null`原樣保留；pilot summary
  若出現非 null selection即 fail closed。
- `AX-10`：所有 audit artifact使用安全 relative path，bytes與SHA-256 readback exact；
  missing/tamper/path escape均 fail closed。
- `AX-11`：另一個 `python -I -S` stdlib-only process由 raw episode rows exact重建 audit summary。
- `AX-12`：receipt維持 `paper_data_ready=false`與本 spec的 claim boundary。

只有 `AX-01..AX-12`全部通過才是完整 audit evidence。

## 6. Failure semantics

- Structural failure：source bundle drift、output root位於 source bundle內、missing/duplicate/
  unexpected arm或seed、forbidden seed access、invalid JSON、duplicate JSON key、non-finite
  JSON number、path escape、bytes/SHA-256 mismatch、phase-schedule drift、exposure或
  denominator不一致、over-exposure、non-null pilot selection、bundle class binding mismatch、
  replay mismatch。CLI exit `2`，不得信任 partial summary。
- Retained censoring blocker：至少一個 non-comparable pair或 censored primary-outcome值被保留，
  `pilot_planning_ready=false`，CLI exit `1`。
- Audit complete without censoring blocker：所有 pair皆 comparable，CLI exit `0`。
- 任何 NaN/Infinity不得寫成 JSON number；以 typed `NONFINITE` state與reason保留。

Retain states為 `COMPLETED`、`FAILED`、`CANCELLED`、`NULL`、`NONFINITE`、
`EXPOSURE_CENSORED`與 `METHOD_FAILURE_NOT_CENSORING`。threshold change為 `FORBIDDEN`。

## 7. Claim boundary and theory check

[SOURCE] NIST/SEMATECH把 censoring定義為只知 bound或interval的觀察機制；Wünsch et al.
（Statistics in Medicine 2025）要求 comparison study保存 method failure的 frequency、reason與
handling，不做 silent deletion。

[SOURCE] Patterson et al.（JMLR 2024）要求 fully specified methods使用 paired differences並
分開 agent/environment RNG；Agarwal et al.（NeurIPS 2021）指出少量 runs只報 point estimate
會低估 statistical uncertainty。

[SOURCE] NASA-STD-7009B要求保留 discretization、iterative與finite-precision error evidence，
並要求 model結果附帶其適用範圍。

[INFERENCE] `saturation_duty_pct`是 rate，分母與 realized exposure成正比；當兩臂 realized
exposure不相等時，逐 seed的算術差不是同一 estimand的 contrast。這是 measurement-support
問題，不是 statistical power問題，因此無法用增加 seeds解決。

[RESULT] 本 audit只重播既有 raw traces，輸出 exposure、termination、censoring分類、
assumption-free bounds與 descriptive sensitivity。

[BLOCKER] 沒有 independent training-seed variance、full 11-criterion Live evidence、actual
Study A、frozen censored estimator、binary paired CI、complete environment lock、
immutable storage、HIL、bench或robot evidence。

因此允許的結論只到：在此 frozen MuJoCo plant、v5 warm start、單一 training seed與 DEV
evaluation seeds下，v7 pilot的 primary-outcome contrast在 realized exposure不相等時是否具有
內部可比性。不得宣稱 controller superiority、method-level effect、sample-size adequacy、
paper readiness、physical torque/thermal margin、安全、sim-to-real或實體機器人效能，也不得
用本 audit回改 pilot的 selection或 thresholds。

Primary/official sources：

- [NIST/SEMATECH Censoring](https://www.itl.nist.gov/div898/handbook/apr/section1/apr131.htm)
- [Rethinking the Handling of Method Failure in Comparison Studies, Statistics in Medicine 2025](https://doi.org/10.1002/sim.70257)
- [Empirical Design in Reinforcement Learning, JMLR 2024](https://www.jmlr.org/papers/v25/23-0183.html)
- [Deep RL at the Edge of the Statistical Precipice, NeurIPS 2021](https://proceedings.neurips.cc/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html)
- [IETF RFC 8259 — JSON](https://www.rfc-editor.org/rfc/rfc8259.html)
- [NASA-STD-7009B](https://standards.nasa.gov/sites/default/files/standards/NASA/B/1/NASA-STD-7009B-Final-3-5-2024.pdf)
- [MuJoCo Actuation Model](https://mujoco.readthedocs.io/en/stable/computation/index.html#actuation-model)
