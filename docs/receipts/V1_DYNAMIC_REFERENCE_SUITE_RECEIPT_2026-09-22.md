# V1 dynamic reference suite implementation receipt（2026-09-22）

ID：`V1-DYNAMIC-REFERENCE-SUITE-V1` ｜ 任務 #105 ｜ 規格：[V1_DYNAMIC_REFERENCE_SUITE_SPEC](../V1_DYNAMIC_REFERENCE_SUITE_SPEC.md)
｜ 性質：**實作 receipt 與量測**；`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`；V1 gate 仍 `PARTIAL_IMPLEMENTED_NOT_PASS`

---

## 0. 一句話

**6/6 case PASS，stdlib 獨立重算 84 個 metric 逐一相符；第一次執行 FAIL，原因是重算公式的缺陷（不是門檻、不是物理），修公式後在乾淨的源碼樹重跑。**
單擺週期對閉式解誤差 `6.5e-6／1.6e-6／4.1e-7`（4／2／1 ms，二階收斂）；人形被動擺動的能量平衡殘差
`0.70%／0.35%／0.17%`（一階收斂），門檻 `5%／2.5%／1.25%`。

---

## 1. Frozen milestone 與 claim boundary

- Milestone：`V1-DYNAMIC-REFERENCE-SUITE-V1`——兩個無接觸、無控制器、無致動的動態參考案例族，各 `4／2／1 ms`：
  **P. known pendulum**（閉式週期與能量）與 **A. articulated passive swing**（專案人形、軀幹固定、去地板、去致動器；能量平衡含關節阻尼功；球／盒 body 的閉式慣量）。
- 凍結：規格與門檻於 **`a65bef2`** commit 並 push，**在任何 case 執行之前**；門檻由積分器的離散誤差分析推得（規格 §3 的「依據」欄），首輪後未動。
- Claim boundary：引擎對有閉式解的動態系統、以及專案 articulated plant 在無接觸／無致動下的能量記帳，在凍結門檻內；**不**是接觸物理、致動器、控制器、任何實體能力的證據，也**不**使 V1 PASS。

---

## 2. Implementation inventory

| 檔 | 內容 |
|---|---|
| `backend/v1_dynamic_reference_suite.py` | primary：MJCF 建構（單擺；人形的四個宣告變換）、逐步序列化（`qpos/qvel`、引擎能量、`ncon`、外力、每個 body 的 `xpos/xipos/ximat`、世界角速度與**質心**線速度）、NumPy 重算、判準、suite 層收斂判準、CLI（exclusive-create 寫 raw artifact） |
| `backend/v1_dynamic_replay.py` | stdlib-only replay：schema／contract 漂移驗證（自帶凍結常數副本）、純 Python 重算全部 metric（AGM 橢圓積分、能量、梯形阻尼功、Jacobi 特徵值）、primary/replay 比對（相對 `1e-10`／絕對 `1e-12`）、fail-closed |
| `backend/test_v1_dynamic_reference_suite.py` | 20 項：凍結契約一致、橢圓積分已知值、四個變換恰好各一次且缺一即失敗、閉式慣量教科書值、primary PASS、replay 相符且 PASS、replay 無 MuJoCo／NumPy／專案匯入、有限值篡改保留 FAIL、六種結構問題 raise、非標準 JSON 拒收 |
| `docs/V1_DYNAMIC_REFERENCE_SUITE_SPEC.md` | 凍結規格 |

Primary 用 NumPy、replay 用純 Python：兩者不是同一段程式跑兩次；一致到 `1e-10` 才算 agreement。

---

## 3. 執行記錄：兩次，第一次 FAIL

