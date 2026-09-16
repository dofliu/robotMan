import { useEffect, useMemo, useState } from "react";
import { fetchTrace, fetchTraceList } from "./api";
import LineChart, { type Series } from "./LineChart";
import { Playback } from "./playback";
import type { DynamicTraceDetail, DynamicTraceListItem } from "./types";
import { JOINT_LABELS } from "./types";
import { Disclosure, Tabs } from "./ui";

type TraceChart = "pose" | "grf" | "joint" | "torque" | "power";
const TRACE_CHARTS: { id: TraceChart; label: string }[] = [
  { id: "pose", label: "姿態與速度" },
  { id: "grf", label: "模擬接觸 GRF" },
  { id: "joint", label: "關節 realized vs reference" },
  { id: "torque", label: "扭矩／追蹤誤差／飽和" },
  { id: "power", label: "功率 proxy" },
];
const TRACE_UNIT: Record<TraceChart, string> = {
  pose: "deg / m/s",
  grf: "N",
  joint: "rad",
  torque: "mixed",
  power: "W",
};

function Metric({ label, value, alert = false }: { label: string; value: string; alert?: boolean }) {
  return (
    <div className={`rounded border px-2 py-1.5 ${alert ? "border-red-500/50 bg-red-500/10" : "border-slate-700 bg-slate-800/60"}`}>
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className={`mt-0.5 text-sm font-semibold ${alert ? "text-red-300" : "text-slate-100"}`}>{value}</div>
    </div>
  );
}

function formatCriterionValue(value: string | number | boolean | number[]) {
  if (Array.isArray(value)) return value.map((item) => Number(item).toFixed(3)).join(" – ");
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3);
  return String(value);
}

