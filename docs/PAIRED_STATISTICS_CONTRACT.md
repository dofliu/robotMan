# Paired Statistics and Paper Export Contract V1

最後更新：2026-09-05

狀態：`FROZEN V1 / BOUNDED SOFTWARE IMPLEMENTATION VERIFIED`

證據範圍：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`

## 1. Bounded milestone

Milestone ID：`PDR6-PDR8-PAIRED-STATISTICS-EXPORT-V1`

本 milestone 只建立 fail-closed paired statistics 與 machine-readable paper input
contract，回答：

> 一個已通過 identity/completeness gate 的 frozen two-controller matrix，能否在不遺失
> terminal failure、null、non-finite、censored 或不利結果的前提下，形成可獨立 replay
> 的 paired raw table、effect estimate、confidence interval 與 paper table/figure inputs？

本 milestone 只以 synthetic `REGRESSION` matrix 驗證 software contract；不執行 actual
Study A、power/sample-size 決策、formal evaluation 或 v7 PILOT，也不解除 P1/V1、PDR-6、
PDR-7、PDR-8 或 V3 scientific gate。

## 2. Frozen inputs and outputs

Primary evaluator讀取：

1. `experiment_matrix.json`：既有 `EXPERIMENT_MATRIX_SPEC_V1`。
2. `experiment_matrix_run_index.json`：既有 `EXPERIMENT_MATRIX_RUN_INDEX_V1`。
3. `paired_statistics_spec.json`：`PAIRED_STATISTICS_SPEC_V1`，綁定 matrix/index
   SHA-256、source Git identity、reference/candidate controller、explicit pair map、outcome
   semantics與 interval settings。
4. 每個 indexed run bundle 的 `metrics` artifact：`PAPER_RUN_METRICS_V1`，綁定
   `run_id`、`cell_id`、metric set、evaluator、terminal status與 raw-trace SHA-256。

Primary evaluator輸出：

- `matrix_completeness_receipt.json`；
- `paired_raw_table.json`：`PAIRED_RAW_TABLE_V1`；
- `statistics_summary.json`：`PAIRED_STATISTICS_SUMMARY_V1`；
- `paper_table_input.json`：`PAPER_TABLE_INPUT_V1`；
- `paper_figure_input.json`：`PAPER_FIGURE_INPUT_V1`；
- `statistics_receipt.json`：`PAIRED_STATISTICS_RECEIPT_V1`，保存上述 artifact的
  relative path、bytes與SHA-256；receipt不自我列入 inventory，避免 circular hash。

另一個不載入 Pydantic、NumPy、MuJoCo、controller或 primary evaluator module的
stdlib-only process，從 frozen spec與 `paired_raw_table.json`重算 summary/table/figure，
並輸出 `PAIRED_STATISTICS_REPLAY_RECEIPT_V1`。

## 3. Frozen estimands and numerical methods

### 3.1 Pair identity

V1只接受一個 reference controller與一個 candidate controller。每個 explicit pair保存
`pair_id`、`reference_cell_id`與`candidate_cell_id`；所有 matrix cells必須各出現一次且只
出現一次。Pair兩側必須有相同：

- `scenario_id`、`replicate_id`；
- evaluation、environment與scenario seed；
- typed-canonical scenario payload。

Controller identity、training seed與controller-specific resolved config可不同。V1不從
相近 label或排序推測 pairing，也不使用 run自報 pair ID。

### 3.2 Continuous outcome

- Estimand：pair-level `candidate - reference` 的 arithmetic mean。
- Effect outputs：mean difference、median difference與 standardized paired effect
  `Cohen dz = mean(diff) / sample_sd(diff)`。
- `sample_sd(diff) == 0`時，`Cohen dz=null`並保存 `ZERO_VARIANCE`，不得補成 0或
  infinity。
- 95% CI：對完整 pair-level differences做 percentile paired bootstrap；每次以 replacement
  重抽完整 pair，不分開抽兩側。此 interval只對應 mean difference；median difference與
  Cohen dz在V1只有 descriptive point estimate，不共用該CI。

### 3.3 Binary outcome

- Estimand：paired risk difference `mean(candidate_bool - reference_bool)`。
- 保存 `both_true`、`reference_only`、`candidate_only`與`both_false`四格 counts。
- V1不實作paired risk-difference CI；輸出
  `confidence_interval=null / PAIRED_BINARY_CI_NOT_IMPLEMENTED_V1`並將該outcome
  inference標為blocked。後續若採Fay–Lumbard、score或其他matched-pair方法，必須先以
  published reference cases獨立驗證並建立新contract version，不得結果後fallback。
- Reference與candidate各自的 marginal success probability另報 Wilson score 95% interval；
  這兩個 marginal descriptive intervals不取代 paired effect interval，也不作為兩組獨立
  樣本檢定。

### 3.4 Deterministic bootstrap

- Confidence level固定為 `0.95`；resample count由 frozen outcome spec明定，範圍
  `1,000..200,000`。
- Resample index由 frozen integer seed、bootstrap replicate、draw index與 retry counter
  經 SHA-256產生；使用 64-bit rejection sampling避免 modulo bias。
- Percentile採 linear interpolation的 Hyndman-Fan type 7等價規則：
  `h=(m-1)q`，在 `floor(h)`與`ceil(h)`間線性插值。
- 使用 `math.fsum`計算 sums。Primary與replay必須對 raw pairs、effect、interval及
  table/figure payload exact identity。

Bootstrap minimum-pair gate是 protocol欄位，只阻擋不符合該 frozen gate的 inference；
它不是 sample-size adequacy或 power analysis。Formal sample size仍須由後續 PILOT與
predeclared decision決定。

若多個scenario/evaluation cells共用同一trained checkpoint，pair-level bootstrap只能支持
固定controller artifacts下的conditional scenario/evaluation estimand，不能外推到training-run
population。Training-level推論必須先凍結independent cluster/resampling unit與hierarchical或
pre-aggregation方法；V1不自行猜測該結構。

## 4. Frozen observation semantics

每個 outcome必須是下列 mutually exclusive state之一：

| State | Required payload | Downstream semantics |
|---|---|---|
| `OBSERVED` | continuous finite number或binary boolean；unit exact | 保留原值，包括負值與0 |
| `NULL` | `value=null` + bounded reason | 保留；該 outcome inference blocked |
| `NONFINITE` | `value=null` + bounded source diagnostic | 保留；該 outcome inference blocked；不可把 NaN寫進JSON |
| `CENSORED` | `value=null` + `LEFT`/`RIGHT` + finite bound + reason | 保留 bound；V1不估計 censored effect，該 outcome inference blocked |

V1的 non-observed policy固定為 `PRESERVE_AND_BLOCK`：只要任一 expected pair對該
outcome不是雙側 `OBSERVED`，effect、CI與standardized effect一律為 `null`，並列出
exact `nonestimable_pair_ids`與state counts。不得做 silent complete-case analysis、
imputation、bound-as-observation或成功案例平均。

若完整 observed binary pairs少於 frozen `minimum_pairs`，effect/paired CI仍為null；但四格
paired counts與兩側marginal descriptive counts/interval仍保留，不可因 inference blocked而
抹除原始 denominator。

`FAILED` run仍在 matrix與pair denominator內。Binary outcome若將 terminal failure定義為
task failure，metrics artifact必須明確保存 `OBSERVED false`，且 outcome spec使用
`REQUIRE_EXPLICIT_FALSE_FOR_FAILED_V1`；只有採此 policy 的 outcome 才要求
`OBSERVED false`。其他 binary outcome 必須採 `PRESERVE_EXPLICIT_STATE_V1` 並保存實際
state；aggregator不得自行把 missing/null轉成 false。
Continuous outcome依原 observation state保存，不因 run failed而刪除。任何
`CANCELLED` cell使 upstream `statistics_input_ready=false`；statistics CLI保存 blocked
receipt與cancelled cell IDs，不產生可誤認為有效的effect/CI。

JSON中的 `NaN`、`Infinity`、overflow-to-infinity、duplicate key或unknown field是
structural error；已由 upstream evaluator辨識到的 non-finite observation只能以
`NONFINITE + null + diagnostic`表示。

### 4.1 Bounded execution

- Aggregate JSON單檔上限為 16 MiB；超限不寫出部分可信 artifact。
- 全部 continuous outcomes的 `expected_pair_count × bootstrap_resamples`總和上限為
  `5,000,000` draws，避免合法 schema 形成不可控的數十億次 SHA-256 workload。
- Independent replay上限 120 s，stdout上限 1 MiB；timeout、non-empty stderr、unknown
  receipt field、duplicate key或任何 spec/raw/summary/table/figure hash drift皆為structural
  error。
- Primary在 aggregate完成後再次執行 matrix validator並比對完整 receipt，避免讀取期間
  manifest/raw trace/index發生 identity drift。

## 5. Frozen acceptance criteria

| ID | Acceptance criterion |
|---|---|
| `PS-01` | Spec、metrics、replay receipt與outputs皆以 bounded strict JSON/schema處理；duplicate key、NaN/Infinity、overflow-to-infinity、unknown field、pathological integer/nesting與size limit均 fail closed。 |
| `PS-02` | Primary evaluator重新執行 matrix validator；matrix必須 exact complete且 `statistics_input_ready=true`。CANCELLED保留於blocked receipt並停止aggregate。 |
| `PS-03` | Statistics spec的matrix/index SHA-256、matrix/source Git、metric set、evaluator、run class、evidence scope與fixed claim boundary全部 exact match。 |
| `PS-04` | Explicit two-arm pair map exact覆蓋matrix cells；cell不可遺漏、重複、跨pair重用或同controller配對，pair labels、seeds與typed scenario必須一致。 |
| `PS-05` | 每個 `PAPER_RUN_METRICS_V1`由manifest的metrics artifact path/bytes/SHA-256讀取，且run/cell/status/raw-trace/metric-set/evaluator/outcome identity全部一致；manifest與raw trace在aggregate讀取時再次驗證。 |
| `PS-06` | `COMPLETED`、`FAILED`、`CANCELLED`與failure record counts保留；FAILED binary mapping必須explicit，禁止自動補值或只保留successful runs。 |
| `PS-07` | Negative/zero observations原值保留；NULL/NONFINITE/CENSORED保存reason/bound並依 `PRESERVE_AND_BLOCK`阻擋該outcome inference。 |
| `PS-08` | Ready continuous outcome輸出所有pair differences、mean/median difference、Cohen dz與frozen paired-bootstrap CI；zero variance與minimum-pair不足使用明示null/blocker。 |
| `PS-09` | Binary outcome輸出paired 2×2 counts、risk-difference point estimate與兩側Wilson marginal descriptive intervals；paired CI固定為null/blocked，denominator仍等於全部expected pairs。 |
| `PS-10` | Raw table、statistics summary、paper table與paper figure inputs保存schema/source/pair/scenario/seeds/run status/outcome/unit/denominator/blocked reason及manifest/metrics/raw-trace identities；`paper_data_ready=false`。 |
| `PS-11` | Strict aggregate receipt逐檔保存canonical relative path、bytes與SHA-256；post-build validator對tamper、unindexed file、link/reparse point、path escape、missing artifact或hash drift均fail closed。 |
| `PS-12` | `python -I -S` stdlib-only process由raw table重算summary/table/figure並exact match，receipt須回綁五個input/output SHA-256；CLI使用 `0=all outcomes ready`、`1=contract-valid but semantic/inference blocked`、`2=structural error`。 |

只有 `PS-01..PS-12`的 software behavior與tests成立時，才可回報
`STATISTICS_CONTRACT_VALID`。這不代表每個outcome都有可用CI；`statistics_ready`只在
所有outcomes皆ready時為true。`paper_data_ready`在本V1 regression milestone固定為false。

## 6. Failure semantics and change control

- Structural identity/schema/artifact錯誤：不信任aggregate，CLI exit 2。
- Matrix完整但CANCELLED、outcome有NULL/NONFINITE/CENSORED、pair數不足：保留
  machine-readable blocker；不產生該outcome的effect/CI，CLI exit 1。
- `FAILED`不是missing；只要artifact integrity有效就保留run、failure record與denominator。
- 不對既有結果改threshold、bootstrap settings、pair map、outcome direction、failure mapping
  或minimum pairs以取得PASS；任何變更建立新spec content hash/version。
- Output JSON不可手工修補；任何變更都必須由同一frozen raw table重建並通過replay。
- Synthetic fixture可驗證公式與governance behavior，不能當成scientific observation。

## 7. Claim boundary

固定 claim文字必須 exact 等於：

> `SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED; paired statistical software output only, without Study A or formal authorization, controller superiority, sim-to-real, physical fidelity, safety, or paper-acceptance claims.`

[RESULT] Contract PASS最多支持「指定 frozen synthetic matrix的pairing、statistics arithmetic、
blocked semantics與machine-readable export可由另一process重算」。

[INFERENCE] Pair-level differences可控制兩側共同scenario/initialization variation；這只在
pair identity正確且estimand/protocol事先凍結時成立，不保證sample size或外部效度。

[BLOCKER] Actual Study A matrix、formal sample-size decision、remaining V1/V2/V3 gates、
immutable project-wide storage、external preregistration、HIL/bench/robot evidence與publication
review均未完成。

## 8. Research and standards basis

- [SOURCE] Patterson et al., [Empirical Design in Reinforcement Learning](https://www.jmlr.org/papers/v25/23-0183.html), JMLR 25(318), 2024：對fully specified algorithms先形成paired differences，可控制environment/initialization variation；interval around difference比兩個獨立interval更直接。該文也說明percentile bootstrap需以replacement重抽完整samples，並提醒少量runs可能得到不可靠或過寬interval。
- [SOURCE] Agarwal et al., [Deep Reinforcement Learning at the Edge of the Statistical Precipice](https://proceedings.neurips.cc/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html), NeurIPS 2021：point estimates不足以呈現少量runs的不確定性，應保存run distributions、interval estimates與performance-profile inputs；其跨task stratified bootstrap設計不能直接借稱本單task paired estimator。
- [SOURCE] NIST/SEMATECH, [Confidence intervals for a binomial proportion](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm)：Wilson score interval由score-test inversion形成，且界限不會落到不可能的負機率；本V1只將它用於各controller marginal binary proportion。
- [SOURCE] Newcombe, [Improved confidence intervals for the difference between binomial proportions based on paired data](https://doi.org/10.1002/(SICI)1097-0258(19981130)17:22%3C2635::AID-SIM954%3E3.0.CO;2-C), Statistics in Medicine 17, 1998：paired binary difference需保留discordant/concordant結構，naive asymptotic interval可能有coverage問題。
- [SOURCE] Fay and Lumbard, [Confidence intervals for difference in proportions for matched pairs compatible with exact McNemar's or sign tests](https://doi.org/10.1002/sim.8829), Statistics in Medicine 40, 2021：提出與exact sign/McNemar test相容的matched-pair risk-difference interval；作者以大規模numerical calculations檢查coverage，但未宣稱一般數學證明。[INFERENCE] 本V1尚未對published implementation/reference cases做獨立驗證，因此不實作也不冒稱該方法。
- [SOURCE] Chang et al., [Continuity corrected score confidence interval for the difference in proportions in paired data](https://pmc.ncbi.nlm.nih.gov/articles/PMC10763857/), 2022：paired binary interval的coverage與width依方法及sample configuration而異，簡單Wald interval可能低於nominal coverage。[INFERENCE] Marginal Wilson intervals不能取代paired risk-difference CI。
- [SOURCE] Wünsch et al., [Rethinking the Handling of Method Failure in Comparison Studies](https://doi.org/10.1002/sim.70257), Statistics in Medicine, 2025：method failure通常形成undefined performance；silent deletion或一般missing-data imputation通常不適當，應保存failure frequency、reason與handling。[INFERENCE] Terminal task failure只有在outcome預先定義時可明示為observed false；NaN、process/solver error與cancellation不可自動轉false。
- [SOURCE] NIST/SEMATECH, [Censoring](https://www.itl.nist.gov/div898/handbook/apr/section1/apr131.htm)：right/left/interval censoring描述事件只知bound或interval的觀察機制。[INFERENCE] NaN、solver error與cancelled run不是censoring；未凍結censored estimator前只保存bound並阻擋一般mean/bootstrap。
- [SOURCE] [IETF RFC 8259](https://www.rfc-editor.org/rfc/rfc8259.html)：JSON grammar不包含NaN/Infinity，duplicate object names會造成interoperability問題。
- [SOURCE] CRAN `exact2x2` [version 1.7.0 package documentation](https://cran.r-project.org/package=exact2x2), 2025-08-20：提供與 Fay–Lumbard matched-pair interval相容的 `mcnemarExactDP` reference implementation。[BLOCKER] 本V1尚未建立 published golden-case cross-check，因此只登錄後續 V2 oracle候選，不在結果後臨時啟用。
- [INFERENCE] 因此V1採strict JSON、explicit observation states、exact pair map、continuous pair-level deterministic bootstrap、binary paired-CI blocker、Wilson marginal descriptive interval與stdlib-only replay；這些software choices不產生controller或physical claims。

## 9. Bounded implementation result

[RESULT] Clean-source synthetic `REGRESSION` package在 Git
`a36b230de28c9f00f495027539c9266b22a9ec15`通過 `PS-01..PS-12`；source
pre/post相同且均為 clean。Package receipt列入 191 個 artifacts / 297961 bytes，
receipt為 `sha256:c3b860ce70690a1ed855e475f72cfc4da83d236a6e71dd3fdec93ec9a834ebf1`。
Aggregate bundle的6個 artifacts / 170487 bytes通過 path/bytes/SHA-256與 no-extra-file
readback；`python -I -S` replay對 raw table、summary、table與figure exact identity。

[RESULT] Aggregate fixture保留 `FAILED`、negative、`NULL`、`NONFINITE`與
`CENSORED`；另一 fixture保留 `CANCELLED` 並回報
`BLOCKED_UPSTREAM_MATRIX`。`STATISTICS_CONTRACT_VALID` 只表示結構、pairing、
arithmetic、retention與replay符合contract；由於 binary paired CI與保留的
nonobserved outcomes仍有blocker，`statistics_ready=false`、`paper_data_ready=false`。

[INFERENCE] 此 evidence支持 synthetic software pipeline的bounded verification；不支持
sample-size adequacy、controller ranking、actual Study A、physical fidelity或publication readiness。

[BLOCKER] 後續仍需獨立驗證matched-pair binary CI、以PILOT凍結sample size、
執行actual matrix，並完成P1/V1、V3、formal authorization與project-wide immutable
storage。