| 次 | 源碼 | Artifact | 結果 |
|---|---|---|---|
| 1 | `a65bef2`（凍結 commit，工作樹乾淨） | `backend/run_traces/v1-dynamic-reference-20260922T074346.json`，`sha256:476fbd251d0d130910f2a1e0ef3e0110aef6355d63eeb24fb33912a06a04f99b`，31,692,999 bytes | **FAIL**：三個 articulated case 的 `ENGINE_KINETIC_ENERGY_AGREEMENT` 讀到 **1.2**（相對差 120%），連帶 `ENERGY_BALANCE_RESIDUAL_RELATIVE_MAX` 0.85 與 suite 的 `ARTICULATED_RESIDUAL_TIMESTEP_MONOTONE`；三個 pendulum case PASS |
| 2 | `4a96f54`（修正 commit，執行前後 `git status` 皆乾淨） | `backend/run_traces/v1-dynamic-reference-20260922T074732.json`，`sha256:77b9f1e295e282f8c0cbc297952538b28c4814a8f3afe57d097cbccee2f66163`，31,966,185 bytes | **PASS 6/6**，suite 6/6 |

### 3.1 第一次為什麼 FAIL——重算公式的缺陷，由設計來抓它的判準抓到

MuJoCo `mj_objectVelocity(mjOBJ_BODY, …, flg_local=0)` 回傳的 6D 速度以 body 的**慣性框（質心 `xipos`）**為參考點，
線速度**已經是質心速度**。primary 與 replay 都把它當成 body frame 原點的速度、再加一次 `ω × (xipos − xpos)`，動能因此重複計算。
單擺三個 case 沒暴露這個錯，因為單擺 body 的原點就是固定的樞軸（原點速度為零，兩種讀法一致）。
`ENGINE_KINETIC_ENERGY_AGREEMENT` 就是為了抓「重算與引擎不一致」而設的判準；它在第一次執行就把問題攤開。

修法（`4a96f54`）：拿掉 `ω × r` 項、欄位改名 `linvel_com_world`；以 `mj_energyVel` 對照同一狀態，相對差 `0.0`。
**門檻一個都沒動**；第一次的 artifact 保留在磁碟、sha256 記在上表。

---

## 4. 量測結果（第 2 次執行）

### 4.1 P. known pendulum（m = 2 kg、r = 0.05 m、L = 0.5 m、θ₀ = 60°、6 s）

閉式週期 T = 4·√(I/(m g L))·K(sin 30°) = **1.5253538620 s**（I = 0.502 kg·m²；K = 1.6857503548）。

| dt | T_meas (s) | 相對誤差 | 門檻 | 能量振盪 | 門檻 | 長期漂移 | 週期數 | 引擎 KE／PE 一致 |
|---|---|---|---|---|---|---|---|---|
| 4 ms | 1.5253439258 | `6.514e-6` | `1e-3` | `8.352e-3` | `2e-2` | `9.0e-8` | 3 | `7.5e-16`／`2.8e-16` |
| 2 ms | 1.5253513779 | `1.629e-6` | `1e-3` | `4.161e-3` | `1e-2` | `1.2e-8` | 3 | `7.5e-16`／`2.8e-16` |
| 1 ms | 1.5253532410 | `4.071e-7` | `1e-3` | `2.077e-3` | `5e-3` | `1.3e-9` | 3 | `7.5e-16`／`2.8e-16` |

- 週期誤差 observed order **1.99994**（`ESTIMATED`）：與規格 §3 推的半隱式 Euler 頻率誤差 (ωΔt)²/24 完全一致（預測 1.3e-5／3.2e-6／8e-7 量級）。
- 能量振盪 0.84%／0.42%／0.21%：與規格預測 0.81%／0.41%／0.20% 相符（一階，來源是 shadow Hamiltonian 的 O(Δt) 項）。長期漂移 ~1e-8：辛積分器的特徵。
- compiled 慣量對 (2/5)·m·r² 相對誤差 `0`；`body_ipos` 對 `(0,0,−0.5)` 誤差 `0`。
- Suite：`PENDULUM_PERIOD_TIMESTEP_FINE_DELTA` `1.22e-6`（≤ 5e-4）、`MONOTONE` PASS。

### 4.2 A. articulated passive swing（人形、軀幹固定於 z = 1.6 m、12 個被動關節、3 s）

E₀ = 793.258 J（PE 以絕對 z 計），E_scale = E₀ − min PE = **27.651 J**。

