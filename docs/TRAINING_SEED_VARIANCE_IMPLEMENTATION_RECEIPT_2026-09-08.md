# Independent Training-Seed Variance Implementation Receipt

日期：2026-09-08

Protocol：`SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1`
Spec：[`docs/TRAINING_SEED_VARIANCE_SPEC.md`](TRAINING_SEED_VARIANCE_SPEC.md)
（SHA-256 `102fdb4811690e9b9bee53a2f623fa514b6320504f3e77310d3b39826db2174b`）
Machine-readable protocol：
[`backend/rl/training_seed_variance_protocol.json`](../backend/rl/training_seed_variance_protocol.json)
（SHA-256 `56c51e2ab37c4777c0c0434d60cdf73c9835489704d7ec439c684c0e0a86d5a5`）

實作：

| 檔案 | SHA-256 |
| --- | --- |
| `backend/training_seed_variance_contract.py` | `079c5dad81880850a93b3deb445acc159fce947b70358893b0fa1ef70a7e7cc9` |
| `backend/training_seed_variance_replay.py` | `21c7fba6ad877a3e7e9bebe6319bd6dcd0e26fbec5937e6a59347682a6998365` |
| `backend/test_training_seed_variance_contract.py` | `ec1bc92a626aef12619aa98372ed67c38414f167dfdae093562f56f57d02c769` |
| `backend/build_training_seed_variance_regression_bundle.py` | `a6425fcfd7b99b1cc3354b14e5e32692a8748637ad8ebd0ffe85bfb5949e104a` |

