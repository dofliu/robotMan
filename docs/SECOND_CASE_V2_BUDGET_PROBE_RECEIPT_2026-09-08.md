# V2 Budget Probe 回條（pilot）

日期：2026-09-08 ｜ 對應 gate：`PUB-A1`（V2 前置） ｜ 性質：**pilot，不是 evidence**

## 1. Probe V1：`SECONDCASE-V2-BUDGET-PROBE-V1` → `PROBE_NEGATIVE_MAX_BUDGET_REACHED`

| 項目 | 值 |
|---|---|
| Probe JSON | `backend/rl/second_case_v2_budget_probe.json` `sha256:8f20535c43157169026ff26dcf7c825334e4889b8ed687b8e61477cc6bf01370` |
| 結果 JSON | `backend/second_case_evidence/2026-09-08-v2-budget-probe/probe_result.json` `sha256:76612f470c952501486efca32518d450424417406ab6553248e4496cff7ab021` |
| Source | `e11463482765aa774446a0aa59706bdc5d8a6700`，pre == post，clean（tree 與 merge 後的 `3b0b4f3` 相同） |
| Lock | `locked_sha256 sha256:93d23a27…`（與 V1／seed-variance 執行相同），0 mismatch |
| Recipe | V1 的 SB3 PPO 預設、單 env、reference arm（`alpha = 1.0`）、probe seed `42000` |
| 評估 | 每 checkpoint 30 個 probe seeds `43000–43029`，deterministic |
| 規則（凍結） | 連續兩個 checkpoint ≥ 27/30 FULL_EXPOSURE → budget = 較晚者；上限 12 × 245,760 = 2,949,120 |

### 1.1 曲線

| ck | 累計 steps | FULL／30 | realized steps min／med／max | naive duty |
|---:|---:|---:|---|---:|
| 1 | 245,760 | 0 | 358／558／739 | 44.604% |
| 2 | 491,520 | 0 | 203／263／436 | 54.005% |
| 3 | 737,280 | 0 | 261／291／378 | 58.796% |
| 4 | 983,040 | 0 | 272／304／376 | 55.919% |
| 5 | 1,228,800 | 0 | 332／349／449 | 55.111% |
| 6 | 1,474,560 | 0 | 319／349／441 | 55.692% |
| 7 | 1,720,320 | 0 | 193／339／540 | 55.990% |
| 8 | 1,966,080 | 0 | 221／270／695 | 58.412% |
| 9 | 2,211,840 | 0 | 167／258／414 | 62.862% |
| 10 | 2,457,600 | 0 | 231／433／800 | 60.361% |
| 11 | 2,703,360 | 0 | 203／375／468 | 61.075% |
| 12 | 2,949,120 | **1** | 133／240／1000 | 54.528% |

[RESULT] 360 個 probe episode 中 **1 個** 跑完 horizon。SB3 PPO 預設在 Walker2d-v5 上到 2.95M 步都沒有形成能站穩的 reference；median realized steps 在 240–560 之間震盪，沒有上升趨勢。0 個 `NONFINITE`。總 wall time 2,968 s。

[INFERENCE] 這與 V1 的觀察一致（V1 reference 在 301k 步 median 178–376），並把它延伸到 10 倍的 budget：**問題不是 budget，是 recipe**。

[BLOCKER] 依凍結規則，probe V1 的上限**不得**事後提高。V2 在此 recipe 下不凍結。

## 2. 決定：換 recipe，不換 plant、不換規則

決定在 checkpoint 6 時（結果出來**之前**）寫下（scratch `PROBE_CONTINGENCY.md`，摘要如下）：

