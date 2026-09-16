# Changelog

本專案採語意化版本概念記錄可公開的 development releases。所有版本目前仍屬 SIM-only prototype，不表示 physical validation maturity。

## Unreleased — 2026-09-16 (y)

### 專案評估：現況、價值與去向（決策文件，負責人尚未決定）

- [RESULT] 新增 [PROJECT_ASSESSMENT_2026-09-16](docs/PROJECT_ASSESSMENT_2026-09-16.md)，回答三個問題：專案現在是什麼、值不值得推廣、下一步。**每個數字從 repo 量出**，每個判斷標明量測／推論／建議。它不替負責人做決定。
- [RESULT] **比例**：核心 robotics + 應用 `6,871` 行、前端 `3,561` 行；證據契約／replay／bundle `29,294` 行；測試 `14,768` 行（692 函式 → 942 case）。核心：外衣 = **1 : 4.3**。已結案研究線（v7、second case、seed variance、tracked lineage、R0）合計約 `15,800` 行契約碼、420 個測試函式，佔契約碼 54%、測試 61%。**692 個測試函式只有 76 個測教學應用。**
- [RESULT] **盤點初始假設被推翻並照實記錄**：(1) 「有死碼」——21 個零 importer 模組全部帶 `__main__`，都是合法 CLI 入口，後端**沒有任何不可達程式**；問題是活著但任務已結束的工具碼。(2) 「跌倒懲罰只有 −5」——tracked-lineage 用的 `phase_observable_v5` 繼承 v4 `PathStopEnv`，終止另加 −45，實為 **−50**。
- [RESULT] **機器人為什麼加預算沒用——量化診斷**：控制步 0.02 s；站好時每步 ≈ 2.5；站滿 2.5 s ≈ 125 步 ≈ 310，跌倒 −50 ≈ 260，**正對上 V1 的 227–232 與 V2 的 283–295**。十個 replicate 寧吃 −50 也不起步 ⇒ 嘗試起步的期望代價 > 50；v4 加重懲罰後仍失敗 ⇒ 懲罰不是綁住結果的項。槓桿在 curriculum／分階段形塑／參考軌跡，**不在預算**——這給了 V2 receipt「要改的不是預算」一個機制解釋。
- [RESULT] **證據版控範圍**：seedvar `raw_replicates.json`（276 KB）進版控，`[-13.5, -12.4]` pp 可重導；但 **v7 pilot 原始 bundle（109.5 MB）與 audit 凍結 bundle（113 MB）在 gitignored `run_traces/`，不在版控**——依 REPOSITORY_GUIDE §3 明文政策，非疏忽，但專案自稱「最強結果」的 v7 線是所有線裡從 repo 最不可重導的一條。已在 PROJECT_STATUS §4 加註。
- [INFERENCE] **價值判斷**：作為 robotics 研究弱（無新方法、無實體驗證、可重建的線全不會走）；作為評估效度研究**真的有一篇**（V7C 假改善、`OBSERVED ⇏ full exposure`、Walker2d 重現、regime 分類——Track A 證據已齊）；作為教學工具有實質價值且**與研究契約完全解耦**（`main.py` 零 import、前端 `tsc`/`vite build` 乾淨、v5 policy 可示範行走）；作為可重現實驗工程範例比多數已發表 RL 工作嚴謹——但它在驗證一個不會走的機器人。
- [INFERENCE] **關鍵觀察：`PUB-B2` 的理由消失了。** 它是為 `PUB-B3` 的 reference 而設；2026-09-09 Track A 重構為 censoring regime 研究後，論文不再需要會走的 reference，需要的是被截斷的例子——那正是各線已提供的。gate 留下來後又花了兩條線追它。
- [RESULT] **架構建議**（未執行，待決定）：教學應用與研究基礎設施今天就可拆成兩個產品（A 教學模擬器 ~10.4k 行；B 可重用實驗工具組 ~6.4k 行）；已結案線的程式與文件建議**封存**至 `archive/`（證據原地不動、digest 不變），全套測試會由 942 降至約 520；`STATUS.yaml` 拆結構化、文件 63 → 活的約 12 份。**不動**：任何凍結 protocol／spec、已保留證據、`environment_lock`+`run_manifest_lock`、v5 artifact、30/30 門檻與 2M 上限。
- [RESULT] 三個去向選項寫在 §5：一、收斂（拆教具、拆工具組、寫 Track A、封存其餘——**不需 PUB-B2**）；二、修機器人但換槓桿不加預算（V3 以 v5 行走 checkpoint 為 curriculum 起點，據實揭露）；三、維持現狀（**唯一不建議**）。
- 順手修正：REPOSITORY_GUIDE `tracked_lineage_evidence` 「尚未建立」→ 實測 40 個 checkpoint、77 MB；測試數 923 → 941。

## Unreleased — 2026-09-14 (x)

### `TRACKED-LINEAGE-TRAINING-V2` 執行完成：加倍預算，曝露仍是 `0/30`

