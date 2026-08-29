import { useEffect, useRef } from "react";
import type { Playback } from "./playback";

export interface Series {
  label: string;
  color: string;
  data: (number | null)[];   // null = 該時刻無定義（如騰空期），畫線時斷開
}

// 輕量 canvas 折線圖：自動縮放、格線、圖例、播放游標、參考線
export default function LineChart({
  time,
  series,
  playback,
  height = 180,
  unit = "",
  refLines = [],
}: {
  time: number[];
  series: Series[];
  playback: Playback;
  height?: number;
  unit?: string;
  refLines?: { value: number; color: string; label: string }[];
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef({ time, series, unit, refLines });
  stateRef.current = { time, series, unit, refLines };

  useEffect(() => {
    const canvas = canvasRef.current!;
    const draw = (tPlay: number) => {
      const { time, series, unit, refLines } = stateRef.current;
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (w === 0 || h === 0) return;
      if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
        canvas.width = w * dpr;
        canvas.height = h * dpr;
      }
      const ctx = canvas.getContext("2d")!;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      if (time.length < 2 || series.length === 0) {
        ctx.fillStyle = "#5b6675";
        ctx.font = "12px sans-serif";
        ctx.fillText("無資料", w / 2 - 16, h / 2);
        return;
      }

      const padL = 46, padR = 8, padT = 8, padB = 18;
      const pw = w - padL - padR, ph = h - padT - padB;
      const t0 = time[0], t1 = time[time.length - 1];

      let vmin = Infinity, vmax = -Infinity;
      for (const s of series)
        for (const v of s.data) {
          if (v === null || !isFinite(v)) continue;
          if (v < vmin) vmin = v;
          if (v > vmax) vmax = v;
        }
      for (const r of refLines) {
        vmin = Math.min(vmin, r.value);
        vmax = Math.max(vmax, r.value);
      }
      if (!isFinite(vmin)) { vmin = 0; vmax = 1; }
      const range = vmax - vmin || 1;
      vmin -= range * 0.08;
      vmax += range * 0.08;

      const X = (t: number) => padL + ((t - t0) / (t1 - t0)) * pw;
      const Y = (v: number) => padT + (1 - (v - vmin) / (vmax - vmin)) * ph;

      // 格線與刻度
      ctx.strokeStyle = "#242b35";
      ctx.fillStyle = "#7a8595";
      ctx.font = "10px sans-serif";
      ctx.lineWidth = 1;
      const nTicks = 4;
      for (let i = 0; i <= nTicks; i++) {
        const v = vmin + ((vmax - vmin) * i) / nTicks;
        const y = Y(v);
        ctx.beginPath();
        ctx.moveTo(padL, y);
        ctx.lineTo(w - padR, y);
        ctx.stroke();
        ctx.fillText(v.toFixed(Math.abs(vmax) > 20 ? 0 : 1), 4, y + 3);
      }
      for (let ti = Math.ceil(t0); ti <= t1; ti++) {
        const x = X(ti);
        ctx.strokeStyle = "#1d232c";
        ctx.beginPath();
        ctx.moveTo(x, padT);
        ctx.lineTo(x, h - padB);
        ctx.stroke();
        ctx.fillText(`${ti}s`, x - 6, h - 5);
      }

      // 參考線（額定/峰值）
      for (const r of refLines) {
        const y = Y(r.value);
        ctx.strokeStyle = r.color;
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        ctx.moveTo(padL, y);
        ctx.lineTo(w - padR, y);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = r.color;
        ctx.fillText(r.label, w - padR - 60, y - 3);
      }

      // 資料線（null 斷開）
      for (const s of series) {
        ctx.strokeStyle = s.color;
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        let pen = false;
        for (let i = 0; i < time.length; i++) {
          const v = s.data[i];
          if (v === null || !isFinite(v)) {
            pen = false;
            continue;
          }
          const x = X(time[i]), y = Y(v);
          pen ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
          pen = true;
        }
        ctx.stroke();
      }

      // 播放游標 + 當前值
      const xp = X(Math.min(tPlay, t1));
      ctx.strokeStyle = "#e2e6ea88";
      ctx.beginPath();
      ctx.moveTo(xp, padT);
      ctx.lineTo(xp, h - padB);
      ctx.stroke();

      const fi = Math.min(
        Math.round(((tPlay - t0) / (t1 - t0)) * (time.length - 1)),
        time.length - 1
      );
      let ly = 12;
      for (const s of series) {
        ctx.fillStyle = s.color;
        const v = s.data[Math.max(fi, 0)];
        ctx.fillText(`${s.label}: ${v === null || v === undefined ? "—" : v.toFixed(1) + unit}`, padL + 6, padT + ly);
        ly += 12;
      }
    };

    draw(playback.t);
    const unsub = playback.subscribe(draw);
    return unsub;
  }, [playback]);

  return <canvas ref={canvasRef} style={{ width: "100%", height }} />;
}