- **不變**：plant（Walker2d-v5 預設）、兩臂與 wrapper、saturation threshold、adequacy 規則（≥ 27/30、連續兩個 checkpoint）。
- **改變**：訓練 recipe 改為 **rl-baselines3-zoo 的 Walker2d tuned PPO 設定**（VecNormalize obs+reward、`n_steps 512`、`batch 32`、`n_epochs 20`、`lr 5.05041e-05`、`clip 0.1`、`ent 0.000585045`、`vf_coef 0.871923`、`max_grad_norm 1.0`、`log_std_init −2`、`ortho_init False`、ReLU、`[256, 256]`）。理由來自**外部出處**（已發表的參考設定），不是我們的資料。
- **上限**：8 × 245,760 = 1,966,080，取 zoo 自身 `n_timesteps = 1e6` 的 2 倍，在看到任何 probe-V2 曲線之前固定。
- **新 seeds**：training `46000`，evaluation `47000–47029`；probe V1 與 probe V2 的區段對 V2 皆為禁區。

[BLOCKER] **Recipe 數值標記為 `U_VERIFIED_FROM_MEMORY`**：本執行環境無法讀取 GitHub raw content，上述數值是憑記憶寫下的 zoo 設定；投稿前必須對照已發表檔案核對。核對結果影響的是 recipe 的出處描述，不影響 probe 作為 pilot 的效力（probe 量的是「這組設定下 reference 站不站得穩」，設定本身被完整記錄）。

## 3. Probe V2：`SECONDCASE-V2-BUDGET-PROBE-V2`

| 項目 | 值 |
|---|---|
| Probe JSON | `backend/rl/second_case_v2_budget_probe_v2.json` `sha256:70662db367b3dbaf8edbf18efa96a6e7faff4e6edfa43769ed0129728b7b36f7` |
| 結果 JSON | `backend/second_case_evidence/2026-09-08-v2-budget-probe-v2/probe_result.json` |
| Source | `a6508ac3c292c6e4bec5dde56c1583460793c9a9`，pre == post，clean（tree 與 merge 後的 `7091545` 相同） |
| Lock | 同一 `locked_sha256`，0 mismatch |
| 結果 | **`PROBE_NEGATIVE_MAX_BUDGET_REACHED`** |

### 3.1 曲線（tuned recipe、probe seed 46000、probe eval seeds 47000–47029）

| ck | 累計 steps | FULL／30 | realized steps min／med／max | naive duty | 累計 wall |
|---:|---:|---:|---|---:|---:|
| 1 | 245,760 | 0 | 23／24／568 | 13.714% | 689 s |
| 2 | 491,520 | 0 | 187／202／206 | 6.517% | 1,440 s |
| 3 | 737,280 | 0 | 68／194／209 | 2.596% | 2,222 s |
| 4 | 983,040 | **5** | 48／304／1000 | 3.769% | 3,023 s |
| 5 | 1,228,800 | 0 | 152／173／194 | 3.415% | 3,847 s |
| 6 | 1,474,560 | 0 | 150／156／165 | 1.639% | 4,764 s |
| 7 | 1,720,320 | 0 | 116／139／155 | 2.884% | 5,740 s |
| 8 | 1,966,080 | 0 | 81／144／154 | 3.407% | 6,714 s |

[RESULT] 240 個 probe episode 中 **5 個**跑完 horizon，全部在 checkpoint 4；之後 policy 退化到 median ~140–170 步的一致早跌。0 個 `NONFINITE`。
[INFERENCE] 兩種 recipe（SB3 預設到 2.95M、zoo tuned 到 1.97M）在 Walker2d-v5 單次訓練下都沒有形成能穩定跑完 horizon 的 reference。tuned recipe 的 saturation 也低得多（1.6–13.7% vs 預設的 44–63%），這與 VecNormalize＋小 `log_std_init` 一致。
[BLOCKER] 依規則，probe V2 上限不追加；V2 在 Walker2d 上不凍結。

## 4. 決定：換 plant（probe V3，`SECONDCASE-V3-BUDGET-PROBE-HOPPER-V1`）

在 probe V2 結果**之前**（ck6 時）寫下的下一步：只換 plant，wrapper、兩臂、threshold、規則不動。

