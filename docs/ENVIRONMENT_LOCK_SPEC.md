# Environment Lock Specification

日期：2026-09-08

狀態：`FROZEN BEFORE IMPLEMENTATION`

Contract：`ENVIRONMENT-LOCK-V1`
Machine-readable record schema：`ENVIRONMENT_LOCK_RECORD_V1`
實作：[`backend/environment_lock.py`](../backend/environment_lock.py)

證據範圍：`SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED`

## 1. 本 contract 要回答的唯一問題

給定一份保留下來的 evidence bundle，**產生它的 software environment 能不能被
identity 化，並且在之後的 re-execution 中被證明相同，或者 fail closed**？

`docs/VV_PLAN.md` 的 V0-R02 要求 run identity 綁定
`code bundle/config/MJCF/checkpoint/environment`。前四項已有 content-sensitive
Git identity、exact model-package identity 與 checkpoint bytes/SHA-256；第五項
`environment` 至今只有 `backend/requirements*.txt` 的 `>=` floors。Floor 描述的是
一個無上界的環境集合，不是一個環境，因此不能用來重驗任何數值結果。

本 contract 只建立「environment identity 的量測與比對機制」。它**不**宣稱
project-wide environment lock 已完成：把 lock record 綁進每一條 pipeline 的
run manifest 是另一件未完成的工作，V0 blocker 因此只收窄，不解除。

## 2. Locked 與 observed 的分界

Lock record 分兩段，分界規則凍結如下。

`locked`：**同一個 record 在合規機器上必須逐 byte 相同**的欄位。只有會改變
數值結果或會改變 code path 的事實可以進來。

`observed`：保留但**不進 digest**的機器上下文。它會被逐欄比對並輸出 findings，
但不構成 mismatch。凡是同一個環境在不同機器、不同時間會合法變動的事實
（hostname、絕對路徑、CPU 數量、capture 時間）都放這裡。

任何欄位只能屬於其中一段；capture 與 verify 兩側使用同一個 frozen field
registry，出現未宣告或缺漏欄位即 structural failure。

## 3. Locked 欄位

1. `interpreter`：implementation、`version`、`version_info`、`maxsize`、
   `byteorder`、`float_repr_style`、`int_info.bits_per_digit`、
   `float_info` 的 `mant_dig`/`epsilon`/`max`/`min`/`dig`/`radix`。
2. `architecture`：`system` 與 `machine`。x86_64 與 aarch64 的 floating-point
   結果不保證相同，所以 architecture 屬於 locked。
3. `distributions`：frozen required set 的 canonical distribution name → exact
   version。Required set 為
   `numpy`、`mujoco`、`torch`、`gymnasium`、`stable-baselines3`、`cloudpickle`、
   `fastapi`、`pydantic`、`orjson`、`uvicorn`、`pytest`、`httpx`。
   缺任何一個即 `DISTRIBUTION_MISSING`，多出來的套件不進 digest（它們不影響
   本專案的數值結果，但會列入 observed 的 distribution count）。
4. `determinism_environment`：frozen 的 environment-variable set
   `PYTHONHASHSEED`、`PYTHONDONTWRITEBYTECODE`、`PYTHONOPTIMIZE`、`PYTHONUTF8`、
   `OMP_NUM_THREADS`、`MKL_NUM_THREADS`、`OPENBLAS_NUM_THREADS`、
   `NUMEXPR_NUM_THREADS`、`VECLIB_MAXIMUM_THREADS`、`CUBLAS_WORKSPACE_CONFIG`、
   `CUDA_VISIBLE_DEVICES`、`MUJOCO_GL`、`MUJOCO_EGL_DEVICE_ID`。
   Unset 是 typed state `UNSET`，不是空字串；兩者不得互相 imputation。
5. `numeric_fingerprint`、`plant_fingerprint`、`learning_fingerprint`：見第 4 節。

## 4. Fingerprints：量測行為，不是相信 version string

Version string 是 metadata。同一個 `numpy==2.4.6` 可以連到不同的 BLAS、用不同的
SIMD kernel，給出不同的 reduction 結果。因此 lock record 必須包含**實際量測的
數值行為**。