- [RESULT] **標籤 `TL2_BUDGET_EXHAUSTED`，與 V1 相同。** 由每個 V1 replicate 保留的 `1,999,968` 步 checkpoint 續訓，各再加 `2,000,000` 步（realized `4,015,200`）。獎勵由 `226.9`–`231.6` 升到 `283.1`–`295.3`，平均存活由 `2.440`–`2.811` s 升到 `2.725`–`3.458` s，而**完整曝露仍是 `0/30`，五個 replicate 全部、`150` 個 episode 全部**。最長的單一 episode `4.0` s，門檻 `9.0` s。**多花的 `2,000,000` 步買到 `+51.5`–`+66.5` 獎勵與 `+0.145`–`+0.778` 秒存活。**
- [RESULT] **標籤是算出來的不是宣告的。** `backend/rl/run_tracked_lineage_v2_contract.py` **只讀版控內的保留證據**，跑完 `TL2-01`..`TL2-09` 後輸出 `tl2_contract_receipt.json`；V1 的驗收由人逐條核對後寫進 receipt，讀者只能選擇相信作者。它刻意不讀 gitignored 的 `backend/rl/artifacts/`——靜悄悄依賴未保留檔案的檢查，會在最需要它的時候剛好失效。
- [RESULT] **曲線在上限處更陡，不是更平。** 五個全部未收斂，且**五個裡有四個的末四分位斜率比首四分位還大**（比值 `1.119`／`0.636`／`1.143`／`1.039`／`1.091`；末四分位斜率 `+11.8`–`+22.2`／500k，V1 是 `+7.3`–`+11.9`）。跑到 `4,015,200` 步，不是逼近天花板，是找到更多可爬的空間——同時曝露完全沒動。
- [RESULT] **兩個事先宣告的量測選擇都沒有改變結論。** 在任何 V2 曲線存在之前，程式碼就宣告以 lineage 曲線（V1 曲線截到 resume 點再接 V2）而非只看增量、聚合取 `any` 而非 `all`，兩者都是對「再加預算」更不利的方向。結果兩種讀法在五個 replicate 上結論一致，五個聚合值皆 `False`。**事先宣告仍然是對的，而它這次剛好不用付代價**——把它講得比實際更關鍵會是另一種誇大。
- [RESULT] **凍結前的算術五個全中**：realized `4,015,200`、checkpoint 落在 `2499960/2999952/3499944/3999936`、10 次執行 gate 皆 `RUN_LOCK_BOUND`（環境鎖 `sha256:93d23a27…`，與 2026-09-08 執行逐位元相同）、`source_git_pre == source_git_post`、`TL2-08` 五個精確成立（被評估的 digest **就是**保留的 reference checkpoint）。
- [BLOCKER] **七個缺陷，兩種形狀。** 主張為真但證據活不過容器；或程式跑過 fixture、沒跑過真正凍結的東西。(1) V1／V2 guard dispatch 讓 V2 profile 掉進 V1 分支——兩個 guard 各自測過，沒測 `main()` 實際會走的路徑。(2) manifest 用 `relative_to(RL_DIR)` 記錄 resume 路徑——放寬了 guard **接受**什麼，沒動 manifest **記錄**什麼。(3) 保留腳本只支援 V1。(4) **訓練 run manifest 從未被保留**，只保留了評估的——索引裡有 digest 看似完整，但**沒人拿得到的檔案的 digest 不是證據**。(5) **`RUN_LOCK_BOUND` 無法離線重導**：gate 只印到 console，sidecar 沒有 label 欄位，索引寫的是佔位字串——**V1 五筆至今仍是如此**。(6) `verify_checkpoint_lineage` 委派給 V1，而 V1 讀 V2 凍結 protocol 沒有的 `replicate_count`；protocol 不得改，故改由三個凍結事實推導，**三者不一致即 method failure**，且傳給 V1 的是複本——會修改被驗證對象的 verifier 已經不是 verifier。(7) runner 仍讀那個不存在的 label 欄位，**在 10 次執行上全部 fail closed，完全正確**；推導現在只有一份，放在 `run_manifest_lock.evaluate_relocated_run`。
- [RESULT] **一個先立後撤的觀察，保留在記錄裡。** r2 跑完時三個 replicate 呈現乾淨的反向關係（獎勵漲最多的存活漲最少），我在 r3／r4 之前就記進 commit 並註明可能被抹掉；r3 抹掉了。不刪除——**先立後撤比悄悄丟掉誠實**。站得住的是更弱也更硬的敘述：獎勵增益對存活增益不帶任何方向上可用的資訊。
- [BLOCKER] **不授權 V3。** 規格 `escalation_rule` 事先寫定：再次得到 `TL2_BUDGET_EXHAUSTED` 是**結果**，不授權單純再加預算。V3 需要自己的 protocol 版本並揭露它是在已知 V1 **和** V2 結果之後設計的。**要改的不是預算**——`2,000,000` 步買到不到 `0.8` s，而門檻還差 `5` s 以上。
- [RESULT] 儲存實測：`backend/tracked_lineage_evidence/` `77 MB`、`.git` `83 MB`，落在規格 §5.3 事先預估的約 `85 MB` **之內**。V1 §4.1「第三條線之前重新評估外部不可變儲存」的要求依然有效，只是尚未到期。
- [RESULT] 全套 **1 failed / 941 passed**（`507.79` s），失敗項仍是同一個 `PRIMARY_CASE_RECEIPT_IDENTITY`，未新增失敗。數字這次**逐 commit 實測**：`892`（`5b707cb`）→ `924`（＋32 V2 contract，即先前的 923 passed）→ `936`（＋2＋2＋8，PR #20 後的 main）→ **`942`**（＋6）。

## Unreleased — 2026-09-14 (w)

### `TRACKED-LINEAGE-AMENDMENT-03`：更正我自己給錯的結果標籤

- [BLOCKER] **`TL_REFERENCE_NOT_ATTAINED` 是錯的，正確標籤為 `TL_BUDGET_EXHAUSTED`。** 這是在結果已發布並隨 PR #17 合併**之後**才發現並更正的，與 §15／§16 那兩份「執行前收窄」性質不同，必須說清楚。
- [BLOCKER] **錯因是我根本沒量。** §9 定義 `TL_BUDGET_EXHAUSTED` 為「未達門檻**且曲線未收斂**」——條件是 `TL_REFERENCE_NOT_ATTAINED` 再加一項。而 `classify()` 第一版簽章是 `budget_exhausted: bool = False`，我直接採用預設值，**從未量測曲線是否收斂**。一個可以被靜默跳過的判定，就會被跳過。
- [RESULT] 事後量測（規則在套用前先宣告於 `backend/rl/retain_tracked_lineage_curves.py`：末四分位斜率 ≤ 首四分位的 `10%` **且**絕對值 ≤ `1.0`，單位為每 `500,000` 步的 reward 增幅）：比值 `0.377`／`0.403`／`0.536`／`0.475`／`0.341`，末四分位斜率 `+7.309`–`+11.888`——**五個 replicate 全部未收斂**。訓練在被上限截斷時仍在進步。可於 `python -I -S` 下離線重算。
- [RESULT] **沒有任何量測數值改變**：`0/30` × 5、`fall_rate 1.0`、`2,015,232` 步、20 個 checkpoint 全部照舊。`PUB-B1` 仍達成，`PUB-B2` 在兩種標籤下**都是** `NOT_ATTAINED`（只有 `TL_REFERENCE_ATTAINED` 能讓它過）。四個 flag 不變。改變的只有描述結果的名字。
- [BLOCKER] **這個更正讓後續變難不是變易**，這點必須強調否則會被誤讀成替自己找台階：`TL_BUDGET_EXHAUSTED` 隨附一條 `TL_REFERENCE_NOT_ATTAINED` 沒有的規則——§9 明文禁止以「再多跑一點就到了」為由上調上限。曲線未收斂正是最會誘發該念頭的情形，而 §9 在看到任何曲線之前就封住了它。
- [RESULT] **§9 的兩個標籤並非互斥**（我的缺陷）：amendment 03 規定兩者同時成立時報較具體的 `TL_BUDGET_EXHAUSTED`，因為它說明了原因並帶著上述限制；降級成較泛的標籤等於丟掉那條限制。
- [RESULT] **加嚴**：`classify()` 的 `curve_converged` 改為必填具名參數、**無預設值**，`budget_exhausted` 參數移除。新增測試直接斷言該參數沒有預設值，並斷言少傳會 `TypeError`。
- [BLOCKER] **證據搶救**：訓練曲線原本只存在於 gitignored 的 `backend/rl/artifacts/` 下，會隨容器消失——與 v7 pilot 的 `control_step_trace` 同一個坑，而那個坑正是本線存在的理由之一。五份 `progress.csv` 已連同 digest 保留至 `backend/tracked_lineage_evidence/2026-09-14/training_curves/`，判定因此可重驗。
- [BLOCKER] **仍不得宣稱「再多跑就會達標」。** 曲線未收斂只說明訓練尚未停止進步，**不**說明它會收斂到哪裡，也**不**說明它會跨過 `30/30`。
- Digest 連鎖重釘：規格 `96bbae55…` → `1919bf8a…`；protocol `9963a2b2…` → `0b29672e…`；`tracked_lineage_contract.PROTOCOL_SHA256` 同步。receipt 於頂端加上顯著更正聲明並新增 §12，**§0–§11 初版原文刻意不改寫**，保留當時的判斷與依據。

