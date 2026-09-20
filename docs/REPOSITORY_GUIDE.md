# Repository Guide

## 1. Repository

- GitHub：`https://github.com/dofliu/robotMan`
- Default branch：`main`
- License：MIT（沿用遠端 initial commit 的 `LICENSE`）
- Development version：`0.2.0-dev`（權威值在 [`STATUS.yaml`](../STATUS.yaml)）

## 2. Tracked source of truth

Repository 保存：

- `backend/*.py`：simulation、controller、WebSocket/API、trace 與 Motion Task source。**模組使用平坦 import**——`backend/` 必須是 `sys.path[0]`，所以啟動指令是 `python backend/main.py`，不是 `uvicorn backend.main:app`（後者會 `ModuleNotFoundError`）。
- `backend/test_*.py`：software contract 與 regression tests。
- `backend/toolkit/`（**2026-09-19 建立**，`PROJECT_ASSESSMENT` §4.1 產品 B）：可攜的證據工具組，7 個模組／5,508 行。依賴方向由專案指向工具組，不可反向——由 `module_boundary_contract` fail-closed 檢查。見 [TOOLKIT_MOVE](TOOLKIT_MOVE_2026-09-19.md)。
- `backend/archive/`（**2026-09-19 建立**，`PROJECT_ASSESSMENT` §4.2）：已結案研究線的 contract／runner／replay 與**其測試**，22 個檔案。**那 376 個測試仍然全部在跑**——封存的是位置，不是檢查。見 [RESEARCH_LINE_ARCHIVE](RESEARCH_LINE_ARCHIVE_2026-09-19.md)。
- `backend/rl/policy_registry.json`、training profiles 與 training/evaluation source。
- `backend/rl/ppo_walk_final.zip`、`ppo_stand_start_walk_stop_0p7_curriculum_v2.zip`、`ppo_stand_start_walk_stop_0p7_phase_observable_v5.zip`：registry 指定的 inference artifacts；啟用前皆須通過 identity、observation contract、size 與 SHA-256 gate。
- `frontend/src`、package manifests 與 build configuration。
- `README.md`、`STATUS.yaml`、`CHANGELOG.md` 與 `docs/`（51 份活文件）。
- `docs/archive/`（**2026-09-20 建立**）：已結案研究線的 spec／receipt，索引見 [`docs/archive/README.md`](archive/README.md)。
- `docs/receipts/`（**2026-09-20 建立**）：實作 receipt，索引見 [`docs/receipts/README.md`](receipts/README.md)。
- **`docs/` 裡有 8 份一行的轉址存根**（7 份指向 `archive/`、1 份指向 `receipts/`）。它們不是內容：原路徑必須繼續解析，因為凍結證據以路徑指名、或位元組不能動的 spec 連到它們。**不要刪。** 原因見 [DOC_ARCHIVE §2、§3](DOC_ARCHIVE_2026-09-20.md)。
- **有 4 份 spec 的內容 digest 被凍結證據釘住**（`R0_REGIME_PROBE_SPEC`、`RUN_MANIFEST_LOCK_BINDING_SPEC`、`TRACKED_LINEAGE_TRAINING_SPEC`、`TRACKED_LINEAGE_TRAINING_V2_SPEC`）。**連它們的相對連結都不能改**——改連結就改位元組，改位元組就破壞 pin。
- `docs/assets/`：文件引用的圖，含 [TEST_REPORT_2026-09-20](TEST_REPORT_2026-09-20.md) 的五張 UI 截圖。
- 已保留的證據 bundle：`backend/environment_locks/`、`backend/second_case_evidence/`、`backend/seed_variance_evidence/`、`backend/r0_probe_evidence/`。這些是**證據**，內容由 digest 釘住，不得就地編輯或重新產生。
- `backend/tracked_lineage_evidence/`（**已建立**，2026-09-14；由 [TRACKED-LINEAGE-TRAINING-V1](TRACKED_LINEAGE_TRAINING_SPEC.md) §7 與 [V2](TRACKED_LINEAGE_TRAINING_V2_SPEC.md) §7 指定）：V1 與 V2 兩線每 `500,000` 步保留的 policy checkpoint（`.zip`，實測 **40 個、`77 MB`**）、`checkpoint_index.json`／`checkpoint_index_v2.json`、訓練與評估 run manifest、環境鎖與 lock binding、訓練曲線，以及 contract runner 的機器可讀 receipt，全部**進版控**。這是本 repo 唯一刻意 tracked 的 binary training artifact 目錄，與下節排除的 `backend/rl/checkpoints/` 不同：後者是沒有 frozen environment 的 smoke output，前者是 `PUB-B1` 要求的 lineage 證據，**不得**加進 `.gitignore`，也不得為了縮小 repo 而刪除任何已保留的 checkpoint。

## 3. Deliberately excluded artifacts

以下內容不進 Git：

- `frontend/node_modules/`、`frontend/dist/`：可由 lockfile 重建。
- Python caches、test caches、local virtual environments。
- `backend/run_traces/`：每次互動產生的 runtime NPZ/manifest；不是公開 immutable evidence bundle。
- `backend/rl/checkpoints/`、`backend/rl/artifacts/`、training logs：歷史或 smoke training outputs，沒有完整 frozen environment。**與 `backend/tracked_lineage_evidence/` 不同**——後者是上節指定 tracked 的 lineage 證據。
- `backend/debug_shot.*`：本機 UI debug screenshot。
- `.env*`、private keys、local assistant/evaluation state。

若未來要發布正式 experiment bundle，應使用獨立 versioned release/artifact storage，包含 environment lock、manifest、raw traces、checksums、validator receipt 與 claim boundary；不可直接取消 `.gitignore` 後批次提交。

## 4. Development setup

建議 Python 3.12、Node.js 20 以上。完整三 controller 模式需要 RL dependencies 與 repository 內的 registry-selected policy。

安裝與啟動指令見 [README 快速啟動](../README.md)，那是唯一出處，本文件不重複。

## 5. Verification before push

~~~powershell
python -m pytest backend -q
Set-Location frontend
npm run check
~~~

第一個命令目前的預期結果是 **1 failed / 941 passed**（2026-09-14；逐 commit 實測的對帳見 [PROJECT_STATUS §9](PROJECT_STATUS.md)）；唯一的失敗是在具名 environment lock 下記錄為量測結果的 reduction-order 差異（[PROJECT_STATUS §9](PROJECT_STATUS.md)）。**新增任何失敗才算 regression。**

發布前另須確認：

1. staged file inventory 不含 runtime/training/local artifacts。
2. 沒有 credential、token、private key 或個人 absolute path。
3. 所有 policy registry artifacts 的 bytes/SHA-256 與 observation/runtime adapter contract 相同。
4. GitHub remote branch/commit 在 push 後讀回一致。
5. 新產生的 evidence run 目錄帶有 `run_lock_binding.json` 且 gate 判為 `RUN_LOCK_BOUND`（見 [RUN_MANIFEST_LOCK_BINDING_SPEC](RUN_MANIFEST_LOCK_BINDING_SPEC.md) 與 [USAGE §8.1](USAGE.md)）。

## 6. Evidence boundary

Git commit、green tests 與可開啟 UI 只構成 software/source evidence。它們不會把專案升格為 calibrated model、HIL、bench 或 integrated-robot validation。
