# 三機比較與 RL Registry 實作回條

日期：2026-08-26
Evidence scope：SOFTWARE_ONLY / DEVELOPMENT
Project gate：V0 NOT PASS；V3 NOT PASS

## 1. 完成項目

- `/ws/compare`：建立 `track`、`raibert`、`rl` 三個獨立 `LiveSession`。
- 共用 typed commands：mode、push、speed、pause、step、assist、reset。
- compare scene/frame：controller identity、plant signature、independent-plant flag、time skew 與三組完整 telemetry。
- frontend 新增「三機同步比較」；三個 renderer 並排，共用控制，assist 預設 OFF，FALLEN 不自動 reset。
- `RL_POLICY_REGISTRY_V1`：既有 `walk_0p7_legacy` 以 ID、bytes、SHA-256、gait/training contract 與 evidence status fail closed 載入。
- `/api/policies`：只回傳 software artifact inventory，不回報 performance claim。
- `RL_TRAINING_PROFILES_V1`：0.4、0.7、1.0 m/s profiles。
- versioned training pipeline：每個 run 使用獨立 directory；existing run ID fail closed，不覆寫舊 checkpoint。

## 2. Verification results

| Check | Result |
|---|---|
| Backend complete regression | 87 passed；2 existing dependency deprecation warnings |
| Compare-specific tests | 9 passed |
| Policy registry + profile tests | 10 passed |
| Frontend TypeScript typecheck | PASS |
| Frontend production build | PASS；existing >500 kB chunk warning remains |
| Real default PPO registry load | PASS：`walk_0p7_legacy` |
| Real three-session walk smoke | PASS：all WALK，`max_time_skew_s=0.0` |
| Existing run-ID overwrite attempt | Rejected，manifest hash unchanged |
| Browser visual/interaction smoke | BLOCKED：本回合無可用 browser execution interface |

## 3. Training smoke receipts

三個 run 都只有 256 steps、1 env；status 為 `PIPELINE_SMOKE_NOT_POLICY_EVIDENCE`。

| Run ID | Policy SHA-256 | Meaning |
|---|---|---|
| `smoke-20260826-walk-0p4` | `66d8e0244c9bb348c5a4b430691c9042bcce16b0abb093aa1430cf85b35327ec` | pipeline smoke only |
| `smoke-20260826-walk-0p7` | `300bc123f384eb331bb8d02208a52e0e427660329530518a6709f960c6a4d175` | pipeline smoke only |
| `smoke-20260826-walk-1p0` | `2b691e1ef2b98e44ddc2b048d33b97956c6aafe1b58286aff2e365e778e1725c` | pipeline smoke only |

Smoke artifacts 不加入 policy registry，也不支援「已學會走路」或 controller ranking claim。

## 4. Remaining blockers

- 三個固定速度 profiles 尚未做完整 training/evaluation；目前只有 legacy 0.7 m/s policy 可部署。
- 完整 30M steps × 3 依既有 CPU log 粗估屬數小時級工作；正式啟動前須固定 run IDs、training budget 與 sequential/parallel resource policy。
- Command-conditioned multi-speed、run、turn、terrain、disturbance curriculum 尚未開始。
- Browser visual smoke、immutable training bundle、environment lock、multi-seed evaluation 與 V3 statistics 未完成。
