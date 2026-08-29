import type { RobotConfig } from "../types";
import { Num, Section } from "../ui";

export default function MassPanel({
  robot,
  onChange,
}: {
  robot: RobotConfig;
  onChange: (r: RobotConfig) => void;
}) {
  const m = robot.masses;
  const d = robot.dims;
  const setM = (k: keyof typeof m, v: number) =>
    onChange({ ...robot, masses: { ...m, [k]: v } });
  const setD = (k: keyof typeof d, v: number) =>
    onChange({ ...robot, dims: { ...d, [k]: v } });

  // 結構重（不含致動器，致動器重量由硬體配置自動計入模型）
  const structMass =
    m.trunk + m.head + m.payload + 2 * (m.thigh + m.shin + m.foot + m.upper_arm + m.forearm);
  const actMass = Object.values(robot.actuators).reduce(
    (s, a) => s + 2 * (a.motor.mass + a.gear.mass),
    0
  );

  return (
    <Section title="重量與尺寸" defaultOpen={false}>
      <div className="mb-2 rounded bg-slate-800/60 px-2 py-1.5 text-[11px] text-slate-300">
        結構重 {structMass.toFixed(1)} kg ＋ 致動器 {actMass.toFixed(1)} kg ＝{" "}
        <span className="font-semibold text-amber-300">
          總重 {(structMass + actMass).toFixed(1)} kg
        </span>
      </div>
      <div className="text-[11px] font-semibold text-slate-400">各部件重量（單側）</div>
      <Num label="軀幹" value={m.trunk} onChange={(v) => setM("trunk", v)} min={4} max={40} step={0.5} unit="kg" />
      <Num label="頭部" value={m.head} onChange={(v) => setM("head", v)} min={0.5} max={8} step={0.1} unit="kg" />
      <Num label="大腿" value={m.thigh} onChange={(v) => setM("thigh", v)} min={0.5} max={10} step={0.1} unit="kg" />
      <Num label="小腿" value={m.shin} onChange={(v) => setM("shin", v)} min={0.3} max={8} step={0.1} unit="kg" />
      <Num label="腳掌" value={m.foot} onChange={(v) => setM("foot", v)} min={0.2} max={4} step={0.1} unit="kg" />
      <Num label="上臂" value={m.upper_arm} onChange={(v) => setM("upper_arm", v)} min={0.2} max={5} step={0.1} unit="kg" />
      <Num label="前臂" value={m.forearm} onChange={(v) => setM("forearm", v)} min={0.2} max={5} step={0.1} unit="kg" />
      <Num label="酬載（背負）" value={m.payload} onChange={(v) => setM("payload", v)} min={0} max={30} step={0.5} unit="kg" />
      <div className="mt-2 text-[11px] font-semibold text-slate-400">連桿尺寸</div>
      <Num label="大腿長" value={d.thigh_len} onChange={(v) => setD("thigh_len", v)} min={0.2} max={0.6} step={0.01} unit="m" />
      <Num label="小腿長" value={d.shin_len} onChange={(v) => setD("shin_len", v)} min={0.2} max={0.6} step={0.01} unit="m" />
      <Num label="髖寬" value={d.hip_width} onChange={(v) => setD("hip_width", v)} min={0.12} max={0.4} step={0.01} unit="m" />
      <Num label="軀幹長" value={d.torso_len} onChange={(v) => setD("torso_len", v)} min={0.25} max={0.7} step={0.01} unit="m" />
      <Num label="腳掌長" value={d.foot_len} onChange={(v) => setD("foot_len", v)} min={0.12} max={0.4} step={0.01} unit="m" />
    </Section>
  );
}
