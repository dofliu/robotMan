# V1 Dynamic Reference Suite — Frozen V1

最後更新：2026-09-22 ｜ ID：`V1-DYNAMIC-REFERENCE-SUITE-V1` ｜ 任務 #105

狀態：`EXECUTED_2026-09-22_PASS_6_OF_6 / V1 PARTIAL / SIM_ONLY_MUJOCO`（凍結於 `a65bef2`，執行記錄見 [receipt](receipts/V1_DYNAMIC_REFERENCE_SUITE_RECEIPT_2026-09-22.md)）

上游：[VV_PLAN](VV_PLAN.md) `V1-R11`（numerical convergence）、`V1-R13`（energy consistency）、`V1-R14`（analytical reference cases：known pendulum、articulated）
｜ 前一個 V1 milestone：[V1_ANALYTICAL_SUITE_SPEC](V1_ANALYTICAL_SUITE_SPEC.md)（passive single-support fixture）
｜ 實作：`backend/v1_dynamic_reference_suite.py`（primary）、`backend/v1_dynamic_replay.py`（stdlib-only replay）、`backend/test_v1_dynamic_reference_suite.py`

---

## 1. 本次唯一 milestone

補 V1 目前缺的兩個「動態」參考案例，各做 `4／2／1 ms` 網格，全部 **無接觸、無控制器、無致動、無 assist**：

| 案例族 | 內容 | 對應 |
|---|---|---|
| **P. known pendulum** | 單一球體物理單擺，閉式解週期與能量 | `V1-R14` known pendulum；`V1-R11` 動態收斂 |
| **A. articulated passive swing** | 專案的人形 MJCF，軀幹固定於世界、去地板、去致動器，四肢從非對稱初始姿態被動擺動；能量平衡（含關節阻尼功） | `V1-R13` energy consistency；`V1-R14` articulated；`V1-R11` articulated 動態收斂 |

它**不**處理：dynamic contact、solver-tolerance 掃描、finite-difference 研究、joint limits、actuator envelope、controller。V1 gate 在本 milestone 之後仍是 `PARTIAL_IMPLEMENTED_NOT_PASS`。

---

## 2. 凍結的案例定義

### 2.1 P. known pendulum（`known_pendulum_{4,2,1}ms`）

- MJCF：`<compiler angle="radian"/>`；`<option gravity="0 0 -9.81" timestep="dt" integrator="implicitfast"><flag energy="enable"/></option>`；
  worldbody 內一個 body `arm`（pivot 在 `(0, 0, 1.5)`），hinge `pivot` 軸 `(0, 1, 0)`、`damping="0"`、`armature="0"`；
  一個 sphere geom `bob`：`size="0.05"`（r = 0.05 m）、`pos="0 0 -0.5"`（L = 0.5 m）、`mass="2.0"`。沒有地板、沒有其他 geom。
- 初始條件：θ₀ = π/3（60°），θ̇₀ = 0。時長 **6.0 s**。
- 閉式解（獨立於引擎，只用 MJCF 裡的數字）：
  - I_pivot = (2/5)·m·r² + m·L²（球體對自身質心的慣量 + 平行軸），d = L。
  - 週期 T = 4·√(I_pivot／(m·g·d))·K(k)，k = sin(θ₀/2)，K 為第一類完全橢圓積分，以 AGM 計算：K(k) = π／(2·M(1, √(1−k²)))。
  - 能量 E(θ, θ̇) = ½·I_pivot·θ̇² + m·g·L·(1 − cos θ)，E₀ = m·g·L·(1 − cos θ₀)。
- 量測週期：θ(t) 由負轉正的零交越（線性插值）之間隔的平均；6 s 內至少 3 個完整週期。

### 2.2 A. articulated passive swing（`articulated_passive_swing_{4,2,1}ms`）

- 由 `model_builder.build_mjcf(default_robot(), [], dynamic=True)` 的輸出做**四個字串變換**，每個變換的目標在原文中必須恰好出現一次：
  1. 移除 `<freejoint name="root"/>`（軀幹固定於世界）；
  2. 移除 `<geom name="floor" …/>`（無地板，故無任何可能的接觸：機器人自身不互碰）；
  3. 移除 `<actuator>…</actuator>`（`nu = 0`）；
  4. 軀幹 `pos` 改為 `0 0 1.6`；`<option>` 改為 `gravity="0 0 -9.81" timestep="dt" integrator="implicitfast"` 並加 `<flag energy="enable"/>`。
  其餘（所有 geom、質量、關節阻尼 1.0／0.3、armature、碰撞遮罩）**一字不動**；原始 MJCF 與變換後 MJCF 的 sha256 都寫入 model receipt。
- 初始姿態（rad，θ̇ = 0）：`hip_roll_l 0.15`、`hip_pitch_l 0.6`、`knee_l −1.0`、`ankle_l 0.2`、`hip_roll_r −0.10`、`hip_pitch_r −0.4`、`knee_r −0.3`、`ankle_r −0.2`、
  `shoulder_l 1.0`、`elbow_l 0.8`、`shoulder_r −0.8`、`elbow_r 0.3`。時長 **3.0 s**。
