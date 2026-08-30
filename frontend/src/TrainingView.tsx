import { useEffect, useState } from "react";
import { fetchTrainingInventory } from "./api";
import type { TrainingInventory } from "./types";

function compactNumber(value: number): string {
  return value >= 1_000_000 ? `${(value / 1_000_000).toFixed(0)}M` : value.toLocaleString();
}

export default function TrainingView() {
  const [inventory, setInventory] = useState<TrainingInventory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchTrainingInventory().then(setInventory).catch((reason) => setError(String(reason)));
  }, []);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto bg-slate-950 p-4 text-slate-200">
      <div className="mx-auto max-w-6xl space-y-4">
        <section className="rounded-xl border border-fuchsia-500/30 bg-fuchsia-500/5 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold text-fuchsia-200">RL Training Lab</h2>
              <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">
                即時互動畫面只做 deterministic inference，不會邊走邊更新 weights。正式訓練是離線、versioned、不可覆寫的獨立 run；完成後仍需 evaluation 與人工登錄，才可成為可部署 policy。
              </p>
            </div>
            <div className="rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs font-bold text-amber-300">
              NOT PHYSICALLY VALIDATED
            </div>
          </div>
        </section>

        {error && <div className="rounded border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">{error}</div>}

        <section>
          <div className="mb-2 flex items-end justify-between">
            <div>
              <h3 className="text-sm font-bold text-slate-100">可重現 Training Profiles</h3>
              <p className="text-xs text-slate-500">{inventory?.schema_version ?? "LOADING"}｜讀取本頁不會啟動訓練</p>
            </div>
            <span className="text-[10px] font-semibold tracking-wide text-slate-500">{inventory?.execution_mode ?? "—"}</span>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {inventory?.profiles.map((profile) => {
              const taskProfile = profile.environment_id === "motion_task_command_v1";
              return (
                <article key={profile.profile_id} className={`rounded-lg border p-3 ${taskProfile ? "border-violet-500/40 bg-violet-500/10" : "border-slate-700 bg-slate-900/70"}`}>
                  <div className="text-xs font-bold text-slate-100">{profile.profile_id}</div>
                  <div className={`mt-1 text-[10px] font-bold ${taskProfile ? "text-violet-300" : "text-sky-300"}`}>
                    {taskProfile ? "COMMAND-CONDITIONED MOTION TASK" : "FIXED-SPEED WALK"}
                  </div>
                  <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
                    <dt className="text-slate-500">Speed</dt><dd>{profile.speed_mps.toFixed(1)} m/s</dd>
                    <dt className="text-slate-500">Steps</dt><dd>{compactNumber(profile.planned_timesteps)}</dd>
                    <dt className="text-slate-500">Parallel envs</dt><dd>{profile.parallel_envs}</dd>
                    <dt className="text-slate-500">Seed base</dt><dd>{profile.seed_base}</dd>
                  </dl>
                  {profile.task_id && <div className="mt-2 break-all rounded bg-slate-950/60 px-2 py-1 text-[10px] text-violet-200">{profile.task_id}</div>}
                  <div className="mt-2 text-[10px] font-semibold text-amber-300">{profile.status}</div>
                </article>
              );
            })}
          </div>
        </section>

        <section className="grid gap-3 lg:grid-cols-3">
          {[
            ["1. Smoke gate", "先以 256 steps 驗證 observation、environment、artifact 與 manifest pipeline；不能視為學習成果。"],
            ["2. Development training", "以新 run ID 執行完整 timesteps；每次產出獨立 policy.zip、checkpoint 與 hash manifest。"],
            ["3. Evaluation / registry", "multi-seed、failure retention 與同一 Motion Task criteria 通過後，才建立新的 policy registry record。"],
          ].map(([title, body]) => (
            <div key={title} className="rounded-lg border border-slate-700 bg-slate-900/60 p-3">
              <div className="text-sm font-bold text-slate-200">{title}</div>
              <p className="mt-1 text-xs leading-5 text-slate-400">{body}</p>
            </div>
          ))}
        </section>

        <section className="rounded-lg border border-slate-700 bg-slate-900/60 p-4">
          <h3 className="text-sm font-bold text-slate-100">目前 start/stop training 狀態</h3>
          <p className="mt-2 text-xs leading-5 text-slate-400">
            `stand_start_walk_stop_0p7_v1` 已建立 48-D command-conditioned observation 與同一 9 秒 phase schedule。現有 `walk_0p7_legacy` 是 47-D walk-only policy，兩者不相容；必須完成新訓練、evaluation 與 controller adapter，不能直接覆寫舊模型。
          </p>
          <pre className="mt-3 overflow-x-auto rounded bg-slate-950 p-3 text-[11px] text-emerald-300">python backend/rl/train_ppo.py --profile stand_start_walk_stop_0p7_v1 --run-id start-stop-seed2700-run01</pre>
        </section>
      </div>
    </div>
  );
}
