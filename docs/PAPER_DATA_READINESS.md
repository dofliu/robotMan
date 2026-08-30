# Paper Data Readiness Architecture

最後更新：2026-08-30

狀態：`ARCHITECTURE FROZEN V1 / IMPLEMENTATION IN PROGRESS`

證據範圍：`SIM_ONLY_MUJOCO / NOT PHYSICALLY VALIDATED`

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

Regression bundle 可通過 integrity validation，但只能標為 `REGRESSION_BUNDLE_VALID`，不能標為 `PAPER_DATA_READY`。

## 5. Paper Data Readiness gates

| Gate | Exit condition | 目前狀態 |
|---|---|---|
| PDR-0 Claim | RQ、hypothesis、primary outcomes、claim boundary frozen | PARTIAL |
| PDR-1 Model evidence | V1 dynamics/contact/numerical suite完成 | PARTIAL / static only |
| PDR-2 Run identity | manifest schema、source/model/controller/environment hashes | IN PROGRESS |
| PDR-3 Raw integrity | required artifacts、inventory、SHA-256、failure retention | IN PROGRESS |
| PDR-4 Matrix completeness | controller × seed × scenario expected cells exact | NOT STARTED |
| PDR-5 Independent metrics | raw-only evaluator覆蓋 primary/secondary outcomes | PARTIAL |
| PDR-6 Statistics | paired effects、CI、binary intervals、censoring | NOT STARTED |
| PDR-7 Reproduction | clean checkout可重建 selected table/figure | NOT STARTED |
| PDR-8 Paper export | machine-readable table/figure inputs與 appendix receipts | NOT STARTED |

任何前置 gate 未通過時，可以做 DEVELOPMENT/PILOT，但不可啟動 FORMAL_EVALUATION。

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

Primary sources：

- [HumanoidBench, RSS 2024](https://www.roboticsproceedings.org/rss20/p061.pdf)
- [Humanoid-Gym, 2024](https://arxiv.org/abs/2404.05695)
- [MuJoCo MPC for Humanoid Control, 2024](https://arxiv.org/abs/2408.00342)
- [Deep Reinforcement Learning That Matters, AAAI 2018](https://ojs.aaai.org/index.php/AAAI/article/view/11694)
- [Deep RL at the Edge of the Statistical Precipice, NeurIPS 2021](https://proceedings.neurips.cc/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html)

## 8. 立即執行順序

1. 完成 `PAPER_RUN_MANIFEST_V1` 與 artifact validator。
2. 讓 V1 static oracle輸出第一包 regression paper bundle，驗證 hash/readback流程。
3. 將 raw relative Jacobian納入 V1 bundle，移除 replay對 primary generalized-force receipt的依賴。
4. 建立 single-support、known-payload與 time-step convergence cases。
5. 建立 experiment matrix orchestrator與 completeness validator。
6. 執行 v7 PILOT；完成 power/sample-size決策後才 freeze FORMAL Study A。

隨研究規模增加時再評估 Parquet/object storage、distributed queue與 GPU worker；現階段 Windows單機、JSON/NPZ與 versioned local artifact root 已足夠，先避免引入不必要的分散式複雜度。
