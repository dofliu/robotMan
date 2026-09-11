# Changelog

本專案採語意化版本概念記錄可公開的 development releases。所有版本目前仍屬 SIM-only prototype，不表示 physical validation maturity。

## Unreleased — 2026-09-11 (n)

### 動作任務範圍決定，與一個不需要新增動作就能做的 `R0` probe

- [SOURCE] 專案負責人詢問是否現在加入跳躍、轉身或其他基本動作。決定：**現在不新增**，紀錄於 [MOTION_SCOPE_DECISION_2026-09-11](docs/MOTION_SCOPE_DECISION_2026-09-11.md)。四個理由全部是量到的事實，不是偏好：
  - Motion Task V1 本身尚未通過（v5 Live 10/11，saturation duty `38.422222% > 30%`；v6 reward-only 無效；v7 選不出候選）。加第二、三個任務只是把未通過的任務數由 1 變成 3。
  - V1 plant credibility 四項（articulated dynamic、pendulum、energy、solver convergence）全缺，而**跳躍恰好依賴那四項**：飛行相無接觸、落地衝擊受接觸模型支配、能量守恆。在未驗證的 plant 上量跳躍，得到的是關於接觸模型的證據，不是關於跳躍的證據。
  - 轉身與跳躍的早期終止率高於走路，會把比較推入已經擊敗三個 budget probe 的 `R3`／`R4` regime，使 Track A 更難而非更容易。
  - 在版控 checkpoint lineage 建立前新增訓練線，會複製已使 `CONDITIONAL_ON_FIXED_WARM_START` 對 v7 線永久成立的 provenance 損毀。
- 凍結順序：[ROADMAP §9](docs/ROADMAP.md) 第 1、2 項 → 原地轉身（需 `PUB-B2` 出口條件）→ 跳躍（需 V1 PASS）。教學支線不受阻擋，但須標 `DEVELOPMENT_ONLY / NOT_EVIDENCE`，且平衡動作須依 [ROADMAP §8](docs/ROADMAP.md) 定義 contact/support acceptance。
- [RESULT] **調查中發現 taxonomy 的空格不需要新增動作任務就能探測。** [TRACK_A_REFRAME §3](docs/TRACK_A_REFRAME_2026-09-09.md) 六格 regime 中只有 `R0`（兩臂皆 full exposure）是空的。retained 的 450 個 seed-variance evaluation episode，其 `control_step_trace` 每個 control step 都記有 `saturation_substeps_over_threshold` 與 `saturation_substeps_total`（恆為 `10`，即 500 Hz），因此**任意截斷 horizon 的 duty 皆可精確重算**。在全 horizon 上，重算值與凍結的 `metrics.saturation_duty_pct` 對 **450/450 episode 完全相等**，零不符。
- 據此凍結 **`R0-REGIME-HORIZON-PROBE-V1`**：[R0_REGIME_PROBE_SPEC](docs/R0_REGIME_PROBE_SPEC.md)（`sha256:a15cada6…`）與 `backend/rl/r0_regime_probe_protocol.json`（`sha256:07cf6d21…`），狀態 `FROZEN_BEFORE_EXECUTION`。它不訓練、不評估、不動任何 seed，只對既有資料唯讀重算。
- 設計主軸是一個張力：**R0 與 metric 非退化互相拉扯**——截得夠早則沒人跌倒但窗口全在初始站立、reference saturation 趨近 0（即 Hopper probe 落入的 `R5`）；截得夠晚則 censoring 回來。因此 adequacy rule 是**兩段式**：`R0-P0a` 要求 reference 與 candidate 各 150 個 episode 全部 `H_COVERED`；`R0-P0b` 要求 reference 平均 duty 落在 `[5.0, 95.0]` pp。
- [INFERENCE] `R0-P0b` **刻意只約束 reference**：A-C3 的前置條件是「參照臂能否表達對比」，不是「對比是否存在」。對 candidate 設下界等於在結果上做選擇——candidate duty 很低正是可能要被觀察到的結果。這是 Hopper probe 缺口的正確修法，不是它的翻版。
- Horizon grid `H ∈ {125, …, 450}`，下界 `125`（2.5 s）取自 [MOTION_TASK_SPEC](docs/MOTION_TASK_SPEC.md) 凍結 phase 表的 `STEADY_WALK` 起點——由設計常數決定，不由資料決定。選擇規則取最大的 adequate horizon。四個 fail-closed 標籤中，`R0_EXPOSURE_ONLY` 與 `R0_NOT_REACHABLE` **是結果不是失敗**，不得以放寬門檻重跑。
- [BLOCKER] **`R0-PRE-01` 已完成，且有時效性理由。** 來源 `control_step_trace` 只存在於 gitignored 的 `backend/rl/artifacts/`，而執行環境是可回收容器；容器一旦回收，這批 trace 與 `policy.zip` 將永久消失且無法重跑復原（warm start 不可重建）——與毀掉 v7 provenance 的機制完全相同。因此先抽出最小充分統計量納入版控：`backend/r0_probe_evidence/2026-09-11/horizon_trace_index.json`（`sha256:6ad44934…`、`1,272,160` bytes、450 episodes、`158,338` control steps），15 個來源檔 digest **全部命中**母 bundle 的 retained 值。
- [BLOCKER] **probe 尚未執行**：沒有計算任何截斷 horizon、沒有指派任何標籤。其產出將為 `PILOT`、附帶 `CONDITIONAL_ON_FIXED_WARM_START`，且永遠不可寫成任何一臂在 9 s 任務上的陳述——截斷 horizon 的 duty 與 9 s 的 duty 是**不同的估計目標**。
- 對齊：`STATUS.yaml`（新增 `motion_scope_decision` 與 `r0_regime_probe` 兩個 key、`next_milestone`、`docs`）、[PROJECT_STATUS](docs/PROJECT_STATUS.md)（§0、§7 milestone、§8）、[PUBLICATION_PLAN](docs/PUBLICATION_PLAN.md)（`PUB-A2` gate 列、§8 第 2 點）、[TRACK_A_REFRAME](docs/TRACK_A_REFRAME_2026-09-09.md)（`R0` 列）、[ROADMAP](docs/ROADMAP.md)（§8、§9）、README。
- [BLOCKER] 本次沒有任何訓練、評估、seed 變更，也沒有修改任何既有 contract、protocol、門檻或 arm 定義；四個總開關皆為 false 不變。

## Unreleased — 2026-09-10 (m)

### `PUB-B0`：formal evaluation 授權；同時量出這條線上 selection 幾乎必然選不出東西

- [SOURCE] 專案負責人於 2026-09-10 指示「授權 formal evaluation」。紀錄於新增的 [PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10](docs/PUB_B0_AUTHORIZATION_RECEIPT_2026-09-10.md)，狀態 `AUTHORIZATION_GRANTED / PROTOCOL_STILL_NOT_EXECUTABLE / FORMAL_SEEDS_NOT_ACCESSED`。
- [BLOCKER] **授權是一項決定，不是一項狀態變更。** frozen protocol JSON 內 `execution_preconditions` 的 `EP-03` 仍硬寫 `"state": "BLOCKING"`，而 `assert_executable()` 讀的正是該 JSON；改為 `RESOLVED` 需要一次 narrowing-only、execution-before 的 amendment 並重新 pin contract 內的 `PROTOCOL_SHA256`（同 `SEEDVAR-AMENDMENT-01` 機制）。`EP-01`（audit contract 對 sealed seeds raise）與 `EP-02`（`eval_policy.py` 兩個 branch 都釘死 seed schedule）未動。
- [BLOCKER] `PUB-B4` 外部預註冊仍未完成，而 [PUBLICATION_PLAN §4](docs/PUBLICATION_PLAN.md) 的凍結順序是「授權在前、預註冊在中、解封在後」，且預註冊需要 registry 帳號、**只有專案負責人能做**。因此當日**沒有存取** FORMAL seeds `20000–20029`。
- [BLOCKER] **機器可讀的 authorization evidence 刻意未鑄造**：`_require_authorization` 要求 `protocol_sha256` 等於現行 digest `sha256:b4e16370…`，鑄造它等於選定「用現行 post-hoc 規則」這個尚未決定的子選項。
- [RESULT] **本次的實質內容是一項量測**：授權之後的問題不是「能不能跑」，而是「跑了會得到什麼」。由 retained seed-variance evidence（`seed_variance_summary.json`）重算，每臂 150 個 episode 的 `COMPARABLE` 數為 reference `V7A_REWARD_ONLY` **143/150**、`V7B_REDUCED_JOINT_ENVELOPE` **120/150**、`V7C_FILTERED_ACTION` **0/150**。`SEL-C2` 要求 reference 與 candidate 的每一個 episode 都 comparable；iid 外推的聯合通過機率為 reference + `V7B` **`2.2 × 10⁻¹⁸`**、reference + `V7C` **`0`**。`SEL-C4` 與之耦合（`between_replicate_sd` 為 null 的原因正是 censoring）。
- [INFERENCE] 結論不依賴精確機率，而依賴一個結構事實：**reference arm 自己就在 3 個 replicate 上早期終止**，而 FORMAL 用的是同一批已訓練 policy、只換 evaluation seed，沒有機制支持質性不同的結果。預期輸出是 `SELECTION_COMPLETE_NO_CANDIDATE`，機率接近 1。
- [BLOCKER] FORMAL 資料**只套用一次**（[V7_CANDIDATE_SELECTION_SPEC §5](docs/V7_CANDIDATE_SELECTION_SPEC.md)），且 `20000–20029` 是唯一未被檢視的範圍。在 v7 線上執行等於用掉它換一個 `NO_CANDIDATE`，並永久失去日後在該線做出可信 selection 的可能。失敗的原因不是規則設計，而是**這條 policy 線本身跑不完任務**，其 warm start 又不可重建。
- 因此 [PUBLICATION_PLAN](docs/PUBLICATION_PLAN.md) 升版 **`PUBLICATION-PLAN-V3`**：`PUB-B0` 由 `BLOCKED` 改為 `AUTHORIZED_2026-09-10 / SUB_OPTION_OPEN`；§5 由「一個決定」改為「已授權 + 兩個子問題」，新增子問題 (b)「唯一未檢視的 FORMAL seed 範圍花在哪條訓練線」，建議保留給 `PUB-B1`／`PUB-B2` 的新訓練線。Track A、Track C、§6–§7 與四個總開關不變。
- 對齊：`STATUS.yaml`、[PROJECT_STATUS](docs/PROJECT_STATUS.md)（§0、§6.5、§7 milestone、§8）、README（現況一覽、receipt 索引、下一階段）、[RESEARCH_EXECUTION_PLAN](docs/RESEARCH_EXECUTION_PLAN.md)。
- [BLOCKER] 本次**沒有**任何程式、contract、protocol、門檻、arm 定義、seed 或測試變更；frozen protocol JSON 逐位元不變（已驗證）。`paper_data_ready`、`statistics_ready`、`method_level_power_ready`、`sample_size_decision_input_ready` 皆為 false 不變；`selected_candidate_arm_id` 仍為 `null`。

