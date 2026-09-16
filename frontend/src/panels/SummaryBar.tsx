import { useState } from "react";
import type { SimResult, WarningItem, WarningSeverity } from "../types";
import { GROUP_LABELS } from "../types";
import { Pill, type PillTone } from "../ui";

const SEVERITY: Record<WarningSeverity, { label: string; tone: PillTone; text: string; order: number }> = {
  blocking: { label: "不可行", tone: "red", text: "text-red-300", order: 0 },
  warning: { label: "警告", tone: "amber", text: "text-amber-300", order: 1 },
  caution: { label: "注意", tone: "orange", text: "text-orange-300", order: 2 },
  info: { label: "資訊", tone: "sky", text: "text-sky-300", order: 3 },
};
const TORQUE_CODES = ["ACTUATOR_PEAK_OVER_MOTOR_PEAK", "ACTUATOR_RMS_OVER_RATED", "ACTUATOR_PEAK_OVER_RATED"];

// 致動器 screen 的格子：只顯示數字，完整原文放在 title。
function actuatorCell(item: WarningItem | undefined) {
  if (!item) return <span className="text-slate-600">✓</span>;
  const text = item.code === "ACTUATOR_SPEED_OVER_RATED"
    ? `${item.value} / ${item.limit} ${item.unit}`
    : item.code === "ACTUATOR_RMS_OVER_RATED"
      ? `RMS ${item.value}${item.unit}`
      : item.code === "ACTUATOR_PEAK_OVER_RATED"
        ? `峰值 ${item.value}${item.unit}`
        : `${item.value}${item.unit}`;
  return (
    <span title={item.detail} className={`font-semibold tabular-nums ${SEVERITY[item.severity].text}`}>
      {text}
    </span>
  );
}

