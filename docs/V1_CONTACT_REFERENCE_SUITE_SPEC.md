# V1 Contact Reference Suite — Frozen V1

最後更新：2026-09-22 ｜ ID：`V1-CONTACT-REFERENCE-SUITE-V1` ｜ 任務 #106

狀態：`FROZEN_NOT_EXECUTED / V1 PARTIAL / SIM_ONLY_MUJOCO`（門檻在任何 case 執行前寫死；執行後只允許在 §7 追加結果與 receipt 連結，不得回頭改 §2–§5）

上游：[VV_PLAN](VV_PLAN.md) `V1-R05`（unilateral contact，dynamic）、`V1-R06`（friction feasibility，dynamic）、`V1-R08`（contact schedule consistency）、`V1-R11`（numerical convergence）、`V1-R14`（analytical reference cases：dynamic contact）
｜ 前一個 V1 milestone：[V1_DYNAMIC_REFERENCE_SUITE_SPEC](V1_DYNAMIC_REFERENCE_SUITE_SPEC.md)（無接觸的動態參考案例）
｜ 實作：`backend/v1_contact_reference_suite.py`（primary）、`backend/v1_contact_replay.py`（stdlib-only replay）、`backend/test_v1_contact_reference_suite.py`

---

## 1. 本次唯一 milestone

**兩個有接觸、無控制器、無致動的參考案例族，加一個預先登記的 Coulomb 假說量測**，全部用**專案 plant 的接觸參數**（地板 plane 宣告逐字相同：`friction="1.0 0.005 0.0001"`、`contype/conaffinity` 位元遮罩相同；接觸體用腳板的摩擦三元組；`solref`／`solimp`／`condim`／cone／solver 全部是專案未覆寫的 MuJoCo 預設；`integrator="implicitfast"`、`gravity="0 0 -9.81"`）：

- **C. drop-and-settle**（`drop_and_settle_{4,2,1}ms`）：一顆自由球（freejoint，1 個接觸點）從 0.5 m 高自由落下、著地、靜止。閉式：離散自由落體位置與**觸地步**、連續觸地時刻、法向衝量＝重量積分、靜止 GRF＝重量、**靜止穿透深度**（引擎軟接觸模型的閉式平衡）。
- **S. viscous slider**（`viscous_slider_{4,2,1}ms`）：一塊只能平移（`slide x`、`slide z`，4 個接觸點）的薄板，靜置後被賦予 0.02 m/s 的水平速度。閉式：**未飽和摩擦的黏滯衰減**（速率 ρ 由引擎的軟約束模型推得）、靜止穿透深度（4 點分擔的閉式）、法向力＝重量。
- **H. Coulomb 假說**（`coulomb_hypothesis_slider_2ms`，只在 plant 的 2 ms）：同一塊薄板以 0.5 m/s 滑動。**預先登記的假說**：滑動中法向力總和＝重量（±2%）、減速度＝μg（±2%）、四個接觸點不中斷。這個 case 的三個假說**不參與 suite 判定**（`gates_suite = false`），結果作為 plant 接觸模型的量測記錄；它的簿記判準（§3.1）仍參與判定。

不做：接觸下的關節式人形、致動、控制器、恢復係數、任何實體驗證。這些不在本 milestone 的 claim 裡。

### 1.1 設計期觀察（非凍結證據，在**不同於**凍結參數的組態上做，執行前寫下）

設計期以非凍結參數（球 m = 3 kg、r = 0.08 m、h = 0.2 m；薄板 m = 2 kg、半邊 0.08／0.08／0.03 m；速度 0.02–3 m/s）跑了 9 個 pilot，只用來**推導與核對閉式**，不用來調門檻。三個結果決定了本規格的形狀，先寫下來：

