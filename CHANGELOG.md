# Changelog

本專案採語意化版本概念記錄可公開的 development releases。所有版本目前仍屬 SIM-only prototype，不表示 physical validation maturity。

## Unreleased — 2026-09-08 (c)

- 對 2026-09-06 保存的 `V7_PILOT_DEVELOPMENT_BUNDLE` 執行 `AUDIT-V7-EXPOSURE-CENSORING-V1` 的第一次 read-only run，完成 exposure-censoring validity audit V1 的 data 部分。`audit_applies_to_frozen_v7_pilot=true`、`AX-01..AX-12` 全通過、14 個 artifact／`109520182` bytes 在前後 readback 一致且 file set 不變，`source_bundle_read_only_verified=true`，CLI 依 frozen semantics 回傳 exit `1` 並保留 35 個 censoring blocker。
- 實測 exposure：V7A 30/30 `FULL_EXPOSURE`（恰 450 control steps，sd 0）；V7B 27 full + 3 `EARLY_TERMINATED`（420／445／426 steps，`8.4`／`8.9`／`8.52` s，全落在 `FINAL_STAND`）；V7C 30/30 `EARLY_TERMINATED`（`159.7000 ± 2.7687` steps、`3.08–3.30` s、占 horizon `0.354889`，全落在 `STEADY_WALK`）。
- V7C 的 0% duty 經 assumption-free full-horizon bound 量測為 `[0.0, 64.511111]`%，與 V7A 的 `36.2185185`% 重疊；paired bound `[-36.2185185, +28.2925927]` 包含 0，`0/30` pair 方向可識別。pilot 報出的 `-36.2185185` pp 因此被量測確認為 exposure artifact，而非 saturation 改善 —— 這項判斷從敘述變成結果。
- V7B 的 paired bound 在 `30/30` pair 全部排除 0 且皆為 NEGATIVE，即使含 3 個 censored pair；aggregate 仍為 `NULL`（`BLOCKED_EXPOSURE_CENSORED_PAIRS_RETAINED_NO_COMPLETE_CASE_DELETION`）。此方向穩健性不構成 candidate selection、不解除 V7B 的 ineligibility，也不改變單一 training seed 的限制。
- 獨立交叉驗證：audit 只由 `control_step_trace` 長度導出 exposure（不讀 gate 結果、不讀 `fell` flag），卻還原出與 pilot 紀錄一致的跌倒 seed 集合 `{18015, 18021, 18023}`，並正確地把 stop-only 失敗的 `18011` 留在 `FULL_EXPOSURE / COMPARABLE`。
- 實測盲點確認：V7B 那 3 個 censored episode 的 `outcome_state` 全為 `OBSERVED` —— 它們在 `FINAL_STAND` 內才終止，六項 required numeric 皆有值、`reason` 為 null，算術上看不出異常。`outcome_state == OBSERVED` 不蘊含 full exposure。
- `AX-04` 在真實資料上通過：90 個 episode 的每一筆 recorded `command_phase` 都等於重現的 end-of-step accumulated recorder convention。該 convention 相對 contract 的 start-of-step schedule 位移一個 control step，只影響 `INITIAL_STAND`／`START`／`STEADY_WALK` 邊界，原樣保留為 validity finding。若沿用 protocol freeze commit 的原始規則，本次 run 會在 `k=49` 誤判為 structural failure。
- Descriptive exposure-matched sensitivity：V7B `-12.9968027 ± 1.0755263` pp（k 420–450）、V7C `-21.9635049 ± 1.2888118` pp（k 154–165）。截斷對齊後差值未消失，但仍為 `DESCRIPTIVE_ONLY` 且 informative censoring 依然存在，不得用於 selection、CI 或 sample-size。
- 新增 [frozen bundle receipt](docs/V7_EXPOSURE_CENSORING_AUDIT_FROZEN_BUNDLE_RECEIPT_2026-09-08.md)；2026-09-06 pilot receipt 與 synthetic regression receipt 皆未回改。`PAPER_DATA_READINESS` 的 PDR-5／PDR-6 與立即執行順序第 9 項更新為 DONE，第 10 項改為 independent training-seed variance protocol。
- 保留的 blocker 未變：`selected_candidate_arm_id=null`、`pilot_planning_ready=false`、`method_level_power_ready=false`、`statistics_ready=false`、`paper_data_ready=false`、`formal_sample_size_decision=BLOCKED_INDEPENDENT_TRAINING_SEED_VARIANCE_NOT_ESTIMATED`。

## Unreleased — 2026-09-08 (b)

