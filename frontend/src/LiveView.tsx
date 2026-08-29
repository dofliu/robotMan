import { useCallback, useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { GaitParams, GeomDef, MotionTaskResult, Obstacle, RobotConfig } from "./types";
import { GROUP_LABELS } from "./types";

// ---------- 型別 ----------
export interface LiveScene {
  type: "scene";
  geoms: GeomDef[];
  body_names: string[];
}
export interface Decision {
  t: number;
  text: string;
  level: string;
}
export type WalkController = "track" | "raibert" | "rl";

export interface LiveErrorMessage {
  type: "error";
  code: string;
  message: string;
}

export interface TraceReceipt {
  run_id: string;
  group_id: string | null;
  controller: string;
  sample_count: number;
  artifact_sha256: string;
  evidence_scope: string;
  task?: MotionTaskResult | null;
}

export interface MotionTaskStatus {
  active: boolean;
  task_id?: string;
  group_id?: string | null;
  phase?: string;
  elapsed_s?: number;
  duration_s?: number;
  target_speed_mps?: number;
}

interface TraceRecordingMessage {
  type: "trace_recording_started";
  trace: { active: boolean; run_id: string; sample_count: number; elapsed_s: number; max_duration_s: number };
}

interface TraceReadyMessage {
  type: "trace_ready";
  trace: TraceReceipt;
}

interface TaskStartedMessage {
  type: "task_started";
  task: MotionTaskStatus;
  scene: LiveScene;
}

interface TaskCancelledMessage {
  type: "task_cancelled";
  task: MotionTaskResult;
}

export interface LiveFrame {
  type: "frame";
  t: number;
  mode: string;
  walk_controller?: WalkController;
  speed: number;
  paused: boolean;
  assist_enabled?: boolean;
  interventions?: {
    balance_assist_enabled: boolean;
    startup_assist_active: boolean;
    external_push_active: boolean;
  };
  xpos: number[][];
  xquat: number[][];
  joints?: {
    q: number[];
    tau: number[];
  };
  ctrl: {
    state: string;
    pitch_deg: number;
    roll_deg: number;
    com: number[];
    com_vel: number[];
    capture_point: number[];
    cop: number[] | null;
    grf: { l: number; r: number };
    contacts: number[][];
    ankle_corr: number;
    roll_corr: number;
    hip_corr: number;
    step_offset: number[];
    saturation: Record<string, number>;
  };
  push: { dir: number[]; force: number } | null;
  decisions: Decision[];
  recording?: {
    active: boolean;
    run_id?: string;
    sample_count?: number;
    elapsed_s?: number;
    max_duration_s?: number;
  };
  last_trace?: TraceReceipt | null;
  trace_error?: LiveErrorMessage | null;
  motion_task?: MotionTaskStatus;
  last_task?: MotionTaskResult | null;
  task_error?: LiveErrorMessage | null;
}

type LiveMessage = LiveScene | LiveFrame | LiveErrorMessage | TraceRecordingMessage | TraceReadyMessage
  | TaskStartedMessage | TaskCancelledMessage;

// ---------- three.js 場景（即時模式專用） ----------
export class LiveScene3D {
  renderer: THREE.WebGLRenderer;
  scene = new THREE.Scene();
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  dynamicRoot = new THREE.Group();
  robotGroups: THREE.Group[] = [];
  comMarker: THREE.Mesh;
  cpMarker: THREE.Mesh;
  copMarker: THREE.Mesh;
  pushArrow: THREE.ArrowHelper;
  contactDots: THREE.Mesh[] = [];

  constructor(mount: HTMLDivElement) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.shadowMap.enabled = true;
    mount.appendChild(this.renderer.domElement);
    this.scene.background = new THREE.Color(0x14181f);
    this.scene.fog = new THREE.Fog(0x14181f, 10, 35);

    this.camera = new THREE.PerspectiveCamera(45, 1, 0.05, 200);
    this.camera.up.set(0, 0, 1);
    this.camera.position.set(-1.8, -2.4, 1.4);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(0, 0, 0.8);
    this.controls.enableDamping = true;

    this.scene.add(new THREE.HemisphereLight(0xbfd4e6, 0x33404d, 0.9));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(3, -4, 8);
    sun.castShadow = true;
    sun.shadow.camera.left = -5;
    sun.shadow.camera.right = 5;
    sun.shadow.camera.top = 5;
    sun.shadow.camera.bottom = -5;
    this.scene.add(sun);

    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(200, 30),
      new THREE.MeshStandardMaterial({ color: 0x232a33, roughness: 0.95 })
    );
    ground.receiveShadow = true;
    this.scene.add(ground);
    const grid = new THREE.GridHelper(200, 200, 0x3a4654, 0x2b333e);
    grid.rotation.x = Math.PI / 2;
    grid.position.z = 0.002;
    this.scene.add(grid);
    this.scene.add(this.dynamicRoot);

    this.comMarker = new THREE.Mesh(
      new THREE.SphereGeometry(0.03),
      new THREE.MeshBasicMaterial({ color: 0xffd54a })
    );
    this.cpMarker = new THREE.Mesh(
      new THREE.CylinderGeometry(0.04, 0.04, 0.004),
      new THREE.MeshBasicMaterial({ color: 0xe879f9 })
    );
    this.cpMarker.rotation.x = Math.PI / 2;
    this.copMarker = new THREE.Mesh(
      new THREE.CylinderGeometry(0.032, 0.032, 0.004),
      new THREE.MeshBasicMaterial({ color: 0x4ade80 })
    );
    this.copMarker.rotation.x = Math.PI / 2;
    this.scene.add(this.comMarker, this.cpMarker, this.copMarker);

    this.pushArrow = new THREE.ArrowHelper(
      new THREE.Vector3(1, 0, 0), new THREE.Vector3(), 0.6, 0xff4444, 0.12, 0.07
    );
    this.pushArrow.visible = false;
    this.scene.add(this.pushArrow);

    for (let i = 0; i < 8; i++) {
      const dot = new THREE.Mesh(
        new THREE.SphereGeometry(0.018),
        new THREE.MeshBasicMaterial({ color: 0x38bdf8 })
      );
      dot.visible = false;
      this.scene.add(dot);
      this.contactDots.push(dot);
    }
  }

  buildScene(msg: LiveScene) {
    this.dynamicRoot.clear();
    this.robotGroups = msg.body_names.map(() => {
      const g = new THREE.Group();
      this.dynamicRoot.add(g);
      return g;
    });
    for (const geom of msg.geoms) {
      if (geom.type === "plane") continue;
      const mat = new THREE.MeshStandardMaterial({
        color: new THREE.Color(geom.rgba[0], geom.rgba[1], geom.rgba[2]),
        roughness: 0.6,
        metalness: 0.25,
      });
      let mesh: THREE.Mesh;
      if (geom.type === "box") {
        mesh = new THREE.Mesh(new THREE.BoxGeometry(geom.size[0] * 2, geom.size[1] * 2, geom.size[2] * 2), mat);
      } else if (geom.type === "sphere") {
        mesh = new THREE.Mesh(new THREE.SphereGeometry(geom.size[0], 24, 16), mat);
      } else {
        const cap = new THREE.CapsuleGeometry(geom.size[0], geom.size[1] * 2, 6, 16);
        cap.rotateX(Math.PI / 2);
        mesh = new THREE.Mesh(cap, mat);
      }
      mesh.castShadow = true;
      mesh.position.set(geom.pos[0], geom.pos[1], geom.pos[2]);
      mesh.quaternion.set(geom.quat[1], geom.quat[2], geom.quat[3], geom.quat[0]);
      if (geom.body === 0) this.dynamicRoot.add(mesh);
      else this.robotGroups[geom.body - 1].add(mesh);
    }
  }

  updateFrame(f: LiveFrame) {
    for (let b = 0; b < this.robotGroups.length; b++) {
      this.robotGroups[b].position.set(f.xpos[b][0], f.xpos[b][1], f.xpos[b][2]);
      this.robotGroups[b].quaternion.set(f.xquat[b][1], f.xquat[b][2], f.xquat[b][3], f.xquat[b][0]);
    }
    const c = f.ctrl;
    this.comMarker.position.set(c.com[0], c.com[1], c.com[2]);
    this.cpMarker.position.set(c.capture_point[0], c.capture_point[1], 0.008);
    if (c.cop) {
      this.copMarker.visible = true;
      this.copMarker.position.set(c.cop[0], c.cop[1], 0.006);
    } else this.copMarker.visible = false;

    this.contactDots.forEach((d, i) => {
      if (c.contacts && i < c.contacts.length) {
        d.visible = true;
        d.position.set(c.contacts[i][0], c.contacts[i][1], 0.012);
      } else d.visible = false;
    });

    if (f.push) {
      this.pushArrow.visible = true;
      const trunk = f.xpos[0];
      const dir = new THREE.Vector3(f.push.dir[0], f.push.dir[1], f.push.dir[2] ?? 0).normalize();
      this.pushArrow.position.set(
        trunk[0] - dir.x * 0.65, trunk[1] - dir.y * 0.65, trunk[2] + 0.25 - dir.z * 0.65
      );
      this.pushArrow.setDirection(dir);
      this.pushArrow.setLength(0.5, 0.12, 0.07);
    } else this.pushArrow.visible = false;

    // 相機跟隨
    const dx = f.xpos[0][0] - this.controls.target.x;
    const k = Math.abs(dx) > 1.5 ? 1 : 0.12;
    this.controls.target.x += dx * k;
    this.camera.position.x += dx * k;
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }

  resize(w: number, h: number) {
    this.renderer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  dispose(mount: HTMLDivElement) {
    this.renderer.dispose();
    if (this.renderer.domElement.parentElement === mount) mount.removeChild(this.renderer.domElement);
  }
}

