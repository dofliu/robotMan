# V1 actuated energy suite implementation receipt（2026-09-22）

ID：`V1-ACTUATED-ENERGY-SUITE-V1` ｜ 任務 #107 ｜ 規格：[V1_ACTUATED_ENERGY_SUITE_SPEC](../V1_ACTUATED_ENERGY_SUITE_SPEC.md)
｜ 性質：**實作 receipt 與量測**；`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`；V1 gate 仍 `PARTIAL_IMPLEMENTED_NOT_PASS`

---

## 0. 一句話

**6/6 case PASS（首輪即過，門檻未動），stdlib 獨立重算 144 個 metric 逐一相符：專案人形在致動下的能量帳——開環正弦扭矩（無接觸）與 plant 站立 PD 追慢速蹲起（含接觸功）——殘差 `0.18／0.084／0.041%` 與 `0.23／0.13／0.069%`（4／2／1 ms），一階收斂。**
`V1-R13` 的能量一致性從「被動」推到「致動＋接觸」；plant 沒有 drive-loss 模型，帳裡也就沒有這一項，這點明寫為 plant 的限制。

---

## 1. Frozen milestone 與 claim boundary

- Milestone：`V1-ACTUATED-ENERGY-SUITE-V1`——**A1. actuated open-loop**（軀幹固定、去地板、保留 12 個 motor、預先寫死的正弦扭矩）與 **A2. planted squat**（完整人形站在 plant 地板、plant 的 `BalanceController` 站立律 PD 追一次 5 cm／4 s 的蹲起），各 `4／2／1 ms`。
- 凍結：規格、`ACTUATED_SUITE_CONTRACT`、replay 凍結常數與測試於 **`b4b5900`** commit 並 push，**在任何凍結 case 執行之前**；門檻由能量帳的一階離散結構推得（規格 §3.1 依據欄），執行後未動。設計期 pilot 全在不同幅度／頻率／蹲深上做，只為選出不失控的動作與核對記帳結構（規格 §1.1）。
- Claim boundary：PASS 只表示 MuJoCo 對專案人形在這兩種致動情境下的能量帳，可由序列化的 `τ`、`ω`、阻尼、接觸力與接觸點速度獨立重算、在凍結門檻內、隨 dt 一階收斂。**不**是致動器模型的實體驗證、**不**含 drive loss（plant 沒有）、**不**含行走或撞擊、**不**使 V1 PASS。

---

## 2. Implementation inventory

| 檔 | 內容 |
|---|---|
| `backend/v1_actuated_energy_suite.py` | primary：兩個 MJCF 變換（A1 四個、A2 一個，各恰好一次）、`SquatReference`（專案解析 IK 的蹲起參考）、plant 站立律 PD、逐步序列化（`qpos/qvel/qacc/ctrl/actuator_force/qfrc_actuator/qfrc_bias/qfrc_constraint`、引擎能量、接觸含 body id、每個 body 的質心速度／角速度、A2 的 `q_ref/qd_ref`）、NumPy 能量帳（held-torque 致動功、梯形阻尼功與接觸功）、判準、suite 層、CLI |
| `backend/v1_actuated_energy_replay.py` | stdlib-only replay：契約漂移驗證（含 case 清單、dt、殘差門檻、controller receipt）、純 Python 重算全部 metric（能量由 body 運動學與主慣量、三種功、接觸點速度、PD 律、正弦命令、四元數姿態）、primary/replay 比對、非標準 JSON 拒收 |
| `backend/test_v1_actuated_energy_suite.py` | 22 項：凍結契約與 replay 常數一致、正弦命令在 `forcerange` 內且與 replay 相同、蹲深函數端點、MJCF 變換恰好一次且保留致動器、蹲起參考在靜置段等於 plant 站立姿勢與增益公式、primary PASS 與判準清單、A1／A2 物理合理（含 `implicitfast` 隱式修正非零）、replay 相符、replay 無 MuJoCo／NumPy／專案匯入、扭矩與接觸力篡改保留 FAIL、九種結構問題 raise、非標準 JSON、summary 去 raw |
| `docs/V1_ACTUATED_ENERGY_SUITE_SPEC.md` | 凍結規格 |

---

## 3. 執行記錄：一次，PASS

