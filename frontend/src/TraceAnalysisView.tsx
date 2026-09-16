import { useEffect, useMemo, useState } from "react";
import { fetchTrace, fetchTraceList } from "./api";
import LineChart, { type ChartBand, type ChartMarker, type Series } from "./LineChart";
import PlaybackBar from "./PlaybackBar";
import { Playback } from "./playback";
import type { DynamicTraceDetail, DynamicTraceListItem } from "./types";
import { JOINT_LABELS } from "./types";
import { Disclosure, Tabs } from "./ui";

// 每個分頁是一到兩張各有自己 y 軸的小圖；不同單位絕不共用同一軸。
type TraceTab = "pose" | "contact" | "joint" | "tracking" | "power";
const TRACE_TABS: { id: TraceTab; label: string }[] = [
  { id: "pose", label: "姿態與速度" },
  { id: "contact", label: "接觸 GRF" },
  { id: "joint", label: "關節角度與扭矩" },
  { id: "tracking", label: "追蹤誤差與飽和" },
  { id: "power", label: "功率 proxy" },
];

// 類別色：深色面板上驗證過的兩到三個 slot（藍／橘／青綠）；顏色跟著實體走，不跟排序走。
const SERIES_BLUE = "#3987e5";
const SERIES_ORANGE = "#d95926";
// 狀態色：專門給控制器狀態，不拿來當資料序列色。
const STATE_STYLE: Record<string, { label: string; color: string }> = {
  STAND: { label: "站立", color: "#34d399" },
  WALK: { label: "行走", color: "#38bdf8" },
  STOPPING: { label: "停止中", color: "#fbbf24" },
  FALLEN: { label: "跌倒", color: "#f87171" },
};
const DEFAULT_STATE_CODES: Record<string, string> = { "0": "STAND", "1": "WALK", "2": "FALLEN", "3": "STOPPING" };