## Unreleased — 2026-09-14 (v)

### `TRACKED-LINEAGE-TRAINING-V1` 執行完成：`PUB-B1` 達成、`PUB-B2` `NOT_ATTAINED`

- [RESULT] **標籤 `TL_REFERENCE_NOT_ATTAINED`**（[receipt](docs/TRACKED_LINEAGE_TRAINING_RECEIPT_2026-09-14.md)）。五個 scratch replicate 全部訓練完成、全部產出版控 checkpoint lineage，但**沒有任何一個** reference policy 達到事先凍結的 `30/30`：五個皆 `0/30`。
- [BLOCKER] **這是事先宣告的結果，不是失敗。** 規格 §3、§4.2 與 §9 在看到任何訓練曲線之前就寫明 v5 是經 v1→v5 多輪 curriculum 才到 Live 10/11、單發 scratch 未必能到、`30/30` 很可能得到 `TL_REFERENCE_NOT_ATTAINED`。門檻**不得因此下調**；未達即 `PUB-B2` `NOT_ATTAINED`，那是一項結果。
- [RESULT] **不對稱的結論，也是本次最重要的一點**：本線**達成了它存在的主要目的**——一條 pretraining provenance 可重建的訓練線現在存在（`PUB-B1`）——但**沒有**產出一個能可靠完成任務的 reference policy（`PUB-B2`）。兩者是不同的事，不可互相代替。
- [RESULT] 量測：5 replicates、seeds `9100/9112/9124/9136/9148`、每個 realized **恰為 `2,015,232`** 步（五次皆與 amendment 01 的預測相同）、`warm_start` 與 `resume` 全為 null、20 個 checkpoint 共 `39,899,261` bytes（`38.0 MiB`）落在 `499,992`／`999,984`／`1,499,976`／`1,999,968`、無一被 gitignore、digest 與大小皆與磁碟位元組相符。
- [RESULT] **10 次執行（5 訓練 + 5 評估）gate 全部回 `RUN_LOCK_BOUND`**，環境為 `MEASURED_ENVIRONMENT_LOCK` + `FULL_LOCK` + `AMBIENT_THREADING_PINNED`，其 `locked_sha256 = sha256:93d23a27` 與 2026-09-08 seedvar 執行**逐位元相同**——本線與其前身跑在同一個可量測環境上。
- [RESULT] 評估對象是 `TL-CK-04` 指定的 reference policy（最後一個保留 checkpoint，`1,999,968` 步），seeds `22000–22029`、每 replicate 30 episodes。五個 replicate 的 `fall_rate` 皆 `1.0`，`150` 個 episode 的 `outcome_state` 全為 `NULL`，平均 `duration_s` 為 `2.477333`／`2.680000`／`2.520000`／`2.811333`／`2.440000`（任務長 `9.0` s），五者平均 `2.585733`。
- [RESULT] 失敗型態是量到的：跌倒集中在 `2.44`–`2.81` s，而 `STEADY_WALK` 起於 `2.5` s；`mean_saturation_duty_pct = 0.0`、側向 drift `0.219598` m。scratch policy 學到了站立，沒學到起步行走。**但本 receipt 不宣稱「curriculum 是必要的」**——只跑了一個 recipe、一個 budget，沒有對照。
- [BLOCKER] **`150` 是 forbidden denominator**，不得把結果寫成 `0/150`。判定逐 replicate，method-level 分母恆為 `5`；本線的 method-level 結果是 **`0/5` 個 replicate 達標**。
- [RESULT] **`TL-01`、`TL-01b`、`TL-02`..`TL-08`、`TL-CK-01`..`TL-CK-06` 全數通過**，因此這是一次乾淨量測的否定結果，**不是** `TL_METHOD_FAILURE`。特別是 `TL_EXPOSURE_SIGNALS_DISAGREE` 在 150 個 episode 上都沒觸發：短 `duration_s` 與非 `OBSERVED` 的 `outcome_state` 每次同時成立。
- [RESULT] **`TRACKED-LINEAGE-AMENDMENT-02-FINAL-ARTIFACT`**（第三份、也是最後一份）：`TL-CK-03` 要求最終 artifact 是保留 checkpoint 的副本或最後一個，實測**兩者皆不可能**——`policy.zip` 寫於 `learn()` 返回後的 rollout 邊界 `2,015,232`，比最後一個 checkpoint 多 `15,264` 步。更正為「最終 policy artifact 指 `TL-CK-04` 已指定的 reference policy」，並**加嚴**新增 `TL-CK-06`（被評估 policy 的 digest 必須等於某個保留 checkpoint），把原本只是文字的主張變成每次分析都重算的檢查。`policy.zip` 定性為 unretained byproduct，digest 仍記入索引以便日後偵測抽換。
- [BLOCKER] 否決並記錄的替代方案：把 `policy.zip` 也保留為每 replicate 第 5 個檔案。理由是 repo 成本由負責人接受的 `38 MB` 升為約 `47 MB`，且會留下兩個都像「最終 policy」的檔案——正是 v5 provenance 說不清楚的病灶。若負責人偏好保留，那是 §4.1 成本決定的修改，需要新的 protocol 版本而非 amendment。
- [BLOCKER] **更正規格 §5 的一個估計**：§5 依 seedvar 實測寫「約 `1,683` steps/s、5 個 replicate ≈ `1.7` 小時」，實測為 `1,133.5` steps/s、`2.469` 小時。估計值不是凍結參數，沒有任何門檻或設計因此改變；記下以免下一個人沿用那個偏樂觀的數字排程。
- [RESULT] repo `.git` 由 `11 MB` 增為 `47 MB`，落在 §4.1 具名接受的「約 `49 MB`」之內。**20 個已保留 checkpoint 不得刪除**——它們是 `PUB-B1` 的唯一產出，也是任何後續線的可重建起點。
- [BLOCKER] 後續四條路線（提高 budget／引入 curriculum／改 reward 或環境／改以其他方式解 `PUB-B3`）全部需要**新的 protocol 版本**，並須揭露它是在已知本結果的情況下設計的；`2,000,000` 步上限**不得**事後上調。見 receipt §10。
- `paper_data_ready` 等四個 flag 全部不變，仍為 `false`。本線是 `DEVELOPMENT`：不解封 `20000–20029`、不觸及 `SELECT-V7-CANDIDATE-FORMAL-V1`、不支持與 v7 線的任何直接數值比較。

