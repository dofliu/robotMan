# 第二案例執行回條：`SECONDCASE-EXPOSURE-CENSORING-WALKER2D-V1`

日期：2026-09-08 ｜ Publication gate：`PUB-A1` ｜ Spec：[SECOND_CASE_EXPOSURE_CENSORING_SPEC](SECOND_CASE_EXPOSURE_CENSORING_SPEC.md)

結果：**`SECOND_CASE_ARTIFACT_REPRODUCED`** —— 依凍結規則成立；**但 gate 未 PASS**，理由見 §6。

證據等級：`DEVELOPMENT / SIM_ONLY_MUJOCO / NOT_PREREGISTERED_INTERNALLY_FROZEN`

## 1. 一句話

在 Gymnasium `Walker2d-v5` 預設設定下，naive 的 per-step saturation 估計對 `W2D_C_FILTERED − W2D_A_DIRECT` 給出 `−28.795138` pp、95% t-interval `[−46.698919, −10.891357]` pp（排除 0，會被報成「low-pass filter 降低 saturation」）；assumption-free full-horizon bound 給出 `[−79.118, +55.913333]` pp（含 0，0/5 replicates 方向可識別）。**同一份資料、兩種 estimator、相反的結論**——與 v7 上量到的機制同構。但兩臂都重度 censored，bound 寬到必然含 0，所以這是「機制存在」的證據，不是 v7 那種不對稱 censoring 的示範。

## 2. 執行 provenance

| 項目 | 值 |
|---|---|
| Source（執行時） | `b683ddc363b1e040ba366c194430eba546e6ad22`，10 個 cell 前後皆 clean，pre == post |
| Source（merge 後） | `f2d311f`（PR #7 的 merge commit）；**tree 與 `b683ddc` 逐位元相同**，所以執行時的 source identity 對 merge 後的 main 仍成立 |
| Protocol | `sha256:45d1ec553a1124fd613f90a8034b27f10ef8f01f23a219cca216479fc4c5350c`（凍結並 push 於任何 run 之前，PR #7） |
| Plant | `walker2d_v5.xml` `sha256:6bed53a6cc3ca73c4fe8ac3486d3b4228927264a6454f4ef16d3eed3c58bc09d`，每個 cell 建環境時對 gymnasium 實際載入的檔案重驗 |
| Environment lock | `lock-2026-09-08-second-case-execution.json` `sha256:911b436231c8e0b1d7a3d07bca6894ce4c42c517c4a5cbbbdd0f9dff694ff631`；`locked_sha256` `sha256:93d23a2703adc86a1394eacf5dece8d7229fdf742857f1a271656aa1cfeac72d`（**與 seed-variance 執行時相同**）；`MEASURED / FULL_LOCK / AMBIENT_THREADING_PINNED` |
| Lock 驗證 | 每個 cell 訓練前、評估前各重測一次：20 次驗證，**0 mismatch** |
| Cells | 2 arms × 5 replicates = 10，全部 `COMPLETED`／`COMPLETED` |
| Realized timesteps | 每 cell **精確 301,056**（= requested）；合計 3,010,560 |
| Terminal records | **300**（10 × 30 seeds 41000–41029） |
| Method failure | **0**（`NONFINITE` 0、訓練／評估 exception 0） |
| 訓練 wall time | 295.2–312.1 s／cell（單 env、CPU、1 thread） |
| 執行時段 | 14:36:10Z – 15:28:03Z |

### 2.1 保留的證據

| 檔案 | bytes | sha256 |
|---|---:|---|
| `backend/second_case_evidence/2026-09-08/bundle/raw_replicates.json` | 252,626 | `0e9ceaf9a4c4defbe568e4849db48f5dfb2782c0c21b69a0039a36bca7bc143b` |
| `…/bundle/second_case_exposure_protocol.json` | 9,066 | `45d1ec553a1124fd613f90a8034b27f10ef8f01f23a219cca216479fc4c5350c` |
| `…/bundle/environment_lock.json` | 4,232 | `911b436231c8e0b1d7a3d07bca6894ce4c42c517c4a5cbbbdd0f9dff694ff631` |
| `…/analysis/second_case_summary.json` | 17,746 | `e6761b78644b0807bc18bf3791de679e2ebebb359d130d3d672ac063285d47ee` |
| `…/analysis/second_case_receipt.json` | 1,890 | `3ceb8d1b20f435f327f5a6d201be7da86951d4ace93611cb2ee199ef3facd744` |

[RESULT] `python -I -S` replay（isolated、no site、零第三方模組載入）由 raw + protocol 重算 summary，**bytes 一致**。`test_second_case_exposure_contract.py::test_retained_development_evidence_revalidates_and_replays_exactly` 以測試固定此事。

