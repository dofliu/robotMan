# `R0-REGIME-HORIZON-PROBE-V1` 執行 receipt

日期：2026-09-11 ｜ Protocol：`R0-REGIME-HORIZON-PROBE-V1` ｜ 規格：[R0_REGIME_PROBE_SPEC](R0_REGIME_PROBE_SPEC.md)

狀態：`EXECUTED / R0_WINDOW_FOUND_BOTH_CONTRASTS / PILOT_NOT_EVIDENCE`

證據等級：`PILOT / DEVELOPMENT / SIM_ONLY_MUJOCO / CONDITIONAL_ON_FIXED_WARM_START`

---

## 1. 結果

[RESULT] 兩個對比皆為 **`R0_WINDOW_FOUND`**。

| 對比 | 標籤 | 滿足 `R0-P0a` 的 horizon | 同時滿足 `R0-P0b` | 選中的 `H` | 該 `H` 的 reference 平均 duty |
|---|---|---|---|---|---|
| `C_B`（`V7B` vs `V7A`） | `R0_WINDOW_FOUND` | 290 個（`125`–`414`） | **290 個（全部）** | `414`（8.28 s） | `40.262319` pp |
| `C_C`（`V7C` vs `V7A`） | `R0_WINDOW_FOUND` | 28 個（`125`–`152`） | **28 個（全部）** | `152`（3.04 s） | `22.089474` pp |

[RESULT] 在兩個對比中，**每一個滿足 `R0-P0a` 的 horizon 也都滿足 `R0-P0b`**。reference 的平均 duty 在整個 P0a 範圍內最低為 `9.893333` pp（在 `H = 125`），從未接近 `5.0` pp 的下界。

## 2. 本 probe 所設計要防的 R5 陷阱，在這個 plant 上沒有發生

[INFERENCE] 規格 §1.1 的設計主軸是一個張力：截得夠早 → 兩臂都不跌倒，但窗口全在初始站立、reference saturation 趨近 0（Hopper probe 的 `R5`）。**在這批資料上，該張力在凍結的 `2.5 s` 下界之上並不發生**：reference 在 `H = 125` 就已有 `9.893333` pp 的平均 duty，是 Hopper 那個退化 reference（`2.712%`）的 3.6 倍。

[BLOCKER] 這是關於**這個 plant 與這個任務**的量測，不是一般性結論。同一個兩段式規則在 Hopper 上確實會擋下退化 reference。兩者合起來的意思是：非退化性必須**逐案檢查**，不能假設也不能省略——這正是 A-C3 主張該前置條件存在的理由，而不是反例。

## 3. 綁住 R0 窗口的是 candidate，不是 reference

[RESULT] 每個對比的 P0a 上界**恰好等於該 candidate 最短的 episode**：

| Arm | 全 horizon（450 步）episode | 早期終止 | 最短 episode | 早期終止的時間範圍 |
|---|---:|---:|---:|---|
| `V7A_REWARD_ONLY`（reference） | 143 / 150 | 7 | `419`（8.38 s） | 8.38 – 8.98 s |
| `V7B_REDUCED_JOINT_ENVELOPE` | 120 / 150 | 30 | `414`（8.28 s） | 8.28 – 8.98 s |
| `V7C_FILTERED_ACTION` | 0 / 150 | 150 | `152`（3.04 s） | 3.04 – 3.28 s |

[RESULT] **`V7A` 的 7 個與 `V7B` 的 30 個早期終止，全部落在 9 s 任務的最後 `0.62`／`0.72` 秒之內**——依 [MOTION_TASK_SPEC](MOTION_TASK_SPEC.md) 的 phase 表，那是 `FINAL_STAND`（8.0–9.0 s）。`V7C` 完全不同：150 個 episode 全部在 `3.04`–`3.28` s 跌倒，落在 `STEADY_WALK`。

## 4. 對 A-C3 的意義：regime 由一個沒人報告的旋鈕決定

[RESULT] 同一批 policy、同一批 evaluation seed，**只改 evaluation horizon**，同一個對比就落在不同的 censoring regime：

| 對比 | `H = 450`（凍結的完整任務） | `H ≤ ` 本 probe 選中的值 |
|---|---|---|
| `C_B`（`V7B` vs `V7A`） | **R2**：輕度 censoring，bound `[−13.503408, −12.435259]` pp 排除 0，但 `between_replicate_sd` 無定義 | **R0**：兩臂皆 full，點識別 |
| `C_C`（`V7C` vs `V7A`） | **R1**：不對稱，naive 主張 `−36` pp 而 bound 含 0——artifact | **R0**：兩臂皆 full，點識別 |

[INFERENCE] `C_B` 的轉換只需要放棄 **36 個 control step（`0.72` s，不到 horizon 的 8%）**。也就是說，「partially identified 且變異不可估計」與「點識別」之間的差別，在這個案例上是評估者對最後 0.72 秒的一個選擇——而該選擇在標準實務中既不被控制、也不被報告。這是 A-C3 目前最乾淨的示範。

[BLOCKER] 這**不表示**應該改用截斷 horizon 評估，也**不表示**截斷後的結果比較可信。截斷改變的是估計目標：`H = 414` 的 duty 回答的是「前 8.28 秒內的 saturation」，而任務問的是 9 秒。真正的結論是**regime 標籤不是資料的固有屬性，而是設計選擇的函數**，因此必須連同 horizon 一起報告。

## 5. 這**不是**第六個獨立實例