## Unreleased — 2026-09-14 (u)

### `TRACKED-LINEAGE-AMENDMENT-01` 與 driver／contract 實作：我在當天凍結裡留下的兩個缺陷

- [BLOCKER] **兩個缺陷都是我自己的，都在任何訓練之前發現並更正，且都不是門檻放寬。**性質先說清楚，否則會被正確地質疑：第一項把初凍結**未指定**的欄位縮到唯一值（收窄），第二項把一個**機制產生不出來的數字**換成實際會產生的數字（更正）。門檻、seed、replicate 數、`checkpoint_interval`、`planned_timesteps` 上限、arm 定義與 `TL-CK-04` 選擇規則**一字未改**。規格 §14 要求變更那五類才需新 protocol 版本，兩項皆不屬於，故以 amendment 處理（作法沿用 `SEEDVAR-AMENDMENT-01` 與 `LOCKBIND-AMENDMENT-01`）。
- [BLOCKER] **缺陷一：§5 自稱「凍結的訓練設計」，卻沒指定 `environment_id`。** 同樣漏掉 `step_length_m`／`duty`／`clearance_m`（profile id 裡的 `0p7` 只釘住速度），而 `TrainingProfile.environment_id` 是必填 `Literal`——換言之**照初凍結的文字根本寫不出一個合法 profile**，缺的欄位得由實作者當場選，正是本專案的紀律要避免的事。補定為 `motion_task_phase_observable_v5` 與 v5 的 `0.7`／`0.35`／`0.62`／`0.07`。理由不是隨便挑：本線要造 v5 那個不可重建 warm start 的 provenance 可重建替身，而 v5 環境正是這個任務**實際達成過** Live 10/11 的那一個；改用任何 `motion_task_v7_*` 會把本線綁進它明示不觸及的 arm 比較，改用 v6 則引入已被證明不足的 saturation reward。
- [BLOCKER] **缺陷二：§7.1 的 `500_000` 整數倍 checkpoint 不可達**，與 §4.2 的 `0.98` 完全同類——我寫下了一個機制產生不出來的數字。量測：`save_freq = max(checkpoint_interval // n_envs, 1)` = `500_000 // 12` = `41_666`（整數除法丟掉 `0.67`），SB3 2.9.0 判斷 `n_calls % save_freq == 0` 而 `num_timesteps = n_calls × n_envs`，故實際落點是 `499_992`／`999_984`／`1_499_976`／`1_999_968`。`n_envs = 12` 之下 `500_000` 的整數倍**永遠不可達**（`500000/12` 不是整數），而 `n_envs` 與 `checkpoint_interval` 都已凍結，故正解是更正文件不是改設計。個數 `4`／replicate、合計 `20` **不變**。
- [RESULT] 連帶更正 realized timesteps 為 `2_015_232`（`⌈2_000_000 / 24_576⌉ × 24_576`，rollout = `n_steps × n_envs` = `2048 × 12`）。**交叉驗證**：同一算式對 seedvar 線的 planned `100_000` 給出 `122_880`，與該線實際記錄的 realized 值完全相同，故這是量到的 driver 行為而非推測。
- [BLOCKER] `2_015_232 > 2_000_000` **不是上調上限**。上限訂在 `planned_timesteps`，超出的 `15_232` 是 rollout 粒度的既有行為（seedvar 線在同一 driver 上已超出 `22_880` 並記錄接受）。`TL_BUDGET_EXHAUSTED` 仍以凍結的 `2_000_000` 判定，且不得因結果上調。
- [RESULT] **已知但刻意不改的一項**：規格 §6 小節順序為 `6.1 → 6.4 → 6.2 → 6.3`（§6.4 是凍結前補上而我插錯位置）。重編號會動到 §2 與 §11 目前全部正確的交叉引用，為純版面問題churn 一份 digest 釘住的文件代價大於收益；記在 §15.3 以免下一個人以為是遺漏。
- **Driver 實作**：`backend/rl/train_ppo.py` 新增第三個互斥身分 `tracked_lineage_protocol_id`（scratch、v5 環境、非 v7 arm，既有 pilot／seedvar 分支的檢查順序**逐行未動**，依規格 §6.1；新的 request guard 是**獨立函式**而非既有函式裡的分支，因為不碰它是不改動它順序最可靠的辦法），並讓 `checkpoint_interval` 由 protocol 決定——原本 `:705` 寫死 `2_000_000`，使 2M 步的 run 一個中間 checkpoint 都不留，那正是 ROADMAP §9 第 2 項要補的缺口。
- [RESULT] Training seed **不可由命令列到達**：replicate index 由 profile id 推導、seed 由 protocol 依該 index 解析，故沒有任何 invocation 能把一個 profile 配上另一個 replicate 的 seed。新增 5 個 profile `stand_start_walk_stop_0p7_tracked_lineage_b1_r0..r4`。
- **Contract**：新增 `backend/tracked_lineage_contract.py`（stdlib-only、fail-closed）與 `backend/test_tracked_lineage_contract.py` 共 **65 個測試**，涵蓋 `TL-01`..`TL-08` 與 `TL-01b`，每個準則**雙向**測試（只測 happy path 只證明程式跑得動，不證明 guard 會擋）。五個標籤各有正控制，並有一個測試證明 `TL_METHOD_FAILURE` 不會被降級成其他四個之一。
- [RESULT] 三層 digest 連鎖補齊：規格 `sha256:7c9d6fe0…` ← protocol `sha256:8d82637d…` ← `tracked_lineage_contract.PROTOCOL_SHA256`；protocol 的 `training_driver_source_sha256` 由 `null` 補釘為 `sha256:2a3f50c0…`，與 superseded 的 `sha256:877da3b4…` 並存。`backend/rl/eval_policy.py` 逐位元仍等於 `sha256:0cf27434…`，由 `TL-01` 每次執行前重算比對。
- [RESULT] 測試：全套 **1 failed / 882 passed**（512.03 s）。唯一失敗是既有的 `test_stdlib_replay_passes_exact_synthetic_fixture` reduction-order 差異，與 2026-09-13 記錄的同一個，**未新增任何失敗**。數字對得起來：`816 + 1 + 65 = 882`。
- 仍未執行任何訓練、未產生任何證據、未改任何 flag。