- 能量平衡（每步）：
  - KE = Σ_b [½·m_b·|v_b|² + ½·ω_bᵀ·(R_b·diag(I_b)·R_bᵀ)·ω_b] + ½·Σ_j armature_j·q̇_j²，其中 v_b 是 body b **質心**的世界速度、ω_b 世界角速度、R_b 慣量主軸的世界姿態、I_b 主慣量；
  - PE = Σ_b m_b·g·z_{com,b}；
  - W_damp(t) = ∫₀ᵗ Σ_j d_j·q̇_j² dt，以序列化的 q̇ 做梯形法；
  - 殘差 r(t) = KE(t) + PE(t) + W_damp(t) − [KE(0) + PE(0)]；
  - 尺度 E_scale = [KE(0) + PE(0)] − min_t PE(t)（規則事前定，數字由執行決定）。
- 引擎交叉比對：同一步的 MuJoCo `energy = [PE, KE]`（`mj_energyPos`／`mj_energyVel`）必須與獨立重算的 PE、KE 一致（相對 `1e-8`）。這是 same-engine 一致性，不是獨立驗證；獨立的是**守恆**檢查本身。
- 解析慣量比對（只做球體與方盒組成的 body：`trunk`、`foot_l`、`foot_r`；含 capsule 的 body 只比對質量）：由 MJCF 文字的 geom `type／size／pos／mass` 以標準公式（球 2/5·m·r²；盒 m/12·(b²+c²)；平行軸）組合成 body 慣量張量，其特徵值排序後與 compiled `body_inertia` 相對誤差 `≤ 1e-9`，質心與 `body_ipos` 絕對誤差 `≤ 1e-12 m`；每個 body 的 `body_mass` 與 geom mass 總和絕對誤差 `≤ 1e-12 kg`。

---

## 3. 凍結的 acceptance criteria（門檻在執行前寫死於 `DYNAMIC_SUITE_CONTRACT`，不得依首輪結果放寬）

### 3.1 每個 case 共同

| 判準 | 門檻 |
|---|---|
| `FINITE_RAW_VALUES` | 所有序列化值有限 |
| `TRACE_STEP_COUNT` | 步數 = round(duration／dt) |
| `TRACE_TIME_GRID` | max｜t_k − k·dt｜ `≤ 1e-12 s` |
| `COMPILED_TIMESTEP_IDENTITY` | compiled timestep = case dt（exact） |
| `COMPILED_MODEL_CONTRACT` | integrator IMPLICITFAST、gravity `(0,0,−9.81)`、`nu = 0`、energy flag 開、預期 joint 數與 dof 阻尼／armature 與 MJCF 一致 |
| `EXTERNAL_FORCE_ABSENT` | 每步 `qfrc_applied`、`xfrc_applied` 的最大絕對值 = 0 |
| `NO_CONTACT` | 每步 `ncon = 0` |
| `ENGINE_KINETIC_ENERGY_AGREEMENT` | max｜KE_replay − KE_engine｜／(1 + max KE) `≤ 1e-8` |
| `ENGINE_POTENTIAL_ENERGY_AGREEMENT` | max｜PE_replay − PE_engine｜／(1 + max｜PE｜) `≤ 1e-8` |

### 3.2 P. known pendulum

| 判準 | 4 ms | 2 ms | 1 ms | 依據 |
|---|---|---|---|---|
| `PENDULUM_PERIOD_COUNT` ≥ 3 | 3 | 3 | 3 | 6 s ≈ 3.9 T |
| `PENDULUM_PERIOD_RELATIVE_ERROR` = ｜T_meas − T_closed_form｜／T_closed_form | `≤ 1e-3` | `≤ 1e-3` | `≤ 1e-3` | 半隱式 Euler 的頻率誤差 ≈ (ωΔt)²/24 ≈ 1.3e-5（4 ms）；門檻留 ~75× |
| `PENDULUM_ENERGY_RELATIVE_FLUCTUATION` = max_t｜E(t) − E₀｜／E₀ | `≤ 0.02` | `≤ 0.01` | `≤ 0.005` | 半隱式 Euler 的能量振盪 ≈ (Δt/2)·max｜τ_g·θ̇｜／E₀ ≈ 0.81%／0.41%／0.20%；門檻留 ~2.5× |
| `PENDULUM_ENERGY_SECULAR_DRIFT` = ｜mean E（最後一個完整週期）− mean E（第一個完整週期）｜／E₀ | `≤ 1e-3` | `≤ 1e-3` | `≤ 1e-3` | 辛積分器無長期漂移；若引擎非辛，此項會 FAIL 並如實保留 |
| `PENDULUM_INERTIA_ANALYTIC_AGREEMENT` | compiled `body_inertia` 對 (2/5)·m·r² 相對 `≤ 1e-9`；`body_ipos` 對 `(0,0,−0.5)` 絕對 `≤ 1e-12` | | | 球體閉式慣量 |

### 3.3 A. articulated passive swing

