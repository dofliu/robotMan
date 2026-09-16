import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchDefaults, simulate } from "./api";
import type { Defaults, GaitParams, Obstacle, RobotConfig, SimResult } from "./types";
import { JOINT_LABELS } from "./types";
import { Playback } from "./playback";
import Viewport from "./Viewport";
import LineChart, { type ChartBand, type ChartMarker, type Series } from "./LineChart";
import PlaybackBar from "./PlaybackBar";
import GaitPanel from "./panels/GaitPanel";
import HardwarePanel from "./panels/HardwarePanel";
import MassPanel from "./panels/MassPanel";
import ScenePanel from "./panels/ScenePanel";
import SummaryBar, { UtilTable } from "./panels/SummaryBar";
import LiveView from "./LiveView";
import CompareView from "./CompareView";
import TraceAnalysisView from "./TraceAnalysisView";
import TrainingView from "./TrainingView";
import { Chip, Pill, Tabs, type PillTone } from "./ui";

// 關節序列色跟著「關節群組」走（6 個實體），左右腳以線型區分（左實線、右虛線），
// 不再為 12 個關節各配一色。六色在深色面板通過相鄰對 CVD 驗證；預設同時畫的
// 腿部三組（髖 pitch／膝／踝 = 藍／橘／青綠）兩兩皆強分離。六組全開時
// 洋紅↔青綠（deutan）與紫↔藍（一般視覺）較接近，靠讀數列的線頭＋文字標籤補足。
const GROUP_COLORS: Record<string, string> = {
  hip_pitch: "#3987e5",
  knee: "#d95926",
  ankle: "#199e70",
  hip_roll: "#c98500",
  shoulder: "#d55181",
  elbow: "#9085e9",
};
const RIGHT_DASH = [6, 4];
function jointStyle(joint: string): { color: string; dash?: number[] } {
  const group = joint.replace(/_(l|r)$/, "");
  return { color: GROUP_COLORS[group] ?? "#94a3b8", dash: joint.endsWith("_r") ? RIGHT_DASH : undefined };
}
// 支撐相色帶：雙腳＝中性灰，左／右腳沿用 GRF 圖的左藍右橘，騰空＝黃
const SUPPORT_STYLE = {
  double: { label: "雙腳支撐", color: "#64748b" },
  left: { label: "左腳支撐", color: "#3987e5" },
  right: { label: "右腳支撐", color: "#d95926" },
  flight: { label: "騰空", color: "#c98500" },
} as const;
type SupportPhase = keyof typeof SUPPORT_STYLE;

function serializeConfig(robot: RobotConfig, gait: GaitParams, obstacles: Obstacle[]): string {
  // freshness 必須比較完整序列化內容；短 hash 僅作 UI 識別，不能作正確性判斷。
  return JSON.stringify({ robot, gait, obstacles });
}

