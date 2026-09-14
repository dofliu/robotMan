# `TRACKED-LINEAGE-TRAINING-V2` 執行 receipt

最後更新：2026-09-14 ｜ Protocol ID：`TRACKED-LINEAGE-TRAINING-V2` ｜ 對應 gate：`PUB-B2`
｜ 前身：[TRACKED-LINEAGE-TRAINING-V1](TRACKED_LINEAGE_TRAINING_RECEIPT_2026-09-14.md)

規格：[TRACKED_LINEAGE_TRAINING_V2_SPEC](TRACKED_LINEAGE_TRAINING_V2_SPEC.md)
（`sha256:ea1a56f0809f5a588c420fb8c52104fbc2b0eb10567be1baae8c152a35662289`）

證據等級：`DEVELOPMENT / SIM_ONLY_MUJOCO`

---

## 0. 一句話

**加倍預算讓獎勵從 `226.9`–`231.6` 升到 `283.1`–`295.3`，讓平均存活從 `2.440`–`2.811` s
升到 `2.725`–`3.458` s，而完整曝露仍然是 `0/30`，五個 replicate 全部，`150` 個 episode
全部。** 標籤 **`TL2_BUDGET_EXHAUSTED`**，由 contract runner 在保留證據上算出，不是人寫的。

---

## 1. 標籤是算出來的，不是宣告的

V1 的驗收由人逐條核對後寫進 receipt，讀者只能選擇相信作者。V2 不同：
`backend/rl/run_tracked_lineage_v2_contract.py` **只讀版控內的保留證據**，跑完
`TL2-01`..`TL2-09` 後輸出
[`tl2_contract_receipt.json`](../backend/tracked_lineage_evidence/2026-09-14/tl2_contract_receipt.json)。
任何人可以重跑並 diff。

```
$ python3 backend/rl/run_tracked_lineage_v2_contract.py --date 2026-09-14
label          : TL2_BUDGET_EXHAUSTED
curve_converged: False (any=False all=False, measured on lineage)
exposure       : r0 0/30  r1 0/30  r2 0/30  r3 0/30  r4 0/30
```

它刻意**不讀** `backend/rl/artifacts/`。那個目錄 gitignored、隨容器消滅；一個靜悄悄
依賴未保留檔案的檢查，會在最需要它的時候剛好失效。

---

## 2. 量測

| replicate | seed | V1 獎勵 | V2 獎勵 | V1 平均存活 | V2 平均存活 | 完整曝露 | 末/首四分位斜率比 | 收斂 |
|---|---|---|---|---|---|---|---|---|
| r0 | 9100 | 226.9 | **290.2** | 2.477 s | **2.803 s** | `0/30` | 1.119 | 否 |
| r1 | 9112 | 231.6 | **283.1** | 2.680 s | **3.458 s** | `0/30` | 0.636 | 否 |
| r2 | 9124 | 228.8 | **295.3** | 2.520 s | **2.807 s** | `0/30` | 1.143 | 否 |
| r3 | 9136 | 231.0 | **287.7** | 2.811 s | **2.956 s** | `0/30` | 1.039 | 否 |
| r4 | 9148 | 224.7 | **284.2** | 2.440 s | **2.725 s** | `0/30` | 1.091 | 否 |

門檻是 `9.0` s。最長的單一 episode 是 r1 的 `4.0` s。

### 2.1 曲線在上限處更陡，不是更平

五個 replicate 全部**未**收斂，而且**五個裡有四個的末四分位斜率比首四分位還大**
（比值 > 1）。跑到 `4,015,200` 步，這些曲線不是逼近天花板，是找到了更多可爬的空間——
同時曝露完全沒動。

V1 的末四分位斜率是 `+7.3`–`+11.9`／500k 步；V2 的是 `+11.8`–`+22.2`。**加倍預算之後，
獎勵曲線比之前更陡。**

### 2.2 兩個事先宣告的量測選擇，結果都沒有改變標籤

規格與程式碼在任何 V2 曲線存在之前就宣告了兩件事，且兩件都選了對「再加預算」更不利的
方向（見 §5）。結果：

- **lineage 曲線 vs 只看增量**：兩種讀法在五個 replicate 上**結論一致**（都未收斂）。
- **`any` vs `all` 聚合**：五個都是 `False`，所以兩種聚合同值。

**宣告沒有改變任何結論。** 這值得明說：事先宣告仍然是對的，而它這次剛好不用付代價；
把它講得比實際更關鍵，會是另一種形式的誇大。

### 2.3 一個我先立後撤的觀察

r2 跑完時，三個 replicate 呈現乾淨的反向關係——獎勵漲最多的存活漲最少。我在
r3、r4 還沒跑之前就把它記進 commit，並註明「三個點不是相關性，r3/r4 可能抹掉它」。

r3 抹掉了：

