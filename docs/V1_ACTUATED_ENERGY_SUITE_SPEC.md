# V1 Actuated Energy Suite — Frozen V1

最後更新：2026-09-22 ｜ ID：`V1-ACTUATED-ENERGY-SUITE-V1` ｜ 任務 #107

狀態：`EXECUTED_2026-09-22_PASS_6_OF_6 / V1 PARTIAL / SIM_ONLY_MUJOCO`（凍結於 `b4b5900`，執行記錄見 [receipt](receipts/V1_ACTUATED_ENERGY_SUITE_RECEIPT_2026-09-22.md)；§2–§5 自凍結起未改）

上游：[VV_PLAN](VV_PLAN.md) `V1-R13`（energy consistency：power balance and physics-step integration，tau／omega／drive-loss trace）、`V1-R11`（numerical convergence）、`V1-R10`（actuator envelope：只覆蓋靜態扭矩上限這一小部分）
｜ 前兩個 V1 milestone：[V1_DYNAMIC_REFERENCE_SUITE_SPEC](V1_DYNAMIC_REFERENCE_SUITE_SPEC.md)（被動、無接觸的能量平衡）、[V1_CONTACT_REFERENCE_SUITE_SPEC](V1_CONTACT_REFERENCE_SUITE_SPEC.md)（單剛體接觸）
｜ 實作：`backend/v1_actuated_energy_suite.py`（primary）、`backend/v1_actuated_energy_replay.py`（stdlib-only replay）、`backend/test_v1_actuated_energy_suite.py`

---

## 1. 本次唯一 milestone

**把 `V1-R13` 的能量帳從被動推到致動**：專案人形在**致動器出力**下，能量平衡 `E(t) − E(0) = W_act − W_damp (+ W_contact)` 可由序列化量以 stdlib 獨立重算，殘差在凍結門檻內、隨 dt 一階收斂。兩個案例族，各 `4／2／1 ms`：

- **A1. actuated open-loop**（`actuated_openloop_{4,2,1}ms`）：軀幹固定、去地板、**保留 12 個 motor**；每個致動器吃一個預先寫死的正弦扭矩命令（開環，不看狀態）。能量帳只有致動功與阻尼功，沒有接觸——這是致動能量帳最乾淨的形式。
- **A2. planted squat**（`planted_squat_{4,2,1}ms`）：完整人形站在 plant 地板上，用 plant 站立控制律的 PD（`BalanceController` 的 `kp/kd` 與 `0.8·qfrc_bias` 重力前饋，狀態回饋）追一條預先寫死的慢速蹲起參考軌跡。能量帳加上**接觸功** `W_contact = ∫ Σ_i f_i·v_i dt`（接觸力對機器人接觸材料點所做的功）。這是 plant 在真實接觸與致動下的能量帳。

**drive loss**：plant 的致動器是 `<motor>`，傳動效率已折進扭矩上限、沒有 drive-loss 模型；因此能量帳**沒有** drive-loss 項，`V1-R13` 列的「drive-loss trace」在這個 plant 上恆為 0，本規格把這件事明寫成 plant 的限制而不是補一個假的項。

不做：行走、外力擾動、恢復係數、任何實體驗證；`V1-R10` 的 torque-speed envelope 只覆蓋「每步致動力在 `forcerange` 內」這一句簿記。

### 1.1 設計期觀察（非凍結參數，執行前寫下）

設計期以非凍結參數（A1 幅度 0.012·上限與另一組頻率；A2 深 0.04 m、0.3 Hz）跑了三個 pilot，只為了選出動作不失控的幅度並核對記帳結構，不用來調門檻：

1. A1 幅度 0.08·上限時四肢整圈翻轉（|q| > 800°），殘差仍一階收斂（2.4／1.2／0.43%）；幅度 0.012 時擺幅 72°、殘差 0.18／0.084／0.041%。凍結取 0.015。
2. A2 若照 live sim 從離地 4 mm 起跳，撞地那一段的接觸功在 4 ms 只解析到 ~0.3 J，殘差 3.7／2.0／0.95%；改成腳底恰好貼地起始、0.3 Hz，殘差 0.77／0.41／0.21%，八個接觸點全程都在、俯仰 ≤ 2.3°。凍結取貼地起始、0.25 Hz、深 0.05 m。
3. **`implicitfast` 有阻尼時不是半隱式 Euler**：`v_{n+1} − v_n − dt·qacc_n` 的最大差 4e-3／1e-3／2.6e-4（一階），因為隱式積分器對速度相依力用 `(M − dt·D)` 修正而 `qacc` 是顯式加速度。這使前兩個 suite 的 `STEP_VELOCITY_UPDATE_IDENTITY` 只在**無速度相依力**時成立；本 suite 把這個差當報告量，不設門檻。

