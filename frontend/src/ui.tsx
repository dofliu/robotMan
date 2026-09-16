import { useState, type ReactNode } from "react";

// 分段切換：同一時間只顯示一組內容，是每頁減少同時可見資訊的主要工具
export function Tabs<T extends string>({
  value,
  onChange,
  items,
  size = "sm",
  fill = false,
}: {
  value: T;
  onChange: (v: T) => void;
  items: { id: T; label: string }[];
  size?: "sm" | "md";
  fill?: boolean;
}) {
  return (
    <div className={`${fill ? "flex w-full" : "inline-flex"} rounded-lg bg-slate-800/80 p-0.5`}>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          onClick={() => onChange(item.id)}
          className={`${fill ? "flex-1 px-1" : "px-2.5"} whitespace-nowrap rounded-md font-semibold transition-colors ${
            size === "md" ? "py-1 text-sm" : "py-0.5 text-xs"
          } ${value === item.id ? "bg-slate-600 text-slate-50 shadow" : "text-slate-400 hover:text-slate-200"}`}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

// 可收合區塊：標題列常駐、內容預設收起；summary 是收起時仍需看見的狀態
export function Disclosure({
  title,
  summary,
  defaultOpen = false,
  children,
  className = "",
  tone = "default",
}: {
  title: ReactNode;
  summary?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
  className?: string;
  tone?: "default" | "accent";
}) {
  const [open, setOpen] = useState(defaultOpen);
  const frame = tone === "accent"
    ? "border-violet-500/30 bg-violet-500/5"
    : "border-slate-800 bg-slate-900/50";
  return (
    <div className={`rounded-lg border ${frame} ${className}`}>
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs font-semibold text-slate-200 hover:bg-slate-800/40"
        onClick={() => setOpen(!open)}
      >
        <span>{title}</span>
        <span className="flex items-center gap-2 text-[11px] font-normal text-slate-400">
          {summary}
          <span className="text-slate-500">{open ? "▾" : "▸"}</span>
        </span>
      </button>
      {open && <div className="border-t border-slate-800/80 px-3 py-2">{children}</div>}
    </div>
  );
}

const PILL_TONES = {
  slate: "border-slate-600 bg-slate-800/60 text-slate-300",
  sky: "border-sky-500/40 bg-sky-500/10 text-sky-300",
  amber: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  orange: "border-orange-500/40 bg-orange-500/10 text-orange-300",
  emerald: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  red: "border-red-500/40 bg-red-500/10 text-red-300",
  violet: "border-violet-500/40 bg-violet-500/10 text-violet-200",
  cyan: "border-cyan-500/40 bg-cyan-500/10 text-cyan-300",
  fuchsia: "border-fuchsia-500/40 bg-fuchsia-500/10 text-fuchsia-300",
} as const;
export type PillTone = keyof typeof PILL_TONES;

// 狀態標籤（單一短字串）
export function Pill({
  tone = "slate",
  children,
  className = "",
  title,
}: {
  tone?: PillTone;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] font-semibold ${PILL_TONES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

export function Num({
  label,
  value,
  onChange,
  min,
  max,
  step = 0.01,
  unit = "",
  slider = true,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  slider?: boolean;
}) {
  return (
    <div className="mb-1.5">
      <div className="flex items-center justify-between text-xs text-slate-300">
        <span>{label}</span>
        <span className="flex items-center gap-1">
          <input
            type="number"
            className="w-16 rounded bg-slate-800 px-1 py-0.5 text-right text-xs text-slate-100 outline-none ring-slate-600 focus:ring-1"
            value={value}
            min={min}
            max={max}
            step={step}
            onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
          />
          <span className="w-8 text-slate-500">{unit}</span>
        </span>
      </div>
      {slider && (
        <input
          type="range"
          className="mt-0.5 h-1.5 w-full"
          value={value}
          min={min}
          max={max}
          step={step}
          onChange={(e) => onChange(parseFloat(e.target.value))}
        />
      )}
    </div>
  );
}

export function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { id: string; name: string }[];
  onChange: (id: string) => void;
}) {
  return (
    <div className="mb-1.5 flex items-center justify-between gap-2 text-xs">
      <span className="shrink-0 text-slate-300">{label}</span>
      <select
        className="w-full rounded bg-slate-800 px-1.5 py-1 text-xs text-slate-100 outline-none"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </select>
    </div>
  );
}

export function Chip({
  active,
  color,
  children,
  onClick,
}: {
  active: boolean;
  color?: string;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-2 py-0.5 text-[11px] transition-colors ${
        active
          ? "border-transparent text-slate-900"
          : "border-slate-600 text-slate-400 hover:border-slate-400"
      }`}
      style={active ? { background: color ?? "#38bdf8" } : undefined}
    >
      {children}
    </button>
  );
}
