# Paired Statistics / Paper Export V1 Implementation Receipt

日期：2026-09-05

狀態：`BOUNDED SOFTWARE CONTRACT VERIFIED / SCIENTIFIC GATE NOT PASS`

證據範圍：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`

## 1. 本次唯一目標

凍結並實作 `PDR6-PDR8-PAIRED-STATISTICS-EXPORT-V1`：對已通過
matrix identity/completeness gate的 two-controller matrix，產生 failure-retaining
paired raw table、continuous effect/bootstrap CI、binary descriptive counts、machine-readable
paper table/figure inputs，並由另一個 stdlib-only process exact replay。

本次未執行 actual Study A、v7 PILOT、FORMAL_EVALUATION/HOLDOUT、
power/sample-size decision或任何 HIL/bench/robot validation。

## 2. Frozen acceptance、failure semantics and claim boundary

- Acceptance：[Paired Statistics and Paper Export Contract V1](PAIRED_STATISTICS_CONTRACT.md)
  的 `PS-01..PS-12`，包含 strict/bounded JSON、exact pair map、source/matrix/run/raw
  identity、observation-state retention、effect/CI、artifact inventory與 `python -I -S`
  replay。
- Structural error：schema/identity/path/bytes/hash/replay mismatch、duplicate key、
  non-finite JSON或 workload/size超界導致 CLI exit 2，不信任 partial output。
- Semantic blocker：CANCELLED、minimum-pair不足或 outcome出現
  NULL/NONFINITE/CENSORED時保留machine-readable blocker，不對該outcome補值或
  silent complete-case；contract-valid但 inference blocked時 CLI exit 1。
- FAILED：保留run、failure count與denominator。只有預先凍結為terminal
  task-failure的binary outcome可要求explicit observed false；aggregator不自行把missing
  轉false。
- Claim boundary：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED; paired statistical
  software output only, without Study A or formal authorization, controller superiority,
  sim-to-real, physical fidelity, safety, or paper-acceptance claims.`

## 3. 實作與 source identity

Clean implementation source SHA：
`a36b230de28c9f00f495027539c9266b22a9ec15`

Source pre/post的SHA相同，`source_dirty_pre=false`、`source_dirty_post=false`。

主要實作：

- `backend/paired_statistics_contract.py`：spec/metrics/raw/summary/table/figure/receipt
  schemas、primary aggregator、bundle validator與CLI exit semantics。
- `backend/paired_statistics_replay.py`：僅stdlib的independent recomputation，不載入
  Pydantic、NumPy、MuJoCo、controller或primary evaluator module。
- `backend/build_paired_statistics_regression_bundle.py`：clean-source synthetic aggregate
  與cancelled regression package builder。
- `backend/test_paired_statistics_contract.py`：frozen arithmetic、identity、tamper、
  retention、timeout/workload與CLI failure semantics tests。

## 4. Clean-source evidence

Local ignored evidence root：
`backend/run_traces/paired-statistics-v1-clean-20260905T034905Z`

Package receipt：

- path：`regression_package_receipt.json`
- bytes：41040
- SHA-256：`sha256:c3b860ce70690a1ed855e475f72cfc4da83d236a6e71dd3fdec93ec9a834ebf1`
- indexed artifacts：191
- indexed artifact bytes：297961
- inventory readback：191/191 path、bytes、SHA-256 exact；0 unindexed；0 reparse point

Aggregate case：

- `validation_status=STATISTICS_CONTRACT_VALID`；`contract_valid=true`。
- `PS-01..PS-12=true`；`paper_inputs_generated=true`。
- aggregate inventory：6 artifacts / 170487 bytes；receipt
  `sha256:4b280c705ab9086ac556e7e3577199d380c2f0466e53f9b9a4d669a28bed61f3`。
- stdlib replay：`PASS / exact_identity=true`；raw table
  `sha256:3520a69fe2abb6259eceb6dec0c6bb8ecba0b582f1be2a8a0425b33557301cf1`
  與summary
  `sha256:9a9f5b91a97758686cc9035f6efcb728c3cf4fd8abeb8cb62249ea0a523ea6c2`
  均與stored receipt吻合。
- retention：aggregate保留 `FAILED`、negative、`NULL`、`NONFINITE`、
  `CENSORED`；reference `COMPLETED=4`，candidate `COMPLETED=3 / FAILED=1`。
- synthetic arithmetic fixture：`path_error_m` candidate-minus-reference mean
  `-0.07500000000000001`，95% deterministic paired-bootstrap CI
  `[-0.25, 0.049999999999999996]`。這只是formula/replay oracle，不是controller
  performance result。
- binary：paired risk-difference point estimate與2×2 counts保留，但paired CI
  為 `null / PAIRED_BINARY_CI_NOT_IMPLEMENTED_V1`。
- 結果：`statistics_ready=false`、`paper_data_ready=false`。

Cancellation case：

- `CELL-CAND-004` 保留為 `CANCELLED`，結果為
  `BLOCKED_UPSTREAM_MATRIX`。
- blocked receipt artifact integrity通過：1 artifact / 6682 bytes，receipt
  `sha256:44ea61d14e1fd14fb0bc8f869c192624d241ee1626a254acb5ab3bce287209f8`。
- `AGGREGATE_BUNDLE_VALID` 對此case只表示blocked receipt的artifact integrity
  有效；`contract_valid=false`、`statistics_ready=false`，不表示statistics或outcome
  有效。

## 5. Tests and policy checks

- Targeted paired-statistics suite：`27 passed in 14.70s`。
- Expanded statistics/matrix/paper-data/V1 evidence suite：`127 passed in 111.09s`。
- Full backend suite：`246 passed, 5 warnings in 172.72s`；warnings為既有
  FastAPI `ORJSONResponse` deprecation與Torch `pynvml` future warning。
- Python compile、YAML parse、Git diff whitespace、conflict-marker、secret、personal
  absolute-path與tracked artifact-policy checks：PASS。
- Frontend未修改；`npm run check` 不適用。

## 6. Evidence interpretation

[SOURCE] Patterson et al. (JMLR 2024) 支持fully specified methods的paired
differences與interval reporting；Fay and Lumbard (2021)、Newcombe (1998)與Chang
et al. (2022) 說明matched-pair binary CI不能以marginal intervals取代；Wünsch
et al. (2025) 支持將method failure及其handling明示保留。完整來源與
method boundary見 [Paired Statistics and Paper Export Contract V1](PAIRED_STATISTICS_CONTRACT.md)。

[RESULT] Synthetic contract的pairing、continuous arithmetic/bootstrap、state retention、
paper-input serialization、artifact identity與independent replay通過。

[INFERENCE] 這只支持bounded software correctness與traceability；同一trained
checkpoint下的pair-level bootstrap最多是conditional scenario/evaluation estimand，不會
自動成為training-population inference。

[BLOCKER] Actual Study A matrix、validated matched-pair binary CI、independent
training-level resampling unit、PILOT variance/power/sample-size decision、P1/V1、V3、
project-wide immutable storage與formal authorization均未完成。

## 7. 下一個唯一優先目標

v7 action-interface DEVELOPMENT PILOT：先凍結 reward-only、joint-specific action
envelope與 action low-pass/rate-limit 的 protocol、seeds、acceptance criteria、failure
semantics與claim boundary，再以 DEV 18000–18029 執行 bounded PILOT。19000–19029
維持retired；formal 20000–20029維持sealed。不啟動FORMAL/HOLDOUT、不依
結果放寬現有Motion Task threshold，PILOT只用於variance/power/sample-size
planning。
