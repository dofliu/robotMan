import { useEffect, useRef, useState } from "react";
import type { Playback } from "./playback";

// 播放列：播放／暫停、時間軸拖曳、倍速。分析頁與 Dynamic Trace 頁共用。
export default function PlaybackBar({ playback }: { playback: Playback }) {
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
        type="button"
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