## Unreleased — 2026-09-14 (t)

### `TRACKED-LINEAGE-TRAINING-V1` 凍結：兩格已定案，在修改任何 driver 之前 push

- [RESULT] 專案負責人於 2026-09-14 定案 §4 的兩格，**兩者皆在看到任何訓練曲線之前**——這是本節唯一重要的時序事實，也是這兩個值日後能被引用的唯一理由：
  - `CHECKPOINT_STORAGE = GIT_DIRECT`，`checkpoint_interval = 500_000`（每 replicate `4` 個、合計 `20` 個 ≈ `38 MB`）。理由是它是唯一同時「離線可驗」且「不需新基礎設施」的組合：本容器沒有 `git lfs`，`RELEASE_ASSETS` 與 `EXTERNAL_IMMUTABLE` 都需要網路才能驗，而 release assets 還可被有寫入權者刪改。
  - `FULL_EXPOSURE_THRESHOLD = 30/30 = 1.000000`，逐 replicate 判定。理由是 `PUB-B2` 的用途是讓後續比較落在 `R0`／`R1` 而非 `R3`／`R4`；reference 只要還有任何一個 episode 早期終止就仍是 censored，而 v7 線 `between_replicate_sd` 為 null 正是這個原因，`29/30` 會以較輕的形式複製同一個問題。
- [BLOCKER] **兩項代價在定案時即已知並接受，不得事後當成意外或當成「門檻訂得不合理」的理由**：repo 由 `11 MB` 增為約 `49 MB` 且每條新訓練線再加（第三條線之前應重新評估外部 immutable storage，本 protocol 不預先承諾該轉換）；scratch policy 在 5 個 replicate 上全部做到 30/30 是很高的門檻，**很可能**得到 `TL_REFERENCE_NOT_ATTAINED`。門檻凍結後不得因結果下調——未達門檻是 `PUB-B2` `NOT_ATTAINED`，是一項結果。
- [RESULT] 新增 [`backend/rl/tracked_lineage_training_protocol.json`](backend/rl/tracked_lineage_training_protocol.json)（`sha256:e5566eb6bbcb3abf7f95ad9a7b25566b59133b70caf9692fe5e52489e25273ae`），其 `specification_sha256` 釘住規格 `sha256:c584ef4e018abad0f73524efc19686a5734002662c6445abf6c68deddfe5357c`。規格狀態由 `DRAFT_TWO_DECISIONS_OPEN` 轉為 `FROZEN_BEFORE_EXECUTION`。
- [BLOCKER] 三層互釘目前只完成**第一層**：contract 模組的 `PROTOCOL_SHA256` 要到實作 commit 才補上，`source_baseline.training_driver_source_sha256` 在凍結時**刻意為 `null`**——本線的 driver 修改尚未發生，先釘一個還不存在的 digest 等於事後補釘。兩者都由實作 commit 補上並由測試比對。這與 `R0-REGIME-HORIZON-PROBE-V1` 的凍結順序相同：先 push 規則，再寫讀規則的程式。
- [BLOCKER] **本次凍結 push 時 `train_ppo.py`、`eval_policy.py`、`simulator.py` 三個檔案逐位元未變**（`877da3b4…`／`0cf27434…`／`c27e00a0…`），與 §10 執行順序第 3 步的要求一致。
- [RESULT] **新增 §6.4，更正我自己在初稿 §6.1 留下的一個假陳述。** 初稿寫「只改 `train_ppo.py`」，但要取得逐控制步 trace 就必須改 `eval_policy.py`——`rl/eval_policy.py:391` 的 `control_step_trace` 只在 `pilot_interface is not None` 時寫出，而那只在 v7 pilot 與 seedvar 路徑成立。改它會弄紅 `test_v7_candidate_selection_contract.py::test_precondition_digests_match_the_pinned_sources`，也就是弄紅一個綁在 owner 已於 2026-09-10 授權的 protocol 上的綠測試。
- [RESULT] 因此**範圍收窄為 `PUB-B1` 與 `PUB-B2`**：generic evaluation 路徑仍寫出 `duration_s`（`rl/eval_policy.py:325` 為 `round(len(rewards) * 0.02, 3)`，實測 450 步得 `9.0`、449 步得 `8.98`，三位小數可乾淨分離），足以量 full-exposure 比例。`PUB-B3` 需要另一份 protocol，且該 protocol 必須先處理 `eval_policy.py` 這個 owner-gated 問題。§8.3 具名列出本線**量不到**什麼：任何 saturation 重算、任何 `R0`..`R5` regime 分類、任何可與 `V7_EXPOSURE_CENSORING_AUDIT` 比較的 exposure 分析。
- [BLOCKER] generic 路徑**沒有** v7／seedvar 路徑那兩道 `*_EVALUATION_SEED_SCHEDULE_OVERRIDE_FORBIDDEN` 保護（`rl/eval_policy.py:124`、`:161`），所以 seed schedule 只能在**分析期**強制。新增驗收 `TL-01b`：保留輸出的 `evaluation_seeds` 必須恰為 `22000..22029`，不符即 `TL_METHOD_FAILURE`。
- 未執行任何訓練、未產生任何證據、未改任何 flag。`paper_data_ready` 等四個 flag 不變。

## Unreleased — 2026-09-13 (s)

### `TRACKED-LINEAGE-TRAINING-V1` 草稿：新訓練線的設計，兩格待專案負責人決定

