# Experiment Matrix Completeness Contract V1

最後更新：2026-09-05

狀態：`FROZEN / PDR-4 SOFTWARE CONTRACT IMPLEMENTED`

證據範圍：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`

## 1. Bounded milestone

Milestone ID：`PDR4-EXPERIMENT-MATRIX-COMPLETENESS-V1`

本 milestone 只建立 fail-closed experiment-matrix completeness validator，回答：

> 凍結的 expected controller × training seed × evaluation seed × scenario cells，是否各有且僅有一個 integrity-valid `PAPER_RUN_MANIFEST_V1` bundle，且沒有遺漏、重複、未預期或未索引 run？

本 milestone 不執行 Study A、v7 PILOT、controller ranking、statistics、confidence
interval、power analysis或 paper table/figure export，也不解除 P1/V1、PDR-6 或 V3 gate。

## 2. Frozen inputs

Validator 讀取同一 dedicated matrix root 下的兩個 strict JSON files：

1. `experiment_matrix.json`：`EXPERIMENT_MATRIX_SPEC_V1`，凍結 common identity、
   claim boundary與 explicit expected cells。
2. `experiment_matrix_run_index.json`：`EXPERIMENT_MATRIX_RUN_INDEX_V1`，保存
   matrix-spec SHA-256及每個 run manifest的 cell ID、run ID、relative path、bytes與
   SHA-256。

每個 expected cell 明定：

- `cell_id`、`scenario_id`、`replicate_id`；
- controller family、controller identity與 artifact SHA-256；
- `deterministic`、training/evaluation/environment/scenario seeds；
- resolved-config SHA-256與 exact scenario factor map。

每個 matrix spec 明定：

- experiment/protocol/RQ/hypothesis/task identity；
- run class、data partition、source Git SHA與 clean-source requirement；
- plant、protocol artifact、environment artifact、metric set、evaluator、seed
  schedule、primary/secondary outcomes；
- assist/tuning policy；
- canonical expected-cell seed schedule SHA-256；此 hash由排序後的 cell/controller/
  training/evaluation/environment/scenario seed與 scenario fingerprint重算，不接受任意
  self-reported digest；
- exact expected-cell count與 `SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`
  claim boundary。

## 3. Frozen acceptance criteria

| ID | Acceptance criterion |
|---|---|
| `MX-01` | Spec、index與 run manifests均以 bounded strict JSON讀取；unknown fields、duplicate keys、NaN、infinity、pathological integer或 nesting parser failure均 fail closed。V1 matrix cell上限為 1,000。 |
| `MX-02` | Spec與index位於同一 matrix root；index保存的 spec SHA-256必須與實檔完全一致。 |
| `MX-03` | `expected_cell_count`必須等於 explicit cell數；`cell_id`、canonical logical cell tuple與 derived seed-schedule hash各自 exact。Scenario numeric equality將 `0`/`0.0`/`-0.0`正規化，但 boolean與number保持不同 type。 |
| `MX-04` | 每個 indexed `paper_run_manifest.json` path必須是 root內 canonical POSIX relative path，且 bytes、SHA-256與 `PAPER_RUN_MANIFEST_V1` artifact readback全部一致。 |
| `MX-05` | 每個 run的 common identity、protocol/environment/model artifacts及 cell-specific controller/resolved-config/seeds/scenario必須與 frozen spec exact match；requested label不得取代 actual identity。 |
| `MX-06` | 每個 expected cell恰有一個 run；missing、duplicate或 unexpected cell均使 `matrix_complete=false`。 |
| `MX-07` | Indexed manifest path與 actual `run_id`各自唯一；matrix root採 bounded no-follow scan，任何未列入 index 的 `paper_run_manifest.json`、大小寫異體、symlink、junction、scan error或上限超出均 fail closed。 |
| `MX-08` | `COMPLETED`、`FAILED`、`CANCELLED`逐 cell保存並分開計數；FAILED/CANCELLED不是 missing，也不得刪除、補值或改標成 completed。 |
| `MX-09` | Receipt保存 spec/index hashes、expected/indexed/validated counts、status counts、missing/duplicate/unexpected/unindexed/invalid/identity-mismatch清單；`paper_data_ready`固定為 false。 |
| `MX-10` | Library對 semantic incompleteness回傳 machine-readable FAIL receipt；CLI對 FAIL或 structural error回傳非零 exit code。 |

只有 `MX-01` 至 `MX-10` 全部成立時，receipt才可回報
`validation_status=MATRIX_COMPLETE`與 `matrix_complete=true`。此 PASS僅表示
inventory/completeness identity成立；FAILED/CANCELLED outcome仍原樣保留，且不等於
scientific outcome PASS。

## 4. Frozen failure semantics

- Spec/index schema、duplicate key、non-finite value、spec hash、path、bytes、SHA-256
  或 bundle integrity失敗：fail closed，不信任該 run。
- Missing、duplicate、unexpected、unindexed run或 identity drift：輸出 FAIL receipt並
  列出 exact cell/path；不得自動刪除或挑選較有利的 run。
- `FAILED`與`CANCELLED` run若有完整 failure record及 artifact bundle，仍算已保留的
  expected cell；receipt分別列入 `failed_cells`與`cancelled_cells`，不得當作 success。
  `CANCELLED`存在時即使 inventory complete，`statistics_input_ready`仍為 false。
- `COMPLETED`不得夾帶 failure record；terminal failure不可用改標 status規避分母或
  downstream gate。
- Null只允許在 schema明定的欄位，例如非 learning controller的
  `training_seed=null`；scenario factor或必要 evaluation/environment/scenario seed不可
  以 null取代。
- 任何修正都必須產生新的 spec/index content hash；不得放寬本 contract來讓既有結果
  通過。

## 5. Claim boundary

[RESULT] 本 validator的 PASS最多支持「指定 frozen matrix的 run inventory與 identity
完整」。

[INFERENCE] Exact matrix linkage可降低漏報、重複計數、unexpected run與 cherry-pick
風險，但不能證明 metrics正確、sample size充分、controller較優或 model具有 physical
validity。

[PARTIAL] PDR-6/PDR-8已有 bounded synthetic paired-statistics/export software
contract；actual Study statistics、validated paired binary CI、PDR-7 formal reproduction、
完整 V1/V2/V3及任何 HIL/bench/robot evidence仍須獨立完成。

[BLOCKER] `PAPER_RUN_MANIFEST_V1`沒有 `scenario_id/replicate_id`欄位；V1 matrix
因此以 explicit cell label加上 exact controller/seeds/scenario/config fingerprint完成
cross-check。這不是 run-manifest self-binding；若後續需要原生欄位，必須建立新的
manifest schema version，不能暗改 V1。

[BLOCKER] Validator只對 frozen explicit expected-cell list與 supplied dedicated root做
exact set/readback；它不自行證明 matrix已涵蓋所有科學上必要 strata，也不能證明
curator在 freeze前未刪除資料。External time-stamped preregistration與 immutable storage
仍須另建。

## 6. Research and standards basis

- [SOURCE] Patterson et al., [Empirical Design in Reinforcement Learning](https://www.jmlr.org/papers/v25/23-0183.html), JMLR 25(318), 2024：paired comparison、interval reporting與 agent/environment RNG separation可降低不必要變異；seed不是 tunable hyperparameter。
- [SOURCE] Agarwal et al., [Deep Reinforcement Learning at the Edge of the Statistical Precipice](https://proceedings.neurips.cc/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html), NeurIPS 2021：少量 runs的 point estimates不足，需 interval與 distribution-aware reporting。
- [SOURCE] [IETF RFC 8259](https://www.rfc-editor.org/rfc/rfc8259.html)：JSON不允許 NaN/Infinity；duplicate object names造成不一致 parser behavior。
- [SOURCE] [JSON Schema Draft 2020-12 Validation](https://json-schema.org/draft/2020-12/json-schema-validation)：`required`只檢查 property presence，`uniqueItems`只檢查完整 array elements，`format`預設可只是 annotation。
- [SOURCE] [Center for Open Science preregistration guide](https://www.cos.io/blog/choosing-preregistration-template-guide-for-researchers), 2025：preregistration是資料/分析前公開的 time-stamped、read-only plan，後續變更需留 versioned record。
- [INFERENCE] 因此 V1採 strict JSON + Pydantic structural schema + custom exact set arithmetic；internal hash freeze不借稱 external preregistration。

固定 claim文字必須 exact 等於：

> `SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED; matrix inventory identity only, without controller superiority, sim-to-real, physical fidelity, or safety claims.`

Validator不接受在 disclaimer後附加矛盾的 physical/safety claim。
