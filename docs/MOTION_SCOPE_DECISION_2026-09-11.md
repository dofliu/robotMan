# 動作任務範圍決定：現在不新增跳躍／轉身

日期：2026-09-11 ｜ ID：`MOTION-SCOPE-DECISION-2026-09-11` ｜ 決定者：專案負責人

狀態：`DECIDED / NO_NEW_MOTION_TASK / R0_PROBE_OPENED`

證據等級：本文件是**決策紀錄**，不是 evidence。沒有新增任何訓練、評估、profile、protocol 或 seed。

---

## 0. 決定

專案負責人於 2026-09-11 詢問是否現在加入更多動作模擬（跳躍、轉身或其他基本動作），並在聽取下述量測依據後**採納建議：現在不新增**，改為依 [ROADMAP §9](ROADMAP.md) 的既有順序推進，並開啟唯一對學術軌道有直接幫助的那個版本——`R0` regime probe（[R0_REGIME_PROBE_SPEC](R0_REGIME_PROBE_SPEC.md)）。

---

## 1. 四個理由（全部是量到的事實）

### 1.1 現有的唯一任務尚未通過

[SOURCE] Motion Task V1（`stand → start → steady walk → stop`）在 v5 的 `run-20260830t055847-rl_task_v5-b6c4781d` 為 **Live 10/11 criteria**，唯一失敗是 saturation duty `38.422222% > 30%`。門檻未放寬。v6 的 reward-only 對照證明單純加入 500 Hz saturation reward 不足；v7 三臂 protocol 結束時 `selected_candidate_arm_id = null`。

[INFERENCE] 在此狀態下新增第二、第三個任務，是把「未通過的任務數」由 1 變成 3，不會使既有任務更接近通過，也不會增加任何 gate 的通過數。

### 1.2 跳躍正好落在 plant credibility 最未驗證之處

[SOURCE] V1 gate 目前四項全缺：articulated dynamic、known pendulum、energy balance、solver／finite-difference convergence（[VV_PLAN](VV_PLAN.md)、[ROADMAP §9 第 4 項](ROADMAP.md)）。現有 V1 證據只有 static double-support 與 passive single-support analytical fixture，皆非 articulated dynamic。

[INFERENCE] 走路大部分時間維持接觸、能量交換平緩；**跳躍的整段飛行相（無接觸）、落地衝擊（接觸模型與恢復係數）與能量守恆**恰好是那四項未驗證項目所涵蓋的物理。在未驗證的 plant 上量跳躍，得到的不是關於跳躍的證據，而是關於未驗證接觸模型的證據——且此類錯誤無法事後以分析補救。

### 1.3 它使 Track A 更難，不是更容易

[SOURCE] Track A 目前缺的是一個「reference 曝露充分且 metric 非退化」的設定；三個 budget probe（Walker2d ×2、Hopper ×1）皆未找到（[SECOND_CASE_V2_BUDGET_PROBE_RECEIPT](SECOND_CASE_V2_BUDGET_PROBE_RECEIPT_2026-09-08.md)）。

[INFERENCE] 轉身與跳躍的早期終止率高於走路，只會把更多比較推入 `R3`／`R4` regime——bound 更寬、含 0、方向不可識別。對一個以 exposure censoring 為論點的研究而言，加入更難的任務降低而非提高可得結論。

### 1.4 現在加動作會複製已發生過的 provenance 損毀

[SOURCE] v7 的 warm start 來自 gitignored `backend/rl/artifacts/` 下的 v4 local artifact，v3/v4 已不存在於 repo 或磁碟，因此 `CONDITIONAL_ON_FIXED_WARM_START` 對整條 v7 line **永久成立**（[infeasibility receipt](V7_PRETRAINING_SEED_VARIANCE_INFEASIBILITY_RECEIPT_2026-09-08.md)）。

[INFERENCE] 在版控 checkpoint lineage 建立之前新增訓練線，只會再產出一批同樣不可重建的 artifact。先修管線再加任務，成本低於先加任務再回頭補管線。

### 1.5 專案既有規則已寫了一半答案