## Unreleased — 2026-09-10 (l)

### `PUB-A0` 補充 scan：A-C5 降為 artifact 級（**縮小**主張）

- 完成 [LITERATURE_MAP §4 第 5 點](docs/LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md) 點名的最後一項 scan：preregistration／multiverse／post-hoc disclosure 文獻。新增 **§1.7**（14 條，全部 `U`）與 §6 的第二段查詢表（12 個查詢）。
- [RESULT] **判定縮小，不是擴張。** A-C5 原本是「公開宣告非預註冊 + 規則在啟發資料上必須失敗的自檢」這個次貢獻，現拆成三段檢視：
  - 「透明宣告假設／規則是 post hoc」已由 **Hollenbeck & Wright (2017, *Journal of Management*)** 命名為 **Tharking** 並提出辯護，Simmons et al. (2011) 的完整揭露建議更早。→ **不是**貢獻。
  - 「決策資料必須未被檢視」已由 **Cawley & Talbot (2010, JMLR 11)** 量化（model-selection over-fitting 幅度可與演算法差異相當；取最大值等於取 outlier）與 **Dwork et al. (2015, reusable holdout／Science 349)** 建立。本專案 sealed FORMAL seeds 與「只套用一次」是其最保守版本。→ **不是**貢獻。
  - 剩餘只有「把 negative-control falsification test 套在 **selection rule** 上，並以 fail-closed contract 保留其失敗證據」這一窄點；negative control 在 epidemiology 與 IV 設計（arXiv 2312.15624）已建立，但掃到的文獻套的是 outcome 或設計假設。[INFERENCE] 且 2312.15624 明確警告 falsification test 的解讀受混淆——**同樣的混淆適用於本專案**：規則在 DEV 資料上選不出候選，也可能只是因為該資料 exposure 不足（實測擋下 V7B 的正是 `SEL-C2` 的 full-exposure 條件），不必然因為規則保守。
- **A-C5 因此從「次貢獻」降為 artifact 級並併入 A-C4**，不再單獨作為主張。稿件改為引 Tharking 與 Cawley & Talbot 建立語彙與理由，把本專案的 contract 呈現為既有建議的**可執行化**，並如實寫出解讀限制。
- [RESULT] 另一項與本專案立場一致的發現：*Pre-registration for Predictive Modeling*（arXiv 2311.18807）主張 model design 過程太迭代難以 preregister，但**評估**不同（benchmark 與 baseline 的選擇離散可枚舉）。這正是本專案凍結 selection rule 而不凍結訓練迭代的理由，應在稿件引用。NeurIPS 已有 Pre-registration in ML Workshop（PMLR v148／v181），本專案**未**使用，須明說。
- [BLOCKER] **egress 重新量測（2026-09-10）**：`WebFetch` 對 `https://arxiv.org/abs/2311.18807` 回傳 `EGRESS_BLOCKED`；`WebSearch` 可用。因此 §1.7 全數為 `U`，`PUB-A0` **仍未 PASS**。狀態改為 `KEY_TWO_VERIFIED_AND_A_C5_SCANNED / REMAINING_U`；唯一剩餘工作是讀 §1.1、§1.3–§1.5、§1.7 與 §2 的 `U` 條目原文，優先四篇：Pardo 2018、Colas 2019、Manski 1990／Tamer 2010、Hollenbeck & Wright 2017。
- 對齊：[PUBLICATION_PLAN](docs/PUBLICATION_PLAN.md)（§2.1 的 A-C5 條、§3.1 gate 列、§8 下一步、§9 版本紀錄）、[TRACK_A_REFRAME](docs/TRACK_A_REFRAME_2026-09-09.md)（§4 貢獻表、§6 限制第 6 條、§8 gate 列、§10）、`STATUS.yaml`、[PROJECT_STATUS](docs/PROJECT_STATUS.md)、README。
- [BLOCKER] 本次沒有新的訓練或評估、沒有任何程式／contract／protocol／測試變更；`paper_data_ready` 等四個 flag 不變。

## Unreleased — 2026-09-09 (k)

### `PUB-A0`：關鍵兩篇原文核對，gap 仍成立

- 專案負責人提供 arXiv **1911.05728v1**（Leete, Kallus, Hudgens, Napravnik, Kosorok，*Balanced Policy Evaluation and Learning for Right Censored Data*，stat.ME 2019，29 頁）與 **2606.10229v1**（Bedi，*What Demonstration Curation Metrics Do to Your Policy*，cs.RO 2026，5 頁）的 PDF；全文抽出（pypdf）並逐頁讀完；檔案 SHA-256 記於 [LITERATURE_MAP §7](docs/LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md)。這兩篇是 [文獻地圖 §4](docs/LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md) 原本把 gap 判定**條件於**的兩篇。
- [RESULT] **1911.05728**：§2.1 明文假設 censoring time 在給定 covariates 與 treatment 下獨立於 failure time；§2.3–2.4 以 conditional expected survival time **補值**被 censor 的 outcome，再套 balanced policy weights；Theorem 1／3 為 consistency 與 regret／convergence-rate bounds，**不是 identification bounds**。條件「無 censoring 假設下給 bounds」不成立 → A-C1 的 gap **未消失**。該文成為 Track A 的「有假設、點識別、補值」對照；且其假設在本專案情境（censoring 由該臂自身行為產生）不成立。
- [RESULT] **2606.10229**：對象是 behavior-cloning 的 demonstration **curation** metric（LIBERO，早放夾爪缺陷，80% 污染）；§III-D 指出缺陷 demo 跑到 500 步 time limit 而成功 demo 約 325 步終止，任何 mean／cumulative feature 會混入 episode length，以**截到 T = 324** 的設計期處置移除（Table I：5/7 metric 的 AUROC 由 ≈1.0 掉到 0.44–0.76）；下游 policy evaluation（30 rollouts × 3 seeds）**未**處理 exposure、無 bounds。條件「truncation 討論涵蓋 policy evaluation」不成立 → gap **未縮小**。方向與本專案相反（該文缺陷 episode 較長）。
- [RESULT] 兩篇的參考文獻都沒有 Manski 或 partial identification。
- 文獻地圖：兩條目改為 `S`（source-verified）並依原文改寫；新增核實等級 `S`；§4 第 1、2 點改為「兩篇關鍵文獻核對後仍成立；其餘 `U` 待核」；§5 的 `PUB-A0` 狀態改為 `KEY_TWO_VERIFIED_GAP_STANDS / REMAINING_U`；新增 §7 核對紀錄。[PUBLICATION_PLAN](docs/PUBLICATION_PLAN.md) §2.1／§3.1／§8／§9、[TRACK_A_REFRAME](docs/TRACK_A_REFRAME_2026-09-09.md) §6／§8／§10、[PROJECT_STATUS](docs/PROJECT_STATUS.md)、README、`STATUS.yaml` 同步。
- [BLOCKER] `PUB-A0` **仍未 PASS**：其餘條目（Pardo、DERAIL、Colas ×2、AdaStop、2409.09491、SC'24、RepDL、Manski／Tamer 等）仍為 `U`，執行環境對出版方 host 的封鎖不變；A-C5 的 preregistration／multiverse scan 未做。沒有任何程式、contract、protocol、測試或 flag 被更動。

## Unreleased — 2026-09-09 (j)

### 三個 budget probe、一個決定、Track A 重構

- **三個 budget probe 全部記錄為 pilot，不是 evidence。** 為了讓第二案例的 reference 達到事先凍結的 adequacy（≥ 27/30 FULL_EXPOSURE、連續兩個 checkpoint），依序跑了 `SECONDCASE-V2-BUDGET-PROBE-V1`（Walker2d-v5、SB3 PPO 預設、上限 2,949,120）、`-V2`（同 plant、rl-zoo tuned recipe、上限 1,966,080）與 `SECONDCASE-V3-BUDGET-PROBE-HOPPER-V1`（Hopper-v5、tuned、上限 1,966,080）。每一次都在 clean source、同一 `locked_sha256` 下執行、0 mismatch；每一個上限都在看到曲線前寫死，**沒有一次事後提高**；每一次的下一步都在結果出來前寫下。詳見 [probe receipt](docs/SECOND_CASE_V2_BUDGET_PROBE_RECEIPT_2026-09-08.md)。
- [RESULT] Probe V1：360 個 probe episode 只有 1 個跑完 horizon → `PROBE_NEGATIVE_MAX_BUDGET_REACHED`。Probe V2：240 個中 5 個，全在一個 checkpoint，之後退化 → `PROBE_NEGATIVE_MAX_BUDGET_REACHED`。Probe V3：`PROBE_BUDGET_FOUND` 1,474,560（ck5、ck6 連續 30/30）。
- [BLOCKER] Probe V3 選出的 reference 是**站著不動**的 hopper：六個 checkpoint 的 return 中位數 1006–1014，選定 checkpoint 的 saturation 2.712%，兩個更早的 30/30 checkpoint ≈ 0%。凍結規則的缺口：adequacy 只檢查 exposure，不檢查 primary measurement 是否退化；reference 為 0% 時 naive 與 bound 的 contrast **必然同號**，artifact 在數學上不可能出現。記錄為 blocker，**沒有**事後修規則。
- [BLOCKER] Recipe 數值（rl-baselines3-zoo Walker2d／Hopper PPO）為 `U_VERIFIED_FROM_MEMORY`：執行環境無法讀 GitHub raw content。
- **軟體（為 recipe 與 plant 支援，全部有測試）**：`second_case_runner.py` 共用 `build_model()`／`wrap_normalizer()`、`policy_kwargs`（activation 限 Tanh／ReLU）、VecNormalize 訓練後存 `vecnormalize.pkl` 並記 digest、評估經 `VecNormalize.load(training=False, norm_reward=False)`；`second_case_budget_probe.py` 的 `recipe_override` 與 `environment_override`（plant 以 digest 重釘、`H·J` 重算）；contract 的 `CELL_SCHEMA_V2` 多一欄 `normalizer_sha256`。已知限制：probe 的 `vecnormalize.pkl` 每個 checkpoint 覆寫同一檔案，早期 checkpoint 無法事後重評（各 checkpoint 當時的評估正確；V2 cell 各有目錄，不受影響）。