1. **自由 6-DoF 薄板一被推就翹起、跳離地面**（pitch 角速度 5–9 rad/s、法向力尖峰 6–10 倍重量），不論 pyramidal 或 elliptic cone、不論厚薄、不論推力是瞬時還是 0.3–0.9 s 的斜坡。機制是摩擦力對質心的俯仰力矩與軟接觸的耦合。因此 S／H 兩族把滑塊限制為**只能平移**（2 個 slide joint），把剛體俯仰耦合排除在本 milestone 之外，並在此揭露。
2. **在 plant 的接觸參數下，滑動摩擦沒有 Coulomb 區間**：切向速度低於約 0.1 m/s 時摩擦未飽和、呈黏滯衰減（速率 ≈ 100 s⁻¹）；高於約 0.2 m/s 時摩擦需求「漏」進法向力（法向力膨脹到 2–10 倍重量、接觸中斷），減速度只有 0.55–0.6 μg。這就是 H 族被設計成**假說量測**而不是 acceptance case 的原因：依設計期觀察，H1–H3 **預期被拒絕**；把它凍結下來是為了讓這個 plant 特性成為可重現的證據而不是一段軼事。
3. **引擎的軟接觸平衡穿透深度不是材料常數**：它隨分擔負載的接觸點數 n_c 縮小（1 點 3.67e-4 m、4 點 1.08e-4 m，皆與 §2.4 的閉式吻合到 ≤ 5e-7）。

---

## 2. 凍結的案例定義

### 2.1 共同（三族都適用）

| 項 | 值 |
|---|---|
| 重力 | `(0, 0, −9.81)` |
| 積分器／cone／condim | `implicitfast`／pyramidal（MuJoCo 預設）／3 |
| 地板 | `<geom name="floor" type="plane" group="2" contype="2" conaffinity="1" friction="1.0 0.005 0.0001" size="60 8 0.1"/>`（與 `model_builder.py` 的 plant 地板宣告一致） |
| 接觸體 geom | `contype="1" conaffinity="2" friction="1.0 0.005 0.0001"`（與 plant 腳板一致） |
| solref／solimp／margin | 未宣告，即 MuJoCo 預設 `(0.02, 1)`／`(0.9, 0.95, 0.001, 0.5, 2)`／`0`；compiled receipt 必須回讀到這些值 |
| solver | 未宣告，即預設 Newton、`tolerance 1e-8`、`iterations 100`、`impratio 1`、`noslip_iterations 0`；compiled receipt 必須回讀到這些值 |
| 致動器 | 無（`nu = 0`）；每步 `qfrc_applied`、`xfrc_applied` 必須為 0 |
| dt | `4 / 2 / 1 ms`（C、S 各三個 case）；H 只在 `2 ms` |
| 每步序列化 | `time_s`、`qpos`、`qvel`、`qacc`、`ncon`、`qfrc_constraint`、`qfrc_applied_abs_max`、`xfrc_applied_abs_max`、每個接觸的 `geom1/geom2/dim/dist/pos/frame(9)/force_contact_frame(6)`（`mj_contactForce`：法向、切向 1、切向 2、三個力矩）。每步 `mj_step` 後呼叫 `mj_forward`，使接觸、約束力與 `qacc` 都對應**該 sample 的狀態**；第 n 個 sample 的約束力即第 n→n+1 步實際使用的力（到 solver tolerance） |

### 2.2 C. drop-and-settle（`drop_and_settle_{4,2,1}ms`）

- 球：`m = 1.0 kg`、`r = 0.05 m`、freejoint，初始球心 `z₀ = r + h`，`h = 0.5 m`，零初速；`duration = 2.0 s`；靜止窗 `t ∈ [1.5, 2.0]`。
- 閉式：
  - 離散自由落體（半隱式 Euler，`implicitfast` 在無速度相依力時與之相同）：`z_n = z₀ − g·dt²·n(n+1)/2`；**觸地步** `n* = min{ n : g·dt²·n(n+1)/2 > h }`（MuJoCo 在 `dist < margin = 0` 時產生接觸）。
  - 連續觸地時刻 `t_c = √(2h/g) = 0.319275 s`。
  - 離散動量恆等式：`Σ_{n<N} F_z,n·dt = m(v_z,N − v_z,0) + m·g·T`（力取第 n 個 sample、乘 dt，左端點和）。
  - 靜止穿透深度（§2.4，`n_c = 1`）。

### 2.3 S. viscous slider（`viscous_slider_{4,2,1}ms`）與 H. Coulomb 假說（`coulomb_hypothesis_slider_2ms`）

