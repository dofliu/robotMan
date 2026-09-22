# V1 contact reference suite implementation receipt（2026-09-22）

ID：`V1-CONTACT-REFERENCE-SUITE-V1` ｜ 任務 #106 ｜ 規格：[V1_CONTACT_REFERENCE_SUITE_SPEC](../V1_CONTACT_REFERENCE_SUITE_SPEC.md)
｜ 性質：**實作 receipt 與量測**；`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`；V1 gate 仍 `PARTIAL_IMPLEMENTED_NOT_PASS`

---

## 0. 一句話

**7/7 gate case PASS（首輪即過，門檻未動），stdlib 獨立重算 210 個 metric 逐一相符；預先登記的 Coulomb 假說三條全部被拒絕——在 plant 的接觸參數下，滑動摩擦不是 Coulomb。**
自由球觸地步與離散閉式逐步相同（80／160／319 步），法向衝量對重量積分相對差 `≤ 2.2e-12`，靜止 GRF 對重量 `≤ 3.3e-9`，靜止穿透深度對引擎軟接觸模型的閉式 `≤ 2.0e-8`；平移滑塊的黏滯衰減速率對閉式 `99.7907 s⁻¹` 相對差 `≤ 1.4e-11`。

---

## 1. Frozen milestone 與 claim boundary

- Milestone：`V1-CONTACT-REFERENCE-SUITE-V1`——兩個有接觸、無控制器、無致動的參考案例族（**C. drop-and-settle** 自由球、**S. viscous slider** 平移薄板），各 `4／2／1 ms`，加一個只在 plant 的 2 ms 跑的 **H. Coulomb 假說**量測；全部用 plant 的接觸參數（地板宣告逐字相同、腳板摩擦三元組、未覆寫的 MuJoCo 預設 `solref/solimp/condim/cone/solver`）。
- 凍結：規格、`CONTACT_SUITE_CONTRACT`、replay 凍結常數與測試於 **`c4cd809`** commit 並 push，**在任何凍結 case 執行之前**；門檻由引擎的軟約束模型與離散誤差分析推得（規格 §3 的「依據」欄），執行後未動。
- 設計期 pilot（規格 §1.1）全部在**不同於**凍結參數的組態上做（球 3 kg／0.08 m／0.2 m；薄板 2 kg／0.08×0.08×0.03 m），只用來推導與核對閉式；其中兩個觀察直接決定了規格的形狀：自由 6-DoF 薄板一被推就翹起跳離（故 S／H 限制為平移），以及滑動摩擦在 plant 參數下沒有 Coulomb 區間（故 H 是假說量測、不是 acceptance case）。
- Claim boundary：PASS 只表示引擎對單一自由剛體的自由落體／觸地時程／法向衝量／靜止 GRF，以及引擎**自身**軟接觸模型的平衡穿透與未飽和摩擦黏滯衰減，在凍結門檻內與閉式一致。**不**是接觸物理的實體驗證、**不**涉及關節式人形／致動／控制器、**不**使 V1 PASS；H 族的結果是 plant 接觸模型的特性量測，不是能力證據。

---

## 2. Implementation inventory

| 檔 | 內容 |
|---|---|
| `backend/v1_contact_reference_suite.py` | primary：兩個 MJCF 建構（地板宣告逐字取自 plant）、逐步序列化（`qpos/qvel/qacc`、`ncon`、`qfrc_constraint`、外力上界、每個接觸的 `geom/dim/dist/pos/frame/mj_contactForce`）、閉式（阻抗 sigmoid、`K`、`B`、`pen*` 定點、`ρ`、`D(dt)`、離散觸地步）、NumPy 重算與判準、假說角色、suite 層判準、CLI（exclusive-create raw artifact） |
| `backend/v1_contact_replay.py` | stdlib-only replay：schema／契約漂移驗證（自帶凍結常數副本，含 case 清單、dt、`gates_suite`、踢速）、純 Python 重算全部 metric、primary/replay 比對（相對 `1e-10`／絕對 `1e-12`）、criteria 與假說 `passed` 序列逐項比對、非標準 JSON 拒收 |
| `backend/test_v1_contact_reference_suite.py` | 22 項：凍結契約與 replay 常數一致、閉式對引擎模型語義（阻抗端點、`K`、`B`、兩個 `pen*`、`ρ`）、離散觸地步組合數學、MJCF 用 plant 地板且 compiled 與契約相符、primary PASS 與判準清單、drop／slider 物理合理、假說翻面不改 suite 狀態、replay 相符且 PASS、replay 無 MuJoCo／NumPy／專案匯入、兩種有限值篡改保留 FAIL、八種結構問題 raise、非標準 JSON 拒收、summary 去 raw |
| `docs/V1_CONTACT_REFERENCE_SUITE_SPEC.md` | 凍結規格（§1.1 設計期觀察、§2.4 閉式平衡穿透） |

