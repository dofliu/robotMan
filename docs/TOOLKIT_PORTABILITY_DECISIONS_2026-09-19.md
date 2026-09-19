# 工具組可攜性：六項決定的結案記錄

ID：任務 #93 ｜ 日期：2026-09-19
｜ 性質：**決定記錄與量測更正**；不是 protocol、不是 receipt、不是新的契約

上游：[TOOLKIT_PORTABILITY](TOOLKIT_PORTABILITY.md) §8（2026-09-17 記下六項待決）
｜ **§3 的四個問題已於 2026-09-19 由擁有者回答，四項皆為「維持現狀」，見 §3 開頭**
｜ 對外說明書：[TOOLKIT_USAGE](TOOLKIT_USAGE.md)
｜ 凍結規格：[RUN_MANIFEST_LOCK_BINDING_SPEC](RUN_MANIFEST_LOCK_BINDING_SPEC.md)、[ENVIRONMENT_LOCK_SPEC](ENVIRONMENT_LOCK_SPEC.md)

---

## 0. 一句話

**六項裡有三項不需要擁有者決定——因為量測把它們的前提推翻了。**
剩下的四個問題比原本記的更小、也更清楚。

§8 把六項全部歸類為「擁有者的決定」。2026-09-19 逐項重新量測後：
決定 3 的**代價是假的**，決定 5 的**問題已經被解決了**，決定 6 的**建議方向是錯的**。
這三項寫在 §2，連同它們的量測。真正還在等擁有者的四個問題寫在 §3。

**沒有動任何凍結值。** 沒有改任何 digest-pinned 檔案，沒有改 `FROZEN_CLAIM_BOUNDARY`，
沒有改五個 `RUN_LOCK_*` 標籤，沒有改 `LB-01`–`LB-13`，沒有改任何 `Literal` 詞彙。

**2026-09-19 補記：§3 的四個問題已由擁有者回答，四項皆選「維持現狀」。**
結果與本文件建議的預設相同，因此**沒有任何後續程式改動**——但
「**已回答、選擇維持現狀**」與「未回答、依預設維持現狀」是兩個不同的事實，所以記在這裡。

---

## 1. §8 的六項，量測後的現況

| # | §8 記的 | 量測後 | 誰決定 |
|---|---|---|---|
| 1 | `Literal["SIM_ONLY_MUJOCO"]` 是否放寬 | 站點比記的多（4 處 vs 2 處），且**這套詞彙目前並沒有全 repo 生效** | **已答 2026-09-19：維持現狀**（§3 問題 A） |
| 2 | `FROZEN_CLAIM_BOUNDARY` 等值比對 | 比記的大：**兩個**凍結句、**五個**逐字比對點，且 §5.2 的括號註記被推翻 | **已答 2026-09-19：維持現狀**（§3 問題 B） |
| 3 | `learning_fingerprint()` 全域 RNG | **代價被推翻**：不是 41 份 receipt 失效，是 **0 份**。但建議的 docstring 從來沒寫 | docstring **已做**（§2.1）；**已答 2026-09-19：探針維持現狀**，`ENVIRONMENT_LOCK_SPEC.md:92` 不動（§3 問題 C） |
| 4 | `relative_to` 未防護 | 2026-09-18 已修（PR #40、#41） | — |
| 5 | producer 登錄檔可否外部提供 | **可攜性那一半已經解決了**，而且不需要 API 面（§2.2） | **已答 2026-09-19：不放寬** SPEC §3.1（§3 問題 D） |
| 6 | 平坦兄弟 import 改 package-relative | **方向相反**：這麼做會弄壞剛發布的安裝方式（§2.3） | **不要做**，已寫成測試 |
| ＋ | `manifest_schema` 從未被讀 | **不是漏掉一個檢查**，是一份有損的抄本（§2.4） | 不強制；不編輯登錄檔 |

---

## 2. 量測答掉的四件事

### 2.1 決定 3：代價是 0 份 lock record，不是 41 份

§8 第 3 列把代價記成「修＝41 份 lock record 失效」，並據此建議不修。
**兩個前提都是假的。**

**前提一：「目前有 41 份已提交的 lock record 釘著現在這個值」。**

