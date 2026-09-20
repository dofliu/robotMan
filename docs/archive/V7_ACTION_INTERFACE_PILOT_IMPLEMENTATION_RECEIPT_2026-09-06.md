# V7 Action-Interface DEVELOPMENT Pilot Implementation Receipt

日期：2026-09-06

Protocol：`PILOT-V7-ACTION-INTERFACE-DEV-V1`

狀態：`EVIDENCE_COMPLETE / CONTRACT_VALID / RETAINED_SEMANTIC_BLOCKER`

證據邊界：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED / DEVELOPMENT_ONLY`

## 1. 本次唯一目標

依 [V7 Action-Interface DEVELOPMENT Pilot Specification](V7_ACTION_INTERFACE_PILOT_SPEC.md)
建立三臂 action-interface runtime、fail-closed training/evaluation、artifact bundle與
stdlib-only replay，並只以 DEVELOPMENT seeds `18000–18029`完成一次 bounded pilot。

Acceptance criteria、failure semantics與 claim boundary已先在 Git
`e839aa263b391ade21bbfc61c50123a9ca384df4`凍結；實作與實驗 source為 Git
`058657dd43d28a9175e54362cf4d0a0618507c38`。`19000–19029`未讀取且維持退役，
`20000–20029`未讀取且維持 sealed FORMAL range。Motion Task thresholds未變。

## 2. 完成內容

- 新增 strict machine-readable action-interface contract，拒絕 duplicate key、NaN/Infinity、
  task/seed/budget/joint-order/action-scale drift。
- 新增三個 51-D environments；V7C的 previous-action observation明確保存上一個
  applied normalized action，使一階 filter state對 policy可見。
- Training CLI鎖定 run ID、common seed `8700`、12 environments、CPU、v5 warm start、
  requested `100000`與 realized `122880` steps；resume、ad-hoc warm start、smoke與
  device override均 fail closed。
- Evaluator逐 control step保存 requested/applied action、joint target、action deltas，以及
  500 Hz physics substeps的 saturation aggregate numerator/denominator（total固定10）；
  不保存10筆逐substep torque samples。輸出禁止覆寫且採 atomic write。
- Bundle builder逐層重驗 protocol、Git pre/post、source hash、checkpoint、manifest、
  evaluation、safe relative path、bytes與SHA-256，並從 per-control-step aggregate counts重算
  saturation duty與 action operator identity。
- `backend/v7_pilot_replay.py`只使用 Python stdlib；`python -I -S`由 raw episodes
  exact重建 gates、conditional statistics、paired differences與 primary summary。

本次沒有修改 policy registry、Live adapter或 frontend。

## 3. Frozen runs 與 identity

三臂都從同一 v5 artifact warm start：bytes `1983126`，SHA-256
`c548867fbd17c736d54c1b1598d2abed1c7cb2dd28c7d310ea6e86ac3b36718c`。
每個 training manifest的 Git pre/post均為
`058657dd43d28a9175e54362cf4d0a0618507c38`，且兩端
`working_tree_dirty=false`。

| Arm | Training terminal | Realized steps | Policy bytes | Policy SHA-256 |
|---|---|---:|---:|---|
| `V7A_REWARD_ONLY` | `COMPLETED` | 122880 | 1983126 | `7df5c598c0fe1968b443a74c62294166f981bc9cfd02d43377f5807eccf8e80d` |
| `V7B_REDUCED_JOINT_ENVELOPE` | `COMPLETED` | 122880 | 1983126 | `a37550b264f8a3be5f53855d5b1c61094d3d1cac513ca6b9294360b12db3f258` |
| `V7C_FILTERED_ACTION` | `COMPLETED` | 122880 | 1983126 | `e2f8448cebd7d704dc973c671727576afdc0bc82677384420f64a1319ca1dfc9` |

## 4. DEVELOPMENT evaluation結果

每臂皆有 exact 30個 terminal records，seeds為 `18000–18029`。Primary outcome是
500 Hz `saturation_duty_pct`；paired contrast固定為 candidate minus V7A。

| Arm | Observed / NULL / NONFINITE | Gate結果 | Saturation mean ± sample SD | Frozen interpretation |
|---|---:|---|---:|---|
| V7A | 30 / 0 / 0 | FAIL：30個 episodes皆失敗於 saturation | 36.2185185 ± 1.0328300% | reward-only reference負結果 |
| V7B | 30 / 0 / 0 | FAIL：4個 negative episodes；18011 stop；18015 fall/stop/lateral；18021與18023 fall/stop | 23.3896264 ± 1.0044698% | saturation gate通過，但 reliability/stop/lateral使其不 eligible |
| V7C | 0 / 30 / 0 | FAIL：30/30 early fall，required outcomes為 NULL | 0 ± 0%（倒下前片段） | semantic blocker；0%不可解讀為 action-interface改善 |

[RESULT] V7B相對V7A的 saturation paired difference為
`-12.8288921 ± 1.0720320` percentage points（mean ± sample SD，30 pairs）。

[INFERENCE] 在此單一 training checkpoint與固定 DEV seed set下，縮小 target-offset
envelope呈現較低 simulated saturation，但同時出現三次 fall與額外 stop/lateral failure；
它不符合 frozen eligibility，不能選為 candidate或宣稱 superiority。

[BLOCKER] V7C所有 required outcomes均為 NULL。雖然倒下前 saturation仍是 observed
scalar並可做 arithmetic replay，但其 `0%`主要來自 episode提早終止，不是有效改善訊號。

因此 selection固定為 `PILOT_RETAINED_SEMANTIC_BLOCKER`，
`selected_candidate_arm_id=null`、`pilot_planning_ready=false`、
`method_level_power_ready=false`、`paper_data_ready=false`。本 pilot未計算 confidence
interval或 p-value；30個 evaluation seeds不是30個 independent training replicates。

## 5. Evidence bundle與 replay

Bundle root：`backend/run_traces/v7-action-interface-pilot-clean-20260906/`

- `pilot_receipt.json`：14個 indexed artifacts，共 `109520182` bytes；SHA-256
  `ed3e3eaa7c86f2b855d24aca68b09ce45bce61ac2fb6e573328b12157d758435`。
- `raw_episodes.json`：`54265469` bytes；SHA-256
  `974d66936d0071b41adb6e34859eb5d38d2597466f2cd6115b2ba537418a9606`。
- `pilot_summary.json`：`21371` bytes；SHA-256
  `5098f6f8df7aa9c7674944bec0c4f8ecda729c61813cf21806bec58d08449793`。
- `replay_receipt.json`：`1101` bytes；SHA-256
  `aaa31bc77860b9bd56390ee7dbe29442180709c6774bb92307f0232464294bf1`。
- Frozen protocol copy：`9753` bytes；SHA-256
  `719b70a2bdf8d23af5f4ec5dff51a6099e88d6de4e2221fa74f6f7464cdfcb96`。

Bundle validation輸出 `BUNDLE_VALID / contract_valid=true / evidence_complete=true`。
CLI依 frozen semantics回傳 exit `1`，因30個 V7C NULL是 retained semantic blocker；
不是 structural failure。獨立 replay回傳 exit `0`、`exact_identity=true`，六項 replay
checks全部為 true。`AP-01..AP-10`全部通過。

大量 policies、raw traces、evaluations與logs維持 `.gitignore`內的 local versioned
artifact root，不提交 Git；小型 protocol、source、tests與本 receipt進入版本控制。

## 6. 程式驗證與失敗保留

| 驗證 | 結果 |
|---|---|
| 實作前 targeted baseline | `33 passed, 3 warnings` |
| Final v7 action/bundle targeted | `54 passed, 1 warning` |
| Final quiescent full backend suite | `301 passed, 5 warnings` |
| JSON、Python compile、diff whitespace | PASS |
| Secret pattern、artifact tracking policy | PASS；無新增命中、無 runtime artifact被 tracked |
| Frontend | 未受影響，`npm run check`不適用 |

[RESULT] 曾有一輪 full suite在 pytest collection後仍發生 parallel bundle檔案更新，形成
`274 passed / 20 failed`；failure均為舊 synthetic fixture與新 validator的 source-hash
mismatch。該輪標記為 `INVALID_CONCURRENT_SOURCE_EDIT`並保留，沒有當成通過。停止所有
subagents後，stable targeted與 quiescent full suite才分別取得上述54/54與301/301結果。

## 7. 理論與 validity boundary

[SOURCE] Gymnasium official Action Wrappers允許以與 action shape相同的 arrays做逐維
affine rescaling；Stable-Baselines3 official guidance建議 continuous action維持 symmetric
normalized range，且警告 delay若未納入 history會破壞 Markov assumption。

[SOURCE] MuJoCo official actuation model把 low-pass activation明確定義為 stateful
dynamics；Patterson et al.（JMLR 2024）要求區分 agent/environment RNG並建議 paired
comparisons；Agarwal et al.（NeurIPS 2021）要求有限 runs保留 uncertainty而非只報點估計。

[INFERENCE] V7C把 previous applied action放回 observation可維持本一階 operator所需的
state visibility；這不證明 filter常數對真實 actuator有效。

[BLOCKER] Primary/official sources沒有提供 robotMan專屬的 joint envelope、filter alpha或
rate limit。這些數值仍只是 simulation hypotheses；也沒有 independent training-seed
variance、full 11-criterion Live evidence、actual Study A、binary paired CI、HIL、bench或
robot evidence。

Primary/official sources：

- [Gymnasium Action Wrappers](https://gymnasium.farama.org/main/api/wrappers/action_wrappers/)
- [Stable-Baselines3 RL Tips](https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html)
- [MuJoCo Actuation Model](https://mujoco.readthedocs.io/en/stable/computation/index.html#actuation-model)
- [Empirical Design in Reinforcement Learning, JMLR 2024](https://www.jmlr.org/papers/v25/23-0183.html)
- [Deep RL at the Edge of the Statistical Precipice, NeurIPS 2021](https://proceedings.neurips.cc/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html)
- [Action Constraints Benchmark, IEEE RA-L 2023](https://doi.org/10.1109/LRA.2023.3284378)

## 8. Claim boundary與下一步

允許結論僅為：在 frozen MuJoCo plant、v5 warm start、單一 training seed、指定 task與
DEV evaluation seeds下，三個 action interfaces呈現上述 conditional simulated outcomes。

禁止外推為 controller superiority、method-level effect、formal sample-size adequacy、
paper readiness、physical torque/thermal margin、安全、sim-to-real或實體機器人效能。

下一次唯一優先目標是 **V7 early-termination / exposure-censoring validity audit V1**：
只讀本 bundle既有 raw traces，重建 termination time／phase與有效 exposure，將 V7C的
0% duty及其 paired contrast明示為 non-comparable/censored，並保留原 receipt不回改。
不新增 training/evaluation seed、不調 alpha/envelope/threshold、不重跑本 pilot，也不開啟
FORMAL/HOLDOUT；完成此 validity audit後，才另立 fresh DEVELOPMENT protocol考慮
independent training-seed variance。
