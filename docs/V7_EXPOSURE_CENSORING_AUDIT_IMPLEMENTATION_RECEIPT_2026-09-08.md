# V7 Early-Termination / Exposure-Censoring Validity Audit V1 Implementation Receipt

日期：2026-09-08

Protocol：`AUDIT-V7-EXPOSURE-CENSORING-V1`

狀態：`SOFTWARE_CONTRACT_IMPLEMENTED / SYNTHETIC_REGRESSION_PASS / FROZEN_PILOT_BUNDLE_NOT_PRESENT`

證據邊界：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED / DEVELOPMENT_ONLY`

## 1. 本次唯一目標

依 [V7 Exposure-Censoring Validity Audit Specification](V7_EXPOSURE_CENSORING_AUDIT_SPEC.md)
建立一個只讀的 exposure-censoring validity audit：由 retained 500 Hz control-step traces
重建每 episode的 termination control step、termination sim time與 termination phase，導出
realized exposure，並明示哪些 primary-outcome值與 paired contrast可比較、哪些是
exposure-censored、哪些是保留的 method failure。

Acceptance criteria、failure semantics與 claim boundary已先在 Git
`ee7321090089b186d847a958ae607478b6a12e6c`凍結；實作與實驗 source為 Git
`4d0709327a03ba2773c8ad05f6051118dda6f54e`。`19000–19029`未讀取且維持退役，
`20000–20029`未讀取且維持 sealed FORMAL range。Motion Task thresholds未變，
2026-09-06 pilot receipt原文未改。

## 2. 完成內容

- 新增 `backend/v7_exposure_audit_protocol.json`：frozen machine-readable audit protocol，
  含 read-only contract、bundle class binding、exposure horizon derivation、兩個 phase
  convention、censoring/method-failure vocabulary、identification bounds與 `AX-01..AX-12`。
- 新增 `backend/v7_exposure_audit_contract.py`：stdlib-only fail-closed audit。刻意不從
  `v7_pilot_contract` import任何東西，因為沿用被 audit pipeline自身的 validator只會重述
  它的假設。
- 新增 `backend/v7_exposure_audit_replay.py`：獨立 `python -I -S` process，由 raw episode
  rows重建 audit summary並要求 exact identity，逐 block回報 mismatch位置。
- 新增 `backend/test_v7_exposure_audit_contract.py`：38個 synthetic fail-closed tests。
- 新增 `backend/build_v7_exposure_audit_regression_bundle.py`：clean-source synthetic
  regression evidence builder。

本次沒有修改 policy registry、Live adapter、frontend、Motion Task thresholds或任何
既有 receipt。

## 3. Exposure 重建方式

[RESULT] canonical episode row沒有 end-step、elapsed-time或 termination-reason欄位；
episode length只能由 `control_step_trace`長度（等價於 `trace_receipt.control_step_count`）
取得。因此 audit由 trace本身重建 exposure，再與 `trace_receipt` counts及由既有 task
contract導出的 frozen horizon交叉檢查：

```text
control_period_s                  = 1 / 50.0  = 0.02 s
physics_substeps_per_control_step = 500 / 50  = 10
full_exposure_control_steps       = 9.0 * 50  = 450
full_exposure_physics_substeps    = 450 * 10  = 4500
```

每個商與積都必須是 exact integer。`backend/motion_tasks.py`維持 bytes `8892`、SHA-256
`3dd9a47b6798a2fba713eda3654b428377f3a75e825105b233a1da375d4215af`；
`backend/rl/humanoid_env.py`維持 bytes `26277`、SHA-256
`2fc224d67b15d1beb5ea4ffac9b921ce6dc8bf9ce0c87286490bbf655250055d`。

[RESULT] `saturation_duty_pct`的分母與 realized exposure成正比，因此截斷 episode上的
duty不在 full-horizon estimand的同一 measurement support上。這是 measurement-support
問題，不是 statistical-power問題，增加 seeds無法解決。

[RESULT] `outcome_state == OBSERVED`並不代表 full exposure。結束於 `FINAL_STAND`內的
episode仍會回報全部 required numerics，因此在算術上看起來乾淨卻已被 censored。本
receipt以 `18011`（430 steps、全部 required outcomes OBSERVED、仍判為
`EXPOSURE_CENSORED`）保留此 case，並有專屬 test。

## 4. Phase convention amendment（execution前）

[RESULT] Freeze commit規定 recorded `command_phase`對照 contract的
start-of-control-step schedule。`backend/rl/humanoid_env.py:352-353`在 substep loop之後
才推進 `task_elapsed_s`並重新取樣 phase，`:404`保存已推進後的 label，因此 recorded label
採 end-of-step accumulated-time convention。

| Phase | contract control steps | recorder control steps |
|---|---|---|
| `INITIAL_STAND` | 0–49 | 0–48 |
| `START` | 50–124 | 49–123 |
| `STEADY_WALK` | 125–324 | 124–324 |
| `STOP` | 325–399 | 325–399 |
| `FINAL_STAND` | 400–449 | 400–449 |

[RESULT] 累加值在 50步為 `1.0000000000000004`、325步為 `6.499999999999949`、400步為
`7.999999999999917`；`0.002 * 10`、literal `0.02`與 `1.0 / 50.0`是同一個 IEEE 754 double，
所以 accumulation可精確重現。exact multiplication會給出第三種答案，故不採用。

[INFERENCE] 若沿用 freeze commit規則，`AX-04`會因 recording convention差異（而非 data
defect）把有效 bundle誤報為 structurally invalid。因此在任何 audit execution前修正
`AX-04`的對照對象為 reproduced recorder convention，並把 contract與 recorder的逐 phase
邊界差異原樣輸出為 `phase_convention` validity finding，不修改保存資料。修正時尚未執行
任何 audit、也不存在任何 audit output，因此沒有依結果調整 threshold、envelope或 outcome。

## 5. Censoring、bounds 與 comparability

`comparability_state`依固定順序判定：`METHOD_FAILURE_NOT_CENSORING`→
`EXPOSURE_CENSORED`→`COMPARABLE`。

[SOURCE] NIST/SEMATECH把 censoring定義為只知 bound或interval的觀察機制；Wünsch et al.
（Statistics in Medicine 2025）要求保存 method failure的 frequency、reason與 handling。
[RESULT] 因此 non-finite、terminal failure與 no-exposure保留為 method failure而不是
censoring，也不取得 bound。

[SOURCE] 本 repo [Paired Statistics and Paper Export Contract V1](PAIRED_STATISTICS_CONTRACT.md)
已凍結「未凍結 censored estimator前只保存 bound並阻擋一般 mean/bootstrap」。
[RESULT] 本 audit因此對 `COMPARABLE`與 `EXPOSURE_CENSORED` episode輸出 worst-case
identification bounds，不輸出 censored point estimate。此處「assumption-free」限定於：
estimand已由 frozen task contract定義為 full-horizon duty時，bound不再需要任何 censoring
分布假設。

[BLOCKER] estimand本身的存在性仍是 contract約定：對提早終止的 episode，full-horizon duty
是 contract定義的 target，不是「該 episode若能繼續」的可觀測 counterfactual。summary以
`audit_findings.identification_bound_assumption`明示此點。

```text
lower_pct = 100 * over / 4500
upper_pct = 100 * (over + 4500 - observed_substeps) / 4500
paired_lower = candidate_lower - reference_upper
paired_upper = candidate_upper - reference_lower
```

只有 paired bound不含 0時 contrast的 sign才算 identified。aggregate只在 30個 pair全部
`COMPARABLE`時輸出，否則為 null並記
`BLOCKED_EXPOSURE_CENSORED_PAIRS_RETAINED_NO_COMPLETE_CASE_DELETION`；禁止只取
comparable subset，因為 censoring indicator由該臂自身的 early-termination行為產生。

## 6. Synthetic regression 執行結果

Clean-source run：Git pre/post皆為 `4d0709327a03ba2773c8ad05f6051118dda6f54e`，
worktree clean。Package root
`backend/run_traces/v7-exposure-audit-clean-20260908/`，27個 artifacts共 `118218688`
bytes，package receipt SHA-256
`96782c7987af6630be543ee0d18820267e8149f36a21c483526400c86c6519ac`。

三個 case皆回傳 `source_bundle_read_only_verified=true`與 `AUDIT_BUNDLE_VALID`，
且 `python -I -S` replay exact重建 audit summary。前兩個 case回傳
`AUDIT_COMPLETE_RETAINED_CENSORING_BLOCKER`，第三個回傳
`AUDIT_COMPLETE_NO_CENSORING_BLOCKER`。

[BLOCKER] 以下兩個 case的 bundle皆為 synthetic。為維持 schema fidelity，它們沿用
`V7A`／`V7B`／`V7C`這三個 frozen arm identifier，但其 episode長度與 saturation counts都是
本 builder以固定整數算式構造的，**不是** 2026-09-06 pilot的實測值。下列所有數值只描述
audit software的行為，不描述 v7 pilot的實際 exposure分布。

`exposure-censored-case`（synthetic）：

| Arm | exposure steps mean ± SD | comparability | retained bound mean |
|---|---:|---|---|
| V7A | 450.0000 ± 0.0000 | 30 `COMPARABLE` | `[34.974074, 34.974074]%` |
| V7B | 438.3333 ± 60.2342 | 28 `COMPARABLE` / 2 `EXPOSURE_CENSORED` | `[19.594074, 22.186667]%` |
| V7C | 60.0000 ± 0.0000 | 30 `EXPOSURE_CENSORED` | `[0.000000, 86.666667]%` |

| Candidate | pilot reported paired diff | audited paired diff | paired bound mean | sign identified |
|---|---:|---|---|---:|
| V7B | `-14.8712489 ± 0.7032924` pp | `NULL` blocked | `[-15.380000, -12.787407]` pp | 29/30 |
| V7C | `-34.9740740 ± 0.1643473` pp | `NULL` blocked | `[-34.974074, +51.692593]` pp | 0/30 |

[RESULT] V7C的 full-horizon bound寬達 `86.666667` percentage points，其 paired bound
`[-34.974074, +51.692593]` pp包含 0，30個 pair全部 sign-unidentified。因此 0% duty與
其算術 contrast被明示為 `NON_COMPARABLE_EXPOSURE_CENSORED`，`valid_contrast=false`。

[RESULT] V7B有 29/30 pair sign-identified NEGATIVE，但 aggregate仍為 `NULL`，因為 2個
pair被 censored且禁止 complete-case deletion。

[RESULT] `DESCRIPTIVE_ONLY` exposure-matched sensitivity：V7B matched difference
`-14.8783635 ± 0.7127955` pp（matched steps 120/430/450），V7C
`-34.9333334 ± 1.3105817` pp（matched steps全為 60）。此值只顯示 reference被截到同一
exposure時的描述性差異，`informative_censoring=SUSPECTED_DEPENDENT_ON_ARM_BEHAVIOUR`
保留，不得用於 candidate selection、CI、p-value、hypothesis test、恢復 comparability或
sample-size決策。

`method-failure-case`（synthetic）：V7C的 30個 episode為 `FAILED` / `NO_EXPOSURE`，全部歸入
`METHOD_FAILURE_NOT_CENSORING`（`EXPOSURE_CENSORED=0`），bound為 `NULL`，
`method_failure_pair_count=30`。其 paired verdict為
`PAIRED_CONTRAST_NON_COMPARABLE_METHOD_FAILURE`、blocked reason為
`BLOCKED_METHOD_FAILURE_RETAINED_NO_COMPLETE_CASE_DELETION`、
`zero_duty_interpretation`為 `NON_COMPARABLE_RETAINED_METHOD_FAILURE`；成因不再被誤標為
exposure censoring。

`all-comparable-case`（synthetic）：三臂各 30個 episode全部 `FULL_EXPOSURE`且
`COMPARABLE`，但每臂 saturation duty都超過 frozen 30% gate，因此 pilot沒有 eligible
candidate、selection維持 null。audit回傳 `AUDIT_COMPLETE_NO_CENSORING_BLOCKER`、
`censoring_blocker_count=0`、兩個 paired verdict皆 `PAIRED_CONTRAST_COMPARABLE`、
`audited_paired_difference_pct`為 `OBSERVED`，CLI exit `0`。此 case涵蓋 observed-aggregate
與 clean-status分支，先前完全沒有測到。

[RESULT] Audit receipt另記錄產生該 receipt的 replay實作 identity：
`backend/v7_exposure_audit_replay.py`、bytes `79346`、SHA-256
`ae7e0f97c27a0922ddbc7e016c07e882f280e7cd5b0952d94673d2ba05ec4120`。replay script不綁定
frozen hash（它會隨 audit derivation一起改變），但 identity記錄使 retained evidence可追溯到
特定實作而非只有檔名。

## 7. 範圍邊界：frozen pilot bundle 不在本 checkout

[BLOCKER] 2026-09-06的 pilot bundle（14 artifacts / `109520182` bytes / receipt
`sha256:ed3e3eaa7c86f2b855d24aca68b09ce45bce61ac2fb6e573328b12157d758435`）位於
`.gitignore`的 local versioned artifact root，不在 clean checkout內。因此本次無法對
`V7_PILOT_DEVELOPMENT_BUNDLE`執行 audit。

Bundle class以 pilot receipt SHA-256雙向綁定：hash等於上述 frozen值者必須宣告
`V7_PILOT_DEVELOPMENT_BUNDLE`，其他一律必須宣告 `SYNTHETIC_REGRESSION_BUNDLE`，任一
方向不符即 structural failure。本次所有 bundle皆為 synthetic，
`audit_applies_to_frozen_v7_pilot=false`。

[RESULT] 因此本 receipt只支持「audit software在 schema-exact synthetic bundle上行為正確」，
不支持任何關於 frozen v7 pilot實際 exposure分布的敘述。在保有該 bundle的機器上執行：

```text
python backend/v7_exposure_audit_contract.py audit \
  backend/run_traces/v7-action-interface-pilot-clean-20260906 \
  backend/run_traces/v7-exposure-audit-<date>