| 數的是什麼 | 數量 |
|---|---:|
| **已提交的 `ENVIRONMENT_LOCK_RECORD_V1` 記錄** | **20** |
| 已提交、內文含該 `rng_sha256` 的**檔案** | 21（20 份記錄 ＋ 1 份 markdown receipt） |
| **磁碟上**含該值的檔案 | 41（多出的 20 份在 `.gitignore:31` 排除的 `backend/rl/artifacts/`） |

```
$ git ls-files | (parse every .json where schema_version == ENVIRONMENT_LOCK_RECORD_V1)
COMMITTED ENVIRONMENT_LOCK_RECORD_V1 files: 20
distinct learning_fingerprint tuples: 1
```

**41 是磁碟 grep 數，不是已提交記錄數。**
這與 [TOOLKIT_PORTABILITY §6.6](TOOLKIT_PORTABILITY.md) 更正過的「35 vs 15」是**同一個型態的錯誤**，
在同一份文件裡犯了第二次。

**前提二：「改用 `torch.Generator` 區域產生器會改變 fingerprint 的值」。**
在所有 20 份記錄都釘著的那個 torch 版本（2.14.0+cu130）上實測，**兩個變體逐位元相同**：

```
variant A (global manual_seed): sha256:a8224af9d2333d4d2287f0fd29745aa1bcb9227d056214825382a5d1bff6b096
variant B (torch.Generator)  : sha256:a8224af9d2333d4d2287f0fd29745aa1bcb9227d056214825382a5d1bff6b096
A==B: True | both == committed pin: True
```

全新 process、未曾呼叫過 `torch.manual_seed` 的情況下也相同；整份記錄的
`locked_sha256`（`sha256:d350a110…fa3d7c`）代入變體 B 後仍逐位元不變。
**所以「修它＝讓 41 份 receipt 全部失效」量測為 0 份失效。**

**但這不代表該修，而且原因是新量到的：`torch.Generator` 只修掉一半。**

```
caller draw without Linear: 0.9817181825637817
caller draw with    Linear: 0.8873135447502136   STREAM DISTURBED: True
```

`learning_fingerprint()` 有**兩個**獨立的全域 RNG 擾動點，不是一個：
`torch.manual_seed`（:425，換掉種子）與 `torch.nn.Linear`（:429，**自己從全域預設產生器抽初始化**）。
今天 `manual_seed` 的重設遮住了第二個。只把 :425 換成區域產生器，
種子不再被換掉，但呼叫端的**串流仍然被悄悄推進**——那是個看起來像修好的半修。

**已做（不需要決定）**：§8 自己建議的「在 docstring 明寫這個副作用」**從來沒有做**。
量測：`grep -i "side effect\|global\|mutat\|restore"` 掃過 `environment_lock.py` 全部 1,366 行，**零個命中**。
本次補上，**兩個擾動點都寫進去**，並用兩個測試把它釘住（見 §4）。

**剩下的**是一個比原本記的小得多的決定，見 §3 問題 C。

### 2.2 決定 5：可攜性那一半已經解決，而且代價不是「新的 API 面」

§8 第 5 列把代價記成「需要新的 API 面」。**推翻**：
`build_binding_record` 早就把 `binding_mode` 與 `sidecar_reason` 當成普通關鍵字參數收
（`run_manifest_lock.py:484-485`），外部登錄檔要供的就是這兩個值，不需要任何新介面。

更要緊的是：**外部專案根本不必碰那份登錄檔。**
[TOOLKIT_USAGE](TOOLKIT_USAGE.md) §4 的三呼叫流程
（`capture_lock_for_run` → `build_binding_record` → `evaluate_run`）
在一個**沒有那份 protocol JSON 的目錄**裡跑得完，全程 0 次開啟該檔。
`rl/bind_run_lock` 對外關死仍然成立，但**沒有人需要它**。

因此 §5.3 的結論「要可攜，需要的是讓外部專案能提供自己的 producer 登錄檔」
**是錯的**：可攜性不需要它。真正還沒解決的是另一件事，見 §3 問題 D。

### 2.3 決定 6：方向相反，不要做——已經寫成測試

§8 第 6 列說「可做，且應該在真的要搬檔案時一起做」；§5.1 稱它為「純工程問題」。
**兩句都被量測推翻。**

把三個兄弟 import 改成 `from . import environment_lock as el`，照
[TOOLKIT_USAGE §2](TOOLKIT_USAGE.md) 發布的平坦安裝方式擺好，實測：

```
import OK, __package__ = ''
FAILED: ImportError attempted relative import with no known parent package
```

