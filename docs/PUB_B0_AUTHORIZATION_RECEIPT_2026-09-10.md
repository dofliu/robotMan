# `PUB-B0` 授權紀錄與 v7 線的 selection 可行性量測

日期：2026-09-10 ｜ Gate：`PUB-B0` ｜ 對應 protocol：[V7_CANDIDATE_SELECTION_SPEC](V7_CANDIDATE_SELECTION_SPEC.md)（`SELECT-V7-CANDIDATE-FORMAL-V1`）

狀態：`AUTHORIZATION_GRANTED / PROTOCOL_STILL_NOT_EXECUTABLE / FORMAL_SEEDS_NOT_ACCESSED`

證據等級：本文件是**決策紀錄 + 可行性量測**，不是 evaluation evidence。沒有存取 `20000–20029`，沒有產生任何 FORMAL 資料，沒有選出任何 candidate。

## 1. 授權

[SOURCE] 專案負責人於 2026-09-10 的工作 session 中指示「授權 formal evaluation」。這解除 [V7_CANDIDATE_SELECTION_SPEC §7](V7_CANDIDATE_SELECTION_SPEC.md) 的 `EP-03`（`formal authorization has not been obtained`）作為一項**決定**。

[BLOCKER] 但**授權本身不使 protocol 可執行**，原因有三，全部在授權之前就已記錄，不是事後新增的門檻：

| 項目 | 狀態 | 誰能解除 |
|---|---|---|
| `EP-03` formal authorization | **決定已取得**（本文件）；但 frozen protocol JSON 內 `execution_preconditions` 仍硬寫 `"state": "BLOCKING"`，而 `assert_executable()` 讀的是該 JSON | 需要一次 **narrowing-only、execution-before 的 amendment** 把 `EP-03` 改為 `RESOLVED` 並附授權證據，同時在 contract 內重新 pin `PROTOCOL_SHA256`（與 `SEEDVAR-AMENDMENT-01` 同一機制） |
| `EP-01` audit contract 拒絕 FORMAL seeds | `BLOCKING`：`v7_exposure_audit_contract._episode_exposure` 對 `range(20000, 20030)` 內任何 seed 直接 raise，而 exposure 分類正是 `SEL-C2` 的輸入 | 需要對已 merge 的 audit contract 做 amendment，允許在授權證據存在時分類 FORMAL seeds。該 contract 有下游 pins |
| `EP-02` evaluation seed schedule 釘死 | `BLOCKING`：`rl/eval_policy.py` 兩個 branch 都禁止覆寫 seed schedule，沒有路徑接受 `20000–20029` | 需要第三個互斥的 evaluation identity（FORMAL selection 專用） |
| `PUB-B4` external preregistration | **未完成**。[PUBLICATION_PLAN §4](PUBLICATION_PLAN.md) 的凍結順序寫明：「`PUB-B4` 必須在解封 sealed seeds `20000–20029` 之前。授權在前、預註冊在中、解封在後。」 | **只有專案負責人**（需要 OSF 或同級 registry 帳號）。本執行環境無法代為登錄 |

[RESULT] 因此 2026-09-10 當日**沒有**、也**不應該**進行解封。依專案自訂的凍結順序，授權解除的是順序中的第一格，不是最後一格。

[BLOCKER] **機器可讀的 authorization evidence 刻意尚未鑄造。** `v7_candidate_selection_contract._require_authorization` 要求 `authority`／`reference`／`granted_at_utc`／`scope_git_sha` 四個字串，並要求 `protocol_sha256` 等於 `sha256:b4e16370b5744c510fa11b06343dafb3c1893711639721a406504720bbe99b58`——也就是說，鑄造該證據**等於選定「用現行的 post-hoc 規則」這個子選項**。該子選項尚未決定（§4），且 `PUB-B4` 在解封之前，故本次只記錄決定，不產生證據檔。

## 2. 授權當下的 protocol 身分（供日後 amendment 對照）

| 項目 | 值 |
|---|---|
| Protocol | `SELECT-V7-CANDIDATE-FORMAL-V1` |
| Protocol JSON | `backend/rl/v7_candidate_selection_protocol.json`，`sha256:b4e16370b5744c510fa11b06343dafb3c1893711639721a406504720bbe99b58` |
| Spec digest | `sha256:bab998579bdb4f260…`（protocol 內 `specification_sha256`） |
| Freeze parent | `f72814765a49e4f7141cf5482c8d029e3488f27d` |
| 授權時的 repository state | `496cccacbb8a9e5ec1ef941ef3e2f5df0918c3a4`（`main`） |
| `preregistered` | `false`（由 contract 強制；規則在看過 DEV 結果後寫成） |

## 3. 量測：在 v7 線上 `SEL-C2` 幾乎確定不成立

這是本文件的實質內容。授權之後的下一個問題不是「能不能跑」，而是「跑了會得到什麼」。

`SEL-C2` 要求 candidate 與 reference 的**每一個** episode 都 `COMPARABLE`。`replicate_count = 5`、每 replicate 30 個 evaluation seeds，故每臂 150 個 episode。FORMAL 評估用的是**同一批已訓練好的 15 個 policy**（`backend/rl/artifacts/…_seedvar-r{0..4}/policy.zip`），只是把 evaluation seeds 從 `18000–18029` 換成 `20000–20029`。

[RESULT] 由 retained seed-variance evidence（`seed_variance_summary.json`，`sha256:42b4cfac…`）重算的實測 comparability：