export default function TraceAnalysisView() {
  const [traces, setTraces] = useState<DynamicTraceListItem[]>([]);
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<DynamicTraceDetail | null>(null);
  const [joint, setJoint] = useState(0);
  const [chart, setChart] = useState<TraceChart>("pose");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const playback = useMemo(() => new Playback(), []);

  const refresh = async () => {
    setBusy(true);
    setError(null);
    try {
      const items = await fetchTraceList();
      setTraces(items);
      setSelected((current) => current || items[0]?.run_id || "");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    playback.start();
    void refresh();
    return () => playback.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playback]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    let active = true;
    setBusy(true);
    setError(null);
    fetchTrace(selected)
      .then((result) => {
        if (!active) return;
        setDetail(result);
        setJoint(0);
        const time = result.series.time;
        playback.duration = time.length ? time[time.length - 1] - time[0] : 0;
        playback.t = 0;
      })
      .catch((cause) => active && setError(cause instanceof Error ? cause.message : String(cause)))
      .finally(() => active && setBusy(false));
    return () => { active = false; };
  }, [selected, playback]);

  const manifest = detail?.manifest;
  const summary = manifest?.summary;
  const jointNames = manifest?.joint_names ?? [];

  const time = useMemo(() => {
    const raw = detail?.series.time ?? [];
    const t0 = raw[0] ?? 0;
    return raw.map((value) => value - t0);
  }, [detail]);

  const series: Series[] = useMemo(() => {
    if (!detail) return [];
    const s = detail.series;
    switch (chart) {
      case "pose":
        return [
          { label: "pitch", color: "#f97316", data: s.pitch_deg },
          { label: "roll", color: "#e879f9", data: s.roll_deg },
          { label: "vx", color: "#38bdf8", data: s.com_vel.map((row) => row[0]) },
        ];
      case "grf":
        return [
          { label: "Left GRF", color: "#ef4444", data: s.grf_lr.map((row) => row[0]) },
          { label: "Right GRF", color: "#3b82f6", data: s.grf_lr.map((row) => row[1]) },
        ];
      case "joint":
        return [
          { label: "Realized q", color: "#38bdf8", data: s.joint_q.map((row) => row[joint] ?? 0) },
          { label: "Reference q", color: "#fbbf24", data: s.joint_q_ref.map((row) => row[joint] ?? 0) },
        ];
      case "torque":
        return [
          { label: "Torque (Nm)", color: "#4ade80", data: s.joint_tau.map((row) => row[joint] ?? 0) },
          { label: "Tracking RMSE (rad)", color: "#fbbf24", data: s.tracking_rmse_rad },
          { label: "Max saturation (%)", color: "#f87171", data: s.max_saturation_pct },
        ];
      case "power":
        return [
          { label: "Positive power", color: "#22d3ee", data: s.positive_power_w },
          { label: "Absolute power", color: "#a78bfa", data: s.absolute_power_w },
        ];
    }
  }, [detail, chart, joint]);

  if (!traces.length && !busy && !error) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center bg-slate-950 p-6">
        <div className="max-w-lg rounded-xl border border-slate-700 bg-slate-900 p-5 text-center">
          <div className="text-lg font-semibold text-slate-100">尚無 Dynamic Run Trace</div>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            請到「即時互動」或「三機同步比較」開始記錄，完成後回到這裡分析 realized simulation。
          </p>
          <button type="button" className="mt-3 rounded bg-sky-500 px-3 py-1.5 text-xs font-bold text-slate-950" onClick={() => void refresh()}>
            重新整理
          </button>
        </div>
      </div>
    );
  }

  const task = manifest?.task;
  const taskTone = task?.evaluation.status === "PASS"
    ? "border-emerald-500/40 bg-emerald-500/5"
    : task?.evaluation.status === "FAIL"
      ? "border-red-500/40 bg-red-500/5"
      : "border-amber-500/40 bg-amber-500/5";
  const taskBadge = task?.evaluation.status === "PASS"
    ? "bg-emerald-500/20 text-emerald-300"
    : task?.evaluation.status === "FAIL"
      ? "bg-red-500/20 text-red-300"
      : "bg-amber-500/20 text-amber-300";
  const showJointPicker = chart === "joint" || chart === "torque";

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-slate-950">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-slate-800 bg-slate-900/70 px-3 py-2">
        <select
          className="min-w-[330px] rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-100"
          value={selected}
          onChange={(event) => setSelected(event.target.value)}
        >
          {traces.map((trace) => (
            <option key={trace.run_id} value={trace.run_id}>
              {trace.controller}｜{trace.label || trace.run_id}｜{new Date(trace.completed_at).toLocaleString()}
            </option>
          ))}
        </select>
        <button type="button" className="rounded bg-slate-700 px-2 py-1 text-xs hover:bg-slate-600" onClick={() => void refresh()}>
          {busy ? "讀取中…" : "重新整理"}
        </button>
        <span className="ml-auto text-[11px] text-slate-500">
          模擬 realized 輸出，非實體量測
          {manifest && ` ｜ ${manifest.sample_rate_hz.toFixed(0)} Hz ｜ ${manifest.sample_count} samples`}
        </span>
      </div>

      {error && <div className="m-3 rounded border border-red-500/50 bg-red-950/60 p-2 text-xs text-red-200">{error}</div>}

      {detail && manifest && summary && (
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          <div className="grid grid-cols-4 gap-2 xl:grid-cols-8">
            <Metric label="Controller" value={manifest.controller} />
            <Metric label="最終狀態" value={summary.final_state} alert={summary.fell} />
            <Metric label="時長" value={`${summary.duration_s.toFixed(2)} s`} />
            <Metric label="距離" value={`${summary.distance_m.toFixed(3)} m`} />
            <Metric label="平均 vx" value={`${summary.average_forward_speed_mps.toFixed(3)} m/s`} />
            <Metric label="最大 pitch" value={`${summary.max_abs_pitch_deg.toFixed(1)}°`} />
            <Metric label="最大 roll" value={`${summary.max_abs_roll_deg.toFixed(1)}°`} />
            <Metric label="絕對機械功" value={`${summary.absolute_mechanical_work_j.toFixed(1)} J`} />
          </div>

          {task && (
            <section className={`mt-3 rounded-lg border px-3 py-2 ${taskTone}`}>
              <div className="flex flex-wrap items-center gap-3">
                <div>
                  <div className="text-[11px] text-slate-500">正式動作任務</div>
                  <div className="text-sm font-bold text-slate-100">{task.contract.name}</div>
                </div>
                <span className={`rounded px-3 py-1 text-sm font-black ${taskBadge}`}>{task.evaluation.status}</span>
                <span className="text-[11px] text-slate-400">
                  {task.evaluation.criteria.filter((item) => item.passed).length}/{task.evaluation.criteria.length} criteria 通過｜target {task.contract.gait.speed.toFixed(1)} m/s
                </span>
              </div>
              {task.evaluation.criteria.length > 0 ? (
                <Disclosure title="判定細節" summary={`${task.evaluation.criteria.length} 項 criteria、${task.contract.phases.length} 個階段`} className="mt-2">
                  <div className="mb-2 flex flex-wrap gap-1">
                    {task.contract.phases.map((phase) => (
                      <span key={phase.id} className="rounded border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[11px] text-violet-200">
                        {phase.id} {phase.start_s.toFixed(1)}–{phase.end_s.toFixed(1)}s
                      </span>
                    ))}
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-[11px]">
                      <thead className="border-b border-slate-700 text-slate-500">
                        <tr><th className="py-1">Criterion</th><th>Measured</th><th>Limit</th><th>Result</th></tr>
                      </thead>
                      <tbody>
                        {task.evaluation.criteria.map((criterion) => (
                          <tr key={criterion.id} className="border-b border-slate-800/80">
                            <td className="py-1.5 font-semibold text-slate-300">{criterion.id}</td>
                            <td className="tabular-nums text-slate-300">{formatCriterionValue(criterion.value)} {criterion.unit}</td>
                            <td className="tabular-nums text-slate-500">{criterion.operator} {formatCriterionValue(criterion.limit)}</td>
                            <td className={criterion.passed ? "font-bold text-emerald-300" : "font-bold text-red-300"}>{criterion.passed ? "PASS" : "FAIL"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Disclosure>
              ) : (
                <div className="mt-2 text-xs text-amber-300">任務已取消；partial trace 保留，但不產生成功判定。</div>
              )}
            </section>
          )}

          <section className="mt-3 rounded border border-slate-800 bg-slate-900/50 p-2">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Tabs value={chart} onChange={setChart} items={TRACE_CHARTS} />
              {showJointPicker && (
                <select
                  className="ml-auto rounded bg-slate-800 px-2 py-1 text-xs"
                  value={joint}
                  onChange={(event) => setJoint(Number(event.target.value))}
                >
                  {jointNames.map((name, index) => <option key={name} value={index}>{JOINT_LABELS[name] ?? name}</option>)}
                </select>
              )}
            </div>
            <LineChart time={time} playback={playback} height={340} unit={TRACE_UNIT[chart]} series={series} />
          </section>
        </div>
      )}
    </div>
  );
}