[BLOCKER] 必須明說，否則 taxonomy 會被誤讀：本 probe 的 R0 實例**不是**新的 plant、新的 policy family 或新的資料。它是**同一批 450 個 episode 在較短 horizon 上的重讀**。它為 taxonomy 增加的不是一個獨立案例，而是一項**案例內**的示範——regime 可由 horizon 決定。

[BLOCKER] 選中的 `H` 雖由凍結規則（取最大 adequate horizon）決定，但其**數值**由資料決定（它追隨 candidate 最短的 episode）。`414` 與 `152` 不是設計選擇，不得當作推薦的評估 horizon。

## 6. 執行與驗證

| 項目 | 值 |
|---|---|
| 執行 commit | `edf3611`（clean source，pre == post） |
| 凍結 commit | `06ebf60`（規格與 protocol 在任何截斷計算之前已 push） |
| Protocol digest | `sha256:07cf6d21dbc84d299384846d21abb8e25d921da8aea9214a77c95abe7bed08fe` |
| 規格 digest | `sha256:a15cada64637800a9fa50184d0e4dec1eaad958602c296c3211b90edf031c03a` |
| Horizon trace index | `sha256:6ad44934232e110741a69879027ccc1f84c10ae4c63b0acf2877756af0d330c7` |
| 結果檔 | `backend/r0_probe_evidence/2026-09-11/probe_result.json`，`sha256:f8a8db7265af3c316e76dcefd5c09856a42b7f79aa561a79a8402a69519b65e9` |
| Environment lock | `MEASURED_ENVIRONMENT_LOCK` / `FULL_LOCK`；`locked_sha256` **與母證據（seedvar 執行）逐位元相同** |

[RESULT] **獨立重算 bit-exact。** 以 `python -I -S`（`isolated=True`、`no_site=True`，無任何 site package）重跑同一個 contract，分析部分的序列化與保留結果的 SHA-256 完全相同：`2445190273c2c66aab46050d1b729a9b2713554b8b3a12b1ea92bd5e4c4855b4`。

[RESULT] **判定不依賴 reduction order。** 本專案已量測過同一環境下 stdlib 逐項求和與 `numpy` 求和會在末位不同，故另行檢查：對每一個 P0a horizon，以左至右、`math.fsum` 與反向三種順序計算 reference 平均 duty，最大差異為 `1.0 × 10⁻⁶`，而最接近門檻的 margin 是 `9.893333` pp 對下界 `5.0` pp。**沒有任何 horizon 的 `R0-P0b` 判定依賴求和順序。**

### 驗收 `R0-01` .. `R0-08`

| ID | 結果 |
|---|---|
| `R0-01` | PASS —— 450 個 episode 全數載入；`saturation_substeps_total` 恆為 `10`，逐 episode 與 control step 數一致 |
| `R0-02` | PASS —— 15 個來源 digest 於抽取時全部命中母 bundle 的 retained 值；索引 digest 於分析時再次比對相符 |
| `R0-03` | PASS —— `H = 450` 的重算 duty 對 **450/450** episode 與凍結的 `metrics.saturation_duty_pct` 6 位小數相等 |
| `R0-04` | PASS —— grid `125..450` step `1`、門檻 `[5.0, 95.0]`、選擇規則「取最大」與規格 §6 及 protocol JSON 一致，digest 已 pin 並由測試比對 |
| `R0-05` | PASS —— 兩個對比各得恰好一個標籤，皆非 `R0_PROBE_METHOD_FAILURE` |
| `R0-06` | PASS —— `python -I -S` 重算 bit-exact |
| `R0-07` | PASS —— 產出中無 `150`／`450` 作為 method-level 分母；所有 duty 為逐 episode 值或單一 horizon 上單一臂的平均 |
| `R0-08` | PASS —— 本 receipt 明載 pilot 等級、`CONDITIONAL_ON_FIXED_WARM_START` 與 §7 claim boundary |

## 7. Claim boundary（與規格 §7 相同，重述以免被單獨引用）

本結果**只**支持：未來一份凍結 R0 protocol 的 horizon 選擇；以及「regime 在 horizon 維度上可達且由 horizon 決定」這項觀察，用於 A-C3。

本結果**不**支持：`V7B` 或 `V7C` 在 9 s 任務上的任何表現或優劣陳述；任何 task PASS；任何 controller superiority；對 [MOTION_TASK_SPEC](MOTION_TASK_SPEC.md) 11 項 criteria 的任何判定；把截斷 horizon 的 duty 與 9 s 的 duty 相比或混用；以及任何 physical feasibility、safety、sim-to-real 或 actuator 陳述。

[BLOCKER] 本 probe 在**已被檢視過**的 DEVELOPMENT 資料（seeds `18000–18029`，`DEVELOPMENT_EXHAUSTED`）上執行，且 v7 線的 5 個 replicate 共用同一個不可重建的 v5 warm start。稿件引用時必須同時出現這兩項限制。

## 8. 沒有改變的事

`paper_data_ready`、`statistics_ready`、`method_level_power_ready`、`sample_size_decision_input_ready` 皆為 false 不變。沒有訓練、沒有新評估、沒有動任何 seed、沒有存取 `19000–19029` 或 `20000–20029`。沒有修改任何既有 contract、protocol、門檻或 arm 定義。`PUB-A1a`／`PUB-A1b` 狀態不變；Track B 的兩個子問題不受影響。門檻**未**因結果而調整——本 probe 首次執行即得 `R0_WINDOW_FOUND`，不存在放寬重跑的情形。