interface ChartSpec {
  title: string;
  unit: string;
  series: Series[];
  refLines?: { value: number; color: string; label: string }[];
}

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
  const [tab, setTab] = useState<TraceTab>("pose");
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
  const t0 = detail?.series.time[0] ?? 0;

  // 時間軸從 0 起算
  const time = useMemo(() => (detail?.series.time ?? []).map((value) => value - t0), [detail, t0]);

  // 控制器狀態色帶：state_code 連續相同的區段合成一段
  const bands: ChartBand[] = useMemo(() => {
    if (!detail) return [];
    const codes = detail.series.state_code;
    const names = detail.manifest.state_codes ?? DEFAULT_STATE_CODES;
    const out: ChartBand[] = [];
    let start = 0;
    for (let i = 1; i <= codes.length; i++) {
      if (i === codes.length || codes[i] !== codes[start]) {
        const name = names[String(codes[start])] ?? "UNKNOWN";
        const style = STATE_STYLE[name] ?? { label: name, color: "#64748b" };
        out.push({ t0: time[start], t1: time[Math.min(i, codes.length - 1)], color: style.color, label: style.label });
        start = i;
      }
    }
    return out;
  }, [detail, time]);
  const statesPresent = useMemo(() => [...new Set(bands.map((b) => b.label))], [bands]);

  // 垂直標記：第一次跌倒、正式任務各階段起點
  const markers: ChartMarker[] = useMemo(() => {
    if (!summary) return [];
    const out: ChartMarker[] = [];
    if (summary.fell && summary.first_fall_time_s != null) {
      out.push({ t: summary.first_fall_time_s - t0, label: "跌倒", color: "#f87171" });
    }
    for (const phase of manifest?.task?.contract.phases ?? []) {
      if (phase.start_s > 0) out.push({ t: phase.start_s, label: phase.id, color: "#9085e9" });
    }
    return out;
  }, [summary, manifest, t0]);

  const charts: ChartSpec[] = useMemo(() => {
    if (!detail) return [];
    const s = detail.series;
    switch (tab) {
      case "pose":
        return [
          { title: "軀幹姿態", unit: "°", series: [
            { label: "pitch", color: SERIES_BLUE, data: s.pitch_deg },
            { label: "roll", color: SERIES_ORANGE, data: s.roll_deg },
          ] },
          { title: "前進速度 vx", unit: " m/s", series: [
            { label: "vx", color: SERIES_BLUE, data: s.com_vel.map((row) => row[0]) },
          ] },
        ];
      case "contact":
        return [
          { title: "模擬接觸地面反力", unit: " N", series: [
            { label: "左腳", color: SERIES_BLUE, data: s.grf_lr.map((row) => row[0]) },
            { label: "右腳", color: SERIES_ORANGE, data: s.grf_lr.map((row) => row[1]) },
          ] },
        ];
      case "joint":
        return [
          { title: `關節角度：${JOINT_LABELS[jointNames[joint]] ?? jointNames[joint] ?? "—"}`, unit: " rad", series: [
            { label: "實際", color: SERIES_BLUE, data: s.joint_q.map((row) => row[joint] ?? 0) },
            { label: "參考", color: SERIES_ORANGE, data: s.joint_q_ref.map((row) => row[joint] ?? 0) },
          ] },
          { title: "關節扭矩", unit: " Nm", series: [
            { label: "扭矩", color: SERIES_BLUE, data: s.joint_tau.map((row) => row[joint] ?? 0) },
          ] },
        ];
      case "tracking":
        return [
          { title: "追蹤 RMSE（全關節）", unit: " rad", series: [
            { label: "RMSE", color: SERIES_BLUE, data: s.tracking_rmse_rad },
          ] },
          { title: "最大馬達飽和", unit: "%", series: [
            { label: "飽和", color: SERIES_BLUE, data: s.max_saturation_pct },
          ], refLines: [{ value: 100, color: "#f8717188", label: "峰值 100%" }] },
        ];
      case "power":
        return [
          { title: "機械功率 proxy", unit: " W", series: [
            { label: "正功率", color: SERIES_BLUE, data: s.positive_power_w },
            { label: "絕對功率", color: SERIES_ORANGE, data: s.absolute_power_w },
          ] },
        ];
    }
  }, [detail, tab, joint, jointNames]);

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
  const chartHeight = charts.length > 1 ? 190 : 300;

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
            <Metric label="最終狀態" value={STATE_STYLE[summary.final_state]?.label ?? summary.final_state} alert={summary.fell} />
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

          <section className="mt-3 overflow-hidden rounded border border-slate-800 bg-slate-900/50">
            <div className="flex flex-wrap items-center gap-2 px-2 pt-2">
              <Tabs value={tab} onChange={setTab} items={TRACE_TABS} />
              {tab === "joint" && (
                <select
                  className="rounded bg-slate-800 px-2 py-1 text-xs"
                  value={joint}
                  onChange={(event) => setJoint(Number(event.target.value))}
                >
                  {jointNames.map((name, index) => <option key={name} value={index}>{JOINT_LABELS[name] ?? name}</option>)}
                </select>
              )}
              <span className="ml-auto flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                <span>圖頂色帶：控制器狀態</span>
                {statesPresent.map((label) => {
                  const style = Object.values(STATE_STYLE).find((item) => item.label === label);
                  return (
                    <span key={label} className="flex items-center gap-1">
                      <span className="inline-block h-2 w-3 rounded-sm" style={{ background: style?.color ?? "#64748b" }} />
                      {label}
                    </span>
                  );
                })}
                <span className="text-slate-600">｜滑過看數值，點一下定位播放</span>
              </span>
            </div>
            <div className="grid gap-2 px-2 pb-2 pt-1">
              {charts.map((chart) => (
                <div key={chart.title}>
                  <div className="mb-0.5 text-xs font-semibold text-slate-300">
                    {chart.title}
                    <span className="ml-1 text-[11px] font-normal text-slate-500">{chart.unit.trim()}</span>
                  </div>
                  <LineChart
                    time={time}
                    playback={playback}
                    height={chartHeight}
                    unit={chart.unit}
                    series={chart.series}
                    refLines={chart.refLines ?? []}
                    markers={markers}
                    bands={bands}
                  />
                </div>
              ))}
            </div>
            <PlaybackBar playback={playback} />
          </section>
        </div>
      )}
    </div>
  );
}