- 對已合併的 exposure-censoring audit執行一次 adversarial multi-dimension review與 contract／replay differential sweep，共 59個 findings；修正一律為「命名更精確、增加檢查、或縮小主張」，未動任何 threshold、envelope、horizon或 bound formula，既有數值結果不變。
- 修正 cause mislabel：method-failure-only的 arm曾被標為 `EXPOSURE_CENSORED`。verdict與 blocked reason改為分別區分 exposure censoring、method failure與混合成因。
- 修正 `arms_without_any_comparable_episode`的多餘 `FULL_EXPOSURE == 0`條件，該條件會讓「有 full exposure但沒有任何 comparable episode」的 arm被漏列，使 summary可能讀成「所有 arm皆可比較」。
- 修正 shipped evidence中重複的 `PAIRED_CONTRAST_` 前綴；修正 descriptive sensitivity會把 retained method failure重新物化為 observed值；no-exposure episode不再允許保留 observed primary outcome；缺少 selection key不再被當成 null selection。
- `validate_v7_exposure_audit_bundle`原本只比對 hash與 receipt-versus-summary，因此一份一致地重新蓋章的 receipt可為被改寫的 summary背書。改為由 summary自身 retained comparability states重新導出 blocker list，並把 applicability flag綁定到 bundle class。
- Differential sweep發現兩個同名 `build_audit_summary`的 precondition不一致（contract驗證 raw、pilot summary與 bundle-class binding，replay不驗證），已改為完全一致；66個 case涵蓋所有 phase boundary、各臂 terminal failure、mixed comparability與 NONFINITE primary outcome，結果 `66/66`一致或同時拒絕。
- Integrity強化：replay的 check inventory凍結並要求完全相符（原本任何 all-true dict即可通過 AX-11）、replay把輸入檔綁定到 audited receipt inventory、replay receipt的 boolean改型別嚴格比較（`1 == True`）、`V7_PILOT_DEVELOPMENT_BUNDLE`必須保留 pinned audited protocol hash、audited bundle的 file set在前後比對、directory scan對不可讀子樹 fail closed、輸出寫入拒絕跟隨 link、output/source root另比對 filesystem identity。
- 縮小主張：receipt原本斷言 v7 pilot的 contrast不具內部可比性，但本次從未讀取該 frozen bundle、也未量測；已改為只陳述 software已驗證與 metric定義層面的性質，並明示 pilot實際 exposure與 bounds未量測。synthetic表格另加註為 synthetic，因其沿用 frozen `V7A`／`V7B`／`V7C` identifier。identification bounds的 estimand存在性約定改為明示；replay的 exact-identity改為說明它證明什麼（summary忠實於 retained rows）與不證明什麼（共用推導規則本身的正確性）。
- Tests由 38增至 72。新增的 fixture guard把 synthetic raw送進 pilot自身 validator，首次執行即發現 fixture編造了 frozen protocol未宣告的 per-arm identifier，意即先前 audit是對真實 pipeline不可能產生的輸入做測試。另補上先前無法到達的 zero-blocker clean status／observed aggregate／CLI exit 0路徑、partial-exposure method failure、duplicate／unexpected seed、arm-inventory mismatch、post-audit source drift與夾帶檔案、forged replay receipt，以及以重新索引 output receipt到達的 validator語意檢查。
- Clean source `4d0709327a03ba2773c8ad05f6051118dda6f54e`重新產生 evidence：27 artifacts / `118218688` bytes，package receipt `sha256:96782c7987af6630be543ee0d18820267e8149f36a21c483526400c86c6519ac`；三個 case皆 `AUDIT_BUNDLE_VALID`與 read-only verified，兩個保留 censoring blocker、一個 blocker為 0。
- 59個 findings中 25個完成 adversarial verification（15 confirmed、10 refuted）後主動停止該 workflow，因其 verifier與本地 validation競用 CPU；其餘由直接對照 source與 shipped evidence判定。`paper_data_ready=false`等 blocker全部保留。

## Unreleased — 2026-09-08

