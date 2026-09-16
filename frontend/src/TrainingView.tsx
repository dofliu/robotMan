import { useEffect, useMemo, useState } from "react";
import { fetchTrainingInventory } from "./api";
import type { TrainingInventory, TrainingProfile } from "./types";
import { Disclosure, Pill } from "./ui";

function compactNumber(value: number): string {
  return value >= 1_000_000 ? `${(value / 1_000_000).toFixed(0)}M` : value.toLocaleString();
}

// 25 個 profile 分成六個家族。分組只用 API 已回傳的欄位判斷，不靠 profile id 字串猜。
// compact 的家族成員只差 seed 或 arm，用一列一行的表格比 5 張幾乎相同的卡片清楚。
interface ProfileGroup {
  id: string;
  title: string;
  description: string;
  compact: boolean;
  defaultOpen?: boolean;
  match: (profile: TrainingProfile) => boolean;
}

const GROUPS: ProfileGroup[] = [
  {
    id: "development",
    title: "Motion task 開發版本（v1–v6）",
    description: "同一個 stand → start → steady walk → stop 任務，逐版更換觀測、獎勵與環境；每一版是獨立 profile，不覆寫前一版。",
    compact: false,
    defaultOpen: true,
    match: (p) => p.environment_id !== "fixed_walk_v1"
      && !p.pilot_protocol_id && !p.seedvar_protocol_id && !p.tracked_lineage_protocol_id,
  },
  {
    id: "pilot",
    title: "v7 pilot 三臂（凍結）",
    description: "三種 action interface（reward only／reduced joint envelope／filtered action），各 100k 步，由 v5 policy warm start；配置已凍結。",
    compact: true,
    match: (p) => Boolean(p.pilot_protocol_id),
  },
  {
    id: "seedvar",
    title: "v7 seed-variance replicates（凍結）",
    description: "同三臂、只換訓練 seed 的 replicate 配置，用來量訓練 seed 造成的變異。",
    compact: true,
    match: (p) => Boolean(p.seedvar_protocol_id),
  },
  {
    id: "tracked-v1",
    title: "Tracked lineage V1（凍結）",
    description: "在 v5 環境從零訓練 5 個 replicate，每個 checkpoint 進版控；沒有 warm start。",
    compact: true,
    match: (p) => p.tracked_lineage_protocol_id === "TRACKED-LINEAGE-TRAINING-V1",
  },
  {
    id: "tracked-v2",
    title: "Tracked lineage V2 續訓（凍結）",
    description: "由 V1 各 replicate 保留的 checkpoint 續訓，planned_timesteps 是再加的增量。",
    compact: true,
    match: (p) => p.tracked_lineage_protocol_id === "TRACKED-LINEAGE-TRAINING-V2",
  },
  {
    id: "fixed-walk",
    title: "固定速度行走（legacy）",
    description: "fixed_walk_v1：只有行走、沒有起停命令的舊環境；三個速度的 profile 狀態皆為未訓練。",
    compact: false,
    match: (p) => p.environment_id === "fixed_walk_v1",
  },
];

const OTHER_GROUP: ProfileGroup = {
  id: "other",
  title: "其他",
  description: "未落入上述任何家族的 profile。",
  compact: false,
  match: () => true,
};

const COMMON_PREFIX = "stand_start_walk_stop_0p7_";
function shortId(profileId: string): string {
  return profileId.startsWith(COMMON_PREFIX) ? profileId.slice(COMMON_PREFIX.length) : profileId;
}

function protocolOf(profile: TrainingProfile): string | null {
  return profile.tracked_lineage_protocol_id ?? profile.seedvar_protocol_id ?? profile.pilot_protocol_id ?? null;
}

function ProfileCard({ profile }: { profile: TrainingProfile }) {
  return (
    <article className="min-w-0 rounded-lg border border-slate-700 bg-slate-900/70 p-3">
      <div className="break-all text-xs font-bold text-slate-100">{profile.profile_id}</div>
      <div className="mt-0.5 break-all text-[11px] text-slate-500">{profile.environment_id}</div>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
        <dt className="text-slate-500">速度</dt><dd>{profile.speed_mps.toFixed(1)} m/s</dd>
        <dt className="text-slate-500">Steps</dt><dd>{compactNumber(profile.planned_timesteps)}</dd>
        <dt className="text-slate-500">平行環境</dt><dd>{profile.parallel_envs}</dd>
        <dt className="text-slate-500">Seed base</dt><dd>{profile.seed_base}</dd>
      </dl>
      {profile.warm_start_policy_id && (
        <div className="mt-1.5 break-all text-[11px] text-slate-400">
          warm start ← <span className="text-sky-300">{profile.warm_start_policy_id}</span>
        </div>
      )}
      <div className="mt-2 break-all text-[11px] font-semibold text-amber-300">{profile.status}</div>
    </article>
  );
}

