# Repository Guide

## 1. Repository

- GitHub：`https://github.com/dofliu/robotMan`
- Default branch：`main`
- License：MIT（沿用遠端 initial commit 的 `LICENSE`）
- Development version：`0.2.0-dev`（權威值在 [`STATUS.yaml`](../STATUS.yaml)）

## 2. Tracked source of truth

Repository 保存：

- `backend/*.py`：simulation、controller、WebSocket/API、trace 與 Motion Task source。
- `backend/test_*.py`：software contract 與 regression tests。
- `backend/rl/policy_registry.json`、training profiles 與 training/evaluation source。
- `backend/rl/ppo_walk_final.zip`、`ppo_stand_start_walk_stop_0p7_curriculum_v2.zip`、`ppo_stand_start_walk_stop_0p7_phase_observable_v5.zip`：registry 指定的 inference artifacts；啟用前皆須通過 identity、observation contract、size 與 SHA-256 gate。
- `frontend/src`、package manifests 與 build configuration。
- `README.md`、`STATUS.yaml`、`CHANGELOG.md` 與 `docs/`。
- 已保留的證據 bundle：`backend/environment_locks/`、`backend/second_case_evidence/`、`backend/seed_variance_evidence/`、`backend/r0_probe_evidence/`。這些是**證據**，內容由 digest 釘住，不得就地編輯或重新產生。

## 3. Deliberately excluded artifacts

以下內容不進 Git：

- `frontend/node_modules/`、`frontend/dist/`：可由 lockfile 重建。
- Python caches、test caches、local virtual environments。
- `backend/run_traces/`：每次互動產生的 runtime NPZ/manifest；不是公開 immutable evidence bundle。
- `backend/rl/checkpoints/`、`backend/rl/artifacts/`、training logs：歷史或 smoke training outputs，沒有完整 frozen environment。
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

第一個命令目前的預期結果是 **1 failed / 816 passed**；唯一的失敗是在具名 environment lock 下記錄為量測結果的 reduction-order 差異（[PROJECT_STATUS §9](PROJECT_STATUS.md)）。**新增任何失敗才算 regression。**

發布前另須確認：

1. staged file inventory 不含 runtime/training/local artifacts。
2. 沒有 credential、token、private key 或個人 absolute path。
3. 所有 policy registry artifacts 的 bytes/SHA-256 與 observation/runtime adapter contract 相同。
4. GitHub remote branch/commit 在 push 後讀回一致。
5. 新產生的 evidence run 目錄帶有 `run_lock_binding.json` 且 gate 判為 `RUN_LOCK_BOUND`（見 [RUN_MANIFEST_LOCK_BINDING_SPEC](RUN_MANIFEST_LOCK_BINDING_SPEC.md) 與 [USAGE §7.1](USAGE.md)）。

## 6. Evidence boundary

Git commit、green tests 與可開啟 UI 只構成 software/source evidence。它們不會把專案升格為 calibrated model、HIL、bench 或 integrated-robot validation。