- 新增 [TRACKED_LINEAGE_TRAINING_SPEC](docs/TRACKED_LINEAGE_TRAINING_SPEC.md)，狀態 `DRAFT_TWO_DECISIONS_OPEN`。**尚未凍結、沒有 protocol JSON、沒有任何 digest 被釘住**；§4 填定後才 freeze、push、執行。
- [RESULT] **凍結的設計決定：必須 scratch，不得 warm start。** [ROADMAP §9 第 2 項](docs/ROADMAP.md) 原文是「scratch **或** tracked warm start」，本規格收窄為 scratch。版控內唯一的 warm start 候選是 v5 artifact——它的**檔案**可由 digest 重建，**訓練過程**不可重建，而那正是本線要移除的缺陷。從它 warm start 會原封不動保留 `CONDITIONAL_ON_FIXED_WARM_START`：用一條新線去複製它要移除的限制，等於沒做。
- [BLOCKER] 代價明說：scratch 比 fine-tune 難得多，v5 是經 v1→v2→v3→v4→v5 多輪 curriculum 才到 Live 10/11，單發 scratch 未必能到。§9 預先宣告 `TL_REFERENCE_NOT_ATTAINED` 與 `TL_BUDGET_EXHAUSTED` 為**結果而非失敗**，且上限不得因結果上調。
- [RESULT] 凍結：5 replicates、training seeds `9100/9112/9124/9136/9148`（與既有 11 個全部不相交、environment seed block 互不重疊）、`parallel_envs 12`、上限 `2,000,000` steps／replicate、evaluation seeds `22000–22029`（全新）。`18000–18029` EXHAUSTED、`19000–19029` retired、`20000–20029` sealed 三者皆不得使用。
- [RESULT] 依 seedvar 實測吞吐（約 `1,683` steps/s）估 `2M` steps ≈ 20 分／replicate、5 個 ≈ 1.7 小時。容器為 ephemeral，故執行順序要求**逐 replicate** 保留而非全部跑完才保留。
- [BLOCKER] 本線會修改 `backend/rl/train_ppo.py`，使已執行 seedvar protocol 的 `training_driver_source_sha256` 對活著的 repo 不再為真。§6.2 要求本 protocol **同時保留兩個 digest** 並具名揭露——這正是 [RUN_MANIFEST_LOCK_BINDING_SPEC §15.4](docs/RUN_MANIFEST_LOCK_BINDING_SPEC.md) 指定的揭露位置。§6.3 另補上 seedvar 沒有的執行期 digest 重算。
- [BLOCKER] `TL-CK-04`：reference checkpoint 的選擇規則必須在**看到評估結果之前**凍結。v5 的 checkpoint 是看過結果後從一個 regressed run 裡挑出來的，那是它 provenance 說不清楚的原因之一；本線不得重演。
- 兩格待決（見 §4，皆須在看到任何訓練曲線之前固定）：`CHECKPOINT_STORAGE`（無 git-lfs、`.git` 現 11 MB；`500k` 間隔 20 個 ≈ 38 MB，`250k` 間隔 40 個 ≈ 76 MB；建議 `GIT_DIRECT` + `500k`，因為它是唯一同時離線可驗且不需新基礎設施的組合）與 `FULL_EXPOSURE_THRESHOLD`（建議 `30/30`）。
- [BLOCKER] §4.2 初稿的精度錯誤已就地更正：初稿建議的 `0.98` 在本設計下**不存在**——判定是逐 replicate，而每個 replicate 只有 30 個 episode，`0.98` 會進位成 `30/30`。真正可選的只有 `30/30` 與 `29/30`（`28/30` 比 v7 reference 還鬆，不可取）。

## Unreleased — 2026-09-13 (r)

### `LOCKBIND-AMENDMENT-01-LB12-SCOPE`：修掉我自己在 `LB-12` 留下的過度約束

- [BLOCKER] **缺陷**：`LB-12` 條文宣稱「**本 contract** 的實作沒有修改 `train_ppo.py`／`eval_policy.py`／`simulator.py`」，但實作出來的測試比對的是**工作樹當下**的內容。那回答的是另一個問題——「有沒有任何人在任何時候改過」——屬於各檔案自己的 contract，本 contract 沒有立場加這道限制。兩種讀法在實作當下給出相同答案，所以驗收時沒有顯現，只在**未來的修改**上分歧。
- [RESULT] **具體傷害**：[ROADMAP §9 第 2 項](docs/ROADMAP.md) 的新訓練線必須改 `backend/rl/train_ppo.py`——`:705` 的 `checkpoint_interval = 2_000_000` 使 2M timesteps 以下的 run **不保存任何中間 checkpoint**，而「有版控 checkpoint lineage」正是該項的定義。在原始 `LB-12` 之下，那次修改會讓一個無關的 contract 變紅，唯一出路是修改凍結的驗收條件——正是本專案最不該養成的習慣。
- [RESULT] **更正**：`LB-12` 改以 git 讀取凍結父 commit `501a7ee` 與實作 commit `c4bd470` 兩點的內容比對，把主張固定成不受未來影響的歷史事實；另新增一個測試斷言本 contract **不**凍結這三個檔案，並在 protocol 內具名各檔案的持續保護歸屬。實測：`train_ppo.py` 改成非釘住值後本 contract 63 測試全綠，同樣修改在原版為紅。
- [BLOCKER] **這不是門檻放寬**，必須明說否則會被正確地質疑：條文主張一字未改，本 contract 的實作仍然不得修改那三個檔案。放寬會是把「不得修改」改成「可以修改」；本次沒有。更正後**更強**——原版只在工作樹恰好乾淨時成立，之後無法區分「本 contract 動過手腳」與「別人後來改過」。
- [RESULT] `train_ppo.py` **在執行期無人重算**這個缺口（規格 §2.3）**不在此處補**。正確位置是修改該 driver 的那條線自己的 protocol：它必須具名記載自己的 driver 與 2026-09-08 保留證據所用的 driver 不同並同時保留兩個 digest。曾考慮並否決的 `LB-13`（在本 protocol 內設 source-drift 登記簿）理由記於規格 §15.4，以免下一個人以為沒想過。
- Digest 連鎖重 pin：規格 `1b3a7b26…` → `717bb910…`；protocol `2e3bde9a…` → `5202173f…`；`run_manifest_lock.PROTOCOL_SHA256` 同步。於**任何保留證據依賴本 contract 之前**套用，不使任何既有證據失效。
- `LB-01`..`LB-11`、五個標籤、兩個 digest 詞彙、範圍、`simulator.py` 例外、capture-before-run、分析期 gate、前向立場與 claim boundary 全部逐字不變。

## Unreleased — 2026-09-13 (q)

### 文件整理：去重、修正過期陳述、對齊 `RUN-MANIFEST-LOCK-BINDING-V1`