| 候選 | 判定 |
|---|---|
| **Hopper-v5** | **採用**：平面腿式、預設跌倒即終止（`healthy_z_range (0.7, ∞)`、`healthy_angle_range ±0.2`），比 Walker2d 容易；3 actuators、gear 200，saturation 非退化 |
| InvertedDoublePendulum-v5 | 排除：reference 站穩後 saturation ≈ 0%，naive 與 bound 的 contrast 必同號，artifact 在數學上不可能出現 |
| HalfCheetah／Swimmer | 排除：無 termination，無可 censor |
| Ant-v5 | 排除：兩臂幾乎都不會終止，P1 必失敗 |
| Humanoid-v5 | 排除：預設 recipe 在數 M 步內站不起來，與 Walker2d 同病 |

| 項目 | 值 |
|---|---|
| Probe JSON | `backend/rl/second_case_v3_budget_probe_hopper.json` `sha256:0e291db1bd4e3b8ebd16d9143d73a0a9b9c05580b965743f938b28bbd093a2ef` |
| Plant | `hopper.xml` `sha256:3ce93a055ffdcd83c0c701d2400768e40d2cbb9532f3c4ae33377c27f8b39f9e`，horizon 1000，obs 11（wrapper 後 14），`H·J = 3000` |
| Recipe | rl-zoo Hopper tuned PPO（VecNormalize、`n_steps 512`、`batch 32`、`n_epochs 20`、γ 0.999、λ 0.99、lr 9.80828e-05、clip 0.2、ent 0.00229519、vf 0.835671、max_grad_norm 0.7、ReLU 256×256、`log_std_init −2`）——**`U_VERIFIED_FROM_MEMORY`** |
| Seeds | training `48000`，evaluation `49000–49029`；先前所有區段皆為禁區 |
| 規則／上限 | 同前：≥ 27/30、連續兩個 checkpoint；8 × 245,760 = 1,966,080 |
| 若負結果 | 記錄、不追加上限、**停止**——是否再投入算力或改第二案例設計，是專案負責人的決定 |
| 結果 JSON | `backend/second_case_evidence/2026-09-08-v3-budget-probe-hopper/probe_result.json` |
| Source | `334efc391526d212c676960118a1379bed310732`，pre == post，clean |
| Lock | 同一 `locked_sha256`，0 mismatch |
| 結果 | **`PROBE_BUDGET_FOUND`：selected budget `1,474,560`**（ck5、ck6 連續 30/30） |

### 4.1 曲線（Hopper-v5、tuned recipe、probe seed 48000、probe eval seeds 49000–49029）

| ck | 累計 steps | FULL／30 | realized steps min／med／max | naive duty mean（min／med／max） | return min／med／max | 累計 wall |
|---:|---:|---:|---|---|---|---:|
| 1 | 245,760 | 30 | 1000／1000／1000 | 0.013%（0.00／0.00／0.13） | 1004／1013／1022 | 817 s |
| 2 | 491,520 | 23 | 94／1000／1000 | 0.000% | 88／1006／1008 | 1,840 s |
| 3 | 737,280 | 30 | 1000／1000／1000 | 0.000% | 1007／1008／1010 | 2,985 s |
| 4 | 983,040 | 8 | 136／140／1000 | 6.968%（0.43／9.62／10.48） | 254／259／1019 | 4,148 s |
| 5 | 1,228,800 | 30 | 1000／1000／1000 | 8.822%（7.87／8.77／9.67） | 1011／1013／1017 | 5,337 s |
| **6** | **1,474,560** | **30** | 1000／1000／1000 | **2.712%（2.07／2.70／3.33）** | 1013／1014／1015 | 6,541 s |

