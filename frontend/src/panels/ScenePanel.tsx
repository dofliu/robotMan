import type { Obstacle } from "../types";
import { Num } from "../ui";

export default function ScenePanel({
  obstacles,
  onChange,
}: {
  obstacles: Obstacle[];
  onChange: (o: Obstacle[]) => void;
}) {
  const update = (i: number, patch: Partial<Obstacle>) => {
    const next = obstacles.slice();
    next[i] = { ...next[i], ...patch };
    onChange(next);
  };
  return (
    <div>
      <p className="mb-2 text-[11px] leading-4 text-slate-500">
        頭部射線感測（LiDAR 示意）偵測到路徑上的障礙時，會自動提高抬腳並避開落點；被偵測到的障礙物亮紅。
      </p>
      {obstacles.length === 0 && (
        <div className="mb-2 rounded bg-slate-800/40 px-2 py-2 text-[11px] text-slate-500">目前沒有障礙物。</div>
      )}
      {obstacles.map((ob, i) => (
        <div key={i} className="mb-2 rounded-lg bg-slate-800/50 p-2">
          <div className="mb-1 flex items-center justify-between text-xs font-semibold text-slate-200">
            障礙物 {i + 1}
            <button
              type="button"
              className="rounded bg-red-500/20 px-2 py-0.5 text-[11px] text-red-300 hover:bg-red-500/40"
              onClick={() => onChange(obstacles.filter((_, j) => j !== i))}
            >
              移除
            </button>
          </div>
          <Num label="距離起點" value={ob.x} onChange={(v) => update(i, { x: v })} min={1} max={15} step={0.5} unit="m" />
          <Num label="高度" value={ob.height} onChange={(v) => update(i, { height: v })} min={0.05} max={0.5} step={0.01} unit="m" />
          <Num label="深度" value={ob.depth} onChange={(v) => update(i, { depth: v })} min={0.1} max={1} step={0.05} unit="m" />
        </div>
      ))}
      <button
        type="button"
        className="w-full rounded bg-slate-700 py-1 text-xs text-slate-200 hover:bg-slate-600"
        onClick={() =>
          onChange([
            ...obstacles,
            { x: 3 + obstacles.length * 2, depth: 0.3, height: 0.15, width: 1.2 },
          ])
        }
      >
        ＋ 新增障礙物
      </button>
    </div>
  );
}