---

## 3. 執行記錄：一次，PASS

| 次 | 源碼 | Artifact | 結果 |
|---|---|---|---|
| 1 | `c4cd809`（凍結 commit，執行前 `git status` 乾淨） | `backend/run_traces/v1-contact-reference-20260922T095516.json`，`sha256:c778d7e95c00bfda1b74fde7afcc9fcd30dfd1a8be0da9d0bcf97123d3ecc3db`，7,987,608 bytes | **PASS 7/7**（gate），suite 4/4；假說 H1／H2／H3 **全部 rejected** |

同一 commit 上 `pytest backend/test_v1_contact_reference_suite.py`：22 passed（12.2 s）。MuJoCo `3.12.0`；契約 canonical-JSON `sha256:90ae75553d1fc5e9ffc17d7774f3ee26be64dc9b89e7355c73ab4b43e8811a31`。

---

## 4. 量測結果

### 4.1 C. drop-and-settle（m = 1 kg、r = 0.05 m、h = 0.5 m、2 s；靜止窗 [1.5, 2.0] s）

閉式：連續觸地時刻 `t_c = 0.3192754 s`；靜止穿透 `pen*(n_c = 1) = 3.6718184e-4 m`。

| dt | 觸地步（量測＝閉式） | ｜t_td − t_c｜ | 自由落體位置對離散閉式 | 衝量恆等式 | 衝量對 mgT | 靜止 GRF 對 mg | 靜止速度 | 穿透對閉式 | 撞擊峰值 N／最大穿透 | 觸地後分離 |
|---|---|---|---|---|---|---|---|---|---|---|
| 4 ms | 80 = 80 | `0.72 ms`（≤ 4） | `3.1e-16 m` | `1.8e-16` | `1.6e-12` | `2.4e-9` | `7.1e-11` | `5.2e-9` | 344.6 N／20.9 mm | 0 |
| 2 ms | 160 = 160 | `0.72 ms`（≤ 2） | `3.5e-16 m` | `5.4e-16` | `2.2e-12` | `3.3e-9` | `4.8e-11` | `1.9e-9` | 336.8 N／22.9 mm | 0 |
| 1 ms | 319 = 319 | `0.28 ms`（≤ 1） | `1.6e-15 m` | `1.8e-16` | `0` | `1.8e-16` | `3.3e-15` | `2.0e-8` | 321.0 N／21.5 mm | 0 |

- 觸地步與 `n* = min{n : g·dt²·n(n+1)/2 > h}` 逐字相同：`implicitfast` 在無速度相依力時就是半隱式 Euler，接觸在 `dist < 0` 才產生——契合 `V1-R08` 的「prescribed 對 solved 事件」，誤差在一步以內。
- 法向衝量的離散動量恆等式（左端點和）到 round-off；「衝量＝重量積分」的物理閉式到 `2e-12`，因為靜止末速 `≤ 7e-11 m/s`。
- 步進恆等式 `v_{n+1} = v_n + dt·qacc_n` 最大差 `1.2e-10`（warm-start 下 solver tolerance 量級）；世界力總和對 `qfrc_constraint` 差 `0`。
- 靜止穿透對閉式平衡（`pen = (1−d)g/(n_c d² K)`）`≤ 2e-8`；三個 dt 的極差 `1.8e-8`（穩態，與 dt 無關）。
- 單點接觸是精確臨界阻尼（`ζ = B/(2√K) = 1`），觸地後**沒有**任何分離事件；撞擊峰值約 33–35 倍重量、最大穿透約 2.1–2.3 cm（1 kg 球以 3.13 m/s 撞地，`solref` 預設 20 ms）——這兩個數只記錄、不設門檻。

