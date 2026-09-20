# 訓練策略文獻地圖（RQ2：什麼方法讓機器人走得更好）

搜尋截點：2026-09-16 ｜ 原文核對：**2026-09-16，四篇**（`2010.04304`、`1804.02717`、`1712.00378`、`2505.20619`，見 §7）；其餘條目仍為 `U`
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

[RESULT] **2026-09-16 更新**：專案負責人提供四篇 PDF 全文，已逐篇核對並記於 §7。§3 判定所依賴的三篇（`2010.04304`、`1804.02717`、`2505.20619`）全部核完，其中兩篇**確認**、一篇（`2505.20619`）使原判定**被更正、且必須收窄**（§1.3、§3 第 3 點）。另核 `1712.00378`（Pardo），它屬 [LITERATURE_MAP_2026-09-08 §1.1](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md) 的 `U` 條目，本次一併升為 `S`。**§3 的總判定在更正後仍然成立**，但支撐點已改變。

[BLOCKER] 特別注意：搜尋引擎回傳的若干 arXiv 編號（`2601.*`、`2603.*`、`2605.*`、`2607.*`、`2608.*`）
落在最近數月，**這些編號與其對應內容都未經核對**，不排除摘要有誤植或拼接。§3 的 gap 判定**不依賴
任何單一條目**，而是依賴「多個獨立查詢一致指向同一批既有工作」這個型態——但該判定仍為 `[INFERENCE]`。

## 1. 與 RQ2 直接相關的研究群

### 1.1 「站著不動」是 locomotion RL 的已知局部最優

