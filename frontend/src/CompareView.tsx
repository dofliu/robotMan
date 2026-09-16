import { useCallback, useEffect, useRef, useState } from "react";
import type { GaitParams, Obstacle, RobotConfig } from "./types";
import type { MotionTaskResult } from "./types";
import {
  LiveScene3D,
  type LiveErrorMessage,
  type LiveFrame,
  type LiveScene,
  type MotionTaskStatus,
  type TraceReceipt,
  type CompareController,
} from "./LiveView";
import { Pill } from "./ui";

const CONTROLLERS: CompareController[] = ["track", "raibert", "rl"];
const LABELS: Record<CompareController, string> = {
  track: "Trajectory Tracking",
  raibert: "Raibert Closed-loop",
  rl: "RL Policy (PPO)",
};

interface CompareScene {
  type: "compare_scene";
  controllers: CompareController[];
  scenes: Record<CompareController, LiveScene>;
  plant_signature: string;
  evidence_scope: "DEVELOPMENT_COMPARISON_ONLY";
  plant_isolation: boolean;
  assist_default: boolean;
}

interface CompareFrame {
  type: "compare_frame";
  t: number;
  frames: Record<CompareController, LiveFrame>;
  sync: {
    max_time_skew_s: number;
    same_input: boolean;
    independent_plants: boolean;
  };
}

interface CompareTraceStartedMessage {
  type: "trace_recording_started";
  group_id: string;
  traces: Record<CompareController, { run_id: string }>;
}

interface CompareTraceReadyMessage {
  type: "trace_ready";
  group_id: string;
  traces: Record<CompareController, TraceReceipt>;
}

interface CompareTaskStartedMessage {
  type: "task_started";
  group_id: string;
  plant_signature: string;
  tasks: Record<CompareController, MotionTaskStatus>;
  scenes: Record<CompareController, LiveScene>;
}

interface CompareTaskCancelledMessage {
  type: "task_cancelled";
  group_id: string;
  tasks: Record<CompareController, MotionTaskResult>;
}

type CompareMessage = CompareScene | CompareFrame | LiveErrorMessage
  | CompareTraceStartedMessage | CompareTraceReadyMessage
  | CompareTaskStartedMessage | CompareTaskCancelledMessage;