[SOURCE] [RL_POLICY_TRAINING](RL_POLICY_TRAINING.md)：「Multi-speed policy、turn、terrain 與其他 primitive 仍需另立 profile/protocol version，不可改 label 冒充。」
[SOURCE] [ROADMAP §8](ROADMAP.md)：「完成此 task framework 後，再以 registry 新增舉手、抬腳、深蹲與原地轉身。抬腳等平衡動作必須定義 contact/support acceptance，不能只新增視覺動畫。」

本決定與這兩條既有規則一致，不是新增限制。

---

## 2. 凍結的順序

| 順位 | 項目 | 前置 |
|---|---|---|
| 1 | [ROADMAP §9 第 1 項](ROADMAP.md)：`ENVIRONMENT-LOCK-V1` 的 lock record 綁進每一條 pipeline 的 run manifest | 無（V0 具名 blocker） |
| 2 | [ROADMAP §9 第 2 項](ROADMAP.md)：有版控 checkpoint lineage 的新訓練線 | 無；同時是 Track B 的硬前置 |
| 3 | **原地轉身**作為第二個動作任務 | 第 2 項，且 reference policy 達到 `PUB-B2` 的出口條件（DEV seeds 上達到事先凍結的 full-exposure 比例） |
| 4 | **跳躍** | 第 3 項，且 V1 gate 的 articulated dynamic、pendulum、energy、solver convergence 皆 PASS |

[INFERENCE] 第 3 項選轉身而非跳躍，理由是轉身與走路共用同一組接觸假設、沒有飛行相、且能重用既有的 phase／acceptance 框架；它對 V1 的依賴遠低於跳躍。

---

## 3. 兩個不受本決定阻擋的例外

### 3.1 教學展示（Track C）

舉手、抬腳、深蹲等可作為教學支線隨時進行，但：

- 必須標示 `DEVELOPMENT_ONLY / NOT_EVIDENCE`，不得進入任何 V&V 或 PDR gate 的證據鏈；
- 依 [ROADMAP §8](ROADMAP.md)，抬腳這類平衡動作必須定義 contact/support acceptance，不得只新增視覺動畫；
- 不得與 Motion Task V1 的 11 項 criteria 混用或比較。

### 3.2 `R0` regime probe（**本次開啟**）

[INFERENCE] 若目的是替 Track A 補 taxonomy 的空格，正確方向是找**更簡單**的比較，不是更難的。`R0`（兩臂皆 full exposure、點識別）是 [TRACK_A_REFRAME §3](TRACK_A_REFRAME_2026-09-09.md) 六格中唯一標為「未觀察到」的一格。

[RESULT] 本次調查發現該格**不需要新增任何動作任務**即可探測：retained 的 450 個 seed-variance evaluation episode，其 `control_step_trace` 每個 control step 都記有 `saturation_substeps_over_threshold` 與 `saturation_substeps_total`（10 substeps = 500 Hz），因此任意截斷 horizon 的 saturation duty 皆可**精確重算**。在全 horizon（450 control steps）上，重算值與凍結的 `metrics.saturation_duty_pct` 對 30/30 episode 完全相等。

規格見 [R0_REGIME_PROBE_SPEC](R0_REGIME_PROBE_SPEC.md)（`R0-REGIME-HORIZON-PROBE-V1`，`FROZEN_BEFORE_EXECUTION`）。

[BLOCKER] 該 probe 依賴的 trace 只存在於 **gitignored** 的 `backend/rl/artifacts/`，而執行環境是可回收容器。若容器被回收，這批 trace 與其 `policy.zip` 將永久消失，且因 warm start 不可重建而無法重跑復原——與毀掉 v7 provenance 的機制完全相同。因此該規格的執行第一步是把分析所需的最小充分統計量抽出並納入版本控制，而不是搜尋。

---

## 4. 沒有改變的事

`paper_data_ready`、`statistics_ready`、`method_level_power_ready`、`sample_size_decision_input_ready` 皆為 false 不變。沒有新增或修改任何 profile、protocol、contract、門檻、arm 定義、seed 或測試。Motion Task V1 的 11 項 criteria 與其保留的失敗結果不變。Track B 的 `PUB-B0` 兩個子問題（規則選擇、FORMAL seed 範圍花在哪條線）仍未決，不受本決定影響。