### 專案負責人的決定（2026-09-09）：停止第二案例 V2 線，重構 Track A

- 三個選項——照 probe 結果凍結並執行 Hopper protocol（約 17 CPU-h；reference 2.7% 下 P2 power 不確定；且是在已知規則缺口下凍結）、開含 saturation 下限的 probe V4（再一輪無保證的 pilot）、停止並重構——**選擇停止**。
- **Contract：兩個從未 pin 的 protocol id 撤回。** `SECONDCASE-EXPOSURE-CENSORING-WALKER2D-V2` 與 `SECONDCASE-EXPOSURE-CENSORING-HOPPER-V1` 進入 `WITHDRAWN_PROTOCOLS`；`load_protocol` 在任何路徑（含 `require_pinned_digest=False`）以 `SECONDCASE_PROTOCOL_WITHDRAWN` 拒絕，錯誤訊息具名決定日期與文件；import 時斷言撤回 id 不得有 pinned digest；DEVELOPMENT bundle 無法綁到撤回 id（其 pinned digest 為 None）。V2 schema（P0、candidate-scoped P1、第六個 label）與 probe runner **保留為軟體**並持續測試；V1 retained evidence 的 bytes 與 replay 不變（測試固定）。新增 3 個測試、修改 1 個（second-case 測試 84 → 87）。
- **[TRACK_A_REFRAME_2026-09-09](docs/TRACK_A_REFRAME_2026-09-09.md)。** Track A 的論點從「在公開 benchmark 上重現 v7 的 artifact」改為「comparative evaluation 落在哪一種 **censoring regime** 決定 bound 是否有資訊、artifact 是否可能出現，而該 regime 由 budget／recipe／plant 決定、通常不被控制也不被報告」。五種 regime 各有已量測實例：R1 不對稱（v7 V7C，凍結量測 ×2）、R2 輕度 censoring 但 bound 有資訊（v7 V7B，θ 排除 0、5/5，`between_replicate_sd` 卻無定義）、R3 對稱重度（Walker2d V1，凍結量測）、R4 無可達的 adequate reference（probe V1／V2，pilot）、R5 退化 reference（probe V3，pilot + 數學陳述）。新增主貢獻 **A-C3**：censoring regime 是未被控制的設計變數；reference-adequacy 前置條件必須同時檢查 exposure 與 metric 非退化；方向可識別 ≠ 變異可估計。文件含 12 列 claim → evidence 對照（每列附 receipt digest）、10 條不可宣稱與限制、figure／table 計畫，即 `PUB-A2` 的草稿。
- **[PUBLICATION_PLAN](docs/PUBLICATION_PLAN.md) 升版 `PUBLICATION-PLAN-V2`。** `PUB-A1` 拆為 `PUB-A1a`（第二 plant 的機制證據，**PASS**，依據是既有的 Walker2d V1 receipt 與其凍結規則下的 outcome：A-C1 的 R3 實例、A-C2 的 284/284 `OBSERVED`）與 `PUB-A1b`（公開 benchmark 上的不對稱 regime，**CLOSED_NOT_ATTAINED**——不是 PASS、不是放寬，寫進稿件 Limitations 第一條；重開需新 protocol id 與含 saturation 下限的 probe 規則）。`PUB-A2` 進入 `IN_PROGRESS`。這是 V1 → V2 唯一的 gate 語義變更，在計畫 §3.1 與 §9 揭露。Track B、Track C、寫作規範與不可宣稱清單不變。
- [BLOCKER] **明文放棄的主張**：v7 的不對稱 artifact 在公開 benchmark 上重現。Probe 資料在稿件中只能以「凍結程序的 outcome label」與「關於規則的觀察」出現，任何關於 Walker2d／Hopper／PPO recipe 能力的陳述都在其凍結 claim boundary 之外。
- 對齊：`STATUS.yaml`（`publication_plan_status`、`second_case_exposure_status`、`second_case_exposure_receipt`、`next_milestone`、新增 `track_a_reframe`）、[PROJECT_STATUS](docs/PROJECT_STATUS.md)（§0、新 §4.4、§7、§8）、README、[ROADMAP §10](docs/ROADMAP.md)、[RESEARCH_EXECUTION_PLAN](docs/RESEARCH_EXECUTION_PLAN.md) `PUB-A` 列。
- 測試：`backend/` 1 failed / 729 passed（295.78 s）；唯一失敗仍是具名 lock 下記錄的 `PRIMARY_CASE_RECEIPT_IDENTITY`，未放寬。56 個 tracked markdown、0 個壞連結。
- [BLOCKER] 本次沒有新的訓練或評估、沒有任何 threshold／seed／budget 被調整；`paper_data_ready` 等四個 flag 不變。

## Unreleased — 2026-09-08 (i)

### `PUB-A1` 第二案例：凍結、push、執行完成

- **凍結先於資料。** `SECONDCASE-EXPOSURE-CENSORING-WALKER2D-V1`（[spec](docs/SECOND_CASE_EXPOSURE_CENSORING_SPEC.md)，protocol `sha256:45d1ec55…`）在任何 Walker2d run 之前 commit 並 push（PR #7）。Gymnasium `Walker2d-v5` **全預設**，兩臂共用一個 wrapper 只差 `alpha`（1.0 vs 0.25），5 × 30 配對 seeds，PPO from scratch 精確 `301,056` 步。**不預測方向**；P1／P2 與五個 outcome label 由 contract 強制。`preregistered=false` 由 contract 強制。
- **通用模組 `exposure_identification.py`。** stdlib-only；對 v7 seed-variance 的 retained evidence 重算全部 10 個 replicate bound 與兩個 method-level θ，**bit-exact**。兩套實作、同一份資料、同一個答案。
- [RESULT] 執行：10/10 cells `COMPLETED`、300 terminal records、0 method failure、每 cell realized 精確 301,056、environment lock 20 次驗證 0 mismatch（`locked_sha256` 與 seed-variance 執行**相同**）、`python -I -S` replay bytes 一致。證據保留於 `backend/second_case_evidence/2026-09-08/`。
- [RESULT] **`SECOND_CASE_ARTIFACT_REPRODUCED`**：naive `W2D_C − W2D_A` = `−28.795138` pp、95% t-interval `[−46.698919, −10.891357]`（排除 0）；identification bound θ = `[−79.118, +55.913333]` pp（含 0、0/5 可識別）。同一份資料、兩種 estimator、相反結論——v7 的機制在第二個 plant 上重現。P3：284/284 early-terminated episode 的 `outcome_state` 皆 `OBSERVED`。
- [BLOCKER] **gate 仍未 PASS。** 只有 16/300 episode 跑完 horizon，reference 本身 4/5 replicate 30/30 早跌；bound 因兩臂皆 censored 而必然含 0。這證明「對稱 censoring 下 naive 會偽造方向」，但沒有重現 v7 的關鍵形狀（reference 近乎 full、bound 單側變寬）。budget 選擇的後果，如實記錄；**不得**回頭調 budget 重跑 V1。下一步凍結 V2（reference 達事先凍結的 full-exposure 比例）。詳見 [execution receipt](docs/SECOND_CASE_EXPOSURE_CENSORING_EXECUTION_RECEIPT_2026-09-08.md)。
- [BLOCKER] `direction_claim_permitted=false`；`paper_data_ready` 等 flag 不變；NPZ trace 與 checkpoint 為 gitignored 本機 artifact，digest 保留於 raw bundle，且本次沒有任何主張依賴它們。

## Unreleased — 2026-09-08 (h)

### 文件重整與學術產出規劃

- **README 從狀態傾倒回到入口。** 原「下一階段」一節已成長為約 1,500 字的狀態敘述；全數移入新的 [PROJECT_STATUS](docs/PROJECT_STATUS.md)（gates、PDR、flags、已量測結果、依根因分類的 blockers、milestone 歷史、下一步），README 改為一張「現況一覽」表加指標。40 餘列的扁平文件表改為六類分組；補上先前漏列的 `V1_RAW_JACOBIAN_IMPLEMENTATION_RECEIPT_2026-08-31`。沒有任何連結被移除。
- **新增 [PUBLICATION_PLAN](docs/PUBLICATION_PLAN.md)（`PUBLICATION-PLAN-V1`）。** 三條 track、fail-closed 的 `PUB-A*`／`PUB-B*`／`PUB-C*` gates、執行順序與相依、寫作規範、不可宣稱清單。核心判斷：[INFERENCE] 原定 Study A 卡在 provenance 與 censoring 兩個**結構性**問題，不是算力；現在寫得出的是評估效度／可重現性方法論論文（Track A），且 Track A 不浪費 Track B。專案負責人只需做一個決定（`PUB-B0`）。
- **`PUB-A0` 文獻 scan 完成，但未通過。** 新增 [LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY](docs/LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md)。[BLOCKER] 執行環境的 egress proxy 封鎖 arxiv.org、PMLR、OpenReview、ACM DL 與 Semantic Scholar，**沒有任何一篇原文被讀過**；每條目標 `U`（unverified），gap 判定為條件式 [INFERENCE]。暫定結論：exposure censoring 作為 comparative evaluation 的 identification 問題、以及 `OBSERVED ⇏ full exposure` 的記錄層盲點**暫定有 gap**；reduction-order 發現**不是貢獻**（SC'24、RepDL 已建立），降為動機。關鍵待核兩篇：arXiv 2606.10229、1911.05728。
- **修正三處過期敘述。** `VV_PLAN.md §11` 與 `EXPERIMENT_PROTOCOL.md §1` 仍寫 seed-variance「尚未執行任何訓練」；`ROADMAP.md §9` 第 1 項仍是「執行已凍結的 SEEDVAR」。三處改為已執行、方向 5/5 可識別、variance null。`ROADMAP §9` 新增「有版控 lineage 的新訓練線」為第 2 項並說明它同時是 Track B 前置與 variance 解封的唯一途徑；`§10` 明確 Track A **不要求** V1/V3 PASS 的理由（它不對 plant 或 controller 做 claim）。
- `RESEARCH_EXECUTION_PLAN` 更新日期並新增 `P-NEW`、`PUB-A`、`PUB-B` 三列；`STATUS.yaml` 新增 `publication_plan_status`、`project_status_report`，`next_milestone` 改為雙軌並保留原授權敘述。
- [BLOCKER] 本次**沒有**新增任何證據、沒有執行任何訓練或評估、沒有變更任何 contract、protocol 或測試；`paper_data_ready` 等四個 flag 不變。