| | 獎勵增益 | 存活增益 |
|---|---|---|
| r0 | +63.3 | +0.326 s |
| r1 | +51.5 | +0.778 s |
| r2 | +66.5 | +0.287 s |
| r3 | +56.1 | +0.145 s |
| r4 | +59.5 | +0.285 s |

記錄保留，不刪除。**先立後撤的觀察，比悄悄丟掉的觀察誠實。**

五個 replicate 之後站得住的是更弱也更硬的敘述：**獎勵增益對存活增益不帶任何方向上可用
的資訊，而且無論如何每個 replicate 都是 `0/30`。**

---

## 3. 執行品質

凍結前寫下的算術，五個 replicate 全部命中，一步不差：

- realized `4,015,200`（= `1,999,968` resume + `82` 個 `24,576` rollout）
- checkpoint 落在 `2499960 / 2999952 / 3499944 / 3999936`
- 10 次執行（5 訓練 + 5 評估）gate 全部 `RUN_LOCK_BOUND`，環境鎖
  `sha256:93d23a27…`，與 2026-09-08 seedvar 執行逐位元相同
- 每次 `source_git_pre == source_git_post`，工作區皆乾淨

`TL2-08` 五個全部精確成立：被評估的 policy digest **就是**保留的 reference
checkpoint（`r<i>-3999936.zip`），不是那個未保留的 `policy.zip` 副產物。

---

## 4. 本線補掉的五個缺陷

每一個都是同一種形狀：**主張為真，但證據活不過容器**；或**程式跑過 fixture，沒跑過真正
凍結的東西**。

| # | 缺陷 | 為什麼之前沒被發現 |
|---|---|---|
| 1 | V1／V2 guard dispatch：V2 profile 會掉進 V1 分支 | 兩個 guard 各自單獨測過，沒測 `main()` 實際會走的路徑 |
| 2 | manifest 用 `relative_to(RL_DIR)` 記錄 resume 路徑，遇到 evidence 路徑就拋例外 | 放寬了 guard **接受**什麼，沒動 manifest **記錄**什麼——驗證與記錄是兩條路徑 |
| 3 | 保留腳本只支援 V1 | V2 的保留從來沒被執行過 |
| 4 | **訓練 run manifest 從未被保留**，只保留了評估的 | 索引裡有 digest，看起來很完整——但**沒人拿得到的檔案的 digest 不是證據** |
| 5 | `RUN_LOCK_BOUND` 無法離線重導：gate 只印到 console，sidecar 沒有 label 欄位，索引寫的是字串 `"see gate output"` | V1 五筆到今天還是這樣。從沒有人試著在保留證據上重跑這條準則 |

第一次完整跑 contract runner 又抓到兩個，同樣形狀：

6. `verify_checkpoint_lineage` 委派給 V1，而 V1 讀 `training_design.replicate_count`
   ——V2 凍結的 protocol 沒有這個鍵。protocol 已凍結不得改，所以改程式：replicate 數由
   **三個凍結事實**推導（`total_count / per_replicate_count`、seed 數、pinned resume 數），
   **三者不一致即 method failure**，而不是挑一個當權威。推導結果交給 V1 時傳的是複本：
   會修改被驗證對象的 verifier 已經不是 verifier。
7. runner 仍在讀 `binding["label"]`——正是本分支已在保留腳本裡修掉的那個佔位符。它在
   10 次執行上**全部 fail closed，完全正確**。現在推導只有一份，放在
   `run_manifest_lock.evaluate_relocated_run`，緊鄰 `evaluate_run`，因為 lock 語義屬於
   那個模組。`evaluate_run` 無法判斷保留副本：它比對 `bound_manifest_path`，而把證據複製
   進版控必然改變那個路徑。relocated 版本重算搬移後仍成立的部分，並**顯式放棄**路徑比對，
   而不是近似它。

---

## 5. Claim boundary

本線**支持**：

- 在此任務、此 recipe、此環境鎖下，`2,000,000` → `4,015,200` 步的續訓使獎勵顯著上升，
  而 `30/30` 完整曝露在 5 個 replicate、150 個 episode 上**一次都沒有達成**。
- 續訓線的 provenance 可重建：resume 來源逐一由 digest 釘住且在版控內，20 個 V2
  checkpoint 可從 repo 直接重新雜湊。

本線**不支持**：

- **不支持**「再多跑一些步數就會到 `30/30`」。曲線仍在上升，這正是 `TL2_BUDGET_EXHAUSTED`
  的定義，**不是**它會成功的證據。
- **不支持**任何 method-variance 或 between-replicate 陳述：分析單位是 training
  replicate，method-level 分母為 `5`，禁止分母為 `[30, 150, 450]`。
- **不支持**與 V1 的獨立比較：V2 **續訓**自 V1 的 checkpoint，兩者不獨立
  （`not_independent_of_v1: true`）。