- **安裝與測試指令去重**：原本同一段 PowerShell 安裝區塊出現在 [README](README.md)、[USAGE §1](docs/USAGE.md) 與 [REPOSITORY_GUIDE §4](docs/REPOSITORY_GUIDE.md) **三處**。現在只留 README 一份，另外兩處改為指回。完整測試指令同理。
- [BLOCKER] **修正八處過期陳述**：`ENVIRONMENT_LOCK_SPEC`、`EXPERIMENT_PROTOCOL`、`PAPER_DATA_READINESS`、`PROJECT_STATUS`、`PUBLICATION_PLAN`、`ROADMAP`、`VV_PLAN`、`STATUS.yaml` 都還寫著「沒有任何 pipeline 把 lock record 綁進 run manifest」。該句自 2026-09-13 起為假。改寫時一併保留三項**仍然成立**的殘餘缺口，避免從一個錯誤陳述換成另一個：sidecar 可被遺漏、`backend/simulator.py` 明示排除、2026-09-08 bundle 的兩個 lock 斷言不可重驗。
- [RESULT] **具日期的 receipt 與 decision record 一律不改寫**（`ENVIRONMENT_LOCK_IMPLEMENTATION_RECEIPT_2026-09-08`、`MOTION_SCOPE_DECISION_2026-09-11` 等），凍結且被 digest 釘住的 spec 亦同。它們記錄的是當時的狀態，事後改寫會毀掉它們的用途。
- **USAGE 補上缺的操作**：新增 §7.1「產生可引用的 run」，說明 `backend/rl/bind_run_lock.py` 的用法與三個旗標語義。原本手冊只教直接呼叫 driver，而那樣產生的 run 現在會被 gate 判為 `RUN_LOCK_UNBOUND`。§1 原稱「尚無 environment lock」，§10 只寫到 v6，§12 未提綁定記錄，皆已更正。
- **REPOSITORY_GUIDE 更正版本與預期測試結果**：release 由過期的 `0.1.0` 改為 `0.2.0-dev`（權威值在 `STATUS.yaml`）；§5 明寫預期為 1 failed / 816 passed，**新增任何失敗才算 regression**，避免下一個人把已知的 reduction-order 差異誤判為自己弄壞的。tracked 清單補上四個證據 bundle 目錄。
- **README 壓縮**：`Repository 內容` 與 `下一階段` 兩節原本是 `REPOSITORY_GUIDE` 與 `PROJECT_STATUS §8` 的散文複述，改為表格加連結；`現況一覽` 新增證據環境綁定一列。載重的 `backend/rl/artifacts/` gitignore 警告保留並升為 `[BLOCKER]`。
- `PAPER_RUN_MANIFEST_V1` 在 `EXPERIMENT_MATRIX_CONTRACT`、`RESEARCH_EXECUTION_PLAN` 中改為版本中立寫法；`PAPER_DATA_READINESS` 新增第 14 項記錄綁定，原第 14 項順延為 15。
- 未改任何程式、contract、protocol、門檻或 digest；`paper_data_ready` 等四個 flag 不變。

## Unreleased — 2026-09-13 (p)

### `RUN-MANIFEST-LOCK-BINDING-V1`：lock record 綁進 run manifest，而且沒有讓任何既有為真的事變成假的

- 凍結先於實作：[spec](docs/RUN_MANIFEST_LOCK_BINDING_SPEC.md)（`sha256:1b3a7b26…`）與 `backend/run_manifest_lock_binding_protocol.json`（`sha256:2e3bde9a…`）在 commit `00f8e62` 推送，該 commit **不含任何程式碼改動**。[receipt](docs/RUN_MANIFEST_LOCK_BINDING_RECEIPT_2026-09-13.md)。
- [RESULT] **量到一個活著的 provenance 缺陷**：同一個欄位名 `environment_lock_sha256` 在 `second_case_evidence` 存的是 lock **檔案位元組**（`sha256:911b4362…`），在 `seed_variance_evidence` 存的是 **`locked` 子樹** digest（`sha256:93d23a27…`），而兩次執行所用 lock record 的 `locked_sha256` **完全相同**。兩個保留值不同**只因為兩條 pipeline 對該欄位的定義不同**；讀者比較它們會錯誤地推論「證據來自不同環境」。新記錄以 `lock_record_sha256` 與 `environment_locked_sha256` 兩個名字保留兩個量，並在兩處拒絕那個模糊名稱。舊 bundle 未改寫（digest 已被釘住），缺陷具名記錄。
- [RESULT] **綁定採 sidecar**，因為三個 producer 若直接改寫會讓某件今天為真的事變成假的：`rl/eval_policy.py` 被 `test_v7_candidate_selection_contract.py` **主動重算**並比對 owner 於 2026-09-10 授權之 protocol 的 pin；`rl/train_ppo.py` 被已執行的 `SEEDVAR-...-V1` 釘住而執行期無人重算；`simulator.py` 的 `meta.provenance` 進入 deterministic content hash。[INFERENCE] 為了修一個 provenance blocker 而讓兩個既有 pinned digest 變成假的，等於拿本專案存在的理由去換方便。
- [RESULT] 結果是**沒有任何 pinned digest 變假、沒有任何綠測試變紅、不需要任何 protocol amendment**，`v7_candidate_selection_contract.PROTOCOL_SHA256` 未重釘，2026-09-10 的授權仍指向同一份 protocol。`LB-12` 以測試重算那三個檔案的 SHA-256，把「我不碰它們」從宣稱變成機器檢查。
- [RESULT] 新增 `RUN_LOCK_BINDING_V1`（18 欄位、key set 雙向精確）、五個 fail-closed 標籤（`RUN_LOCK_BOUND` / `UNBOUND` / `INSUFFICIENT` / `MISMATCH` / `BINDING_METHOD_FAILURE`，最後一個永不降級），gate 要求 `satisfies_full_lock_requirement`（`MEASURED` **且** `FULL_LOCK`）而非只看 `lock_class`，且該旗標為**推得**而非宣告。`backend/run_manifest_lock.py` module scope 僅 import stdlib（AST 測試 + `python -I -S` 子行程實跑）。
- [RESULT] `PAPER_RUN_MANIFEST` 升至 `V2`（必備 `environment_lock` 區塊、可選 `environment_lock` artifact role）；`V1` 仍可讀故既有 bundle 不失效，但 `V1` 永不可能通過綁定 gate。兩個 V1 bundle builder 改為產生 `V2` 並在回傳前要求 `RUN_LOCK_BOUND`。`backend/rl/bind_run_lock.py` 以 subprocess 包覆未經修改的 driver，其 `binding_mode` 與 `sidecar_reason` **由凍結 protocol 依 producer 路徑查出**，包覆器無法宣稱更弱的理由。
- [BLOCKER] **blocker 只是變窄，不是清除**：sidecar 可以被遺漏（直接呼叫 driver 仍得 `RUN_LOCK_UNBOUND`，這是具名結果而非靜默通過）；`backend/simulator.py` 為第一天就存在的明示例外；2026-09-08 seed-variance bundle 未重建，`build_training_seed_variance_bundle.py:204`／`:208` 的兩個寫死 `True` 仍是**不可重新驗證的斷言**。
- [BLOCKER] **自承缺陷**：規格 §12 寫「兩條指令都必須全綠」，這在我凍結它之前就已是錯的——`PRIMARY_CASE_RECEIPT_IDENTITY` 自 2026-09-08 起即被記錄為量測結果而非放寬。本次就地定位其成因（fixture 用 `np.mean`、replay 用 stdlib `sum(...)/len(...)`，`196.2` 對 `196.19999999999854`，差 `1.46e-12`；把四個 thread 變數 pin 回 `1` 不改變結果，故非 thread drift）。依 §7.2「門檻不得因結果而放寬」，凍結的 §12 與 `1e-12` 門檻**都未修改**，正確措辭留給下一個 contract 版本。
- 測試：`backend/` **1 failed / 816 passed**（405.58 s）。新增 62 個測試，未新增任何失敗；基線為 1 failed / 754 passed。規格 §12 的針對性指令 362 passed 全綠。

