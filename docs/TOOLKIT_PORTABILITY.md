# 實驗工具組的邊界與可攜性

ID：`MODULE-BOUNDARY-V1`（toolkit 邊界）｜ 日期：2026-09-17
｜ 性質：**工程規範與 fail-closed 契約**，加上一份**可攜性審計**；不是 protocol、不是 receipt

登錄檔：[`backend/module_boundary_registry.json`](../backend/module_boundary_registry.json)
｜ 檢查程式：[`backend/module_boundary_contract.py`](../backend/module_boundary_contract.py)
｜ 測試：`backend/test_module_boundary_contract.py`
｜ 另一個邊界：[TEACHING_BOUNDARY](TEACHING_BOUNDARY.md)

```
python3 -I -S backend/module_boundary_contract.py          # 兩個邊界都檢查，不乾淨則 exit 1
python3 -I -S backend/module_boundary_contract.py --list   # 列出兩個閉包與行數
```

---

## 1. 這份文件同時回答兩個問題，而且答案不一樣

[PROJECT_ASSESSMENT §4.1](PROJECT_ASSESSMENT_2026-09-16.md) 說這個 repo 裡有**第二個產品**：
一套可複用的實驗工具組，別人的 RL 專案可以拿去用。

那個宣稱其實是兩件事，2026-09-17 分別量過：

| 問題 | 結果 |
|---|---|
| **它有沒有反過來依賴這個專案？**（import 邊界） | **沒有。乾淨，而且現在被契約守著。** |
| **外面的人今天拿得走嗎？**（可攜性） | **拿不走。七個模組裡只有一個可以原封不動使用。** |

**這兩件事必須分開講，否則綠燈會被讀成第二件事。**
契約檢查的是第一件；第二件是本文件 §4 起的審計，**沒有**任何自動檢查在守它。

## 2. 為什麼是一般化，不是再寫一個契約

教學邊界先做（`TEACHING-BOUNDARY-V1`）。工具組邊界的規則**逐字相同**：
一個產品的遞移本地 import 閉包，必須恰好等於它登錄的模組清單。

再寫一份幾乎相同的契約，就會犯下這個專案剛用兩個 PR 打掉的那個型態——
**同一個事實兩份實作**（見 [GATE_STATUS_SINGLE_SOURCE](GATE_STATUS_SINGLE_SOURCE.md)、
[DERIVED_CLAIM_CONSISTENCY](DERIVED_CLAIM_CONSISTENCY.md)）。
所以登錄檔改成多邊界，`TEACHING-BOUNDARY-V1` 由 `MODULE-BOUNDARY-V1` 取代，**程式只有一份**。

依先立後撤，`TEACHING-BOUNDARY-V1` 這個 ID 沒有被當成沒發生過：它記在新登錄檔的 `purpose`、
契約 docstring，以及 [TEACHING_BOUNDARY §0](TEACHING_BOUNDARY.md) 裡。

## 3. 量到的是一個**不對稱**，這才是重點

兩個邊界指向相反方向：

| 邊界 | 擋的方向 | 強度 |
|---|---|---|
| teaching | 應用**不得向上**碰研究模組 | 研究模組不得進入應用閉包 |
| **toolkit** | 函式庫**不得向外**碰這個專案的任何東西 | **嚴格更強：閉包裡除了它自己什麼都沒有** |

2026-09-17 實測：

```
toolkit 閉包 ＝ 恰好 7 個模組、5,300 行，本地相依為零
              environment_lock  experiment_matrix_contract  exposure_identification
              paired_statistics_contract  paper_data_contract  rl.bind_run_lock
              run_manifest_lock

反方向       ＝ 13 個非測試專案模組 import 它
              build_paired_statistics_regression_bundle、build_training_seed_variance_bundle、
              build_training_seed_variance_regression_bundle、build_v1_analytical_bundle、
              build_v1_paper_bundle、rl.retain_tracked_lineage_checkpoints、
              rl.run_tracked_lineage_v2_contract、rl.second_case_budget_probe、
              rl.second_case_runner、run_r0_regime_probe、second_case_exposure_contract、
              training_seed_variance_contract、v7_candidate_selection_contract
```

**工具組已經坐在相依圖的最底層**——那正是函式庫該待的位置。
契約的作用不是把它搬過去，而是**讓它留在那裡**：哪天某個工具組模組 import 了專案的東西，測試就是紅的。