[BLOCKER] 300 個 per-episode NPZ trace 與 10 個 `policy.zip` 位於 gitignored `backend/rl/artifacts/second_case/2026-09-08/runs/`，**不在版控內**；每個 trace 的 `trace_sha256` 與每個 policy 的 `policy_sha256` 保留在 `raw_replicates.json`。這是依 [REPOSITORY_GUIDE](REPOSITORY_GUIDE.md) 的 artifact policy 所做的選擇，並且與 v4 warm start 遺失的情況**不同**：本回條的每一個主張都只依賴 raw JSON 中的 counts，不依賴 trace 或 checkpoint；沒有任何下游訓練以這些 checkpoint 為起點。風險仍在：若要對 trace 做本回條以外的分析，需要這台機器上的檔案。

## 3. 實測結果

### 3.1 Exposure

| Replicate | `W2D_A_DIRECT` full／early | realized steps min／med／max | `W2D_C_FILTERED` full／early | realized steps min／med／max |
|---|---|---|---|---|
| r0 | 0／30 | 164／179／194 | 0／30 | 303／313／374 |
| r1 | 0／30 | 254／267／278 | 0／30 | 226／241／254 |
| r2 | **4**／26 | 346／376／1000 | 0／30 | 252／257／266 |
| r3 | 0／30 | 152／178／207 | 0／30 | 342／373／445 |
| r4 | 0／30 | 183／200／228 | **12**／18 | 324／911／1000 |

[RESULT] 300 個 episode 中 **284 個 EARLY_TERMINATED、16 個 FULL_EXPOSURE**。**P1 成立**：5/5 replicates 至少一臂 censored（凍結門檻 ≥ 3）。
[RESULT] **P3 成立**：284 個 early-terminated episode 的 `outcome_state` **全為 `OBSERVED`**——每個 numeric 都有限、算術上正常。`OBSERVED ⇏ full exposure` 在第二個 plant 上重現。
[RESULT] Reference arm（`alpha = 1.0`）在 5 個 replicate 中 4 個是 30/30 早跌，median 178–376 steps（1.4–3.0 s of 8.0 s）。**這是本回條最重要的邊界條件**（§6）。

### 3.2 Per-replicate contrast（`W2D_C_FILTERED − W2D_A_DIRECT`，pp）

| Replicate | naive paired diff | naive sign | identification bound | bound sign | 同意？ |
|---|---:|---|---|---|---|
| r0 | −18.557872 | NEGATIVE | `[−83.016666, +67.516666]` | UNIDENTIFIED | 否 |
| r1 | −19.335733 | NEGATIVE | `[−79.067223, +70.272777]` | UNIDENTIFIED | 否 |
| r2 | −22.131946 | NEGATIVE | `[−68.616666, +58.766666]` | UNIDENTIFIED | 否 |
| r3 | −53.055463 | NEGATIVE | `[−89.322222, +55.114445]` | UNIDENTIFIED | 否 |
| r4 | −30.894674 | NEGATIVE | `[−75.567222, +27.896111]` | UNIDENTIFIED | 否 |

Cell-level mean bound（%）：A r0 `[6.500556, 88.667222]`、r1 `[10.920556, 84.250556]`、r2 `[21.630556, 74.727222]`、r3 `[11.582222, 93.582222]`、r4 `[10.033889, 89.873889]`；C r0 `[5.650556, 74.017222]`、r1 `[5.183333, 81.193333]`、r2 `[6.110556, 80.397222]`、r3 `[4.260000, 66.696667]`、r4 `[14.306667, 37.930000]`。Naive cell means（%）：A 36.44／40.93／45.89／64.39／49.67；C 17.88／21.59／23.76／11.33／18.78。所有 10 個 cell 皆 `PARTIALLY_IDENTIFIED`，level SD 無定義。

### 3.3 Method level（analysis unit = training replicate，n = 5）

| Estimator | 結果 |
|---|---|
| **Naive per-step rate** | mean `−28.795138` pp，SD `14.419184` pp，95% t-interval（df 4，t 2.776445）`[−46.698919, −10.891357]` pp → **asserts NEGATIVE** |
| **Identification bound θ** | `[−79.118, +55.913333]` pp，width `135.031333` pp → **UNIDENTIFIED**，0/5 replicates sign-identified |
| Between-replicate SD | `null`（`BLOCKED_PARTIALLY_IDENTIFIED_REPLICATE_DIFFERENCES`） |
| `naive_versus_bound` | **`NAIVE_ASSERTS_DIRECTION_BOUND_CONTAINS_ZERO`** |
| **Outcome（凍結規則）** | **`SECOND_CASE_ARTIFACT_REPRODUCED`** |

