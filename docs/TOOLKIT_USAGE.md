# 在你自己的 RL 專案裡用這套工具組

日期：2026-09-19 ｜ 性質：**對外使用說明**，不是 protocol、不是 receipt
｜ 前置：[TOOLKIT_PORTABILITY](TOOLKIT_PORTABILITY.md)（逐模組審計）

**這份文件只寫今天真的做得到的事。** 做不到的寫在 §6，附上原因與該去讀哪一段。
本文件每一段程式碼與每一個輸出都在 2026-09-19 實際跑過，執行環境見 §7。

---

## 1. 你拿得走的是三個檔案，不是七個

[PROJECT_ASSESSMENT §4.1](PROJECT_ASSESSMENT_2026-09-16.md) 說這個 repo 裡有一套可複用的實驗工具組（7 個模組）。
[逐模組審計](TOOLKIT_PORTABILITY.md#4-可攜性審計邊界乾淨--拿得走)之後，**外部專案今天能用的是三個**：

| 檔案 | 行數 | 第三方相依 | 它給你什麼 |
|---|---:|---|---|
| `backend/exposure_identification.py` | 312 | **無** | 早期終止會讓 per-step 平均說謊；這個模組算出不做假設的識別區間 |
| `backend/environment_lock.py` | 1,366 | mujoco／numpy／torch**（皆惰性，缺了就降級）** | 量測並凍結「這次執行是在哪個環境上跑的」 |
| `backend/run_manifest_lock.py` | 813 | **無** | 把一份 run manifest 與一份環境 lock 綁成**可重算**的關係，並在分析期 fail-closed 檢查 |

其餘四個（`experiment_matrix_contract`、`paired_statistics_contract`、`paper_data_contract`、`rl/bind_run_lock`）
**今天擋死**，原因與繞法見 §6。

## 2. 安裝：把三個檔案放進同一個目錄

**沒有套件、沒有 `pip install`。** `run_manifest_lock` 用**平坦**名稱 import `environment_lock`
（[TOOLKIT_PORTABILITY §5.1](TOOLKIT_PORTABILITY.md#51-平坦兄弟-import可修是純工程問題)），
所以三個檔案要在**同一個目錄**，而那個目錄要在 `sys.path` 上：

```
your-project/
  lockkit/                     <- 把三個 .py 原封不動複製進來
    environment_lock.py
    exposure_identification.py
    run_manifest_lock.py
  bind.py                      <- 你自己寫的，見 §4
  runs/
```

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "lockkit"))
```

**不需要**複製 `run_manifest_lock_binding_protocol.json`。模組 import 時不會讀它；
只有 `load_protocol()` 會，而下面的流程完全不呼叫它。

三個模組**都在 `python3 -I -S` 下載入**（無 site-packages），實測沒有任何第三方模組進 `sys.modules`。

## 3. 用途一：識別區間——這是完全可攜的那一個

**問題**：一個 episode 在第 300 步倒下，觀察到 300 步裡有 90 次事件。
per-step 平均報 `90/300 = 30.0%`——**和一個跑完 1000 步、也是 30% 的 episode 完全一樣**。
那 700 步沒被觀察到的事，被無聲地當成「和觀察到的一樣」。

```python
import exposure_identification as ex

H = 1000  # 凍結的 horizon

full  = ex.episode_bound_pct(observed_positive=120, observed_total=H,   horizon_total=H)
early = ex.episode_bound_pct(observed_positive=90,  observed_total=300, horizon_total=H)
```

實測輸出：

```
full   {'exposure_class': 'FULL_EXPOSURE',    'lower_pct': 12.0, 'upper_pct': 12.0, 'point_identified': True}
early  {'exposure_class': 'EARLY_TERMINATED', 'lower_pct':  9.0, 'upper_pct': 79.0, 'width_pct': 70.0}
        naive_rate_pct(90, 300) == 30.0
```

**區間不做任何假設**：沒看到的 700 步，每一步可以是 0 也可以是 1，所以真值落在 `[9.0, 79.0]`。
跑完全程時區間塌成一個點，就等於 naive 值。

### 3.1 這件事會改變結論，不只是加個誤差棒

五個 replicate、候選組有**兩個**早期終止，其餘全程：

```python
cand = [(120,H), (118,H), (30,300), (122,H), (15,150)]
ref  = [(150,H), (147,H), (152,H),  (149,H), (151,H)]

diffs = [ex.paired_difference_pp(
             ex.episode_bound_pct(observed_positive=cp, observed_total=ct, horizon_total=H),
             ex.episode_bound_pct(observed_positive=rp, observed_total=rt, horizon_total=H))
         for (cp, ct), (rp, rt) in zip(cand, ref)]

theta = ex.method_level_pp(diffs, expected_denominator=5, forbidden_denominators=(10, 50))
naive = ex.naive_method_level_pp(
    [ex.naive_rate_pct(cp, ct) - ex.naive_rate_pct(rp, rt) for (cp, ct), (rp, rt) in zip(cand, ref)],
    t_critical=2.776, expected_denominator=5, forbidden_denominators=(10, 50))

