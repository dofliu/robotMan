# 評估效度與可重現性文獻地圖

搜尋截點：2026-09-08；A-C5 補充 scan 2026-09-10（§1.7） ｜ 原文核對：2026-09-09（§4 點名的兩篇關鍵文獻，§7）
性質：scoped rapid scan，不是 systematic review
目的：回答 [PUBLICATION_PLAN](PUBLICATION_PLAN.md) 的 `PUB-A0` —— Track A 想主張的東西，哪些已經有人做了、哪些沒有。

## 0. 本次 scan 的核實限制（必讀）

[BLOCKER] 本次 scan 在遠端執行環境完成，該環境的 egress proxy **封鎖** `arxiv.org`、`proceedings.mlr.press`、`openreview.net`、`dl.acm.org`、`api.semanticscholar.org` 與 `gymnasium.farama.org`。因此在 scan 當日**每一條目的內容都只來自搜尋引擎回傳的摘要，沒有任何一篇原文被讀過**。**2026-09-09 更新**：§4 點名的兩篇關鍵文獻（arXiv 1911.05728、2606.10229）已由專案負責人提供 PDF 全文並逐頁核對，改標 `S`（§7 記錄檔案 digest）；其餘條目仍為 `U`。

依 [LITERATURE_MAP_2026-08-30](LITERATURE_MAP_2026-08-30.md) 的來源政策（只採論文原文、publisher page 或作者官方 page），本文件的條目**尚不符合 [SOURCE] 標準**。每條標注核實程度：

- `U`：unverified —— 只有搜尋摘要；作者、年份、venue 與內容主張都待原文核對。
- `R`：repo 既有引用 —— 已在 [PAPER_DATA_READINESS §7](PAPER_DATA_READINESS.md) 以原文／publisher page 引用過。
- `S`：source-verified —— 原文全文已讀（PDF 由專案負責人提供，digest 記於 §7），內容主張符合 [SOURCE] 標準。

