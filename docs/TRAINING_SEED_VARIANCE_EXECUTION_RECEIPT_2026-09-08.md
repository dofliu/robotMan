# Independent Training-Seed Variance Execution Receipt

日期：2026-09-08

Protocol：`SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1`
（`sha256:9ab17c74ddb021f9b69b1df843f9fa49ea45ecf790837204270d8bc01046b359`，
含 [Amendment 01](TRAINING_SEED_VARIANCE_SPEC.md)）

保留證據：[`backend/seed_variance_evidence/2026-09-08/`](../backend/seed_variance_evidence/2026-09-08/)

證據範圍：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED / DEVELOPMENT_ONLY`

## 1. 這次真的跑了

[RESULT] `3 arms × 5 replicates × 122,880 = 1,843,200` realized timesteps 全部
執行完成，450 個 terminal records 齊全，0 個 training 或 evaluation 失敗。

| 項目 | 值 |
| --- | --- |
| clean source | `12bfddfc5143298d43db6b3a2e477c5e05e2856d` |
| environment lock | `sha256:93d23a2703adc86a1394eacf5dece8d7229fdf742857f1a271656aa1cfeac72d` |
| lock class / completeness / threading | `MEASURED_ENVIRONMENT_LOCK` / `FULL_LOCK` / `AMBIENT_THREADING_PINNED` |
| lock verifications | `30`（每 cell 的 training 與 evaluation 各一次） |
| training seeds | `8720`、`8740`、`8760`、`8780`、`8800` |
| 每 run realized timesteps | `122880`（exact，符合 frozen expectation） |
| 每 run wall clock | 約 `73` s（4 cores，`OMP_NUM_THREADS=1`） |
| raw bundle | `sha256:0fe9c0b9e8cc81446f64c9522bb5c64ef5b1c4bc2ea054f3ef651ac859ff4535` |
| summary | `sha256:42b4cfac2ffff47b922c2ffe8f74492a7310e5cdb637bde1201084e365027965` |
| receipt | `sha256:bc8a5b059842df3c200e7498cc0e095beb713e10e3f6602e3734215545eec1a4` |
| 獨立 `python -I -S` replay | exact |
| status | `SEED_VARIANCE_EVIDENCE_COMPLETE_WITH_RETAINED_BLOCKERS`（CLI exit `1`） |
| retained blockers | `16` |

## 2. 實測 exposure

[RESULT] 450 個 episodes 全部落在 `COMPARABLE`（`263`）或 `EXPOSURE_CENSORED`
（`187`）；**沒有任何 `METHOD_FAILURE_NOT_CENSORING`**。

| Arm | FULL_EXPOSURE | EARLY_TERMINATED | 對照 pilot（單一 seed 8700） |
| --- | --- | --- | --- |
| V7A_REWARD_ONLY | `143`/150 | `7`/150 | `30`/30 full，`0` early |
| V7B_REDUCED_JOINT_ENVELOPE | `120`/150 | `30`/150 | `27` full，`3` early |
| V7C_FILTERED_ACTION | `0`/150 | `150`/150 | `0` full，`30` early |

### 2.1 第一個新發現：pilot 的乾淨 reference 是 seed 的性質，不是 arm 的性質

[RESULT] Pilot 的 V7A 在 seed `8700` 上是 30/30 `FULL_EXPOSURE`、恰 450 control
steps、sd `0`。在 5 個獨立 seeds 上，V7A 有 **3 個 replicate 出現 early
termination**：

- replicate 2（seed `8760`）：`{18013}`
- replicate 3（seed `8780`）：`{18001, 18004, 18005, 18014, 18016}`
- replicate 4（seed `8800`）：`{18000}`

[INFERENCE] 因此「reference arm 不會跌倒」不是 V7A 的性質，而是 seed `8700` 的
性質。這件事只有在有獨立 training replicates 之後才看得見，且它直接影響
identification：reference cell 一旦被 censored，paired bound 兩端都會變寬。

### 2.2 V7C 的行為跨 seed 完全重現

[RESULT] V7C 在 5 個獨立 training seeds 上都是 **30/30 early termination、30/30
`outcome_state = NULL`**，full-horizon bound 一律 `[0.0, ~64.1–64.6]`%。

[INFERENCE] Pilot 觀察到的 V7C 崩潰不是單一 seed 的壞運氣，而是該 action
interface 在此 task 與 warm start 下的 method-level 行為。

## 3. Method-level 結果

分母恆為 `replicate_count = 5`；`150` 與 `450` 為 enforced forbidden
denominators，receipt 內 `method_level_n = [5, 5]`。

### 3.1 V7B vs V7A：方向跨 seed 成立，但 variance 仍不可用

[RESULT] `theta_bound = [-13.503408, -12.435259]` pp，寬度 `1.068149`。
**Bound 完全排除 0，sign 為 `NEGATIVE`，5/5 replicates 方向可識別。**

逐 replicate 的 paired difference 下界：

```text
r0 (8720)  -13.962963
r1 (8740)  -12.630370
r2 (8760)  -14.868148
r3 (8780)  -11.750371
r4 (8800)  -14.305186
```

[INFERENCE] 這是**比 pilot 更強**的證據：pilot 的 `-12.8288921 ± 1.0720320` pp
是單一 checkpoint 下的 evaluation-seed 變異；此處的方向在 5 個獨立
fine-tuning seeds 上、且在 assumption-free censoring bounds 之下依然成立。

[BLOCKER] 但 `between_replicate_sd_pp = null`，reason
`BLOCKED_PARTIALLY_IDENTIFIED_REPLICATE_DIFFERENCES`：5 個 replicate 的
difference 全部是 interval（每個 replicate 至少有一臂被 censored），sample SD
沒有定義在 interval 上。因此
**`sample_size_decision_input_ready = false`，sample-size 決策仍然 blocked。**

[INFERENCE] 方向可識別與變異可估計是兩件事，本次結果同時給出前者、拒絕後者。
上列 5 個下界的全距約 `3.1` pp，但那是 5 個**區間端點**的描述性全距，不是
between-replicate SD，不得代入任何 power 或 sample-size 計算。

### 3.2 V7C vs V7A：sign 不可識別，與 pilot 的判定一致

[RESULT] `theta_bound = [-37.195407, +27.315704]` pp，寬度 `64.511111`，
**包含 0，sign `UNIDENTIFIED`，0/5 replicates 方向可識別。**

[INFERENCE] V7C 的表面 `-37` pp 再次被量測確認為 exposure artifact，而且這個
判定在 5 個獨立 seeds 上一致。Bound 寬度 `64.511111` pp 與
`AUDIT-V7-EXPOSURE-CENSORING-V1` 在 frozen pilot bundle 上量到的 V7C
full-horizon 寬度 `64.511111` 完全相同——因為兩者的 exposure fraction 幾乎相同，
而 bound 寬度只由未觀測到的 horizon 比例決定。

## 4. 保留的 16 個 blockers

| 類別 | 數量 |
| --- | --- |
| cell `PARTIALLY_IDENTIFIED` | `13` |
| method-level `BETWEEN_REPLICATE_SD_WITHHELD` | `2` |
| method-level `SIGN_UNIDENTIFIED` | `1` |

15 個 cell 中只有 2 個是 `POINT_IDENTIFIED`（V7A r0 與 r1，within-replicate
level SD 分別為 `1.091723` 與 `1.103957`%）。因此
`within_replicate_level_sd.mean_level_sd_pct` 三臂皆為 `null`——它要求 5 個
replicate 全部有定義，這是 fail-closed 的正確輸出，不是缺漏。

## 5. Selection 與 sample size

`selected_candidate_arm_id = null`，`selection_permitted = false`。

[BLOCKER] **V7B 的方向穩健性不構成 candidate selection。** 本 protocol 明文
禁止 selection：用同一批資料先估變異再據以選擇，會把選擇條件建立在被選中的
雜訊上。要選 candidate 必須另立 protocol version，並在看到本結果**之前**凍結
決策規則——而本結果現在已經公開，所以任何新的 selection protocol 都必須明示它是
在知道 V7B 方向為負的情況下設計的。

`replicate_count = 5` 不得因為「方向已經清楚」而事後上調或下調。

## 6. Provenance

每個 cell 綁定四項：frozen audit protocol digest（哪些規則）、
`v7_exposure_audit_contract.py` 與 `v7_pilot_contract.py` 的 source digest
（哪些實作套用了規則）、以及該 cell 的 `evaluation_output_sha256`（規則套用在
哪一份 raw 輸出上）。兩個 implementation pin 在分析時對磁碟重新 hash
（`inherited_implementations_verified = true`）。

`verify_pilot_inheritance` 逐欄比對 pilot protocol 檔本身並通過，包含 pilot
自陳的 `independent_training_replicates_per_arm == 1`。

## 7. 執行過程中的兩件事，記錄而非淡化

### 7.1 Protocol 凍結時是無法執行的

見 [Amendment 01](TRAINING_SEED_VARIANCE_SPEC.md)。凍結時把 `train_ppo.py` 與
`eval_policy.py` 都以 digest pin 住，卻沒有檢查它們能不能跑本設計——兩者的
pilot guard 分別鎖定單一 seed 與 pilot 自己的 artifact 目錄。這是 freeze 程序
本身的缺陷。

### 7.2 Guard 抓到的是我自己

[RESULT] 第一次執行跑完 2 個 replicate 後，其餘 13 個全部以
`SEEDVAR_SOURCE_GIT_NOT_CLEAN` 拒絕——因為我在 runs 進行中修改了 tracked
files。這是 guard 按設計運作：source identity 無法釘住的 training run 作為
evidence 一文不值。修正方式是把所有程式修改先 commit 完再執行，不是放寬 guard。

（另外我自己的 runner script 在失敗路徑上 `mkdir -p` 了 run 目錄，於是
driver 的 `exist_ok=False` 防覆寫 gate 正確地擋下重試；清掉那 13 個空目錄並
移除該行後才重跑。）

## 8. Claim boundary

[BLOCKER] 仍缺：independent **pretraining**-seed variance（5 個 replicate 共用
同一個 v5 warm start，故 `training_replicate_scope =
CONDITIONAL_ON_FIXED_WARM_START`，本次量到的變異**系統性低估**完整 method-level
variance）、full 11-criterion Live evidence、actual Study A matrix、binary
paired CI、project-wide immutable storage、formal authorization、HIL、bench 與
實機證據。

[BLOCKER] `cross_protocol_comparability = NON_VERIFIABLE_ENVIRONMENT`：pilot 與
audit 的 retained bundles 沒有 environment lock record，其環境為
`ABSENT_UNRECOVERABLE`。本 receipt 的數值不得與 pilot receipt 的數值相減、不得
並排成趨勢，也不得用來「確認」或「推翻」pilot 的點估計。第 2 節與第 3 節的
pilot 對照只用於陳述**exposure pattern 的定性差異**，不是數值比較。

因此允許的結論只到：在此 frozen MuJoCo plant、固定 v5 warm start、frozen task
與 DEV evaluation seeds 下，V7B 相對 V7A 的 conditional saturation-duty 差異在
5 個獨立 fine-tuning training seeds 上方向為負且可識別，而其 between-replicate
變異因 exposure censoring 不可估計；V7C 的對比在同樣條件下方向不可識別。不得
宣稱 controller superiority、candidate selection、sample-size adequacy、paper
readiness、physical torque/thermal margin、安全、sim-to-real 或實體機器人效能。

`method_level_power_ready=false`、`statistics_ready=false`、
`paper_data_ready=false` 全部保留。