[INFERENCE] 若只看 naive，這份資料會被寫成「一階 low-pass（α=0.25）使 Walker2d PPO 的 actuator saturation duty 降低約 29 個百分點，95% CI 排除 0」。Bound 說：在**未被觀察到的 65–80% horizon** 上，兩臂的 saturation 可以是任何值，這個方向沒有被資料識別。這正是 v7 上 V7C 的同一種錯誤，換了 plant、換了 policy 家族、沒有任何專案控制程式碼。

[RESULT] 引理「naive 恆落在 bound 內」在 300/300 episode 與 10/10 cell 成立（由 contract 的 SC-03 重算與 `test_exposure_identification` 斷言）。

## 4. 沒有主張什麼

- **不主張 `W2D_C_FILTERED` 比 `W2D_A_DIRECT` 好或差。** `direction_claim_permitted = false`。5 個 naive 差全為負這件事本身也不是證據——正是本回條要說的。
- 不主張 Walker2d 行走品質、low-pass filter 的設計價值、v7 humanoid 的任何新結論、physical actuator。
- 不主張 preregistration。protocol 是在 v7 結果已知後寫的，屬 internal hash freeze。
- `paper_data_ready`、`statistics_ready`、`method_level_power_ready` 皆不變（false）。

## 5. 凍結前後的自我核對

- [RESULT] 所有門檻、seeds、budget、alpha、預測皆在 `b683ddc`（14:3x Z）凍結，第一個 run 於 14:36:10Z 開始，**中間沒有任何 amendment**。
- [RESULT] 沒有 override：runner 的 CLI 不接受 budget／seed／alpha／threshold；`test_runner_has_no_override_flags` 斷言原始碼中沒有這些旗標。
- [RESULT] 沒有 selection：只有最終 checkpoint，沒有 checkpoint 挑選；沒有 episode 被刪、沒有 interval 被補值。
- [RESULT] 我在第一個 cell 完成後（14:41Z）就看到 reference 30/30 早跌，並在 PR／對話中先行揭露這對 P2 的結構性後果；分析程式與 protocol 在此之後**未被更動**（source pre == post 於每一 cell）。

## 6. 為什麼 `PUB-A1` 仍未 PASS（保留發現）

[BLOCKER] **兩臂皆重度 censored。** 只有 16/300 episode 跑完 horizon；reference 本身在 4/5 replicate 是 30/30 早跌。當 reference 只實現 ~18–38% 的 horizon 時，其 bound 寬達 53–82 pp，paired bound 必然含 0——**與 candidate 是什麼無關**。所以本案例證明的是「兩臂皆 censored 時，naive 會偽造一個 bound 不支持的方向」；它**沒有**重現 v7 的關鍵形狀：reference 近乎 full exposure、只有 candidate 被 censored、bound 因此**只在一側**變寬。後者才是審稿人會問「你的 bound 是不是永遠無資訊」時的回答。

[INFERENCE] 這不是 protocol 的錯誤，而是 budget 選擇的後果：`301,056` steps 的 Walker2d PPO 尚未學會站穩。凍結時我預期「至少一臂會 censored」，沒有預期「reference 幾乎全部 censored」。這點如實記錄。

[BLOCKER] 依 spec §3.3，**不得**回頭調 budget 重跑當同一 protocol。正確的下一步是凍結 **V2**：

1. budget 提高到 reference arm 在 DEV seeds 上達到**事先凍結**的 full-exposure 比例（例如 ≥ 27/30）——這個比例要在看 V2 資料前寫死；
2. 允許先以 reference arm 做一次 budget 探測（單臂、單 seed），並把探測記錄為 V2 的 pilot，**不得**把探測資料當 V2 evidence；
3. 其餘設計（arms、seeds 禁區規則、estimands、P1/P2、五個 label）沿用 V1，seeds 換新區段。

V1 的結果保留為 Track A 的一個**邊界案例**：它顯示 bound 在對稱 censoring 下的行為（正確地無資訊），而 v7 顯示不對稱 censoring 下的行為（單側變寬）。兩者一起比單一案例更完整地描述這個 estimator；但要通過 `PUB-A1`，需要 V2 給出第二個不對稱案例。

## 7. 對上游文件的影響

- [PUBLICATION_PLAN](PUBLICATION_PLAN.md) `PUB-A1`：`EXECUTED — SECOND_CASE_ARTIFACT_REPRODUCED`，gate 未 PASS，下一步 V2。
- `STATUS.yaml`：新增 `second_case_exposure_status`／`second_case_exposure_receipt`。
- Track A 主張 A-C1／A-C2：獲得第二個 plant 上的機制證據與 `OBSERVED ⇏ full exposure` 證據；generalizability 的**完整**支持仍待 V2。
- 工程：無任何 contract、protocol、training driver 或 threshold 被更動。
