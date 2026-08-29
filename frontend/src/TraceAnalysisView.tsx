import { useEffect, useMemo, useState } from "react";
import { fetchTrace, fetchTraceList } from "./api";
import LineChart from "./LineChart";
import { Playback } from "./playback";
import type { DynamicTraceDetail, DynamicTraceListItem } from "./types";
import { JOINT_LABELS } from "./types";

function Metric({ label, value, alert = false }: { label: string; value: string; alert?: boolean }) {
  return (
    <div className={`rounded border px-2 py-1.5 ${alert ? "border-red-500/50 bg-red-500/10" : "border-slate-700 bg-slate-800/60"}`}>
      <div className="text-[9px] uppercase tracking-wide text-slate-500">{label}</div>
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

  if (!traces.length && !busy && !error) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center bg-slate-950 p-6">
        <div className="max-w-lg rounded-xl border border-slate-700 bg-slate-900 p-5 text-center">
          <div className="text-lg font-semibold text-slate-100">尚無 Dynamic Run Trace</div>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            請到「即時互動」或「三機同步比較」開始記錄，完成後回到這裡分析 realized simulation。
          </p>
          <button className="mt-3 rounded bg-sky-500 px-3 py-1.5 text-xs font-bold text-slate-950" onClick={() => void refresh()}>
            重新整理
          </button>
        </div>
      </div>
    );
  }

  const manifest = detail?.manifest;
  const summary = manifest?.summary;
  const rawTime = detail?.series.time ?? [];
  const t0 = rawTime[0] ?? 0;
  const time = rawTime.map((value) => value - t0);
  const jointNames = manifest?.joint_names ?? [];
  const actualJoint = detail?.series.joint_q.map((row) => row[joint] ?? 0) ?? [];
  const referenceJoint = detail?.series.joint_q_ref.map((row) => row[joint] ?? 0) ?? [];
  const torque = detail?.series.joint_tau.map((row) => row[joint] ?? 0) ?? [];

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-slate-950">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-slate-800 bg-slate-900/70 px-3 py-2">
        <span className="rounded border border-amber-500/50 bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-300">
          SIMULATED REALIZED OUTPUT / NOT PHYSICAL MEASUREMENT
        </span>
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
        <button className="rounded bg-slate-700 px-2 py-1 text-xs hover:bg-slate-600" onClick={() => void refresh()}>
          {busy ? "讀取中…" : "重新整理"}
        </button>
        {manifest && (
          <span className="ml-auto text-[10px] text-slate-500">
            {manifest.run_id} ｜ {manifest.sample_rate_hz.toFixed(0)} Hz ｜ {manifest.sample_count} samples
          </span>
        )}
      </div>

      {error && <div className="m-3 rounded border border-red-500/50 bg-red-950/60 p-2 text-xs text-red-200">{error}</div>}

      {detail && manifest && summary && (
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          <div className="grid grid-cols-4 gap-2 xl:grid-cols-8">
            <Metric label="Controller" value={manifest.controller} />
            <Metric label="Final state" value={summary.final_state} alert={summary.fell} />
            <Metric label="Duration" value={`${summary.duration_s.toFixed(2)} s`} />
            <Metric label="Distance" value={`${summary.distance_m.toFixed(3)} m`} />
            <Metric label="Average vx" value={`${summary.average_forward_speed_mps.toFixed(3)} m/s`} />
            <Metric label="Max pitch" value={`${summary.max_abs_pitch_deg.toFixed(1)}°`} />
            <Metric label="Max roll" value={`${summary.max_abs_roll_deg.toFixed(1)}°`} />
            <Metric label="Absolute work" value={`${summary.absolute_mechanical_work_j.toFixed(1)} J`} />
          </div>

          {manifest.task && (
            <section className={`mt-3 rounded-lg border p-3 ${manifest.task.evaluation.status === "PASS" ? "border-emerald-500/40 bg-emerald-500/5" : manifest.task.evaluation.status === "FAIL" ? "border-red-500/40 bg-red-500/5" : "border-amber-500/40 bg-amber-500/5"}`}>
              <div className="flex flex-wrap items-center gap-3">
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-slate-500">Formal Motion Task</div>
                  <div className="text-sm font-bold text-slate-100">{manifest.task.contract.name}</div>
                </div>
                <span className={`rounded px-3 py-1 text-sm font-black ${manifest.task.evaluation.status === "PASS" ? "bg-emerald-500/20 text-emerald-300" : manifest.task.evaluation.status === "FAIL" ? "bg-red-500/20 text-red-300" : "bg-amber-500/20 text-amber-300"}`}>
                  {manifest.task.evaluation.status}
                </span>
                <span className="text-[10px] text-slate-400">
                  {manifest.task.task_id}｜{manifest.task.evaluation.evaluated_samples} samples｜target {manifest.task.contract.gait.speed.toFixed(1)} m/s
                </span>
                <div className="ml-auto flex flex-wrap gap-1">
                  {manifest.task.contract.phases.map((phase) => (
                    <span key={phase.id} className="rounded border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[9px] text-violet-200">
                      {phase.id} {phase.start_s.toFixed(1)}–{phase.end_s.toFixed(1)}s
                    </span>
                  ))}
                </div>
              </div>
              {manifest.task.evaluation.criteria.length > 0 ? (
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-left text-[10px]">
                    <thead className="border-b border-slate-700 text-slate-500">
                      <tr><th className="py-1">Criterion</th><th>Measured</th><th>Limit</th><th>Result</th></tr>
                    </thead>
                    <tbody>
                      {manifest.task.evaluation.criteria.map((criterion) => (
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
              ) : (
                <div className="mt-2 text-xs text-amber-300">任務已取消；partial trace 保留，但不產生成功判定。</div>
              )}
            </section>
          )}

          <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
            <section className="rounded border border-slate-800 bg-slate-900/50 p-2">
              <div className="mb-1 text-xs font-semibold text-slate-300">姿態與前進速度</div>
              <LineChart time={time} playback={playback} height={200} unit="deg / m/s" series={[
                { label: "pitch", color: "#f97316", data: detail.series.pitch_deg },
                { label: "roll", color: "#e879f9", data: detail.series.roll_deg },
                { label: "vx", color: "#38bdf8", data: detail.series.com_vel.map((row) => row[0]) },
              ]} />
            </section>
            <section className="rounded border border-slate-800 bg-slate-900/50 p-2">
              <div className="mb-1 text-xs font-semibold text-slate-300">模擬接觸 GRF</div>
              <LineChart time={time} playback={playback} height={200} unit="N" series={[
                { label: "Left GRF", color: "#ef4444", data: detail.series.grf_lr.map((row) => row[0]) },
                { label: "Right GRF", color: "#3b82f6", data: detail.series.grf_lr.map((row) => row[1]) },
              ]} />
            </section>
            <section className="rounded border border-slate-800 bg-slate-900/50 p-2">
              <div className="mb-1 flex items-center justify-between text-xs font-semibold text-slate-300">
                <span>關節 realized vs reference</span>
                <select className="rounded bg-slate-800 px-2 py-0.5 text-[10px]" value={joint} onChange={(event) => setJoint(Number(event.target.value))}>
                  {jointNames.map((name, index) => <option key={name} value={index}>{JOINT_LABELS[name] ?? name}</option>)}
                </select>
              </div>
              <LineChart time={time} playback={playback} height={200} unit="rad" series={[
                { label: "Realized q", color: "#38bdf8", data: actualJoint },
                { label: "Reference q", color: "#fbbf24", data: referenceJoint },
              ]} />
            </section>
            <section className="rounded border border-slate-800 bg-slate-900/50 p-2">
              <div className="mb-1 text-xs font-semibold text-slate-300">關節 torque、tracking error 與 saturation</div>
              <LineChart time={time} playback={playback} height={200} unit="mixed" series={[
                { label: "Torque (Nm)", color: "#4ade80", data: torque },
                { label: "Tracking RMSE (rad)", color: "#fbbf24", data: detail.series.tracking_rmse_rad },
                { label: "Max saturation (%)", color: "#f87171", data: detail.series.max_saturation_pct },
              ]} />
            </section>
            <section className="rounded border border-slate-800 bg-slate-900/50 p-2 xl:col-span-2">
              <div className="mb-1 text-xs font-semibold text-slate-300">Mechanical power proxy</div>
              <LineChart time={time} playback={playback} height={180} unit="W" series={[
                { label: "Positive power", color: "#22d3ee", data: detail.series.positive_power_w },
                { label: "Absolute power", color: "#a78bfa", data: detail.series.absolute_power_w },
              ]} />
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
