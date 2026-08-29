# Hardware Data Provenance

## 1. Current status

內建 motor/gearbox catalog 全部視為：

> D0 — representative demo data

它不是原廠 datasheet、CAD/BOM、supplier qualification、bench measurement 或 integrated subsystem evidence。名稱、數值看似合理或使用者在 UI 中覆寫，都不會自動改變此 evidence class。

## 2. Evidence classes

| Class | Evidence | 可支持用途 | 不可支持 |
|---|---|---|---|
| D0 Demo | representative/synthetic/manual estimate | UI、教學、sensitivity screening | 型號能力、採購、硬體可行 |
| D1 Datasheet | identifiable manufacturer document/revision/page | bounded nominal/rated parameter model | actual unit variation、installation、thermal integration |
| D2 CAD/BOM | controlled CAD mass properties、BOM、drawings | geometry/mass/inertia configuration | actuator performance或 assembled behavior |
| D3 Bench | calibrated actuator/joint bench raw data | tested subsystem envelope | untested robot/system conditions |
| D4 Integrated | instrumented limb/robot data under frozen protocol | tested integrated conditions | untested tasks/environment或 safety certification |

Evidence 不可跳級。D1 + D2 也不等於 D3。

## 3. Required provenance record

每個 hardware parameter set 至少需：

- record_id and evidence_class；
- manufacturer、model、option/variant；
- source document/file identity；
- revision/date；
- page/table/figure or data channel；
- original units and converted SI units；
- operating conditions；
- min/nominal/max and tolerance；
- interpolation/extrapolation rule；
- source file SHA-256；
- reviewer and review date；
- redistribution/license note；
- unresolved ambiguity and blockers。

若 source 只有圖線，digitization method、point uncertainty 與原圖 checksum 必須保留。

## 4. Motor and drive fields

正式 actuator screening 最低需要：

- continuous and peak torque；
- peak duration/duty cycle/cooling condition；
- torque-speed envelope；
- current-torque constant and current limits；
- voltage/back-EMF/speed limits；
- drive/battery voltage and current limits；
- rotor inertia；
- efficiency/loss map；
- winding/drive temperature limits；
- thermal resistance/capacitance or validated equivalent；
- regeneration/braking policy；
- mass and mounting/interface data。

只有 rated torque、peak torque、rated speed 與單一 efficiency，仍不足以判定 full operating envelope。

## 5. Gearbox/transmission fields

- ratio and tolerance；
- continuous/peak output torque；
- input/output speed limits；
- efficiency map versus torque/speed/direction；
- backlash；
- torsional stiffness/compliance；
- reflected inertia；
- lubrication/temperature；
- rated life/load spectrum；
- mass、mounting與interface；
- emergency/impact load boundary。

單一 rated output torque 不代表 dynamic shock、backdrive 或 lifetime feasibility。

## 6. Joint and structure fields

- hard/soft position limits；
- velocity/acceleration limits；
- joint stiffness/damping/friction；
- bearing/load limits；
- link mass、center of mass、inertia tensor；
- CAD revision；
- material/structural limits；
- self-collision envelope；
- cable/hose routing and service loops；
- end-effector/payload interface。

M7 arm dynamic V&V 另需 wrist/gripper/object contact、payload mass properties 與 grasp/load path。

## 7. Sensor/estimator fields

- sensor model and revision；
- range、resolution、sampling rate；
- noise density/repeatability；
- bias、drift、temperature effect；
- latency/jitter；
- dropout/error behavior；
- coordinate frame/extrinsic calibration；
- calibration date/method；
- raw characterization data。

Ideal raycast 或 simulator state 是 D0 simulation signal，不是 sensor evidence。

## 8. Bench evidence

D3 record 必須附：

- test fixture and diagram；
- calibrated instruments and uncertainty；
- sampling/clock synchronization；
- control and load profile；
- environment/cooling；
- raw channels；
- calibration versus holdout split；
- preprocessing；
- acceptance criteria；
- failed/aborted runs；
- code/config/data hashes。

只有圖表、抄錄峰值或平均值不能升為 D3。

## 9. Promotion workflow

1. 以 D0 建立 teaching/screening record。
2. 收集 D1 source，保留原檔與 exact citation。
3. 以 D2 確定實際 geometry/mass/inertia configuration。
4. preregister D3 bench protocol，凍結 acceptance。
5. 保存 raw/processed/receipt 與 uncertainty。
6. 只有對應 parameter/use case 通過才提升 class。
7. 更換 model、drive、gear ratio、cooling、mount或 firmware 需重新評估 identity。

## 10. Uncertainty handling

- 不以單一 nominal value 隱藏 tolerance。
- min/nominal/max 與 distribution source 分開。
- 未知相關性不自行假設 independent。
- extrapolation outside source envelope標記 BLOCKER。
- Monte Carlo distribution 必須來自 source、bench 或明示 hypothesis；D0 guess 不能包裝成 measured uncertainty。

## 11. Allowed claim examples

### D0

> [RESULT] 在 representative demo parameters 下，gear ratio 增加使 simulation speed utilization 上升。

### D1/D2

> [SOURCE] Manufacturer document revision X 提供 nominal torque-speed envelope；CAD revision Y 提供 mass properties。
> [BLOCKER] 尚未完成 drive integration與bench holdout，因此不宣稱實際 continuous feasibility。

### D3

> [RESULT] 指定 actuator subsystem 在 protocol、fixture與environment所列 conditions 下通過 bench acceptance。
> [BLOCKER] 結果不外推到整機 gait或跌倒 safety。

## 12. Current blockers

- built-in catalog 沒有 authoritative source identity；
- torque-speed/current/voltage/thermal information 不完整；
- gearbox backlash/compliance/life data 不完整；
- joint limits與CAD-correlated inertia不完整；
- sensor/estimator characterization缺失；
- 無 actuator/limb bench raw data。

因此目前所有 hardware output 保持 D0 SIM-only screening。
