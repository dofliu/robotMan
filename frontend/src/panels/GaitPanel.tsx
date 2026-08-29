import type { GaitParams } from "../types";
import { Num, Section } from "../ui";

// 走路 / 跑步 的建議參數組（一鍵切換）
const WALK_PRESET: Partial<GaitParams> = {
  mode: "walk", speed: 1.2, step_length: 0.5, duty: 0.6,
  clearance: 0.07, pelvis_bounce: 0.012, arm_swing_deg: 20,
};
const RUN_PRESET: Partial<GaitParams> = {
  mode: "run", speed: 2.6, step_length: 0.85, duty: 0.38,
  clearance: 0.12, pelvis_bounce: 0.025, arm_swing_deg: 40,
};

export default function GaitPanel({
  gait,
  onChange,
}: {
  gait: GaitParams;
  onChange: (g: GaitParams) => void;
}) {
  const set = (patch: Partial<GaitParams>) => onChange({ ...gait, ...patch });
  return (
    <Section title="步態參數">
      <div className="mb-2 flex gap-2">
        <button
          className={`flex-1 rounded py-1 text-xs font-semibold ${
            gait.mode === "walk" ? "bg-sky-500 text-slate-900" : "bg-slate-800 text-slate-300"
          }`}
          onClick={() => set(WALK_PRESET)}
        >
          🚶 走路
        </button>
        <button
          className={`flex-1 rounded py-1 text-xs font-semibold ${
            gait.mode === "run" ? "bg-orange-400 text-slate-900" : "bg-slate-800 text-slate-300"
          }`}
          onClick={() => set(RUN_PRESET)}
        >
          🏃 跑步
        </button>
      </div>
      <Num label="前進速度" value={gait.speed} onChange={(v) => set({ speed: v })} min={0.2} max={5} step={0.1} unit="m/s" />
      <Num label="步長" value={gait.step_length} onChange={(v) => set({ step_length: v })} min={0.2} max={1.2} step={0.05} unit="m" />
      <Num label="支撐期占比" value={gait.duty} onChange={(v) => set({ duty: v })} min={0.3} max={0.8} step={0.02} unit="" />
      <Num label="抬腳高度" value={gait.clearance} onChange={(v) => set({ clearance: v })} min={0.03} max={0.3} step={0.01} unit="m" />
      <Num label="手臂擺幅" value={gait.arm_swing_deg} onChange={(v) => set({ arm_swing_deg: v })} min={0} max={60} step={5} unit="°" />
      <Num label="軀幹前傾" value={gait.torso_lean_deg} onChange={(v) => set({ torso_lean_deg: v })} min={0} max={20} step={1} unit="°" />
      <Num label="骨盆起伏" value={gait.pelvis_bounce} onChange={(v) => set({ pelvis_bounce: v })} min={0} max={0.05} step={0.002} unit="m" />
      <Num label="骨盆側擺" value={gait.pelvis_sway} onChange={(v) => set({ pelvis_sway: v })} min={0} max={0.08} step={0.005} unit="m" />
      <Num label="站姿下蹲" value={gait.crouch} onChange={(v) => set({ crouch: v })} min={0.04} max={0.25} step={0.01} unit="m" />
      <Num label="模擬時長" value={gait.duration} onChange={(v) => set({ duration: v })} min={3} max={15} step={1} unit="s" />
      <p className="mt-1 text-[10px] leading-4 text-slate-500">
        支撐期占比 &lt; 0.5 會產生騰空期（跑步）。步長過大會超出腿長可及範圍。
      </p>
    </Section>
  );
}