| 核實 | 年份 | 研究 | 搜尋摘要所述內容 | 與本專案的關係 |
|---|---:|---|---|---|
| **S** | 2020 | Reda, Tao, van de Panne, *Learning to Locomote: Understanding How Environment Design Matters for Deep RL*, UBC；[arXiv 2010.04304](https://arxiv.org/abs/2010.04304)（**2026-09-16 原文核對，§7**） | **§9 原文**：以 TD3 在 `Walker2DBulletEnv` 上對 survival bonus `0`／`1`／`5` 做 ablation，測試時一律移除該項以求公平；原文結論句為「If the survival bonus term is too large, however, the algorithm exploits the survival bonus reward while neglecting other reward terms. This results in a character that balances but never steps forward.」，Summary 為「Values that are too small or too large leads to local minima corresponding to falling-forward and standing still, respectively.」，並把此現象上溯至 Henderson et al. 2018 與 Mania et al. 2018。survival bonus 過大時，演算法會**壓榨 survival bonus 而忽略其他獎勵項**，產生「會平衡但從不跨步」的角色；過小與過大分別導向前撲與站立不動兩個局部最優。以 PyBullet 預設值 1 對照 0 與 5 做 ablation。 | **這就是 §1.4 的現象，而且已被具名、被 ablate。** 本專案十個 replicate 的「站好、在轉換點跌倒」是同一個局部最優。**[BLOCKER] 本條目已在 [LITERATURE_MAP_2026-09-08 §1.1](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md) 引用過**，當時只取其「termination rule 是設計變數」的面向，未注意到它的 survival-bonus ablation 正是本專案後來獨立撞上的東西。 |
| U | 2019 | *Visualizing Movement Control Optimization Landscapes*；[arXiv 1909.07869](https://arxiv.org/abs/1909.07869) | 終止本身會造出局部最優（趨向終止以避免累積成本）；加 termination penalty 或 alive bonus 可使 landscape 明顯較凸。 | 與 §1.4 的算術論證同一件事的 landscape 版本。本專案的貢獻若存在，不會在「發現這個現象」。 |
| U | 2017 | *Emergence of Locomotion Behaviours in Rich Environments*；[arXiv 1707.02286](https://arxiv.org/abs/1707.02286) | 獎勵工程可達成 locomotion，但**脆弱**：獎勵稍改結果就可能大不同。 | 支持「形塑結構是主要變數」，但這是 2017 年就有的共識。 |

### 1.2 從行走狀態起步 = Reference State Initialization（本專案 Arm B 的先前技術）

| 核實 | 年份 | 研究 | 搜尋摘要所述內容 | 與本專案的關係 |
|---|---:|---|---|---|
| **S** | 2018 | Peng, Abbeel, Levine, van de Panne, *DeepMimic*, SIGGRAPH；[arXiv 1804.02717](https://arxiv.org/abs/1804.02717)（**2026-09-16 原文核對，§7**） | **§10.4 原文**：RSI 與 ET 是「two of the most important components of our training procedure」，對照組為有／無 RSI、有／無 ET（無 ET 時每 episode 跑滿 20 s）。ET 的機制寫明是「helps to **eliminate local optima**, such as those where the character falls and mimes the motions as it lies on the ground」。**§6.1 對 RSI 的理由，結構上與本專案的困境相同**：以 backflip 為例，「for the character to be motivated to perform such a jump, it must be aware that the jump will lead to states that yield higher rewards… the agent is unlikely to encounter states from a successful flip, and never discover such high reward states」；RSI 即由參考動作沿線抽樣起始狀態，讓 agent 直接遇到那些高報酬狀態。 | **本專案 §5 選項二的「以 v5 行走 checkpoint 當 curriculum 起點」在結構上就是 RSI**，而 RSI 自 2018 年起已 ablate 證明必要。**核對後這條比原本更強**：把 backflip 換成 steady walk，§6.1 那段話就是 [PROJECT_ASSESSMENT §1.4](PROJECT_ASSESSMENT_2026-09-16.md) 的診斷。另可記：RSI 的原形是**沿參考軌跡抽樣起始狀態**，比本專案原本設想的「從 v5 checkpoint 暖啟動」更直接可用，因為本專案已有參考軌跡（`r_imitate`）。 |
| U | 2019 | *Self-Imitation Learning of Locomotion Movements through Termination Curriculum*, ACM SIGGRAPH MIG；[arXiv 1907.11842](https://arxiv.org/abs/1907.11842)、[DOI 10.1145/3359566.3360072](https://dx.doi.org/10.1145/3359566.3360072) | 以 **termination curriculum** 搭配 self-imitation 學 locomotion。 | 「用終止條件排課程」也已有專門工作。 |
| U | 2023 | *DecAP: Decaying Action Priors for Accelerated Imitation Learning of Torque-Based Legged Locomotion*；[arXiv 2310.05714](https://arxiv.org/abs/2310.05714) | 以**遞減的 action prior** 加速 legged locomotion 的模仿學習。 | 「先給先驗、再逐步撤掉」這個模式也已被佔。 |

### 1.3 分階段／相位條件的形塑（本專案 Arm C 的先前技術）

| 核實 | 年份 | 研究 | 搜尋摘要所述內容 | 與本專案的關係 |
|---|---:|---|---|---|
| **S** | 2025 | Peng, Bao, Zhou, *Gait-Conditioned Reinforcement Learning with Multi-Phase Curriculum for Humanoid Locomotion*；[arXiv 2505.20619](https://arxiv.org/abs/2505.20619)（**2026-09-16 原文核對，§7**） | **原文**：以 one-hot gait ID 做 **reward routing** 與 gait mask，降低 reward interference；三階段 curriculum —— **Phase 1 只訓練走路**（gait ID 固定為 `Walk`）、**Phase 2 加入 `Stand` 與 `W2S`（walk-to-stand）**、Phase 3 加入 `Run` 與 `R2W`（run-to-walk）。五個 mode 為 `Stand`／`Walk`／`Run`／`W2S`／`R2W`。真機為 Unitree G1，驗證項目是「standing, walking, and walk-to-stand transitions」。 | **[BLOCKER] 本欄 2026-09-16 原文核對後更正，原判定過強，更正如下。** 原寫「這是 Arm C 的完整版，而且做到真機」——**該文沒有 stand-to-walk（`S2W`）這個 mode，五個 mode 裡的兩個轉換 `W2S` 與 `R2W` 都是減速方向**；它的 Phase 1 直接把 gait ID 固定為 `Walk` 訓練走路，**因此從來不需要解決「從站立起步」**——而那正是本專案 `START → STEADY_WALK` 卡住的地方。此文確立的是「分階段 curriculum 與 reward routing 可降低 reward interference」，**不是**「起步轉換已被解決」。關掉 Arm C 新穎性的論據因此改掛在 §1.2（RSI）與 §1.1（survival bonus ablation）上，不再掛在本條；本條退為「相位條件形塑本身是既有技術」。 |
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

這些是 repo 內可重導的量測（見 [V1 receipt](archive/TRACKED_LINEAGE_TRAINING_RECEIPT_2026-09-14.md)、
[V2 receipt](archive/TRACKED_LINEAGE_TRAINING_V2_RECEIPT_2026-09-14.md)、[PROJECT_ASSESSMENT §1.4](PROJECT_ASSESSMENT_2026-09-16.md)）：

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

1. **「站著不動是局部最優」——沒有 gap，且已被 ablate。（2026-09-16 原文核對，判定不變）** §1.1 的 2010.04304 明確以 survival bonus 0/1/5 做對照並命名此局部最優。**該文已在本專案自己的文獻地圖裡**（2026-09-08 §1.1）。
2. **Arm B（從行走狀態暖啟動）——沒有 gap。（2026-09-16 原文核對，判定不變且**更強**）** 它在結構上是 DeepMimic 的 Reference State Initialization，2018 年提出、已 ablate、被廣泛採用。
3. **Arm C（分階段／相位條件形塑）——沒有 gap，但本點的論據於 2026-09-16 原文核對後更正並收窄。** **[BLOCKER] 原文為**「沒有 gap，且已到真機。§1.3 的 2505.20619 以 multi-phase curriculum 加 reward routing 處理同一問題，Phase 2 正是站立與 walk-to-stand 轉換，並在 Unitree G1 上驗證。」——**「處理同一問題」是錯的**：該文的兩個轉換 `W2S`、`R2W` **都是減速方向，沒有 stand-to-walk**，且其 Phase 1 直接固定 gait ID 為 `Walk` 訓練走路，**從未面對從站立起步的問題**。它確立的是「分階段 curriculum 與 reward routing 降低 reward interference」，這仍使「相位條件形塑」本身不具新穎性（再加 2603.05113 已系統比較權重 annealing schedule），**但它不是本專案起步問題的解答**。本點的「沒有 gap」因此改由第 1、2 點承擔——起步型局部最優已被具名 ablate（§1.1，已核對），而其標準解法 RSI 已於 2018 年 ablate 證明必要（§1.2，已核對）。
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

## 7. 原文核對紀錄（2026-09-16）

專案負責人提供四篇 PDF 全文。抽取方式：`pypdf`（本容器的 `cryptography` rust binding 損毀，
以 stub 繞過該相依後可用；PDF 未加密，不影響抽取），逐頁讀完。

| 文獻 | 來源檔 | SHA-256 | 頁數 | 判定 |
|---|---|---|---:|---|
| `arXiv 2010.04304v1`（Reda, Tao, van de Panne） | `0c5bfb04-2010.04304v1.pdf` | `d928ecfb902a96e6cfad66c53814004c2d56b5128853a4ac7098b8279c07ac2e` | 9 | **確認**。§9 以 TD3 對 survival bonus `0`／`1`／`5` ablation；「balances but never steps forward」為原文；Summary 明言過小與過大分別導向前撲與站立不動兩個局部最優；上溯 Henderson 2018、Mania 2018。§3 第 1 點**不變** |
| `arXiv 1804.02717v3`（Peng, Abbeel, Levine, van de Panne） | `757da173-1804.02717v3.pdf` | `4bd4cc353bd2dc19da99bb21a254cbfdb9840e49940ce69d484eb6d45bfa348f` | 18 | **確認且更強**。§10.4 RSI／ET 為「two of the most important components」並含 ablation；§6.1 的 backflip 論證與本專案 `START → STEADY_WALK` 結構同形。§3 第 2 點**不變** |
| `arXiv 2505.20619v3`（Peng, Bao, Zhou） | `b35d05e2-2505.20619v3.pdf` | `574f17417361f58a25c47e1a3f4b3de1bd53c6d20bd4059ceb9eea6d30c1764d` | 9 | **更正原判定**。五個 mode 為 `Stand`／`Walk`／`Run`／`W2S`／`R2W`，**無 stand-to-walk**；Phase 1 直接以 gait ID = `Walk` 訓練走路。§1.3 與 §3 第 3 點已就地更正並收窄 |
| `arXiv 1712.00378v4`（Pardo, Tavakoli, Levdik, Kormushev） | `28a512a9-1712.00378v4.pdf` | `5bb677ee1a3d6916aedf7d6df74463238cfe792fc348976502f46c14998067c6` | 10 | **確認**（本篇屬 [2026-09-08 文獻地圖 §1.1](LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md)）。全文處理 time-limit 的 Markov 性與 bootstrapping，即 **learning correctness**；無 censoring、無 comparative evaluation 的 identification 討論。該地圖對它的定性**不變** |

[RESULT] **搜尋摘要的方向大致正確，但在一篇上遺漏了決定性細節**——與 2026-09-09 核對 `1911.05728`／`2606.10229` 時的型態相同：
摘要說 `2505.20619` 的 Phase 2 涵蓋「standing and walk-to-stand transitions」，這句話本身沒錯，
錯在我據此推論它「處理同一問題」，而沒有注意到**該文沒有反方向的 stand-to-walk**。
原判定留在原地並標記更正，不刪除。

[RESULT] **對總判定的淨效果**：§3 的「RQ2 的 robotics-method 貢獻沒有 gap」**仍然成立**，
但支撐從三點縮為兩點，且這兩點現在都是 `S` 級：起步型局部最優已被具名 ablate（`2010.04304`），
其標準解法 RSI 已 ablate 證明必要（`1804.02717`）。§1.4–§1.6 的條目仍為 `U`。

[RESULT] **一個對 Track A 有利的副產品**：[TRACK_A_REFRAME §3.7](TRACK_A_REFRAME_2026-09-09.md) 的 A-C3 補強論據
（「落進 R4 是可預期的，因為該失敗模式已具名、已 ablate」）原本條件於 `U` 條目，
**現在條件於已核對的 `2010.04304`**，等級由 `U` 升為 `S`。

[BLOCKER] 一個應記下的方法論觀察：`1804.02717` §10.4 自承「Due to the time needed to train each policy,
the majority of performance statistics are collected from **one run** of the training process」——
即該 ablation 多數為 `n = 1`。這不影響「RSI 是既有技術」的判定（其概念已被廣泛採用），
但它本身正是 Track A 關於 statistical unit 與 replicate 的論點的一個實例，稿件若引用可如實註明。

## 6. 尚未核對的條目（§1.4–§1.6）

§3 判定所依賴的三篇已於 2026-09-16 核對完畢（§7）。**仍未核對**的是 §1.4–§1.6 的條目——終止懲罰量值、加預算無效、獎勵拆解診斷這三組。它們支撐的是 §3 第 4–6 點，而那三點目前**不是**總判定的承重點（總判定已由第 1、2 點承擔），因此優先度較低。原本列為優先的三篇即：

1. [arXiv 1804.02717](https://arxiv.org/abs/1804.02717)（DeepMimic）——確認 RSI 的定義與 ablation 結論。決定 §3 第 2 點。
2. [arXiv 2505.20619](https://arxiv.org/abs/2505.20619)（Gait-Conditioned Multi-Phase Curriculum）——確認 Phase 2 是否確實涵蓋站立與 walk-to-stand 轉換、reward routing 的機制、真機結果。決定 §3 第 3 點。
3. [arXiv 2010.04304](https://arxiv.org/abs/2010.04304)（Learning to Locomote）——確認 survival bonus ablation 的數值與結論。決定 §3 第 1 點。
