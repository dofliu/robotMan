# Environment Lock Implementation Receipt

日期：2026-09-08

Contract：`ENVIRONMENT-LOCK-V1`
Spec：[`docs/ENVIRONMENT_LOCK_SPEC.md`](ENVIRONMENT_LOCK_SPEC.md)
（SHA-256 `96e931aebf4a1814ae1d6e267fa5e6bd757278269ec044dc169cdf18b48cdbcd`）

實作：
- [`backend/environment_lock.py`](../backend/environment_lock.py)
  SHA-256 `d220960672426bfdbf06f79841990563002097a56d9d70899fb700b282b3d488`
- [`backend/test_environment_lock.py`](../backend/test_environment_lock.py)
  SHA-256 `288963ee57817a4581cfb1701b38934d36c14e733d8568a6fb8647e38b518f2e`

證據範圍：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`

## 1. 完成了什麼

`docs/VV_PLAN.md` V0-R02 要求 run identity 綁定
`code bundle/config/MJCF/checkpoint/environment`。前四項本來就有
content-sensitive identity；第五項只有 `backend/requirements*.txt` 的 `>=`
floors。Floor 描述的是一個無上界的環境集合，不是一個環境。

本次建立了 environment identity 的**量測與比對機制**，並在本容器留下一份實測
record。它**不**代表 project-wide environment lock 已完成，V0 blocker 只收窄。

## 2. 實測 lock record

[RESULT] `backend/environment_locks/lock-2026-09-08-remote-dev-container.json`

| 項目 | 值 |
| --- | --- |
| record bytes | `4157` |
| record SHA-256 | `sha256:889efeb0b73cec0ea818fecf821806b1904fd1a211025399362f8fa3ef4e8bb5` |
| `locked_sha256` | `sha256:d350a110ca9a1f3a5c063c2d12996ef63a74ceba1a324b5f2098eab031fa3d7c` |
| `captured_at_utc` | `2026-09-08T07:47:23Z` |
| `lock_class` | `MEASURED_ENVIRONMENT_LOCK` |
| `lock_completeness` | `FULL_LOCK` |
| `threading_determinism` | `AMBIENT_THREADING_NOT_PINNED` |
| architecture | `Linux` / `x86_64`，glibc `2.39` |
| interpreter | CPython `3.11.15` |

實測 exact versions（見
[`backend/requirements-lock-2026-09-08.txt`](../backend/requirements-lock-2026-09-08.txt)，
SHA-256 `8ed771d57f1f16f1e1756134a5f2fb8fd1caf1eac0e17d636393ac25f7494ff4`）：

```text
cloudpickle==3.1.2      mujoco==3.12.0            pytest==8.4.2
fastapi==0.141.1        numpy==2.4.6              stable-baselines3==2.9.0
gymnasium==1.3.0        orjson==3.12.0            torch==2.14.0
httpx==0.28.1           pydantic==2.13.5          uvicorn==0.52.4
```

[RESULT] Fingerprints：

| Fingerprint | 值 |
| --- | --- |
| `stdlib_reciprocal_sum` | `7.485470860550343` |
| `numpy_reciprocal_sum` | `7.485470860550345` |
| `numpy_dot` | `80.1801122831865` |
| `numpy_matmul_trace` | `18.483828632190946` |
| `plant_fingerprint.mjcf_sha256` | `sha256:4d752d1affe3b26d7ac0b4d9aae1be9581c420dbe6453c96315a30698e7a6441` |
| `plant_fingerprint.state_sha256` | `sha256:f825de347c5e735e749df21f77b8621bdeb6b3fcb07fd414383217f35a52af2f` |
| `plant_fingerprint.final_qpos_z` | `0.4893011834280971`（`500` 個 `mj_step` 後） |
| `learning_fingerprint.rng_sha256` | `sha256:a8224af9d2333d4d2287f0fd29745aa1bcb9227d056214825382a5d1bff6b096` |
| `learning_fingerprint.parameter_sha256` | `sha256:9915f243a1a324e81ff0f4946e5f42c143dad617b339232e5af776b32f8247d8` |
| `learning_fingerprint.loss_value` | `2.724874973297119` |

## 3. 為什麼 version pin 不夠：一個實測差異

[RESULT] 同一組 `1/i, i = 1..1000` 的 1000 個 float64，在同一個環境、同一個
`numpy==2.4.6` 下：

- 依序左至右相加（stdlib）得 `7.485470860550343`；
- 交給 `numpy.ndarray.sum` 得 `7.485470860550345`。

[SOURCE] IEEE 754-2019 只規定基本運算的 correctly-rounded 結果，不規定
reduction order；numpy 使用 pairwise summation 與 SIMD。

[INFERENCE] 因此兩個值都合規，差異來自 reduction order 而非任一方有錯。這正是
「pin 版本號」無法涵蓋的那一類事實，也是本 contract 必須量測實際行為
（stepped MuJoCo state digest、實際執行的 torch optimiser step）而不是只記錄
`__version__` 的原因。

[RESULT] `backend/test_v1_analytical_suite.py::
test_stdlib_replay_passes_exact_synthetic_fixture` 在本 lock 下失敗，replay
`status` 為 `FAIL`（`PRIMARY_CASE_RECEIPT_IDENTITY`）。

[INFERENCE] 該 gate 要求 numpy reduction 與 stdlib reduction bit-exact 相等，
而上一段量到的正是同一類 reduction-order 差異，因此判斷兩者是同一個機制。本次
**不**放寬該 gate，也**不**改寫該 fixture；只把它記為在本 named lock 下量到的
失敗。

## 4. 對 retained v7 evidence 的判定

[BLOCKER] `PILOT-V7-ACTION-INTERFACE-DEV-V1` 與
`AUDIT-V7-EXPOSURE-CENSORING-V1` 的 retained bundles 都在本 contract 凍結前
產生，兩者都沒有 environment lock record。其 environment 狀態為
`ABSENT_UNRECOVERABLE`。

`absent_lock_record()` 刻意不含任何量測值：把「今天這台機器」的 capture 結果
附到一份在未知環境產生的 evidence 上，是 imputation，不是補齊欄位。因此 v7
的數值無法被 environment-level 重驗，只能被 raw-artifact-level 重放（那一項
已由 `python -I -S` exact replay 完成）。

## 5. Acceptance criteria

| ID | 要求 | 結果 |
| --- | --- | --- |
| `EL-01` | locked/observed 欄位集合與 frozen registry exact | PASS（雙向檢查，缺漏與未宣告皆 fail closed） |
| `EL-02` | `locked_sha256` 由另一個 `python -I -S` process exact 重算 | PASS |
| `EL-03` | 同 process 連續兩次 capture digest 相同 | PASS（跨 process 亦相同） |
| `EL-04` | locked 欄位漂移為 mismatch，observed 漂移只是 retained finding | PASS（7 個 locked section、8 個 parametrized drift case） |
| `EL-05` | unset 與空字串是不同 state | PASS |
| `EL-06` | `PARTIAL_LOCK` 不滿足 `FULL_LOCK` 要求 | PASS |
| `EL-07` | synthetic 與 measured 不可互相冒充 | PASS（雙向） |
| `EL-08` | `ABSENT_UNRECOVERABLE` 不含量測值且不可被現行 capture 替代 | PASS |
| `EL-09` | strict finite JSON，非有限值以 typed state 保留 | PASS |
| `EL-10` | CLI exit `0`/`1`/`2` | PASS |

[RESULT] `backend/test_environment_lock.py`：**60 passed**（53 個 test function，含 parametrized case）。
Contract 的 schema、digest 與 verification 路徑不依賴任何 third-party 套件；
third-party 只出現在 probe 內部，測試本身則在 pytest 下執行。

另外一項結構性檢查值得單獨記錄：
`test_module_keeps_every_third_party_import_inside_a_probe` 以 AST 斷言
`backend/environment_lock.py` 的 top level 只 import stdlib。`python -I -S`
replay 能成立完全依賴這一點，而未來若有人加一行 top-level `import numpy`，
其他所有測試都還會綠，只有這一個會失敗。

## 6. Claim boundary

[BLOCKER] 本 contract 不提供 project-wide immutable artifact storage、沒有把
lock record 綁進既有 pipelines 的 run manifest、沒有回溯 v7 的環境，也沒有
raise `requirements.txt` 的 floors（那有 install 後果，不是本 contract 該決定
的事；只加了指向本 receipt 的註解）。

因此允許的結論只到：本容器在 `2026-09-08T07:47:23Z` 的 software environment
identity 已被量測並可被重驗；fingerprint 相同只證明**本 contract 所量測的那些
行為**相同，不證明兩個環境等價。V0/V1/V3 gate 均未解除。