所有 fingerprint 的輸入都由本模組內 frozen 的 pure-Python LCG 產生，不使用
`numpy.random` 或 `torch.random` 產生輸入資料：RNG stream stability 是另一個
會隨版本改變的事實，不能同時當作 probe 的載具。

所有 float 量測值以 `repr()` 字串保存，不以 JSON number 保存。理由有二：
digest 不依賴任何 float 格式化行為；non-finite 結果可以用 typed state 保留，
不必寫出非法 JSON number。

1. `numeric_fingerprint`（stdlib + numpy）：
   - `stdlib_reciprocal_sum`：固定順序的 `sum(1/i for i in 1..1000)`。此值在
     IEEE-754 下應該處處相同，作用是 replay 的 self-check，不是 discriminator。
   - `numpy_reciprocal_sum`：同一組值交給 `numpy.ndarray.sum`。numpy 的
     pairwise summation 與 SIMD width 會改變結果，是 discriminator。
   - `numpy_dot`、`numpy_matmul_trace`：固定 257 維向量的 dot 與固定 33×33
     矩陣自乘後的 trace，走 BLAS，是 BLAS kernel 的 discriminator。
   - `longdouble_itemsize`、`dtype_sizes`：platform ABI discriminator。
2. `plant_fingerprint`（MuJoCo）：以本模組內 frozen 的最小 MJCF（不使用
   `backend/model_builder.py`，避免與 repo drift 耦合）建模，用固定 `ctrl`
   跑 `500` 個 `mj_step`，再對每個 `qpos`/`qvel` 元素的 `repr` 串接取
   SHA-256。這是 plant 可重現性最直接的 probe：它量測的是 solver 實際輸出，
   而不是 `mujoco.__version__`。
3. `learning_fingerprint`（torch）：`torch.manual_seed(0)` 後，對固定輸入跑一次
   linear forward/backward 與一步 SGD，對結果 parameter 的 `repr` 取 SHA-256。
   Probe 期間強制 `torch.set_num_threads(1)` 並在結束後還原，讓 locked 值
   與 ambient thread 設定無關；ambient `torch.get_num_threads()` 另存 observed。

`torch`/`mujoco`/`numpy` 匯入或量測失敗時，對應 fingerprint 以 typed
`{"state": "UNAVAILABLE", "reason": ...}` 保留。任一 fingerprint 為
`UNAVAILABLE`，或 required distribution set 中任一項為 `MISSING`，record 的
`lock_completeness` 即為 `PARTIAL_LOCK`；兩者皆無才是 `FULL_LOCK`。
`PARTIAL_LOCK` 永遠不能滿足要求 `FULL_LOCK` 的 protocol。

## 5. Digest 與 record identity

`locked_sha256` 是 `locked` subtree 的 canonical JSON（`sort_keys=True`、
`ensure_ascii=False`、`allow_nan=False`、`indent=2`、尾端換行）的 SHA-256，
與 `backend/v7_exposure_audit_contract.py` 使用的 canonical form 相同。

Digest 只覆蓋 `locked`。`observed` 與 `captured_at_utc` 不進 digest，否則同一個
環境每次 capture 都會得到不同 identity，lock 就失去意義。

## 6. Lock class 與缺失 lock 的表述

- `MEASURED_ENVIRONMENT_LOCK`：在實際執行環境中量測得到。
- `SYNTHETIC_REGRESSION_LOCK`：測試用，永遠不得被回報成 measured lock。
- `ABSENT_UNRECOVERABLE`：retained evidence 沒有 lock record，且產生它的環境
  已無法回溯。此狀態必須明示 reason，並且**不得**以「目前環境」的 capture
  結果替代。

[BLOCKER] `PILOT-V7-ACTION-INTERFACE-DEV-V1` 與
`AUDIT-V7-EXPOSURE-CENSORING-V1` 的 retained bundles 都在本 contract 凍結前
產生，兩者都沒有 environment lock record。它們的 environment 狀態是
`ABSENT_UNRECOVERABLE`。這不是可以事後補上的欄位：v7 training 在哪一組
numpy/mujoco/torch build 上跑，已經不存在證據。因此 v7 的數值結果無法被
environment-level 重驗，只能被 raw-artifact-level 重放。

## 7. Verification semantics

`verify_environment_lock(expected, observed)` 輸出 typed findings：