- 先以 Git `ee7321090089b186d847a958ae607478b6a12e6c`凍結 `AUDIT-V7-EXPOSURE-CENSORING-V1`：read-only contract、bundle class binding、由既有 task contract導出的 exposure horizon、censoring/method-failure vocabulary、assumption-free identification bounds、`AX-01..AX-12`與 `SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED / DEVELOPMENT_ONLY` boundary。
- 新增 stdlib-only audit contract、獨立 `python -I -S` replay、38個 synthetic fail-closed tests與 clean-source regression builder；刻意不從 `v7_pilot_contract` import任何東西，避免沿用被 audit pipeline自身的 validator與假設。
- Canonical episode row沒有 end-step、elapsed-time或 termination-reason欄位，因此 episode length只能由 retained `control_step_trace`取得；audit由 trace重建 termination control step／sim time／phase，再與 `trace_receipt` counts及 frozen `9.0 s / 450 steps / 4500 substeps` horizon交叉檢查。每個商與積必須是 exact integer。
- Execution前修正 `AX-04`：`backend/rl/humanoid_env.py:352-353`在 substep loop之後才推進 `task_elapsed_s`並重新取樣 phase，recorded label採 end-of-step accumulated-time convention（邊界 `0–48 / 49–123 / 124–324`而非 `0–49 / 50–124 / 125–324`）。沿用 freeze commit規則會因 recording convention差異把有效 bundle誤報為 structurally invalid。改為對照 reproduced recorder convention，並把 contract與 recorder的邊界差異輸出為 `phase_convention` validity finding；未依結果調整任何 threshold、envelope或 outcome。
- Method failure（`NULL`、`NONFINITE`、terminal failure、no exposure）保留為 method failure且明示不是 censoring；exposure-censored primary outcome改輸出 assumption-free worst-case full-horizon與 paired identification bounds，不輸出 censored point estimate。aggregate只在30個 pair全部 comparable時輸出，否則 null並記 `BLOCKED_EXPOSURE_CENSORED_PAIRS_RETAINED_NO_COMPLETE_CASE_DELETION`。
- Clean source `428ba214ec7d9e85c254b3b4f85d2c417094d202`的 synthetic package列入 18 artifacts / `68338712` bytes，receipt `sha256:15c2aef746edc2976a30f186180f32ba3c2c2ebcb6e30f1e08a5a2bf1a4b1415`；兩個 case皆 `AUDIT_COMPLETE_RETAINED_CENSORING_BLOCKER`、`source_bundle_read_only_verified=true`、`AUDIT_BUNDLE_VALID`，replay exact。
- Synthetic結果顯示 60/450 steps且零 saturated substeps的臂 full-horizon bound為 `[0.000000, 86.666667]%`，其 paired bound `[-34.974074, +51.692593]` percentage points包含 0，30個 pair全部 sign-unidentified；`valid_contrast=false`。另一臂29/30 pair sign-identified NEGATIVE，但因2個 pair被 censored，aggregate仍為 null。
- `DESCRIPTIVE_ONLY` exposure-matched sensitivity保留 `informative_censoring=SUSPECTED_DEPENDENT_ON_ARM_BEHAVIOUR`，不得用於 candidate selection、CI、p-value、hypothesis test、恢復 comparability或 sample-size決策。
- 2026-09-06 pilot bundle在 `.gitignore`的 local artifact root、不在 clean checkout內，因此本次無法對 `V7_PILOT_DEVELOPMENT_BUNDLE`執行 audit。Bundle class以 pilot receipt SHA-256雙向綁定，所有本次 bundle皆為 `SYNTHETIC_REGRESSION_BUNDLE`且 `audit_applies_to_frozen_v7_pilot=false`。
- 新增 audit suite為 `38 passed`，完整 backend為 `337 passed, 2 failed`。兩個 failure在 clean tree `ee7321090089b186d847a958ae607478b6a12e6c`（不含本次任何程式）同樣失敗，屬既有 environment lock缺口，原樣保留未繞過。
- 未重訓、未新增 seed、未調 alpha/envelope/threshold、未開啟 FORMAL/HOLDOUT、未選 candidate、未計 CI或 p-value；原 pilot receipt未回改。下一個唯一目標是在保有 2026-09-06 bundle的機器上對 `V7_PILOT_DEVELOPMENT_BUNDLE`執行一次 read-only audit run。

## Unreleased — 2026-09-06