（測試斷言的是下限 10 而不是 13。新增一支 bundle 腳本是合法的第 14 個依賴者，不該讓它變紅；
掉到個位數才代表登錄檔的註記過期了。）

## 4. 可攜性審計：邊界乾淨 ≠ 拿得走

以下是 2026-09-17 對七個模組逐一審計的結果。
**分類標準**：*blocking* ＝ 外部專案不改本專案的程式碼就無法使用；*friction* ＝ 能用，但難用或要多做事。

| 模組 | 行數 | 第三方 | 今天可攜？ | 阻斷項 |
|---|---:|---|---|---|
| `exposure_identification` | 312 | 無（stdlib） | **可以** | 0（只有 friction） |
| `environment_lock` | 1,366 | mujoco/numpy/torch**（皆惰性）** | **可以，功能退化** | 0（只有 friction，見 §5） |
| `run_manifest_lock` | 619 | 無（stdlib） | 大致可以 | 0 blocking；1 個 bug，見 §6 |
| `rl.bind_run_lock` | 133 | 無（stdlib） | **不行** | 4（見 §5.3） |
| `paired_statistics_contract` | 1,780 | pydantic | **不行** | 2 |
| `experiment_matrix_contract` | 758 | pydantic | **不行** | 2 |
| `paper_data_contract` | 332 | pydantic | **不行** | 2 |

阻斷項可以歸成三類，**而三類的「誰能決定」完全不同**。

## 5. 三類阻斷

### 5.1 平坦兄弟 import（可修，是純工程問題）

七個模組裡有四個用平坦的兄弟 import，預設自己躺在 `sys.path` 上：

| 位置 | 內容 |
|---|---|
| `experiment_matrix_contract.py:22` | `from paper_data_contract import (...)` |
| `paired_statistics_contract.py:24,29` | `from experiment_matrix_contract import (...)`、`from paper_data_contract import (...)` |
| `run_manifest_lock.py:338,376,452` | `import environment_lock as el`（函式內，但仍是平坦名稱） |
| `rl/bind_run_lock.py:43-46` | `REPO_ROOT` 由 `__file__` 往上推兩層，並 `sys.path.insert(0, BACKEND)` |

外部專案把這些檔案拷進自己的 package 之後，這些 import 全部斷掉——除非他把 `backend/` 整個放進 `sys.path`，
而那等於把這個專案的**全部** 60 幾個模組名稱倒進他的命名空間。

**這一類我可以修**（改成 package-relative import ＋ 一個 `__init__.py`），但它會動到
`run_manifest_lock.py` 與三個 contract 模組的 import 行，而這些模組被 13 個依賴者與整套測試覆蓋。
**不在本次範圍**：本次只把邊界變成被檢查的事實，見 §8。

### 5.2 封閉 `Literal` 詞彙與凍結的 claim boundary（**這是擁有者的決定，我不做**）

三個 contract 模組把**這個專案的證據範圍**寫死在型別裡：

| 位置 | 內容 | 對外部專案的意思 |
|---|---|---|
| `experiment_matrix_contract.py:212` | `evidence_scope: Literal["SIM_ONLY_MUJOCO"]` | 不是 MuJoCo 就無法通過驗證 |
| `paired_statistics_contract.py:156` | `evidence_scope: Literal["SIM_ONLY_MUJOCO"]` | 同上 |
| `experiment_matrix_contract.py:40,257` | `claim_boundary` 必須**逐字等於** `FROZEN_CLAIM_BOUNDARY` | 外部使用者得照抄本專案的主張邊界句 |
| `paper_data_contract.py:54-70` | `role: Literal[...]` 16 個值的封閉清單 | 多一種 artifact 角色（video、dataset…）就失敗 |
| `experiment_matrix_contract.py:63`、`paper_data_contract.py:159` | `controller_family: Literal[...]` 4 個值 | 非這四類的控制器無法登錄 |

**這些不是疏忽，是這個專案最重要的防線。** `FROZEN_CLAIM_BOUNDARY` 寫著
「SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED；只宣稱矩陣清單身分，不宣稱控制器優越性、
sim-to-real、物理保真或安全性」——**這句話能被逐字檢查，正是這個專案不會誇大主張的機制之一。**

