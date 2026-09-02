# Paper Data Readiness Architecture

最後更新：2026-09-03

狀態：`ARCHITECTURE FROZEN V1 / IMPLEMENTATION IN PROGRESS`

證據範圍：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`

## 1. 決策

後續開發以「能產生可重現、可統計、可追溯的論文 simulation data」為首要前提。介面功能、單一 policy training 或 nominal animation 不再單獨構成里程碑。

第一篇論文的合理定位是：

> 在 frozen MuJoCo humanoid plant 與固定 motion task 下，比較 model-based、learning-based 或 hybrid control/training methods 的 task performance、constraint behavior、robustness與 sample efficiency。

允許的主張只到 simulation method comparison。沒有 HIL、bench 或 robot evidence 時，不宣稱 hardware feasibility、sim-to-real、實機穩定或安全。

## 2. 功能與非功能需求

Functional requirements：

1. 每個 run 可定位到 research question、hypothesis、protocol、controller、plant、scenario、seed 與 metric set。
2. 500 Hz raw realized trace、failure、early termination、NaN與 solver issue 全數保留。
3. Metrics 由不依賴 UI summary 的 evaluator 重算。
4. Artifact inventory 逐檔保存 bytes 與 SHA-256，任何缺檔、path escape或 tamper 均 fail closed。
5. Experiment matrix 可檢查 expected/missing/duplicate/unexpected cells。
6. Training seed、evaluation seed 與 HOLDOUT partition 分離。
7. Aggregate stage 產生 paired raw table、effect size、confidence interval、binary outcome interval與 performance profile inputs。

Non-functional requirements：

- reproducible：source、environment、model、config、controller/checkpoint identity 可重建；
- failure-retaining：不刪除不利 runs，不對 formal output補值或 repair；
- bounded：大量 raw data 不直接提交 Git，Git 只保存 contracts、validators、small receipts；
- portable：paper tables/figures 只讀 machine-readable artifacts，不依賴 UI screenshot；
- evidence-aware：regression、development、calibration、formal evaluation 明確分層。

## 3. 系統架構與資料流

```text
Research Question / Hypothesis
            │
            ▼
Frozen Protocol + Scenario/Seed Matrix
            │
            ▼
Experiment Orchestrator ──► Controller / Training Pipeline
            │                         │
            │                         ▼
            └────────────────► Frozen MuJoCo Plant
                                      │
                                      ▼
                               500 Hz Raw Trace
                                      │
                  ┌───────────────────┴──────────────────┐
                  ▼                                      ▼
        Independent Evaluator                  Artifact Inventory
                  │                                      │
                  └───────────────────┬──────────────────┘
                                      ▼
                              Per-run Gate Receipt
                                      │
                                      ▼
                        Matrix Completeness Validator
                                      │
                                      ▼
                          Paired Statistics / CI / UQ
                                      │
                                      ▼
                     Paper Tables / Figures / Appendix Data