| dt | KE max (J) | W_damp(3 s) (J) | 殘差 max (J) | 殘差／E_scale | 門檻 | 引擎 KE／PE 一致 |
|---|---|---|---|---|---|---|
| 4 ms | 19.334 | 20.540 | 0.1923 | `6.956e-3` | `5e-2` | `7.0e-16`／`2.9e-16` |
| 2 ms | 19.313 | 20.529 | 0.0966 | `3.492e-3` | `2.5e-2` | `5.2e-16`／`4.3e-16` |
| 1 ms | 19.303 | 20.525 | 0.0484 | `1.750e-3` | `1.25e-2` | `8.7e-16`／`4.3e-16` |

- 殘差 observed order **0.9914**（`ESTIMATED`）：一階，與「梯形法對隱式阻尼離散化」的預期一致；3 s 內阻尼耗掉 74% 的能量尺度。
- 引擎能量與獨立重算（body 質心速度、慣性框角速度、主慣量、armature）一致到 `1e-15`——這證明的是**記帳一致**，不是獨立物理驗證。
- 閉式慣量：`trunk`、`foot_l`、`foot_r`（只含球與盒）的主慣量相對誤差 `6.2e-16`、質心 `6.9e-18 m`；全部 11 個 body 的質量與 MJCF geom 質量總和誤差 `0`。含 capsule 的 body 只比對質量（規格明列）。
- 每步 `ncon = 0`、外力 `0`、`nu = 0`、時間格 `≤ 1e-12 s`。

### 4.3 Replay

`python -I -S backend/v1_dynamic_replay.py <artifact>` → **PASS**；`all_agree = true`，84 個 metric 比對、最大相對差 `0.0`；
每個 case 的 criteria `passed` 序列與 primary 逐項相同；`primary_file_sha256` 與上表 artifact 相同。

---

## 5. 對 V1 gate 的影響

| VV_PLAN 列 | 前 | 後 |
|---|---|---|
| `V1-R11` numerical convergence | PARTIAL：只有 passive one-body GRF 的 4/2/1 ms；observed order null | PARTIAL：**加** known pendulum 週期（order 2.0）與 articulated 被動能量殘差（order 0.99）兩個動態收斂研究；solver-tolerance、finite-difference、接觸下的收斂仍缺 |
| `V1-R13` energy consistency | **BLOCKED** | **PARTIAL**：被動 articulated 的能量平衡（含阻尼功）可由序列化量獨立重算，殘差 0.70／0.35／0.17%；**致動下的 tau／omega／drive-loss 帳仍缺** |
| `V1-R14` analytical reference cases | PARTIAL：known pendulum 與 articulated 仍缺 | PARTIAL：**known pendulum 完成、articulated（被動、無接觸）完成**；dynamic contact 仍缺 |

V1 gate 狀態不變：`PARTIAL_IMPLEMENTED_NOT_PASS`。PASS 還缺：dynamic contact（接觸下的 unilateral／friction／CoP／schedule）、solver-tolerance 與 finite-difference 研究、joint limits（`V1-R09`）、actuator envelope（`V1-R10`）、致動下的能量帳。

---

## 6. 不能拿這份 receipt 說什麼

- 不能說 plant 的接觸物理被驗證了——兩個案例族都刻意無接觸。
- 不能說控制器或致動器被驗證了——`nu = 0`。
- 「引擎能量一致到 1e-15」是同一引擎的記帳一致；獨立的是守恆檢查與閉式解（週期、球／盒慣量）。
- 第一次執行 FAIL 是重算公式的缺陷；它**不**是關於 MuJoCo 的量測結果。

---

## 7. 重現

```bash
python3 -X utf8 -m pytest backend/test_v1_dynamic_reference_suite.py -p no:cacheprovider -q     # 20 項，約 30 s
python3 -X utf8 backend/v1_dynamic_reference_suite.py --raw-output backend/run_traces/v1-dynamic-reference-<ts>.json
python3 -I -S backend/v1_dynamic_replay.py backend/run_traces/v1-dynamic-reference-<ts>.json
```

Contract sha256（canonical JSON）：`sha256:55fa7a29b1d108c2d37d8c80ef28a5b055a68cdfe72d7acd208a84e928a9961d`
