# V7 Exposure-Censoring Validity Audit — Frozen Bundle Run Receipt

日期：2026-09-08

Protocol：`AUDIT-V7-EXPOSURE-CENSORING-V1`

狀態：`AUDIT_COMPLETE / CONTRACT_VALID / RETAINED_CENSORING_BLOCKER / APPLIES_TO_FROZEN_V7_PILOT`

證據邊界：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED / DEVELOPMENT_ONLY`

## 1. 本次唯一目標

對 2026-09-06 保存的 `V7_PILOT_DEVELOPMENT_BUNDLE` 執行一次 read-only audit run，
記錄真實 exposure 分布、`phase_convention` finding 與 identification bounds。

本 receipt 與 [synthetic regression receipt](V7_EXPOSURE_CENSORING_AUDIT_IMPLEMENTATION_RECEIPT_2026-09-08.md)
並存且不取代它；該 receipt 記錄的是 audit software 在 synthetic bundle 上的驗證，本 receipt
記錄的是對 frozen pilot bundle 的實際量測。2026-09-06 的 pilot receipt 原文亦未回改。

## 2. Identity 與 read-only 證明

| 項目 | 值 |
|---|---|
| Source bundle class | `V7_PILOT_DEVELOPMENT_BUNDLE` |
| `audit_applies_to_frozen_v7_pilot` | `true` |
| Audited pilot receipt SHA-256 | `ed3e3eaa7c86f2b855d24aca68b09ce45bce61ac2fb6e573328b12157d758435` |
| Source artifacts | 14 個／`109520182` bytes |
| Pilot source Git（pre == post） | `058657dd43d28a9175e54362cf4d0a0618507c38` |
| `source_bundle_read_only_verified` | `true` |
| Audit protocol SHA-256 | `b15505b73f3745141c2dfa31cf57564b0863242949f5d1ad4d351dfb96dec6ce` |
| Frozen recorder source | `backend/rl/humanoid_env.py`、`26277` bytes、`2fc224d6…` |
| Frozen motion task source | `backend/motion_tasks.py`、`8892` bytes、`3dd9a47b…` |
| Independent replay 實作 | `backend/v7_exposure_audit_replay.py`、`79346` bytes、`ae7e0f97…` |

[RESULT] `AX-01..AX-12` 全部通過。14 個 source artifact 在 audit 前後各做一次 bytes 與
SHA-256 readback，且 audited bundle 的 regular-file set 前後相同，因此 read-only 是被檢查
過的性質而非宣稱。CLI 依 frozen semantics 回傳 exit `1`，因保留 35 個 censoring blocker。

[RESULT] `backend/rl/humanoid_env.py` 與 `backend/motion_tasks.py` 在 pilot source commit
`058657dd` 與本次 audit 執行時是同一個 Git blob，因此本 audit 重現的 recorder convention
正是當初記錄那些 traces 的同一份程式碼。

輸出 artifacts：

- `audit_receipt.json`：`5239` bytes；SHA-256 `6da78e2856d6e9be7727ff0de91515ee40fd4717acd439215c220f3f2c8f4b97`。
- `audit_summary.json`：`294701` bytes；SHA-256 `74f6edfa7ed04615f2dff60bccc9f10e818ecdb4c12b8dfa480717f29dc0ce94`。
- `audit_replay_receipt.json`：`2002` bytes；SHA-256 `1939eeb2de0b55f558e4592de1c672f77354973d7b4e78d87e2cb922afc33a79`。
- `source_index.json`：`5041` bytes；SHA-256 `e72d5eefef61f71ecd05287e1203449411caf6561db1b97ba6a05e6e29e13f0f`。
- Audit protocol copy：`28259` bytes；SHA-256 `b15505b7…`。

## 3. 真實 exposure 分布

Frozen horizon 為 `450` control steps／`4500` physics substeps／`9.0` s。

| Arm | FULL / EARLY / NONE | observed control steps（mean ± sd，min–max） | 終止 phase（recorder） | outcome states |
|---|---|---|---|---|
| V7A | 30 / 0 / 0 | `450.0000 ± 0.0000`，450–450 | `FINAL_STAND` ×30 | OBSERVED ×30 |
| V7B | 27 / 3 / 0 | `448.0333 ± 6.9107`，420–450 | `FINAL_STAND` ×30 | OBSERVED ×30 |
| V7C | 0 / 30 / 0 | `159.7000 ± 2.7687`，154–165 | `STEADY_WALK` ×30 | NULL ×30 |

[RESULT] V7C 的 30 個 episode 全部在 `3.08–3.30 s` 之間、於 `STEADY_WALK` 期間終止，
平均只實現了 frozen horizon 的 `0.354889`。

[RESULT] V7B 的 3 個 censored episode 全部落在 `FINAL_STAND`：

| Seed | control steps | 終止時間 | primary outcome | full-horizon bound |
|---|---:|---:|---|---|
| 18015 | 420 | `8.4` s | `OBSERVED` | `[22.444444, 29.111111]` % |
| 18021 | 445 | `8.9` s | `OBSERVED` | `[24.333333, 25.444444]` % |
| 18023 | 426 | `8.52` s | `OBSERVED` | `[23.488889, 28.822222]` % |

[RESULT] 這三個 episode 的 `outcome_state` 全為 `OBSERVED`。它們在 `FINAL_STAND` 內才終止，
因此六項 required numeric 全部有值、`reason` 為 null，在算術上看起來完全乾淨，實際上卻是
exposure censored。這正是本 audit 存在的理由：`outcome_state == OBSERVED` 不蘊含 full exposure。

### 3.1 與 pilot 自身紀錄的獨立交叉驗證

本 audit 只由 `control_step_trace` 長度導出 exposure，**不讀** pilot 的 gate 結果，也不讀
`fell` flag。

[RESULT] audit 獨立認定的 V7B early-termination seed set 為 `{18015, 18021, 18023}`，與
2026-09-06 pilot receipt 記錄的三個含 fall 的 negative episode 完全一致。第四個 negative
episode `18011` 的失敗是 stop-only（未跌倒），audit 正確地把它留在
`FULL_EXPOSURE / COMPARABLE`，共 450 steps。

[INFERENCE] 因此 exposure 重建與 pilot 的獨立紀錄互相印證：跌倒集合可以只由 trace 長度
還原，而未跌倒的 gate 失敗不會被誤判為 censoring。

## 4. Identification bounds 與 paired comparability

| Arm | pilot reported duty | arm-level full-horizon bound |
|---|---:|---|
| V7A | `36.2185185 ± 1.0328300` % | `[36.2185185, 36.2185185]` %（degenerate） |
| V7B | `23.3896264 ± 1.0044698` % | `[23.282963, 23.720000]` % |
| V7C | `0 ± 0` % | `[0.0, 64.511111]` % |

| Contrast | comparable / censored / method-failure | pilot reported paired diff | audited aggregate | paired bound（mean） | sign identified |
|---|---|---:|---|---|---:|
| V7B − V7A | 27 / 3 / 0 | `-12.8288921 ± 1.0720320` pp | `NULL`（blocked） | `[-12.9355555, -12.4985185]` | **30 / 30 NEGATIVE** |
| V7C − V7A | 0 / 30 / 0 | `-36.2185185 ± 1.0328300` pp | `NULL`（blocked） | `[-36.2185185, +28.2925927]` | **0 / 30** |

[RESULT] V7C 的 arm-level bound `[0, 64.511111]` % **與 V7A 的 `36.2185185` % 重疊**；其
paired bound `[-36.2185185, +28.2925927]` **包含 0**，30 個 pair 全部 sign 不可識別。

[RESULT] V7B 的 paired bound 在 30 個 pair 中**全部排除 0 且皆為 NEGATIVE**，即使其中 3 個
pair 是 censored。

[INFERENCE] 兩個 candidate 落在完全不同的位置。V7C 報出的 `-36.22` pp 在 worst-case
censoring 下連方向都不可識別，因此該數字是 exposure artifact，不是 saturation 改善的證據；
這一點現在是**量測結果**，不再是敘述。V7B 的 saturation 下降則對 worst-case censoring
穩健（方向在每個 pair 都被識別），但 aggregate 仍為 `NULL`，因為 censoring indicator 由該臂
自身的 early-termination 行為產生，禁止只取 comparable subset。

[BLOCKER] V7B 的 sign 穩健性**不是** candidate selection、不是 superiority claim，也不解除
pilot 的 eligibility 判定：V7B 在 frozen pilot 中仍因 reliability／stop／lateral 失敗而不
eligible，且本 audit 只有單一 training seed。`selected_candidate_arm_id` 維持 `null`。

## 5. Phase convention finding

[RESULT] `AX-04` 通過：90 個 episode 的每一筆 recorded `command_phase` 都等於本 audit
重現的 recorder convention（end-of-step accumulated sim time）。

| Phase | contract（start-of-step） | recorder（end-of-step accumulated） | 一致 |
|---|---|---|---|
| `INITIAL_STAND` | 0–49 | 0–48 | 否 |
| `START` | 50–124 | 49–123 | 否 |
| `STEADY_WALK` | 125–324 | 124–324 | 否 |
| `STOP` | 325–399 | 325–399 | 是 |
| `FINAL_STAND` | 400–449 | 400–449 | 是 |

[RESULT] Recorded phase label 相對 frozen task contract 的 start-of-step schedule 位移一個
control step，且只有 `INITIAL_STAND`／`START`／`STEADY_WALK` 三個邊界受影響。這是 pilot
instrumentation 先前未記載的性質，本 audit 原樣保留為 validity finding，不修改保存資料。

[INFERENCE] 若沿用本 audit protocol freeze commit 的原始規則（recorded label 對照 contract
start-of-step schedule），本次 run 會在 `k=49` fail closed，把一份有效 bundle 誤報為
structurally invalid。該規則在任何 audit 執行前已依 amendment 修正。

## 6. Exposure-matched descriptive sensitivity

`status=DESCRIPTIVE_ONLY`、`informative_censoring=SUSPECTED_DEPENDENT_ON_ARM_BEHAVIOUR`。

| Contrast | matched exposure k | matched difference（mean ± sd） |
|---|---|---:|
| V7B − V7A | 420–450 | `-12.9968027 ± 1.0755263` pp |
| V7C − V7A | 154–165 | `-21.9635049 ± 1.2888118` pp |

[RESULT] 把 V7A 截斷到 V7C 的同一實現 exposure 後，V7A 在該窗口內已累積約 20–22 % duty，
而 V7C 為 0 %，差值 `-21.9635049` pp，並未消失。

[BLOCKER] 此值只是 denominator 對齊後的描述量，不恢復 comparability、不是 contrast、也不得
用於 candidate selection、CI、p-value、hypothesis test 或 sample-size 決策。截斷點由 V7C
自身跌倒產生，informative censoring 依然存在。

## 7. 保留的 blockers

`censoring_blocker_count=35`：V7B 3 個 censored episode、V7C 30 個 censored episode，
以及 2 個 non-comparable paired contrast。

`preserved_pilot_selection` 記錄 `selection_status=PILOT_RETAINED_SEMANTIC_BLOCKER`、
`selected_candidate_arm_id=null`、`audit_modified_pilot_conclusions=false`。

`pilot_planning_ready=false`、`method_level_power_ready=false`、`statistics_ready=false`、
`paper_data_ready=false`、
`formal_sample_size_decision=BLOCKED_INDEPENDENT_TRAINING_SEED_VARIANCE_NOT_ESTIMATED`。

## 8. Claim boundary

允許的結論只到：在 frozen MuJoCo plant、v5 warm start、單一 training seed 與 DEV evaluation
seeds `18000–18029` 下，v7 pilot 的 `saturation_duty_pct` paired contrast 在實現 exposure
不相等時的內部可比性如上所述 —— V7C 方向不可識別，V7B 方向可識別但 aggregate 仍 blocked。

禁止外推為 controller superiority、method-level effect、sample-size adequacy、paper
readiness、physical torque/thermal margin、安全、sim-to-real 或實體機器人效能。本 audit
未選 candidate、未計算 CI 或 p-value、未變更任何 threshold，也未開啟 FORMAL/HOLDOUT。

[BLOCKER] 仍缺 independent training-seed variance、full 11-criterion Live evidence、
actual Study A、frozen censored estimator、binary paired CI、complete environment lock、
project-wide immutable storage、HIL、bench 與 robot evidence。本次 run 不解除 V0/V1/V3 gate。

## 9. 下一步

Exposure-censoring validity audit V1 至此完成（software 已驗證、frozen bundle 已量測）。
依 pilot receipt 既定順序，下一步才是另立 fresh DEVELOPMENT protocol 處理
independent training-seed variance；在該 protocol 凍結前，不得依 V7B 的 sign 穩健性做任何
selection 或 sample-size 決策。

Primary/official sources：

- [NIST/SEMATECH Censoring](https://www.itl.nist.gov/div898/handbook/apr/section1/apr131.htm)
- [Rethinking the Handling of Method Failure in Comparison Studies, Statistics in Medicine 2025](https://doi.org/10.1002/sim.70257)
- [Empirical Design in Reinforcement Learning, JMLR 2024](https://www.jmlr.org/papers/v25/23-0183.html)
- [Deep RL at the Edge of the Statistical Precipice, NeurIPS 2021](https://proceedings.neurips.cc/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html)
- [IETF RFC 8259 — JSON](https://www.rfc-editor.org/rfc/rfc8259.html)
- [NASA-STD-7009B](https://standards.nasa.gov/sites/default/files/standards/NASA/B/1/NASA-STD-7009B-Final-3-5-2024.pdf)