- 薄板：`m = 1.0 kg`、半邊 `(0.10, 0.10, 0.02) m`、兩個 `slide` joint（`axis 1 0 0`、`axis 0 0 1`，無阻尼、無 armature），初始底面恰好貼地（`z = 0.02`）、零初速。
- 時程：`[0, 1.0)` 靜置；在 `t_kick = 1.0 s` 的 sample（`n_kick = round(1.0/dt)`）把 `qvel[slide_x]` 設為 `v₀`（狀態設定，不是外力；該 sample 記錄的是設定後、步進前的狀態；`STEP_VELOCITY_UPDATE_IDENTITY` 與 `TANGENTIAL_IMPULSE_IDENTITY` 都從這個 sample 起算，`n_kick−1 → n_kick` 這一步不算積分器更新）；`duration = 2.0 s`。
  靜置要 1.0 s 的原因：n_c = 4 時法向模態的有效阻抗 `d_eff = 4d/(1+3d)` 使阻尼比 `ζ = √(d_eff/d) ≈ 1.04`，慢模態衰減率只有約 37 s⁻¹（單點接觸才是臨界阻尼 52.6 s⁻¹）；設計期量到 0.3 s 時法向力殘差仍有 3e-6（4 ms），1.0 s 後 < 1e-12。
  - S：`v₀ = 0.02 m/s`；H：`v₀ = 0.5 m/s`。
- 窗：踢前靜止窗 `t ∈ [0.7, 1.0)`；滑動窗 = 踢後、從 n_kick 起連續 `v_x ≥ 1e-3·v₀` 的 sample（H 的假說窗改為連續 `v_x ≥ 0.1 m/s`）；踢後靜止窗 `t ∈ [1.5, 2.0]`（H：`[1.7, 2.0]`）。
- 閉式（S）：
  - 未飽和摩擦的黏滯衰減。引擎對每個接觸的每個 pyramid facet 用 `a_ref = −B·v − d·K·pos`，`B = 2/(d_max·t_c)`，`K = 1/(d_max²·t_c²·ζ²)`（`solref = (t_c, ζ)`），正則化 `R = (1−d)/d · diag(A)`，而 `μ = 1`、condim 3 的 facet 的 `diag(A) = 4/m`（設計期由引擎 `efc_R` 回讀，見 §1.1）。對 n_c 個共速接觸、切向無其他力，由 facet 差分的駐點條件得切向加速度 `a_t = −ρ·v_t`，
    **`ρ = B · n_c·d / (n_c·d + 2(1−d))`**，n_c = 4 時 `ρ = B·2d/(1+d)`，`d = d(pen*)` 取靜止穿透的阻抗。
    離散：`v_k = v₀·(1 − dt·ρ)^k`（k = 踢後步數）；連續：`v(t) = v₀·e^{−ρt}`；兩者的最大差 `D(dt) = max_k |(1−dt·ρ)^k − e^{−k·dt·ρ}|` 由凍結常數算出（不是量出來的）。
  - 飽和速度 `v_sat = μg/ρ ≈ 0.098 m/s`；`v₀ = 0.02` 使 cone 利用率 ≈ 0.2。
  - 靜止穿透深度（§2.4，`n_c = 4`）。
- 假說（H，`gates_suite = false`）：H1 滑動窗內每步 `ncon = 4`；H2 滑動窗內 `max |ΣN − mg| / mg ≤ 0.02`；H3 滑動窗內平均減速度對 `μg` 相對誤差 `≤ 0.02`。設計期觀察預期三者皆被拒絕（§1.1 第 2 點）。

### 2.4 引擎軟接觸的閉式平衡穿透

