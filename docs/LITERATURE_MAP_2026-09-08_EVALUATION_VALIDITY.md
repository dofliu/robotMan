# 評估效度與可重現性文獻地圖

搜尋截點：2026-09-08
性質：scoped rapid scan，不是 systematic review
目的：回答 [PUBLICATION_PLAN](PUBLICATION_PLAN.md) 的 `PUB-A0` —— Track A 想主張的東西，哪些已經有人做了、哪些沒有。

## 0. 本次 scan 的核實限制（必讀）

[BLOCKER] 本次 scan 在遠端執行環境完成，該環境的 egress proxy **封鎖** `arxiv.org`、`proceedings.mlr.press`、`openreview.net`、`dl.acm.org`、`api.semanticscholar.org` 與 `gymnasium.farama.org`。因此**每一條目的內容都只來自搜尋引擎回傳的摘要，沒有任何一篇原文被讀過**。

依 [LITERATURE_MAP_2026-08-30](LITERATURE_MAP_2026-08-30.md) 的來源政策（只採論文原文、publisher page 或作者官方 page），本文件的條目**尚不符合 [SOURCE] 標準**。每條標注核實程度：

- `U`：unverified —— 只有搜尋摘要；作者、年份、venue 與內容主張都待原文核對。
- `R`：repo 既有引用 —— 已在 [PAPER_DATA_READINESS §7](PAPER_DATA_READINESS.md) 以原文／publisher page 引用過。

`PUB-A0` 的 exit condition 因此**尚未達成**：§4 的 gap 判定是 `[INFERENCE]`，條件於 §1–§3 的內容經原文核對後仍成立。核對工作需要有出版方存取權的環境（例如校內網路）。

## 1. 與 Track A 直接相關的研究群

### 1.1 Early termination／truncation 的語義與學習正確性