| 次 | 源碼 | Artifact | 結果 |
|---|---|---|---|
| 1 | `b4b5900`（凍結 commit，執行前 `git status` 乾淨） | `backend/run_traces/v1-actuated-energy-20260922T102345.json`，`sha256:fbffa6d669e9ba592f395ff5662c7a0c4aa7c9695d14a9e5ccca34849173a7b4`，139,121,014 bytes | **PASS 6/6**，suite 2/2 |

同一 commit 上 `pytest backend/test_v1_actuated_energy_suite.py`：22 passed（61.3 s）。MuJoCo `3.12.0`；契約 canonical-JSON `sha256:1daba7d9cb248733a1bcc6396b812a9e2a5986129b5284e492760b955e685611`。Artifact 大（每步 11 個 body 與 8 個接觸的運動學），保留在 gitignored 的 `backend/run_traces/`。

---

## 4. 量測結果

### 4.1 A1. actuated open-loop（軀幹固定於 1.6 m、12 個 motor、幅度 0.015·forcerange、3 s）

E_scale = max|W_act| ≈ 91 J；關節擺幅最大 77°，命令扭矩最大 8.1 N·m。

| dt | W_act (J) | W_damp (J) | ΔE (J) | 殘差 max (J) | 殘差／E_scale | 門檻 | 引擎 KE／PE 一致 | 隱式修正 max | 離散致動功殘差 |
|---|---|---|---|---|---|---|---|---|---|
| 4 ms | 91.17 | 73.66 | 17.59 | 0.162 | `1.77e-3` | `2e-2` | `6.4e-16`／`4.4e-16` | `4.8e-3` | `6.9e-3` |
| 2 ms | 91.43 | 73.87 | 17.60 | 0.077 | `8.44e-4` | `1e-2` | `9.0e-16`／`4.4e-16` | `1.2e-3` | `3.5e-3` |
| 1 ms | 91.56 | 73.97 | 17.61 | 0.038 | `4.12e-4` | `5e-3` | `7.8e-16`／`4.4e-16` | `3.1e-4` | `1.7e-3` |

- 殘差 observed order **1.07／1.04**（`ESTIMATED`）；三個 dt 單調遞減。
- `actuator_force = clip(ctrl, forcerange)`、`qfrc_actuator = gear·actuator_force` 每步差 `0`；命令與規格式子差 `0`；`ncon = 0`。
- **`implicitfast` 有阻尼時不是半隱式 Euler**：`|v_{n+1} − v_n − dt·qacc_n|` 最大 `4.8e-3／1.2e-3／3.1e-4`（一階；規格 §1.1 第 3 點）。這說明前兩個 suite 的 `STEP_VELOCITY_UPDATE_IDENTITY` 之所以到 1e-10，是因為那些案例沒有速度相依力。
- 用「力取步首、位置差」的離散致動功（`Σ τ_n·Δq_n`）算出的殘差（0.69／0.35／0.17%）比 held-torque 梯形（0.18／0.084／0.041%）大：對 `implicitfast` 的位置更新，速度梯形是比較準的功估計。兩者都只是報告。

### 4.2 A2. planted squat（完整人形、plant 地板、plant 站立 PD、5 cm／0.25 Hz 蹲起、5 s）

E_scale = 能量極差 24.06 J（蹲下時 PE 降 ~24 J）；`kp` 腿 900／肩 121.8／肘 60，`kd = 0.06·kp`；骨盆最低 0.647 m（`z_nom` 0.710 的 91%）；軀幹傾角最大 2.26°；八個接觸點 `t ≥ 0.5 s` 後每步都在。

| dt | W_act 終值 (J) | W_damp (J) | W_contact (J) | ΔE (J) | 殘差 max (J) | 殘差／E_scale | 門檻 | cone 利用率 max | 法向力 min (N) | 世界力對 `qfrc_constraint` |
|---|---|---|---|---|---|---|---|---|---|---|
| 4 ms | −2.82 | 0.260 | −0.168 | −3.240 | 0.055 | `2.28e-3` | `5e-2` | 0.279 | 22.8 | `3.4e-13` |
| 2 ms | −2.79 | 0.260 | −0.190 | −3.239 | 0.031 | `1.29e-3` | `2.5e-2` | 0.300 | 17.6 | `4.0e-13` |
| 1 ms | −2.78 | 0.259 | −0.203 | −3.239 | 0.017 | `6.86e-4` | `1.25e-2` | 0.315 | 15.1 | `3.4e-13` |