- **不支持**任何物理可行性、安全、sim-to-real 或致動器主張。

### 5.1 升級規則：本結果**不**授權 V3

規格 `escalation_rule` 事先寫定：再次得到 `TL2_BUDGET_EXHAUSTED` 是**結果**，
**不授權**單純再加預算。V3 需要自己的 protocol 版本，並揭露它是在已知 V1 **和** V2
結果之後設計的。每次都付這個揭露成本，正是阻止無限升級的機制。

---

## 6. Gate 狀態

| Gate | 狀態 | 依據 |
|---|---|---|
| `PUB-B1` | 已達成（V1 已達成，V2 未削弱） | 20 個 V2 checkpoint 進版控，lineage 完整 |
| `PUB-B2` | **`NOT_ATTAINED`** | `pub_b2_pass: false`，0 個 replicate 達 `30/30` |
| `PUB-B3` | 未開始 | 本線不產生逐控制步 trace；需另一份 protocol |

---

## 7. 保留物清單

`backend/tracked_lineage_evidence/2026-09-14/`（V1 與 V2 共用日期目錄；步數範圍不重疊，
兩線各自保有索引，互不改寫）：

| 路徑 | 內容 |
|---|---|
| `checkpoints/r<i>-{2499960,2999952,3499944,3999936}.zip` | V2 的 20 個 checkpoint |
| `checkpoint_index_v2.json` | V2 lineage 索引與 5 筆評估摘要 |
| `training_runs_v2/r<i>/` | **訓練** run manifest／環境鎖／binding（V1 從未保留這些） |
| `training_run_index_v2.json` | 5 筆訓練執行摘要，含重導的 `RUN_LOCK_BOUND` |
| `evaluations_v2/r<i>/` | 評估輸出／環境鎖／binding |
| `training_curves_v2/r<i>-progress.csv` | V2 曲線 |
| `training_curve_index_v2.json` | lineage 收斂量測，含未採用的只看增量讀法 |
| `tl2_contract_receipt.json` | contract runner 的輸出，即標籤的來源 |

儲存成本：`backend/tracked_lineage_evidence/` 為 `77 MB`，`.git` 為 `83 MB`。規格 §5.3
在定案時預估 `.git` 約 `85 MB`，**實測落在預估內**。V1 §4.1「第三條線之前必須重新評估
外部不可變儲存」的要求**依然有效**，只是尚未到期。

---

## 8. 測試

`backend/`：**1 failed / 941 passed**（2026-09-14，507.79 s）。數字對得起來：

| 節點 | collected |
|---|---|
| `5b707cb`（V2 contract 之前的 main） | 892 |
| ＋32（`TRACKED-LINEAGE-TRAINING-V2` contract） | 924 ＝ 先前記錄的 1 failed / 923 passed |
| ＋2（guard dispatch）＋2（resume 路徑）＋8（保留線） | 936（PR #20 合併後的 main） |
| ＋6（本分支：replicate 數推導、relocated lock、標籤） | **942** ＝ 1 failed / 941 passed |

失敗項仍是同一個 `test_v1_analytical_suite.py::test_stdlib_replay_passes_exact_synthetic_fixture`
（`PRIMARY_CASE_RECEIPT_IDENTITY`），與 reduction-order 差異同源，**記錄為量測結果、未放寬**。
本線未新增任何失敗。

---

## 9. 下一步（本 receipt 不代為決定）

1. **接受 `PUB-B2` `NOT_ATTAINED` 並停止加預算**。這是規格的預設路徑。
2. 若要繼續，改變的**不該是預算**：`2,000,000` 步買到 `+0.33`–`+0.78` s，而門檻還差
   `5` s 以上。reward shaping、curriculum、任務定義或門檻本身才是候選——而**門檻在凍結後
   不得因結果下調**。
3. `PUB-B3` 需要逐控制步 trace，須修改 `backend/rl/eval_policy.py`，那會弄紅一個綁在
   owner 已授權 protocol 上的綠測試。需要另一份 protocol。

---

## 10. 相關文件

| 文件 | 關係 |
|---|---|
| [TRACKED_LINEAGE_TRAINING_V2_SPEC](TRACKED_LINEAGE_TRAINING_V2_SPEC.md) | 本線的凍結規格 |
| [TRACKED_LINEAGE_TRAINING_RECEIPT_2026-09-14](TRACKED_LINEAGE_TRAINING_RECEIPT_2026-09-14.md) | V1 的結果，本線存在的理由 |
| [TRACKED_LINEAGE_TRAINING_SPEC](TRACKED_LINEAGE_TRAINING_SPEC.md) | V1 規格與三份 amendment |
| [PUBLICATION_PLAN](PUBLICATION_PLAN.md) | `PUB-B` 系列 gate 定義 |
| [PROJECT_STATUS](PROJECT_STATUS.md) | 專案現況 |