// ---------- UI ----------
const STATE_LABEL: Record<string, [string, string]> = {
  STAND: ["🧍 站立平衡", "bg-emerald-500/20 text-emerald-300"],
  WALK: ["🚶 行走中", "bg-sky-500/20 text-sky-300"],
  FALLEN: ["💥 已跌倒", "bg-red-500/30 text-red-300"],
};

function CorrBar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = Math.min(Math.abs(value) / max, 1) * 50;
  return (
    <div className="mb-1 flex items-center gap-1 text-[10px]">
      <span className="w-16 shrink-0 text-slate-400">{label}</span>
      <div className="relative h-2 flex-1 rounded bg-slate-800">
        <div className="absolute left-1/2 top-0 h-full w-px bg-slate-600" />
        <div
          className="absolute top-0 h-full rounded bg-sky-400"
          style={value >= 0 ? { left: "50%", width: `${pct}%` } : { right: "50%", width: `${pct}%` }}
        />
      </div>
      <span className="w-14 text-right tabular-nums text-slate-300">{value.toFixed(0)} Nm</span>
    </div>
  );
}

export default function LiveView({
  robot,
  gait,
  obstacles,
}: {
  robot: RobotConfig;
  gait: GaitParams;
  obstacles: Obstacle[];
}) {
  const mountRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<LiveScene3D | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [liveError, setLiveError] = useState<LiveErrorMessage | null>(null);
  const [frame, setFrame] = useState<LiveFrame | null>(null);
  const [speed, setSpeed] = useState(0.25);
  const [paused, setPaused] = useState(false);
  const [assist, setAssist] = useState(true);
  const [walkCtrl, setWalkCtrl] = useState<WalkController>("raibert");
  const [pushForce, setPushForce] = useState(150);
  const [obsHeight, setObsHeight] = useState(0.15);
  const [traceNotice, setTraceNotice] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const frameCount = useRef(0);
  const [, forceUi] = useState(0);

  const send = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    } else {
      setLiveError({
        type: "error",
        code: "WS_NOT_OPEN",
        message: "即時模擬連線尚未就緒，命令未送出。",
      });
    }
  }, []);

  // ---------- WebSocket 連線 ----------
  useEffect(() => {
    let disposed = false;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const host = location.port === "5183" ? "127.0.0.1:8710" : location.host;
    const ws = new WebSocket(`${proto}://${host}/ws/live`);
    wsRef.current = ws;
    ws.onopen = () => {
      setConnected(true);
      setLiveError(null);
      // 即時模式必須沿用畫面目前設定，避免分析與 live session 使用不同的隱藏 nominal gait。
      ws.send(JSON.stringify({ type: "init", robot, gait: { ...gait }, obstacles }));
    };
    ws.onerror = () => {
      if (!disposed) {
        setLiveError({ type: "error", code: "WEBSOCKET_ERROR", message: "即時模擬 WebSocket 發生錯誤。" });
      }
    };
    ws.onclose = () => {
      if (!disposed) {
        setConnected(false);
        setLiveError((prev) => prev ?? ({
          type: "error",
          code: "WEBSOCKET_CLOSED",
          message: "即時模擬連線已中斷。",
        }));
      }
    };
    ws.onmessage = (ev) => {
      let msg: LiveMessage;
      try {
        msg = JSON.parse(ev.data) as LiveMessage;
      } catch {
        setLiveError({ type: "error", code: "INVALID_JSON", message: "後端回傳無法解析的即時資料。" });
        return;
      }
      if (msg.type === "error") {
        setLiveError(msg);
        return;
      }
      if (msg.type === "trace_recording_started") {
        setTraceNotice(`記錄中：${msg.trace.run_id}`);
        return;
      }
      if (msg.type === "trace_ready") {
        setTraceNotice(`已完成：${msg.trace.run_id}（${msg.trace.sample_count} samples）`);
        return;
      }
      if (msg.type === "task_started") {
        sceneRef.current?.buildScene(msg.scene);
        setTraceNotice(`正式任務已開始：${msg.task.task_id}`);
        return;
      }
      if (msg.type === "task_cancelled") {
        setTraceNotice(`正式任務已取消：${msg.task.task_id}`);
        return;
      }
      if (msg.type === "scene") {
        sceneRef.current?.buildScene(msg);
      } else if (msg.type === "frame") {
        if (msg.walk_controller) setWalkCtrl(msg.walk_controller);
        if (typeof msg.assist_enabled === "boolean") setAssist(msg.assist_enabled);
        if (Number.isFinite(msg.speed)) setSpeed(msg.speed);
        setPaused(msg.paused);
        if (msg.last_task && msg.last_trace) {
          setTraceNotice(`正式任務 ${msg.last_task.evaluation.status}：${msg.last_trace.run_id}`);
        }
        sceneRef.current?.updateFrame(msg);
        // 面板 5Hz 更新即可，避免 React 重繪過頻
        frameCount.current++;
        if (frameCount.current % 6 === 0) setFrame(msg);
      }
    };
    return () => {
      disposed = true;
      ws.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---------- three 場景 ----------
  useEffect(() => {
    const mount = mountRef.current!;
    const s = new LiveScene3D(mount);
    sceneRef.current = s;
    const resize = () => s.resize(mount.clientWidth, mount.clientHeight);
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(mount);
    return () => {
      ro.disconnect();
      s.dispose(mount);
      sceneRef.current = null;
    };
  }, []);

  // 決策日誌自動捲動
  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [frame?.decisions?.length]);

  const push = (dx: number, dy: number) =>
    send({ type: "push", dir: [dx, dy, 0], force: pushForce, duration: 0.2 });

  const st = frame?.ctrl;
  const [stateLabel, stateCls]: [string, string] = liveError
    ? [`⛔ ERROR ${liveError.code}`, "bg-red-500/30 text-red-300"]
    : !connected
      ? ["🔌 尚未連線", "bg-slate-700/50 text-slate-300"]
      : !st
        ? ["⏳ 已連線，等待 frame", "bg-sky-500/20 text-sky-300"]
        : STATE_LABEL[st.state] ?? [`⚠ 未知狀態 ${st.state}`, "bg-amber-500/20 text-amber-300"];

  return (
    <div className="flex min-h-0 flex-1">
      {/* 左：控制面板 */}
      <aside className="flex w-[290px] shrink-0 flex-col gap-2 overflow-y-auto border-r border-slate-800 bg-slate-900/40 p-2">
        <div className={`rounded-lg px-3 py-2 text-sm font-bold ${stateCls}`}>
          {stateLabel}
          <span className="ml-2 text-[10px] font-normal opacity-70">
            t = {frame?.t?.toFixed(2) ?? "0.00"} s
          </span>
        </div>

        <div className="rounded-lg bg-slate-800/50 p-2">
          <div className="mb-1 text-xs font-semibold text-slate-300">運動模式</div>
          <div className="flex gap-1">
            <button
              className="flex-1 rounded bg-emerald-600/70 py-1.5 text-xs font-semibold hover:bg-emerald-500/70"
              onClick={() => send({ type: "mode", mode: "stand" })}
            >
              🧍 站立平衡
            </button>
            <button
              className="flex-1 rounded bg-sky-600/70 py-1.5 text-xs font-semibold hover:bg-sky-500/70"
              onClick={() => send({ type: "mode", mode: "walk", controller: walkCtrl })}
            >
              🚶 行走
            </button>
          </div>
          <div className="mt-1.5 text-[10px] font-semibold text-slate-400">行走控制器</div>
          {([
            ["track", "軌跡追蹤（開環時序 — 對照組）"],
            ["raibert", "Raibert 閉環（觸地重置＋落腳法則）"],
            ["rl", "RL 學習策略（PPO 訓練）"],
          ] as [WalkController, string][]).map(([id, label]) => (
            <label key={id} className="flex items-center gap-1.5 text-[11px] text-slate-300">
              <input
                type="radio"
                name="walkctrl"
                checked={walkCtrl === id}
                onChange={() => {
                  setWalkCtrl(id);
                  send({ type: "mode", mode: "walk", controller: id });
                }}
              />
              {label}
            </label>
          ))}
          <label className="mt-1.5 flex items-center gap-1.5 text-[11px] text-slate-300">
            <input
              type="checkbox"
              checked={assist}
              onChange={(e) => {
                setAssist(e.target.checked);
                send({ type: "assist", on: e.target.checked });
              }}
            />
            🛡️ 外加平衡 assist（所有 controller）＋ track 起步 assist；皆為模擬護具
          </label>
        </div>

        <div className="rounded-lg border border-violet-500/30 bg-violet-500/10 p-2">
          <div className="flex items-center justify-between text-xs font-semibold text-violet-200">
            <span>正式動作任務 V1</span>
            <span>{frame?.motion_task?.active ? frame.motion_task.phase : frame?.last_task?.evaluation.status ?? "READY"}</span>
          </div>
          <div className="mt-1 text-[10px] leading-4 text-slate-400">
            stand → start → steady walk → stop<br />
            9.0 s｜0.7 m/s｜500 Hz｜assist OFF｜啟動時清除障礙物並重設
          </div>
          {frame?.motion_task?.active && (
            <div className="mt-1 h-1.5 overflow-hidden rounded bg-slate-800">
              <div
                className="h-full bg-violet-400"
                style={{ width: `${Math.min(100, 100 * (frame.motion_task.elapsed_s ?? 0) / (frame.motion_task.duration_s ?? 9))}%` }}
              />
            </div>
          )}
          <button
            className={`mt-2 w-full rounded py-1.5 text-xs font-bold ${frame?.motion_task?.active ? "bg-red-500/40 text-red-200" : "bg-violet-500/40 text-violet-100"}`}
            onClick={() => send(frame?.motion_task?.active
              ? { type: "task_cancel" }
              : { type: "task_start", task_id: "stand_start_walk_stop_v1" })}
          >
            {frame?.motion_task?.active ? "■ 取消正式任務" : "▶ 執行正式任務"}
          </button>
          {frame?.last_task && (
            <div className={`mt-1 rounded px-2 py-1 text-[10px] font-bold ${frame.last_task.evaluation.status === "PASS" ? "bg-emerald-500/20 text-emerald-300" : frame.last_task.evaluation.status === "FAIL" ? "bg-red-500/20 text-red-300" : "bg-amber-500/20 text-amber-300"}`}>
              RESULT {frame.last_task.evaluation.status}｜{frame.last_task.evaluation.criteria.filter((item) => item.passed).length}/{frame.last_task.evaluation.criteria.length} criteria
            </div>
          )}
        </div>

        <div className="rounded-lg bg-slate-800/50 p-2">
          <div className="mb-1 flex items-center justify-between text-xs font-semibold text-slate-300">
            時間控制
            <span className="text-[10px] font-normal text-slate-500">{speed.toFixed(2)}×</span>
          </div>
          <input
            type="range" min={0.05} max={1} step={0.05} value={speed} className="w-full"
            onChange={(e) => {
              const v = parseFloat(e.target.value);
              setSpeed(v);
              send({ type: "speed", value: v });
            }}
          />
          <div className="mt-1 flex gap-1">
            <button
              className="flex-1 rounded bg-slate-700 py-1 text-xs hover:bg-slate-600"
              onClick={() => {
                const p = !paused;
                setPaused(p);
                send({ type: "pause", on: p });
              }}
            >
              {paused ? "▶ 繼續" : "⏸ 暫停"}
            </button>
            <button
              className="flex-1 rounded bg-slate-700 py-1 text-xs hover:bg-slate-600"
              onClick={() => send({ type: "step", dt: 0.05 })}
              title="前進 0.05 秒"
            >
              ⏭ 單步 50ms
            </button>
            <button
              className="rounded bg-red-500/30 px-2 py-1 text-xs text-red-200 hover:bg-red-500/50"
              onClick={() => send({ type: "reset" })}
            >
              🔄
            </button>
          </div>
          <div className="mt-2 border-t border-slate-700 pt-2">
            <div className="mb-1 flex items-center justify-between text-[10px] font-semibold text-slate-400">
              <span>Dynamic Run Trace（500 Hz）</span>
              <span>{frame?.recording?.active ? `${frame.recording.elapsed_s?.toFixed(1) ?? "0.0"} s` : "READY"}</span>
            </div>
            <button
              className={`w-full rounded py-1 text-xs font-semibold ${frame?.recording?.active ? "bg-red-500/40 text-red-200" : "bg-cyan-500/30 text-cyan-200"}`}
              onClick={() => send(frame?.recording?.active
                ? { type: "record_stop" }
                : { type: "record_start", label: `live-${walkCtrl}`, max_duration_s: 30.0 })}
            >
              {frame?.recording?.active ? "■ 停止並保存 Trace" : "● 開始記錄 Trace"}
            </button>
            {(traceNotice || frame?.last_trace) && (
              <div className="mt-1 break-all text-[9px] leading-4 text-cyan-300">
                {traceNotice ?? `已完成：${frame?.last_trace?.run_id}`}<br />
                回到「分析模式 → 動態紀錄」查看完整輸出。
              </div>
            )}
          </div>
        </div>

        <div className="rounded-lg bg-slate-800/50 p-2">
          <div className="mb-1 flex items-center justify-between text-xs font-semibold text-slate-300">
            👊 外力推撞
            <span className="text-[10px] font-normal text-slate-500">{pushForce} N × 0.2s</span>
          </div>
          <input
            type="range" min={50} max={600} step={25} value={pushForce} className="w-full"
            onChange={(e) => setPushForce(parseInt(e.target.value))}
          />
          <div className="mx-auto mt-1 grid w-32 grid-cols-3 gap-1 text-sm">
            <button className="rounded bg-slate-700 py-1 hover:bg-red-500/50" onClick={() => push(1, 1)}>↘</button>
            <button className="rounded bg-slate-700 py-1 hover:bg-red-500/50" onClick={() => push(1, 0)} title="從後方推（機器人向前）">⬇︎推</button>
            <button className="rounded bg-slate-700 py-1 hover:bg-red-500/50" onClick={() => push(1, -1)}>↙</button>
            <button className="rounded bg-slate-700 py-1 hover:bg-red-500/50" onClick={() => push(0, 1)}>⬅ 左</button>
            <div />
            <button className="rounded bg-slate-700 py-1 hover:bg-red-500/50" onClick={() => push(0, -1)}>右 ➡</button>
            <button className="rounded bg-slate-700 py-1 hover:bg-red-500/50" onClick={() => push(-1, 1)}>↗</button>
            <button className="rounded bg-slate-700 py-1 hover:bg-red-500/50" onClick={() => push(-1, 0)} title="從前方推（機器人向後）">⬆︎推</button>
            <button className="rounded bg-slate-700 py-1 hover:bg-red-500/50" onClick={() => push(-1, -1)}>↖</button>
          </div>
        </div>

        <div className="rounded-lg bg-slate-800/50 p-2">
          <div className="mb-1 flex items-center justify-between text-xs font-semibold text-slate-300">
            🧱 臨時障礙物
            <span className="text-[10px] font-normal text-slate-500">高 {obsHeight.toFixed(2)} m</span>
          </div>
          <input
            type="range" min={0.05} max={0.4} step={0.05} value={obsHeight} className="w-full"
            onChange={(e) => setObsHeight(parseFloat(e.target.value))}
          />
          <button
            className="mt-1 w-full rounded bg-orange-500/40 py-1 text-xs text-orange-200 hover:bg-orange-500/60"
            onClick={() => send({ type: "obstacle", dist: 1.5, height: obsHeight, depth: 0.3 })}
          >
            在前方 1.5m 放置障礙物
          </button>
        </div>
      </aside>

      {/* 中：3D 視圖 */}
      <div className="relative min-w-0 flex-1">
        <div ref={mountRef} className="h-full w-full" />
        {liveError ? (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-950/70">
            <div className="max-w-md rounded-lg border border-red-500/50 bg-red-950/90 px-4 py-3 text-sm text-red-200">
              <div className="font-bold">ERROR {liveError.code}</div>
              <div className="mt-1 text-xs">{liveError.message}</div>
              <button
                className="mt-2 rounded bg-red-500/25 px-2 py-1 text-xs hover:bg-red-500/40"
                onClick={() => setLiveError(null)}
              >
                關閉訊息
              </button>
            </div>
          </div>
        ) : !connected && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-950/60">
            <div className="rounded-lg bg-slate-800 px-4 py-2 text-sm text-amber-300">
              連線中…（請確認後端已啟動）
            </div>
          </div>
        )}
        <div className="absolute bottom-2 left-2 rounded bg-slate-900/70 px-2 py-1 text-[10px] leading-4 text-slate-400">
          🟡 質心 ｜ 🟣 capture point ｜ 🟢 模擬接觸 CoP ｜ 🔵 接觸點 ｜ 紅箭頭：外力
        </div>
      </div>

      {/* 右：控制器狀態 + 決策日誌 */}
      <aside className="flex w-[300px] shrink-0 flex-col border-l border-slate-800 bg-slate-900/40">
        <div className="border-b border-slate-800 p-2">
          <div className="mb-1 text-xs font-semibold text-slate-300">控制器狀態</div>
          <div
            data-testid="intervention-status"
            className="mb-2 grid grid-cols-1 gap-1 rounded border border-amber-500/20 bg-amber-500/5 p-1.5 text-[9px] font-semibold tracking-wide"
          >
            <span className="text-amber-200">
              BALANCE ASSIST {frame?.interventions
                ? frame.interventions.balance_assist_enabled ? "ENABLED" : "DISABLED"
                : "LEGACY_UNKNOWN"}
            </span>
            <span className={frame?.interventions?.startup_assist_active ? "text-red-300" : "text-slate-400"}>
              STARTUP ASSIST {frame?.interventions
                ? frame.interventions.startup_assist_active ? "ACTIVE" : "INACTIVE"
                : "LEGACY_UNKNOWN"}
            </span>
            <span className={frame?.interventions?.external_push_active ? "text-red-300" : "text-slate-400"}>
              EXTERNAL PUSH {frame?.interventions
                ? frame.interventions.external_push_active ? "ACTIVE" : "INACTIVE"
                : "LEGACY_UNKNOWN"}
            </span>
          </div>
          {st && (
            <>
              <div className="mb-1 grid grid-cols-2 gap-1 text-[11px] text-slate-300">
                <div className="rounded bg-slate-800/60 px-1.5 py-1">
                  軀幹 pitch <span className={Math.abs(st.pitch_deg) > 20 ? "font-bold text-red-300" : "text-slate-100"}>{st.pitch_deg}°</span>
                </div>
                <div className="rounded bg-slate-800/60 px-1.5 py-1">
                  roll <span className={Math.abs(st.roll_deg) > 20 ? "font-bold text-red-300" : "text-slate-100"}>{st.roll_deg}°</span>
                </div>
                <div className="rounded bg-slate-800/60 px-1.5 py-1">
                  質心速度 <span className="text-slate-100">{st.com_vel[0].toFixed(2)}</span> m/s
                </div>
                <div className="rounded bg-slate-800/60 px-1.5 py-1">
                  GRF {st.grf.l.toFixed(0)}/{st.grf.r.toFixed(0)} N
                </div>
              </div>
              <div className="mb-1 text-[10px] font-semibold text-slate-400">平衡策略作用量</div>
              <CorrBar label="踝策略" value={st.ankle_corr} max={45} />
              <CorrBar label="髖策略" value={st.hip_corr} max={80} />
              <CorrBar label="側向髖" value={st.roll_corr} max={60} />
              <div className="mb-1 flex items-center gap-1 text-[10px]">
                <span className="w-16 shrink-0 text-slate-400">踏步調整</span>
                <span className="tabular-nums text-slate-300">
                  ({(st.step_offset[0] * 100).toFixed(0)}, {(st.step_offset[1] * 100).toFixed(0)}) cm
                </span>
              </div>
              <div className="mt-1 text-[10px] font-semibold text-slate-400">馬達出力（相對峰值）</div>
              <div className="grid grid-cols-3 gap-x-2 text-[10px]">
                {Object.entries(st.saturation).map(([g, pct]) => (
                  <div key={g} className="flex justify-between">
                    <span className="text-slate-500">{(GROUP_LABELS[g] ?? g).slice(0, 3)}</span>
                    <span className={pct > 95 ? "font-bold text-red-300" : "text-slate-300"}>{pct}%</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
        <div className="flex min-h-0 flex-1 flex-col p-2">
          <div className="mb-1 text-xs font-semibold text-slate-300">🧠 控制器決策日誌</div>
          <div ref={logRef} className="min-h-0 flex-1 overflow-y-auto rounded bg-slate-950/60 p-1.5">
            {(frame?.decisions ?? []).map((d, i) => (
              <div
                key={i}
                className={`mb-0.5 text-[10px] leading-4 ${
                  d.level === "fall" ? "text-red-300 font-semibold"
                  : d.level === "impact" ? "text-amber-300"
                  : d.level === "strategy" ? "text-sky-300"
                  : "text-slate-400"
                }`}
              >
                <span className="text-slate-600">[{d.t.toFixed(1)}s]</span> {d.text}
              </div>
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}