把它放寬以換取可攜性，是在**動凍結的主張邊界**。
**這是專案擁有者的決定，不是我的。** 我把選項寫在 §8，沒有動任何一個字。

（`paper_data_contract.py:152` 的 `evidence_scope` 是 `SIM_ONLY_MUJOCO/SIL/HIL/BENCH/ROBOT` 五值，
本來就比較通用；`paired_statistics_contract.py:157` 的 `claim_boundary` 只限長度、不做等值比對。
**不是每一處都一樣硬**，這個差異在做決定時有用。）

### 5.3 凍結的 producer 登錄檔（`rl.bind_run_lock`）

`rl/bind_run_lock.py` 的 `_producer_entry()` 會去
[`run_manifest_lock_binding_protocol.json`](../backend/run_manifest_lock_binding_protocol.json)
的 `producers_in_scope` 找 producer，找不到就 fail closed。那份清單裡是**四個寫死的 repo 相對路徑**：

```
backend/rl/train_ppo.py            SIDECAR_ONLY          （理由：改它會讓已執行 protocol 的 digest 變假）
backend/rl/eval_policy.py          SIDECAR_ONLY          （理由同上，另一份 protocol）
backend/build_v1_paper_bundle.py   EMBEDDED_AND_SIDECAR
backend/build_v1_analytical_bundle.py  EMBEDDED_AND_SIDECAR
```

外部專案的 driver **不可能**在這份清單裡，所以 `bind_run_lock.py` 對外部使用者是 100% 擋死的。
這一項的 fail-closed **是對的**：binding mode 與理由必須來自凍結的 protocol，不能由呼叫端自由填寫。
要可攜，需要的是**讓外部專案能提供自己的 producer 登錄檔**，而不是放寬這個檢查。

另外三項：`REPO_ROOT` 由 `__file__` 往上推兩層（§5.1）、`sys.path` 注入（§5.1）、
`--require-full-lock` 的語義綁在 protocol §6.2。

**審計中另外發現一件事**：producer 登錄檔的 `manifest_schema` 欄位（例如 `RL_TRAINING_RUN_V2`）
**從來沒有被任何程式讀過**——全 repo grep 只有它自己那份 JSON 出現這個鍵。
`bind_run_lock.py:111` 記進 binding record 的是**manifest 自己宣告的** `schema_version`，
不是登錄檔期望的那個。兩者不一致時沒有東西會說話。
這是一個**被凍結卻沒有被強制的欄位**，記在這裡，不在本次修。

## 6. 審計中逐字驗證的兩個 bug

這兩個我親自重讀原始碼確認過，不是轉述。

### 6.1 `backend/environment_lock.py:425`——`learning_fingerprint()` 改動全域 torch RNG

```python
torch.set_num_threads(1)
torch.manual_seed(LEARNING_PROBE_SEED)      # <-- 全域
stream = torch.rand(8)
```

**對本專案不咬人**：`rl/second_case_runner.py` 在 `build_model` 時把 `seed=` 明確傳給 SB3，
會重新設種，所以量測順序不影響結果。
**對外部使用者會咬人**：任何在同一個 process 裡先跑 fingerprint、再依賴自己 RNG 狀態的程式，種子會被悄悄換掉。

**但它不能就這樣修。** 改用 `torch.Generator` 區域產生器會**改變 fingerprint 的值**，
而目前有 **41 份已提交的 lock record** 釘著現在這個值。
修它＝讓 41 份 receipt 全部失效。**這是擁有者的決定**（選項見 §8）。

### 6.2 `backend/run_manifest_lock.py:530`——未防護的 `relative_to`

同一份檔案裡，建立路徑有防護、檢查路徑沒有：

```python
# 384（建立）：有防護
if not target.is_relative_to(run_root):
    raise RunLockBindingError(f"{label} must live inside the run root: {target}")

# 530（檢查）：沒有
actual = manifest_path.resolve().relative_to(run_root).as_posix()
```

`evaluate_run()` 碰到一個指向 run root 之外的 symlink 時，會丟**未捕捉的 `ValueError`**，
而不是回傳一個 typed label。對一個以「每種失敗都有一個標籤」為設計前提的 fail-closed 契約來說，
這是一個**沒有標籤的失敗路徑**。