- `INTERPRETER_DRIFT`、`ARCHITECTURE_DRIFT`、`DISTRIBUTION_VERSION_DRIFT`、
  `DISTRIBUTION_MISSING`、`DETERMINISM_ENVIRONMENT_DRIFT`、
  `NUMERIC_FINGERPRINT_DRIFT`、`PLANT_FINGERPRINT_DRIFT`、
  `LEARNING_FINGERPRINT_DRIFT`、`FINGERPRINT_UNAVAILABLE`
  （以上皆 `severity=LOCK_MISMATCH`）；
- `OBSERVED_CONTEXT_DRIFT`（`severity=RETAINED_FINDING`，不構成 mismatch）。

任何一個 `LOCK_MISMATCH` finding 使 `environment_lock_match=false`。要求
exact lock 的 protocol 在此情況下必須 fail closed，不得以 findings 數量、
「差異很小」或「只差 patch version」為理由放寬。

`THREAD_COUNT_NOT_PINNED` 是 capture 期間的 retained finding：ambient
`OMP_NUM_THREADS` 未設為 `1` 時記錄它，並把 record 的
`threading_determinism` 標成 `AMBIENT_THREADING_NOT_PINNED`。它不改變
locked digest（fingerprint 已在 probe 內把 thread 數固定成 1），但它是
training reproducibility 的已知風險，必須保留。

## 8. Acceptance criteria

- `EL-01`：`locked`/`observed` 欄位集合與 frozen field registry exact；未宣告或
  缺漏欄位 fail closed。
- `EL-02`：`locked_sha256` 等於 `locked` subtree canonical JSON 的 SHA-256，且
  由另一個 `python -I -S` stdlib-only process 從同一份 record exact 重算。
- `EL-03`：同一個 process 內連續兩次 capture 的 `locked_sha256` 相同
  （fingerprint 具備 run-to-run determinism）。
- `EL-04`：任一 locked 欄位被改動即產生對應 `LOCK_MISMATCH` finding 且
  `environment_lock_match=false`；`observed` 欄位改動只產生 retained finding。
- `EL-05`：unset 與空字串的 environment variable 是不同 state，互換即 mismatch。
- `EL-06`：`PARTIAL_LOCK` record 不能滿足要求 `FULL_LOCK` 的 protocol。
- `EL-07`：`SYNTHETIC_REGRESSION_LOCK` 不能在任何路徑上被回報成
  `MEASURED_ENVIRONMENT_LOCK`，反向亦然。
- `EL-08`：`ABSENT_UNRECOVERABLE` record 不含任何量測值，且不得以現行環境
  capture 結果替代。
- `EL-09`：record 的 JSON 為 strict finite JSON；NaN/Infinity 以 typed
  `NONFINITE` state 保留。
- `EL-10`：CLI structural failure 退出碼為 `2`，lock mismatch 為 `1`，
  match 為 `0`。

`EL-01..EL-10` 全部通過才算完整 environment-lock 機制證據。

## 9. Claim boundary

[SOURCE] IEEE 754-2019 只規定基本運算的 correctly-rounded 結果，不規定
reduction order；因此不同 summation order 或 SIMD width 給出不同但都合規的
結果。[SOURCE] MuJoCo official documentation 說明 solver 設定與 build 選項會
影響數值輸出。[SOURCE] PyTorch official reproducibility 文件明示跨版本、
跨平台與跨 thread 數不保證 bitwise 相同。

[INFERENCE] 因此「pin 版本號」不足以保證數值可重現，必須量測實際行為；
反之，fingerprint 相同也只證明本 contract 所量測的那些行為相同，不證明整個
環境等價。

[RESULT] 本節只凍結 contract，尚無 lock measurement。

[BLOCKER] 本 contract 不提供 immutable artifact storage、不把 lock record 綁進
既有 pipelines 的 run manifest、不回溯 v7 的環境，也不解除 V0/V1/V3 gate。

Primary/official sources：

- [IEEE 754-2019](https://doi.org/10.1109/IEEESTD.2019.8766229)
- [MuJoCo Computation / Solver](https://mujoco.readthedocs.io/en/stable/computation/index.html)
- [PyTorch Reproducibility](https://pytorch.org/docs/stable/notes/randomness.html)
- [NumPy Reduction Accuracy](https://numpy.org/doc/stable/reference/generated/numpy.sum.html)