ex.compare_naive_to_bound(naive=naive, bound=theta)
```

實測輸出：

```
naive 逐 replicate 差 (pp): [-3.0, -2.9, -5.2, -2.7, -5.1]
naive  : mean -3.78   t-interval [-5.339016, -2.220984]   asserts NEGATIVE
bound  : [-6.88, +24.12]                                   sign UNIDENTIFIED
verdict: NAIVE_ASSERTS_DIRECTION_BOUND_CONTAINS_ZERO
```

**per-step 平均宣告候選組更好，而且信賴區間不含零。** 不做假設的區間**跨過零**。
五個 replicate 裡只有兩個被截斷。

`expected_denominator` 與 `forbidden_denominators` 是**強制**的：分析單位是 replicate，
傳入 episode 數會丟例外。這擋掉的是 pseudo-replication，與 censoring 是兩件獨立的事，
模組刻意讓它們不能互相掩護。

### 3.2 三條它不肯做的事

- **`NOT_IDENTIFIED` 不會塌成一個方向。** 區間跨零就是 `UNIDENTIFIED`，不給你取中點。
- **區間沒有 SD。** `between_replicate_sd_pp` 在有任一 replicate 未點識別時回 `None`，
  並附上 `BLOCKED_PARTIALLY_IDENTIFIED_REPLICATE_DIFFERENCES` 而不是猜一個。
- **加總順序是契約的一部分。** 浮點加法不可結合，所以值要依 seed／replicate 遞增順序傳入。

## 4. 用途二：把 run manifest 綁到環境 lock

`rl/bind_run_lock.py` **對你關死**：它到一份凍結的 protocol 裡用 **repo 相對路徑**找 producer，
那裡只有本專案的四個檔案（[§5.3](TOOLKIT_PORTABILITY.md#53-凍結的-producer-登錄檔rlbind_run_lock)）。
**但它包的那個模組沒有關死。** 你自己寫大約 30 行取代它（下面這段實為 31 行、26 行非空非註解）：

```python
# bind.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "lockkit"))
import run_manifest_lock as rml

rml.CLAIM_BOUNDARY = (
    "This binding establishes only that one run manifest and one environment "
    "lock record are linked by a recomputable relation. It supports no claim "
    "about the correctness of any result."
)   # 這個欄位驗的是「非空字串」，不是等值——所以你寫你自己的

def capture(run_dir):                      # 步驟 1：跑之前量環境
    return rml.capture_lock_for_run(Path(run_dir))

def bind(root, run_dir, manifest_name, cap):   # 步驟 2：driver 寫完 manifest 後釘住它的 bytes
    record = rml.build_binding_record(
        root=Path(root),
        manifest_path=Path(run_dir) / manifest_name,
        manifest_schema_version="MY_RUN_MANIFEST_V1",
        lock_record_path=cap["lock_record_path"],
        binding_mode=rml.MODE_SIDECAR_ONLY,
        sidecar_reason="my driver's digest is pinned elsewhere, so it is not edited",
        verified_before_run=cap["verified_before_run"],
        lock_verified_at_utc=cap["lock_verified_at_utc"],
    )
    rml.write_binding_record(Path(run_dir), record)
    return record

def check(root, run_dir, manifest_name):   # 步驟 3：分析期 gate
    return rml.evaluate_run(Path(run_dir), manifest_name, root=Path(root))