function RobotCard({
  controller,
  scene,
  frame,
}: {
  controller: CompareController;
  scene?: LiveScene;
  frame?: LiveFrame;
}) {
  const mountRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<LiveScene3D | null>(null);

  useEffect(() => {
    const mount = mountRef.current!;
    const renderer = new LiveScene3D(mount);
    rendererRef.current = renderer;
    const resize = () => renderer.resize(mount.clientWidth, mount.clientHeight);
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(mount);
    return () => {
      observer.disconnect();
      renderer.dispose(mount);
      rendererRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (scene) rendererRef.current?.buildScene(scene);
  }, [scene]);

  useEffect(() => {
    if (frame) rendererRef.current?.updateFrame(frame);
  }, [frame]);

  const ctrl = frame?.ctrl;
  const maxSaturation = ctrl
    ? Math.max(0, ...Object.values(ctrl.saturation).filter(Number.isFinite))
    : 0;
  const stateClass = ctrl?.state === "FALLEN"
    ? "border-red-500/60 text-red-300"
    : ctrl?.state === "STOPPING"
      ? "border-amber-500/50 text-amber-300"
    : ctrl?.state === "WALK"
      ? "border-sky-500/50 text-sky-300"
      : "border-emerald-500/40 text-emerald-300";
  const interventions = frame?.interventions;
  const lastTask = !frame?.motion_task?.active ? frame?.last_task : undefined;
  const flags: { key: string; text: string; tone: "amber" | "red" | "violet" | "emerald" }[] = [];
  if (interventions?.balance_assist_enabled) flags.push({ key: "assist", text: "assist 開", tone: "amber" });
  if (interventions?.startup_assist_active) flags.push({ key: "startup", text: "起步 assist", tone: "red" });
  if (interventions?.external_push_active) flags.push({ key: "push", text: "外力", tone: "red" });
  if (frame?.motion_task?.active) flags.push({ key: "task", text: `任務 ${frame.motion_task.phase ?? ""}`, tone: "violet" });
  if (lastTask) flags.push({ key: "last", text: `任務 ${lastTask.evaluation.status}`, tone: lastTask.evaluation.status === "PASS" ? "emerald" : "red" });

  return (
    <section className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-slate-700 bg-slate-900/60">
      <div className="flex items-center justify-between border-b border-slate-700 px-2 py-1.5">
        <div className="text-xs font-bold text-slate-100">{LABELS[controller]}</div>
        <span className={`rounded border px-1.5 py-0.5 text-[11px] font-bold ${stateClass}`}>
          {ctrl?.state ?? "WAITING"}
        </span>
      </div>
      <div ref={mountRef} className="min-h-0 flex-1" data-testid={`compare-canvas-${controller}`} />
      <div className="grid grid-cols-3 gap-px border-t border-slate-700 bg-slate-700 text-[11px]">
        <div className="bg-slate-900 px-2 py-1">t <b>{frame?.t.toFixed(2) ?? "—"} s</b></div>
        <div className="bg-slate-900 px-2 py-1">x <b>{frame?.xpos?.[0]?.[0]?.toFixed(2) ?? "—"} m</b></div>
        <div className="bg-slate-900 px-2 py-1">vx <b>{ctrl?.com_vel[0].toFixed(2) ?? "—"} m/s</b></div>
        <div className="bg-slate-900 px-2 py-1">pitch <b>{ctrl?.pitch_deg.toFixed(1) ?? "—"}°</b></div>
        <div className="bg-slate-900 px-2 py-1">roll <b>{ctrl?.roll_deg.toFixed(1) ?? "—"}°</b></div>
        <div className="bg-slate-900 px-2 py-1">sat max <b>{maxSaturation.toFixed(0)}%</b></div>
      </div>
      {flags.length > 0 && (
        <div className="flex flex-wrap gap-1 border-t border-slate-800 px-2 py-1">
          {flags.map((flag) => <Pill key={flag.key} tone={flag.tone}>{flag.text}</Pill>)}
        </div>
      )}
    </section>
  );
}

export default function CompareView({
  robot,
  gait,
  obstacles,
}: {
  robot: RobotConfig;
  gait: GaitParams;
  obstacles: Obstacle[];
}) {
  const socketRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [scene, setScene] = useState<CompareScene | null>(null);
  const [frame, setFrame] = useState<CompareFrame | null>(null);
  const [error, setError] = useState<LiveErrorMessage | null>(null);
  const [speed, setSpeed] = useState(0.25);
  const [paused, setPaused] = useState(false);
  const [assist, setAssist] = useState(false);
  const [pushForce, setPushForce] = useState(150);
  const [traceNotice, setTraceNotice] = useState<string | null>(null);
  const [more, setMore] = useState(false);

  const send = useCallback((message: object) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(message));
    } else {
      setError({ type: "error", code: "WS_NOT_OPEN", message: "比較模式連線尚未就緒。" });
    }
  }, []);

  useEffect(() => {
    let disposed = false;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const host = location.port === "5183" ? "127.0.0.1:8710" : location.host;
    const socket = new WebSocket(`${proto}://${host}/ws/compare`);
    socketRef.current = socket;
    socket.onopen = () => {
      setConnected(true);
      setError(null);
      socket.send(JSON.stringify({ type: "init", robot, gait: { ...gait }, obstacles }));
    };
    socket.onerror = () => {
      if (!disposed) setError({ type: "error", code: "WEBSOCKET_ERROR", message: "比較模式 WebSocket 發生錯誤。" });
    };
    socket.onclose = () => {
      if (!disposed) {
        setConnected(false);
        setError((previous) => previous ?? ({
          type: "error", code: "WEBSOCKET_CLOSED", message: "比較模式連線已中斷。",
        }));
      }
    };
    socket.onmessage = (event) => {
      let message: CompareMessage;
      try {
        message = JSON.parse(event.data) as CompareMessage;
      } catch {
        setError({ type: "error", code: "INVALID_JSON", message: "後端比較資料無法解析。" });
        return;
      }
      if (message.type === "error") {
        setError(message);
      } else if (message.type === "compare_scene") {
        setScene(message);
        setAssist(message.assist_default);
      } else if (message.type === "trace_recording_started") {
        setTraceNotice(`三機記錄中：${message.group_id}`);
      } else if (message.type === "trace_ready") {
        setTraceNotice(`三機 Trace 已完成：${message.group_id}`);
      } else if (message.type === "task_started") {
        setScene((previous) => previous ? {
          ...previous,
          plant_signature: message.plant_signature,
          scenes: message.scenes,
        } : null);
        setTraceNotice(`三機正式任務已開始：${message.group_id}`);
      } else if (message.type === "task_cancelled") {
        setTraceNotice(`三機正式任務已取消：${message.group_id}`);
      } else {
        // 每個 compare frame 同時更新三個 renderer，避免視覺時間不同步。
        setFrame(message);
        setPaused(message.frames.track.paused);
        setSpeed(message.frames.track.speed);
        setAssist(Boolean(message.frames.track.assist_enabled));
        if (message.frames.track.last_task && message.frames.track.last_trace) {
          const statuses = CONTROLLERS.map((controller) =>
            `${LABELS[controller]} ${message.frames[controller].last_task?.evaluation.status ?? "—"}`,
          );
          setTraceNotice(`三機正式任務完成：${statuses.join("｜")}`);
        }
      }
    };
    return () => {
      disposed = true;
      socket.close();
    };
    // init 使用進入模式當下的 frozen props；設定改變須重新進入比較模式。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const push = (dx: number, dy: number) =>
    send({ type: "push", dir: [dx, dy, 0], force: pushForce, duration: 0.2 });

  const track = frame?.frames.track;
  const recordingActive = Boolean(track?.recording?.active);
  const taskActive = Boolean(track?.motion_task?.active);
  const skew = frame?.sync.max_time_skew_s;

  return (
    <div className="relative flex min-h-0 flex-1 flex-col bg-slate-950">
      {/* 主工具列：常用操作 */}
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-slate-800 bg-slate-900/60 px-3 py-2">
        <button type="button" className="rounded bg-emerald-600/70 px-3 py-1 text-xs font-semibold" onClick={() => send({ type: "mode", mode: "stand" })}>站立</button>
        <button type="button" className="rounded bg-sky-600/70 px-3 py-1 text-xs font-semibold" onClick={() => send({ type: "mode", mode: "walk" })}>三機開始行走</button>
        <button type="button" className="rounded bg-red-500/30 px-3 py-1 text-xs text-red-200" onClick={() => send({ type: "reset" })}>重置三機</button>
        <span className="mx-1 h-4 w-px bg-slate-700" />
        <button type="button" className="rounded bg-slate-700 px-2 py-1 text-xs" onClick={() => {
          const next = !paused;
          setPaused(next);
          send({ type: "pause", on: next });
        }}>{paused ? "▶ 繼續" : "⏸ 暫停"}</button>
        <button type="button" className="rounded bg-slate-700 px-2 py-1 text-xs" onClick={() => send({ type: "step", dt: 0.05 })}>⏭ 單步 50 ms</button>
        <label className="flex items-center gap-1 text-[11px] text-slate-300">
          速度 {speed.toFixed(2)}×
          <input type="range" min={0.05} max={1} step={0.05} value={speed} onChange={(event) => {
            const value = Number(event.target.value);
            setSpeed(value);
            send({ type: "speed", value });
          }} />
        </label>
        <button
          type="button"
          className={`ml-auto rounded border px-2 py-1 text-[11px] ${more ? "border-slate-500 text-slate-200" : "border-slate-700 text-slate-400 hover:text-slate-200"}`}
          onClick={() => setMore(!more)}
        >
          更多操作 {more ? "▾" : "▸"}
        </button>
      </div>

      {/* 次工具列：推撞、assist、Trace、正式任務 */}
      {more && (
        <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-slate-800 bg-slate-900/40 px-3 py-2">
          <label className="flex items-center gap-1 text-[11px] text-slate-300">
            <input type="checkbox" checked={assist} onChange={(event) => {
              const on = event.target.checked;
              setAssist(on);
              send({ type: "assist", on });
            }} />
            外加 assist（預設 OFF）
          </label>
          <span className="mx-1 h-4 w-px bg-slate-700" />
          <label className="flex items-center gap-1 text-[11px] text-slate-300">
            推力 {pushForce} N
            <input type="range" min={50} max={600} step={25} value={pushForce} onChange={(event) => setPushForce(Number(event.target.value))} />
          </label>
          <button type="button" className="rounded bg-orange-500/30 px-2 py-1 text-xs" onClick={() => push(1, 0)}>向前推</button>
          <button type="button" className="rounded bg-orange-500/30 px-2 py-1 text-xs" onClick={() => push(-1, 0)}>向後推</button>
          <button type="button" className="rounded bg-orange-500/30 px-2 py-1 text-xs" onClick={() => push(0, 1)}>側向推</button>
          <span className="mx-1 h-4 w-px bg-slate-700" />
          <button
            type="button"
            className={`rounded px-3 py-1 text-xs font-semibold ${recordingActive ? "bg-red-500/40 text-red-200" : "bg-cyan-500/30 text-cyan-200"}`}
            onClick={() => send(recordingActive
              ? { type: "record_stop" }
              : { type: "record_start", label: "three-controller-compare", max_duration_s: 30.0 })}
          >
            {recordingActive ? "■ 停止三機 Trace" : "● 記錄三機 Trace"}
          </button>
          <button
            type="button"
            className={`rounded px-3 py-1 text-xs font-bold ${taskActive ? "bg-red-500/40 text-red-200" : "bg-violet-500/40 text-violet-100"}`}
            title="stand → start → steady walk → stop｜9.0 s｜0.7 m/s｜500 Hz｜assist OFF｜reset + clear obstacles"
            onClick={() => send(taskActive
              ? { type: "task_cancel" }
              : { type: "task_start", task_id: "stand_start_walk_stop_v1" })}
          >
            {taskActive ? "■ 取消三機正式任務" : "▶ 三機執行正式任務"}
          </button>
        </div>
      )}

      {(taskActive || traceNotice) && (
        <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-slate-800 bg-slate-900/30 px-3 py-1 text-[11px]">
          {taskActive && track?.motion_task && (
            <span className="font-semibold text-violet-200">
              正式任務 {track.motion_task.phase}｜{track.motion_task.elapsed_s?.toFixed(1)} / 9.0 s
            </span>
          )}
          {traceNotice && (
            <span className="text-cyan-300">{traceNotice}｜完成後到「分析模式 → Dynamic Trace」查看三組 realized outputs。</span>
          )}
        </div>
      )}

      <div className="flex min-h-0 flex-1 gap-2 p-2">
        {CONTROLLERS.map((controller) => (
          <RobotCard
            key={controller}
            controller={controller}
            scene={scene?.scenes[controller]}
            frame={frame?.frames[controller]}
          />
        ))}
      </div>

      <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-t border-slate-800 px-3 py-1 text-[11px] text-slate-500">
        <span>僅供開發比較，不是驗證證據（DEVELOPMENT_COMPARISON_ONLY）</span>
        <span>相同輸入、三個獨立 plant</span>
        <span className={skew === 0 ? "text-emerald-400/80" : skew === undefined ? "" : "text-red-300"}>
          time skew {skew?.toFixed(6) ?? "—"} s
        </span>
        <span>plant {scene?.plant_signature.slice(0, 20) ?? "—"}</span>
      </div>

      {(!connected || error) && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-slate-950/60">
          <div className={`rounded-lg border px-4 py-3 text-sm ${error ? "border-red-500/50 bg-red-950/90 text-red-200" : "border-slate-600 bg-slate-800 text-amber-300"}`}>
            {error ? `ERROR ${error.code}：${error.message}` : "正在初始化三個 controller…"}
          </div>
        </div>
      )}
    </div>
  );
}