- 先以 Git `e839aa263b391ade21bbfc61c50123a9ca384df4`凍結 `PILOT-V7-ACTION-INTERFACE-DEV-V1`：三臂 action math、common training seed 8700、DEV 18000–18029、retired/formal seed ranges、acceptance、failure semantics與 `SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED / DEVELOPMENT_ONLY` boundary。
- 新增 v7 action-interface runtime、`RL_TRAINING_PROFILES_V4`三個 profiles、strict training/evaluation CLI、requested/applied action與每個control step的500 Hz saturation aggregate counts、14-artifact bundle validator及 `python -I -S` stdlib-only raw-to-summary replay；未修改 policy registry、Live adapter或 frontend。
- Clean source `058657dd43d28a9175e54362cf4d0a0618507c38`完成三臂各122880 training steps及30個DEV episodes：V7A saturation `36.2185185 ± 1.0328300%`；V7B `23.3896264 ± 1.0044698%`，paired B−A `-12.8288921 ± 1.0720320` percentage points，但保留4個 negative episodes而不 eligible。
- V7C 30/30 early fall，required outcomes全數保留為 NULL；倒下前0% saturation與 paired arithmetic contrast不得解讀為改善。Selection為 `PILOT_RETAINED_SEMANTIC_BLOCKER`，candidate null、pilot planning/method-level power/paper data均 false。
- Bundle列入14 artifacts / `109520182` bytes，receipt `sha256:ed3e3eaa7c86f2b855d24aca68b09ce45bce61ac2fb6e573328b12157d758435`；path/bytes/SHA-256/source/policy identities與六項 independent replay checks通過。Frozen semantic blocker使builder/validator exit 1，並非 structural invalidity。
- Final targeted為 `54 passed, 1 warning`，quiescent完整 backend為 `301 passed, 5 warnings`。另保留一輪 concurrent source edit造成的 `274 passed / 20 failed`無效結果；frontend未受影響。
- 未開啟FORMAL/HOLDOUT、未放寬 threshold、未重標 failures。下一個唯一目標是只讀既有 bundle的 V7 early-termination / exposure-censoring validity audit V1；不重訓、不新增 seed、不調 alpha/envelope/threshold。

## Unreleased — 2026-09-05

- 新增 frozen `PAIRED_STATISTICS_SPEC_V1`、per-run metrics、paired raw table、statistics summary、paper table/figure inputs、aggregate receipt與 stdlib-only replay schemas。
- Continuous outcome輸出 candidate-minus-reference mean/median、Cohen dz與 deterministic paired percentile-bootstrap CI；binary outcome保留 2×2 counts、risk-difference point estimate與 marginal Wilson descriptions，paired CI明示 `PAIRED_BINARY_CI_NOT_IMPLEMENTED_V1`。
- `FAILED`、`CANCELLED`、negative、`NULL`、`NONFINITE`與 `CENSORED` 均保留；nonobserved outcome不做 silent complete-case/imputation，CANCELLED在 upstream fail closed。
- Aggregate對 spec/index/source/run/controller/scenario/seeds、manifest/metrics/raw trace identity、path/bytes/SHA-256、unindexed file、reparse point與 read-during-build drift重新驗證；`python -I -S`另一process對 raw-to-summary/table/figure exact replay。
- Clean source `a36b230de28c9f00f495027539c9266b22a9ec15` 的 synthetic package列入 191 artifacts / 297961 bytes，receipt `sha256:c3b860ce70690a1ed855e475f72cfc4da83d236a6e71dd3fdec93ec9a834ebf1`；contract valid，但 `statistics_ready=false`、`paper_data_ready=false`。
- Targeted statistics tests為 `27 passed`，expanded evidence tests為 `127 passed`，完整 backend為 `246 passed, 5 warnings`；frontend未受影響。
- 未執行 Study A、v7、FORMAL/HOLDOUT、HIL/bench/robot或 physical validation；下一個唯一目標是 v7 action-interface DEVELOPMENT PILOT。

## Unreleased — 2026-09-03

- 新增 frozen `EXPERIMENT_MATRIX_SPEC_V1`與 run-index contract，explicit 保存 controller、training/evaluation/environment/scenario seeds、scenario/replicate labels、resolved config及 common protocol/environment/model identities。
- 新增 fail-closed matrix validator：bounded strict JSON、spec hash、derived canonical seed-schedule hash、typed scenario equality、1,000-cell schema cap、dedicated-root no-follow scan、Windows case-variant manifest拒絕、per-run bundle path/bytes/SHA-256 readback，以及 missing/duplicate/unexpected/unindexed/tamper/identity drift檢查。
- `COMPLETED`、`FAILED`、`CANCELLED`逐 cell保留；CANCELLED可維持 inventory complete但阻擋 `statistics_input_ready`，matrix receipt固定 `paper_data_ready=false`。
- `COMPLETED`不得夾帶 failure record；claim boundary改為 exact frozen wording，避免以 contradictory suffix繞過 SIM-only boundary。
- 強化 `PAPER_RUN_MANIFEST_V1` readback：拒絕 duplicate JSON keys、NaN/Infinity及 requested controller label與 actual controller identity不一致。
- Matrix tests以 synthetic bundles覆蓋 exact、negative/null與 CLI failure semantics；未執行 actual Study A、statistics、v7 PILOT或 physical validation。
- Clean-source synthetic receipt綁定 Git `b8aea995eca0f3a3eff36ff04137ea3dd163f017`：3/3 identity-valid cells保留 `COMPLETED=1`、`FAILED=1`、`CANCELLED=1`，receipt SHA-256為 `8ebe7aa2509135143371774147dc85cc35fd5072c046522d1aabf90a74eb4691`；`statistics_input_ready=false`、`paper_data_ready=false`。
- Targeted matrix/paper-data為 `51 passed`，expanded V1 replay為 `101 passed`，完整 backend為 `220 passed, 5 warnings`；frontend未受影響。
- 下一個唯一 paper-data milestone為 paired statistics/CI與 paper table/figure input contract。