阻抗 `d(pen)` 為 `solimp = (d_min, d_max, width, midpoint, power)` 的 sigmoid：`x = min(pen/width, 1)`；`x ≤ midpoint` 時 `y = x^power / midpoint^(power−1)`，否則 `y = 1 − (1−x)^power / (1−midpoint)^(power−1)`；`d = d_min + (d_max − d_min)·y`。
n_c 個對稱分擔重量的接觸，每個 facet 力 `λ = mg/(4·n_c)`，駐點條件 `R·λ = d·K·pen` 給
**`pen* = (1 − d(pen*))·g / (n_c · d(pen*)² · K)`**（不含質量；定點迭代求解）。
設計期在非凍結參數上核對：n_c = 1 相對差 ≤ 1e-9、n_c = 4 相對差 ≤ 5e-7（4 ms；2 ms、1 ms 更小）。

---

## 3. 凍結的 acceptance criteria（門檻在執行前寫死於 `CONTACT_SUITE_CONTRACT`，不得依首輪結果放寬）

### 3.1 每個 case 共同（簿記；H 也參與判定）

| 判準 | 門檻 | 依據 |
|---|---|---|
| `FINITE_RAW_VALUES` | 所有序列化值有限 | — |
| `TRACE_STEP_COUNT` | 步數 = round(duration／dt) | — |
| `TRACE_TIME_GRID` | max｜t_k − k·dt｜ `≤ 1e-12 s` | 浮點累加 |
| `COMPILED_TIMESTEP_IDENTITY` | compiled timestep = case dt（exact） | — |
| `COMPILED_MODEL_CONTRACT` | integrator IMPLICITFAST、cone PYRAMIDAL、gravity `(0,0,−9.81)`、`nu = 0`、地板與接觸體的 friction／condim／solref／solimp／margin、solver tolerance／iterations／impratio／noslip 與 §2.1 逐項相等、body 質量 = 宣告 | 規格的前提 |
| `EXTERNAL_FORCE_ABSENT` | 每步 `qfrc_applied`、`xfrc_applied` 最大絕對值 = 0 | 無致動、無外力 |
| `CONTACT_FRAME_AXIS_ALIGNED` | 每個接觸 frame 的三個列向量各與某個 `±e_x/±e_y/±e_z` 的差 `≤ 1e-12` | plane 法向 `+z`，pyramid 沿座標軸——閉式的前提 |
| `UNILATERAL_NORMAL_FORCE` | 每個接觸每步法向力 `≥ −1e-12 N` | `V1-R05`：cone 力非負 |
| `FRICTION_CONE_RESPECTED` | 每個接觸每步 `‖f_t‖ / (μ·f_n) ≤ 1 + 1e-9` | `V1-R06`：cone 投影 |
| `STEP_VELOCITY_UPDATE_IDENTITY` | max｜v_{n+1} − v_n − dt·qacc_n｜ `≤ 1e-8` | 半隱式更新；差只來自 warm-start 下 solver 解的 tolerance（1e-8） |
| `CONTACT_FORCE_WORLD_SUM_MATCHES_QFRC_CONSTRAINT` | 每步｜Σ_i frameᵀ·f_i − qfrc_constraint（平移分量）｜ `≤ 1e-9 N` | 同一個 `efc_force` 的兩種線性投影，只差 round-off |

### 3.2 C. drop-and-settle