---

## 2. 凍結的案例定義

### 2.1 共同

| 項 | 值 |
|---|---|
| 模型 | `build_mjcf(default_robot(), [], dynamic=True)` 的專案人形（12 個 `<motor>`，gear 1，`ctrlrange = forcerange = ±峰值`；腿關節阻尼 1.0、臂 0.3；armature 為反射慣量） |
| option | `gravity="0 0 -9.81" timestep=dt integrator="implicitfast"`，`<flag energy="enable"/>`（用 regex 逐一替換，每個 pattern 恰好一次） |
| 外力 | 每步 `qfrc_applied`、`xfrc_applied` = 0（致動只經 `ctrl`） |
| dt | `4 / 2 / 1 ms` |
| 每步序列化 | `time_s`、`qpos`、`qvel`、`qacc`、`ctrl`、`actuator_force`、`qfrc_actuator`、`qfrc_bias`、`qfrc_constraint`、`energy_engine`（`mj_energyPos/Vel`）、`ncon`、每個接觸（`geom1/geom2/body1/body2/dim/dist/pos/frame/force_contact_frame`）、每個 body（`xpos/xipos/ximat/angvel_world/linvel_com_world`）、外力上界；A2 另記 `q_ref`、`qd_ref`。每步 `mj_step` 後 `mj_forward` 再記錄，使所有量對應該 sample 的狀態 |

### 2.2 A1. actuated open-loop（`actuated_openloop_{4,2,1}ms`）

- 變換（各恰好一次）：去 `<freejoint name="root"/>`、去 `<geom name="floor" …/>`、`trunk` 固定於 `pos="0 0 1.6"`、option 替換；**不**去 `<actuator>`。
- 初始：全部關節角 0、零速度。
- 命令（`JOINT_ORDER` 順序）：`ctrl_j(t) = 0.015·F_j·sin(2π·f_j·t + 0.4·j)`，`F_j` = 該致動器 `forcerange` 上限，`f = (0.55, 0.75, 0.95, 1.15, 0.65, 0.85, 1.05, 1.25, 0.60, 0.80, 1.00, 1.20) Hz`；在第 n 個 sample 的狀態設定、用於 n→n+1 步。`duration = 3.0 s`。
- 能量帳：`E = KE + PE`（引擎；KE 含 armature）；致動力在步內保持常數（MuJoCo 的 `ctrl` 語義），故 `W_act,n+1 = W_act,n + τ_n·½(q̇_n + q̇_{n+1})·dt`（力取步首、速度取梯形，`τ = qfrc_actuator`）；`W_damp(t) = ∫ Σ_j d_j·q̇_j² dt` 對 sample 取梯形；殘差 `r(t) = E − E₀ − W_act + W_damp`；`E_scale = max(max_t|W_act|, max E − min E, 1 J)`。
- 報告（不設門檻）：離散致動功 `Σ_n τ_n·(q_{n+1} − q_n)` 的殘差；`max|v_{n+1} − v_n − dt·qacc_n|`（隱式修正量）。

### 2.3 A2. planted squat（`planted_squat_{4,2,1}ms`）