**import 成功，第一次真的呼叫才爆。** 這是最難看的失敗型態——
使用者會以為安裝好了。在同一個平坦目錄裡加 `__init__.py` 也救不回來。

§5.1 寫於說明書之前，當時把平坦 import 當成**待移除的缺陷**；
2026-09-19 發布的 §2 把它當成**官方安裝機制**並用兩個測試背書。
兩者作為計畫是**互相矛盾**的，本次以量測結果為準：**平坦兄弟 import 留著**，
並新增 `test_the_toolkit_modules_stay_flat_vendorable` 把它變成被檢查的事實。

**順手量到一個真的洞，而且比決定 6 本身重要。**
`module_boundary_contract.imported_names` 只讀 `node.module`、從不讀 `node.level`，
所以 `from . import X` **對閉包完全隱形**。負控制：

```
OLD extractor: NO ERROR RAISED -> MODULE_BOUNDARIES_CLEAN   <-- blind
NEW extractor: CAUGHT -> 5 module-boundary violation(s) ...
```

——一個工具組模組用 `from . import simulator` 伸進教學產品，
**舊的檢查照樣印出 `MODULE_BOUNDARIES_CLEAN`**。那是 fail-closed 契約裡的 fail-open。
今天全 repo **0 處**相對 import，所以修它對現有閉包**可證明是 no-op**；
這正是現在修的理由：**在決定 6 有可能讓它變成承重之前就關掉。**

### 2.4 `manifest_schema`：不是漏掉一個檢查，是一份有損的抄本

登錄檔為 `eval_policy.py` 釘的是單一值 `RL_TRAINING_ENV_EVALUATION_V4`。
實測全部 35 份 binding record（用 `sidecar_reason` 逐字回推 producer）：

| tracked | producer | 登錄檔 `manifest_schema` | 記錄的 `bound_manifest_schema_version` | 相符 | n |
|---|---|---|---|---|---:|
| 是 | `eval_policy.py` | `…_V4` | `…_V3` | **否** | 10 |
| 是 | `train_ppo.py` | `RL_TRAINING_RUN_V2` | `RL_TRAINING_RUN_V2` | 是 | 5 |
| 否 | `eval_policy.py` | `…_V4` | `…_V3` | **否** | 10 |
| 否 | `train_ppo.py` | `RL_TRAINING_RUN_V2` | `RL_TRAINING_RUN_V2` | 是 | 10 |

**若照字面實作等值檢查，35 份裡有 20 份會變紅（已提交的 15 份裡有 10 份）——而它們全都是對的。**

三件事一起判定不該強制：

1. **凍結規格自己就記著兩個值。** [SPEC §3.1](RUN_MANIFEST_LOCK_BINDING_SPEC.md) 第 2 列寫
   `RL_TRAINING_ENV_EVALUATION_V4／V3`。`eval_policy.py:475,678` 也確實是
   **有 `--pilot-arm` 才發 V4，否則發 V3**。登錄檔的單一值是**規格那個雙值事實的有損抄本**。
   同一份 protocol 的 `enforcement_scope.unchanged_contracts`（:64）也寫著
   「`RL_TRAINING_ENV_EVALUATION_V3 and V4`」——**這份檔案自己前後不一致**。
2. **規格沒有要求這個檢查。** 裸的 `manifest_schema` 在整份 SPEC 出現 **0 次**；
   `LB-01`–`LB-13` 沒有一條提到它。SPEC §4.1（:148）把
   `bound_manifest_schema_version` 定義為「**被綁 manifest 自身的** `schema_version`」，
   而 `bind_run_lock.py:111` 記的正是那個。**記錄是合規的。**
3. **編輯登錄檔的代價不小。** 它被 `run_manifest_lock.py:58` 的 `PROTOCOL_SHA256` 釘住，
   由 `:360` 在執行期強制（改一個 byte，未同步更新 pin 之前**每一個呼叫端都會 raise**），
   `test_run_manifest_lock.py:76` 重算它，該 digest 另外出現在
   `STATUS.yaml`、`CHANGELOG.md`、`RUN_MANIFEST_LOCK_BINDING_RECEIPT_2026-09-13.md` 的散文裡。

**本次的處置：不強制、不編輯登錄檔、把這個不一致記在這裡。**
這在型態上屬於 [DERIVED_CLAIM_CONSISTENCY](DERIVED_CLAIM_CONSISTENCY.md) 管的那一類
（一份推導抄本與其來源不符），只是目前那個契約沒有涵蓋 protocol JSON 的欄位。

