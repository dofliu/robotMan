# 三機同步比較模式規格

最後更新：2026-08-26
狀態：BACKEND + FRONTEND IMPLEMENTED / BROWSER VISUAL SMOKE PENDING / DEVELOPMENT ONLY

## 1. 目的與證據邊界

本模式同時顯示 `track`、`raibert`、`rl` 三組機器人，讓使用者在相同初始 robot、gait、obstacles、simulated push 與時間命令下觀察控制器行為差異。

- Evidence scope：`SOFTWARE_ONLY / MUJOCO_CONTACT_SIM / DEVELOPMENT_COMPARISON_ONLY`。
- 允許用途：教學、除錯、控制器行為觀察、建立正式實驗前的假設。
- 禁止宣稱：控制器普遍優劣、統計顯著性、實機穩定性、實測抗推能力或 sim-to-real 能力。
- 本功能不等同 V3 Fair Benchmark PASS；正式 ranking 仍須 frozen manifest、multi-seed/scenario、raw traces、effect size 與 confidence interval。

## 2. 公平性架構

三個機器人不放在同一個 MuJoCo world，避免彼此碰撞或共享 contact state。後端建立三個互相隔離的 `LiveSession`：

| Session | Controller | Plant/config | Assist |
|---|---|---|---|
| A | trajectory tracking (`track`) | 與 B/C 相同的獨立副本 | 預設 OFF |
| B | Raibert (`raibert`) | 與 A/C 相同的獨立副本 | 預設 OFF |
| C | PPO policy (`rl`) | 與 A/B 相同的獨立副本 | 預設 OFF |

每次 advance 使用同一個 bounded wall-time increment；共享命令先完成 schema validation，再以相同 payload 套用到三個 session。若任何 controller 初始化失敗，整個 comparison init fail closed，不建立部分比較。

## 3. WebSocket contract

Endpoint：`/ws/compare`

Client 首先送出既有 live init contract：

```json
{"type":"init","robot":{},"gait":{},"obstacles":[]}
```

Server 成功後依序送出：

```json
{
  "type":"compare_scene",
  "controllers":["track","raibert","rl"],
  "scenes":{"track":{},"raibert":{},"rl":{}},
  "evidence_scope":"DEVELOPMENT_COMPARISON_ONLY",
  "plant_isolation":true,
  "assist_default":false
}
```

```json
{
  "type":"compare_frame",
  "t":1.25,
  "frames":{"track":{},"raibert":{},"rl":{}},
  "sync":{"max_time_skew_s":0.0,"same_input":true,"independent_plants":true}
}
```

第一版只接受可原子化地共享的命令：

- `mode`：`stand` 或 `walk`，controller 由 session 身分固定，不接受 client 切換。
- `push`：相同方向、力與 duration 套用至三個 session。
- `speed`、`pause`、`step`、`assist`、`reset`。

第一版不接受 runtime `gait` 或臨時 `obstacle` 命令，避免 RL 固定 gait contract 或場景重建失敗造成三組 state 分歧；需改動時建立新 init。

## 4. 顯示要求

- 三張並排 3D 卡片，標示 controller 名稱，不合成同一個物理場景。
- 共用開始、站立、push、speed、pause、step、assist 與 reset 控制。
- 每張卡片至少顯示 state、sim time、前進距離、forward velocity、pitch、roll、最大 actuator saturation 與 intervention state。
- `FALLEN` 後保持當下 forward simulation 與畫面，不自動 reset、不隱藏、不以 assist 修復。
- UI 固定顯示 `SAME_INPUT / INDEPENDENT_PLANTS` 與 `DEVELOPMENT_COMPARISON_ONLY`。

## 5. Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| DCOMP-R01 | init 建立恰好三個固定 controller session；任一失敗則不替換現有 comparison | PASS — backend contract/integration test |
| DCOMP-R02 | 三組使用相同 robot/gait/obstacles 且 model/config fingerprint 相同 | PASS — scene signature/model isolation test |
| DCOMP-R03 | 每個 compare frame 三組 `sim_t` 相同，time skew 在 floating-point tolerance 內 | PASS — backend test；UI visual pending |
| DCOMP-R04 | 共享命令 schema fail closed；不支援命令不改變任何 session | PASS — backend negative test |
| DCOMP-R05 | assist 預設關閉；UI 顯示實際 intervention readback | PASS — backend + frontend source/build；visual pending |
| DCOMP-R06 | 跌倒不觸發自動 reset 或 controller 替換 | PASS — source/regression behavior |
| DCOMP-R07 | frontend 同時呈現三個 renderer 與共同控制 | PARTIAL — typecheck/build PASS；browser smoke pending |
| DCOMP-R08 | 文件與 UI 不做 controller ranking 或 physical claim | PASS — documentation/source review |

## 6. 後續順序

1. 完成三機同步比較與測試。
2. 建立 RL policy registry：version、checkpoint SHA-256、training contract、seed/environment metadata 與 evidence status。
3. 以不覆寫 artifact 的方式建立 0.4、0.7、1.0 m/s 固定速度 training profiles；先做 pipeline smoke，再決定正式 training budget。
4. 建立 command-conditioned multi-speed policy。
5. 逐步增加 run、turn、terrain 與 disturbance curriculum；正式比較仍受 V0/V1/V3 gates 約束。