## Unreleased — 2026-09-08 (g)

### 兩個 milestone 分支：一個經查證關閉，一個凍結

`STATUS.yaml` 排定的 next milestone 有兩條路：估計 independent
**pretraining**-seed variance，或另立 selection protocol。第一條經查證關閉，第二條已凍結並實作。

### Pretraining-seed variance 不可量測 —— 是 provenance，不是算力

- 算力上完全可行（`5 + 15 = 20 × 122,880 = 2,457,600` timesteps，約 25 分鐘），所以先查 provenance。查完的結論是**不能做**。
- [SOURCE] `policy_registry.json` 記載 v5「**warm-started from the v4 local development artifact**」，且其被採用的 `122,880`-step checkpoint 是在另一個 `516,096`-step run **regressed 並 DEV 失敗**之後選出來的。
- [SOURCE] `.gitignore:31` 排除 `backend/rl/artifacts/`。版本控制中只有 3 個 policy artifact（`walk_0p7_legacy`、`curriculum_v2`、`phase_observable_v5`）—— **沒有 v3、沒有 v4**，磁碟上也沒有。
- [RESULT] 而 v5 自己的 training profile 寫 `warm_start_policy_id: null`、`planned_timesteps: 2000000`，與 registry 在 warm start 與 budget 兩件事上都矛盾。Driver 讀的是 profile，所以單看 frozen training contract，v5 看起來是從零訓練的。
- [INFERENCE] 三件事同時擋住：起點不存在、frozen contract 不記錄它、停止點本身是一次 selection（在新 seed 上照抄「取第 122,880 步」，等於把一次在舊 seed 上做過的 selection 當成規則）。v5 artifact 的 `sha256:c548867f…` 無法從本 repository 重建。
- [BLOCKER] 因此 `training_replicate_scope = CONDITIONAL_ON_FIXED_WARM_START` 對 v7 line 是**永久的**，不是待補的缺口。V7B 的方向結論永遠附帶「條件於那一個 v5 warm start」。這是**縮小**可宣稱範圍。
- Profile/registry 的矛盾**刻意不修**：`training_profiles.json` 已被 `SEEDVAR-AMENDMENT-01` pin 進 protocol，而該 protocol digest 又被 contract pin 住，其下游是已 merge 的 seed-variance evidence。修 metadata 而動搖一份**已完成執行**證據的 source identity，不划算。記錄於 [pretraining infeasibility receipt](docs/V7_PRETRAINING_SEED_VARIANCE_INFEASIBILITY_RECEIPT_2026-09-08.md)。

### `SELECT-V7-CANDIDATE-FORMAL-V1`：凍結一條自己承認不是 preregistered 的規則

- [BLOCKER] **本 protocol 是在已看過結果之後寫的。** 凍結時已知 V7B 的 bound `[-13.503408, -12.435259]` pp 排除 0、5/5 可識別。它**不得**被描述為 preregistered、blinded 或 confirmatory。`validate_protocol` 強制 `preregistered=false` 與四個 disclosure 欄位齊全；把它改成 `true` 的版本無法載入。
- 在這種情況下唯一還能提供的保護不是假裝沒看過，而是**讓規則對已看過的資料不生效**：只在未被檢視的 seeds 上決策、只套用一次、而且——最關鍵的——**把規則套在已看過的資料上必須選不出東西**。
- [RESULT] 對真實 DEV evidence 執行 `rule-check`：`SELECTION_COMPLETE_NO_CANDIDATE`。實際擋下兩者的是 `SEL-C2`（全數 full exposure）：V7B comparable `120/150`、V7C `0/150`，reference V7A `143/150`。另外從 summary 直接讀出、未進入條件鏈的事實：V7B 的 bound 排除 0（`SEL-C3` 本會 PASS），`between_replicate_sd` 為 `null`（`SEL-C4` 本會 FAIL）。
- [INFERENCE] 擋下 V7B 的兩條都直接來自上游 audit 與 seed-variance 的既有發現，不是為本 protocol 新造的。**如果規則是為了讓 V7B 通過而設計，它在我唯一看過的資料上就會讓 V7B 通過。**
- 決策資料只能是 sealed FORMAL `20000–20029`：`18000–18029` 已 `DEVELOPMENT_EXHAUSTED` 且被本 protocol 的作者看過，`19000–19029` 已退役且曾作為 v5 HOLDOUT。這不是偏好，是唯一剩下的選項。
- `SEL-C2` 要求候選與 reference 的**每一個** episode 都 `COMPARABLE`，因為 audit 量測確認 V7B 那 3 個 censored pilot episode 的 `outcome_state` 全是 `OBSERVED`、六項 required numeric 皆有值 —— 「outcomes observed」不蘊含 full exposure。`SEL-C4` 要求 `between_replicate_sd` 是點值，因為方向可識別而變異不可估計時，選出來的 candidate 無法規劃任何東西。
- Eligible 需要**六個明確的 PASS**；`NOT_REACHED` 與 `NOT_APPLICABLE` 都永遠不等於 PASS，所以缺輸入只能擋下 selection，不能放行。

### 這次在凍結前先量執行前置條件

- `SEEDVAR-AMENDMENT-01` 的代價是凍結時把 driver pin 住卻沒檢查跑不跑得動。本次先查，三項皆 `BLOCKING` 並寫進 protocol：`EP-01` audit contract 對 `SEALED_SEED_RANGE` 的 seed 直接 raise（而 exposure 分類正是 `SEL-C2` 的輸入）；`EP-02` `eval_policy.py` 兩個 branch 都把 seed schedule 釘死；`EP-03` 授權未取得。
- `assert_executable` 在任一項未解除時拒絕執行並具名列出。`test_measured_preconditions_still_match_the_code` 對 code 重驗這些斷言 —— 過期的 precondition 比沒有更糟，它會宣告一個已不存在的 blocker 或藏起一個新出現的。
- 解除順序寫進 protocol：**授權在前，解封在後**。在授權仍不存在時先拆掉 sealed-seed 的門，順序是反的。

### 一個我自己寫壞、被測試抓到的洞

- [RESULT] 第一版的 self-check **在任何輸入上都不可能通過**：它把 `SEL-C5` 當成必須提供的輸入，而 self-check 從不提供，所以 `SEL-C5` 恆 FAIL。那使「規則擋下 V7B」的論證變成空話 —— 它擋下一切，因此對規則本身沒有提供任何證據。
- 修正：`SEL-C5`／`SEL-C6` 在 self-check scope 下標為 `NOT_APPLICABLE`（兩者都不區分 candidate，也都不可由 summary 導出），因此一份乾淨的 summary **真的會通過** self-check —— 這才使它在真實資料上的拒絕成為證據。`test_the_self_check_could_have_passed_which_is_what_makes_it_evidence` 同時斷言兩個方向。
- 另有防漂移檢查：`test_the_protocols_documented_self_check_matches_what_the_code_reports` 逐條比對 protocol 記載的 self-check 表格與 contract 實際輸出的 condition chain；若分歧，frozen 文件就會在描述一個沒人在跑的規則。
- `SEL-01..SEL-09` 共 **47 個測試**通過。新增 [selection spec](docs/V7_CANDIDATE_SELECTION_SPEC.md) 與 [implementation receipt](docs/V7_CANDIDATE_SELECTION_IMPLEMENTATION_RECEIPT_2026-09-08.md)。
- [BLOCKER] **沒有執行 selection、沒有存取 `20000–20029`、沒有產生任何 FORMAL 資料、沒有選出任何 candidate。** `selected_candidate_arm_id` 維持 `null`，`method_level_power_ready`、`statistics_ready`、`paper_data_ready` 全部維持 `false`。

## Unreleased — 2026-09-08 (f)

### `SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1` 實際執行完成

- **凍結的 protocol 一開始是無法執行的**，而 freeze 沒有抓到這件事。`train_ppo.py` 對任何 v7 profile 硬性要求 `seed_base == 8700`，`eval_policy.py` 只在 pilot 路徑輸出 `control_step_trace` 且該路徑強制 pilot 自己的 artifact 目錄。凍結時把兩個 driver 都以 digest pin 住，卻沒有檢查它們能不能跑本設計。記錄為 [Amendment 01](docs/TRAINING_SEED_VARIANCE_SPEC.md)（執行前、narrowing-only），並在 `validate_protocol` 強制 amendment 必須同時聲明 narrowing-only 與 applied-before-any-execution——事後的 amendment 等於讓設計繞著資料重寫。
- 兩個 driver 各加一個**互斥**的 frozen identity：v7 profile 必須且只能宣告一個 governing protocol；replicate 的 training seed 由 protocol 依 index 解析，**永遠不能**由 CLI 提供。Pilot branch 的檢查順序原樣保留——我第一版把共用檢查上提，害得 arm 換掉時先觸發的 rejection 從 `V7_PROFILE_ID_MISMATCH` 變成 `V7_ENVIRONMENT_ID_MISMATCH`，被 pilot 自己的測試抓到並還原。
- 選擇擴充而非另寫 driver：另寫會複製 PPO geometry、warm-start transplant 與 artifact 寫入，而與 pilot 的可比性正建立在這些**完全相同**之上，兩份副本無聲分歧的風險更大。

### 實測結果

