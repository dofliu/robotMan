# 教學模擬器的邊界

ID：`MODULE-BOUNDARY-V1`（teaching 邊界）｜ 日期：2026-09-17
｜ 性質：**工程規範與 fail-closed 契約**，不是 protocol、不是 receipt

登錄檔：[`backend/module_boundary_registry.json`](../backend/module_boundary_registry.json)
｜ 檢查程式：[`backend/module_boundary_contract.py`](../backend/module_boundary_contract.py)
｜ 測試：`backend/test_module_boundary_contract.py`
｜ 另一個邊界：[TOOLKIT_PORTABILITY](TOOLKIT_PORTABILITY.md)

```
python3 -I -S backend/module_boundary_contract.py          # 兩個邊界都檢查，不乾淨則 exit 1
python3 -I -S backend/module_boundary_contract.py --list   # 列出兩個閉包與行數
```

---

## 0. 本文件原本的 ID 是 `TEACHING-BOUNDARY-V1`

（**2026-09-17 更正**：本文件原本登錄為 `TEACHING-BOUNDARY-V1`，登錄檔
`backend/teaching_boundary_registry.json`、契約 `backend/teaching_boundary_contract.py`。
原措辭依先立後撤保留在此。）

拆[實驗工具組](TOOLKIT_PORTABILITY.md)時發現，工具組邊界的規則與本文件**逐字相同**：
一個產品的遞移本地 import 閉包，必須恰好等於它登錄的模組清單。
再寫一份幾乎相同的契約，就會犯下這個專案剛用兩個 PR 打掉的那個型態——**同一個事實兩份實作**
（見 [GATE_STATUS_SINGLE_SOURCE](GATE_STATUS_SINGLE_SOURCE.md)、
[DERIVED_CLAIM_CONSISTENCY](DERIVED_CLAIM_CONSISTENCY.md)）。

所以登錄檔改成多邊界、程式只留一份，ID 改為 `MODULE-BOUNDARY-V1`。
**規則、教學模組清單與下面所有量測結果一個字都沒有改**，只是檢查它的程式現在同時檢查兩個產品。

## 1. 這是「拆」的第一步，而且是可驗證的那一步

[PROJECT_ASSESSMENT §4.1](PROJECT_ASSESSMENT_2026-09-16.md) 說教學應用與研究基礎設施
**「在程式碼層面已經完全解耦」**、「拆開不需要重構，只需要搬」。

2026-09-17 實測：**13 個模組裡 12 個成立，1 行不成立。**

`main.py` 從 `rl/train_ppo.py` 取 `public_training_inventory`——
於是「列出訓練 profile」這個唯讀端點，拉進一個 **1,292 行的訓練驅動**，
再經由它拉進 `stable_baselines3`、`gymnasium`，以及該 profile schema 所驗證的**每一個凍結研究 protocol**。

那個宣稱**離真的只差一行**，而且**如果再多出一行，沒有任何東西會說話**。

本契約就是把那個宣稱從「宣稱」變成「被檢查的事實」。

## 2. 規則：一條等式

> 已登錄進入點的**遞移本地 import 閉包**，必須**恰好等於**已登錄的教學模組清單。

兩個方向都有用：

| 方向 | 意思 | 為什麼要擋 |
|---|---|---|
| 閉包 ⊄ 登錄 | **研究模組跑進教學產品** | 這就是邊界存在的理由 |
| 登錄 ⊄ 閉包 | **登錄清單過期** | 留著沒人載入的項目，等於哪天讓某個模組**無聲地**回來 |

錯誤訊息會給出**到達路徑**，不只是「有東西 import 了它」：

```
RESEARCH_MODULE_IN_TEACHING_CLOSURE: environment_lock
    reached by main -> live_sim -> controller -> environment_lock
```

## 3. 現況

**16 個模組、5,066 行**（`--list` 可列出；2026-09-22 重新量測——`controller_cp` 是
Capture-point 落腳法則的開發對照組，由 `live_sim` 載入，原為 15 個模組、4,943 行）：

```
compare_live  config_schema  controller  controller_cp  controller_raibert  controller_rl
gait  hardware_db  live_sim  main  model_builder  motion_tasks
rl.policy_registry  rl.training_inventory  run_trace  simulator
```