```

**順序不可反。** 環境要在 driver **啟動前**量，不是在組 manifest 時量——
兩者的差異正是這個 lock 存在要偵測的東西。

### 4.1 四個標籤，實測

同一個外部專案，同一份程式：

| 你做了什麼 | `evaluate_run` 回傳 |
|---|---|
| 正常流程（環境有 numpy／torch／mujoco） | **`RUN_LOCK_BOUND`** |
| 正常流程（`python3 -I -S`，無 site-packages） | **`RUN_LOCK_INSUFFICIENT`** |
| 改掉 manifest 裡一個數字 | **`RUN_LOCK_MISMATCH`** |
| 刪掉 `environment_lock.json` | **`RUN_LOCK_BINDING_METHOD_FAILURE`** |

第四列是 2026-09-18 才修好的（[CHANGELOG (aq)](../CHANGELOG.md)）；在那之前刪掉 lock record
仍會回 `BOUND`。**如果你複製的是更早的版本，那個假 PASS 也一起複製走了。**

### 4.2 第二列不是 bug，是這套 lock 在告訴你實話

無 site-packages 時 `environment_lock` 仍可 import、仍可用，但三個重量級 fingerprint
（numpy／mujoco／torch）回報 unavailable，於是 completeness 是 `PARTIAL_LOCK` 而不是 `FULL_LOCK`，
gate 據此回 `RUN_LOCK_INSUFFICIENT`。

**這是正確行為。** 一個沒量到 RL 執行環境主要組成的 lock，不該被報成「已綁定」。
`satisfies_full_lock_requirement` 是**推導**出來的，不是宣告的——你在記錄裡寫 `True` 也沒有用，
`validate_binding_record` 會拿 class 與 completeness 重推並拒絕不一致。

要拿到 `RUN_LOCK_BOUND`，執行環境就得裝著你 RL 專案真的在用的那些套件。**那本來就是重點。**

### 4.3 保留證據時：lock record 要放在 binding 旁邊

`evaluate_run` 是「run 還在原地」時的權威。把證據**複製**到別處後要用
`evaluate_relocated_run(directory, manifest_filename)`——它丟掉路徑比對，但**仍然重算兩個 digest**。

它用 `lock_record_path` 的 **basename** 在該目錄裡找 lock record。
所以**保留目錄必須把 lock record 放在 binding 旁邊**；用別的檔名複製就傳
`lock_record_filename="你的檔名"`。沒保留 lock record 的目錄會得到 `METHOD_FAILURE`，
理由寫在該函式的 docstring 裡。

## 5. 這些工具**不**主張什麼

照抄自 `run_manifest_lock.CLAIM_BOUNDARY` 的精神，換成對你成立的講法：

- 綁定只證明**這份 manifest 與這份 lock 記錄由一個可重算的關係連著**，且該記錄是 MEASURED＋FULL_LOCK。
- 它**不**證明任何數值正確、任何方法更好、任何結果可在別台機器重現。
  **lock 偵測環境差異；它不保證跨環境的數值同一性。**
- 識別區間**不**告訴你真值是多少，只告訴你在不做假設的前提下它可能落在哪裡。
  區間寬不是缺點，是你的資料真的只支撐到那個程度。

**這是基礎設施，不是證據。**

## 6. 今天擋死的四個模組

| 模組 | 為什麼擋死 | 你能做的 |
|---|---|---|
| `experiment_matrix_contract` | `evidence_scope: Literal["SIM_ONLY_MUJOCO"]`（`:212`）；`claim_boundary` 必須**逐字等於**本專案的 `FROZEN_CLAIM_BOUNDARY`（`:257`） | 不能用。放寬它等於動本專案凍結的主張邊界，那是擁有者的決定（任務 #93） |
| `paired_statistics_contract` | 同樣的 `Literal["SIM_ONLY_MUJOCO"]`（`:156`）＋ 平坦兄弟 import 另外兩個 contract | 不能用 |
| `paper_data_contract` | `role` 是 16 個值的封閉 `Literal`（`:54-70`）——多一種 artifact 角色就失敗 | 不能用 |
| `rl/bind_run_lock` | producer 登錄檔是四個寫死的 repo 相對路徑，找不到就 fail closed | **不必用**：§4 的那 31 行直接取代它 |

前三個**不是疏忽**。那句逐字比對的「SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED」，
正是這個專案不誇大主張的機制之一（[TOOLKIT_PORTABILITY §5.2](TOOLKIT_PORTABILITY.md)）。

**還有一個已知、未修的 bug 你要知道**：`environment_lock.py:425` 的 `learning_fingerprint()`
會動**全域** torch RNG。對本專案不咬人，但如果你在同一個 process 裡先量 fingerprint、
再依賴自己的 RNG 狀態，種子會被悄悄換掉。**修它會改變 fingerprint 的值**，所以本專案沒修
（~~41 份已提交的 lock record 會失效~~ **2026-09-19 更正：實測為 20 份已提交記錄，而且 0 份會失效**——`torch.Generator` 變體產生**逐位元相同**的 fingerprint。不修的理由換成：那是個**半修**，`torch.nn.Linear` 也從全域預設產生器抽初始化，串流照樣被推進。見 [TOOLKIT_PORTABILITY_DECISIONS_2026-09-19](TOOLKIT_PORTABILITY_DECISIONS_2026-09-19.md) §2.1）。**你的對策：在自己的訓練流程開始前量，不要量到一半。**

## 7. 本文件的量測條件

- 全部在 `python3 -I -S`（無 site-packages）下跑過，唯一例外是 §4.1 第一列，那一列**需要** numpy／torch／mujoco。
- 外部專案是一個乾淨目錄，只複製了 §1 的三個 `.py`，**沒有**複製 protocol JSON、沒有複製任何測試。
- 每一段輸出都是貼上來的實際 stdout，不是手寫的。
- 這些程式碼**沒有進版控**——它是外部專案該長的樣子，不是本 repo 的一部分。
  本 repo 對它們的保證仍然是 `backend/test_run_manifest_lock.py` 與
  `backend/test_exposure_identification.py`。

## 8. 你回報問題時該附什麼

`evaluate_run` 與 `evaluate_relocated_run` 回傳的 `detail` 欄位設計上就是要能貼出來的：
它會指名是哪一個檔案、哪一個 digest、哪一個框架。連同 `label` 一起附上即可。

**不要**把 `run_lock_binding.json` 改成「看起來對」的樣子再回報——那份記錄的每一個欄位
都是被重算的，改它只會把一個有標籤的失敗變成另一個。