| 判準 | 門檻 | 依據 |
|---|---|---|
| `TOUCHDOWN_STEP_MATCHES_DISCRETE_FREE_FALL` | 第一個 `ncon > 0` 的 sample 索引 = `n*`（差 = 0 步） | §2.2 離散閉式 exact |
| `TOUCHDOWN_TIME_VS_CONTINUOUS_CLOSED_FORM` | ｜n*·dt − t_c｜ `≤ dt` | `n(n+1) > (t_c/dt)²` 夾出 `n* ∈ (t_c/dt − 1, t_c/dt + 1)` |
| `FREE_FALL_POSITION_DISCRETE_EXACT` | 觸地前每步｜z_n − z_n^closed｜ `≤ 1e-10 m` | round-off（≤ 320 步 × 1e-16） |
| `NORMAL_IMPULSE_MOMENTUM_IDENTITY` | ｜Σ_{n<N} F_z,n dt − m(v_z,N − v_z,0) − mgT｜／(mgT) `≤ 1e-6` | 每步 tolerance 1e-8 × 最多 2,000 步 |
| `NORMAL_IMPULSE_VS_WEIGHT_INTEGRAL` | ｜Σ_{n<N} F_z,n dt − mgT｜／(mgT) `≤ 1e-6` | 上式加靜止末速 `|v_N| ≤ 1e-6 m/s` |
| `REST_NORMAL_FORCE_VS_WEIGHT` | 靜止窗內 max｜ΣN − mg｜／mg `≤ 1e-6` | 平衡殘餘加速度 = solver tolerance；單點接觸臨界阻尼、瞬態 e^{−t·B/2}，觸地後 t ≥ 1.18 s 時 < e^{−60} |
| `REST_VELOCITY` | 靜止窗內 max｜qvel｜ `≤ 1e-6` | 同上 |
| `REST_PENETRATION_VS_CLOSED_FORM` | ｜pen_rest − pen*(n_c = 1)｜／pen* `≤ 1e-5`（pen_rest = 靜止窗末 sample 的 `r − z`） | §2.4；殘餘加速度／(d·K) ~ 1e-11 m，留 3 個量級給 sigmoid 算術與 dt 相依的平衡偏移（設計期 ≤ 5e-7） |
| 報告（非判準） | 最大穿透、法向力峰值、觸地後分離事件數、觸地後 `ncon` 序列 | 供 receipt 描述，不設門檻 |

### 3.3 S. viscous slider

| 判準 | 門檻 | 依據 |
|---|---|---|
| `CONTACT_COUNT_CONSTANT_FOUR` | `t ≥ 0.1 s` 的每個 sample `ncon = 4` | 平移滑塊四角貼地 |
| `PRE_KICK_REST_NORMAL_FORCE_VS_WEIGHT` | 踢前靜止窗 max｜ΣN − mg｜／mg `≤ 1e-6` | 同 §3.2 |
| `PRE_KICK_REST_PENETRATION_VS_CLOSED_FORM` | ｜pen_rest − pen*(n_c = 4)｜／pen* `≤ 1e-5`（踢前最後一個 sample） | §2.4 |
| `VISCOUS_SLIP_VS_DISCRETE_CLOSED_FORM` | 滑動窗內 max｜v_x,k − v₀(1−dt·ρ)^k｜／v₀ `≤ 1e-4` | 半隱式逐步 exact；d 隨穿透變動 ≤ 1e-9；solver tolerance × 步數 ≤ 1e-6；留 100× |
| `VISCOUS_SLIP_VS_CONTINUOUS_CLOSED_FORM` | 滑動窗內 max｜v_x,k − v₀e^{−ρ·k·dt}｜／v₀ `≤ D(dt) + 1e-3` | D(dt) 由凍結常數精確算出（4／2／1 ms ≈ 0.089／0.040／0.019） |
| `VISCOUS_SLIP_RATE_VS_CLOSED_FORM` | 滑動窗內每步速率 `(v_k − v_{k+1})/(dt·v_k)` 的平均對 ρ 相對誤差 `≤ 1e-4` | 同上 |
| `FRICTION_UNSATURATED_IN_SLIP` | 滑動窗內 cone 利用率 max `< 0.5` | `v₀/v_sat ≈ 0.2`；≥ 0.5 即閉式前提不成立 |
| `SLIP_NORMAL_FORCE_VS_WEIGHT` | 滑動窗內 max｜ΣN − mg｜／mg `≤ 1e-6` | 未飽和時法向與切向解耦 |
| `TANGENTIAL_IMPULSE_IDENTITY` | ｜Σ_{n≥n_kick} F_x,n dt − m(v_x,N − v₀)｜／(m·v₀) `≤ 1e-6` | 離散動量恆等式 |
| `POST_REST_NORMAL_FORCE_VS_WEIGHT`、`POST_REST_VELOCITY`、`POST_REST_PENETRATION_VS_CLOSED_FORM` | 與 §3.2 的三個靜止判準相同門檻，用踢後靜止窗 | 同 §3.2 |

### 3.4 H. Coulomb 假說（`gates_suite = false`；§3.1 與下列簿記仍參與判定）

