# Humanoid Control / Training 近期文獻地圖

搜尋截點：2026-08-30  
性質：scoped rapid scan，不是 systematic review  
來源政策：只採論文原文、conference/publisher page 或作者官方 project/source page。

## 1. 與本專案直接相關的研究群

| 年份 | 研究 | 方法與證據 | 對本專案的可用啟發 | 不可直接移植的 claim |
|---:|---|---|---|---|
| 2026 | [Booster Lab](https://arxiv.org/abs/2606.27813) | motion data curation、real-to-sim adaptation、AMP RL；Booster T1 與初步 K1 外部實驗 | 後續 motion primitive 的資料治理與 feasible-motion filtering | 本專案目前沒有對應 real-to-sim 或硬體資料 |
| 2025 | [Learning Sim-to-Real Humanoid Locomotion in 15 Minutes](https://arxiv.org/abs/2512.01996) | FastSAC/FastTD3、大量 parallel simulation、domain randomization；G1/T1 實機 | Study B 可加入 off-policy sample-efficiency baseline | 訓練時間與 sim-to-real 結果依賴其 simulator、GPU、robot 與完整 recipe |
| 2025 | [ResMimic](https://arxiv.org/abs/2510.05070) | general motion tracking base + residual policy；simulation 與 Unitree G1 | 支持「base skill + residual task refinement」研究主線 | loco-manipulation 結果不能當成本專案 locomotion evidence |
| 2025 | [ASAP](https://arxiv.org/abs/2502.01143) | simulation policy + real rollout + delta action model，再回 simulator fine-tune；跨 simulator 與 G1 | 外部資料到位後可建立 dynamics residual calibration track | 沒有真實 rollout 時不能聲稱已做 physics alignment |
| 2025 | [Booster Gym](https://arxiv.org/abs/2506.15132) | training-to-deployment framework、reward、domain randomization、parallel structures；T1 實機 | 借鑑 deployment contract 與 end-to-end artifact lineage | framework 可運行不等於本專案模型已驗證 |
| 2025 | [RL-augmented Adaptive MPC](https://arxiv.org/abs/2509.18466) | RL 調整 simplified-dynamics MPC、swing controller 與 gait frequency；IsaacLab simulation | 可形成 MPC/WBC 與 RL 分工的 hybrid baseline | 目前來源只支持其指定 simulation terrain 結果 |
| 2024 | [HOVER](https://arxiv.org/abs/2410.21229) | full-body kinematic imitation 作共同 abstraction，多控制模式 distillation | 支持將舉手、抬腳、行走等 primitive 先建立共同 motion representation | 多模式能力需 motion data、retargeting 與對應 robot evidence |
| 2024 | [Humanoid-Gym](https://arxiv.org/abs/2404.05695) | Isaac Gym training、Isaac→MuJoCo sim-to-sim、XBot 實機 zero-shot transfer | P3 可加入跨 engine replay，檢查 simulator-specific policy | sim-to-sim robustness 不能取代本專案 V1 或硬體 validation |
| 2024 | [RL-augmented MPC for bipedal footstep control](https://arxiv.org/abs/2407.17683) | ALIP-MPC foot placement + learned refinement；DRACO 3 experiments | 支持用 learning 補 simplified-model gap，而非完全取代 controller | 其硬體、MPC formulation 與 footstep results 不能直接外推 |
| 2024 | [Generic dynamic locomotion across discrete terrains](https://arxiv.org/abs/2405.17227) | high-level RL policy + MPC/WBIC；三種 humanoid dynamic simulation | 提供 sample-efficient hierarchical hybrid 對照方向 | 尚不能作為本專案實機或 constraint validation 證據 |
| 2024 | [Real-world humanoid locomotion with reinforcement learning](https://hybrid-robotics.berkeley.edu/publications/ScienceRobotics2024_Learning_Humanoid_Locomotion.pdf) | Digit 大型實驗與 simulator/hardware transfer | 比較 training variability、hardware-aware observation 與 external evaluation 架構 | Digit 的硬體與模型結果不能外推至目前 12-DoF prototype |

## 2. 方法路線判讀

### A. 純 RL locomotion

可比較 PPO、FastSAC 與 FastTD3，但第一篇研究不應一次擴張太多演算法。現階段先把 PPO observation、task gate、multi-seed 與 failure retention 做完整；off-policy 方法放入後續 sample-efficiency study。

### B. Motion imitation / multi-skill

HOVER、ResMimic 與 Booster Lab 都顯示 motion representation、feasible data 與 skill consolidation 是多動作的重要路線。對應本專案的順序應是：

```text
primitive task contract
→ robot-feasible reference / retargeting
→ imitation policy
→ task or residual refinement
→ frozen transition evaluation
```

因此舉手、單腳抬起、蹲下等動作不能只有 UI command；每個動作需要 reference、contact schedule、success metrics 與 transition criteria。

### C. Residual / hybrid control

ASAP 與 ResMimic 的共同訊息是：保留一個能提供結構或基本技能的 base，再學 residual correction。對本專案最合理的研究版本是：

```text
verified WBC torque
  + bounded RL residual torque
  → actuator / contact safety projection
```

這個方向要等 V1 constraint oracle 與 WBC baseline 完成，否則 residual 是否改善 constraint compliance 無法判讀。

### D. Dynamics mismatch 與跨 simulator

Humanoid-Gym 的 sim-to-sim、ASAP 的 real-to-sim residual 都值得納入，但兩者回答不同問題：

- 跨 simulator：檢查 policy 是否過度依賴單一 engine implementation。
- 實體 residual：使用外部量測修正 simulation-real mismatch。

兩者都不能替代 equations/contact/numerical V1 verification。

## 3. 對第一篇研究的建議定位

暫定題目方向：

`Verification-aware training of start–walk–stop humanoid locomotion: observability, curriculum and hybrid residual control`

可能貢獻仍以假設表示：

- `[HYPOTHESIS]` realized-task evaluator 能揭露 training return 與真實 task criteria 間的 reward/evaluation gap。
- `[HYPOTHESIS]` path-observable state 可降低 command-only policy 的 heading/lateral drift。
- `[HYPOTHESIS]` WBC + bounded residual PPO 比 pure PPO 有較好的 constraint compliance 與 robustness。
- `[HYPOTHESIS]` failure-retaining、paired、multi-seed protocol 能提高 humanoid controller comparison 的可重現性。

Novelty 必須在正式投稿前以完整 literature review 再確認；本 rapid scan 只用於工程路線與第一版研究問題凍結。

## 4. 下一輪文獻工作

1. 建立 paper-level evidence extraction：robot、DoF、simulator、control rate、action type、observation、reward、randomization、training seeds、evaluation trials、hardware evidence。
2. 針對 WBC + residual RL、humanoid benchmark statistics、model V&V 與 actuator/contact identification 做第二輪檢索。
3. 將每篇方法映射至本專案可重現的 experiment cell；缺少實作或 evidence 的欄位保留 unknown。
4. 正式 Study A 前完成 related-work claim map，避免把 framework demo、simulation result 與 hardware validation 混在一起。