- 殘差 observed order **0.81／0.91**（`ESTIMATED`）；單調遞減。接觸功為負（軟接觸只耗能）且隨 dt 收斂到約 −0.21 J；致動器一個蹲起週期淨吸收 2.8 J（下蹲時制動、起身時出力，PE 回到起點附近、阻尼與接觸耗掉 0.46 J，其餘是終態的 KE／PE 差）。
- `ctrl` 與記錄的 `kp(q_ref − q) + kd(q̇_ref − q̇) + 0.8·qfrc_bias` 逐步差 `0`；`q̇_ref` 與後向差分差 `0`；`q_ref(0)` = plant 站立姿勢。
- 接觸簿記：法向力每步 ≥ 15 N（無單邊違反）、cone 利用率 ≤ 0.32、frame 軸對齊差 `0`、接觸力世界和對 freejoint 平移 `qfrc_constraint` 差 ≤ 4e-13 N。
- 隱式修正量 `1.1e-2／2.8e-3／7.2e-4`（腿關節阻尼 1.0 與 PD 皆是速度相依力）。

### 4.3 Replay

`python -I -S backend/v1_actuated_energy_replay.py <artifact>` → **PASS**；`all_agree = true`，144 個 metric（20×3＋28×3）逐一相符、最大相對差 `0.0`；criteria `passed` 序列逐項相同；`primary_file_sha256` 與 §3 相同。

---

## 5. 對 V1 gate 的影響

| VV_PLAN 列 | 前 | 後 |
|---|---|---|
| `V1-R13` energy consistency | PARTIAL：只有被動 articulated 的能量帳；致動下的 tau／omega／drive-loss 帳缺 | PARTIAL：**致動能量帳完成**——開環正弦（無接觸）殘差 0.18／0.084／0.041%、plant 站立 PD 蹲起（含接觸功）0.23／0.13／0.069%，皆由 `τ`／`ω`／阻尼／接觸力序列獨立重算；**drive loss 在此 plant 恆為 0（無模型），明列為限制**；仍缺行走／撞擊情境的能量帳與 `implicitfast` 的步進恆等式（目前只作報告量） |
| `V1-R11` numerical convergence | PARTIAL | PARTIAL：**加**兩個致動能量殘差的 4/2/1 ms 收斂研究（order 1.07／1.04、0.81／0.91）；solver-tolerance 與 finite-difference 仍缺 |
| `V1-R10` actuator torque-speed feasibility | BLOCKED | BLOCKED：本 suite 只把「每步 `actuator_force = clip(ctrl, forcerange)`」記為簿記事實（差 0）；torque-speed envelope（D1+）仍無來源，狀態不變 |

V1 gate 狀態不變：`PARTIAL_IMPLEMENTED_NOT_PASS`。PASS 還缺：關節式人形的 dynamic contact 與步態排程、solver-tolerance／finite-difference、joint limits（`V1-R09`）、actuator envelope（`V1-R10`）、行走情境的能量帳；以及接觸 suite 揭示的 plant 滑動摩擦非 Coulomb 的處置。

---

## 6. 不能拿這份 receipt 說什麼

- 不能說致動器被實體驗證了——`<motor>` 是理想扭矩源，`forcerange` 是唯一的限制，沒有 torque-speed curve、沒有 drive loss。
- 不能說行走時的能量帳成立——A2 是雙腳貼地、無滑動、無撞擊的慢動作。
- 「引擎能量一致到 1e-16」是同一引擎的記帳一致；獨立的是功－能平衡本身。
- 隱式修正量說的是 `implicitfast` 與半隱式 Euler 的差，不是錯誤；它使「物理步進恆等式」在有阻尼時不能用 `qacc` 一句話寫出，這點留待後續。

---

## 7. 重現

```bash
python3 -X utf8 -m pytest backend/test_v1_actuated_energy_suite.py -p no:cacheprovider -q     # 22 項，約 60 s
python3 -X utf8 backend/v1_actuated_energy_suite.py --raw-output backend/run_traces/v1-actuated-energy-<ts>.json
python3 -I -S backend/v1_actuated_energy_replay.py backend/run_traces/v1-actuated-energy-<ts>.json
```