`PUB-A0` 的 exit condition 因此**尚未達成**：§4 的 gap 判定是 `[INFERENCE]`，條件於 §1–§3 的內容經原文核對後仍成立。核對工作需要有出版方存取權的環境（例如校內網路）。2026-09-09 起，§4 第 1、2 點的判定**不再條件於**兩篇關鍵文獻（已核對、gap 仍成立），但仍條件於其餘 `U` 條目。

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
| **S** | 2026 | Bedi, *What Demonstration Curation Metrics Do to Your Policy*，arXiv 2606.10229v1 [cs.RO]，2026-06-08，單一作者 preprint（未經同儕審查）；[arXiv](https://arxiv.org/abs/2606.10229) | [SOURCE] 領域：behavior-cloning 的 demonstration **curation**——LIBERO pick-and-place，人工注入 early-gripper-release 結構性缺陷，80% 污染率。§III-D「Episode-Length Control」：缺陷 demo 跑到 500 步 time limit，成功 demo 約 325 步終止，因此任何以 mean／cumulative trajectory feature 計算的 metric 會部分把 episode length 當 defect label 的 proxy；把所有 demo **截到 `T = 324`**（最短成功長度）後再算 feature，7 個 metric 中 5 個的 detection AUROC 由 ≈1.0 掉到 0.44–0.76（Table I：length 1.000→0.500、isolation forest 1.000→0.440、kNN 1.000→0.712、trajectory alignment 1.000→0.638、smoothness 0.979→0.447、gripper timing 0.957→0.804）。結論：「any curation benchmark must control for episode length before reporting detection accuracy」。下游 policy 以 30 rollouts × 3 seeds 的 task success（mean ± SD across seeds）評估，rollout **未**做任何 exposure 處理，無 bounds。參考文獻無 Manski／partial identification。 | 核對結果：**gap 未縮小。** 共享的是「episode length 系統性差異 → mean／cumulative 指標混入 length」這個 confound 的陳述，且方向相反（該文缺陷 episode 較**長**、成功 episode 較短；本專案失敗 episode 較**短**）。差異：（a）對象是 curation metric 的 detection 效度，不是 policy 的 comparative evaluation；（b）補救是**設計期** common-prefix truncation——丟棄 prefix 之後的資料、要求所有 episode 活到 prefix——不是事後的 identification 分析；（c）全文未討論 policy evaluation 中的 exposure censoring、identification 或 bounds。Track A 引為 confound 的既有陳述與「設計期處置」的對照。 |

### 1.3 Survival／right-censoring 在 RL 與 robotics 中的處理

| 核實 | 年份 | 研究 | 搜尋摘要所述內容 | 與 Track A 的關係 |
|---|---:|---|---|---|
| **S** | 2019 | Leete, Kallus, Hudgens, Napravnik, Kosorok, *Balanced Policy Evaluation and Learning for Right Censored Data*，arXiv 1911.05728v1 [stat.ME]，2019-11-13；[arXiv](https://arxiv.org/abs/1911.05728) | [SOURCE] 情境：多治療、觀察性 HIV 世代（UNC CFAR）的 individualized treatment rule；outcome 為 right-censored 存活時間 `T = min(T̃, τ)`。§2.1 明文假設 **censoring time `C(a)` 在給定 `X, A` 下獨立於 `T(a)`**（conditionally independent censoring），另假設 no unmeasured confounders（Assumption 1）、overlap（Assumptions 4／5）與 survival estimator 的收斂率（Assumption 2）。方法（§2.3–2.4）：以 conditional expected survival time `E[T | X, A, T > C]`（RSF／RIST 估計）**補值**被 censor 的 outcome，得到「estimated fully observed outcome vector」，再套 Kallus (2018) 的 balanced policy weights；比較對象 IPW + IPCW 需 censoring model 正確設定。理論結果為 consistency（Theorem 1）與 **regret／convergence-rate bounds**（Theorem 3），不是 identification bounds。§2.3 引 Fleming & Harrington：不處理 censoring 會有 bias。參考文獻無 Manski／partial identification。 | 核對結果：**gap 未消失。** 該文在 independent-censoring 假設下給**點估計**，且核心操作正是**補值**——Track A 拒絕的兩件事。本專案的 censoring（跌倒→終止）由該臂自身的行為產生，與 outcome 過程不獨立，該假設在此情境下不成立。定位：survival-analysis／off-policy-evaluation 路線處理 right censoring 的代表作，Track A 引為「有假設、點識別」的對照；其「不處理 censoring 會有 bias」的陳述支持 Track A 的動機。 |
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

### 1.7 Preregistration、post-hoc disclosure 與 selection-on-evaluation-data（2026-09-10 補充 scan）

本節為 §4 第 5 點點名的補充 scan。全部條目為 `U`：**同日重新量測，`arxiv.org` 仍被執行環境的 egress proxy 封鎖**（§7），因此內容只來自搜尋引擎摘要。

| 核實 | 年份 | 研究 | 搜尋摘要所述內容 | 與 A-C5 的關係 |
|---|---:|---|---|---|
| U | 2017 | Hollenbeck & Wright, *Harking, Sharking, and Tharking: Making the Case for Post Hoc Analysis of Scientific Data*, **Journal of Management** | 區分 HARKing（把 post hoc 假設當成 a priori 呈現）、**Sharking**（在 Introduction 秘密 HARK）與 **Tharking**（在 Discussion **透明宣告**假設是 post hoc）；主張 Sharking 無正當性，但 Tharking 若透明且有理論支撐可促進科學效率。 | **對 A-C5 最關鍵。** 「公開宣告規則是 post hoc」這一半正是 Tharking，2017 年即已命名並辯護。→ A-C5 的此半**不是**貢獻。 |
| U | 2013/2014 | Gelman & Loken, *The garden of forking paths* | 即使沒有 p-hacking、也沒有 fishing、且假設事先提出，資料相依的分析選擇仍造成隱性多重比較。 | 動機：為何「規則在看過資料後寫成」本身就是問題，與作者是否有意無關。 |
| U | 2011 | Simmons, Nelson & Simonsohn（researcher degrees of freedom 的揭露建議） | 對策聚焦揭露：報告所有 manipulation、measure、data exclusion 與停止規則。 | 本專案四個 disclosure 欄位的更早依據；具體條目待原文核對。 |
| U | 2020 | Rubin, *Does preregistration improve the credibility of research findings?*, TQMP 16(4) 376；[arXiv 2010.10513](https://arxiv.org/abs/2010.10513) | 檢視 preregistration 的可信度主張；指出部分益處**不是** preregistration 的本質特徵（規劃與 results-blind review 在非預註冊研究中也可達成），透明措施可部分替代。 | 直接關係到本專案「internal hash freeze 不是 preregistration」的措辭：核對後可能要求把「較弱的替代品」改寫為「不同機制、部分重疊的保護」。 |
| U | 2020, 2021 | NeurIPS **Pre-registration in Machine Learning** Workshop（[PMLR v148](https://proceedings.mlr.press/v148/)、[v181](https://proceedings.mlr.press/v181/)） | ML 的 preregistration 出版模型：論文不帶實驗結果送審，先審實驗協定、通過後執行。 | ML 已有 preregistration 的制度化管道；本專案**未**使用，稿件必須明說而非只說「沒有 registry」。 |
| U | 2023 | *Pre-registration for Predictive Modeling*；[arXiv 2311.18807](https://arxiv.org/abs/2311.18807) | 主張 model design 過程過於混亂迭代、難以 preregister，但**評估不同**：benchmark 與 baseline 的選擇是離散、可事先枚舉的。 | **與本專案立場一致且應引用**：可 preregister 的是評估與選擇規則，不是訓練探索。這正是本專案凍結 selection rule 而不凍結訓練迭代的理由。 |
| U | 2021 | *Preregistering NLP Research*；[arXiv 2103.06944](https://arxiv.org/abs/2103.06944) | NLP 領域的 preregistration 實作討論。 | 另一個領域先例。 |
| U | 2024 | Leech, Vazquez, Kupper, Yagudin, Aitchison, *Questionable practices in machine learning*；[arXiv 2407.12220](https://arxiv.org/abs/2407.12220) | 編目 **44 項** QRP，偏重公開 benchmark 上的 LLM 評估，並列出「irreproducible research practices」。 | 本專案的 forbidden denominators、fail-closed 契約、`NOT_REACHED ≠ PASS` 可對照其中數條；作為 A-C4 的動機與定位，不是新發現。 |
| U | 2010 | Cawley & Talbot, *On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation*, **JMLR 11** | model selection 的 over-fitting 幅度可與演算法間的效能差異相當；取最大值傾向取到 outlier 而非無偏估計，偏誤隨候選數增加、測試 episode 數減少、內在變異增加而放大。 | **A-C5 「決策資料必須未被檢視」這一半的既有依據**。本專案 sealed FORMAL seeds 的理由已被建立，不是新的。 |
| U | 2015 | Dwork, Feldman, Hardt, Pitassi, Reingold, Roth, *Generalization in Adaptive Data Analysis and Holdout Reuse*（NeurIPS）；*The reusable holdout*, **Science 349** | 適應性地重複使用 holdout 會過擬合 holdout 本身；以差分隱私式加噪給出可重複使用的 holdout。 | 同上。本專案採的是最保守版本：規則**只套用一次**，不重複使用決策資料。 |
| U | 2019 | *Let's Play Again: Variability of Deep Reinforcement Learning Agents in Atari Environments*；[arXiv 1904.06312](https://arxiv.org/abs/1904.06312) | 深度 RL agent 的變異性使單次評估不可靠。 | 支持 replicate-level analysis unit（已由 §1.4 的 Colas 等建立，此處為 RL 端補強）。 |
| U | 2020 | *A Selective Review of Negative Control Methods in Epidemiology* | negative control：對「若設計假設成立則應無關聯」的 outcome 或 setting 套用**主分析**，作為 falsification test。 | **A-C5 剩餘部分的最近鄰居。** A-C5 的自檢在結構上就是 negative-control falsification test，但掃到的文獻把它套在 outcome／假設上，未見套在 **selection rule** 上。 |
| U | 2023 | *Negative Control Falsification Tests for Instrumental Variable Designs*；[arXiv 2312.15624](https://arxiv.org/abs/2312.15624) | 把 negative control 形式化為 IV 設計的 falsification test；並警告 **exogenous 設計也可能因函數形式錯置而失敗**，故通過／失敗的解讀有限制。 | 同上；其警告可直接移植：規則在啟發資料上選不出東西，也**可能只是因為該資料的 exposure 不足**，而不是因為規則保守。此限制必須寫進稿件。 |
| U | 2025 | Semmelrock et al., *Reproducibility in machine-learning-based research: overview, barriers and drivers*, **AI Magazine**；[arXiv 2406.14325](https://arxiv.org/abs/2406.14325) | 綜述 ML 可重現性的障礙與驅動因子；把 preregistration 列為對 HARKing／p-hacking／spin 有效的出版政策驅動因子。 | 背景；支持把本專案的 contract 定位為「把既有建議做成可執行」。 |

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

1. **Exposure censoring 作為 comparative evaluation 的 identification 問題：有 gap——兩篇關鍵文獻核對後仍成立；其餘 `U` 條目待核。** 既有工作在 learning 端處理 termination（Pardo；DERAIL；Survival RL；Arrive and Survive），或在設計期把 exposure 併進指標（survival time、normalized time-to-fall、common-prefix truncation）。**原本可能推翻此判定的兩篇已全文核對（§7）**：[2606.10229](https://arxiv.org/abs/2606.10229) 的 truncation 討論限於 demonstration-curation metric 的 detection 效度，未涉及 policy evaluation，條件「已涵蓋 policy evaluation」不成立，gap **未縮小**；[1911.05728](https://arxiv.org/abs/1911.05728) 在 conditionally independent censoring 假設下以補值得到點估計，其 bounds 是 regret／convergence-rate bounds 而非 identification bounds，條件「無 censoring 假設下給 bounds」不成立，gap **未消失**。兩篇的參考文獻都沒有 Manski 或 partial identification——這是「bounds 路線尚未進入這兩個社群」的弱證據。未見有人對 locomotion policy 的 **comparative evaluation**，把 early termination 視為 rate 型 outcome 的 exposure censoring，報 assumption-free identification bounds、拒絕 complete-case deletion 與 interval 補值、並把 method failure 與 exposure censoring 分開保留。此判定仍為 [INFERENCE]：§1.1、§1.3 其餘條目與 §2 的 Manski／Tamer 線尚未原文核對。
2. **`outcome_state == OBSERVED ⇏ full exposure` 這個記錄層盲點：有 gap（條件同上）。** 掃到的文獻沒有討論「所有 required outcome 都有值、算術上正常，但 exposure 不足」這種資料層失效。核對後最接近的是 2606.10229：它顯示在**完整記錄**的資料上正常計算的 mean／cumulative 指標仍被 length 混入，但它處理的是 metric 定義，不是記錄層旗標與 exposure 的脫鉤，也沒有「由 trace 長度獨立重建 exposure」的檢查。這是可獨立檢查、可移植到其他 pipeline 的貢獻。
3. **Statistical unit 的程式層強制：貢獻邊際。** 文獻已充分建議 run 為單位（Colas ×2、Agarwal、Patterson）；把它做成 forbidden denominators 是 engineering，可作為 artifact 但不宜當主貢獻。
4. **Floating-point reduction-order：不是貢獻。** SC'24 與 RepDL 已完整建立。只能當動機。
5. **Post-hoc rule 的自檢：A-C5 大幅縮小，降為 artifact 級。** 本項的補充 scan 已於 2026-09-10 完成（§1.7、§6）。判定分三段：
   - **「公開宣告規則是 post hoc」不是貢獻。** Hollenbeck & Wright (2017) 已把它命名為 **Tharking** 並提出辯護；Simmons et al. (2011) 的完整揭露建議更早。本專案以 contract 強制 `preregistration.preregistered = false` 與四個 disclosure 欄位，是**工程實作**，不是新的方法論主張。
   - **「決策資料必須是未被檢視過的」不是貢獻。** Cawley & Talbot (2010) 與 Dwork et al. (2015) 已建立 selection-on-evaluation-data 的偏誤方向與量級；本專案的 sealed FORMAL seeds 與「只套用一次」是其最保守版本。
   - **剩餘可能新穎的只有一點，而且很窄**：把「規則套在啟發它的資料上必須選不出東西」當作**規則本身**的 falsification test，並以 fail-closed contract 保留其失敗證據。它在結構上就是 negative-control falsification test，該方法在 epidemiology 與 IV 設計中已建立；掃到的文獻把它套在 outcome 或設計假設上，**未見套在 selection rule 上**。[INFERENCE] 但 arXiv 2312.15624 明確警告 falsification test 的通過／失敗解讀受函數形式等因素混淆，**同樣的混淆適用於本專案**：規則在 DEV 資料上選不出候選，也可能只是因為該資料 exposure 不足（實測擋下 V7B 的正是 `SEL-C2` 的 full-exposure 條件），而不是因為規則保守。這使該自檢的證據力比原本設想的弱。

   **結論：A-C5 從「次貢獻」降為 artifact 級，併入 A-C4，不單獨作為主張。** 稿件應改為：引 Tharking 與 Cawley & Talbot 建立語彙與理由，把本專案的 contract 呈現為既有建議的**可執行化**，並如實寫出上述解讀限制。

## 5. 對 PUBLICATION_PLAN 的直接後果

- `PUB-A0` 狀態：`KEY_TWO_VERIFIED_AND_A_C5_SCANNED / REMAINING_U`（2026-09-10；2026-09-09 為 `KEY_TWO_VERIFIED_GAP_STANDS / REMAINING_U`；scan 當日為 `SCAN_COMPLETE / PRIMARY_SOURCES_UNVERIFIED`）。**仍未通過。** 已完成：§4 點名的兩篇原文核對（§7）、A-C5 的補充 scan（§1.7）。其餘通過條件：§1.1、§1.3–§1.5、§1.7 與 §2 的 `U` 條目逐條改為 `S` 或刪除；把 §4 重寫為非條件式。
- Track A 的主貢獻收斂為 §4 的第 1、第 2 點（加 [TRACK_A_REFRAME](TRACK_A_REFRAME_2026-09-09.md) 的 A-C3）；第 3 點為 artifact；第 4 點降為動機；**第 5 點（A-C5）於 2026-09-10 降為 artifact 級並併入 A-C4**。
- `PUB-A1`（第二案例）的候選：Gymnasium MuJoCo `Humanoid`／`Walker2d` 系列在 `terminate_when_unhealthy` 預設下用 SB3 PPO 做 rate 型指標（例如 control-cost rate、action saturation rate）的有／無 exposure 處理對照。理由：公開、便宜、early termination 是預設行為，且與本專案的 stack 相同。**後續**：已凍結並執行為 Walker2d-v5 V1（`PUB-A1a` PASS）；V2／Hopper 線於 2026-09-09 依決定關閉，見 [PUBLICATION_PLAN](PUBLICATION_PLAN.md) V2 與 [TRACK_A_REFRAME](TRACK_A_REFRAME_2026-09-09.md)。

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
| **以下為 2026-09-10 的 A-C5 補充 scan** | |
| preregistration machine learning research practice adoption barriers | 2406.14325、2311.18807、2407.12220、NeurIPS pre-registration workshop |
| multiverse analysis specification curve robustness reporting | specification curve／multiverse 工具與視覺化（R `multiverse`、RobustiPy）；無 policy-evaluation 應用 |
| HARKing garden of forking paths post hoc hypothesis disclosure requirement | Hollenbeck & Wright 2017（Tharking）、Gelman & Loken、Simmons et al. |
| adaptive data analysis reusable holdout overfitting test set Dwork | 1506.02629、Science 349、1905.10360 |
| negative control falsification test analysis pipeline must fail sanity check causal inference | 2312.15624、Negative Control Methods in Epidemiology review、2210.00528 |
| arXiv 2407.12220 questionable practices in machine learning | 44 項 QRP，作者 Leech 等 |
| THARKing transparently hypothesizing after results known Hollenbeck Wright | Journal of Management 2017、2010.10513 |
| preregistration reinforcement learning empirical evaluation NeurIPS preregistration workshop | PMLR v148、v181、2311.18807、2103.06944 |
| checkpoint selection bias reinforcement learning evaluation model selection inflates reported performance | Cawley & Talbot JMLR 11、1904.06312 |
| "specification search" preregister model selection rule ML benchmark evaluation protocol | 無直接命中（只回到 2311.18807 與 benchmark-lottery 討論） |
| does preregistration improve credibility of research findings limitations critique | Rubin TQMP 16(4)、2010.10513、2103.06944 |
| decision rule validated by showing it selects nothing on exploratory data self-check | **無命中** —— 這是 A-C5 剩餘那一窄點尚無先例的弱證據 |

## 7. 原文核對紀錄

| 日期 | 文獻 | 來源檔 | SHA-256 | 頁數 | 讀法 | 判定 |
|---|---|---|---|---:|---|---|
| 2026-09-09 | arXiv 1911.05728v1（Leete et al.） | 專案負責人上傳的 PDF `1911.05728v1.pdf` | `6266d181da26b06a65bedc6837d00bd1366b622f1ab9b5e604d01998fd538f85` | 29（含 4 頁 supplement） | 全文文字抽出（pypdf）並逐頁讀完；引用的假設與定理對照 §2.1、§2.3–2.4、§3 | 條件「無 censoring 假設下給 bounds」**不成立**：conditionally independent censoring + imputation → 點估計；bounds 為 regret／rate |
| 2026-09-09 | arXiv 2606.10229v1（Bedi） | 專案負責人上傳的 PDF `2606.10229v1.pdf` | `b94078567a89bb5042a71c25828bf41ef036edc3e0b8316f56f16ea9fd6510be` | 5 | 全文文字抽出（pypdf）並逐頁讀完；Table I／II 數字對照 §III-D、§V | 條件「truncation 討論涵蓋 policy evaluation」**不成立**：對象為 curation metric 的 detection 效度；下游 policy evaluation 未處理 exposure |

[RESULT] 兩篇的內容摘要（§1.2、§1.3）已依原文改寫；scan 當日的搜尋摘要對兩篇的描述在方向上正確，但都遺漏了決定性的細節（1911.05728 的 independent-censoring 假設與補值操作；2606.10229 的 curation 而非 evaluation 定位）。
[BLOCKER] 其餘 `U` 條目仍未核對；執行環境對出版方 host 的封鎖不變。`PUB-A0` 未通過。
[RESULT] **2026-09-10 重新量測 egress**：`WebFetch` 對 `https://arxiv.org/abs/2311.18807` 回傳 `EGRESS_BLOCKED`（`Access to arxiv.org is blocked by the network egress proxy`）。搜尋引擎（`WebSearch`）可用，出版方 host 不可用——與 2026-09-08 的 scan 條件相同。因此 §1.7 的 A-C5 補充 scan 全數為 `U`。
[RESULT] A-C5 的補充 scan 於 2026-09-10 完成（§1.7、§6 的第二段查詢表）。判定寫在 §4 第 5 點：A-C5 **降為 artifact 級並併入 A-C4**——「透明宣告 post hoc」是 Hollenbeck & Wright (2017) 的 Tharking，「決策資料未被檢視」是 Cawley & Talbot (2010) 與 Dwork et al. (2015) 已建立的事，剩下的只有「把 falsification test 套在 selection rule 上」這一窄點，且其解讀受 exposure 不足的混淆。這是**縮小**可宣稱範圍。