### 4.2 S. viscous slider（m = 1 kg、半邊 0.10／0.10／0.02 m、4 個接觸、踢速 0.02 m/s、2 s）

閉式：`pen*(n_c = 4) = 1.0775542e-4 m`、`d(pen*) = 0.901161`、`ρ = B·2d/(1+d) = 99.7907 s⁻¹`、飽和速度 `μg/ρ = 0.0983 m/s`（踢速為其 20%）。

| dt | 滑動窗 sample | 速率對 ρ | 對離散幾何衰減 | 對連續指數 | 預算的 D(dt) | cone 利用率 max | 滑動中法向力對 mg | 踢前／踢後穿透對閉式 | 踢後靜止 GRF／速度 |
|---|---|---|---|---|---|---|---|---|---|
| 4 ms | 14 | `7.1e-12` | `5.7e-12` | `0.08908` | `0.08908` | 0.203 | `6.8e-11` | `9.8e-9`／`9.3e-9` | `2.0e-9`／`5.4e-11` |
| 2 ms | 32 | `8.6e-12` | `6.2e-12` | `0.04011` | `0.04011` | 0.203 | `2.5e-10` | `1.2e-8`／`1.1e-8` | `1.8e-9`／`2.4e-11` |
| 1 ms | 66 | `1.4e-11` | `9.5e-12` | `0.01916` | `0.01916` | 0.203 | `4.7e-10` | `1.9e-8`／`3.3e-9` | `1.9e-9`／`1.5e-11` |

- 引擎的未飽和摩擦是**黏滯**的：切向速度每步乘 `(1 − dt·ρ)`，與由 `a_ref = −B·v − d·K·pos`、`R = (1−d)/d·diag(A)`、facet `diag(A) = 4/m` 推出的 ρ 相符到 `1e-11`。對連續指數的差就是預算的離散差 `D(dt)`（差在 `3e-10` 內），三個 dt 單調遞減，observed order `1.15`／`1.07`（`ESTIMATED`，預期 1）。
- 四點分擔的平衡穿透是單點的 `1/3.41`（`1.0776e-4` 對 `3.6718e-4`），與 `1/n_c` 縮放乘上阻抗變動的閉式一致到 `2e-8`：**引擎的接觸柔度不是材料常數，隨分擔負載的接觸點數變**。
- 切向動量恆等式 `Σ F_x dt = m(v_N − v₀)` 到 round-off；四個接觸點在 `t ≥ 0.1 s` 後每步都在。

### 4.3 H. Coulomb 假說（同一薄板、踢速 0.5 m/s、2 ms；`gates_suite = false`）

| 假說 | 預登記門檻 | 量測 | 結果 |
|---|---|---|---|
| H1 滑動窗內四個接觸不中斷 | 每步 `ncon = 4` | 踢後 **11 個 sample（22 ms）失去接觸** | **rejected** |
| H2 滑動中法向力總和 = 重量 | 相對 `≤ 0.02` | 相對誤差 **`2.03`**（法向力膨脹到 **3.03 倍重量**） | **rejected** |
| H3 減速度 = μg | 相對 `≤ 0.02` | 平均 `9.422 m/s²`，相對 **`0.0396`** | **rejected** |

滑行距離 12.9 mm（Coulomb 閉式 `v₀²/(2μg) = 12.7 mm`——平均減速度接近 μg 是因為法向力膨脹與失去接觸的兩段效應部分抵銷，不是因為摩擦是 Coulomb）。簿記判準全過：cone 利用率恰為 `1.000000000`（力在 cone 邊界上）、切向動量恆等式 `0`、步進恆等式 `4e-11`、踢後靜止 GRF／穿透回到閉式（`1.8e-9`／`1.2e-8`）。
**對 plant 的意義**：腳板一旦以 ≳ 0.2 m/s 滑動，plant 的接觸模型會把摩擦需求「漏」進法向力（`impratio = 1`、pyramidal cone、`solref` 預設），這是 `V1-R06` 在動態情境下**不能**被宣稱為 Coulomb-feasible 的直接證據；它也是行走控制器比較（[CONTROLLER_COMPARISON_2026-09-22](../CONTROLLER_COMPARISON_2026-09-22.md)）與 Raibert 診斷（[RAIBERT_STACK_DIAGNOSIS_2026-09-22](../RAIBERT_STACK_DIAGNOSIS_2026-09-22.md)）解讀時必須帶著的 caveat。

