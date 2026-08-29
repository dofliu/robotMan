import { useState } from "react";
import type { SimResult } from "../types";
import { GROUP_LABELS } from "../types";

function Card({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="rounded-lg bg-slate-800/70 px-3 py-1.5">
      <div className="text-[10px] text-slate-400">{label}</div>
      <div className="text-sm font-semibold text-slate-100">
        {value}
        {unit && <span className="ml-0.5 text-[10px] font-normal text-slate-400">{unit}</span>}
      </div>
    </div>
  );
}

export default function SummaryBar({ result }: { result: SimResult | null }) {
  const [showWarnings, setShowWarnings] = useState(true);
  if (!result) return null;
  const s = result.meta.summary;
  const warnings = result.meta.warnings;
  const zmpAvailable = s.zmp_stable_pct != null && s.zmp_valid_sample_count !== 0;
  const zmpCoverage = s.zmp_valid_coverage_pct == null
    ? "coverage LEGACY_UNKNOWN"
    : `coverage ${s.zmp_valid_coverage_pct.toFixed(1)}% (${s.zmp_valid_sample_count ?? "—"}/${s.zmp_candidate_sample_count ?? "—"})`;
  return (
    <div className="border-b border-slate-800 bg-slate-900/60 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <Card label="模型總質量" value={s.total_mass.toFixed(1)} unit="kg" />
        <Card label="D0 致動器質量" value={s.actuator_mass.toFixed(1)} unit="kg" />
        <Card label="prescribed 步頻" value={s.cadence_spm.toFixed(0)} unit="步/分" />
        <Card label="簡化平均功率" value={s.avg_power_W.toFixed(0)} unit="W" />
        <Card label="簡化能耗估計" value={s.energy_J.toFixed(0)} unit="J" />
        <Card label="CoT estimate" value={s.cot == null ? "—" : s.cot.toFixed(2)} />
        <div data-testid="zmp-summary" className="rounded-lg bg-slate-800/70 px-3 py-1.5">
          <div className="text-[10px] text-slate-400">ZMP 支撐區指標（模型）</div>
          <div
            className={`text-sm font-semibold ${
              !zmpAvailable ? "text-slate-300"
              : s.zmp_stable_pct! >= 97 ? "text-emerald-300"
              : s.zmp_stable_pct! >= 85 ? "text-amber-300" : "text-red-300"
            }`}
          >
            {zmpAvailable ? `${s.zmp_stable_pct!.toFixed(0)}%` : "— / UNAVAILABLE"}
            <span className="ml-1 text-[10px] font-normal text-slate-400">
              P1 裕度 {s.p01_zmp_margin_cm ?? "—"} cm ｜ true min {s.min_zmp_margin_cm ?? "—"} cm
            </span>
            {zmpAvailable && (
              <span className="ml-1 text-[10px] font-normal text-slate-400">{zmpCoverage}</span>
            )}
          </div>
        </div>
        {warnings.length > 0 ? (
          <button
            className="ml-auto rounded-lg bg-red-500/15 px-3 py-1.5 text-xs font-semibold text-red-300 hover:bg-red-500/25"
            onClick={() => setShowWarnings(!showWarnings)}
          >
            ⚠ {warnings.length} 項警告 {showWarnings ? "▾" : "▸"}
          </button>
        ) : (
          <div className="ml-auto rounded-lg bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-300">
            ✓ 目前已實作 checks 未觸發警告
          </div>
        )}
      </div>
      {showWarnings && warnings.length > 0 && (
        <ul className="mt-1.5 space-y-0.5">
          {warnings.map((w, i) => (
            <li key={i} className="text-[11px] leading-4 text-amber-200/90">
              {w}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// 各關節群組使用率表（額定 / 峰值 / 轉速 / 減速機）
export function UtilTable({ result }: { result: SimResult | null }) {
  if (!result) return null;
  const summary = result.meta.summary;
  const groups = summary.groups;
  const windowLabel = summary.actuator_stats_window?.mode === "steady_window"
    ? "穩態窗"
    : summary.actuator_stats_window?.mode === "full_window_fallback"
      ? "完整窗 fallback"
      : "legacy 未標示窗口";
  const bar = (pct: number, warnAt = 100) => (
    <div className="flex items-center gap-1">
      <div className="h-1.5 w-14 overflow-hidden rounded bg-slate-700">
        <div
          className="h-full rounded"
          style={{
            width: `${Math.min(pct, 100)}%`,
            background: pct > warnAt ? "#f87171" : pct > warnAt * 0.8 ? "#fbbf24" : "#34d399",
          }}
        />
      </div>
      <span
        className={`w-10 text-right text-[10px] ${
          pct > warnAt ? "text-red-300 font-semibold" : "text-slate-300"
        }`}
      >
        {pct.toFixed(0)}%
      </span>
    </div>
  );
  return (
    <div className="h-full overflow-y-auto p-2">
      <div className="mb-1 text-xs font-semibold text-slate-300">D0 致動器參數 screen（{windowLabel}）</div>
      <table className="w-full text-[10px]">
        <thead>
          <tr className="text-slate-500">
            <th className="pb-1 text-left font-normal">關節</th>
            <th className="pb-1 text-left font-normal">RMS/額定</th>
            <th className="pb-1 text-left font-normal">峰值/峰值</th>
            <th className="pb-1 text-left font-normal">轉速</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(groups).map(([g, st]) => (
            <tr key={g} className="border-t border-slate-800">
              <td className="py-1 pr-1 text-slate-300">{GROUP_LABELS[g] ?? g}</td>
              <td className="py-1 pr-1">{bar(st.rms_util_pct)}</td>
              <td className="py-1 pr-1">{bar(st.peak_vs_peak_pct)}</td>
              <td className="py-1">{bar(st.speed_util_pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-1 text-[10px] leading-4 text-slate-500">
        超過 100% 只代表觸發目前 representative threshold。Thermal、torque-speed 與 drive feasibility
        尚未建模，不能據此判定實體過熱、可承受時間或動作可行性。
      </div>
    </div>
  );
}
