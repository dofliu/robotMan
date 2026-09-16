# 訓練策略文獻地圖（RQ2：什麼方法讓機器人走得更好）

搜尋截點：2026-09-16 ｜ 原文核對：**無，一篇都沒有**（見 §0）
性質：scoped rapid scan，不是 systematic review
目的：回答一個決策問題——[PROJECT_ASSESSMENT §1.4](PROJECT_ASSESSMENT_2026-09-16.md) 的診斷
（「綁住結果的是獎勵形塑結構，不是預算也不是懲罰量值」）**是不是新的**？
若是，`RESEARCH_EXECUTION_PLAN` 的 `RQ2` 值得開一條 V3 訓練線；若不是，就不值得。

## 0. 本次 scan 的核實限制（必讀）

[BLOCKER] 本次 scan 在遠端執行環境完成。**egress 條件與 2026-09-08、2026-09-10 的 `PUB-A0` scan 完全相同**：
`WebSearch` 可用，出版方 host 全部封鎖。本次實測被拒的 host：`arxiv.org`、`discovery.ucl.ac.uk`、
`www.alphaxiv.org`、`pmc.ncbi.nlm.nih.gov`（皆回傳 `EGRESS_BLOCKED`）。

因此：**本文件每一條目的內容都只來自搜尋引擎回傳的摘要，沒有任何一篇原文被讀過**，連標題、作者、
年份、venue 與 arXiv 編號都未經核對。依 [LITERATURE_MAP_2026-08-30](LITERATURE_MAP_2026-08-30.md)
的來源政策，本文件**全部條目不符合 [SOURCE] 標準**，一律標 `U`。

[BLOCKER] 特別注意：搜尋引擎回傳的若干 arXiv 編號（`2601.*`、`2603.*`、`2605.*`、`2607.*`、`2608.*`）
落在最近數月，**這些編號與其對應內容都未經核對**，不排除摘要有誤植或拼接。§3 的 gap 判定**不依賴
任何單一條目**，而是依賴「多個獨立查詢一致指向同一批既有工作」這個型態——但該判定仍為 `[INFERENCE]`。

## 1. 與 RQ2 直接相關的研究群

### 1.1 「站著不動」是 locomotion RL 的已知局部最優