## Unreleased — 2026-09-02

- 新增 frozen V1 analytical fixture：passive exact single-support、centered 5 kg simulated payload與 4/2/1 ms grid-refinement共 4 cases。
- Primary保存 exact config/MJCF/model package、full raw state/applied force/solver/contact frame/6-D wrench/relative Jacobians；stdlib-only process不讀 primary PASS，從 raw與 model package完整重算。
- Frozen acceptance、failure/cancel/non-finite semantics與 `SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED` claim boundary在首次執行前寫入 versioned spec；threshold未因結果放寬。
- Clean-source bundle綁定 Git `b39a5ea2524a10189959d4968a9a7e15747fbf59`，primary/replay 4/4 PASS；payload mass error為 0、GRF increment relative error為 `1.303748139009358e-15`。
- 4/2/1 ms normalized-GRF QoI通過 grid-stability gate；successive differences進入 round-off區，因此 observed order保留為 `null / ROUND_OFF_LIMITED`。
- 10-role bundle的 path/bytes/SHA-256、exact model content與 pre/post source identity readback通過；狀態仍為 `REGRESSION_BUNDLE_VALID_ONLY / paper_data_ready=false`。
- 下一個 paper-data milestone凍結為 experiment matrix completeness validator；paired statistics/CI與 v7 PILOT不得提前取代它。

- V1 static contact oracle V4：1000-step/500 Hz raw evidence、16 項 frozen criteria，既有 thresholds未變。
- 依 compiled `PYRAMIDAL` cone 與 `condim=3` 重算 friction utilization。
- 由 aggregate foot wrench 在 foot-local sole plane 重算 CoP/support margin。
- 每個 contact新增 `body2 - body1` 的 `3 × nv` translational/rotational Jacobians與 frozen `adhesion_n == 0` precondition；移除 per-contact `generalized_force` raw receipt。
- stdlib-only replay完全不載入 MuJoCo/controller，改由 raw Jacobians、contact frame與6-D wrench重建 generalized force；14 項 replay criteria另涵蓋全 trace closure、absolute time grid與 evaluation count，primary metrics保持一致。
- 新增 paper-data-first architecture、`PAPER_RUN_MANIFEST_V1`、formal HOLDOUT/seed/clean-source gates與 path/size/SHA-256 artifact validator。
- V1 static oracle可產出10-role integrity-valid regression bundle；primary exception/non-finite result與 replay `FAIL`/process/schema error會保留為 failed bundle、diagnostic artifact與 failure record；validator明確回報 `REGRESSION_BUNDLE_VALID_ONLY`，不偽裝成 formal paper result。
- Bundle builder不信任 primary/replay自報 PASS；exact 16/14 criterion mapping、frozen raw/model fields、model.xml SHA-256與 pre/post Git identity皆 fail closed。
- 保留證據邊界：Jacobian與wrench仍是 same-engine MuJoCo receipts；single-support、known-payload、dynamic contact、independent contact model、convergence、energy與 physical validation仍未完成。

## 0.1.0 — 2026-08-29

第一個公開版本：

- 分析模式：prescribed kinematics、analytical GRF/contact schedule、inverse dynamics 與 design-screening outputs。
- 即時互動：MuJoCo forward dynamics、simulated contact、Track／Raibert／RL controllers。
- 三機同步比較：三個獨立 plants、相同命令、同步 simulation time、assist 預設 OFF。
- Dynamic Run Trace V1：500 Hz bounded NPZ/manifest、SHA-256 validation 與 Analysis readback。
- Motion Task V1：`stand → start → steady walk → stop`、固定 gait/phase 與 11 項可量測 criteria。
- Versioned RL policy registry 與固定速度 training profiles；歷史 training outputs 不納入 repository。
- 101 個 backend tests 與 frontend TypeScript/production build verification。

已知限制：

- V0 尚未 PASS；缺 immutable evidence bundle、environment lock 與獨立 validator。
- 第一組三 controller Motion Task development baseline 均為 FAIL。
- 模型未經實體校準，內建 hardware catalog 為 representative demo data。