- [RESULT] `3 arms × 5 replicates × 122,880 = 1,843,200` realized timesteps、**450 個 terminal records、0 失敗**、獨立 `python -I -S` replay exact。每 run 約 `73` s（4 cores、`OMP_NUM_THREADS=1`）。證據保留於 `backend/seed_variance_evidence/2026-09-08/`。
- [RESULT] **V7B 相對 V7A 的方向跨獨立 seed 成立**：method-level bound `[-13.503408, -12.435259]` pp，**排除 0**，sign `NEGATIVE`，`5/5` replicates 方向可識別。這比 pilot 的單一 checkpoint 證據更強。
- [BLOCKER] **但 `between_replicate_sd` 仍是 `null`**（`BLOCKED_PARTIALLY_IDENTIFIED_REPLICATE_DIFFERENCES`）：每個 replicate 至少有一臂被 censored，5 個 paired difference 全是 interval，sample SD 沒有定義在 interval 上。`sample_size_decision_input_ready = false`，**sample-size 決策仍然 blocked**。方向可識別與變異可估計是兩件事，本次同時給出前者、拒絕後者。
- [RESULT] **第一個新發現：pilot 那個乾淨的 reference 是 seed 的性質，不是 arm 的性質。** Pilot 的 V7A 在 seed `8700` 上是 30/30 full exposure、sd `0`；在 5 個獨立 seeds 上 V7A 有 3 個 replicate 出現 early termination（r2 `{18013}`、r3 `{18001,18004,18005,18014,18016}`、r4 `{18000}`，共 7/150）。reference cell 一旦被 censored，paired bound 兩端都會變寬——這只有在有獨立 replicates 之後才看得見。
- [RESULT] **V7C 的崩潰跨 seed 完全重現**：5 個獨立 seeds 全部 30/30 early termination、30/30 `NULL` outcomes，method-level bound `[-37.195407, +27.315704]` pp 含 0、`0/5` 方向可識別。它表面上的 `-37` pp 再次被量測確認為 exposure artifact，而且現在證明那不是單一 seed 的壞運氣。
- [RESULT] 450 個 episodes 全部落在 `COMPARABLE`（`263`）或 `EXPOSURE_CENSORED`（`187`），**零 method failure**。15 個 cell 只有 2 個 `POINT_IDENTIFIED`（V7A r0/r1，level SD `1.091723`/`1.103957`%），因此三臂的 `mean_level_sd_pct` 皆為 `null`——fail-closed 的正確輸出。
- [BLOCKER] `selected_candidate_arm_id` 維持 `null`。**V7B 的方向穩健性不構成 selection**：用同一批資料先估變異再據以選擇，會把選擇條件建立在被選中的雜訊上。要選必須另立 protocol version，且因為本結果已公開，任何新 selection protocol 都必須明示它是在已知 V7B 為負的情況下設計的。

### Provenance 與過程中的自我修正

- 每個 cell 綁定四項：frozen audit protocol digest（哪些規則）、`v7_exposure_audit_contract.py` 與 `v7_pilot_contract.py` 的 source digest（哪些實作套用了規則）、以及該 cell 的 `evaluation_output_sha256`（套用在哪一份 raw 輸出上）。原本設計的 `audit_summary_sha256` 無法使用：audit 的 frozen bundle classes 只有 pilot bundle 與 synthetic regression bundle，而本資料兩者皆非；把真實量測稱為 synthetic 以便重用 CLI 會敗壞該 class 存在的目的。兩個 implementation pin 在分析時對磁碟重新 hash。
- Bundle adapter 重用 `v7_pilot_contract` 的 canonicalisation 與 audit 的 `_episode_exposure`。重用在這裡正確、在 replay 裡錯誤：audit 是 exposure 的 frozen 上游權威，而 replay 存在的目的是檢查本 contract 的算術，因此不得共用任何東西。
- [RESULT] **Guard 抓到的是我自己。** 第一次執行跑完 2 個 replicate 後，其餘 13 個全部以 `SEEDVAR_SOURCE_GIT_NOT_CLEAN` 拒絕——因為我在 runs 進行中修改 tracked files。這是 guard 按設計運作：source identity 釘不住的 training run 作為 evidence 一文不值。修正是把程式修改先 commit 完再跑，不是放寬 guard。（另外我自己的 runner script 在失敗路徑 `mkdir -p` 了 run 目錄，於是 driver 的 `exist_ok=False` 防覆寫 gate 正確擋下重試。）
- 新增 [execution receipt](docs/TRAINING_SEED_VARIANCE_EXECUTION_RECEIPT_2026-09-08.md)。保留證據會從 repository 重新驗證並 exact replay，由測試斷言。

## Unreleased — 2026-09-08 (e)

### `ENVIRONMENT-LOCK-V1`：把 environment identity 從 floor 變成量測

- `docs/VV_PLAN.md` 的 V0-R02 要求 run identity 綁定 `code bundle/config/MJCF/checkpoint/environment`。前四項本來就有 content-sensitive identity；第五項只有 `backend/requirements*.txt` 的 `>=` floors。**Floor 描述的是一個無上界的環境集合，不是一個環境**，因此不能用來重驗任何數值結果。
- 新增 [ENVIRONMENT_LOCK_SPEC](docs/ENVIRONMENT_LOCK_SPEC.md)（實作前凍結）與 `backend/environment_lock.py`。Record 分兩段：進 digest 的 `locked`（會改變數值結果或 code path 的事實）與保留但不進 digest 的 `observed`（hostname、絕對路徑、CPU 數量等在合規機器間合法變動的上下文）。這個分界是必要的：若把 `observed` 一起 digest，同一個環境每次 capture 都會拿到新 identity，lock 就不帶資訊。
- **Fingerprint 量測行為，不相信 version string。** 同一個 `numpy==2.4.6` 可以連到不同 BLAS、用不同 SIMD kernel。因此 record 內含實際跑 `500` 個 `mj_step` 後的 MuJoCo contact state digest、以及實際執行一次 torch forward/backward/SGD 後的 parameter digest；probe 輸入來自模組內凍結的 pure-Python LCG，不用 `numpy.random`／`torch.random`（RNG stream 穩定性本身就是會隨版本改變的事實，不能同時當 probe 的載具）。
- 實測差異直接證明了這一點：同一組 `1/i, i = 1..1000` 依序左至右相加得 `7.485470860550343`，交給 `numpy.ndarray.sum` 得 `7.485470860550345`。**同一個環境、兩種 reduction order、兩者都符合 IEEE 754。** 這也是 `test_v1_analytical_suite.py::test_stdlib_replay_passes_exact_synthetic_fixture` 的 `PRIMARY_CASE_RECEIPT_IDENTITY` 在本 lock 下失敗的原因；本次**不放寬該 gate、不改寫 fixture**，只把它記為在具名 lock 下量到的失敗。
- 所有 third-party import 都是 lazy 且封在 probe 內，所以另一個 `python -I -S` process 可以在完全沒有 site packages 的情況下重算 `locked_sha256`。`test_module_keeps_every_third_party_import_inside_a_probe` 以 AST 斷言這件事：未來若有人加一行 top-level `import numpy`，其他測試都還會綠，只有這一個會失敗。
- 保留實測 record `backend/environment_locks/lock-2026-09-08-remote-dev-container.json`（`4157` bytes，`locked_sha256 sha256:d350a110…`，`FULL_LOCK`，`AMBIENT_THREADING_NOT_PINNED` 因為本容器未設 `OMP_NUM_THREADS`）與 `backend/requirements-lock-2026-09-08.txt`。`requirements.txt` 的 floors **未調整**，只加註解指向本 contract：調 floor 有 install 後果，不是本 contract 該決定的事。
- **v7 的判定：`ABSENT_UNRECOVERABLE`。** `PILOT-V7-ACTION-INTERFACE-DEV-V1` 與 `AUDIT-V7-EXPOSURE-CENSORING-V1` 都在本 contract 之前產生，沒有 lock record。`absent_lock_record()` 刻意不含任何量測值——把今天這台機器的 capture 附到一份在未知環境產生的 evidence 上是 imputation，不是補齊欄位。
- `EL-01..EL-10`／**60 個測試**通過。Contract 的 schema、digest 與 verification 路徑不依賴任何 third-party 套件，third-party 只出現在 probe 內部。V0 的 environment-lock blocker **收窄但未解除**：還沒有任何 pipeline 把 lock record 綁進自己的 run manifest。

### `SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1`：凍結 independent training-seed variance protocol

- 這是 `STATUS.yaml` 自己排定的 next milestone。新增 [TRAINING_SEED_VARIANCE_SPEC](docs/TRAINING_SEED_VARIANCE_SPEC.md) 與 `backend/rl/training_seed_variance_protocol.json`，**在任何 source implementation 前凍結**。
- **Analysis unit 是 training replicate，不是 episode。** Method-level 分母恆為 `replicate_count = 5`；`150`（episode-level pairs）與 `450`（terminal records）在 protocol 內被明列為 forbidden denominators。把 150 個 episode-level pair 當成 150 個獨立單位，是把 evaluation-seed 變異冒充成 training-seed 變異，標準誤會縮小約 `sqrt(30)` 倍。這條規則在三處被檢查，名稱為 `PSEUDO_REPLICATION_FORBIDDEN`。
- **Exposure censoring 逐層向上組合，不在中途退回點估計。** Cell、paired、method 三層都用 interval arithmetic（對 independent unknowns 皆為 tight）。只要有任一 replicate difference 不是 point-identified，`between_replicate_sd` 就輸出 `null`：sample SD 沒有定義在 interval 上，用區間中點代替就是 imputation。依 audit 的實測結果，V7C 幾乎確定落在這個 blocked 分支——那是**正確**輸出。
- **Method failure 不是 censoring。** 含 method failure 的 cell 沒有 mean，因為要產生一個 mean 就得刪掉那個 failure；因此 method-level bound 變 `NULL` 並列出被 blocked 的 replicate。
- V7C 仍必須執行。把已知會截斷的 arm 移出設計，等於用結果決定樣本。
- Selection 在本 protocol 內**永久禁止**，`replicate_count` 不得在看到結果後上調（optional stopping）。用同一批資料先估變異再據以選擇，會把選擇條件建立在被選中的雜訊上。
- 兩個 scope 限制被寫成 typed field 而非留在字裡行間：所有 replicates 共用同一個 v5 warm start，故 `training_replicate_scope = CONDITIONAL_ON_FIXED_WARM_START`，估到的 SD **系統性低估**完整 method variance；且因 v7 沒有 lock record，`cross_protocol_comparability = NON_VERIFIABLE_ENVIRONMENT`，並逐條列出禁止的操作。
- **Plant identity 附帶量到一個事實。** Protocol 改 pin plant 而非只 pin source file，於是可以檢驗：用 v7 所 pin 的那份舊 `model_builder.py`（`0beabfa2…`）重建 training MJCF，得到與現行檔案**完全相同**的 `7594` bytes 與 `sha256:fd0a191f…`。`geom_render_list` 的修正從未觸及 `build_mjcf` 或 `make_model`，所以 **plant 與 pilot 的 plant byte-identical，即使 source file identity 不同**。這不證明 solver 行為相同——pilot 仍沒有 lock。
- 算力誠實列出：`3 arms × 5 replicates × 122,880 = 1,843,200` timesteps，是 v7 pilot 的 5 倍。**因算力不足而減少 replicate 數需要另立 protocol version。**