| 核實 | 年份 | 研究 | 搜尋摘要所述內容 | 與 Track A 的關係 |
|---|---:|---|---|---|
| U | 2018 | Pardo, Tavakoli, Kormushev, *Time Limits in Reinforcement Learning*, ICML（PMLR v80）；[arXiv 1712.00378](https://arxiv.org/abs/1712.00378) | 區分 environment termination 與 time-limit truncation；time limit 屬環境時應把剩餘時間放進 observation 以維持 Markov property；不屬環境時應在 truncation 處 bootstrap（partial-episode bootstrapping）。 | 是 termination／truncation 區分的標準出處，但關切的是 **learning correctness**（Bellman update），不是 **evaluation／reporting validity**。Track A 引為語義基礎，不與之競爭。 |
| U | — | Gymnasium `Env.step` 的 `terminated`／`truncated` 官方定義；[docs](https://gymnasium.farama.org/api/env/) | API 層把兩者分開回傳。 | 本專案的 exposure audit 由 trace 長度重建終止，不依賴 driver 的 flag；原文待核。 |
| U | 2020 | *DERAIL: Diagnostic Environments for Reward And Imitation Learning*；[arXiv 2012.01365](https://arxiv.org/abs/2012.01365) | 實作若把 terminal state 的價值錯設為零，會依 reward 符號偏向提早或延長 episode，使某些任務的表現被高估。 | 同樣是 **learning 端**的 termination bias；機制與 Track A 的量測端 censoring 不同，可作對照。 |
| U | 2020 | *Learning to Locomote: Understanding How Environment Design Matters for Deep RL*；[arXiv 2010.04304](https://arxiv.org/abs/2010.04304) | 環境設計選擇（含 termination conditions）改變 locomotion 學習結果。 | 支持「termination rule 是設計變數」；未涉及量測端的 identification。 |

### 1.2 Episode length 作為 metric confound

| 核實 | 年份 | 研究 | 搜尋摘要所述內容 | 與 Track A 的關係 |
|---|---:|---|---|---|
| U | 2026 | *What Demonstration Curation Metrics Do to Your Policy*；[arXiv 2606.10229](https://arxiv.org/abs/2606.10229) | 任何以 mean／cumulative features 計算的 metric 會部分利用 episode length 作為 proxy；提出把所有 demonstration **截到共同長度 prefix** 再算 metric，以移除 episode length 這個 confound。 | **最接近 Track A 的既有工作。** 但（a）領域是 imitation learning 的 demonstration curation，不是 policy 比較；（b）補救是**設計期**的 common-prefix truncation —— 它丟棄 prefix 之後的資料、要求所有 episode 都活到 prefix，且本身是一種對「未觀察區間」的處置選擇，不是事後的 identification 分析。Track A 的差異：對已產生的資料給出 assumption-free bounds，不丟資料、不補值。**原文必讀。** |

### 1.3 Survival／right-censoring 在 RL 與 robotics 中的處理

| 核實 | 年份 | 研究 | 搜尋摘要所述內容 | 與 Track A 的關係 |
|---|---:|---|---|---|
| U | 2019 | *Balanced Policy Evaluation and Learning for Right Censored Data*；[arXiv 1911.05728](https://arxiv.org/abs/1911.05728) | Off-policy evaluation／learning 在 outcome 被 right-censored 時的方法，採 survival-analysis 式框架。 | **方法論上最近的鄰居。** 若其在 censoring mechanism 上做假設（如 independent censoring）以得到**點估計**，則與 Track A 的「拒絕點估計、只報 sharp bounds」互補而非重疊。**原文必讀**，這是 novelty 判定的關鍵。 |
| U | 2026 | *Survival Reinforcement Learning: Toward Scalable Self-Supervised RL*；[arXiv 2605.31273](https://arxiv.org/abs/2605.31273) | 以 observed 與 right-censored trajectories 的 MLE 為**學習目標**；在 locomotion／navigation／manipulation 任務上評估。 | Censoring 進入 objective，不是進入 comparative evaluation 的效度分析。 |
| U | 2026 | *Arrive and Survive: Scaling Safe Goal-Conditioned Policy Learning from One-Bit Failure Signals*；[arXiv 2608.26571](https://arxiv.org/abs/2608.26571) | 修正 short surviving futures 的 overweighting；12 個 failure-prone navigation／locomotion 任務。 | 同上：learning 端。 |
| U | 2026 | *OSCAR: Obstacle Survival Curves for Adaptive Robot Navigation*；[arXiv 2606.00990](https://arxiv.org/abs/2606.00990) | 每 episode 更新 Kaplan–Meier 估計，用於 navigation 適應。 | Survival estimator 作為 controller 的一部分；不是 evaluation validity。 |
| U | 2022 | *Saving the Limping: Fault-tolerant Quadruped Locomotion via RL*；[arXiv 2210.00474](https://arxiv.org/abs/2210.00474) | 以 survival time 的 mean／25th／50th percentile 為評估指標。 | 顯示 locomotion 文獻慣用 survival time 當**主指標**；但沒有處理「其他 rate 型指標在 censored episode 上被偽造」的問題。 |

[INFERENCE] 搜尋摘要另顯示 legged locomotion 文獻常見兩種處置：以 normalized time-to-fall 為指標，或以 survived percentage 縮放 tracking error。兩者都是**把 exposure 併入指標定義**的設計期做法，與 Track A「保留原指標、對 exposure 不足的 episode 給 bounds」不同。此段無法歸屬到特定論文，待原文核對。

### 1.4 Statistical unit、seeds 與 reporting

| 核實 | 年份 | 研究 | 搜尋摘要所述內容 | 與 Track A 的關係 |
|---|---:|---|---|---|
| R | 2018 | Henderson et al., *Deep RL That Matters*, AAAI | 單一 seed 與點估計不足。 | 既有引用；動機。 |
| U | 2018 | Colas, Sigaud, Oudeyer, *How Many Random Seeds? Statistical Power Analysis in Deep RL Experiments*；[arXiv 1806.08295](https://arxiv.org/abs/1806.08295) | 對 t-test 與 bootstrap CI 給出所需 seed 數的 power 分析指引。 | Track B 的 sample-size 決策應引用；Track A 引為「statistical unit = training run」的出處之一。 |
| U | 2019 | Colas, Sigaud, Oudeyer, *A Hitchhiker's Guide to Statistical Comparisons of RL Algorithms*；[arXiv 1904.06979](https://arxiv.org/abs/1904.06979) | 一個 run 是一次獨立訓練；run 的分數是訓練後多個 evaluation episodes 的平均；比較的單位是 run。 | 明確支持本專案的 **forbidden denominators**（episode 數不得作分母）。 |
| R | 2021 | Agarwal et al., *Deep RL at the Edge of the Statistical Precipice*, NeurIPS | 少量 runs 下的 interval 與 run-distribution reporting。 | 既有引用。 |
| U | 2023 | *AdaStop: adaptive statistical testing for sound comparisons of Deep RL agents*；[arXiv 2306.10882](https://arxiv.org/abs/2306.10882) | 序貫式、自適應的 seed 數決定與比較檢定。 | Track B 可考慮；與 Track A 無直接重疊。 |
| R | 2024 | Patterson et al., *Empirical Design in RL*, JMLR | paired comparison、interval、seed 不是 hyperparameter。 | 既有引用。 |
| U | 2024 | *Robot Learning as an Empirical Science: Best Practices for Policy Evaluation*；[arXiv 2409.09491](https://arxiv.org/abs/2409.09491) | 報 CI 與 raw k/n；初始條件對 success rate 的影響；不同 policy 用不同初始條件會誤判。 | 支持 paired evaluation seeds；未見 exposure censoring 的討論（待核）。 |
| U | — | *RE-EVALUATE: Reproducibility in Evaluating RL Algorithms*；[OpenReview](https://openreview.net/pdf?id=HJgAmITcgm) | RL 演算法評估的可重現性問題。 | 待核；可能是 evaluation-protocol 標準化的相關出處。 |

### 1.5 數值可重現性

| 核實 | 年份 | 研究 | 搜尋摘要所述內容 | 與 Track A 的關係 |
|---|---:|---|---|---|
| U | 2024 | *Impacts of floating-point non-associativity on reproducibility for HPC and deep learning applications*, SC'24 Workshops；[arXiv 2408.05148](https://arxiv.org/abs/2408.05148) | Floating-point 加法不具結合律，reduction 順序改變結果；DL pipeline 對此極度敏感，妨礙認證、robustness 評估與除錯。 | **本專案的 reduction-order 發現（`7.485470860550343` vs `7.485470860550345`）不是新發現。** Track A 應把它定位為**動機與最小可重現案例**，不是貢獻。 |
| U | 2025 | *RepDL: Bit-level Reproducible Deep Learning Training and Inference*；[arXiv 2510.09180](https://arxiv.org/abs/2510.09180) | 以 correct rounding 與 order invariance 達成跨 CPU/GPU bitwise 一致。 | 同上；可作為「若要 bitwise 重現該怎麼做」的指引。 |

### 1.6 Method failure 與 missing data

| 核實 | 年份 | 研究 | 內容 | 關係 |
|---|---:|---|---|---|
| R | 2025 | Wünsch et al., *Statistics in Medicine* | comparison study 的 method failure 不應 silent deletion 或以一般 missing-data imputation 處理。 | 既有引用；本專案「method failure 與 exposure censoring 分開保留」的依據。 |

## 2. Partial identification 的方法出處

| 核實 | 研究 | 關係 |
|---|---|---|
| U | Manski (1990) worst-case／no-assumption bounds；Manski & Pepper (2000) monotone IV；Tamer (2010) *Partial Identification in Econometrics* review | 本專案 exposure audit 的 full-horizon bound（`[已觀察部分的貢獻, 已觀察部分 + 未觀察區間全為 1]`）就是對 bounded outcome 的 Manski 型 bound。Track A 需要正確引用這條線，並說明本專案只用了其中最弱的版本（無 monotonicity、無 IV）。 |
| U | *Predictive Performance Comparison of Decision Policies Under Confounding*；[arXiv 2404.00848](https://arxiv.org/abs/2404.00848) | 在 confounding 下用 partial identification 比較 decision policies —— 顯示「用 bounds 做 policy 比較」在 ML 社群已有先例，但情境是 confounding 而非 exposure censoring。 |

## 3. 本專案已量測、且與上述文獻交會的事實

| 事實 | 出處 |
|---|---|
| V7C 30/30 early termination 於 horizon 的 `0.354889`；full-horizon bound `[0.0, 64.511111]`% 與 V7A `36.2185185`% 重疊；paired bound 含 0 | [frozen bundle receipt](V7_EXPOSURE_CENSORING_AUDIT_FROZEN_BUNDLE_RECEIPT_2026-09-08.md) |
| V7B 3 個 censored episode 的 `outcome_state == OBSERVED` 且六項 numeric 齊全 | 同上 |
| 跨 5 個 independent training seeds，V7C 的崩潰 150/150 重現；V7B 方向 5/5 可識別但 variance 不可估 | [execution receipt](TRAINING_SEED_VARIANCE_EXECUTION_RECEIPT_2026-09-08.md) |
| 同環境同資料兩種 IEEE-conformant reduction order 給不同結果 | [environment lock receipt](ENVIRONMENT_LOCK_IMPLEMENTATION_RECEIPT_2026-09-08.md) |
| 分母 `150`／`450` 為 enforced forbidden denominators | [TRAINING_SEED_VARIANCE_SPEC](TRAINING_SEED_VARIANCE_SPEC.md) |

## 4. Gap 判定（[INFERENCE]，條件於 §1–§2 經原文核對後仍成立）

1. **Exposure censoring 作為 comparative evaluation 的 identification 問題：暫定有 gap。** 既有工作在 learning 端處理 termination（Pardo；DERAIL；Survival RL；Arrive and Survive），或在設計期把 exposure 併進指標（survival time、normalized time-to-fall、common-prefix truncation）。未見有人對 locomotion policy 的 **comparative evaluation**，把 early termination 視為 rate 型 outcome 的 exposure censoring，報 assumption-free identification bounds、拒絕 complete-case deletion 與 interval 補值、並把 method failure 與 exposure censoring 分開保留。**最需要核對的兩篇**：[2606.10229](https://arxiv.org/abs/2606.10229)（若其 truncation 討論已涵蓋 policy evaluation，gap 縮小）與 [1911.05728](https://arxiv.org/abs/1911.05728)（若其在無 censoring 假設下給 bounds，gap 消失）。
2. **`outcome_state == OBSERVED ⇏ full exposure` 這個記錄層盲點：暫定有 gap。** 掃到的文獻沒有討論「所有 required outcome 都有值、算術上正常，但 exposure 不足」這種資料層失效。這是可獨立檢查、可移植到其他 pipeline 的貢獻。
3. **Statistical unit 的程式層強制：貢獻邊際。** 文獻已充分建議 run 為單位（Colas ×2、Agarwal、Patterson）；把它做成 forbidden denominators 是 engineering，可作為 artifact 但不宜當主貢獻。
4. **Floating-point reduction-order：不是貢獻。** SC'24 與 RepDL 已完整建立。只能當動機。
5. **Post-hoc rule 在啟發資料上必須失敗的自檢：定位不明。** 未搜尋 preregistration／multiverse 文獻；在寫作前需另做一次 scan（COS、Nosek 等）。

## 5. 對 PUBLICATION_PLAN 的直接後果

- `PUB-A0` 狀態：`SCAN_COMPLETE / PRIMARY_SOURCES_UNVERIFIED`。**未通過。** 通過條件：在可存取出版方的環境讀完 §4 點名的兩篇與 §1.2–§1.4 的 U 條目，逐條把 `U` 改為 `[SOURCE]` 或刪除，並重寫 §4。
- Track A 的主貢獻應收斂為 §4 的第 1 與第 2 點；第 3 點為 artifact；第 4 點降為動機。
- `PUB-A1`（第二案例）的候選：Gymnasium MuJoCo `Humanoid`／`Walker2d` 系列在 `terminate_when_unhealthy` 預設下用 SB3 PPO 做 rate 型指標（例如 control-cost rate、action saturation rate）的有／無 exposure 處理對照。理由：公開、便宜、early termination 是預設行為，且與本專案的 stack 相同。**尚未凍結。**

## 6. 搜尋紀錄

| 查詢 | 主要命中 |
|---|---|
| early termination bias RL evaluation per-step metrics episode length confound | 2012.01365、2606.10229、1712.00378 |
| partial identification bounds Manski censored outcomes ML evaluation | Tamer review、2404.00848、Manski 原文 |
| Pardo Time Limits termination truncation | 1712.00378、PMLR v80、2010.04304 |
| legged locomotion early fall metrics normalized survived steps | 2210.00474、2306.03286、2408.00776 |
| floating point summation order reproducibility | 2408.05148、2510.09180 |
| RL evaluation pseudo-replication statistical unit training seed | 1904.06979、2108.13264、HJgAmITcgm、2305.15284 |
| survival analysis RL locomotion right-censored | 2605.31273、2608.26571、2606.00990、1911.05728 |
| success rate conditional on survival reporting guidelines robotics | 2409.09491、TRI blog |
| worst-case bounds early terminated episodes partial identification | 無直接命中（只回到 Pardo 與 Manski）—— 這本身是 gap 的弱證據 |
| Colas How Many Random Seeds | 1806.08295、2306.10882 |