[RESULT] 規則於 ck6 觸發。選定 checkpoint 的 reference 曝露充足（30/30），primary measurement **非零但很小**（2.71%；ck5 為 8.82%）。
[RESULT] **Reference 是「站著不動」的 hopper**：六個 checkpoint 的 return 中位數都在 1006–1014，≈ 每步 1.0 的 healthy reward × 1000 步，forward reward 幾乎為零；ck4 短暫開始跳躍（return 259、median 140 步、saturation 7–10%）後又退回站立。ck6 ep0 的 mean |applied| 0.285，saturated joint-step 比例 2.8%（第 2 關節 6.4%、其餘 ≤ 2%）。
[BLOCKER] **規則的缺口**：adequacy 只檢查 exposure，沒有要求 primary measurement 非退化。ck1／ck3 的 30/30 是 saturation ≈ 0% 的站立 policy，若 ck2 也 ≥ 27/30，規則會在 491,520 就觸發並選出一個 artifact 在數學上不可能出現的 reference（reference 為 0% 時 naive 與 bound 的 contrast 必同號）。這次是運氣（ck2 = 23/30）讓規則越過了退化區。任何後續 probe 規則都應加上「reference saturation ≥ 門檻」的條件。
[INFERENCE] 以 2.71% 的 reference rate，P2 要成立需要 naive t-interval（5 個 replicate）排除 0：候選臂觀察到的 rate 必須穩定低於 2.7 個百分點且跨 replicate 一致。這比 v7（36%）或 V1（36–64%）的 reference 難得多——**power 不確定**。
[RESULT] 算力：probe 訓練 1,474,560 步約 101 分鐘（tuned recipe，單 env）。凍結後的 protocol 為 10 個 cell → 約 **17 小時**序列執行；4 核可 3–4 個 cell 並行（每個 process 單執行緒，lock 要求的 thread pin 不受影響）→ 約 **5–6 小時**。
[BLOCKER] 依專案負責人指示，probe V3 完成後**停止並回報**：Hopper protocol **未凍結、未執行**。`SECONDCASE-EXPOSURE-CENSORING-HOPPER-V1` 在 contract 中仍為 unpinned（不可載入）。
[BLOCKER] Probe 的 `vecnormalize.pkl` 每個 checkpoint 覆寫同一檔案（`normalizer_path_for(policy)` 以固定檔名存於 checkpoints 目錄），因此只有最後一個 checkpoint 的 normalizer 被保留；各 checkpoint 當時的評估使用的是**當時**剛存下的統計值，結果正確，但無法事後重評早期 checkpoint。V2 cell 各有獨立目錄，不受影響。列為 probe runner 的已知限制。

## 5. 程式變更（為 recipe 與 plant 支援）

- `rl/second_case_runner.py`：`build_model()`／`wrap_normalizer()` 共用建構、`policy_kwargs`（activation 限 Tanh／ReLU）、VecNormalize 訓練後存 `vecnormalize.pkl` 並記 digest；評估在有 normalizer 時經 `VecNormalize.load(training=False, norm_reward=False)`，recorder 仍在 raw env 層，記錄的 action／reward 為未正規化值。
- `rl/second_case_budget_probe.py`：`recipe_override`（只允許 hyperparameters／normalize／policy_kwargs／source／verification_status），`effective_training()`。
- `second_case_exposure_contract.py`：`CELL_SCHEMA_V2` 多一欄 `normalizer_sha256`（recipe 有 normalize 時必填，無則必為 null）；V2 protocol 可帶 `training.normalize`／`training.policy_kwargs`，V1 帶則拒。V1 retained evidence 仍 bit-exact replay（測試固定）。

- `rl/second_case_budget_probe.py`：`environment_override`（plant 換置，`make_kwargs` 必須為空、plant 以 digest 重釘、`H·J` 重算）；`effective_environment()`。
- `second_case_exposure_contract.py`：pinned map 新增 `SECONDCASE-EXPOSURE-CENSORING-HOPPER-V1`（尚未凍結，digest 為 None，不可載入）。

## 6. Claim boundary

只支持「第二案例的 budget（與可用的 plant／recipe）該選多少」這一件事。不支持任何關於 Walker2d、兩臂、artifact 的陳述。Probe 資料不得與 V1、V2 或彼此比較。