- 模型不去地板、不去 freejoint；只替換 option。
- 初始：`qpos[0:3] = (0, 0, pelvis_height(cfg, 0.10))`（腳底恰好貼地，不像 live sim 的 +4 mm）、四元數 `(1,0,0,0)`、關節 = `BalanceController._stand_pose()`、零速度。
- 參考：`Δz(t) = 0`（`t < 1.0 s`），之後 `Δz(t) = 0.05·½(1 − cos(2π·0.25·(t − 1.0)))` m（一次完整蹲起，4 s）；腿部 `(hp, kn, ap) = GaitEngine(cfg, GaitParams(crouch=0.10), []).leg_ik((0, hw, z_nom − Δz), (0, hw, ankle_h), 0)`，`hip_roll = 0`、`shoulder = 0.05`、`elbow = 0.35`（與站立姿勢相同）；`q̇_ref` 為後向差分（第 0 步為 0）。`duration = 5.0 s`。
- 控制律（plant 的站立律，狀態回饋）：`ctrl = kp·(q_ref − q) + kd·(q̇_ref − q̇) + 0.8·qfrc_bias[6:]`，`kp_j = clip(12·rated_j, 60, 900)`、`kd_j = 0.06·kp_j`（`BalanceController`）；MuJoCo 以 `ctrlrange` 截斷。
- 能量帳：加 `W_contact(t) = ∫ Σ_i f_i·v_i dt`，`f_i` = 接觸 i 作用於**機器人**的世界力（`frameᵀ·mj_contactForce`，地板為 geom1 時取正、否則取負），`v_i = v_com,b + ω_b × (p_i − xipos_b)`，b 為該接觸的機器人 body；殘差 `r = E − E₀ − W_act + W_damp − W_contact`。軟接觸的彈性儲能不在 `E` 裡（量級 `f·pen/2 ≈ 0.01 J`，在門檻內）。
- 前提 gate：`NO_FALL`（每步骨盆 `z ≥ 0.75·z_nom`、|pitch|、|roll| `≤ 0.2 rad`）、`CONTACT_COUNT_PLANTED`（`t ≥ 0.5 s` 每步 `ncon = 8`：兩腳板各 4 角）。

---

## 3. 凍結的 acceptance criteria（門檻在執行前寫死於 `ACTUATED_SUITE_CONTRACT`，不得依首輪結果放寬）

### 3.1 每個 case 共同

| 判準 | 門檻 | 依據 |
|---|---|---|
| `FINITE_RAW_VALUES`、`TRACE_STEP_COUNT`、`TRACE_TIME_GRID`（`≤ 1e-12 s`）、`COMPILED_TIMESTEP_IDENTITY` | 同前兩個 suite | — |
| `COMPILED_MODEL_CONTRACT` | integrator IMPLICITFAST、gravity、energy flag 開、`nu = 12`、gear 全為 1、`ctrlrange = forcerange`、關節阻尼／armature 與 MJCF 一致、A1 無 floor 無 freejoint、A2 有兩者 | 規格前提 |
| `EXTERNAL_FORCE_ABSENT` | `qfrc_applied`、`xfrc_applied` 最大絕對值 = 0 | 致動只經 ctrl |
| `ACTUATOR_FORCE_IS_CLIPPED_CTRL` | 每步 max｜actuator_force − clip(ctrl, forcerange)｜ `≤ 1e-12` | `<motor>` 語義 |
| `QFRC_ACTUATOR_MATCHES_GEAR_FORCE` | 每步 max｜qfrc_actuator − Σ gear·actuator_force 投影｜ `≤ 1e-12` | 同一線性映射 |
| `ENGINE_KINETIC_ENERGY_AGREEMENT`、`ENGINE_POTENTIAL_ENERGY_AGREEMENT` | 相對 `≤ 1e-8`（以 E_scale 為分母下界） | 與動態 suite 相同的重算 |
| `ACTUATOR_WORK_SCALE_MIN` | `max_t｜W_act｜ ≥ 1 J` | 帳要非平凡 |
| `ENERGY_BALANCE_RESIDUAL_RELATIVE_MAX` | A1：`≤ 0.02 / 0.01 / 0.005`；A2：`≤ 0.05 / 0.025 / 0.0125`（4／2／1 ms） | 梯形法對速度相依項是 O(dt)；被動 articulated 前例 4 ms 為 0.70%；A2 多接觸功的梯形誤差（接觸時間常數 20 ms）與 PD 起始瞬態，取被動前例的門檻 |

### 3.2 A1 專屬

| 判準 | 門檻 | 依據 |
|---|---|---|
| `CTRL_MATCHES_PRESCRIBED` | 每步 max｜ctrl_j − 0.015·F_j·sin(2π f_j t + 0.4 j)｜ `≤ 1e-12·F_j` | harness 用的就是規格的式子 |
| `NO_CONTACT` | 每步 `ncon = 0` | 去地板、自碰撞關 |

### 3.3 A2 專屬

