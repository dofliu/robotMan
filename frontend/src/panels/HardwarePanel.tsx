import type { Defaults, JointActuator, RobotConfig } from "../types";
import { GROUP_LABELS } from "../types";
import { Num, Section, Select } from "../ui";

// 單一關節群組的硬體設定卡
function ActuatorCard({
  group,
  act,
  defaults,
  onChange,
}: {
  group: string;
  act: JointActuator;
  defaults: Defaults;
  onChange: (a: JointActuator) => void;
}) {
  const jointRated = act.motor.rated_torque * act.gear.ratio * act.gear.efficiency;
  const jointPeak = act.motor.peak_torque * act.gear.ratio * act.gear.efficiency;
  const jointSpeed = (act.motor.rated_speed_rpm / act.gear.ratio) * (Math.PI / 30); // rad/s

  return (
    <div className="mb-2 rounded-lg bg-slate-800/50 p-2">
      <div className="mb-1 text-xs font-semibold text-slate-200">{GROUP_LABELS[group] ?? group}</div>
      <Select
        label="馬達"
        value={act.motor.id}
        options={defaults.motors}
        onChange={(id) => {
          const m = defaults.motors.find((x) => x.id === id)!;
          onChange({ ...act, motor: { ...m } });
        }}
      />
      <Select
        label="減速機"
        value={act.gear.id}
        options={defaults.gearboxes}
        onChange={(id) => {
          const g = defaults.gearboxes.find((x) => x.id === id)!;
          onChange({ ...act, gear: { ...g } });
        }}
      />
      <div className="grid grid-cols-2 gap-x-2">
        <Num label="額定扭矩" value={act.motor.rated_torque} onChange={(v) => onChange({ ...act, motor: { ...act.motor, rated_torque: v, id: "custom" } })} min={0.1} max={30} step={0.1} unit="Nm" slider={false} />
        <Num label="峰值扭矩" value={act.motor.peak_torque} onChange={(v) => onChange({ ...act, motor: { ...act.motor, peak_torque: v, id: "custom" } })} min={0.2} max={90} step={0.1} unit="Nm" slider={false} />
        <Num label="額定轉速" value={act.motor.rated_speed_rpm} onChange={(v) => onChange({ ...act, motor: { ...act.motor, rated_speed_rpm: v, id: "custom" } })} min={100} max={10000} step={100} unit="rpm" slider={false} />
        <Num label="馬達重量" value={act.motor.mass} onChange={(v) => onChange({ ...act, motor: { ...act.motor, mass: v, id: "custom" } })} min={0.05} max={5} step={0.05} unit="kg" slider={false} />
        <Num label="減速比" value={act.gear.ratio} onChange={(v) => onChange({ ...act, gear: { ...act.gear, ratio: v, id: "custom" } })} min={1} max={200} step={1} unit=":1" slider={false} />
        <Num label="傳動效率" value={act.gear.efficiency} onChange={(v) => onChange({ ...act, gear: { ...act.gear, efficiency: v, id: "custom" } })} min={0.4} max={1} step={0.01} unit="" slider={false} />
      </div>
      <div className="mt-1 rounded bg-slate-900/70 px-2 py-1 text-[10px] text-slate-400">
        關節端：額定 {jointRated.toFixed(0)} Nm ／ 峰值 {jointPeak.toFixed(0)} Nm ／ 最高{" "}
        {jointSpeed.toFixed(1)} rad/s ／ 單顆重 {(act.motor.mass + act.gear.mass).toFixed(2)} kg
      </div>
    </div>
  );
}

export default function HardwarePanel({
  robot,
  defaults,
  onChange,
}: {
  robot: RobotConfig;
  defaults: Defaults;
  onChange: (r: RobotConfig) => void;
}) {
  return (
    <Section title="硬體規格（馬達 / 減速機）" defaultOpen={false}>
      <p className="mb-2 text-[10px] leading-4 text-slate-500">
        型錄為代表性示意規格，實際選型請以原廠 datasheet 修改欄位（改動後標記為自訂）。左右對稱共用同一組配置。
      </p>
      {Object.entries(robot.actuators).map(([group, act]) => (
        <ActuatorCard
          key={group}
          group={group}
          act={act}
          defaults={defaults}
          onChange={(a) =>
            onChange({ ...robot, actuators: { ...robot.actuators, [group]: a } })
          }
        />
      ))}
    </Section>
  );
}
