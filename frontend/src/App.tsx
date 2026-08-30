import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchDefaults, simulate } from "./api";
import type { Defaults, GaitParams, Obstacle, RobotConfig, SimResult } from "./types";
import { JOINT_LABELS } from "./types";
import { Playback } from "./playback";
import Viewport from "./Viewport";
import LineChart, { type Series } from "./LineChart";
import GaitPanel from "./panels/GaitPanel";
import HardwarePanel from "./panels/HardwarePanel";
import MassPanel from "./panels/MassPanel";
import ScenePanel from "./panels/ScenePanel";
import SummaryBar, { UtilTable } from "./panels/SummaryBar";
import LiveView from "./LiveView";
import CompareView from "./CompareView";
import TraceAnalysisView from "./TraceAnalysisView";
import TrainingView from "./TrainingView";
import { Chip } from "./ui";

const JOINT_COLORS = [
  "#38bdf8", "#f472b6", "#4ade80", "#fbbf24", "#a78bfa", "#fb923c",
  "#22d3ee", "#f87171", "#a3e635", "#e879f9", "#fde047", "#94a3b8",
];

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

function PlaybackBar({ playback }: { playback: Playback }) {
  const [, force] = useState(0);
  const [t, setT] = useState(0);
  const lastRef = useRef(0);
  useEffect(() => {
    return playback.subscribe((tt) => {
      if (Math.abs(tt - lastRef.current) > 0.05) {
        lastRef.current = tt;
        setT(tt);
      }
    });
  }, [playback]);
  return (
    <div className="flex items-center gap-3 border-t border-slate-800 bg-slate-900/70 px-3 py-1.5">
      <button
        className="w-8 rounded bg-slate-700 py-0.5 text-sm hover:bg-slate-600"
        onClick={() => {
          playback.playing = !playback.playing;
          force((x) => x + 1);
        }}
      >
        {playback.playing ? "⏸" : "▶"}
      </button>
      <input
        type="range"
        className="flex-1"
        min={0}
        max={playback.duration || 1}
        step={0.01}
        value={t}
        onChange={(e) => {
          playback.seek(parseFloat(e.target.value));
          playback.playing = false;
          force((x) => x + 1);
        }}
      />
      <span className="w-20 text-right text-xs tabular-nums text-slate-400">
        {t.toFixed(2)} / {playback.duration.toFixed(1)}s
      </span>
      <select
        className="rounded bg-slate-800 px-1 py-0.5 text-xs text-slate-200"
        defaultValue="1"
        onChange={(e) => (playback.speed = parseFloat(e.target.value))}
      >
        <option value="0.1">0.1×</option>
        <option value="0.25">0.25×</option>
        <option value="0.5">0.5×</option>
        <option value="1">1×</option>
        <option value="2">2×</option>
      </select>
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
  const [rightTab, setRightTab] = useState<"grf" | "power" | "angle" | "stab">("grf");
  const [view, setView] = useState<"analysis" | "live" | "compare" | "training">("analysis");
  const [analysisSource, setAnalysisSource] = useState<"reference" | "trace">("reference");

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

  // 圖表資料
  const time = result?.frames.time ?? [];
  const jointNames = result?.meta.joint_names ?? [];
  const torqueSeries: Series[] = useMemo(() => {
    if (!result) return [];
    const src = motorSide ? result.telemetry.tau_motor : result.telemetry.tau;
    return selJoints
      .filter((j) => jointNames.includes(j))
      .map((j) => {
        const ji = jointNames.indexOf(j);
        return {
          label: JOINT_LABELS[j] ?? j,
          color: JOINT_COLORS[ji % JOINT_COLORS.length],
          data: src.map((row) => row[ji]),
        };
      });
  }, [result, selJoints, motorSide, jointNames]);

  const rightSeries: Series[] = useMemo(() => {
    if (!result) return [];
    if (rightTab === "grf") {
      return [
        { label: "左腳 Fz", color: "#f87171", data: result.gait.grf_l.map((f) => f[2]) },
        { label: "右腳 Fz", color: "#60a5fa", data: result.gait.grf_r.map((f) => f[2]) },
      ];
    }
    if (rightTab === "power") {
      return [
        {
          label: "簡化電功率估計",
          color: "#fbbf24",
          data: result.telemetry.power.map((row) => row.reduce((a, b) => a + b, 0)),
        },
      ];
    }
    if (rightTab === "stab") {
      return [
        {
          label: "ZMP 裕度",
          color: "#4ade80",
          data: result.stability.zmp_margin.map((v) => (v === null ? null : v * 100)),
        },
        {
          label: "CoM 靜態裕度",
          color: "#fbbf24",
          data: result.stability.com_margin.map((v) => (v === null ? null : v * 100)),
        },
      ];
    }
    return selJoints
      .filter((j) => jointNames.includes(j))
      .map((j) => {
        const ji = jointNames.indexOf(j);
        return {
          label: JOINT_LABELS[j] ?? j,
          color: JOINT_COLORS[ji % JOINT_COLORS.length],
          data: result.telemetry.q.map((row) => (row[ji] * 180) / Math.PI),
        };
      });
  }, [result, rightTab, selJoints, jointNames]);

  // 單選關節時顯示額定/峰值參考線
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

  const resultIsRequestFresh = Boolean(
    result && resultFresh && !busy && resultConfigExact && resultConfigExact === currentConfigExact
  );
  const resultState = !result
    ? busy ? "RUNNING_NO_RESULT" : "NO_RESULT"
    : busy ? "RUNNING_LAST_SUCCESS_FROZEN"
    : resultIsRequestFresh ? "REQUEST_FRESH_HASH_UNVERIFIED"
    : "STALE_LAST_SUCCESS";
  const resultStateClass = resultState === "REQUEST_FRESH_HASH_UNVERIFIED"
    ? "border-sky-500/40 bg-sky-500/10 text-sky-300"
    : resultState.startsWith("RUNNING")
      ? "border-sky-500/40 bg-sky-500/10 text-sky-300"
      : resultState.startsWith("STALE")
        ? "border-amber-500/40 bg-amber-500/10 text-amber-300"
        : "border-slate-600 bg-slate-800/60 text-slate-400";

  return (
    <div className="flex h-full flex-col">
      {/* 頂部：標題 + 模式切換 */}
      <header className="flex shrink-0 items-center gap-4 border-b border-slate-800 bg-slate-900/70 px-3 py-1.5">
        <div>
          <span className="text-sm font-bold text-slate-100">🤖 人形機器人設計篩選模擬原型</span>
          <span className="ml-2 text-[10px] text-slate-500">SIM-only reduced-order ｜ software screening</span>
        </div>
        <div className="flex gap-1">
          <button
            className={`rounded-t px-3 py-1 text-xs font-semibold ${
              view === "analysis" ? "bg-sky-500 text-slate-900" : "bg-slate-800 text-slate-300 hover:bg-slate-700"
            }`}
            onClick={() => setView("analysis")}
          >
            📊 分析模式
          </button>
          <button
            className={`rounded-t px-3 py-1 text-xs font-semibold ${
              view === "live" ? "bg-purple-400 text-slate-900" : "bg-slate-800 text-slate-300 hover:bg-slate-700"
            }`}
            onClick={() => setView("live")}
          >
            🎮 即時互動（動力學 + 平衡控制）
          </button>
          <button
            className={`rounded-t px-3 py-1 text-xs font-semibold ${
              view === "compare" ? "bg-amber-400 text-slate-900" : "bg-slate-800 text-slate-300 hover:bg-slate-700"
            }`}
            onClick={() => setView("compare")}
          >
            ⚖ 三機同步比較
          </button>
          <button
            className={`rounded-t px-3 py-1 text-xs font-semibold ${
              view === "training" ? "bg-fuchsia-400 text-slate-900" : "bg-slate-800 text-slate-300 hover:bg-slate-700"
            }`}
            onClick={() => setView("training")}
          >
            🧠 RL 訓練
          </button>
          {view === "analysis" && (
            <div className="ml-2 flex gap-1 border-l border-slate-700 pl-2">
              <button
                className={`rounded px-2 py-1 text-[10px] font-semibold ${analysisSource === "reference" ? "bg-sky-500/30 text-sky-200" : "bg-slate-800 text-slate-400"}`}
                onClick={() => setAnalysisSource("reference")}
              >
                Reference 估算
              </button>
              <button
                className={`rounded px-2 py-1 text-[10px] font-semibold ${analysisSource === "trace" ? "bg-cyan-500/30 text-cyan-200" : "bg-slate-800 text-slate-400"}`}
                onClick={() => setAnalysisSource("trace")}
              >
                Dynamic Trace
              </button>
            </div>
          )}
        </div>
      </header>

      <div className="flex shrink-0 flex-wrap items-center gap-1.5 border-b border-slate-800 bg-slate-950/80 px-3 py-1 text-[9px] font-semibold tracking-wide">
        <span className="rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-amber-300">
          SOFTWARE_ONLY
        </span>
        <span className="rounded border border-sky-500/40 bg-sky-500/10 px-1.5 py-0.5 text-sky-300">
          {view === "analysis"
            ? analysisSource === "trace"
              ? "MUJOCO_REALIZED_SIMULATION_TRACE"
              : "KINEMATIC_INVERSE_DYNAMICS_ESTIMATE"
            : view === "compare"
              ? "MUJOCO_SAME_INPUT_INDEPENDENT_PLANTS"
              : view === "training"
                ? "OFFLINE_TRAINING_CONFIGURATION_ONLY"
                : "MUJOCO_CONTACT_SIM"}
        </span>
        <span className="rounded border border-fuchsia-500/40 bg-fuchsia-500/10 px-1.5 py-0.5 text-fuchsia-300">
          CALIBRATION_NOT_ESTABLISHED
        </span>
        <span className="ml-1 text-slate-500">UI_INPUT {currentConfigId ?? "—"}</span>
        {view === "analysis" && analysisSource === "reference" && (
          <>
            <span className="text-slate-500">UI_RESULT_CONFIG {resultConfigId ?? "—"}</span>
            {result?.meta.provenance?.config_hash && (
              <span className="text-cyan-400">
                SERVER_REPORTED_CONFIG_SHA256 {shortSha256(result.meta.provenance.config_hash)}
              </span>
            )}
            <span className={`rounded border px-1.5 py-0.5 ${resultStateClass}`}>{resultState}</span>
            <span className="text-slate-600">
              RUN {result?.meta.provenance?.run_id ?? "LEGACY_NO_RUN_ID"}
            </span>
          </>
        )}
      </div>

      {view === "training" ? (
        <TrainingView />
      ) : view === "compare" && robot && gait ? (
        <CompareView robot={robot} gait={gait} obstacles={obstacles} />
      ) : view === "live" && robot && gait ? (
        <LiveView robot={robot} gait={gait} obstacles={obstacles} />
      ) : analysisSource === "trace" ? (
        <TraceAnalysisView />
      ) : (
      <div className="flex min-h-0 flex-1">
      {/* 左側設定欄 */}
      <aside className="flex w-[330px] shrink-0 flex-col border-r border-slate-800 bg-slate-900/40">
        <div className="flex items-center gap-2 border-b border-slate-800 px-3 py-2">
          <button
            className="flex-1 rounded bg-sky-500 py-1.5 text-xs font-bold text-slate-900 hover:bg-sky-400 disabled:opacity-50"
            disabled={busy || !robot || !gait}
            onClick={() => robot && gait && runSim(robot, gait, obstacles)}
          >
            {busy ? "計算中…" : "▶ 執行模擬"}
          </button>
          <label className="flex items-center gap-1 text-[10px] text-slate-400">
            <input
              type="checkbox"
              checked={autoRun}
              onChange={(e) => setAutoRun(e.target.checked)}
            />
            自動
          </label>
        </div>
        <div className="flex-1 overflow-y-auto">
          {gait && <GaitPanel gait={gait} onChange={setGait} />}
          {robot && defaults && (
            <HardwarePanel robot={robot} defaults={defaults} onChange={setRobot} />
          )}
          {robot && <MassPanel robot={robot} onChange={setRobot} />}
          <ScenePanel obstacles={obstacles} onChange={setObstacles} />
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
              {busy ? "FROZEN LAST SUCCESS" : "STALE LAST SUCCESS"}
              <span className="ml-2 font-normal text-amber-300/80">
                result config {resultConfigId ?? "LEGACY_UNKNOWN"}
              </span>
            </div>
          )}
          {error && (
            <div className="absolute left-1/2 top-3 -translate-x-1/2 rounded-lg bg-red-500/90 px-4 py-2 text-xs text-white">
              {error}
            </div>
          )}
          <div className="absolute bottom-2 left-2 rounded bg-slate-900/70 px-2 py-1 text-[10px] leading-4 text-slate-400">
            🟡 質心 CoM ｜ 🟢 ZMP ｜ 紅/藍箭頭：左右腳地面反力 ｜ 青色線：LiDAR 射線
          </div>
        </div>
        <PlaybackBar playback={playback} />

        {/* 底部圖表區 */}
        <section className="flex h-[290px] shrink-0 border-t border-slate-800 bg-slate-900/50">
          <div className="flex min-w-0 flex-[1.3] flex-col border-r border-slate-800 p-2">
            <div className="mb-1 flex flex-wrap items-center gap-1">
              <span className="mr-1 text-xs font-semibold text-slate-300">
                {motorSide ? "馬達端扭矩 (Nm)" : "關節扭矩 (Nm)"}
              </span>
              <Chip active={!motorSide} onClick={() => setMotorSide(false)}>關節端</Chip>
              <Chip active={motorSide} onClick={() => setMotorSide(true)}>馬達端</Chip>
              {refLines.length >= 3 && (
                <span
                  data-testid="torque-ref-source"
                  data-result-config={resultConfigId ?? ""}
                  data-rated-torque={Math.abs(refLines[0].value)}
                  data-peak-torque={Math.abs(refLines[2].value)}
                  className="text-[9px] text-slate-500"
                >
                  frozen {resultConfigId ?? "—"}：額定 {Math.abs(refLines[0].value).toFixed(1)} / 峰值 {Math.abs(refLines[2].value).toFixed(1)} Nm
                </span>
              )}
              <span className="mx-1 text-slate-700">|</span>
              {jointNames.map((j, i) => (
                <Chip
                  key={j}
                  active={selJoints.includes(j)}
                  color={JOINT_COLORS[i % JOINT_COLORS.length]}
                  onClick={() =>
                    setSelJoints((prev) =>
                      prev.includes(j) ? prev.filter((x) => x !== j) : [...prev, j]
                    )
                  }
                >
                  {JOINT_LABELS[j] ?? j}
                </Chip>
              ))}
            </div>
            <div className="min-h-0 flex-1">
              <LineChart
                time={time}
                series={torqueSeries}
                playback={playback}
                height={210}
                unit=" Nm"
                refLines={refLines}
              />
            </div>
          </div>
          <div className="flex min-w-0 flex-1 flex-col border-r border-slate-800 p-2">
            <div className="mb-1 flex items-center gap-1">
              <Chip active={rightTab === "grf"} onClick={() => setRightTab("grf")}>解析 GRF</Chip>
              <Chip active={rightTab === "power"} onClick={() => setRightTab("power")}>功率估計</Chip>
              <Chip active={rightTab === "angle"} onClick={() => setRightTab("angle")}>關節角度</Chip>
              <Chip active={rightTab === "stab"} onClick={() => setRightTab("stab")}>ZMP 指標</Chip>
            </div>
            <div className="min-h-0 flex-1">
              <LineChart
                time={time}
                series={rightSeries}
                playback={playback}
                height={210}
                unit={rightTab === "grf" ? " N" : rightTab === "power" ? " W" : rightTab === "stab" ? " cm" : "°"}
                refLines={rightTab === "stab" ? [{ value: 0, color: "#f8717188", label: "支撐面邊界" }] : []}
              />
            </div>
          </div>
          <div className="w-[290px] shrink-0">
            <UtilTable result={result} />
          </div>
        </section>
      </main>
      </div>
      )}
    </div>
  );
}