| 判準 | 門檻 | 依據 |
|---|---|---|
| `CTRL_MATCHES_PD_LAW` | 每步 max｜ctrl − [kp(q_ref − q) + kd(q̇_ref − q̇) + 0.8·qfrc_bias]｜ `≤ 1e-9` | 記錄的 `q_ref/q̇_ref/qfrc_bias` 重算 |
| `QD_REF_IS_BACKWARD_DIFFERENCE` | 每步 max｜q̇_ref,n − (q_ref,n − q_ref,n−1)/dt｜ `≤ 1e-9` | 規格定義 |
| `NO_FALL` | 每步 `z ≥ 0.75·z_nom`、|pitch|、|roll| `≤ 0.2 rad` | 前提 |
| `CONTACT_COUNT_PLANTED` | `t ≥ 0.5 s` 每步 `ncon = 8` | 前提；pilot 全程 8 |
| `UNILATERAL_NORMAL_FORCE`（`≥ −1e-12 N`）、`FRICTION_CONE_RESPECTED`（`≤ 1 + 1e-9`）、`CONTACT_FRAME_AXIS_ALIGNED`（`≤ 1e-12`） | 同接觸 suite | `V1-R05/R06` 簿記 |
| `CONTACT_FORCE_WORLD_SUM_MATCHES_QFRC_CONSTRAINT` | 每步｜Σ_i f_i − qfrc_constraint[0:3]｜ `≤ 1e-9 N` | freejoint 平移 dof 對齊世界座標 |

### 3.4 Suite 層

| 判準 | 門檻 |
|---|---|
| `OPENLOOP_RESIDUAL_TIMESTEP_MONOTONE`、`SQUAT_RESIDUAL_TIMESTEP_MONOTONE` | 相對殘差 4 ms > 2 ms > 1 ms |
| `*_OBSERVED_ORDER` | 報告 `log2(e_4/e_2)`、`log2(e_2/e_1)`（`ESTIMATED`） |
| 報告 | 隱式修正量、離散致動功殘差、`W_contact` 三個 dt |

### 3.5 Primary 對 replay

stdlib-only replay 重算全部 metric（能量由 body 運動學與主慣量重算、三種功的梯形、接觸點速度、PD 律、正弦命令）與 primary 比對：相對 `≤ 1e-10` 或絕對 `≤ 1e-12`；criteria `passed` 序列逐項相同；契約常數漂移、缺欄、非有限值、非標準 JSON → `ReplayValidationError`。

## 4. Failure semantics

同前兩個 suite：任一判準 FAIL → case FAIL → suite FAIL；結構問題 raise；首輪若 FAIL 於記帳公式缺陷，修公式、保留 artifact、揭露、門檻不動；若是引擎行為，照實記。

## 5. Claim boundary

PASS 只表示：在凍結門檻內，MuJoCo 對專案人形在致動（開環正弦；plant 站立 PD 追慢速蹲起）下的能量帳，可由序列化的 `τ`、`ω`、阻尼、接觸力與接觸點速度獨立重算並隨 dt 一階收斂。**不**是致動器模型的實體驗證、**不**含 drive loss（plant 沒有）、**不**含行走、**不**使 V1 PASS；`V1-R10` 的 torque-speed envelope 仍缺。

## 6. 執行順序

1. 本規格、`ACTUATED_SUITE_CONTRACT`、replay 凍結常數與測試一起 commit 並 push。
2. 之後才跑凍結 case；raw artifact exclusive-create 到 `backend/run_traces/`，sha256 進 receipt。
3. replay 以 `python -I -S` 跑；receipt 記結果與 `V1-R13` 的狀態變化。

## 7. 執行結果（2026-09-22，寫於執行之後）

- 凍結 commit `b4b5900`（push 後、工作樹乾淨）上執行一次：**6/6 PASS、suite 2/2**；artifact `backend/run_traces/v1-actuated-energy-20260922T102345.json`（`sha256:fbffa6d6…a7b4`，139,121,014 bytes）；stdlib replay PASS、144 個 metric 相符。門檻一個都沒動。
- 殘差／E_scale：A1 `0.18／0.084／0.041%`（order 1.07／1.04）、A2 `0.23／0.13／0.069%`（order 0.81／0.91）；隱式修正量 `4.8e-3／1.2e-3／3.1e-4`（A1）與 `1.1e-2／2.8e-3／7.2e-4`（A2），與 §1.1 第 3 點一致。
- 量測表、對 V1 gate 的影響與非宣稱見 [receipt](receipts/V1_ACTUATED_ENERGY_SUITE_RECEIPT_2026-09-22.md)。