證據範圍：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED / DEVELOPMENT_ONLY`

## 1. 本次完成與未完成的分界

[RESULT] 完成：protocol 凍結（spec + machine-readable contract）、evidence
contract 實作、獨立 stdlib-only replay、synthetic regression 驗證。

[BLOCKER] 未完成：**實際訓練沒有執行**。protocol 要求
`3 arms × 5 replicates × 122,880 = 1,843,200` timesteps，是 v7 pilot
（`368,640`）的 5 倍，需要算力。因此本 receipt 不含任何 v7 method-level
variance 數值，`method_level_power_ready` 維持 `false`，
`formal_sample_size_decision` 維持
`BLOCKED_UNTIL_THIS_PROTOCOL_EXECUTES`。

## 2. Plant identity：一個附帶量到的事實

`backend/model_builder.py` 在 `geom_render_list` 修正後 SHA-256 由
`0beabfa2...` 變為 `09163a81...`，而 v7 protocol 仍 pin 舊值。為了不讓 file
drift 冒充 plant drift，本 protocol 改 pin plant 本身。

[RESULT] `model_builder.build_mjcf(default_robot(), [], dynamic=True)` 產生
`7594` bytes、SHA-256
`fd0a191f35a7c50d186a104b3378a92acdb794e82606d7f0c9aca902c7eac9df`。用 v7 所
pin 的那一份舊 `model_builder.py`（`0beabfa2...`，自 Git 取出）重建同一個
MJCF，得到**完全相同**的 bytes 與 digest。

[INFERENCE] 該次修改只動到 `geom_render_list`，沒有觸及 `build_mjcf` 或
`make_model`，所以 training plant 與 pilot 的 plant byte-identical，即使
source file identity 不同。

[BLOCKER] Plant identity 只建立在 MJCF content 層。它不證明 pilot 當時的
solver 行為相同——pilot 沒有 environment lock record，其環境狀態是
`ABSENT_UNRECOVERABLE`。因此
`cross_protocol_comparability = NON_VERIFIABLE_ENVIRONMENT` 保留，本 protocol
的數值不得與 v7 receipt 的數值相減或並排成趨勢。

## 3. 三條結構性規則的實作

### 3.1 Analysis unit 是 training replicate

`method_level_denominator` 恆為 `replicate_count = 5`。`150`（episode-level
pairs）與 `450`（terminal records）在 protocol 內被明列為
`forbidden_denominators`，並在三處被檢查：`_method_level` 拒絕任何非
`replicate_count` 的分母、`validate_seed_variance_bundle` 拒絕
`method_level_n` 為 forbidden denominator 的 receipt、`validate_protocol`
拒絕未把 episode-level 計數列為 forbidden 的 protocol 版本。

[RESULT] 在 `all-comparable` regression case 上，把兩個分母的後果並排（以下是
對已輸出的兩個 SD 做算術，不是 protocol 輸出的統計量）：

| Candidate | `between_replicate_sd` (pp) | `mean_within_replicate_paired_sd` (pp) | 正確 SE（`n=5`） | pseudo-replicated SE（`n=150`） | 低估倍數 |
| --- | --- | --- | --- | --- | --- |
| V7B | `1.912096` | `0.810572` | `0.855115` | `0.066183` | `12.92×` |
| V7C | `1.539097` | `0.834210` | `0.688305` | `0.068113` | `10.11×` |

[INFERENCE] 這是 fixture 上的數字，不是 v7 的數字；它示範的是機制：把
evaluation-seed 變異當成 training-seed 變異，標準誤會小一個數量級。

### 3.2 Exposure censoring 逐層向上組合

Cell → paired → method 三層都用 interval arithmetic，每一層對 independent
unknowns 都是 tight bound：

- cell：`[mean(lo_i), mean(hi_i)]`
- paired：`[lo_candidate - hi_reference, hi_candidate - lo_reference]`
- method：`[mean_r(lo_d), mean_r(hi_d)]`

只要有任一 `d[r]` 不是 point-identified，`between_replicate_sd` 輸出 `null`，
reason `BLOCKED_PARTIALLY_IDENTIFIED_REPLICATE_DIFFERENCES`。Sample SD 沒有
定義在 interval 上，用區間中點代替就是 imputation。

### 3.3 Method failure 不是 censoring

含 method failure 的 cell **沒有 mean**：產生一個 mean 需要刪掉那個 failure。
因此 cell 進入 `BLOCKED_METHOD_FAILURE`，method-level bound 變 `NULL`，並列出
被 blocked 的 replicate index。Failure 本身保留在 counts 裡。

## 4. Synthetic regression 結果

[RESULT] Clean source `7d961cbf767447ae967d4e2264b460e20c0595ee`，
19 artifacts / `978501` bytes。Environment lock 以 `OMP_NUM_THREADS=1` 實際
設定後 capture，`locked_sha256`
`sha256:3c48f040ee3b104f7e543f3366830e692dafa24645c083f6823a74463fcb7642`
（`MEASURED_ENVIRONMENT_LOCK` / `FULL_LOCK` / `AMBIENT_THREADING_PINNED`）。

| Case | Status | Blockers | Summary SHA-256 | Replay |
| --- | --- | --- | --- | --- |
| `all-comparable` | `SEED_VARIANCE_EVIDENCE_COMPLETE` | `0` | `61561d8500ff94615030dc3a10ec8766b01be6e9ec0f90f7c2b6cf988c3d6632` | exact |
| `censored-candidate` | `..._WITH_RETAINED_BLOCKERS` | `7` | `80433015a9d659cfe88f0fd35a61412f3c52b6e1d9c65cf90bf02e8b07ac0d72` | exact |
| `method-failure` | `..._WITH_RETAINED_BLOCKERS` | `2` | `de9670dbcf9348c670dd2a84ec9050d9e2a1e21f7e317a76a607ba4e5210092c` | exact |

逐 case 的 method-level 輸出：

| Case | Candidate | `theta_bound_pp` | sign | signed replicates | `between_replicate_sd` | ready |
| --- | --- | --- | --- | --- | --- | --- |
| all-comparable | V7B | `[-12.392918, -12.392918]` | `NEGATIVE` | `5/5` | `1.912096` | true |
| all-comparable | V7C | `[-14.755794, -14.755794]` | `NEGATIVE` | `5/5` | `1.539097` | true |
| censored-candidate | V7B | `[-12.392918, -12.392918]` | `NEGATIVE` | `5/5` | `1.912096` | true |
| censored-candidate | V7C | `[-28.607824, +35.903276]` | `UNIDENTIFIED` | `0/5` | `null` | false |
| method-failure | V7B | `NULL` | `NULL` | `0/5` | `null` | false |
| method-failure | V7C | `[-14.755794, -14.755794]` | `NEGATIVE` | `5/5` | `1.539097` | true |

[RESULT] `censored-candidate` 的 V7C bound 寬度為 `64.5111` pp，與
`AUDIT-V7-EXPOSURE-CENSORING-V1` 在 frozen bundle 上量到的 V7C full-horizon
bound 寬度 `64.511111` 一致（fixture 使用同一個 exposure fraction
`0.354889`）。

[RESULT] 三個 case 中，被 censoring 影響的 arm 沒有汙染同一個 bundle 內
comparable 的 arm：`censored-candidate` 的 V7B 與 `all-comparable` 的 V7B 輸出
完全相同。

## 5. 兩個自己發現並修掉的缺陷

### 5.1 Lock 驗證的顆粒度與 spec 不符

Spec 要求「每一個 training 與 evaluation run 之前」都要 verify lock，但 raw
schema 起初每個 `(arm, replicate)` cell 只有一個 `environment_lock_verified`
flag，把兩個獨立的 run 混成一個：training run 驗過而 evaluation 沒驗過的 cell
會通過驗證。改為每個 cell 分別攜帶
`training_environment_lock_verified` 與 `evaluation_environment_lock_verified`，
兩者皆須為 true。Frozen protocol 只規定 verify point、不規定欄位名，因此這個
修正沒有動到 frozen protocol。

### 5.2 Fixture 讓 pairing 看起來完美有效

[RESULT] 初版 fixture 讓三臂共用同一組 per-replicate offset。Replicate-level
pairing 正是用來消掉共同 offset 的，所以它在 contrast 中被完全抵銷：
`between_replicate_sd` 只有 `0.146` pp，對比 within-replicate paired SD
`0.811` pp。測試全綠，但整個 suite 從未真正驗證「paired difference 的
between-replicate 變異」——也就是本 protocol 唯一要量的東西。

修正後每臂各有自己的 offset series，並新增
`test_fixture_paired_differences_vary_between_replicates` 直接斷言該性質，
避免無聲退化。

## 6. Acceptance criteria

下表是**contract-level 驗證**，在 synthetic replicate rows 上取得。它陳述的是
「gate 存在且會擋下對應的違規」，**不是**「protocol 已執行並通過」。`SV-02` 與
`SV-05` 特別要注意：它們是執行時的 gate，這裡只驗證 contract 會在 pre/post Git
SHA 不同、worktree dirty 或 lock 不符時 fail closed；真正的執行期檢查要等實際
訓練跑起來才會被行使。

| ID | 要求 | 結果 |
| --- | --- | --- |
| `SV-01` | 三臂與 warm start identity 與 pilot exact | PASS（`verify_pilot_inheritance` 逐欄比對 pilot protocol 檔本身，含 warm start path/bytes/SHA、arm 順序、PPO geometry、episode 數、seed ranges，並複查 pilot 自陳的 `independent_training_replicates_per_arm == 1`） |
| `SV-02` | 執行前後 Git SHA 相同且 worktree clean | PASS（raw 內 pre/post 相同、`dirty` 皆 false，且 builder 拒絕 dirty worktree） |
| `SV-03` | 5 個 training seeds、env blocks 兩兩不重疊且與 pilot `8700–8711` 不重疊 | PASS |
| `SV-04` | 每 cell 恰 30 個 `18000–18029` records、總數 exact `450` | PASS |
| `SV-05` | lock 為 measured + `FULL_LOCK` + `AMBIENT_THREADING_PINNED` | PASS（每個 cell 分別攜帶 `training_environment_lock_verified` 與 `evaluation_environment_lock_verified`，兩者皆須為 true；receipt 記錄 `2 × 5 × 3 = 30` 次 verification） |
| `SV-06` | method-level 分母 exact 等於 `replicate_count` | PASS |
| `SV-07` | failure/null/censored 全部保留，無 complete-case deletion | PASS |
| `SV-08` | censoring 逐層組合；partial identification 使 SD 為 `null` | PASS |
| `SV-09` | 輸出 variance components 與 `theta_bound`，保留兩個 scope 標註 | PASS |
| `SV-10` | artifact relative path/bytes/SHA readback exact，path escape fail closed | PASS（含 symlink escape） |
| `SV-11` | 另一個 `python -I -S` stdlib-only process exact 重建 summary | PASS（三個 case 全部 exact） |
| `SV-12` | receipt 維持 `selected_candidate_arm_id=null` 等 flags | PASS |

[RESULT] `backend/test_training_seed_variance_contract.py`：**101 passed**。

Replay 的獨立性以 AST 斷言：
`test_replay_module_imports_no_repository_code_at_top_level` 要求 replay 的
top-level import 只有 stdlib，且不 import contract 模組。Replay 從 protocol
JSON 重讀 arm roles、seeds、denominators 與 lock requirement，而不是共用
constants，所以 exact identity 是檢查而不是覆述。

兩邊共用一個 reduction 定義：`ordered_mean` 依 ascending replicate/seed 順序
左至右相加。`test_reduction_order_is_fixed_not_sorted` 以 `[1e16, 1.0, 1.0]`
與其反序證明順序會改變結果——兩者都合規，正因如此順序必須凍結。

## 7. Selection 與後續

`selected_candidate_arm_id` 在本 protocol 內恆為 `null`，`selection_permitted`
恆為 `false`。用同一批資料先估變異再據以選擇，會把選擇條件建立在被選中的雜訊
上；candidate selection 與 sample-size decision 必須另立 protocol version，並
在看到本 protocol 結果**之前**凍結決策規則。

`replicate_count = 5` 不得在看到結果後上調（optional stopping）；要加必須另立
新 protocol version，且新舊 replicates 不得混算。

## 8. Claim boundary

[BLOCKER] 沒有 independent **pretraining**-seed variance（所有 replicates 共用
同一個 v5 warm start，故 `training_replicate_scope =
CONDITIONAL_ON_FIXED_WARM_START`，估到的 SD 系統性**低估**完整 method-level
variance）、沒有 full 11-criterion Live evidence、沒有 actual Study A matrix、
沒有 binary paired CI、沒有 project-wide immutable storage、沒有 formal
authorization、沒有 HIL/bench/實機證據，也**沒有實際訓練資料**。

因此允許的結論只到：本 protocol 已凍結，且其 evidence contract 在 synthetic
rows 上被證明會拒絕它無權計算的數字。不得宣稱 controller superiority、
candidate selection、sample-size adequacy、paper readiness、physical
torque/thermal margin、安全、sim-to-real 或實體機器人效能。