### Seed-variance evidence contract 與獨立 replay

- 新增 `backend/training_seed_variance_contract.py`、`backend/training_seed_variance_replay.py`、`backend/build_training_seed_variance_regression_bundle.py`。`SV-01..SV-12`／**101 個測試**通過。
- Contract 消費 audit 輸出但**不信任**它：每一個繼承來的 bound 都對照自身宣告的 comparability state 重新檢查（comparable 必須 degenerate、censored 必須不是、method failure 不得帶 bound、width 必須相符、interval 不得反轉）。這些正是會無聲改變所有下游區間的變異。
- `verify_pilot_inheritance` 補上 freeze 的一個真實缺口：pin pilot 的 digest 只證明「打算用哪個檔案」，不能阻止本 protocol 從裡面抄錯數字。因此 warm start、arm 清單與順序、PPO geometry、episode 數與 seed ranges 逐欄比對 `backend/rl/v7_action_interface_pilot_protocol.json` 本身，並複查 pilot 自陳的「每臂一個 training replicate」——若那一項變成大於 1，本 protocol 就沒有量到 pilot 量不到的東西。
- Replay 是第二個實作而不是第二次呼叫：它不 import contract，從 protocol JSON 重讀 arm roles／seeds／denominators／lock requirement。兩邊共用一個 reduction 定義（`ordered_mean` 依 ascending replicate/seed 順序左至右相加），因為 float 加法不具結合律；`test_reduction_order_is_fixed_not_sorted` 以 `[1e16, 1.0, 1.0]` 與其反序證明順序會改變答案。
- Synthetic regression（clean source `7d961cbf`，19 artifacts／`978501` bytes）三個 case 全部 replay exact：`all-comparable` 0 blockers；`censored-candidate` 7 blockers、V7C theta bound `[-28.607824, +35.903276]` pp、`0/5` 方向可識別、SD 為 `null`；`method-failure` 2 blockers、V7B theta `NULL` 且 replicate 2 blocked。censored V7C bound 寬度 `64.5111` pp 與 audit 在 frozen bundle 上量到的 `64.511111` 一致。
- 修掉一個 lock 驗證顆粒度與 spec 不符的缺陷：spec 要求每一個 training **與** evaluation run 之前都要 verify lock，但 raw schema 起初每個 cell 只有一個 flag，把兩個獨立 run 混成一個 —— training 驗過而 evaluation 沒驗過的 cell 會通過。改為 `training_environment_lock_verified` 與 `evaluation_environment_lock_verified` 兩個欄位皆須為 true，receipt 記錄 `2 × 5 × 3 = 30` 次 verification。Frozen protocol 只規定 verify point 不規定欄位名，故未動到它。
- 順帶修掉 contract 的一個行為缺陷：`analyse_seed_variance` 現在拒絕位於 source bundle 內的 output root。把衍生 artifact 寫進被審查的 bundle 會破壞 read-only 保證，而原本的 "file set changed" 失敗訊息會怪錯對象。
- **也修掉自己 fixture 的一個缺陷**（值得記錄，因為它會讓 suite 假綠）：初版讓三臂共用同一組 per-replicate offset。Replicate-level pairing 正是用來消掉共同 offset 的，所以它在 contrast 中被完全抵銷——`between_replicate_sd` 只有 `0.146` pp 對比 within-replicate paired SD `0.811` pp，測試全綠但從未驗證「paired difference 的 between-replicate 變異」，也就是本 protocol 唯一要量的東西。修正後每臂各有自己的 offset series，並新增測試直接斷言該性質。修正後 fixture 上正確的 `n=5` 標準誤比 pseudo-replicated 的 `n=150` 標準誤大 `12.92×`（V7B）與 `10.11×`（V7C）——這是機制示範，不是 v7 的結果。
- 新增 [environment lock receipt](docs/ENVIRONMENT_LOCK_IMPLEMENTATION_RECEIPT_2026-09-08.md) 與 [seed-variance receipt](docs/TRAINING_SEED_VARIANCE_IMPLEMENTATION_RECEIPT_2026-09-08.md)。
- **沒有執行任何訓練。** 因此沒有任何 v7 method-level variance 數值；`selected_candidate_arm_id=null`、`method_level_power_ready=false`、`statistics_ready=false`、`paper_data_ready=false` 全部保留，`formal_sample_size_decision` 改為 `BLOCKED_UNTIL_THIS_PROTOCOL_EXECUTES`。

## Unreleased — 2026-09-08 (d)

- 修正 `geom_render_list()` 的 geom 型別查表：`MjModel.geom_type` 回傳 `numpy` 整數，而 MuJoCo 3.12 把 `mjtGeom` 實作為 native pybind11 enum —— 它與 `int` 相等但**與 `numpy.int32` 不相等**。以 enum 當 dict key 因此每一次查表都 miss，該函式回傳**空的 geom 清單**，`/ws/live` 的 scene payload 一個 geom 都不送，前端 3D 視圖實際上什麼都畫不出來。改為以 plain `int` 建表並以 `int(...)` 查表，與 `vv_oracles.py` 既有的正確寫法一致。修正後 minimum-config 模型的 25 個 geom 全部輸出（plane 1／box 5／sphere 11／capsule 8），`obstacle_0` 也回來了。
- 這是先前在 PR #1／#2 被低估為「環境相關測試失敗」的兩項之一。成因確實是 dependency 變更，但實際影響是 user-visible 的 live 視圖全黑，不是測試細節；該描述已在此更正。
- 新增 `test_geom_render_list_maps_every_supported_geom_type`：直接對 `geom_render_list` 斷言 `len(rendered) == model.ngeom > 0`，因此**部分**或**全空**清單都會被抓到。原有的 `obstacle_0` 斷言無法區分「只掉了障礙物」與「整個 scene 是空的」。該測試已驗證具鑑別力：把修正還原後它會失敗，套用修正後通過。
- 全庫掃描確認這是此 bug class 的**唯一**一處；`vv_oracles.py` 的 `mjtObj` 用法是把 enum 當函式引數傳給 `mj_id2name`，屬正確用法。前端 `Viewport.tsx` 對 plane／box／sphere／capsule 四型皆有分支，因此恢復清單不會觸發未處理的型別。

### Provenance 後果（必須記錄，不可默默吸收）

- `backend/model_builder.py` 的 SHA-256 由 `0beabfa2df6fde118dc2dfaea94a22da9af42c69c49ee2290993322cf96aab29` 變為 `09163a81a9dfef363a88424f98e4506e81be7639689aaa3fd66e6505ccb98a5e`。
- Frozen 的 `PILOT-V7-ACTION-INTERFACE-DEV-V1` protocol 仍 pin 舊值，且**刻意不改**：該 protocol 自身的 SHA `719b70a2…` 同時被 `v7_pilot_contract.py` 與 exposure-censoring audit protocol pin 住，改它會破壞既有 evidence chain。
- 因此語意是：**v7 pilot 已無法從目前這棵樹 byte-reproducible 重建**。這是事實，應該可見而非隱藏。
- 已逐項驗證受影響範圍：`validate_v7_pilot_bundle` 經 `_validate_source_index_deep` 一律以 `verify_repository=False` 呼叫 `_validate_source_files`，因此**保存的 pilot bundle 仍可從本樹通過驗證**；exposure-censoring audit protocol 只 pin pilot receipt、pilot protocol、`motion_tasks.py` 與 `humanoid_env.py`，**完全未提及 `model_builder.py`**（已以程式確認），因此 audit 與其 receipt 不受影響；只有帶預設 `verify_repository=True` 的**未來** `build_v7_pilot_bundle` 重建會 fail closed。
- `test_v7_pilot_contract.py` 的 synthetic `_source_files()` 仍寫舊值，這是正確的：它必須對齊 frozen protocol 的 pin，且該路徑以 `verify_repository=False` 執行，不觸碰磁碟檔案。

## Unreleased — 2026-09-08 (c)