前端 18 個 TS/TSX 檔只經 HTTP／WebSocket 打 **5 個 REST 路徑與 2 個 socket**
（`/api/defaults`、`/api/simulate`、`/api/policies`、`/api/traces`、`/api/training/profiles`、`/ws/live`、`/ws/compare`），
因此**在結構上不可能** import 到研究模組。

## 4. 那一行是怎麼切掉的——以及為什麼不是用「把 schema 搬出來」

**顯而易見的重構被量測否決了。** 原本該把 `TrainingProfile` schema 從 `train_ppo.py` 搬進共用模組，
但它的 validator 會呼叫 `load_tracked_lineage_protocol()`，並比對
`TRACKED-LINEAGE-TRAINING-V1`／`V2` 與 seed-variance protocol——
**schema 與凍結的研究身分是糾纏的**，搬它等於把那個身分一起搬過邊界。

改用[唯讀投影](../backend/rl/training_inventory.py)：

- **`train_ppo.py` 逐位元未動。** 連 digest 的問題都不會發生——protocol 釘的是執行當下的 digest，本次沒碰它。
  （附帶一提，`LB-12` 自己的測試 `test_lb12_does_not_freeze_those_files_for_the_rest_of_the_repository`
  就是為了保證「日後合法編輯 `train_ppo.py` 不得讓契約變紅」，且 `ongoing_protection` 記為 `NONE`；
  我們仍選擇不動它，因為不需要。）
- **這是投影，不是第二份 schema。** `training_profiles.json` 仍是單一來源。
  `train_ppo.py` 為了**訓練**驗證它（這個 profile 是否符合它宣稱的凍結 protocol）；
  本模組為了**顯示**驗證它（端點要送的欄位在不在、型別對不對）。
  **唯讀端點沒有義務去重新驗證研究凍結**，而縮小教學應用的主張是安全的方向。
- **投影是精確的，不是近似的。** 送出的 payload 不是原始 JSON：pydantic 每個 profile 補 7 個欄位
  （`environment_id` 預設 `fixed_walk_v1`，其餘 6 個 `null`），且欄位依宣告順序輸出。
  測試**逐位元比對**本模組與 `train_ppo.public_training_inventory()` 的輸出（含鍵序），
  所以這次拆分是**被證明**行為不變，不是假設它不變。

唯讀投影對「顯示可能出錯」的方向 fail closed：缺必要欄位、型別錯、出現未知欄位，全部丟例外。
它**刻意不做**的是重跑研究 validator——真的要訓練時，`train_ppo.py` 仍然會做。

## 5. 邊界畫在「研究模組」，不是「第三方套件的重量」

教學閉包**確實** import `stable_baselines3`——經由 `controller_rl` 載入 PPO policy 給 Live 頁用。
**那是教學產品在做它該做的事**，不是研究相依。

`backend/rl/` 兩邊都有：`policy_registry`、`training_inventory` 是教學；
`train_ppo`、`eval_policy`、`humanoid_env` 與各 runner 是研究。
**這正是邊界用列舉、而不是用目錄畫的理由**——目錄畫不出這件事。

## 6. 明確不在範圍內

| 不涵蓋 | 為什麼 |
|---|---|
| `backend/test_*.py` | 測試可以 import 任何東西；**測試不是出貨的應用** |
| 教學產品需要哪些 PyPI 套件 | 那是打包問題，不是邊界問題 |
| 前端 | 只經 API 溝通，結構上不可能 import 研究模組 |
| **檔案還沒有搬** | 本次只切斷耦合並把邊界變成被檢查的事實；§4.1 的「搬」是下一步，見 §7 |

## 7. 這一步之後

邊界現在是**被驗證的事實**，所以後續無論要搬到 `teaching/` 目錄或另開 repo，
都只是**機械動作**：`--list` 就是那份清單，契約會在搬完後立刻告訴你有沒有漏。

本次**沒有**搬任何檔案，也沒有改任何 API。

## 8. 加一個教學模組的步驟

1. 寫程式，確認它**不 import 任何研究模組**。
2. 把模組名加進 `backend/module_boundary_registry.json` 的 `boundaries.teaching.modules`。
3. 跑 `python3 -I -S backend/module_boundary_contract.py`，直到輸出 `MODULE_BOUNDARIES_CLEAN`。

反過來，如果契約說某個研究模組進了閉包：**先想能不能切，而不是先想把它加進清單。**
把它加進清單是一個刻意的決定，而不是讓紅燈變綠的手段。
