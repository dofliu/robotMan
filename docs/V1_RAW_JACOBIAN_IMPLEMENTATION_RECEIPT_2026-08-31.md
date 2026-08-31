# V1 Raw-Jacobian V4 Implementation Receipt

日期：2026-08-31

結果：`MILESTONE PASS / V1 GATE NOT PASS`

證據邊界：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`

## 1. Bounded milestone

本次只完成 raw relative Jacobian serialization 與 process-independent
stdlib-only replay；未加入 single-support、known-payload、time-step
convergence、experiment matrix、statistics 或 v7 PILOT。Frozen physics thresholds
與 16 項 primary criteria未放寬。

## 2. Clean-source evidence

- Implementation Git SHA：`07b742c65b96c70f77556331a5a2aee8fe5580a2`
- Bundle：`backend/run_traces/v1-jacobian-v4-clean-20260831T151644`
- Run ID：`v1-regression-20260831t071657-5dcf99a5`
- Source identity：run 前/後 SHA皆為 implementation SHA，`dirty=false`，
  `stable_during_run=true`
- Manifest：`COMPLETED`；10 artifacts；`46,209,395 bytes`；
  SHA-256 `sha256:97bc4b1705dee679284c315ed666c27c51499dbc51549a61feb0a0595de34f31`
- Raw artifact：`raw_oracle.json`；`46,177,938 bytes`；manifest/readback
  SHA-256皆為
  `sha256:fc837efd398ad2fb91eee1cad5992e29ead021617cce7eb78f00adc1a5fe9b32`
- Model identity：manifest `model.xml` 與 primary compiled-config receipt SHA-256皆為
  `sha256:fd0a191f35a7c50d186a104b3378a92acdb794e82606d7f0c9aca902c7eac9df`
- Bundle validator：`REGRESSION_BUNDLE_VALID_ONLY`；
  `paper_data_ready=false`。

大型 bundle 依 repository policy 保留在 ignored `backend/run_traces/`，
Git 只保存 contract、tests、documents 與本 small receipt。

## 3. Raw-to-replay identity

- Raw schema：`V1_STATIC_DOUBLE_SUPPORT_ORACLE_V4`；1000 physics steps。
- Primary：16/16 PASS。
- Replay：14/14 PASS；不匯入 MuJoCo、`LiveSession` 或 controller。
- Full-trace raw-Jacobian closure：`6.83306152520628e-16`。
- Evaluation-window closure：`6.83306152520628e-16`。
- Absolute time-grid error：`1.5543122344752192e-15 s`。
- Primary/replay 八個 contact metrics 最大差異：`0.0`。

Replay 只以 serialized contact frame、6-D wrench、relative translational/
rotational Jacobians 與 support geometry重算 criteria。`force_world_n`、
`normal_force_n`、`friction_utilization`、foot aggregate 與
`qfrc_contact_reconstructed` 等 redundant primary summaries只做
completeness/finite/shape檢查，不作為 replay authoritative input。

## 4. Verification

- Targeted：`42 passed, 1 warning`。
- Full backend：`154 passed, 5 warnings`。
- Frontend：`npm run check` PASS（TypeScript + Vite production build）。
- Frozen threshold AST identity：15 tolerance fields與前一 HEAD完全一致。
- `git diff --check`、staged diff、YAML parse、local Markdown links、
  ignored-artifact policy、high-confidence secret/personal-path scan：PASS。

Fail-closed tests覆蓋：缺少/malformed Jacobian、`nv`/`condim` drift、
active metadata矛盾、inactive nonzero wrench、nonzero adhesion、缺少 frozen
step/model field、NaN/±Infinity、constant time offset、finite raw tamper、forged
complete PASS、錯誤 claim、primary/replay process/schema error、source identity drift、
artifact tamper 與 cancelled bundle。

保留的負面/tooling結果：

- Windows sandbox system temp 路徑曾導致 paper tests `PermissionError`；改用
  repository-local `--basetemp` 後重跑。
- 一次 targeted command 引用不存在的 test filename，pytest未執行 tests；
  改為 `backend/test_policy_registry.py` 後重跑。
- Initial raw-schema strict run 為 `5 failed, 13 passed`，暴露 redundant
  summary receipt 會提前覆蓋 finite-tamper `FAIL` semantics；修正後為
  `18 passed`。
- Initial Markdown root-path scanner 與 threshold `literal_eval` checker各有一次
  tooling error；修正 scanner 與 AST structural checker後均 PASS。

既有 warnings 未當作本 milestone blocker：FastAPI `ORJSONResponse`
deprecation、`pytest-asyncio` default-loop-scope、`pynvml` deprecation 與 Vite
chunk-size warning。Repository 未安裝 dedicated secret scanner；本次只能證明
high-confidence pattern scan PASS。`STATUS.yaml` 以 ambient PyYAML parse PASS，但
PyYAML 尚未成為 project-pinned validation dependency。

## 5. Claim boundary 與下一步

[SOURCE] Jacobian、contact frame 與 contact wrench 均來自同一 MuJoCo engine。

[RESULT] 本證據只支持 raw serialization、process isolation、arithmetic
reconstruction、artifact integrity 與 software-regression claims。

[INFERENCE] Exact replay identity可偵測 schema、frame/sign、aggregation 與
threshold drift，但不會將 same-engine receipt變成 independent plant evidence。

[BLOCKER] V1 仍缺 single-support、known-payload、time-step convergence、
analytical/dynamic contact、energy 與 external force/bench validation。不支持實體
robot、sim-to-real、safety 或 controller superiority。

下一次唯一優先目標：以凍結 acceptance/failure semantics 建立
single-support、known-payload 與 time-step convergence V1 cases。