- 對 2026-09-06 保存的 `V7_PILOT_DEVELOPMENT_BUNDLE` 執行 `AUDIT-V7-EXPOSURE-CENSORING-V1` 的第一次 read-only run，完成 exposure-censoring validity audit V1 的 data 部分。`audit_applies_to_frozen_v7_pilot=true`、`AX-01..AX-12` 全通過、14 個 artifact／`109520182` bytes 在前後 readback 一致且 file set 不變，`source_bundle_read_only_verified=true`，CLI 依 frozen semantics 回傳 exit `1` 並保留 35 個 censoring blocker。
- 實測 exposure：V7A 30/30 `FULL_EXPOSURE`（恰 450 control steps，sd 0）；V7B 27 full + 3 `EARLY_TERMINATED`（420／445／426 steps，`8.4`／`8.9`／`8.52` s，全落在 `FINAL_STAND`）；V7C 30/30 `EARLY_TERMINATED`（`159.7000 ± 2.7687` steps、`3.08–3.30` s、占 horizon `0.354889`，全落在 `STEADY_WALK`）。
- V7C 的 0% duty 經 assumption-free full-horizon bound 量測為 `[0.0, 64.511111]`%，與 V7A 的 `36.2185185`% 重疊；paired bound `[-36.2185185, +28.2925927]` 包含 0，`0/30` pair 方向可識別。pilot 報出的 `-36.2185185` pp 因此被量測確認為 exposure artifact，而非 saturation 改善 —— 這項判斷從敘述變成結果。
- V7B 的 paired bound 在 `30/30` pair 全部排除 0 且皆為 NEGATIVE，即使含 3 個 censored pair；aggregate 仍為 `NULL`（`BLOCKED_EXPOSURE_CENSORED_PAIRS_RETAINED_NO_COMPLETE_CASE_DELETION`）。此方向穩健性不構成 candidate selection、不解除 V7B 的 ineligibility，也不改變單一 training seed 的限制。
- 獨立交叉驗證：audit 只由 `control_step_trace` 長度導出 exposure（不讀 gate 結果、不讀 `fell` flag），卻還原出與 pilot 紀錄一致的跌倒 seed 集合 `{18015, 18021, 18023}`，並正確地把 stop-only 失敗的 `18011` 留在 `FULL_EXPOSURE / COMPARABLE`。
- 實測盲點確認：V7B 那 3 個 censored episode 的 `outcome_state` 全為 `OBSERVED` —— 它們在 `FINAL_STAND` 內才終止，六項 required numeric 皆有值、`reason` 為 null，算術上看不出異常。`outcome_state == OBSERVED` 不蘊含 full exposure。
- `AX-04` 在真實資料上通過：90 個 episode 的每一筆 recorded `command_phase` 都等於重現的 end-of-step accumulated recorder convention。該 convention 相對 contract 的 start-of-step schedule 位移一個 control step，只影響 `INITIAL_STAND`／`START`／`STEADY_WALK` 邊界，原樣保留為 validity finding。若沿用 protocol freeze commit 的原始規則，本次 run 會在 `k=49` 誤判為 structural failure。
- Descriptive exposure-matched sensitivity：V7B `-12.9968027 ± 1.0755263` pp（k 420–450）、V7C `-21.9635049 ± 1.2888118` pp（k 154–165）。截斷對齊後差值未消失，但仍為 `DESCRIPTIVE_ONLY` 且 informative censoring 依然存在，不得用於 selection、CI 或 sample-size。
- 新增 [frozen bundle receipt](docs/V7_EXPOSURE_CENSORING_AUDIT_FROZEN_BUNDLE_RECEIPT_2026-09-08.md)；2026-09-06 pilot receipt 與 synthetic regression receipt 皆未回改。`PAPER_DATA_READINESS` 的 PDR-5／PDR-6 與立即執行順序第 9 項更新為 DONE，第 10 項改為 independent training-seed variance protocol。
- 保留的 blocker 未變：`selected_candidate_arm_id=null`、`pilot_planning_ready=false`、`method_level_power_ready=false`、`statistics_ready=false`、`paper_data_ready=false`、`formal_sample_size_decision=BLOCKED_INDEPENDENT_TRAINING_SEED_VARIANCE_NOT_ESTIMATED`。

## Unreleased — 2026-09-08 (b)

- 對已合併的 exposure-censoring audit執行一次 adversarial multi-dimension review與 contract／replay differential sweep，共 59個 findings；修正一律為「命名更精確、增加檢查、或縮小主張」，未動任何 threshold、envelope、horizon或 bound formula，既有數值結果不變。
- 修正 cause mislabel：method-failure-only的 arm曾被標為 `EXPOSURE_CENSORED`。verdict與 blocked reason改為分別區分 exposure censoring、method failure與混合成因。
- 修正 `arms_without_any_comparable_episode`的多餘 `FULL_EXPOSURE == 0`條件，該條件會讓「有 full exposure但沒有任何 comparable episode」的 arm被漏列，使 summary可能讀成「所有 arm皆可比較」。
- 修正 shipped evidence中重複的 `PAIRED_CONTRAST_` 前綴；修正 descriptive sensitivity會把 retained method failure重新物化為 observed值；no-exposure episode不再允許保留 observed primary outcome；缺少 selection key不再被當成 null selection。
- `validate_v7_exposure_audit_bundle`原本只比對 hash與 receipt-versus-summary，因此一份一致地重新蓋章的 receipt可為被改寫的 summary背書。改為由 summary自身 retained comparability states重新導出 blocker list，並把 applicability flag綁定到 bundle class。
- Differential sweep發現兩個同名 `build_audit_summary`的 precondition不一致（contract驗證 raw、pilot summary與 bundle-class binding，replay不驗證），已改為完全一致；66個 case涵蓋所有 phase boundary、各臂 terminal failure、mixed comparability與 NONFINITE primary outcome，結果 `66/66`一致或同時拒絕。
- Integrity強化：replay的 check inventory凍結並要求完全相符（原本任何 all-true dict即可通過 AX-11）、replay把輸入檔綁定到 audited receipt inventory、replay receipt的 boolean改型別嚴格比較（`1 == True`）、`V7_PILOT_DEVELOPMENT_BUNDLE`必須保留 pinned audited protocol hash、audited bundle的 file set在前後比對、directory scan對不可讀子樹 fail closed、輸出寫入拒絕跟隨 link、output/source root另比對 filesystem identity。
- 縮小主張：receipt原本斷言 v7 pilot的 contrast不具內部可比性，但本次從未讀取該 frozen bundle、也未量測；已改為只陳述 software已驗證與 metric定義層面的性質，並明示 pilot實際 exposure與 bounds未量測。synthetic表格另加註為 synthetic，因其沿用 frozen `V7A`／`V7B`／`V7C` identifier。identification bounds的 estimand存在性約定改為明示；replay的 exact-identity改為說明它證明什麼（summary忠實於 retained rows）與不證明什麼（共用推導規則本身的正確性）。
- Tests由 38增至 72。新增的 fixture guard把 synthetic raw送進 pilot自身 validator，首次執行即發現 fixture編造了 frozen protocol未宣告的 per-arm identifier，意即先前 audit是對真實 pipeline不可能產生的輸入做測試。另補上先前無法到達的 zero-blocker clean status／observed aggregate／CLI exit 0路徑、partial-exposure method failure、duplicate／unexpected seed、arm-inventory mismatch、post-audit source drift與夾帶檔案、forged replay receipt，以及以重新索引 output receipt到達的 validator語意檢查。
- Clean source `4d0709327a03ba2773c8ad05f6051118dda6f54e`重新產生 evidence：27 artifacts / `118218688` bytes，package receipt `sha256:96782c7987af6630be543ee0d18820267e8149f36a21c483526400c86c6519ac`；三個 case皆 `AUDIT_BUNDLE_VALID`與 read-only verified，兩個保留 censoring blocker、一個 blocker為 0。
- 59個 findings中 25個完成 adversarial verification（15 confirmed、10 refuted）後主動停止該 workflow，因其 verifier與本地 validation競用 CPU；其餘由直接對照 source與 shipped evidence判定。`paper_data_ready=false`等 blocker全部保留。

## Unreleased — 2026-09-08

- 先以 Git `ee7321090089b186d847a958ae607478b6a12e6c`凍結 `AUDIT-V7-EXPOSURE-CENSORING-V1`：read-only contract、bundle class binding、由既有 task contract導出的 exposure horizon、censoring/method-failure vocabulary、assumption-free identification bounds、`AX-01..AX-12`與 `SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED / DEVELOPMENT_ONLY` boundary。
- 新增 stdlib-only audit contract、獨立 `python -I -S` replay、38個 synthetic fail-closed tests與 clean-source regression builder；刻意不從 `v7_pilot_contract` import任何東西，避免沿用被 audit pipeline自身的 validator與假設。
- Canonical episode row沒有 end-step、elapsed-time或 termination-reason欄位，因此 episode length只能由 retained `control_step_trace`取得；audit由 trace重建 termination control step／sim time／phase，再與 `trace_receipt` counts及 frozen `9.0 s / 450 steps / 4500 substeps` horizon交叉檢查。每個商與積必須是 exact integer。
- Execution前修正 `AX-04`：`backend/rl/humanoid_env.py:352-353`在 substep loop之後才推進 `task_elapsed_s`並重新取樣 phase，recorded label採 end-of-step accumulated-time convention（邊界 `0–48 / 49–123 / 124–324`而非 `0–49 / 50–124 / 125–324`）。沿用 freeze commit規則會因 recording convention差異把有效 bundle誤報為 structurally invalid。改為對照 reproduced recorder convention，並把 contract與 recorder的邊界差異輸出為 `phase_convention` validity finding；未依結果調整任何 threshold、envelope或 outcome。
- Method failure（`NULL`、`NONFINITE`、terminal failure、no exposure）保留為 method failure且明示不是 censoring；exposure-censored primary outcome改輸出 assumption-free worst-case full-horizon與 paired identification bounds，不輸出 censored point estimate。aggregate只在30個 pair全部 comparable時輸出，否則 null並記 `BLOCKED_EXPOSURE_CENSORED_PAIRS_RETAINED_NO_COMPLETE_CASE_DELETION`。
- Clean source `428ba214ec7d9e85c254b3b4f85d2c417094d202`的 synthetic package列入 18 artifacts / `68338712` bytes，receipt `sha256:15c2aef746edc2976a30f186180f32ba3c2c2ebcb6e30f1e08a5a2bf1a4b1415`；兩個 case皆 `AUDIT_COMPLETE_RETAINED_CENSORING_BLOCKER`、`source_bundle_read_only_verified=true`、`AUDIT_BUNDLE_VALID`，replay exact。
- Synthetic結果顯示 60/450 steps且零 saturated substeps的臂 full-horizon bound為 `[0.000000, 86.666667]%`，其 paired bound `[-34.974074, +51.692593]` percentage points包含 0，30個 pair全部 sign-unidentified；`valid_contrast=false`。另一臂29/30 pair sign-identified NEGATIVE，但因2個 pair被 censored，aggregate仍為 null。
- `DESCRIPTIVE_ONLY` exposure-matched sensitivity保留 `informative_censoring=SUSPECTED_DEPENDENT_ON_ARM_BEHAVIOUR`，不得用於 candidate selection、CI、p-value、hypothesis test、恢復 comparability或 sample-size決策。
- 2026-09-06 pilot bundle在 `.gitignore`的 local artifact root、不在 clean checkout內，因此本次無法對 `V7_PILOT_DEVELOPMENT_BUNDLE`執行 audit。Bundle class以 pilot receipt SHA-256雙向綁定，所有本次 bundle皆為 `SYNTHETIC_REGRESSION_BUNDLE`且 `audit_applies_to_frozen_v7_pilot=false`。
- 新增 audit suite為 `38 passed`，完整 backend為 `337 passed, 2 failed`。兩個 failure在 clean tree `ee7321090089b186d847a958ae607478b6a12e6c`（不含本次任何程式）同樣失敗，屬既有 environment lock缺口，原樣保留未繞過。
- 未重訓、未新增 seed、未調 alpha/envelope/threshold、未開啟 FORMAL/HOLDOUT、未選 candidate、未計 CI或 p-value；原 pilot receipt未回改。下一個唯一目標是在保有 2026-09-06 bundle的機器上對 `V7_PILOT_DEVELOPMENT_BUNDLE`執行一次 read-only audit run。

