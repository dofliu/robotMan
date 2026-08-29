import { useState, type ReactNode } from "react";

export function Section({
  title,
  children,
  defaultOpen = true,
}: {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-slate-700/60">
      <button
        className="flex w-full items-center justify-between px-3 py-2 text-sm font-semibold text-sky-300 hover:bg-slate-800/40"
        onClick={() => setOpen(!open)}
      >
        {title}
        <span className="text-slate-500">{open ? "▾" : "▸"}</span>
      </button>
      {open && <div className="px-3 pb-3">{children}</div>}
    </div>
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