```

Component boundaries：

- `Physics Oracle`：回答 model equations/contact/numerical checks，不比較 controller優劣。
- `Experiment Orchestrator`：只依 frozen manifest 執行完整 matrix，不自行調參。
- `Raw Recorder`：保存 realized physics samples，不使用 UI decimation。
- `Independent Evaluator`：只讀 raw artifact，不讀 training return 或 frontend summary。
- `Bundle Validator`：驗證 identity、artifact hash、failure retention與 evidence class。
- `Statistics Stage`：只讀已通過 inventory/completeness 的 per-run receipts。

## 4. Paper run bundle

每個 run directory 至少包含：

```text
paper_run_manifest.json
protocol.json
resolved_config.json
model.xml
controller.json
environment.json
raw_trace.*
metrics.json
evaluator_receipt.json
stdout.txt
stderr.txt
```

`paper_run_manifest.json` 使用 `PAPER_RUN_MANIFEST_V1`，每個 artifact 保存 relative path、role、media type、bytes 與 SHA-256。Manifest 不把自己放進 inventory，以避免 circular hash。

正式 paper-data-ready run 必須額外符合：

- `run_class=FORMAL_EVALUATION`；
- `protocol_status=FROZEN`；
- `data_partition=HOLDOUT`；
- clean Git source identity；
- assist OFF；
- no tuning after freeze；
- learning/hybrid controller 有 training seed；
- 所有 controller 有 evaluation/scenario seed schedule；
- required artifact roles 完整且 hash readback一致。

Regression bundle 可通過 integrity validation，但只能標為 `REGRESSION_BUNDLE_VALID_ONLY`，不能標為 `PAPER_DATA_READY`。

## 5. Paper Data Readiness gates

| Gate | Exit condition | 目前狀態 |
|---|---|---|
| PDR-0 Claim | RQ、hypothesis、primary outcomes、claim boundary frozen | PARTIAL |
| PDR-1 Model evidence | V1 dynamics/contact/numerical suite完成 | PARTIAL / static V4 replay + passive single-support、centered payload與 4/2/1 ms analytical fixture PASS；articulated dynamic/pendulum/energy仍缺 |
| PDR-2 Run identity | manifest schema、source/model/controller/environment hashes | IN PROGRESS / content-sensitive pre/post Git、exact MJCF/model package與 clean-source identity PASS；full environment lock missing |
| PDR-3 Raw integrity | required artifacts、inventory、SHA-256、failure retention | IN PROGRESS / static與analytical 10-role completed/failed/cancelled paths、bytes與SHA-256 readback PASS |
| PDR-4 Matrix completeness | controller × seed × scenario expected cells exact | SOFTWARE VALIDATOR IMPLEMENTED / ACTUAL STUDY MATRIX NOT RUN；strict spec/index、derived seed-schedule hash、bounded no-follow root scan、bundle identity、missing/duplicate/unexpected/unindexed與 FAILED/CANCELLED retention covered |
| PDR-5 Independent metrics | raw-only evaluator覆蓋 primary/secondary outcomes | PARTIAL / static與analytical fixture已有 stdlib-only raw replay；Study A outcomes未覆蓋 |
| PDR-6 Statistics | paired effects、CI、binary intervals、censoring | NOT STARTED |
| PDR-7 Reproduction | clean checkout可重建 selected table/figure | NOT STARTED |
| PDR-8 Paper export | machine-readable table/figure inputs與 appendix receipts | NOT STARTED |

任何前置 gate 未通過時，可以做 DEVELOPMENT/PILOT，但不可啟動 FORMAL_EVALUATION。

[RESULT] `EXP-V1-ANALYTICAL-FIXTURE-REGRESSION` clean-source bundle在 Git
`b39a5ea2524a10189959d4968a9a7e15747fbf59`通過 4/4 cases與 independent replay；
payload mass error為 `0 kg`、paired GRF increment relative error為
`1.303748139009358e-15`。4/2/1 ms normalized-GRF differences已低於 frozen gate，
但因差值進入 round-off區，observed order依 preregistered semantics保留為 `null`。
此結果仍是 `REGRESSION_BUNDLE_VALID_ONLY / paper_data_ready=false`。

## 6. 第一篇 Study A 建議

第一篇先聚焦一個可回答的問題，避免同時聲稱所有動作與所有演算法：

- Primary RQ：action interface／observability設計是否改善 `stand → start → steady walk → stop` 的成功率與 saturation behavior？
- Methods：phase-observable PPO、joint-specific action envelope、action rate/low-pass filtering；WBC residual 等 P1/P2完成後再加入。
- Primary outcomes：task success、fall、steady path error、saturation duty。
- Secondary outcomes：stop speed、yaw/lateral error、work、smoothness、constraint utilization。
- Design：獨立 training seeds、paired evaluation seeds、preregistered scenario strata。
- Sample size：先用 PILOT variance/power analysis決定，不在看到 formal results 後調整。

目前 v2–v6 runs 都是 DEVELOPMENT evidence；不得直接重新標記為 formal replicates。

## 7. Literature-derived design choices

- HumanoidBench 說明 standardized simulated tasks 與共同 benchmark 對 humanoid algorithm research的重要性，因此本專案必須凍結 task、plant、metric與 controller comparison protocol。
- Humanoid-Gym 使用 sim-to-sim validation檢查 policy 在不同 simulator 的 robustness；本專案可將 cross-simulator列為後續 validation，但目前只有 MuJoCo，不能先宣稱 sim-to-real。
- MuJoCo MPC on HumanoidBench 指出 sparse reward可能產生不自然行為，因此 paper outcomes不能只報 reward/return，必須包含 posture、smoothness、contact與 saturation metrics。
- Deep RL reproducibility研究顯示單一 seed與點估計不足；正式結果需多 training seeds、interval estimates與保留 run-level distribution。
- [SOURCE] MuJoCo 官方定義 contact generalized force 由兩側 body 的 relative spatial Jacobian 與 contact-frame wrench形成。[RESULT] V1 V4保存 `body2 - body1` relative Jacobians，讓另一 process 重算 arithmetic identity。
- [SOURCE] Joseph and Dutta（2026）及 Crotti et al.（2025）的 MuJoCo contact/foot研究都使用外部 physical force、deformation或 bench prototype做 model validation。[INFERENCE] 本專案只有 same-engine Jacobian/wrench receipts，不能借用其 physical validity。
- [SOURCE] MuJoCo的 continuous equations、integration timestep與 `solver_fwdinv` diagnostics定義不同；NASA-STD-7009B要求留下 discretization、iterative與 finite-precision error evidence。[RESULT] 本次以 4/2/1 ms grid保存 timestep stability，並把 round-off-limited order保留為 null，而非用 solver diagnostic代替 convergence study。
- [SOURCE] Patterson et al.（JMLR 2024）建議 algorithm comparison使用 paired comparisons與 interval，並分開 agent/environment RNG；seed不是可調 hyperparameter。[INFERENCE] Matrix V1因此把 training、evaluation、environment與scenario seeds分欄保存，但 sample size仍須由後續 PILOT與 preregistered estimand決定。
- [SOURCE] Agarwal et al.（NeurIPS 2021）指出少量 runs下只報 point estimate會忽略顯著 statistical uncertainty，建議 interval與 run-distribution reporting。[INFERENCE] Statistics stage只能讀已保留所有 FAILED/COMPLETED cells且通過 identity/completeness的 receipts；本 validator本身不產生 CI。
- [SOURCE] RFC 8259禁止 JSON `NaN`/`Infinity`，並指出 duplicate object names造成 parser interoperability問題；JSON Schema 2020-12的 `required`與`uniqueItems`只提供結構條件。[RESULT] Matrix/Run manifest readback改採 strict JSON及 custom composite-cell set arithmetic，不把 schema-valid誤寫為 matrix-complete。
- [SOURCE] Center for Open Science將 preregistration定義為 data/analysis前發布至 public repository的 time-stamped、read-only plan。[BLOCKER] 本 repo的 frozen hash只能稱 internal preregistered-style freeze；未登錄 external registry，不宣稱 OSF preregistration。

Primary sources：

- [HumanoidBench, RSS 2024](https://www.roboticsproceedings.org/rss20/p061.pdf)
- [Humanoid-Gym, 2024](https://arxiv.org/abs/2404.05695)
- [MuJoCo MPC for Humanoid Control, 2024](https://arxiv.org/abs/2408.00342)
- [Deep Reinforcement Learning That Matters, AAAI 2018](https://ojs.aaai.org/index.php/AAAI/article/view/11694)
- [Deep RL at the Edge of the Statistical Precipice, NeurIPS 2021](https://proceedings.neurips.cc/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html)
- [Empirical Design in Reinforcement Learning, JMLR 2024](https://www.jmlr.org/papers/v25/23-0183.html)
- [IETF RFC 8259 — JSON](https://www.rfc-editor.org/rfc/rfc8259.html)
- [JSON Schema Draft 2020-12 Validation](https://json-schema.org/draft/2020-12/json-schema-validation)
- [Center for Open Science preregistration guide, 2025](https://www.cos.io/blog/choosing-preregistration-template-guide-for-researchers)
- [MuJoCo Computation — Contact](https://mujoco.readthedocs.io/en/stable/computation/index.html#contact)
- [Contact force estimation with compliance in MuJoCo, 2026](https://doi.org/10.1177/09544062251407012)
- [Soft Adaptive Feet for Legged Robots, IEEE Access 2025](https://doi.org/10.1109/ACCESS.2025.3608584)
- [MuJoCo 3.12 Computation](https://mujoco.readthedocs.io/en/3.12.0/computation/)
- [NASA-STD-7009B](https://standards.nasa.gov/sites/default/files/standards/NASA/B/1/NASA-STD-7009B-Final-3-5-2024.pdf)
- [Caron, Pham and Nakamura, ICRA 2015](https://arxiv.org/abs/1501.04719)

## 8. 立即執行順序

1. [DONE] 完成 `PAPER_RUN_MANIFEST_V1` 與 artifact validator。
2. [DONE] 讓 V1 static oracle輸出第一包 regression paper bundle，驗證 hash/readback流程。
3. [DONE] 將 raw relative Jacobian納入 V1 V4 bundle；stdlib-only replay不再讀取 primary per-contact generalized-force receipt。
4. [DONE] 建立 passive single-support、centered known-payload與 4/2/1 ms time-step analytical fixture；round-off-limited order保留為 null。
5. [DONE-SOFTWARE] 建立 [Experiment Matrix Completeness Contract V1](EXPERIMENT_MATRIX_CONTRACT.md)與 strict fail-closed validator；actual Study A matrix/orchestrator仍未執行，PDR-4不視為 scientific coverage PASS。
6. [NEXT] 建立 paired statistics、confidence interval與 paper table/figure input contract；先以 synthetic/REGRESSION matrix驗證 failure/cancellation與 null/censoring semantics，不啟動 formal Study A。
7. 執行 v7 PILOT；完成 power/sample-size決策後才 freeze FORMAL Study A。

隨研究規模增加時再評估 Parquet/object storage、distributed queue與 GPU worker；現階段 Windows單機、JSON/NPZ與 versioned local artifact root 已足夠，先避免引入不必要的分散式複雜度。