## Unreleased — 2026-09-06

- 先以 Git `e839aa263b391ade21bbfc61c50123a9ca384df4`凍結 `PILOT-V7-ACTION-INTERFACE-DEV-V1`：三臂 action math、common training seed 8700、DEV 18000–18029、retired/formal seed ranges、acceptance、failure semantics與 `SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED / DEVELOPMENT_ONLY` boundary。
- 新增 v7 action-interface runtime、`RL_TRAINING_PROFILES_V4`三個 profiles、strict training/evaluation CLI、requested/applied action與每個control step的500 Hz saturation aggregate counts、14-artifact bundle validator及 `python -I -S` stdlib-only raw-to-summary replay；未修改 policy registry、Live adapter或 frontend。
- Clean source `058657dd43d28a9175e54362cf4d0a0618507c38`完成三臂各122880 training steps及30個DEV episodes：V7A saturation `36.2185185 ± 1.0328300%`；V7B `23.3896264 ± 1.0044698%`，paired B−A `-12.8288921 ± 1.0720320` percentage points，但保留4個 negative episodes而不 eligible。
- V7C 30/30 early fall，required outcomes全數保留為 NULL；倒下前0% saturation與 paired arithmetic contrast不得解讀為改善。Selection為 `PILOT_RETAINED_SEMANTIC_BLOCKER`，candidate null、pilot planning/method-level power/paper data均 false。
- Bundle列入14 artifacts / `109520182` bytes，receipt `sha256:ed3e3eaa7c86f2b855d24aca68b09ce45bce61ac2fb6e573328b12157d758435`；path/bytes/SHA-256/source/policy identities與六項 independent replay checks通過。Frozen semantic blocker使builder/validator exit 1，並非 structural invalidity。
- Final targeted為 `54 passed, 1 warning`，quiescent完整 backend為 `301 passed, 5 warnings`。另保留一輪 concurrent source edit造成的 `274 passed / 20 failed`無效結果；frontend未受影響。
- 未開啟FORMAL/HOLDOUT、未放寬 threshold、未重標 failures。下一個唯一目標是只讀既有 bundle的 V7 early-termination / exposure-censoring validity audit V1；不重訓、不新增 seed、不調 alpha/envelope/threshold。

## Unreleased — 2026-09-05

- 新增 frozen `PAIRED_STATISTICS_SPEC_V1`、per-run metrics、paired raw table、statistics summary、paper table/figure inputs、aggregate receipt與 stdlib-only replay schemas。
- Continuous outcome輸出 candidate-minus-reference mean/median、Cohen dz與 deterministic paired percentile-bootstrap CI；binary outcome保留 2×2 counts、risk-difference point estimate與 marginal Wilson descriptions，paired CI明示 `PAIRED_BINARY_CI_NOT_IMPLEMENTED_V1`。
- `FAILED`、`CANCELLED`、negative、`NULL`、`NONFINITE`與 `CENSORED` 均保留；nonobserved outcome不做 silent complete-case/imputation，CANCELLED在 upstream fail closed。
- Aggregate對 spec/index/source/run/controller/scenario/seeds、manifest/metrics/raw trace identity、path/bytes/SHA-256、unindexed file、reparse point與 read-during-build drift重新驗證；`python -I -S`另一process對 raw-to-summary/table/figure exact replay。
- Clean source `a36b230de28c9f00f495027539c9266b22a9ec15` 的 synthetic package列入 191 artifacts / 297961 bytes，receipt `sha256:c3b860ce70690a1ed855e475f72cfc4da83d236a6e71dd3fdec93ec9a834ebf1`；contract valid，但 `statistics_ready=false`、`paper_data_ready=false`。
- Targeted statistics tests為 `27 passed`，expanded evidence tests為 `127 passed`，完整 backend為 `246 passed, 5 warnings`；frontend未受影響。
- 未執行 Study A、v7、FORMAL/HOLDOUT、HIL/bench/robot或 physical validation；下一個唯一目標是 v7 action-interface DEVELOPMENT PILOT。

## Unreleased — 2026-09-03

- 新增 frozen `EXPERIMENT_MATRIX_SPEC_V1`與 run-index contract，explicit 保存 controller、training/evaluation/environment/scenario seeds、scenario/replicate labels、resolved config及 common protocol/environment/model identities。
- 新增 fail-closed matrix validator：bounded strict JSON、spec hash、derived canonical seed-schedule hash、typed scenario equality、1,000-cell schema cap、dedicated-root no-follow scan、Windows case-variant manifest拒絕、per-run bundle path/bytes/SHA-256 readback，以及 missing/duplicate/unexpected/unindexed/tamper/identity drift檢查。
- `COMPLETED`、`FAILED`、`CANCELLED`逐 cell保留；CANCELLED可維持 inventory complete但阻擋 `statistics_input_ready`，matrix receipt固定 `paper_data_ready=false`。
- `COMPLETED`不得夾帶 failure record；claim boundary改為 exact frozen wording，避免以 contradictory suffix繞過 SIM-only boundary。
- 強化 `PAPER_RUN_MANIFEST_V1` readback：拒絕 duplicate JSON keys、NaN/Infinity及 requested controller label與 actual controller identity不一致。
- Matrix tests以 synthetic bundles覆蓋 exact、negative/null與 CLI failure semantics；未執行 actual Study A、statistics、v7 PILOT或 physical validation。
- Clean-source synthetic receipt綁定 Git `b8aea995eca0f3a3eff36ff04137ea3dd163f017`：3/3 identity-valid cells保留 `COMPLETED=1`、`FAILED=1`、`CANCELLED=1`，receipt SHA-256為 `8ebe7aa2509135143371774147dc85cc35fd5072c046522d1aabf90a74eb4691`；`statistics_input_ready=false`、`paper_data_ready=false`。
- Targeted matrix/paper-data為 `51 passed`，expanded V1 replay為 `101 passed`，完整 backend為 `220 passed, 5 warnings`；frontend未受影響。
- 下一個唯一 paper-data milestone為 paired statistics/CI與 paper table/figure input contract。

## Unreleased — 2026-09-02

- 新增 frozen V1 analytical fixture：passive exact single-support、centered 5 kg simulated payload與 4/2/1 ms grid-refinement共 4 cases。
- Primary保存 exact config/MJCF/model package、full raw state/applied force/solver/contact frame/6-D wrench/relative Jacobians；stdlib-only process不讀 primary PASS，從 raw與 model package完整重算。
- Frozen acceptance、failure/cancel/non-finite semantics與 `SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED` claim boundary在首次執行前寫入 versioned spec；threshold未因結果放寬。
- Clean-source bundle綁定 Git `b39a5ea2524a10189959d4968a9a7e15747fbf59`，primary/replay 4/4 PASS；payload mass error為 0、GRF increment relative error為 `1.303748139009358e-15`。
- 4/2/1 ms normalized-GRF QoI通過 grid-stability gate；successive differences進入 round-off區，因此 observed order保留為 `null / ROUND_OFF_LIMITED`。
- 10-role bundle的 path/bytes/SHA-256、exact model content與 pre/post source identity readback通過；狀態仍為 `REGRESSION_BUNDLE_VALID_ONLY / paper_data_ready=false`。
- 下一個 paper-data milestone凍結為 experiment matrix completeness validator；paired statistics/CI與 v7 PILOT不得提前取代它。

- V1 static contact oracle V4：1000-step/500 Hz raw evidence、16 項 frozen criteria，既有 thresholds未變。
- 依 compiled `PYRAMIDAL` cone 與 `condim=3` 重算 friction utilization。
- 由 aggregate foot wrench 在 foot-local sole plane 重算 CoP/support margin。
- 每個 contact新增 `body2 - body1` 的 `3 × nv` translational/rotational Jacobians與 frozen `adhesion_n == 0` precondition；移除 per-contact `generalized_force` raw receipt。
- stdlib-only replay完全不載入 MuJoCo/controller，改由 raw Jacobians、contact frame與6-D wrench重建 generalized force；14 項 replay criteria另涵蓋全 trace closure、absolute time grid與 evaluation count，primary metrics保持一致。
- 新增 paper-data-first architecture、`PAPER_RUN_MANIFEST_V1`、formal HOLDOUT/seed/clean-source gates與 path/size/SHA-256 artifact validator。
- V1 static oracle可產出10-role integrity-valid regression bundle；primary exception/non-finite result與 replay `FAIL`/process/schema error會保留為 failed bundle、diagnostic artifact與 failure record；validator明確回報 `REGRESSION_BUNDLE_VALID_ONLY`，不偽裝成 formal paper result。
- Bundle builder不信任 primary/replay自報 PASS；exact 16/14 criterion mapping、frozen raw/model fields、model.xml SHA-256與 pre/post Git identity皆 fail closed。
- 保留證據邊界：Jacobian與wrench仍是 same-engine MuJoCo receipts；single-support、known-payload、dynamic contact、independent contact model、convergence、energy與 physical validation仍未完成。

## 0.1.0 — 2026-08-29

第一個公開版本：

- 分析模式：prescribed kinematics、analytical GRF/contact schedule、inverse dynamics 與 design-screening outputs。
- 即時互動：MuJoCo forward dynamics、simulated contact、Track／Raibert／RL controllers。
- 三機同步比較：三個獨立 plants、相同命令、同步 simulation time、assist 預設 OFF。
- Dynamic Run Trace V1：500 Hz bounded NPZ/manifest、SHA-256 validation 與 Analysis readback。
- Motion Task V1：`stand → start → steady walk → stop`、固定 gait/phase 與 11 項可量測 criteria。
- Versioned RL policy registry 與固定速度 training profiles；歷史 training outputs 不納入 repository。
- 101 個 backend tests 與 frontend TypeScript/production build verification。

已知限制：

- V0 尚未 PASS；缺 immutable evidence bundle、environment lock 與獨立 validator。
- 第一組三 controller Motion Task development baseline 均為 FAIL。
- 模型未經實體校準，內建 hardware catalog 為 representative demo data。