// 分類後的警告面板：致動器 screen 併成一張表，其餘一行一條短標題；原文收在按鈕後面。
function WarningPanel({
  items,
  warnings,
  groupOrder,
}: {
  items: WarningItem[];
  warnings: string[];
  groupOrder: string[];
}) {
  const [showRaw, setShowRaw] = useState(false);
  const actuator = items.filter((item) => item.scope === "actuator");
  const others = items
    .filter((item) => item.scope !== "actuator")
    .sort((a, b) => SEVERITY[a.severity].order - SEVERITY[b.severity].order);
  const counts = (Object.keys(SEVERITY) as WarningSeverity[])
    .map((severity) => ({ severity, n: items.filter((item) => item.severity === severity).length }))
    .filter((entry) => entry.n > 0);
  const byGroup = new Map<string, WarningItem[]>();
  for (const item of actuator) {
    if (item.group) byGroup.set(item.group, [...(byGroup.get(item.group) ?? []), item]);
  }
  const rows = groupOrder.filter((group) => byGroup.has(group));
  const pick = (group: string, codes: string[]) =>
    byGroup.get(group)?.find((item) => codes.includes(item.code));

  return (
    <div className="mt-2 rounded bg-slate-950/50 p-2">
      <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
        {counts.map(({ severity, n }) => (
          <Pill key={severity} tone={SEVERITY[severity].tone}>{SEVERITY[severity].label} {n}</Pill>
        ))}
        <span className="text-slate-500">rule-based screen，不是硬體 pass/fail</span>
        <button
          type="button"
          className="ml-auto text-slate-400 hover:text-slate-200"
          onClick={() => setShowRaw((open) => !open)}
        >
          {showRaw ? "隱藏完整訊息 ▾" : "完整訊息 ▸"}
        </button>
      </div>

      {rows.length > 0 && (
        <table className="mt-2 w-full text-[11px]">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1 pr-3 text-left font-normal">致動器 screen（{rows.length} 個關節群組）</th>
              <th className="py-1 pr-3 text-left font-normal">馬達扭矩</th>
              <th className="py-1 pr-3 text-left font-normal">轉速</th>
              <th className="py-1 text-left font-normal">減速機</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((group) => (
              <tr key={group} className="border-t border-slate-800/80">
                <td className="py-1 pr-3 text-slate-300">{GROUP_LABELS[group] ?? group}</td>
                <td className="py-1 pr-3">{actuatorCell(pick(group, TORQUE_CODES))}</td>
                <td className="py-1 pr-3">{actuatorCell(pick(group, ["ACTUATOR_SPEED_OVER_RATED"]))}</td>
                <td className="py-1">{actuatorCell(pick(group, ["GEARBOX_PEAK_OVER_RATED"]))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {others.length > 0 && (
        <ul className={`space-y-1 ${rows.length > 0 ? "mt-2 border-t border-slate-800/80 pt-2" : "mt-2"}`}>
          {others.map((item, index) => (
            <li key={`${item.code}-${index}`} className="flex items-start gap-2 text-[11px]" title={item.detail}>
              <Pill tone={SEVERITY[item.severity].tone} className="shrink-0">{SEVERITY[item.severity].label}</Pill>
              <span className="text-slate-200">{item.title}</span>
            </li>
          ))}
        </ul>
      )}

      {showRaw && (
        <ul className="mt-2 max-h-40 space-y-0.5 overflow-y-auto border-t border-slate-800/80 pt-2">
          {warnings.map((w, i) => (
            <li key={i} className="text-[11px] leading-4 text-amber-200/90">{w}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Card({ label, value, unit, tone }: { label: string; value: string; unit?: string; tone?: string }) {
  return (
    <div className="rounded-lg bg-slate-800/70 px-3 py-1.5">
      <div className="text-[11px] text-slate-400">{label}</div>
      <div className={`text-sm font-semibold ${tone ?? "text-slate-100"}`}>
        {value}
        {unit && <span className="ml-0.5 text-[11px] font-normal text-slate-400">{unit}</span>}
      </div>
    </div>
  );
}

// 預設只顯示四個關鍵指標；其餘指標與警告清單都收在按鈕後面
export default function SummaryBar({ result }: { result: SimResult | null }) {
  const [showMore, setShowMore] = useState(false);
  const [showWarnings, setShowWarnings] = useState(false);
  if (!result) return null;
  const s = result.meta.summary;
  const warnings = result.meta.warnings;
  const items = result.meta.warning_items;
  const blockingCount = items?.filter((item) => item.severity === "blocking").length ?? 0;
  const zmpAvailable = s.zmp_stable_pct != null && s.zmp_valid_sample_count !== 0;
  const zmpTone = !zmpAvailable ? "text-slate-300"
    : s.zmp_stable_pct! >= 97 ? "text-emerald-300"
    : s.zmp_stable_pct! >= 85 ? "text-amber-300" : "text-red-300";
  const zmpCoverage = s.zmp_valid_coverage_pct == null
    ? "LEGACY_UNKNOWN"
    : `${s.zmp_valid_coverage_pct.toFixed(1)}% (${s.zmp_valid_sample_count ?? "—"}/${s.zmp_candidate_sample_count ?? "—"})`;
  return (
    <div className="border-b border-slate-800 bg-slate-900/60 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <Card label="模型總質量" value={s.total_mass.toFixed(1)} unit="kg" />
        <Card label="平均功率（簡化估計）" value={s.avg_power_W.toFixed(0)} unit="W" />
        <Card label="CoT（估計）" value={s.cot == null ? "—" : s.cot.toFixed(2)} />
        <div data-testid="zmp-summary" className="rounded-lg bg-slate-800/70 px-3 py-1.5">
          <div className="text-[11px] text-slate-400">ZMP 落在支撐區內（模型）</div>
          <div className={`text-sm font-semibold ${zmpTone}`}>
            {zmpAvailable ? `${s.zmp_stable_pct!.toFixed(0)}%` : "— / UNAVAILABLE"}
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            className="rounded-lg bg-slate-800/70 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-700"
            onClick={() => setShowMore(!showMore)}
          >
            {showMore ? "較少指標 ▾" : "更多指標 ▸"}
          </button>
          {warnings.length > 0 ? (
            <button
              type="button"
              className="rounded-lg bg-red-500/15 px-3 py-1.5 text-xs font-semibold text-red-300 hover:bg-red-500/25"
              onClick={() => setShowWarnings(!showWarnings)}
            >
              ⚠ {warnings.length} 項警告{blockingCount > 0 ? `（${blockingCount} 項不可行）` : ""} {showWarnings ? "▾" : "▸"}
            </button>
          ) : (
            <div className="rounded-lg bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-300">
              ✓ 無警告
            </div>
          )}
        </div>
      </div>
      {showMore && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Card label="D0 致動器質量" value={s.actuator_mass.toFixed(1)} unit="kg" />
          <Card label="prescribed 步頻" value={s.cadence_spm.toFixed(0)} unit="步/分" />
          <Card label="能耗（簡化估計）" value={s.energy_J.toFixed(0)} unit="J" />
          <Card label="ZMP P1 裕度" value={s.p01_zmp_margin_cm == null ? "—" : String(s.p01_zmp_margin_cm)} unit="cm" />
          <Card label="ZMP 最小裕度" value={s.min_zmp_margin_cm == null ? "—" : String(s.min_zmp_margin_cm)} unit="cm" />
          <Card label="ZMP 有效樣本覆蓋" value={zmpAvailable ? zmpCoverage : "—"} />
          <span className="text-[11px] text-slate-500">數值皆為 reduced-order 軟體估算，用於相對比較，不是實體量測。</span>
        </div>
      )}
      {showWarnings && warnings.length > 0 && (
        items && items.length === warnings.length ? (
          <WarningPanel items={items} warnings={warnings} groupOrder={Object.keys(s.groups)} />
        ) : (
          <ul className="mt-2 max-h-32 space-y-0.5 overflow-y-auto rounded bg-slate-950/50 p-2">
            {warnings.map((w, i) => (
              <li key={i} className="text-[11px] leading-4 text-amber-200/90">
                {w}
              </li>
            ))}
          </ul>
        )
      )}
    </div>
  );
}

// 各關節群組使用率表（額定 / 峰值 / 轉速）；在圖表區以獨立分頁顯示
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
    <div className="flex items-center gap-2">
      <div className="h-1.5 min-w-[60px] flex-1 overflow-hidden rounded bg-slate-700">
        <div
          className="h-full rounded"
          style={{
            width: `${Math.min(pct, 100)}%`,
            background: pct > warnAt ? "#f87171" : pct > warnAt * 0.8 ? "#fbbf24" : "#34d399",
          }}
        />
      </div>
      <span className={`w-12 text-right text-[11px] tabular-nums ${pct > warnAt ? "font-semibold text-red-300" : "text-slate-300"}`}>
        {pct.toFixed(0)}%
      </span>
    </div>
  );
  return (
    <div className="h-full overflow-y-auto">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="text-slate-500">
            <th className="pb-1 text-left font-normal">關節群組（{windowLabel}）</th>
            <th className="pb-1 text-left font-normal">RMS 扭矩 / 額定</th>
            <th className="pb-1 text-left font-normal">峰值扭矩 / 峰值</th>
            <th className="pb-1 text-left font-normal">轉速 / 額定</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(groups).map(([g, st]) => (
            <tr key={g} className="border-t border-slate-800">
              <td className="py-1 pr-3 text-slate-300">{GROUP_LABELS[g] ?? g}</td>
              <td className="py-1 pr-3">{bar(st.rms_util_pct)}</td>
              <td className="py-1 pr-3">{bar(st.peak_vs_peak_pct)}</td>
              <td className="py-1">{bar(st.speed_util_pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-1 text-[11px] leading-4 text-slate-500">
        超過 100% 只代表觸發目前的 representative threshold；thermal、torque-speed 與 drive feasibility 尚未建模，不能據此判定實體可行性。
      </div>
    </div>
  );
}
