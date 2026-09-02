# Experiment matrix completeness V1 implementation receipt（2026-09-03）

執行時間：`2026-09-03 04:32 +08:00`（artifact timestamp：`2026-09-02T20:32:48Z`）

## 1. 唯一目標與 frozen boundary

- Milestone：`PDR4-EXPERIMENT-MATRIX-COMPLETENESS-V1`。
- 唯一目標：實作 [Experiment Matrix Completeness Contract V1](EXPERIMENT_MATRIX_CONTRACT.md)，對 frozen controller × seed × scenario explicit cells做 exact inventory與 identity readback。
- Acceptance criteria：`MX-01`至`MX-10`必須全部通過，才可輸出 `MATRIX_COMPLETE`；strict JSON、spec/index hash、run bundle path/bytes/SHA-256、common/cell identity、missing/duplicate/unexpected/unindexed與 terminal status retention均 fail closed。
- Failure semantics：`FAILED`與`CANCELLED`保留為不同 terminal status；`COMPLETED`不可夾帶 failure record；structural error由 CLI輸出 machine-readable `ERROR` receipt與非零 exit code。不得刪除 negative/null result或調整 frozen gate來取得 PASS。
- Frozen claim：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED; matrix inventory identity only, without controller superiority, sim-to-real, physical fidelity, or safety claims.`

本 milestone不執行 actual Study A、paired statistics、confidence interval、v7 PILOT、HIL、bench或 physical robot validation。

## 2. 完成內容

[RESULT] 新增 `EXPERIMENT_MATRIX_SPEC_V1`、`EXPERIMENT_MATRIX_RUN_INDEX_V1`與 `EXPERIMENT_MATRIX_COMPLETENESS_RECEIPT_V1`，並實作：

- derived canonical seed-schedule hash與 typed scenario equality；
- 1,000-cell schema cap、110,000-entry bounded no-follow scan與 Windows case-variant manifest拒絕；
- exact expected/observed set arithmetic，以及 run ID/path uniqueness；
- 每個 `PAPER_RUN_MANIFEST_V1`與十種 artifact role的 bytes、SHA-256及 identity readback；
- `COMPLETED`／`FAILED`／`CANCELLED`分開計數，且 CANCELLED阻擋 `statistics_input_ready`；
- duplicate JSON key、NaN/Infinity、oversized/pathological integer、deep nesting、symlink/junction與 parser error的 fail-closed處理。

[RESULT] `PAPER_RUN_MANIFEST_V1`同步強化 actual controller identity與 requested label一致性；`COMPLETED`不得夾帶 terminal failure record。

## 3. Clean-source synthetic evidence

Evidence root：`backend/run_traces/matrix-contract-clean-20260902T203248Z`

| Evidence | Readback |
|---|---|
| Source Git SHA | `b8aea995eca0f3a3eff36ff04137ea3dd163f017` |
| Source identity | execution前後 `dirty=false`，SHA不變 |
| Matrix status | `MATRIX_COMPLETE`；expected/indexed/identity-valid = `3/3/3` |
| Terminal statuses | `COMPLETED=1`、`FAILED=1`、`CANCELLED=1` |
| Artifact inventory | `30` artifacts，`873 bytes`；3 manifests共 `12,800 bytes` |
| Matrix spec | `3,706 bytes`；`sha256:3d7b781151f597964149e9736a4c17bde05673034fd35c7f9410098160efd3b0` |
| Run index | `1,048 bytes`；`sha256:198bfbb7c495a3240c4a342ce848daa0175b1373ffaf7a8e6eab9ddf07c3b8fd` |
| Matrix receipt | `4,107 bytes`；`sha256:8ebe7aa2509135143371774147dc85cc35fd5072c046522d1aabf90a74eb4691` |
| Manifest SHA-256 | `sha256:aad4e8bd91fdccc60adab7ed6d3c31590851bbe6597d2c2adf962133e2055ea7`、`sha256:81cabe5e83c90af8584721bb42060d0667134e50ca86ef32c04bd285c9aa22a7`、`sha256:0d2c33fd6ab8dff7a8b6af788588641a131071f7beedf77bdc6c05e0e6ddac8d` |
| Deterministic readback | receipt寫入後重新驗證完全相同 |
| Downstream gates | `statistics_input_ready=false`；`paper_data_ready=false` |

[RESULT] 此 synthetic regression fixture證明 validator可在同一完整 inventory中保留一筆成功、一筆失敗與一筆取消，而不把 terminal failure改標成 success；所有 indexed artifact與 manifest identity均完成 readback。

[INFERENCE] Exact inventory可降低 supplied matrix root內漏報、重複計數與 cherry-pick風險，但不能證明 explicit matrix的科學涵蓋充分、metric正確或 sample size足夠。

[BLOCKER] Fixture的 `metrics.json`保留 synthetic null，沒有產生 controller effect estimate。Raw-to-summary／independent replay的 regression相容性由本次 expanded V1 suite驗證；本 synthetic matrix本身不是新的 dynamics或 performance evidence。

## 4. Tests 與 policy checks

| Verification | Result |
|---|---|
| Matrix + paper-data targeted suite | `51 passed` |
| Matrix + paper-data + V1 raw/analytical replay suite | `101 passed` |
| Full backend（isolated `basetemp`、ignore runtime artifacts） | `220 passed, 5 warnings` |
| Frontend | 未受影響，`npm run check`為 `N/A` |
| Syntax/schema | 4 個 changed Python files AST PASS；`STATUS.yaml` parse PASS |
| Repository policy | diff、11 份 Markdown links、high-signal secret、personal absolute path、conflict marker與 forbidden artifact checks PASS |

五項 full-suite warning是既有 FastAPI `ORJSONResponse` deprecation（4）與 PyTorch `pynvml` FutureWarning（1）；另有既有 `pytest-asyncio`設定 deprecation在 session startup顯示，均未改變 test pass/fail。

## 5. Research basis 與 claim boundary

- [SOURCE] Patterson et al., [Empirical Design in Reinforcement Learning](https://www.jmlr.org/papers/v25/23-0183.html), JMLR 2024：paired comparison、interval reporting與 agent/environment RNG separation是 RL empirical design的重要控制。
- [SOURCE] Agarwal et al., [Deep Reinforcement Learning at the Edge of the Statistical Precipice](https://proceedings.neurips.cc/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html), NeurIPS 2021：少量 runs只報 point estimate不足，應保留 distribution與 interval uncertainty。
- [SOURCE] [IETF RFC 8259](https://www.rfc-editor.org/rfc/rfc8259.html)不允許 JSON NaN/Infinity，並指出 duplicate names的 interoperability風險；[JSON Schema 2020-12 Validation](https://json-schema.org/draft/2020-12/json-schema-validation)的 structural keywords不會自行建立 domain-specific exact cell semantics。
- [SOURCE] [Center for Open Science preregistration guide](https://www.cos.io/blog/choosing-preregistration-template-guide-for-researchers)將 preregistration描述為資料分析前的 time-stamped、read-only plan。

[INFERENCE] 因此本 milestone只稱 internal frozen/hash-bound contract，不借稱 external preregistration；statistics與 paper export必須由下一個獨立 contract處理。

[BLOCKER] Actual Study A matrix、orchestrator、immutable storage、formal authorization、paired estimand/CI、binary interval、censoring/null semantics與 table/figure schema均未完成。PDR-4只達到 software validator implemented，不是 scientific coverage PASS。

## 6. 下一次唯一優先目標

凍結並實作 paired statistics／confidence interval與 paper table/figure input contract；先以 synthetic/REGRESSION matrix驗證 pairing、FAILED/CANCELLED、null/censoring與 machine-readable export semantics，不啟動 actual Study A或 v7 PILOT。