function configFingerprint(payload: string): string {
  // 32-bit FNV 只提供容易閱讀的本機短 ID，不宣稱為正式 checksum。
  let hash = 0x811c9dc5;
  for (let i = 0; i < payload.length; i++) {
    hash ^= payload.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return `ui-cfg-${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

function shortSha256(value: string): string {
  const normalized = value.replace(/^sha256:/i, "");
  return normalized.length > 16
    ? `${normalized.slice(0, 12)}…${normalized.slice(-4)}`
    : normalized;
}

interface RunConfigSnapshot {
  robot: RobotConfig;
  gait: GaitParams;
  obstacles: Obstacle[];
}

function cloneRunConfig(robot: RobotConfig, gait: GaitParams, obstacles: Obstacle[]): RunConfigSnapshot {
  // API config 是純 JSON 數值物件；深拷貝可確保 stale result 的規格參考不受後續 UI 編輯影響。
  return JSON.parse(JSON.stringify({ robot, gait, obstacles })) as RunConfigSnapshot;
}

type View = "analysis" | "live" | "compare" | "training";
type AnalysisSource = "reference" | "trace";
type ParamTab = "gait" | "hardware" | "mass" | "scene";
type ChartTab = "torque" | "angle" | "grf" | "power" | "stab" | "util";

const VIEW_TABS: { id: View; label: string }[] = [
  { id: "analysis", label: "分析模式" },
  { id: "live", label: "即時互動" },
  { id: "compare", label: "三機同步比較" },
  { id: "training", label: "RL 訓練" },
];
const SOURCE_TABS: { id: AnalysisSource; label: string }[] = [
  { id: "reference", label: "Reference 估算" },
  { id: "trace", label: "Dynamic Trace" },
];
const PARAM_TABS: { id: ParamTab; label: string }[] = [
  { id: "gait", label: "步態" },
  { id: "hardware", label: "硬體" },
  { id: "mass", label: "質量" },
  { id: "scene", label: "場景" },
];
const CHART_TABS: { id: ChartTab; label: string }[] = [
  { id: "torque", label: "關節扭矩" },
  { id: "angle", label: "關節角度" },
  { id: "grf", label: "解析 GRF" },
  { id: "power", label: "功率估計" },
  { id: "stab", label: "ZMP 指標" },
  { id: "util", label: "致動器利用率" },
];
const CHART_UNIT: Record<ChartTab, string> = {
  torque: " Nm", angle: "°", grf: " N", power: " W", stab: " cm", util: "",
};

// 每個畫面對應的模擬類型 token（完整字串留在證據狀態抽屜）
const SCOPE_TOKEN: Record<Exclude<View, "analysis">, string> = {
  live: "MUJOCO_CONTACT_SIM",
  compare: "MUJOCO_SAME_INPUT_INDEPENDENT_PLANTS",
  training: "OFFLINE_TRAINING_CONFIGURATION_ONLY",
};

type ResultState =
  | "NO_RESULT"
  | "RUNNING_NO_RESULT"
  | "RUNNING_LAST_SUCCESS_FROZEN"
  | "REQUEST_FRESH_HASH_UNVERIFIED"
  | "STALE_LAST_SUCCESS";
const RESULT_STATE_TEXT: Record<ResultState, { text: string; tone: PillTone }> = {
  NO_RESULT: { text: "尚無結果", tone: "slate" },
  RUNNING_NO_RESULT: { text: "計算中", tone: "sky" },
  RUNNING_LAST_SUCCESS_FROZEN: { text: "計算中（顯示上次結果）", tone: "sky" },
  REQUEST_FRESH_HASH_UNVERIFIED: { text: "結果對應目前設定", tone: "sky" },
  STALE_LAST_SUCCESS: { text: "設定已變更，結果過期", tone: "amber" },
};

function EvidenceRow({ label, value, tone = "slate" }: { label: string; value: string; tone?: PillTone }) {
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="w-40 shrink-0 text-slate-500">{label}</span>
      <Pill tone={tone} className="font-mono font-normal">{value}</Pill>
    </div>
  );
}

export default function App() {
  const [defaults, setDefaults] = useState<Defaults | null>(null);
  const [robot, setRobot] = useState<RobotConfig | null>(null);
  const [gait, setGait] = useState<GaitParams | null>(null);
  const [obstacles, setObstacles] = useState<Obstacle[]>([
    { x: 3.5, depth: 0.3, height: 0.15, width: 1.2 },
  ]);
  const [result, setResult] = useState<SimResult | null>(null);
  const [resultConfigId, setResultConfigId] = useState<string | null>(null);
  const [resultConfigExact, setResultConfigExact] = useState<string | null>(null);
  const [resultConfigSnapshot, setResultConfigSnapshot] = useState<RunConfigSnapshot | null>(null);
  const [resultFresh, setResultFresh] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoRun, setAutoRun] = useState(true);
  const [selJoints, setSelJoints] = useState<string[]>(["hip_pitch_l", "knee_l", "ankle_l"]);
  const [motorSide, setMotorSide] = useState(false);
  const [view, setView] = useState<View>("analysis");
  const [analysisSource, setAnalysisSource] = useState<AnalysisSource>("reference");
  const [paramTab, setParamTab] = useState<ParamTab>("gait");
  const [chartTab, setChartTab] = useState<ChartTab>("torque");
  const [chartsOpen, setChartsOpen] = useState(true);
  const [showEvidence, setShowEvidence] = useState(false);

  const currentConfigExact = useMemo(
    () => (robot && gait ? serializeConfig(robot, gait, obstacles) : null),
    [robot, gait, obstacles]
  );
  const currentConfigId = useMemo(
    () => (currentConfigExact ? configFingerprint(currentConfigExact) : null),
    [currentConfigExact]
  );
  const previousConfigExactRef = useRef<string | null>(null);

  useEffect(() => {
    if (!currentConfigExact) return;
    if (previousConfigExactRef.current === null) {
      previousConfigExactRef.current = currentConfigExact;
      return;
    }
    if (previousConfigExactRef.current !== currentConfigExact) {
      previousConfigExactRef.current = currentConfigExact;
      setResultFresh(false);
    }
  }, [currentConfigExact]);

  const playback = useMemo(() => new Playback(), []);
  useEffect(() => {
    playback.start();
    return () => playback.stop();
  }, [playback]);

  const abortRef = useRef<AbortController | null>(null);
  const requestSequenceRef = useRef(0);

  const runSim = useCallback(
    async (r: RobotConfig, g: GaitParams, obs: Obstacle[]) => {
      const requestSequence = ++requestSequenceRef.current;
      const requestConfigExact = serializeConfig(r, g, obs);
      const requestConfigId = configFingerprint(requestConfigExact);
      abortRef.current?.abort();
      const ctl = new AbortController();
      abortRef.current = ctl;
      setBusy(true);
      setError(null);
      // 新 run 完成前只保留「上次成功結果」；即使本次失敗也不會回復為 request-fresh。
      setResultFresh(false);
      try {
        const res = await simulate(r, g, obs, ctl.signal);
        // AbortSignal 以外再加 sequence guard，避免較舊 response 晚到後覆寫較新的成功 run。
        if (requestSequence !== requestSequenceRef.current) return;
        setResult(res);
        setResultConfigId(requestConfigId);
        setResultConfigExact(requestConfigExact);
        setResultConfigSnapshot(cloneRunConfig(r, g, obs));
        setResultFresh(true);
        playback.duration = res.frames.time[res.frames.time.length - 1];
        if (playback.t > playback.duration) playback.t = 0;
      } catch (e: any) {
        if (requestSequence === requestSequenceRef.current && e.name !== "AbortError") {
          setResultFresh(false);
          setError(String(e.message ?? e));
        }
      } finally {
        if (requestSequence === requestSequenceRef.current && abortRef.current === ctl) setBusy(false);
      }
    },
    [playback]
  );

  // 初始化：抓預設配置後跑第一次模擬
  useEffect(() => {
    fetchDefaults()
      .then((d) => {
        setDefaults(d);
        setRobot(d.robot);
        setGait(d.gait);
        runSim(d.robot, d.gait, [{ x: 3.5, depth: 0.3, height: 0.15, width: 1.2 }]);
      })
      .catch((e) => setError(`無法連線後端：${e.message}。請確認 backend/main.py 已啟動。`));
  }, [runSim]);

  // 參數變更 → 800ms 防抖後自動重新模擬
  const firstRef = useRef(true);
  useEffect(() => {
    if (!robot || !gait) return;
    if (firstRef.current) {
      firstRef.current = false;
      return;
    }
    if (!autoRun) return;
    const id = setTimeout(() => runSim(robot, gait, obstacles), 800);
    return () => clearTimeout(id);
  }, [robot, gait, obstacles, autoRun, runSim]);

  // 圖表資料：一次只畫一個分頁
  const time = result?.frames.time ?? [];
  const jointNames = result?.meta.joint_names ?? [];
  const jointSeries = useCallback(
    (source: number[][], scale = 1): Series[] =>
      selJoints
        .filter((j) => jointNames.includes(j))
        .map((j) => {
          const ji = jointNames.indexOf(j);
          const style = jointStyle(j);
          return {
            label: JOINT_LABELS[j] ?? j,
            color: style.color,
            dash: style.dash,
            data: source.map((row) => row[ji] * scale),
          };
        }),
    [selJoints, jointNames]
  );

  const chartSeries: Series[] = useMemo(() => {
    if (!result) return [];
    switch (chartTab) {
      case "torque":
        return jointSeries(motorSide ? result.telemetry.tau_motor : result.telemetry.tau);
      case "angle":
        return jointSeries(result.telemetry.q, 180 / Math.PI);
      case "grf":
        return [
          { label: "左腳 Fz", color: "#3987e5", data: result.gait.grf_l.map((f) => f[2]) },
          { label: "右腳 Fz", color: "#d95926", data: result.gait.grf_r.map((f) => f[2]) },
        ];
      case "power":
        return [{
          label: "簡化電功率估計",
          color: "#3987e5",
          data: result.telemetry.power.map((row) => row.reduce((a, b) => a + b, 0)),
        }];
      case "stab":
        return [
          {
            label: "ZMP 裕度",
            color: "#3987e5",
            data: result.stability.zmp_margin.map((v) => (v === null ? null : v * 100)),
          },
          {
            label: "CoM 靜態裕度",
            color: "#d95926",
            data: result.stability.com_margin.map((v) => (v === null ? null : v * 100)),
          },
        ];
      default:
        return [];
    }
  }, [result, chartTab, motorSide, jointSeries]);

  // 單選關節時顯示額定/峰值參考線（只在扭矩分頁）
  const refLines = useMemo(() => {
    if (!result || !resultConfigSnapshot || selJoints.length !== 1) return [];
    const j = selJoints[0];
    const group = j.replace(/_(l|r)$/, "");
    const act = resultConfigSnapshot.robot.actuators[group];
    if (!act) return [];
    const k = motorSide ? 1 : act.gear.ratio * act.gear.efficiency;
    return [
      { value: act.motor.rated_torque * k, color: "#fbbf2488", label: "額定" },
      { value: -act.motor.rated_torque * k, color: "#fbbf2488", label: "" },
      { value: act.motor.peak_torque * k, color: "#f8717188", label: "峰值" },
      { value: -act.motor.peak_torque * k, color: "#f8717188", label: "" },
    ];
  }, [result, resultConfigSnapshot, selJoints, motorSide]);
  const chartRefLines = chartTab === "torque"
    ? refLines
    : chartTab === "stab"
      ? [{ value: 0, color: "#f8717188", label: "支撐面邊界" }]
      : [];
  const showJointChips = chartTab === "torque" || chartTab === "angle";

  // 圖頂色帶：由接觸權重判定每個時刻的支撐相，連續相同的合成一段
  const supportBands: ChartBand[] = useMemo(() => {
    if (!result) return [];
    const { contact_l, contact_r } = result.gait;
    const t = result.frames.time;
    const phaseAt = (i: number): SupportPhase => {
      const l = contact_l[i] > 0.05, r = contact_r[i] > 0.05;
      return l && r ? "double" : l ? "left" : r ? "right" : "flight";
    };
    const out: ChartBand[] = [];
    let start = 0;
    for (let i = 1; i <= t.length; i++) {
      if (i === t.length || phaseAt(i) !== phaseAt(start)) {
        const style = SUPPORT_STYLE[phaseAt(start)];
        out.push({ t0: t[start], t1: t[Math.min(i, t.length - 1)], color: style.color, label: style.label });
        start = i;
      }
    }
    return out;
  }, [result]);
  const supportPhasesPresent = useMemo(
    () => (Object.keys(SUPPORT_STYLE) as SupportPhase[]).filter((k) => supportBands.some((b) => b.label === SUPPORT_STYLE[k].label)),
    [supportBands],
  );
  // 致動器統計窗的起迄：利用率表與警告用的就是這一段
  const chartMarkers: ChartMarker[] = useMemo(() => {
    const window = result?.meta.summary.actuator_stats_window;
    if (!window || window.mode !== "steady_window") return [];
    return [
      { t: window.start_s, label: "統計窗起", color: "#9085e9" },
      { t: window.end_s, label: "統計窗迄", color: "#9085e9" },
    ];
  }, [result]);

  const resultIsRequestFresh = Boolean(
    result && resultFresh && !busy && resultConfigExact && resultConfigExact === currentConfigExact
  );
  const resultState: ResultState = !result
    ? busy ? "RUNNING_NO_RESULT" : "NO_RESULT"
    : busy ? "RUNNING_LAST_SUCCESS_FROZEN"
    : resultIsRequestFresh ? "REQUEST_FRESH_HASH_UNVERIFIED"
    : "STALE_LAST_SUCCESS";
  const resultStateInfo = RESULT_STATE_TEXT[resultState];
  const scopeToken = view === "analysis"
    ? analysisSource === "trace" ? "MUJOCO_REALIZED_SIMULATION_TRACE" : "KINEMATIC_INVERSE_DYNAMICS_ESTIMATE"
    : SCOPE_TOKEN[view];
  const showReferenceIdentity = view === "analysis" && analysisSource === "reference";

  return (
    <div className="flex h-full flex-col">
      {/* 頂部：標題 + 模式切換 + 證據狀態 */}
      <header className="flex shrink-0 items-center gap-3 border-b border-slate-800 bg-slate-900/70 px-3 py-2">
        <span className="text-sm font-bold text-slate-100">人形機器人模擬器</span>
        <Tabs value={view} onChange={setView} items={VIEW_TABS} size="md" />
        <div className="ml-auto flex items-center gap-2">
          {showReferenceIdentity && (
            <Pill tone={resultStateInfo.tone} title={resultState}>{resultStateInfo.text}</Pill>
          )}
          <button
            type="button"
            className={`rounded border px-2 py-1 text-[11px] ${showEvidence ? "border-slate-500 text-slate-200" : "border-slate-700 text-slate-400 hover:text-slate-200"}`}
            onClick={() => setShowEvidence((open) => !open)}
            title="模擬類型、設定 ID 與結果狀態的完整 token"
          >
            證據狀態 {showEvidence ? "▾" : "▸"}
          </button>
        </div>
      </header>

      {showEvidence && (
        <div className="shrink-0 border-b border-slate-800 bg-slate-950/80 px-3 py-2">
          <div className="grid gap-1 md:grid-cols-2">
            <EvidenceRow label="證據範圍" value="SOFTWARE_ONLY" tone="amber" />
            <EvidenceRow label="模擬類型" value={scopeToken} tone="sky" />
            <EvidenceRow label="校正狀態" value="CALIBRATION_NOT_ESTABLISHED" tone="fuchsia" />
            <EvidenceRow label="UI 目前設定 ID" value={currentConfigId ?? "—"} />
            {showReferenceIdentity && (
              <>
                <EvidenceRow label="結果對應的設定 ID" value={resultConfigId ?? "—"} />
                <EvidenceRow
                  label="伺服器回報 config sha256"
                  value={result?.meta.provenance?.config_hash ? shortSha256(result.meta.provenance.config_hash) : "—"}
                  tone="cyan"
                />
                <EvidenceRow label="結果狀態" value={resultState} tone={resultStateInfo.tone} />
                <EvidenceRow label="Run ID" value={result?.meta.provenance?.run_id ?? "LEGACY_NO_RUN_ID"} />
              </>
            )}
          </div>
          <div className="mt-1.5 text-[11px] text-slate-500">
            所有數值皆為軟體模擬且未經實體校正；這裡顯示正常不代表任何 V0/V1 gate PASS。
          </div>
        </div>
      )}

      {view === "training" ? (
        <TrainingView />
      ) : view === "compare" && robot && gait ? (
        <CompareView robot={robot} gait={gait} obstacles={obstacles} />
      ) : view === "live" && robot && gait ? (
        <LiveView robot={robot} gait={gait} obstacles={obstacles} />
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-slate-800 bg-slate-900/40 px-3 py-1.5">
            <Tabs value={analysisSource} onChange={setAnalysisSource} items={SOURCE_TABS} />
            <span className="text-[11px] text-slate-500">
              {analysisSource === "reference"
                ? "prescribed 步態 → 逆動力學估算；適合看相對趨勢與敏感度"
                : "讀取即時互動／三機比較保存的 500 Hz realized 模擬紀錄"}
            </span>
          </div>

          {analysisSource === "trace" ? (
            <TraceAnalysisView />
          ) : (
            <div className="flex min-h-0 flex-1">
              {/* 左側設定欄：一次只顯示一組參數 */}
              <aside className="flex w-[300px] shrink-0 flex-col border-r border-slate-800 bg-slate-900/40">
                <div className="flex items-center gap-2 border-b border-slate-800 px-3 py-2">
                  <button
                    type="button"
                    className="flex-1 rounded bg-sky-500 py-1.5 text-xs font-bold text-slate-900 hover:bg-sky-400 disabled:opacity-50"
                    disabled={busy || !robot || !gait}
                    onClick={() => robot && gait && runSim(robot, gait, obstacles)}
                  >
                    {busy ? "計算中…" : "▶ 執行模擬"}
                  </button>
                  <label className="flex items-center gap-1 text-[11px] text-slate-400" title="參數變更後 0.8 秒自動重新模擬">
                    <input
                      type="checkbox"
                      checked={autoRun}
                      onChange={(e) => setAutoRun(e.target.checked)}
                    />
                    自動
                  </label>
                </div>
                <div className="border-b border-slate-800 px-3 py-2">
                  <Tabs value={paramTab} onChange={setParamTab} items={PARAM_TABS} fill />
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
                  {paramTab === "gait" && gait && <GaitPanel gait={gait} onChange={setGait} />}
                  {paramTab === "hardware" && robot && defaults && (
                    <HardwarePanel robot={robot} defaults={defaults} onChange={setRobot} />
                  )}
                  {paramTab === "mass" && robot && <MassPanel robot={robot} onChange={setRobot} />}
                  {paramTab === "scene" && <ScenePanel obstacles={obstacles} onChange={setObstacles} />}
                </div>
              </aside>

              {/* 主區域 */}
              <main className="flex min-w-0 flex-1 flex-col">
                <SummaryBar result={result} />
                <div className="relative min-h-0 flex-1">
                  <Viewport result={result} playback={playback} />
                  {busy && (
                    <div className="absolute inset-0 flex items-center justify-center bg-slate-950/40">
                      <div className="rounded-lg bg-slate-800 px-4 py-2 text-sm text-sky-300">
                        逆動力學計算中…
                      </div>
                    </div>
                  )}
                  {result && !resultIsRequestFresh && (
                    <div
                      data-testid="stale-result-overlay"
                      className="absolute left-3 top-3 rounded-lg border border-amber-500/60 bg-amber-950/90 px-3 py-2 text-xs font-semibold text-amber-200 shadow-lg"
                    >
                      {busy ? "計算中，畫面為上次結果" : "設定已變更，畫面為過期結果"}
                      <span className="ml-2 font-normal text-amber-300/80">
                        結果設定 {resultConfigId ?? "LEGACY_UNKNOWN"}
                      </span>
                    </div>
                  )}
                  {error && (
                    <div className="absolute left-1/2 top-3 -translate-x-1/2 rounded-lg bg-red-500/90 px-4 py-2 text-xs text-white">
                      {error}
                    </div>
                  )}
                  <div className="absolute bottom-2 left-2 rounded bg-slate-900/70 px-2 py-1 text-[11px] leading-4 text-slate-400">
                    🟡 質心 CoM ｜ 🟢 ZMP ｜ 紅/藍箭頭：左右腳地面反力 ｜ 青色線：LiDAR 射線
                  </div>
                </div>
                <PlaybackBar playback={playback} />

                {/* 底部圖表區：一次一張圖，可整區收合 */}
                <section className={`flex shrink-0 flex-col border-t border-slate-800 bg-slate-900/50 ${chartsOpen ? "h-[270px]" : ""}`}>
                  <div className="flex shrink-0 flex-wrap items-center gap-2 px-2 py-1.5">
                    <Tabs value={chartTab} onChange={setChartTab} items={CHART_TABS} />
                    {chartsOpen && chartTab === "torque" && (
                      <>
                        <Chip active={!motorSide} onClick={() => setMotorSide(false)}>關節端</Chip>
                        <Chip active={motorSide} onClick={() => setMotorSide(true)}>馬達端</Chip>
                        {refLines.length >= 3 && (
                          <span
                            data-testid="torque-ref-source"
                            data-result-config={resultConfigId ?? ""}
                            data-rated-torque={Math.abs(refLines[0].value)}
                            data-peak-torque={Math.abs(refLines[2].value)}
                            className="text-[11px] text-slate-500"
                          >
                            額定 {Math.abs(refLines[0].value).toFixed(1)} / 峰值 {Math.abs(refLines[2].value).toFixed(1)} Nm（依結果設定 {resultConfigId ?? "—"}）
                          </span>
                        )}
                      </>
                    )}
                    {chartsOpen && chartTab !== "util" && supportPhasesPresent.length > 0 && (
                      <span className="ml-auto flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                        <span>圖頂色帶：支撐相</span>
                        {supportPhasesPresent.map((k) => (
                          <span key={k} className="flex items-center gap-1">
                            <span className="inline-block h-2 w-3 rounded-sm" style={{ background: SUPPORT_STYLE[k].color }} />
                            {SUPPORT_STYLE[k].label}
                          </span>
                        ))}
                        <span className="text-slate-600">｜滑過看數值，點一下定位播放</span>
                      </span>
                    )}
                    <button
                      type="button"
                      className={`${chartsOpen && chartTab !== "util" && supportPhasesPresent.length > 0 ? "" : "ml-auto "}text-[11px] text-slate-400 hover:text-slate-200`}
                      onClick={() => setChartsOpen((open) => !open)}
                    >
                      {chartsOpen ? "收合圖表 ▾" : "展開圖表 ▸"}
                    </button>
                  </div>
                  {chartsOpen && (
                    <div className="flex min-h-0 flex-1 flex-col px-2 pb-2">
                      {showJointChips && (
                        <div className="mb-1 flex flex-wrap gap-1">
                          {jointNames.map((j) => (
                            <Chip
                              key={j}
                              active={selJoints.includes(j)}
                              color={jointStyle(j).color}
                              onClick={() =>
                                setSelJoints((prev) =>
                                  prev.includes(j) ? prev.filter((x) => x !== j) : [...prev, j]
                                )
                              }
                            >
                              {JOINT_LABELS[j] ?? j}
                            </Chip>
                          ))}
                          <span className="ml-1 self-center text-[11px] text-slate-500">左實線、右虛線</span>
                        </div>
                      )}
                      <div className="min-h-0 flex-1 overflow-hidden">
                        {chartTab === "util" ? (
                          <UtilTable result={result} />
                        ) : (
                          <LineChart
                            time={time}
                            series={chartSeries}
                            playback={playback}
                            height={showJointChips ? 180 : 210}
                            unit={CHART_UNIT[chartTab]}
                            refLines={chartRefLines}
                            bands={supportBands}
                            markers={chartMarkers}
                          />
                        )}
                      </div>
                    </div>
                  )}
                </section>
              </main>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