修法很小（`is_relative_to` 防護 ＋ 回傳既有的 `LABEL_MISMATCH` 或新增一個標籤），
但新增標籤會動到 `LB-09`「五個標籤各有正控制」的驗收判準，所以**也需要一個決定**：
是歸進現有標籤，還是開第六個。

（**2026-09-18 更正：上一段把選項說錯了，而且這件事根本不需要擁有者決定。**
上段寫「歸進 `LABEL_MISMATCH` 或開第六個標籤」，並在 §8 建議前者。
**兩個都不對。** 凍結規格
[RUN_MANIFEST_LOCK_BINDING_SPEC](RUN_MANIFEST_LOCK_BINDING_SPEC.md) §7.1 的標籤表，
`RUN_LOCK_BINDING_METHOD_FAILURE` 那一列**逐字列舉「路徑逃逸」**；
`RUN_LOCK_MISMATCH` 則只涵蓋兩個 disjunct——digest 不符，或 `bound_manifest_path` 指向別的檔案。
實測逃逸 symlink 的情形：**manifest bytes 與 `bound_manifest_sha256` 逐位元相符，
declared 路徑相對於該 run 自己的 root 也是對的**——兩個 disjunct 都**可量測地為假**，
所以標成 MISMATCH 會是 §7.2 明文禁止的降級。正確答案凍結規格早就寫好了。
原措辭依先立後撤保留在上方。實際修法見 §6.3。）

### 6.3 上面兩個 bug 中的第二個已於 2026-09-18 修掉——而且它比原本記的更嚴重

**修的是「沒有標籤」這件事本身，不是換一個標籤。** `evaluate_run` 現在對逃逸丟
`RunLockBindingError`，由它自己的 `except` 標成 `RUN_LOCK_BINDING_METHOD_FAILURE`。
**沒有新增第六個標籤，沒有動任何凍結值，兩份 digest-pinned 檔案逐位元未動。**

審計過程中量到三件上面沒有記的事：

| 量到的 | 原本以為 | 實測 |
|---|---|---|
| **觸發條件比 symlink 廣** | 只有逃逸 symlink | **run_dir 本身在宣告 root 之外**、以及**呼叫端傳入含 `..` 的 `manifest_filename`（完全不需要 symlink）**，都走同一條未捕捉的 `ValueError` |
| **`evaluate_relocated_run` 更糟** | 沒提到它 | 它沒有 `relative_to`，所以不會 crash——但一個「binding record ＋ 指向目錄外的 manifest symlink」的保留目錄，**回傳 `RUN_LOCK_BOUND`**。那是**假 PASS**，出現在唯一一個專門判斷保留證據的函式上 |
| **`Path.resolve()` 的 symlink 迴圈丟 `RuntimeError`** | 沒提到 | 而 `RunLockBindingError` **正是 `RuntimeError` 的子類**，所以 `except RunLockBindingError` 看起來涵蓋它、實際上放它過去。這是三條裡最難看出來的一條 |

三條加上 `sha256_file` 的 `OSError` 一併標籤化。**`sha256_file` 那條是 argument-from-code，不是量到的**——
這個容器以 euid 0 執行，`chmod 000` 的檔案照樣讀得到，所以無法重現，記在這裡而不宣稱已量測。

**刻意沒有做的兩件事**，因為審計中兩個「假 PASS」的宣稱**被實測推翻**：

- 宣稱「`manifest_filename` 含 `..` 會產生假 `RUN_LOCK_BOUND`」——**假的**。實測回傳
  `RUN_LOCK_MISMATCH`，訊息正確。因此**沒有**加 `safe_relative_path(manifest_filename, ...)`：
  那會把一個本來就正確的標籤改掉，而背後沒有缺陷。
- 宣稱「root 內指向別處的 symlink 會產生假 `RUN_LOCK_BOUND`」——**也是假的**，實測為 `RUN_LOCK_MISMATCH`。

**仍然沒有修、需要另一個決定的**：`evaluate_run` **從來不重算 lock record**——
刪掉或改壞 `environment_lock.json`，該 run 仍是 `RUN_LOCK_BOUND`。
規格與 protocol 都把「lock record 讀不到或 `validate_lock_record` 失敗」列為 METHOD_FAILURE 條件，
但分析期 gate 沒有實作它。**那是「少一個檢查」，不是「有一條沒標籤的路徑」**，
範圍與本次不同，記為任務 #95。