| 判準 | 角色 | 門檻 |
|---|---|---|
| `TANGENTIAL_IMPULSE_IDENTITY`、`POST_REST_*` 三項、`PRE_KICK_REST_*` 兩項 | gate | 同 §3.3 |
| `H1_CONTACT_COUNT_CONSTANT_FOUR_IN_SLIDE` | hypothesis | 假說窗內每步 `ncon = 4` |
| `H2_SLIDE_NORMAL_FORCE_VS_WEIGHT` | hypothesis | 假說窗內 max｜ΣN − mg｜／mg `≤ 0.02` |
| `H3_COULOMB_DECELERATION_VS_MU_G` | hypothesis | 假說窗內平均減速度對 `μg` 相對誤差 `≤ 0.02` |
| 報告（非判準） | 法向力膨脹比 `max ΣN / mg`、失去接觸的 sample 數、滑行距離 | — |

### 3.5 Suite 層（跨 dt）

| 判準 | 門檻 | 依據 |
|---|---|---|
| `REST_PENETRATION_DT_INDEPENDENT` | C 三個 dt 的 pen_rest 極差／中位 `≤ 1e-5`；S 同 | 平衡是穩態 |
| `VISCOUS_CONTINUOUS_ERROR_MONOTONE` | S 的 `VISCOUS_SLIP_VS_CONTINUOUS` 誤差 4 ms > 2 ms > 1 ms | 一階離散差 D(dt) |
| `VISCOUS_CONTINUOUS_OBSERVED_ORDER` | 報告 `log2(e_4/e_2)`、`log2(e_2/e_1)`（`ESTIMATED`，不設門檻） | 預期 ≈ 1 |
| `TOUCHDOWN_ERROR_WITHIN_DT_ALL` | 三個 C case 的 `TOUCHDOWN_TIME_VS_CONTINUOUS` 皆 PASS | 量化到一步，不做單調性 |

### 3.6 Primary 對 replay

`v1_contact_replay.py` 只讀 primary JSON，不匯入 MuJoCo／NumPy／專案模組；自帶凍結常數副本，漂移即 `ReplayValidationError`。它從序列化樣本重算 §3 的每個量（閉式含 sigmoid 定點、ρ、D(dt)），與 primary 的 metric 逐一比對：相對 `≤ 1e-10` 或絕對 `≤ 1e-12`；每個 case 的 criteria `passed` 序列必須逐項相同；假說的 `passed` 也必須相同。非標準 JSON（NaN／Infinity）拒收。

---

## 4. Failure semantics

- 任一 gate 判準 FAIL → 該 case FAIL → suite FAIL。假說（`role = hypothesis`）的結果只記錄，不改變 suite 狀態。
- 序列化缺欄、非有限值、契約常數漂移、case 清單漂移 → replay raise，不產生 PASS/FAIL。
- 首輪 FAIL 若源於重算公式或序列化的缺陷（如 2026-09-22 動態 suite 的 `linvel` 事件），修正碼、保留首輪 artifact 與 sha256、在 receipt 揭露；**門檻不動**。若 FAIL 是引擎行為與閉式不符，那就是量測結果，照實記。

## 5. Claim boundary

PASS 只表示：在凍結門檻內，MuJoCo 對 (a) 單一自由剛體的自由落體、觸地時程、法向衝量與靜止 GRF，(b) 引擎自身軟接觸模型的平衡穿透與未飽和摩擦的黏滯衰減（含 n_c 縮放），與閉式一致。**不**表示接觸物理被實體驗證（`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`）、**不**表示 plant 的摩擦是 Coulomb（H 族的量測結果會說它不是）、**不**涉及關節式人形、致動或控制器、**不**使 V1 PASS。H 族的結果是 plant 接觸模型的特性量測，不是 plant 的能力證據。

## 6. 執行順序

1. 本規格與 `CONTACT_SUITE_CONTRACT`、replay 凍結常數、測試一起 commit 並 push。
2. 之後才跑第一個 case；primary raw artifact 以 exclusive-create 寫到 `backend/run_traces/`，sha256 進 receipt。
3. replay 以 `python -I -S` 跑；receipt 記兩者結果、V1 gate 影響、H 族的量測。

## 7. 執行結果

（執行後追加。）
