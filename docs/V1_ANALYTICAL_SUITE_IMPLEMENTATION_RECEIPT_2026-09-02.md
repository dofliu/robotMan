# V1 analytical fixture suite implementation receipt（2026-09-02）

## 1. Frozen milestone 與 claim boundary

- Milestone：`V1-ANALYTICAL-FIXTURE-SUITE`。
- 唯一目標：建立可獨立重播的 passive single-support analytical fixture，封裝 nominal single-support、centered known-payload 與 `4/2/1 ms` time-step convergence 四個 case，並把 raw contact frame、wrench、Jacobian 與 summary identity 納入 fail-closed evidence pipeline。
- Frozen fixture：單一 rigid body、矩形單一支撐面、base mass `20 kg`、known payload `+5 kg`、duration `1.2 s`、evaluation window `(0.8, 1.2] s`；無 controller、無 actuation、無 assist、無 external applied force。
- Frozen thresholds：time-grid error `<= 1e-12 s`；raw Jacobian closure relative max `<= 1e-9`；forward/inverse joint 與 constraint force norm 各 `<= 1e-8`；model mass error `<= 1e-12 kg`；weight balance 與 payload GRF delta relative error各 `<= 2%`；mean linear/angular speed 各 `<= 1e-3`；contact normal force `>= -1e-8 N`；friction utilization `<= 1 + 1e-9`；CoP support margin `>= -1e-9 m`；exact single-support duty `= 1`；fine-grid QoI delta `<= 5e-4`，且 fine delta 不得大於 `max(coarse delta, 1e-10)`。
- Failure semantics：任何 schema、case/model inventory、compiled model identity、source identity、artifact path/bytes/SHA-256、non-finite value、raw-to-summary、primary-to-replay、threshold 或 process-exit 不一致，均 fail closed；failed、NaN、cancelled、negative/null result 必須保留，不得刪除或以調整 frozen threshold 修復。當差值受 round-off 主導或無單調收斂時，`timestep_observed_order` 必須保留 `null`。
- Claim boundary：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`。本 receipt 不構成 articulated humanoid、controller performance、payload capacity、contact fidelity、sim-to-real、physical robot safety 或一般 controller superiority 的證據。

## 2. Implementation inventory

[RESULT] 本 milestone 新增下列 source、independent replay、bundle builder、fail-closed tests 與 frozen specification：

- `backend/v1_analytical_suite.py`
- `backend/v1_analytical_replay.py`
- `backend/build_v1_analytical_bundle.py`
- `backend/test_v1_analytical_suite.py`
- `backend/test_v1_analytical_bundle.py`
- `docs/V1_ANALYTICAL_SUITE_SPEC.md`

[RESULT] Primary path 由 MuJoCo 產生逐步 raw trace；independent replay 僅由序列化資料重算 contact-frame wrench、`J^T f`、support/CoP/friction、static load balance、known-payload delta 與 time-step QoI，不重新執行 simulator。Builder 產生十種 role 的 artifact package，並在 execution 前後檢查 content-sensitive Git identity。

## 3. Clean-source evidence receipt

- Bundle：`backend/run_traces/v1-analytical-clean-20260902T065653528`
- Source Git SHA：`b39a5ea2524a10189959d4968a9a7e15747fbf59`
- Source identity：execution 前後皆 `dirty=false`，SHA 未變，`stable_during_run=true`
- Primary / independent replay：`PASS / PASS`
- Case inventory：`4/4 PASS`
- Artifact inventory：`10` artifacts，合計 `41,034,195 bytes`
- Bundle validation：`REGRESSION_BUNDLE_VALID_ONLY`
- `paper_data_ready=false`

### Integrity hashes

| Object | SHA-256 |
|---|---|
| `paper_run_manifest.json` | `sha256:97197f0a68a83e18bc12fc743ba7192d8b8e23626e0579c0c2ecc274de5350ff` |
| `raw_suite.json` | `sha256:82192dc5a62b31d1ae10354ce74256c0b8dc2e66319b00063337bdd6ea76e5c4` |
| `models.json` / plant identity | `sha256:83fa36054f6c04dcf4629d2839b89fc08c0d77c281ccc2f9f87a577e9b0b6357` |
| model package content | `sha256:b6e020cb2197b21d3d30bd7e05216efde65ed3b3ff224a424be950c28e9b84b1` |

### Numerical results

| Metric | Primary | Independent replay |
|---|---:|---:|
| payload mass delta error | `0.0 kg` | `0.0 kg` |
| payload GRF delta relative error | `1.303748139009358e-15` | `1.303748139009358e-15` |
| QoI at `4 ms` | `1.0000000000000078` | `1.0000000000000073` |
| QoI at `2 ms` | `1.0000000000000016` | `1.0000000000000016` |
| QoI at `1 ms` | `1.0000000000000007` | `1.0000000000000004` |
| coarse delta (`4 ms` vs `2 ms`) | `6.217248937900877e-15` | `5.773159728050814e-15` |
| fine delta (`2 ms` vs `1 ms`) | `8.881784197001252e-16` | `1.1102230246251565e-15` |
| convergence classification | `ROUND_OFF_LIMITED` | `ROUND_OFF_LIMITED` |
| observed order | `null` | `null` |

[RESULT] Independent replay 的 raw serialized receipt delta max 為 `4.0389678347315804e-28`；primary summary numeric delta max 為 `5.684341886080802e-14`。Case receipts、suite metrics、criteria 與 status identity checks 全部通過。

[INFERENCE] `4/2/1 ms` QoI 差值已落入 floating-point round-off 尺度，因此本次只可報告「此被動靜態 fixture 在選定 grid 上未見數值發散」，不可據此估算非零 convergence order，也不可外推至 nonsmooth dynamic contact、articulated humanoid 或 controller case。

## 4. Test 與 policy verification

| Verification | Result |
|---|---|
| `backend/test_v1_analytical_suite.py` | `20 passed` |
| `backend/test_v1_analytical_bundle.py` | `12 passed` |
| Targeted old/new V1 與 paper-data contract suite | `67 passed` |
| Full backend（`--ignore=backend/run_traces`） | `186 passed, 5 warnings` |
| Frontend | 未受影響；`npm run check` 為 `N/A` |

[BLOCKER] 首次 ordinary full collection 保留 `17` 個 `PermissionError`：來源是既有、ignored 的 `backend/run_traces/pytest-*` ACL directories。未刪除、未改 ACL、未把它們包裝成 test pass；以 `--ignore=backend/run_traces` 隔離 runtime artifacts 後，tracked backend suite 為 `186 passed`。五項 warning 為既有 FastAPI `ORJSONResponse` deprecation 與 PyTorch `pynvml` FutureWarning，不影響本 milestone 的 pass/fail 判定。

## 5. Research basis 與 validity boundary

- [SOURCE] [MuJoCo 3.12 Computation](https://mujoco.readthedocs.io/en/3.12.0/computation/) 定義 forward dynamics、constraint/contact force 與 time integration；本 suite 依其 simulator quantities 建立 raw receipts，但 simulator self-consistency 不是 physical validation。
- [SOURCE] Caron et al., [Stability of Surface Contacts for Humanoid Robots: Closed-Form Formulae of the Contact Wrench Cone for Rectangular Support Areas](https://arxiv.org/abs/1501.04719), ICRA 2015，提供矩形支撐面的 unilateral force、friction、CoP 與 yaw/contact-wrench feasibility 理論依據。
- [SOURCE] [NASA-STD-7009B](https://standards.nasa.gov/sites/default/files/standards/NASA/B/1/NASA-STD-7009B-Final-3-5-2024.pdf) 要求記錄 numerical error、discretization、iteration 與未驗證面向；本 receipt 因而保留 round-off-limited `null` order 與 ACL collection failure。
- [SOURCE] Joseph & Dutta, [Experimental validation of a physics-based simulation model for a serial robotic manipulator](https://doi.org/10.1177/09544062251407012), 2026，使用 physical measurements 進行 model validation；本專案目前沒有相對應的 physical robot measurements。

[RESULT] 本次 evidence 僅驗證：exact frozen MJCF/model package、single-support passive load balance、centered simulated `+5 kg` mass/GRF relation、選定 static time grids、raw Jacobian serialization 與 stdlib-only independent replay identity。

[BLOCKER] 尚未完成 experiment matrix completeness validator、articulated/dynamic controller cases、paired statistics 與 confidence interval、paper table/figure inputs、v7 PILOT，也沒有 physical robot / force-sensor ground truth。因此整體 V1 gate 與 paper-data readiness 維持未通過。

[INFERENCE] 下一個唯一優先 milestone 應為 experiment matrix completeness validator；其目的為 fail closed 地辨識 required cells、missing/duplicate runs、status retention 與 artifact/source identity，不得把本 fixture 的 pass 直接升格為 manuscript performance claim。