## Unreleased — 2026-09-11 (o)

### `R0-REGIME-HORIZON-PROBE-V1` 執行完成：兩個對比皆 `R0_WINDOW_FOUND`

- 凍結（`06ebf60`）push 之後，在 clean source `edf3611` 上執行。先 commit 分析程式再執行，故 source pre == post。[receipt](docs/R0_REGIME_PROBE_RECEIPT_2026-09-11.md)、結果檔 `backend/r0_probe_evidence/2026-09-11/probe_result.json`（`sha256:f8a8db72…`）。
- [RESULT] **兩個對比皆 `R0_WINDOW_FOUND`**：`C_B`（`V7B` vs `V7A`）有 290 個 horizon 滿足 `R0-P0a`（`125`–`414`），**全部 290 個同時滿足 `R0-P0b`**，選中 `H = 414`（8.28 s，reference 平均 duty `40.262319` pp）；`C_C`（`V7C` vs `V7A`）有 28 個（`125`–`152`），全部 adequate，選中 `H = 152`（3.04 s，`22.089474` pp）。
- [RESULT] **本 probe 設計要防的 R5 陷阱，在這個 plant 上沒有發生。** reference 平均 duty 在整個 P0a 範圍內最低 `9.893333` pp（於 `H = 125`），是被判定為退化的 Hopper reference（`2.712%`）的 3.6 倍。[BLOCKER] 這是關於**這個 plant 與任務**的量測，不是一般結論——同一個兩段式規則在 Hopper 上確實會擋下退化 reference。兩者合起來說明非退化性必須逐案檢查。
- [RESULT] **綁住 R0 窗口的是 candidate 不是 reference**：每個 P0a 上界恰等於該 candidate 最短的 episode（`V7B` `414`、`V7C` `152`；reference 最短 `419`）。
- [RESULT] **對 A-C3 最有意義的一項**：同一批 policy、同一批 evaluation seed，只改 evaluation horizon，同一個對比就跨 regime——`C_B` 在 `H = 450` 是 `R2`（bound 排除 0 但 `between_replicate_sd` 無定義），在 `H ≤ 414` 是 `R0`（點識別）；`C_C` 在 `H = 450` 是 `R1`（artifact），在 `H ≤ 152` 是 `R0`。`C_B` 的轉換只需放棄 **36 個 control step（`0.72` s，不到 horizon 的 8%）**，因為 `V7A` 的 7 個與 `V7B` 的 30 個早期終止**全部落在 `FINAL_STAND`**（8.0–9.0 s），而 `V7C` 的 150 個全部落在 `STEADY_WALK`（`3.04`–`3.28` s）。
- [INFERENCE] 也就是說，「partially identified 且變異不可估計」與「點識別」之間的差別，在此案例上是評估者對最後 0.72 秒的一個選擇——而該選擇在標準實務中既不被控制也不被報告。[BLOCKER] 這**不表示**應改用截斷 horizon 評估：截斷改變估計目標。結論是 regime 標籤不是資料的固有屬性，必須連同 horizon 一起報告。
- [BLOCKER] **不是第六個獨立實例**：它是同一批 450 個 episode 的重讀，加入的是**案例內**示範，不是新的 plant 或 policy family。選中的 `H` 值由資料決定（追隨 candidate 最短 episode），不是推薦的評估 horizon。
- 驗證：`python -I -S`（`isolated`、`no_site`）獨立重算 **bit-exact**（`sha256:24451902…`）；environment lock 為 `MEASURED_ENVIRONMENT_LOCK` / `FULL_LOCK` 且 `locked_sha256` 與母證據（seedvar 執行）**逐位元相同**；另檢查左至右／`math.fsum`／反向三種求和順序，最大差異 `1.0 × 10⁻⁶`，而最近門檻 margin 為 `9.893333` pp 對 `5.0` pp，**沒有任何判定依賴 reduction order**。`R0-01` .. `R0-08` 全數 PASS。
- 新增 `backend/r0_regime_probe_contract.py`（stdlib-only，可在 `python -I -S` 下重算）、`backend/run_r0_regime_probe.py` 與 25 個測試。測試替**三個結果標籤各建一個 positive control**——一條對任何輸入都只能回一種答案的規則，對資料毫無資訊，那正是 v7 selection 自檢曾經藏著、被測試抓到的洞。
- [RESULT] taxonomy 六格自此全部有實例；[TRACK_A_REFRAME §3](docs/TRACK_A_REFRAME_2026-09-09.md) 的 `R0` 列由「未觀察到」改為 pilot 實例並附上述限制。
- 測試：`backend/` **1 failed / 754 passed**（511.86 s）。新增 25 個 R0 測試，未新增任何失敗；唯一失敗仍是具名 environment lock 下記錄的 `PRIMARY_CASE_RECEIPT_IDENTITY` reduction-order 案例，未放寬。
- [BLOCKER] 門檻**未**因結果調整：首次執行即得 `R0_WINDOW_FOUND`，不存在放寬重跑。沒有訓練、沒有新評估、沒有動任何 seed；四個總開關皆為 false 不變。
- 對齊：`STATUS.yaml`（`r0_regime_probe`、`docs`）、[PROJECT_STATUS](docs/PROJECT_STATUS.md)、[PUBLICATION_PLAN](docs/PUBLICATION_PLAN.md)、[TRACK_A_REFRAME](docs/TRACK_A_REFRAME_2026-09-09.md)、README。

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