| 判準 | 4 ms | 2 ms | 1 ms | 依據 |
|---|---|---|---|---|
| `ENERGY_BALANCE_RESIDUAL_RELATIVE_MAX` = max_t｜r(t)｜／E_scale | `≤ 0.05` | `≤ 0.025` | `≤ 0.0125` | 阻尼功以梯形法對隱式阻尼離散化，殘差 O(ω·Δt)；關節角速率 ~5 rad/s → ~2%／1%／0.5%；門檻留 ~2.5× |
| `ENERGY_SCALE_POSITIVE` | E_scale `> 1 J` | | | 避免以零尺度作分母 |
| `BODY_MASS_ANALYTIC_AGREEMENT` | 每個 body：｜body_mass − Σ geom mass｜`≤ 1e-12 kg` | | | MJCF 文字 |
| `BODY_INERTIA_ANALYTIC_AGREEMENT` | `trunk`、`foot_l`、`foot_r`：主慣量相對 `≤ 1e-9`、質心 `≤ 1e-12 m` | | | 球＋盒閉式慣量；capsule body 不在此判準（明列） |

### 3.4 Suite 層（跨 dt）

| 判準 | 門檻 |
|---|---|
| `EXACT_CASE_INVENTORY` | 恰好 6 個 case、id 與 dt 與本規格一致，無缺、無重複、無多餘 |
| `ALL_CASES_PASS` | 6/6 |
| `PENDULUM_PERIOD_TIMESTEP_FINE_DELTA` | ｜T_2ms − T_1ms｜ `≤ 5e-4·T_closed_form` |
| `PENDULUM_PERIOD_TIMESTEP_MONOTONE` | ｜T_2ms − T_1ms｜ `≤ max(｜T_4ms − T_2ms｜, 1e-7 s)` |
| `ARTICULATED_RESIDUAL_TIMESTEP_MONOTONE` | 殘差比（`ENERGY_BALANCE_RESIDUAL_RELATIVE_MAX`）1 ms `≤ max(2 ms, 1e-6)` 且 2 ms `≤ max(4 ms, 1e-6)` |
| `TIMESTEP_NON_DT_CONFIG_IDENTITY` | 同族三個 case 除 dt 外的 config 完全一致 |
| observed order | 只有兩個 successive differences 皆大於 floor、同號且可估時才回報；否則 `null` 與 diagnostic status，不補成 PASS |

### 3.5 Primary 對 replay

- Replay process **只用 Python 標準函式庫**，不匯入 MuJoCo、NumPy、controller 或任何專案模組；輸入只有序列化的 raw trace 與 model receipt；primary 的 metrics 是比對對象，不是輸入。
- 每個 metric 的 primary／replay 相對差異 `≤ 1e-10`（絕對差異 `≤ 1e-12` 亦可）；criteria 的 `passed` 必須逐項相同。
- 缺欄、shape 不符、NaN／Infinity、非標準 JSON、contract 漂移 → `ReplayValidationError`，不得產生 PASS receipt；有限值 tamper 造成門檻超出 → 保留 `FAIL`，不 repair、不放寬。

---

## 4. Failure semantics

- 任一 finite criterion 失敗：case／suite 為 `FAIL`，raw 不刪除、不補值、不 repair；receipt 如實記 FAIL。
- 本規格的門檻是**在看到任何一個 case 的結果之前**由數值分析推得（§3 的「依據」欄）；若首輪 FAIL，記錄為量測結果並另立版本討論，不得就地改門檻。

---

## 5. Claim boundary

`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`。本 suite 證明的是：(P) 引擎對一個有閉式解的動態系統，其週期與能量行為在凍結門檻內；
(A) 專案的 articulated plant 在無接觸、無致動下，引擎的能量記帳可由序列化量獨立重算並在凍結門檻內守恆（含阻尼功），
且球／盒組成 body 的 compiled 慣量與閉式公式一致。它**不**證明接觸物理、致動器、控制器、任何實體能力，也**不**使 V1 PASS。

---

## 6. 執行結果（2026-09-22，寫於執行之後）

- **第 1 次執行**（源碼 `a65bef2`，凍結 commit）：3 個 pendulum case PASS；3 個 articulated case **FAIL**——重算公式把 `mj_objectVelocity(mjOBJ_BODY)` 的線速度當成 body 原點速度再加 `ω × r`，而它已是質心速度；`ENGINE_KINETIC_ENERGY_AGREEMENT` 讀到 1.2。**這是重算公式缺陷，不是門檻或物理問題。**
- 修正（`4a96f54`）：拿掉 `ω × r`、序列化欄位改名 `linvel_com_world`；**§3 的門檻一個都沒動**。
- **第 2 次執行**（源碼 `4a96f54`，乾淨樹）：**6/6 PASS**，stdlib replay 84 個 metric 相符。數字與 artifact sha256 見 [receipt](receipts/V1_DYNAMIC_REFERENCE_SUITE_RECEIPT_2026-09-22.md)。
- 對 V1 gate 的影響：`V1-R13` BLOCKED → PARTIAL、`V1-R14` known pendulum 與被動 articulated 完成、`V1-R11` 加兩個動態收斂研究；gate 仍 `PARTIAL_IMPLEMENTED_NOT_PASS`。