function ProfileTable({ profiles }: { profiles: TrainingProfile[] }) {
  const showArm = profiles.some((p) => p.pilot_arm_id);
  const showWarmStart = profiles.some((p) => p.warm_start_policy_id);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[11px]">
        <thead className="text-slate-500">
          <tr>
            <th className="py-1 pr-3 font-normal">Profile</th>
            {showArm && <th className="py-1 pr-3 font-normal">Arm</th>}
            <th className="py-1 pr-3 font-normal">Seed base</th>
            <th className="py-1 pr-3 font-normal">Steps</th>
            <th className="py-1 pr-3 font-normal">環境</th>
            {showWarmStart && <th className="py-1 pr-3 font-normal">Warm start</th>}
            <th className="py-1 font-normal">Status</th>
          </tr>
        </thead>
        <tbody>
          {profiles.map((p) => (
            <tr key={p.profile_id} className="border-t border-slate-800">
              <td className="py-1.5 pr-3 font-semibold text-slate-200" title={p.profile_id}>{shortId(p.profile_id)}</td>
              {showArm && <td className="py-1.5 pr-3 text-slate-300">{p.pilot_arm_id ?? "—"}</td>}
              <td className="py-1.5 pr-3 tabular-nums text-slate-300">{p.seed_base}</td>
              <td className="py-1.5 pr-3 tabular-nums text-slate-300">{compactNumber(p.planned_timesteps)}</td>
              <td className="break-all py-1.5 pr-3 text-slate-400">{p.environment_id}</td>
              {showWarmStart && <td className="break-all py-1.5 pr-3 text-sky-300">{p.warm_start_policy_id ?? "—"}</td>}
              <td className="min-w-[200px] break-all py-1.5 font-semibold text-amber-300">{p.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function TrainingView() {
  const [inventory, setInventory] = useState<TrainingInventory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchTrainingInventory().then(setInventory).catch((reason) => setError(String(reason)));
  }, []);

  // 每個 profile 只進第一個符合的家族；順序即 GROUPS 的順序。
  const grouped = useMemo(() => {
    const buckets = new Map<string, TrainingProfile[]>();
    for (const profile of inventory?.profiles ?? []) {
      const group = GROUPS.find((g) => g.match(profile)) ?? OTHER_GROUP;
      buckets.set(group.id, [...(buckets.get(group.id) ?? []), profile]);
    }
    return [...GROUPS, OTHER_GROUP]
      .map((group) => ({ group, profiles: buckets.get(group.id) ?? [] }))
      .filter((entry) => entry.profiles.length > 0);
  }, [inventory]);

  const total = inventory?.profiles.length ?? 0;

  return (
    <div className="min-h-0 flex-1 overflow-y-auto bg-slate-950 p-4 text-slate-200">
      <div className="mx-auto max-w-6xl space-y-3">
        <section className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-fuchsia-500/30 bg-fuchsia-500/5 px-4 py-3">
          <div>
            <h2 className="text-base font-bold text-fuchsia-200">RL 訓練設定（離線）</h2>
            <p className="mt-0.5 text-xs text-slate-400">
              此頁只列出 versioned training profiles，不會啟動訓練；即時互動畫面只做推論，不會更新權重。
            </p>
          </div>
          <Pill tone="amber">NOT PHYSICALLY VALIDATED</Pill>
        </section>

        {error && <div className="rounded border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">{error}</div>}

        <section>
          <div className="mb-2 flex items-end justify-between gap-3">
            <h3 className="text-sm font-bold text-slate-100">
              Training profiles
              {inventory && <span className="ml-2 text-[11px] font-normal text-slate-500">{total} 個，分 {grouped.length} 個家族</span>}
            </h3>
            <span className="text-[11px] text-slate-500">
              {inventory?.schema_version ?? "LOADING"}
              {inventory ? `｜${inventory.execution_mode}` : ""}
            </span>
          </div>
          <div className="space-y-2">
            {grouped.map(({ group, profiles }) => {
              const protocol = protocolOf(profiles[0]);
              return (
                <Disclosure
                  key={group.id}
                  title={group.title}
                  defaultOpen={Boolean(group.defaultOpen)}
                  summary={
                    <span className="flex items-center gap-2">
                      {protocol && <span className="hidden font-mono text-slate-500 md:inline">{protocol}</span>}
                      <span>{profiles.length} 個 profile</span>
                    </span>
                  }
                >
                  <p className="mb-2 text-[11px] leading-4 text-slate-500">{group.description}</p>
                  {group.compact ? (
                    <ProfileTable profiles={profiles} />
                  ) : (
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                      {profiles.map((profile) => <ProfileCard key={profile.profile_id} profile={profile} />)}
                    </div>
                  )}
                </Disclosure>
              );
            })}
          </div>
        </section>

        <Disclosure title="訓練流程與目前狀態說明" summary="smoke gate → development training → evaluation / registry">
          <div className="grid gap-3 lg:grid-cols-3">
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
          </div>
          <p className="mt-3 text-xs leading-5 text-slate-400">
            `stand_start_walk_stop_0p7_v1` 已建立 48-D command-conditioned observation 與同一 9 秒 phase schedule。現有 `walk_0p7_legacy` 是 47-D walk-only policy，兩者不相容；必須完成新訓練、evaluation 與 controller adapter，不能直接覆寫舊模型。正式訓練是離線、versioned、不可覆寫的獨立 run；完成後仍需 evaluation 與人工登錄，才可成為可部署 policy。
          </p>
          <pre className="mt-2 overflow-x-auto rounded bg-slate-950 p-3 text-[11px] text-emerald-300">python backend/rl/train_ppo.py --profile stand_start_walk_stop_0p7_v1 --run-id start-stop-seed2700-run01</pre>
        </Disclosure>
      </div>
    </div>
  );
}
