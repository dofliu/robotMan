# 開發與證據規範

本文件定義程式修改與 evidence governance 的共通規則。模型用途與限制見 [MODEL_CARD](MODEL_CARD.md)，V&V requirement 見 [VV_PLAN](VV_PLAN.md)，正式執行規則見 [EXPERIMENT_PROTOCOL](EXPERIMENT_PROTOCOL.md)。

## 1. 語言與程式風格

- 文件、介面與註解使用繁體中文；API、RAG、ZMP、CoP、WBC、SIL、HIL 等 technical terms 保留英文。
- 註解說明「為什麼」與 assumption，不重述語法。
- Python 3.12+，資料契約優先使用 Pydantic；TypeScript types 與 API schema 同步。
- 內部使用 SI units；任何 display conversion 必須在 UI 層明示。
- 物理常數、solver settings 與 thresholds 不可散落成未記錄 magic numbers。

## 2. Evidence labels

所有研究或 V&V 記錄使用：

- [SOURCE] 可定位的原始資料、程式、datasheet、CAD、bench log 或標準。
- [RESULT] 由固定方法產生且保留 raw artifact 的結果。
- [INFERENCE] 在明示 assumptions 下由 SOURCE/RESULT 推得的解讀。
- [HYPOTHESIS] 尚未驗證的機制或預期。
- [BLOCKER] 缺少必要 evidence、identity、oracle 或 authorization。

Software RESULT 不得改寫成 physical RESULT。

## 3. Verification 與 Validation 用語

- verification：code/equation/numerical implementation 是否符合 specification。
- validation：model 是否足以代表指定 physical use case。
- calibration：用資料設定參數；使用過的資料不可再冒充 independent validation。
- benchmark：必須有 frozen protocol、fair conditions、raw traces 與 statistics。
- demo/snapshot：可以展示，但不得使用 validated、measured、realistic、proven 等語句。

「real dynamics」改稱 MuJoCo forward dynamics；「實測」只保留給 instrumented physical measurement。

## 4. Fail-closed

下列任一情況發生，formal run 必須停止並保留證據：

1. code/config/model/checkpoint/environment identity 不符；
2. seed/scenario/assist/disturbance/metric 未凍結；
3. solver 不收斂、constraint infeasible 或 residual 超過 gate；
4. raw trace 缺失、hash 不符或 summary 無法回指 raw data；
5. controller fallback、exception 被吞掉或 label 與實際執行不一致；
6. formal failure 後有人調參、換 metric、刪 case 或放寬 threshold。

修正後必須建立新 experiment/protocol version，不覆寫失敗 run。

## 5. 物理模型契約

- JOINT_ORDER 是 backend、frontend、controller 與 RL 的共用 contract。
- MuJoCo 使用 z-up right-handed coordinates；units 為 SI。
- analysis mode 與 live mode 的 contact semantics 不同，不能共用未定義的 claim。
- floating-base inverse dynamics 必須檢查六個 base equilibrium residual，不能只取 actuated components。
- contact force 必須檢查 unilateral、friction cone、CoP/support、contact schedule 與 wrench closure。
- joint limits、velocity/acceleration limits、self-collision 與 solver convergence 都是正式 feasibility 的必要條件。
- actuator feasibility 必須使用 torque-speed/current/voltage/thermal envelope；constant peak torque 只能作 D0 screening。
- energy metric 必須先指定 mechanical/electrical、positive/absolute/regenerative semantics，再以 physics-step integration。

## 6. Numerical methods

- trajectory 進入 finite difference 前需記錄 continuity class。
- 每個物理結果需有 time-step sensitivity 或 convergence study。
- filtering、smoothing、percentile、transient exclusion 與 topology exclusion 必須在 protocol 前凍結。
- raw curve 不因 summary statistic 而刪除。
- numerical spike 不可在看到結果後手動修補；先建立 root-cause case。
- exact tolerance 由 V0 preregistration 決定，正式 run 後不得放寬。

## 7. Hardware data

- 內建 catalog 一律是 D0 representative demo data。
- datasheet 值需保存 document identity、revision、page/table、units、operating conditions 與 checksum。
- CAD/BOM、bench 與 integrated subsystem evidence 分級管理。
- UI override 不改變 provenance class。
- 缺少 torque-speed、thermal、drive 或 gearbox detail 時，hardware feasibility 保持 BLOCKED。

詳見 [HARDWARE_DATA_PROVENANCE](HARDWARE_DATA_PROVENANCE.md)。

## 8. 修改工作流

1. 先更新 requirement、acceptance criterion 與 impacted evidence。
2. 建立或更新 DEVELOPMENT case。
3. 修改 code 與 tests。
4. 執行 unit、numerical、regression checks。
5. 保存 command、environment、raw output、exit code 與 hashes。
6. 只有全部 gate 通過才更新 status；feature 可用不等於 V&V pass。

若修改 observation、action、reward、joint order、plant parameters 或 delay，舊 RL checkpoint 必須標記 incompatible，不能靜默載入。

## 9. Test 規範

最低測試層：

- schema/unit/coordinate/unit conversion；
- IK/FK analytical cases；
- base wrench and joint torque residual；
- contact/friction/CoP feasibility；
- joint limit and actuator envelope；
- time-step and solver convergence；
- deterministic regression with frozen hashes；
- scenario and Monte Carlo protocol validation；
- raw artifact completeness and checksum。

pytest cache、console print 或 UI screenshot 不是 test receipt。Receipt 至少包括 command、exit code、environment、code identity、case IDs、assertion summary 與 artifact hashes。

## 10. Benchmark 規範

- 所有 controller 使用相同 plant、initialization、assist、disturbance、termination 與 sampling。
- deterministic rerun 不當成 independent replicate。
- stochastic study 的 seed schedule 與 sample size 在 formal execution 前確定。
- 回報 per-run values、failures、censoring、effect size 與 confidence interval。
- push metric 明定 force/impulse、point、direction、phase、duration 與 recovery horizon。
- 調參用 DEVELOPMENT/CALIBRATION；FORMAL_EVALUATION 不可回流調參。

## 11. 文件同步

| 改動 | 必須同步 |
|---|---|
| claim/use case | MODEL_CARD、VV_PLAN |
| experiment/metric | EXPERIMENT_PROTOCOL、VV_PLAN |
| hardware parameter | HARDWARE_DATA_PROVENANCE、manifest |
| architecture/API | ARCHITECTURE、USAGE |
| gate/status | STATUS.yaml、ROADMAP |
| known limitation | MODEL_CARD、ROADMAP |

文件採 link-not-duplicate 原則；各細節只在其 owner document 定義。

## 12. 禁止用語轉換

| 避免 | 改用 |
|---|---|
| 真實動力學 | MuJoCo forward dynamics under assumed model |
| 實測 CoP/GRF | simulated contact-derived CoP/GRF |
| 硬體可行 | passed current SIM-only screening rule |
| 穩定度 100% | no indicator violation in the named nominal scenario |
| 0% 跌倒率 | zero falls in the named finite runs |
| 已驗證 | 指明 requirement ID、oracle、evidence bundle 與 gate |
