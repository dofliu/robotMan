import type {
  Defaults, DynamicTraceDetail, DynamicTraceListItem, GaitParams, Obstacle,
  RobotConfig, SimResult,
  TrainingInventory,
} from "./types";

export async function fetchDefaults(): Promise<Defaults> {
  const r = await fetch("/api/defaults");
  if (!r.ok) throw new Error(`defaults 取得失敗: ${r.status}`);
  return r.json();
}

export async function simulate(
  robot: RobotConfig,
  gait: GaitParams,
  obstacles: Obstacle[],
  signal?: AbortSignal
): Promise<SimResult> {
  const r = await fetch("/api/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ robot, gait, obstacles }),
    signal,
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`模擬失敗 (${r.status}): ${text.slice(0, 300)}`);
  }
  return r.json();
}

export async function fetchTraceList(): Promise<DynamicTraceListItem[]> {
  const r = await fetch("/api/traces?limit=200");
  if (!r.ok) throw new Error(`trace list 取得失敗: ${r.status}`);
  const body = await r.json();
  return body.traces;
}

export async function fetchTrace(runId: string): Promise<DynamicTraceDetail> {
  const r = await fetch(`/api/traces/${encodeURIComponent(runId)}?max_points=2000`);
  if (!r.ok) throw new Error(`trace 取得失敗: ${r.status}`);
  return r.json();
}

export async function fetchTrainingInventory(): Promise<TrainingInventory> {
  const r = await fetch("/api/training/profiles");
  if (!r.ok) throw new Error(`training profiles 取得失敗: ${r.status}`);
  return r.json();
}
