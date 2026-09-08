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
| 結果 | **執行中／待補**（本節於 probe V2 完成後更新） |

## 4. 程式變更（為 recipe 支援）

- `rl/second_case_runner.py`：`build_model()`／`wrap_normalizer()` 共用建構、`policy_kwargs`（activation 限 Tanh／ReLU）、VecNormalize 訓練後存 `vecnormalize.pkl` 並記 digest；評估在有 normalizer 時經 `VecNormalize.load(training=False, norm_reward=False)`，recorder 仍在 raw env 層，記錄的 action／reward 為未正規化值。
- `rl/second_case_budget_probe.py`：`recipe_override`（只允許 hyperparameters／normalize／policy_kwargs／source／verification_status），`effective_training()`。
- `second_case_exposure_contract.py`：`CELL_SCHEMA_V2` 多一欄 `normalizer_sha256`（recipe 有 normalize 時必填，無則必為 null）；V2 protocol 可帶 `training.normalize`／`training.policy_kwargs`，V1 帶則拒。V1 retained evidence 仍 bit-exact replay（測試固定）。

## 5. Claim boundary

只支持「V2 的 budget 該選多少」這一件事。不支持任何關於 Walker2d、兩臂、artifact 的陳述。Probe 資料不得與 V1、V2 或彼此比較。
