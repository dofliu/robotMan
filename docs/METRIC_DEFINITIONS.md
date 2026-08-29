# Analysis Metric Definitions

本文件是 analysis `/api/simulate` runtime 指標的單一公式來源。Current metric set 為 `ANALYSIS_METRICS_V1`；這些值是 SIM-only estimate，不是 physical measurement 或 actuator validation。

## 1. Sampling window

- Internal sample interval：`DT = 1/120 s`。
- Elapsed time：`t[-1] - t[0]`，因此可能略小於 requested duration。
- Distance、energy、average speed、average power 與 CoT 使用完整 sampled window。
- Actuator 與 ZMP statistics 的 nominal steady window 以 gait cycle `T` 定義：

~~~text
t_start = min(2*T, requested_duration/2)
t_end   = requested_duration - T
steady_mask = (t >= t_start) and (t <= t_end)
~~~

若此 mask 無 sample，改用完整 sampled window，回傳
`actuator_stats_window.mode=full_window_fallback` 並產生 warning。Summary 同時回傳實際
`start_s`、`end_s` 與 `n_samples`；獨立重算不得從 UI 畫面猜測窗口。

## 2. Motion

設 floating-base root 的前進座標為 `x_root`：

~~~text
net_displacement = x_root(t_end) - x_root(t_start)
distance         = max(net_displacement, 0)
avg_speed        = distance / elapsed_time
~~~

`distance` 是 non-negative net forward progress，不是 path length、footstep length、CoM travel 或 command speed。倒退會保留在 `net_displacement`，但不冒充 forward task distance。

## 3. Power and energy estimate

每一關節先計算 `P_mech = tau_joint * qd_joint`。只有 `P_mech > 0` 的 driving sample 進入目前的簡化 electrical estimate：

~~~text
P_est = P_mech / (gear_efficiency * motor_efficiency), if P_mech > 0
P_est = 0,                                               otherwise
energy_J   = trapezoidal_integral(sum(P_est), t)
avg_power  = energy_J / elapsed_time
~~~

此模型忽略 copper/iron/driver/idle loss、battery/voltage/current limit、regeneration、thermal state 與 efficiency map；因此欄位只能稱為 simplified electrical energy/power estimate。

## 4. CoT estimate

~~~text
CoT = energy_J / (model_total_mass * g * distance)
~~~

其中 `g=9.81 m/s²`。當 `distance <= 1e-9 m` 時，CoT 回傳 JSON `null` 並附 warning；禁止用 command speed 或 epsilon distance 代算。

Analysis CoT 與 live comparison script 的 sampled absolute mechanical-work proxy 定義不同，不可直接排名。

## 5. Actuator statistics

- `peak_*`：窗口內 true maximum，供目前 representative threshold screen。
- `p99_5_*`：窗口內 99.5 percentile，只作 descriptive diagnostic，不替代 peak gate。
- `rms_*`：窗口內 root-mean-square。
- 所有 motor/gear thresholds 都來自 D0 representative parameters；超限只代表 current SIM-only rule violation。

## 6. ZMP/support indicator

Analysis ZMP、GRF/contact sharing 與 support polygon 使用 prescribed schedule 與 analytical assumptions。`zmp_stable_pct` 是該模型內的 trajectory/support consistency indicator，不是 fall probability、measured stability 或 independent contact validation。

ZMP statistics 先使用第 1 節的 steady/full-window mask，再排除 scheduled contact
topology 切換附近的 samples。左右腳 contact weight 以 `> 0.05` 判定 active；每個
active-state 變化點排除 transition index 前 4 點至後 10 點（120 Hz 下約
`-33 ms` 至 `+83 ms`）。

~~~text
candidate_count = count(statistics_window and not topology_exclusion)
valid_count     = count(candidate samples whose zmp_margin is finite)
coverage_pct    = 100 * valid_count / candidate_count
unstable_pct    = 100 * mean(zmp_margin < -0.025 m over valid samples)
stable_pct      = 100 - unstable_pct
~~~

- `zmp_candidate_sample_count`、`zmp_valid_sample_count` 與
  `zmp_valid_coverage_pct` 明示統計覆蓋率；candidate 為零時 coverage 回傳 `null`。
- valid count 為零時，`zmp_stable_pct`、`min_zmp_margin_cm` 與
  `p01_zmp_margin_cm` 全部回傳 JSON `null`，並產生
  `ZMP_STABILITY=UNAVAILABLE` warning；禁止把無資料轉成 100%。
- `min_zmp_margin_cm` 是 valid samples 的 true minimum；
  `p01_zmp_margin_cm` 是第 1 percentile diagnostic。若 warning 使用 P1 值，文字必須
  明示 P1，不能稱為 minimum。
- `-0.025 m` 是目前未經實體或 higher-fidelity contact model 校準的 model
  tolerance，不是實體穩定門檻。

## 7. Output rounding

Runtime summary 是方便 UI/readback 的 rounded view；正式 oracle 應由 raw sampled
arrays 獨立重算，不得再由 rounded summary 反推。Current response rounding：

- elapsed、distance、net displacement、average speed：4 decimals；
- energy、average power、ZMP percentages 與 margin in cm：1 decimal；
- CoT：3 decimals；
- actuator torque：joint peak/P1 2 decimals，motor peak/P1/RMS 3 decimals；
- actuator utilization percentages：1 decimal；speed rpm：whole rpm。

## 8. Change control

下列任一變更必須提升 metric set version：公式、sampling/integration、window、filter、percentile、null/failure handling、coordinate definition、energy loss/regeneration model、mass/gravity denominator或 summary rounding。舊 result 不可在未重新執行時改標成新 metric version。