**另外兩件記下不修的**：binding record **沒有 `producer` 欄位**，
所以登錄檔那一列只能靠 `sidecar_reason` 逐字回推；
兩個 `EMBEDDED_AND_SIDECAR` producer 的 `sidecar_reason` 是 `null`，**完全無法回推**
——而它們兩個目前在全 repo **0 份** binding record。

---

## 3. 真正還在等擁有者的四個問題

**2026-09-19 已全部回答：四項皆為「維持現狀」。** 每一題下方保留當時提出的量測與選項，
答案記在各題最後一行。四個答案都與本文件的建議相同，因此**沒有觸發任何後續改動**。

### 問題 A — 外部專案要不要能用自己的 `evidence_scope` 詞彙？

**現況比 §5.2 記的廣。** 單值 `Literal["SIM_ONLY_MUJOCO"]` 有**四處**，不是兩處：
`experiment_matrix_contract.py:212`、`paired_statistics_contract.py:156`、**`:259`**、**`:369`**。
`role` 有三處（`paper_data_contract.py:54-70`、**`paired_statistics_contract.py:87`**、**`:301`**），
不是一處。`paper_data_contract.py:152` 確實較寬（五值），§5.2 這點是對的。

**而這套詞彙目前並沒有全 repo 生效**：24 份已提交、帶 `evidence_scope` 的 JSON 裡，
只有 8 份寫 `SIM_ONLY_MUJOCO`；另外三個值
（`SOFTWARE_TRAINING_ENV_DEVELOPMENT_EVALUATION_ONLY` 10 份、
`SOFTWARE_TRAINING_PIPELINE_ONLY` 5 份、`DEVELOPMENT_TRAINING_CONFIGURATION_ONLY` 1 份）
**不在任何一個 `Literal` 清單裡**——它們由 `train_ppo.py`／`eval_policy.py`／`policy_registry.py`
以未驗證的 `str` 欄位寫出。所以「封閉詞彙是本專案的防線」這句話，
**只在三個 pydantic contract 模組的範圍內成立**。

**代價：對本專案為零。** 三個 contract 模組**沒有任何一個被 digest 釘住**，
也沒有任何釘 digest 的程式讀它們的 `Literal`。可以純增量地加一個
`open_vocabulary(model, field, additional)` 之類的工廠，本專案的模型一個字不變。

**建議**：做，但當成「抽成套件」那一步的一部分；**現在不需要為了可攜性做**
——[TOOLKIT_USAGE](TOOLKIT_USAGE.md) 已經證明外部使用者只需要三個模組，而這三個都不含這些 `Literal`。

**擁有者已答（2026-09-19）：維持現狀。** 外部使用者只需要三個可攜模組，而那三個都不含這些 `Literal`，
所以這一項不擋可攜性；若哪天真的抽成套件，再回到這裡。

### 問題 B — 「必須等於某個凍結句」與「那句話是什麼」要不要分開？

**比 §8 記的大。** 有**兩個**凍結句與**五個**逐字比對點：

| 凍結句 | 定義處 | 逐字比對點 |
|---|---|---|
| 157 字（矩陣） | `experiment_matrix_contract.py:40` | `:257` |
| 217 字（統計） | `paired_statistics_contract.py:51` | `:171`、`:295`、`:376`、`paired_statistics_replay.py:263` |

**並且 §5.2 的括號註記被推翻**：該處寫
「`paired_statistics_contract.py:157` 的 `claim_boundary` 只限長度、不做等值比對」。
`:157` 本身確實只有 `min_length`／`max_length`，但**同一個 model 的
`@model_validator`（`:171`）做逐字等值比對**。所以「不是每一處都一樣硬」這個結論，
對 `paired_statistics_contract` **不成立**——它和 `experiment_matrix_contract` 一樣硬。

**真正較軟的是另外兩處，而且這個差別有用**：
`run_manifest_lock.py:420` 只要求非空非空白字串（實測單一字元 `x` 可通過），
`paper_data_contract` 亦然。**外部使用者實際會碰到的那一個（`run_manifest_lock`）已經是開放的**
——這正是 [TOOLKIT_USAGE](TOOLKIT_USAGE.md) §2 能說「`claim_boundary` 可以是你自己的」的原因。