## 7. 先立後撤：我原本的假設是錯的

**我先前對使用者說**，`environment_lock` 裡 top-level 的 `mujoco`／`numpy`／`torch` import
是可攜性上最致命的問題。**這句話是錯的，而且是被實測推翻的。**

實際量到（AST ＋ 在無 site-packages 的 `python3 -I -S` 下實際載入）：

- `environment_lock.py` 的 **top-level import 全部是 stdlib**；
- `numpy`（:356）、`mujoco`（:382）、`torch`（:418, :532, :541）**全部在函式內，而且全部包在 `try/except` 裡**；
- 在 `python3 -I -S` 下 `import environment_lock` **成功**，三個重套件一個都沒進 `sys.modules`。

所以 `environment_lock` 在沒有 MuJoCo 的機器上**可以 import、可以用**，
只是三個對應的 fingerprint 會回報 unavailable——那是**功能退化，不是阻斷**。

依先立後撤，錯的說法留在上面，更正放在旁邊。這條記在這裡是因為它有用：
**「重套件 import」是個看起來很像答案的答案，而這次量出來它不是。**

## 8. 要決定什麼——以及誰決定

我**沒有**動下列任何一項。它們都需要擁有者先做決定：

| # | 決定 | 代價 | 我的建議 |
|---|---|---|---|
| 1 | `Literal["SIM_ONLY_MUJOCO"]` 是否放寬 | 動到凍結的主張邊界 | **不要直接放寬。** 改成外部專案提供自己的詞彙表（登錄檔 ＋ 預設值就是現在這份），本專案的值一個字都不變 |
| 2 | `FROZEN_CLAIM_BOUNDARY` 等值比對是否改為「可設定的凍結句」 | 同上 | 同上：把「必須等於某個凍結句」與「那句話是什麼」分開 |
| 3 | `learning_fingerprint()` 的全域 RNG（§6.1） | 修＝41 份 lock record 失效 | **不修**，改為在文件與 docstring 明寫這個副作用；若哪天要修，必須當成一次 fingerprint 版本升級 |
| 4 | ~~`relative_to` 未防護（§6.2）~~ **已於 2026-09-18 修掉，見 §6.3** | ~~可能要動 `LB-09`~~ **`LB-09` 未動，只加正控制測試** | ~~**修**，歸進現有 `LABEL_MISMATCH`，不開第六個標籤~~ **這個建議是錯的**：凍結規格 §7.1 已把「路徑逃逸」列在 `METHOD_FAILURE`，不需要擁有者決定。原措辭依先立後撤保留 |
| 5 | producer 登錄檔可否外部提供（§5.3） | 需要新的 API 面 | 可做，但屬於「抽成套件」那一步，不是現在 |
| 6 | 平坦兄弟 import 改成 package-relative（§5.1） | 動 4 個模組的 import 行 | 可做，且應該在**真的要搬檔案**時一起做 |

## 9. 明確不在範圍內

| 不涵蓋 | 為什麼 |
|---|---|
| **可攜性本身沒有自動檢查** | §4 起是一份**審計**，日期 2026-09-17。契約只檢查 import 邊界；綠燈**不代表**可攜 |
| `backend/test_*.py` | 測試可以 import 任何東西；測試不是出貨的產品 |
| 需要哪些 PyPI 套件 | 打包問題，不是邊界問題 |
| **檔案沒有搬** | 本次只把邊界變成被檢查的事實；§4.1 的「搬」是下一步 |
| 對外的使用說明書 | 見任務 #92；先有這份審計，才知道說明書上要寫什麼做不到 |

## 10. 加一個工具組模組的步驟

1. 寫程式，確認它**不 import 這個專案的任何模組**（工具組閉包裡只准有工具組自己）。
2. 把模組名加進 `backend/module_boundary_registry.json` 的 `boundaries.toolkit.modules`
   （若它是獨立入口，也加進 `entry_points`）。
3. 跑 `python3 -I -S backend/module_boundary_contract.py`，直到輸出 `MODULE_BOUNDARIES_CLEAN`。
4. **順便看一眼 §4 那張表**：新模組是 blocking 還是 friction？沒有東西會自動告訴你。
