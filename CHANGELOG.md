# Changelog

本專案採語意化版本概念記錄可公開的 development releases。所有版本目前仍屬 SIM-only prototype，不表示 physical validation maturity。

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