**建議**：同問題 A——不為可攜性而動，留給抽成套件那一步。
**擁有者已答（2026-09-19）：維持現狀。** 兩個凍結句與五個逐字比對點全部保留原樣；
外部使用者走的 `run_manifest_lock.py:420` 本來就只要求非空字串，該路徑已經是開放的。

### 問題 C — 要不要改 `ENVIRONMENT_LOCK_SPEC.md:92` 那一行凍結散文？

決定 3 的代價從「41 份 receipt」縮到**一行散文**：

```
docs/ENVIRONMENT_LOCK_SPEC.md:92
3. `learning_fingerprint`（torch）：`torch.manual_seed(0)` 後，對固定輸入跑一次
```

規格逐字寫著 `torch.manual_seed(0)`。要讓探針**完全**不擾動呼叫端 RNG，
得同時處理 `:425` 與 `:429` 兩個點，而那會讓程式與這一行規格文字不符。

**三個選項**：

1. **維持現狀 ＋ 文件（本次已做的）** — 零程式改動，副作用寫進 docstring 並由測試釘住。
2. **改探針、同步改規格那一行** — 量測顯示 fingerprint 值與 `locked_sha256` **不變**，
   20 份已提交記錄**全部不失效**。代價是動一份凍結規格的文字。
3. **當成 fingerprint 版本升級** — §8 原本的說法。**量測顯示不必**：值沒有變。

**建議：選項 1（本次已做）。**
理由是選項 2 雖然代價小，但它為了一個**本專案量測不到的**問題
（`second_case_runner.py` 在 `build_model` 時重設種子）去動凍結規格；
外部使用者的對策已經寫在 [TOOLKIT_USAGE §6](TOOLKIT_USAGE.md)。
**擁有者已答（2026-09-19）：維持現狀＋文件。** 探針不改，`ENVIRONMENT_LOCK_SPEC.md:92` 的
「`torch.manual_seed(0)` 後」一字不動；副作用由本次寫入的 docstring 與兩個測試承載。

### 問題 D — SPEC §3.1 的「逐 producer 凍結範圍」可否為 repo 外的 producer 放寬？

§2.2 已經說明：**可攜性不需要這個**。
剩下的是一個純粹的範圍問題——`rl/bind_run_lock` 本身要不要能被外部專案使用。

**代價與 §8 記的不同。** 不是「新的 API 面」，而是：
`run_manifest_lock.py:59` 的 `SPECIFICATION_SHA256`（`sha256:717bb910…`，由 `:369` 強制、
`test_run_manifest_lock.py:77` 重算）釘住一份規格，其 §3 標題是「**凍結的範圍**」、
§3.1 標題是「**逐 producer 的處置（凍結）**」。
**讓一個 repo 外的 producer 進來，等於在不動任何一個 byte 的情況下放寬那個凍結範圍。**
在一個把凍結值當成「只量測、不更動」的專案裡，那正是擁有者才能做的判斷。

**建議：不做。** 外部使用者有一條不需要它的路（那 31 行取代品），
而 `bind_run_lock` 的 fail-closed 本身是對的。
**擁有者已答（2026-09-19）：不放寬。** SPEC §3.1「逐 producer 的處置（凍結）」維持四個 producer，
`rl/bind_run_lock` 對外維持 100% 擋死。

---

## 4. 本次實際改了什麼

**程式（兩處，都不需要決定）**

| 檔案 | 改動 | 行為改變 |
|---|---|---|
| `backend/environment_lock.py` | `learning_fingerprint()` docstring 補上 SIDE EFFECT 段，**兩個擾動點都點名** | **無**（純 docstring） |
| `backend/module_boundary_contract.py` | `imported_names` 處理 `node.level`：`from . import X` 不再隱形 | 對現有樹**可證明是 no-op**（全 repo 0 處相對 import），對違規樹從假綠燈變成 fail |

**測試（＋5，37 ＋ 66 ＝ 兩個檔案各自的總數）**

| 測試 | 釘住什麼 |
|---|---|
| `test_a_relative_sibling_import_is_visible_to_the_closure` | 四種 import 形式都進閉包 |
| `test_a_toolkit_module_reaching_out_by_relative_import_is_caught` | 端到端：相對寫法的違規會被抓 |
| `test_the_toolkit_modules_stay_flat_vendorable` | **工具組模組不准出現相對 import**——直接保護 TOOLKIT_USAGE §2 的安裝方式 |
| `test_the_learning_probe_documents_its_global_rng_side_effect` | docstring 必須點名兩個擾動點與那個不對稱 |
| `test_the_probe_still_contains_both_documented_mutation_sites` | 反方向：程式若不再擾動，docstring 必須改 |