| Arm | `COMPARABLE` / 150 | 每 episode 比率 | `P(150 個全部 COMPARABLE)`（iid 外推） |
|---|---:|---:|---:|
| `V7A_REWARD_ONLY`（reference） | 143 / 150 | 0.953333 | `7.7 × 10⁻⁴` |
| `V7B_REDUCED_JOINT_ENVELOPE` | 120 / 150 | 0.800000 | `2.9 × 10⁻¹⁵` |
| `V7C_FILTERED_ACTION` | 0 / 150 | 0.000000 | `0` |

[RESULT] `SEL-C2` 需要 reference **與** candidate 同時全數 comparable：

- reference + `V7B`：`2.2 × 10⁻¹⁸`
- reference + `V7C`：`0`

[INFERENCE] iid 外推是粗略的（同一 replicate 內的 episode 不獨立），但結論不依賴精確機率，而依賴一個結構事實：**reference arm 自己就在 3 個 replicate 上早期終止**。要在 FORMAL seeds 上通過 `SEL-C2`，`V7A` 必須在 `20000–20029` 上表現得與 `18000–18029` 上**質性不同**，而 policy 完全相同、只有 evaluation seed 不同，沒有任何機制支持這種差異。

[RESULT] `SEL-C4` 與 `SEL-C2` 耦合：`between_replicate_sd` 為 `null` 的原因**正是** exposure censoring 讓每個 replicate 的 paired difference 成為 interval。`SEL-C2` 不成立時 `SEL-C4` 必然也不成立。

[INFERENCE] 因此執行本 protocol 的預期輸出是 `SELECTION_COMPLETE_NO_CANDIDATE`，機率接近 1。

## 4. 一次性的代價，與待負責人決定的兩件事

[BLOCKER] [V7_CANDIDATE_SELECTION_SPEC §5](V7_CANDIDATE_SELECTION_SPEC.md) 明文：FORMAL 資料**只套用一次**；看過結果後不得重跑、不得調門檻、不得改 `replicate_count`、不得改 arm 定義、不得改 primary outcome；任何改動都需要新的 protocol version，且新版本必須揭露它是在已知 FORMAL 結果的情況下設計的。`20000–20029` 是[§3](V7_CANDIDATE_SELECTION_SPEC.md) 記載的**唯一未被檢視的範圍**（`18000–18029` 已 `DEVELOPMENT_EXHAUSTED`，`19000–19029` 已 `RETIRED`）。

[INFERENCE] 合起來：把唯一剩下的未檢視 seed 範圍花在一條預期回傳 `NO_CANDIDATE` 的規則上，會**永久失去**日後在 v7 線上做出可信 selection 的可能性。這不是規則設計失誤——規則之所以嚴格，正是因為 audit 量測到 `outcome_state == OBSERVED` 不蘊含 full exposure；失敗的原因是**這條 policy 線本身跑不完任務**，而它的 warm start 不可重建（`CONDITIONAL_ON_FIXED_WARM_START` 對 v7 線永久成立）。

因此有兩件事需要負責人決定，本文件不代決：

1. **`PUB-B0` 的子選項**：用現行公開宣告非預註冊的 `SELECT-V7-CANDIDATE-FORMAL-V1`，還是先在 OSF 預註冊一條替代規則？（[PUBLICATION_PLAN §5](PUBLICATION_PLAN.md) 的建議是後者。）
2. **FORMAL seeds 要花在哪條線**：v7 線（預期 `NO_CANDIDATE`，且用掉唯一範圍），或保留給一條 reference policy 能穩定跑完任務的新訓練線（`PUB-B1` + `PUB-B2`，即 [ROADMAP §9](ROADMAP.md) 第 2 項）。

[INFERENCE] 本文件的建議是第 2 項選後者：先建有版控 lineage 的新訓練線並讓 reference 達到事先凍結的 full-exposure 比例，再把 FORMAL 範圍花在那條線上。理由是上述量測，不是偏好。

## 5. 若決定仍在 v7 線上執行，工作順序

紀錄於此，使決定不必重新推導。全部四步都必須在解封之前完成，且**順序不可反**：

1. `PUB-B4`：外部預註冊（負責人，需 registry 帳號）。
2. `SELECT-AMENDMENT-01`：narrowing-only、execution-before amendment，把 `EP-03` 改為 `RESOLVED` 並附授權證據；重新 pin contract 內的 `PROTOCOL_SHA256`；不得同時變更任何門檻或 arm 定義。
3. `EP-01`：對 audit contract 做 amendment，僅在授權證據存在時允許 FORMAL seeds 被分類。該 contract 有下游 pins，須確認既有 retained evidence 仍 bit-exact replay。
4. `EP-02`：在 `rl/eval_policy.py` 加入第三個互斥的 evaluation identity（FORMAL selection 專用），與既有兩條路徑互斥。
5. 執行 15 次評估於 `20000–20029` → 組 bundle → 對 selection contract **只套用一次** → receipt。

## 6. 沒有改變的事

`paper_data_ready`、`statistics_ready`、`method_level_power_ready`、`sample_size_decision_input_ready` 皆為 false 不變。`selected_candidate_arm_id` 仍為 `null`。沒有存取 `20000–20029`。沒有任何 protocol、contract、門檻、seed 或 arm 定義被更動。frozen protocol JSON 逐位元不變。