### 4.4 Replay

`python -I -S backend/v1_contact_replay.py <artifact>` → **PASS**；`all_agree = true`，210 個 metric（27×3＋33×3＋30）逐一相符、最大相對差 `0.0`（絕對差在 `1e-12` 內者不計）；每個 case 的 criteria 與假說 `passed` 序列與 primary 逐項相同；`primary_file_sha256` 與 §3 相同。

---

## 5. 對 V1 gate 的影響

| VV_PLAN 列 | 前 | 後 |
|---|---|---|
| `V1-R05` unilateral contact | PARTIAL：靜態 double／single-support；dynamic coverage 缺 | PARTIAL：**加**自由球落地／靜止與滑塊兩族的每步 `f_n ≥ 0`（含撞擊與失去接觸的 H case）；關節式人形的動態接觸仍缺 |
| `V1-R06` friction feasibility | PARTIAL：靜態 cone 利用率；dynamic scenarios 缺 | PARTIAL：**加** cone 投影每步成立（利用率 ≤ 1）與未飽和黏滯區間的閉式；**H 族量到 plant 的滑動摩擦在 ≳ 0.2 m/s 不是 Coulomb**（法向力膨脹 3 倍、失去接觸）——這是限制的證據，不是 PASS 的證據 |
| `V1-R08` contact schedule consistency | **NOT STARTED** | **PARTIAL**：自由球的 prescribed 觸地步（離散閉式）與 solved 觸地步逐字相同，三個 dt；關節式人形的步態接觸排程仍缺 |
| `V1-R11` numerical convergence | PARTIAL：GRF、pendulum、articulated 能量 | PARTIAL：**加** 黏滯滑動對連續閉式的一階收斂（order 1.15／1.07）與穩態穿透的 dt 無關性 |
| `V1-R14` analytical reference cases | PARTIAL：pendulum 與 articulated 完成；dynamic contact 缺 | PARTIAL：**dynamic contact 的單剛體部分完成**（自由落體、觸地、衝量、靜止、平衡穿透、黏滯滑動）；關節式人形的 dynamic contact 仍缺 |

V1 gate 狀態不變：`PARTIAL_IMPLEMENTED_NOT_PASS`。PASS 還缺：關節式人形的動態接觸與步態排程、致動下的能量帳（`V1-R13`）、solver-tolerance／finite-difference、joint limits（`V1-R09`）、actuator envelope（`V1-R10`）；以及 H 族揭示的 plant 摩擦模型限制要被承認為 plant 的已知特性（或改參數後重測）。

---

## 6. 不能拿這份 receipt 說什麼

- 不能說接觸物理被實體驗證了——全部是 MuJoCo 對自己模型與閉式的一致性。
- 不能說 plant 的摩擦是 Coulomb——H 族三條假說被拒絕，說的正是相反。
- 不能說關節式人形的接觸被驗證了——兩族都是單剛體，滑塊還刻意排除旋轉。
- 平衡穿透與黏滯衰減的閉式是**引擎軟約束模型**的語義（含由 `efc_R` 回讀的 facet `diag(A)`），不是第一原理物理。

---

## 7. 重現

```bash
python3 -X utf8 -m pytest backend/test_v1_contact_reference_suite.py -p no:cacheprovider -q     # 22 項，約 12 s
python3 -X utf8 backend/v1_contact_reference_suite.py --raw-output backend/run_traces/v1-contact-reference-<ts>.json
python3 -I -S backend/v1_contact_replay.py backend/run_traces/v1-contact-reference-<ts>.json
```