**沒有改的**：任何 digest-pinned 檔案、`FROZEN_CLAIM_BOUNDARY`、任何 `Literal`、
五個 `RUN_LOCK_*` 標籤、`LB-01`–`LB-13`、`producers_in_scope`、任何已提交的證據。

---

## 5. 先立後撤：本次推翻的先前說法

依專案慣例，錯的說法留在原處，更正放在旁邊。這裡是清單。

| 出處 | 原說法 | 量測 |
|---|---|---|
| TOOLKIT_PORTABILITY §6.1、§8 第 3 列 | 「41 份已提交的 lock record」 | **20 份**。41 是磁碟 grep 數 |
| 同上 | 「改用 `torch.Generator` 會改變 fingerprint 的值」 | **逐位元相同**，`locked_sha256` 亦不變 |
| 同上 | 「修＝讓 41 份 receipt 全部失效」 | **0 份失效** |
| TOOLKIT_PORTABILITY §6.1 | 副作用只有 `torch.manual_seed` 一處 | **兩處**，`torch.nn.Linear`（:429）自己抽全域 |
| TOOLKIT_PORTABILITY §5.2 括號 | 「`paired_statistics_contract.py:157` 只限長度、不做等值比對」 | 同 model 的 `:171` **做逐字等值比對** |
| TOOLKIT_PORTABILITY §5.2 表 | `evidence_scope` 兩處、`role` 一處 | **四處**、**三處** |
| TOOLKIT_PORTABILITY §5.3 | 「要可攜，需要的是讓外部專案能提供自己的 producer 登錄檔」 | 可攜性**不需要**它 |
| TOOLKIT_PORTABILITY §8 第 5 列 | 代價「需要新的 API 面」 | `build_binding_record` **已經**收這兩個參數 |
| TOOLKIT_PORTABILITY §5.1、§8 第 6 列 | 平坦 import 是缺陷，改成 package-relative「可做」 | 會**弄壞** TOOLKIT_USAGE §2 的安裝方式，且是遲發失敗 |
| TOOLKIT_PORTABILITY §5.3、§8 附記 | `manifest_schema` 是「被凍結卻沒有被強制的欄位」 | 是一份**有損抄本**；照字面強制會讓 20/35 份正確證據變紅 |
| TOOLKIT_PORTABILITY §3、§4 表 | 工具組 5,300 行、`run_manifest_lock` 619 行 | **5,505** 行（本次 ＋11）、**813** 行 |
| TOOLKIT_PORTABILITY §5.1 表 | 兄弟 import 在 `:338,376,452`；`bind_run_lock.py:43-46` | **`:457,495,571`**；**`:42-47`** |
| TOOLKIT_USAGE §6 | 「41 份已提交的 lock record 會失效」 | 同上，20 份且 0 份失效 |
| TOOLKIT_USAGE §4 | 取代品「約 20 行」 | **31 行**（26 行非空非註解） |

`STATUS.yaml` 與 `CHANGELOG.md` 裡鏡射上述數字的段落一併更正。

---

## 6. 明確沒有做、也沒有宣稱的

| 沒做 | 為什麼 |
|---|---|
| 沒有實作外部詞彙表／可設定凍結句 | 問題 A、B 是擁有者的；而且外部使用者用不到那三個模組 |
| 沒有改探針的 RNG 行為 | 問題 C；且半修比不修更糟（§2.1） |
| 沒有讓外部 producer 進登錄檔 | 問題 D |
| 沒有強制 `manifest_schema` | 會讓 20 份正確證據變紅（§2.4） |
| 沒有把檔案搬走 | [TOOLKIT_PORTABILITY §9](TOOLKIT_PORTABILITY.md) 的「搬」仍未做 |
| **可攜性仍然沒有自動檢查** | §4 起是審計。本次新增的三個測試只守「平坦可 vendor」與「相對 import 不隱形」兩件事，**不是**可攜性的全面檢查 |
| `validate_lock_record` 失敗那一半仍未實作 | 記在 [TOOLKIT_PORTABILITY §6.5](TOOLKIT_PORTABILITY.md)，範圍不同 |