| 核實 | 年份 | 研究 | 搜尋摘要所述內容 | 與本專案的關係 |
|---|---:|---|---|---|
| U | 2020 | *Learning to Locomote: Understanding How Environment Design Matters for Deep RL*；[arXiv 2010.04304](https://arxiv.org/abs/2010.04304) | survival bonus 過大時，演算法會**壓榨 survival bonus 而忽略其他獎勵項**，產生「會平衡但從不跨步」的角色；過小與過大分別導向前撲與站立不動兩個局部最優。以 PyBullet 預設值 1 對照 0 與 5 做 ablation。 | **這就是 §1.4 的現象，而且已被具名、被 ablate。** 本專案十個 replicate 的「站好、在轉換點跌倒」是同一個局部最優。**[BLOCKER] 本條目已在 [LITERATURE_MAP_2026-09-08 §1.1](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md) 引用過**，當時只取其「termination rule 是設計變數」的面向，未注意到它的 survival-bonus ablation 正是本專案後來獨立撞上的東西。 |
| U | 2019 | *Visualizing Movement Control Optimization Landscapes*；[arXiv 1909.07869](https://arxiv.org/abs/1909.07869) | 終止本身會造出局部最優（趨向終止以避免累積成本）；加 termination penalty 或 alive bonus 可使 landscape 明顯較凸。 | 與 §1.4 的算術論證同一件事的 landscape 版本。本專案的貢獻若存在，不會在「發現這個現象」。 |
| U | 2017 | *Emergence of Locomotion Behaviours in Rich Environments*；[arXiv 1707.02286](https://arxiv.org/abs/1707.02286) | 獎勵工程可達成 locomotion，但**脆弱**：獎勵稍改結果就可能大不同。 | 支持「形塑結構是主要變數」，但這是 2017 年就有的共識。 |

### 1.2 從行走狀態起步 = Reference State Initialization（本專案 Arm B 的先前技術）

| 核實 | 年份 | 研究 | 搜尋摘要所述內容 | 與本專案的關係 |
|---|---:|---|---|---|
| U | 2018 | Peng et al., *DeepMimic*, SIGGRAPH；[arXiv 1804.02717](https://arxiv.org/abs/1804.02717) | **Reference State Initialization (RSI)** 與 **Early Termination (ET)** 是訓練程序中**最重要的兩個元件**。RSI 從整段參考動作均勻抽樣起始狀態，提供多個進入點，讓 agent 能「從成功結果往回學」。論文含 ablation：有／無 RSI、有／無 ET。 | **本專案 §5 選項二的「以 v5 行走 checkpoint 當 curriculum 起點」在結構上就是 RSI**，而 RSI 自 2018 年起就是標準做法且已被 ablate 證明必要。這條把 Arm B 的新穎性關掉。 |
| U | 2019 | *Self-Imitation Learning of Locomotion Movements through Termination Curriculum*, ACM SIGGRAPH MIG；[arXiv 1907.11842](https://arxiv.org/abs/1907.11842)、[DOI 10.1145/3359566.3360072](https://dx.doi.org/10.1145/3359566.3360072) | 以 **termination curriculum** 搭配 self-imitation 學 locomotion。 | 「用終止條件排課程」也已有專門工作。 |
| U | 2023 | *DecAP: Decaying Action Priors for Accelerated Imitation Learning of Torque-Based Legged Locomotion*；[arXiv 2310.05714](https://arxiv.org/abs/2310.05714) | 以**遞減的 action prior** 加速 legged locomotion 的模仿學習。 | 「先給先驗、再逐步撤掉」這個模式也已被佔。 |

### 1.3 分階段／相位條件的形塑（本專案 Arm C 的先前技術）

| 核實 | 年份 | 研究 | 搜尋摘要所述內容 | 與本專案的關係 |
|---|---:|---|---|---|
| U | 2025 | *Gait-Conditioned Reinforcement Learning with Multi-Phase Curriculum for Humanoid Locomotion*, IEEE Humanoids；[arXiv 2505.20619](https://arxiv.org/abs/2505.20619) | **同時訓練所有步態會造成 reward conflict 與不穩定探索**，故採多階段 curriculum 逐步引入步態模式。Phase 1 低速行走、**Phase 2 加入站立與 walk-to-stand 轉換**、Phase 3 跑步與 run-to-walk。以 one-hot gait ID 做 **reward routing** 動態啟用該步態的目標，降低 reward interference。**真機 Unitree G1 驗證**。 | **這是 Arm C 的完整版，而且做到真機。** 本專案想測的「`START` 期間降 imitation 權重、升進度權重」是它 reward routing 的一個特例。連「為什麼需要分階段」的理由（reward conflict）都與 §1.4 的診斷同一套說法。 |
| U | 2026 | *Decoupling Task and Behavior: A Two-Stage Reward Curriculum in RL for Robotics*；[arXiv 2603.05113](https://arxiv.org/abs/2603.05113) | 比較三種權重向量 annealing schedule：瞬時切換、線性內插、cosine annealing；討論突變會造成 Q 值大幅位移而不穩，過長則浪費算力。 | **連「權重怎麼排程」的設計空間都已被系統性比較過。** |
| U | — | 模仿／任務獎勵加權 `ω^I + ω^T = 1` 的標準寫法（多篇） | 模仿獎勵與任務獎勵以互補權重混合。 | 本專案的 `r_imitate` / `r_vel` 結構屬此標準族。 |

### 1.4 終止懲罰的量值不是主要槓桿

| 核實 | 年份 | 研究 | 搜尋摘要所述內容 | 與本專案的關係 |
|---|---:|---|---|---|
| U | 2024 | *CaT: Constraints as Terminations for Legged Locomotion RL*；[arXiv 2403.18765](https://arxiv.org/abs/2403.18765) | 以終止表達約束，取代手調懲罰項。 | 與本專案 v4「把 −5 加到 −45 仍未治好」的觀察方向一致——**社群已經在往「別調懲罰量值」走**。 |
| U | — | value-bootstrapped termination 對照手調 termination penalty（搜尋摘要，出處未定） | bootstrapped 變體收斂到更高的 time-out 比例且 **seed variance 明顯較低**。 | 若屬實，這正是「懲罰量值不是對的介面」的直接證據，且已有人做。 |

### 1.5 加預算不會脫離形塑造成的局部最優

| 核實 | 年份 | 研究 | 搜尋摘要所述內容 | 與本專案的關係 |
|---|---:|---|---|---|
| U | 2026 | *Walk the PLANC: Physics-Guided RL for Agile Humanoid Locomotion on Constrained Footholds*；[arXiv 2601.06286](https://arxiv.org/abs/2601.06286) | PPO 易陷局部最優；對精確落足點的 locomotion，**從零訓練的最佳化地形太難跨越，policy 一致地塌到局部最優**。 | 與本專案 V1/V2 的「10 個 replicate 全部 0/30」型態相同，且該文同樣以「換方法而非加預算」回應。 |
| U | — | RL 訓練 plateau 與 exploration 極限（多篇，含 LLM 域） | 表現會在數千步後 plateau；「RL 的極限」常只是探索策略的極限。 | 「加步數不解決形塑問題」是社群共識，非新發現。 |

### 1.6 獎勵拆解作為診斷方法

| 核實 | 年份 | 研究 | 搜尋摘要所述內容 | 與本專案的關係 |
|---|---:|---|---|---|
| U | 2022 | *Value Function Decomposition for Iterative Design of RL Agents*；[arXiv 2206.13901](https://arxiv.org/abs/2206.13901) | 為每個獎勵分量學一個分量價值函數，可用來找出偏好的「bug」、**辨識 shaping reward 的影響**、定位最佳化器問題。 | **§1.4 那套「站著每步 2.5 → 125 步 ≈ 310 → 減 50 ≈ 260 → 對上實測 227–232／283–295」的拆解，在方法類別上屬於此族。** 本專案做的是手算靜態版本，該文做的是學習式一般版本。 |
| U | 2019 | *Explainable Reinforcement Learning via Reward Decomposition*, IJCAI XAI workshop | 以獎勵拆解解釋 agent 行為。 | 同上。 |

## 2. 本專案已量測、且與上述文獻交會的事實

這些是 repo 內可重導的量測（見 [V1 receipt](TRACKED_LINEAGE_TRAINING_RECEIPT_2026-09-14.md)、
[V2 receipt](TRACKED_LINEAGE_TRAINING_V2_RECEIPT_2026-09-14.md)、[PROJECT_ASSESSMENT §1.4](PROJECT_ASSESSMENT_2026-09-16.md)）：

1. 10 個 independent training replicate、2 種預算（`2,000,000` 與 realized `4,015,200` 步）、300 個 evaluation episode，**full exposure 一律 `0/30`**。
2. 獎勵拆解：站好 ≈ `2.5`／步 × 125 步 ≈ `310`，減 `−50` 跌倒 ≈ `260`；**實測 V1 `227`–`232`、V2 `283`–`295`**。
3. 加倍預算：獎勵 `+51`–`+66`、平均存活 `+0.145`–`+0.778` s，**曝露完全未動**。
4. v4 曾把跌倒懲罰由 `−5` 提到 `−45`，**未治好**。
5. 全部在 freeze-before-execute 下執行，門檻與上限凍結未動，量測選擇事先宣告。

[INFERENCE] 第 1–4 點合起來，是「形塑結構而非預算或懲罰量值綁住結果」的**一個乾淨的實例**。
第 5 點是它與多數同類報告的差異。

## 3. Gap 判定（`[INFERENCE]`，全部條目未經原文核對）

**判定：RQ2 的 robotics-method 貢獻沒有 gap。不建議為了發表而開 V3 訓練線。**

逐項：

1. **「站著不動是局部最優」——沒有 gap，且已被 ablate。** §1.1 的 2010.04304 明確以 survival bonus 0/1/5 做對照並命名此局部最優。**該文已在本專案自己的文獻地圖裡**（2026-09-08 §1.1）。
2. **Arm B（從行走狀態暖啟動）——沒有 gap。** 它在結構上是 DeepMimic 的 Reference State Initialization，2018 年提出、已 ablate、被廣泛採用。
3. **Arm C（分階段／相位條件形塑）——沒有 gap，且已到真機。** §1.3 的 2505.20619 以 multi-phase curriculum 加 reward routing 處理同一問題，Phase 2 正是站立與 walk-to-stand 轉換，並在 Unitree G1 上驗證。連權重 annealing schedule 的比較都有專文（2603.05113）。
4. **「懲罰量值不是槓桿」——沒有 gap。** §1.4 顯示社群已在用終止表達約束、以 value bootstrapping 取代手調懲罰。
5. **「加預算沒用」——沒有 gap。** §1.5：從零訓練塌進局部最優、加步數不解決，是既有認知。
6. **獎勵拆解診斷——沒有 gap。** §1.6 已有一般化的學習式版本；本專案的手算版本是其特例。

**唯一可能剩下的，很窄，而且不是 robotics 貢獻**：本專案的否定結果是在
**凍結協定、預先宣告量測選擇、10 replicate、上限與門檻不得因結果調整**的條件下取得的。
§1 掃到的 locomotion 工作報告的多半是**成功的**組態；`preregistered negative result in locomotion RL`
這個查詢沒有回到 locomotion 域的直接命中（回到的是 LLM 域的預註冊研究）。

[INFERENCE] 但這是**方法論**主張，不是 robotics 主張——它屬於 Track A 的地盤，不是 RQ2 的。
而且把它當主貢獻很弱：「我們嚴謹地重現了一個已知的失敗模式」不構成一篇 robotics 論文。

## 4. 直接後果

### 4.1 對 `RQ2` 與 V3

- **不建議為了發表開 V3。** §3 的 1–6 點把三個候選槓桿全部關掉了。開 V3 只會得到「用已知方法得到已知結果」。
- [RESULT] 這次 scan 的成本是 9 次查詢；它擋下的是 §5 選項二估計的 **3 小時 × 每個 arm × 5 replicate**，以及一次大概率的退稿。**先查文獻再執行**這條專案自己的紀律，這次直接生效。
- `RESEARCH_EXECUTION_PLAN §2` 的 `RQ2` 建議改記為 **`ANSWERED_BY_LITERATURE_NOT_BY_THIS_PROJECT`**，並指向本文件。此改動需專案負責人確認。

### 4.2 對 Track A

- **不受影響。** Track A 的主張是量測效度（exposure censoring 造成假改善），與 §3 關掉的是不同的東西。
- [INFERENCE] §2 的五點可作 Track A 的**一個 worked example**：訓練策略比較正是 early termination 最兇的場景，
  若不做 censoring 處理，V7C 那種 `−36` pp 假改善就會出現在「哪個訓練策略比較好」的結論裡。
  這是把既有材料換個用途，不需要新實驗。

### 4.3 對教學工具（這次 scan 的意外收穫）

[RESULT] 文獻沒有給論文，但給了**做法**：若目標是讓教學示範裡的機器人會走，
§1.2 的 **RSI** 與 §1.3 的 **multi-phase curriculum** 是已被驗證、且有真機結果的配方。
這是**工程**，成功機率高，且與 `PUB-B2` 無關——不需要任何 gate，不產生新的研究主張。

## 5. 搜尋紀錄

| 查詢 | 主要命中 |
|---|---|
| reinforcement learning locomotion local optimum agent stands still instead of walking reward shaping | 2010.04304、2505.20619、1707.02286、2410.10438 |
| survival bonus alive bonus too large local minimum standing still locomotion DeepMimic reward | 2010.04304（survival bonus 0/1/5 ablation）、1804.02717、1803.07055 |
| termination penalty magnitude ablation bipedal locomotion RL does not escape local optimum | 1909.07869、1907.11842、2403.18765、2403.14864 |
| gait initiation standing to walking transition reinforcement learning humanoid hardest phase curriculum | **2505.20619（IEEE Humanoids，Unitree G1 真機）** |
| reward decomposition diagnosis explain why RL policy converges to degenerate behavior arithmetic return accounting | 2206.13901、Explainable RL via Reward Decomposition、2501.03902 |
| more training steps does not escape reward shaping local optimum RL scaling compute budget locomotion plateau | 2601.06286（PPO 從零塌進局部最優）、1907.11842 |
| DeepMimic reference state initialization early termination ablation necessary learn walking imitation | **1804.02717（RSI／ET 為最重要的兩個元件，含 ablation）**、1907.11842 |
| imitation reward weight annealing schedule curriculum locomotion RL reduce tracking weight increase task reward | 2603.05113（三種 annealing schedule 對照）、2310.05714、2501.14856 |
| preregistered negative result reproducibility report reinforcement learning locomotion failure replicates frozen protocol | **無 locomotion 域直接命中**（回到 LLM 域預註冊研究）——§3 末段那一窄點的弱證據 |

## 6. 若要讓本文件升級為 `[SOURCE]`

需要有出版方存取權的環境（例如校內網路），逐條核對下列**最關鍵的三篇**，任何一篇的內容若與摘要不符，
§3 的對應判定就要重寫：

1. [arXiv 1804.02717](https://arxiv.org/abs/1804.02717)（DeepMimic）——確認 RSI 的定義與 ablation 結論。決定 §3 第 2 點。
2. [arXiv 2505.20619](https://arxiv.org/abs/2505.20619)（Gait-Conditioned Multi-Phase Curriculum）——確認 Phase 2 是否確實涵蓋站立與 walk-to-stand 轉換、reward routing 的機制、真機結果。決定 §3 第 3 點。
3. [arXiv 2010.04304](https://arxiv.org/abs/2010.04304)（Learning to Locomote）——確認 survival bonus ablation 的數值與結論。決定 §3 第 1 點。