```

該次執行會自動解析為 `V7_PILOT_DEVELOPMENT_BUNDLE`並使
`audit_applies_to_frozen_v7_pilot=true`；完成後才可把本 audit的結論套用到 v7 pilot。

## 8. 程式驗證與失敗保留

| 驗證 | 結果 |
|---|---|
| 新增 audit targeted suite | `72 passed` |
| Contract 與 replay builder differential sweep（66 cases） | `66/66` 完全一致或同時拒絕 |
| Full backend suite | `337 passed, 2 failed` |
| Clean-tree 重現 2個 failure（`ee73210`，無本次程式） | `2 failed`，確認為既有環境問題 |
| JSON、Python compile、protocol self-consistency | PASS |
| Artifact tracking policy | PASS；無 runtime artifact被 tracked |
| Frontend | 未受影響，`npm run check`不適用 |

[RESULT] `test_p0_contract.py::test_all_minimum_physical_config_compiles_through_rest_and_live_init`
與 `test_v1_analytical_suite.py::test_stdlib_replay_passes_exact_synthetic_fixture`在
clean tree `ee7321090089b186d847a958ae607478b6a12e6c`（不含本次任何程式）同樣失敗。
本容器的 numpy／MuJoCo／pydantic版本高於 pinned set，屬既有
`complete environment lock`缺口，原樣保留，未在本次修改，也未以任何方式繞過。

## 9. 理論與 validity boundary

[SOURCE] NIST/SEMATECH的 censoring只涵蓋「只知 bound或interval」的觀察機制；
Wünsch et al.（Statistics in Medicine 2025）指出 comparison study的 method failure不應
被 silent deletion或一般 missing-data imputation處理。

[SOURCE] Patterson et al.（JMLR 2024）要求 fully specified methods使用 paired differences
並分開 agent/environment RNG；Agarwal et al.（NeurIPS 2021）指出少量 runs只報 point
estimate會低估 statistical uncertainty。

[INFERENCE] 本 audit提供把「截斷後的 0% duty不是改善」從敘述改為可檢查結果的機制：
對 exposure-censored episode輸出 worst-case bound，並以 paired bound是否含 0判定 sign是否
可識別。上述 bound重疊與 0/30 sign-unidentified是 **synthetic** case的數值；2026-09-06
pilot的實際 exposure、bound與 sign identification尚未量測，因此本次不產生任何關於 v7
pilot的數值結論。

[BLOCKER] 沒有 independent training-seed variance、full 11-criterion Live evidence、
actual Study A、frozen censored estimator、binary paired CI、complete environment lock、
immutable storage、HIL、bench或robot evidence；frozen pilot bundle也不在本 checkout。

因此允許的結論只到兩點：(1) exposure-censoring audit software已實作，並在 synthetic
regression上通過 read-only、identity、censoring分類、bounds與 exact replay檢查；(2) 就
`saturation_duty_pct`這個 rate的定義而言，當兩臂 realized exposure不相等時，逐 seed算術差
不落在同一 measurement support上。

[BLOCKER] 第 (2) 點是 metric定義的性質，不是對 2026-09-06 pilot的量測。pilot自身 receipt
已記錄 V7C為 30/30 early fall，但本次未對該 bundle執行 audit，因此其實際 exposure、
identification bounds與 sign identification皆未量測；不得據本 receipt對 v7 pilot的 contrast
下數值結論或可比性判定。
不得宣稱 controller superiority、method-level effect、sample-size adequacy、paper
readiness、physical torque/thermal margin、安全、sim-to-real或實體機器人效能。
`pilot_planning_ready=false`、`method_level_power_ready=false`、`statistics_ready=false`、
`paper_data_ready=false`、`selected_candidate_arm_id=null`。

Primary/official sources：

- [NIST/SEMATECH Censoring](https://www.itl.nist.gov/div898/handbook/apr/section1/apr131.htm)
- [Rethinking the Handling of Method Failure in Comparison Studies, Statistics in Medicine 2025](https://doi.org/10.1002/sim.70257)
- [Empirical Design in Reinforcement Learning, JMLR 2024](https://www.jmlr.org/papers/v25/23-0183.html)
- [Deep RL at the Edge of the Statistical Precipice, NeurIPS 2021](https://proceedings.neurips.cc/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html)
- [IETF RFC 8259 — JSON](https://www.rfc-editor.org/rfc/rfc8259.html)
- [NASA-STD-7009B](https://standards.nasa.gov/sites/default/files/standards/NASA/B/1/NASA-STD-7009B-Final-3-5-2024.pdf)

## 9.1 Review-driven fix pass（2026-09-08）

本 receipt初版後另做一次 adversarial multi-dimension review與 contract／replay differential
sweep，共產生 59個 findings。修正一律為「命名更精確、增加檢查、或縮小主張」，未動任何
threshold、envelope、horizon或 bound formula，數值結果不變。

[RESULT] 已修正的實質缺陷包含：method-failure-only的 arm曾被標為 `EXPOSURE_CENSORED`；
`arms_without_any_comparable_episode`因多餘的 `FULL_EXPOSURE == 0`條件而漏列 arm；
blocker identifier有重複的 `PAIRED_CONTRAST_` 前綴；descriptive sensitivity會把 retained
method failure重新物化為 observed值；no-exposure episode可保留 observed primary outcome；
缺少 selection key被當成 null selection；validation僅比對 hash，因此一份一致地重新蓋章的
receipt可為被改寫的 summary背書。

[RESULT] Differential sweep另發現兩個同名 `build_audit_summary`的 precondition不一致
（contract驗證 raw、pilot summary與 bundle-class binding，replay不驗證），已改為完全一致；
66個 case涵蓋所有 phase boundary、各臂 terminal failure、mixed comparability與 NONFINITE
primary outcome，全部一致或同時拒絕。

[RESULT] 新增的 fixture guard把 synthetic raw payload送進 pilot自身 validator，首次執行即
發現 fixture自行編造了 frozen protocol未宣告的 per-arm `profile_id`／`environment_id`／
`training_run_id`，意即先前 audit是對「真實 pipeline不可能產生的輸入」做測試。已改為直接
取用 frozen protocol的值。

[BLOCKER] Review的 59個 findings中，25個完成 adversarial verification（15 confirmed、
10 refuted）後 workflow被主動停止，因為其 verifier與本地 validation競用 CPU。其餘 findings
由本次直接對照 source與 shipped evidence判定，未逐一取得獨立 verdict。

## 10. 下一步

下一次唯一優先目標是在保有 2026-09-06 bundle的機器上，用本 audit對
`V7_PILOT_DEVELOPMENT_BUNDLE`執行一次 read-only run，記錄真實 exposure分布、
`phase_convention` finding與 identification bounds，並保留原 receipt不回改。該 run完成後，
才另立 fresh DEVELOPMENT protocol考慮 independent training-seed variance。
