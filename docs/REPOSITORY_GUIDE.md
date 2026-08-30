# Repository Guide

## 1. Repository

- GitHub：`https://github.com/dofliu/robotMan`
- Default branch：`main`
- License：MIT（沿用遠端 initial commit 的 `LICENSE`）
- Release：`0.1.0` development prototype

## 2. Tracked source of truth

Repository 保存：

- `backend/*.py`：simulation、controller、WebSocket/API、trace 與 Motion Task source。
- `backend/test_*.py`：software contract 與 regression tests。
- `backend/rl/policy_registry.json`、training profiles 與 training/evaluation source。
- `backend/rl/ppo_walk_final.zip`、`ppo_stand_start_walk_stop_0p7_curriculum_v2.zip`、`ppo_stand_start_walk_stop_0p7_phase_observable_v5.zip`：registry 指定的 inference artifacts；啟用前皆須通過 identity、observation contract、size 與 SHA-256 gate。
- `frontend/src`、package manifests 與 build configuration。
- `README.md`、`STATUS.yaml`、`CHANGELOG.md` 與 `docs/`。

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

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend/requirements-dev.txt -r backend/requirements-rl.txt

Set-Location frontend
npm ci
npm run build
Set-Location ..

python -X utf8 backend/main.py
~~~

開啟 `http://127.0.0.1:8710/`。

## 5. Verification before push

~~~powershell
python -m pytest backend -q
Set-Location frontend
npm run check
~~~

發布前另須確認：

1. staged file inventory 不含 runtime/training/local artifacts。
2. 沒有 credential、token、private key 或個人 absolute path。
3. 所有 policy registry artifacts 的 bytes/SHA-256 與 observation/runtime adapter contract 相同。
4. GitHub remote branch/commit 在 push 後讀回一致。

## 6. Evidence boundary

Git commit、green tests 與可開啟 UI 只構成 software/source evidence。它們不會把專案升格為 calibrated model、HIL、bench 或 integrated-robot validation。
