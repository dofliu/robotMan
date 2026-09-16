import { useEffect, useRef } from "react";
import type { Playback } from "./playback";

export interface Series {
  label: string;
  color: string;
  data: (number | null)[];   // null = 該時刻無定義（如騰空期），畫線時斷開
}
// 垂直時間標記（跌倒、任務階段起點）
export interface ChartMarker {
  t: number;
  label: string;
  color: string;
}
// 圖頂的狀態色帶（站立／行走／停止中／跌倒）
export interface ChartBand {
  t0: number;
  t1: number;
  color: string;
  label: string;
}

const INK = "#e2e6ea";
const INK_MUTED = "#94a3b8";
const GRID = "#242b35";
const GRID_TIME = "#1d232c";

// 輕量 canvas 折線圖：單一 y 軸、細線、hover 十字線與同時刻讀數、播放游標、
// 參考線（門檻，虛線）、垂直標記與狀態色帶。文字一律用墨色，顏色只給資料線與線頭。
export default function LineChart({
  time,
  series,
  playback,
  height = 180,
  unit = "",
  refLines = [],
  markers = [],
  bands = [],
  seekOnClick = true,
}: {
  time: number[];
  series: Series[];
  playback: Playback;
  height?: number;
  unit?: string;
  refLines?: { value: number; color: string; label: string }[];
  markers?: ChartMarker[];
  bands?: ChartBand[];
  seekOnClick?: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef({ time, series, unit, refLines, markers, bands });
  stateRef.current = { time, series, unit, refLines, markers, bands };
  const hoverRef = useRef<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current!;
    const geometry = () => {
      const { bands } = stateRef.current;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      const padL = 46, padR = 8, padT = bands.length ? 20 : 8, padB = 18;
      return { w, h, padL, padR, padT, padB, pw: w - padL - padR, ph: h - padT - padB };
    };

    const draw = (tPlay: number) => {
      const { time, series, unit, refLines, markers, bands } = stateRef.current;
      const dpr = window.devicePixelRatio || 1;
      const { w, h, padL, padR, padT, padB, pw, ph } = geometry();
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
      // 有門檻線時多留頭部空間，讓門檻標籤不壓到左上角的讀數
      vmax += range * (refLines.length ? 0.22 : 0.08);
      const decimals = vmax - vmin < 5 ? 2 : 1;

      const X = (t: number) => padL + ((t - t0) / (t1 - t0)) * pw;
      const Y = (v: number) => padT + (1 - (v - vmin) / (vmax - vmin)) * ph;

      // 格線與刻度：實線細線，一階離面色
      ctx.lineWidth = 1;
      ctx.font = "10px sans-serif";
      const nTicks = 4;
      for (let i = 0; i <= nTicks; i++) {
        const v = vmin + ((vmax - vmin) * i) / nTicks;
        const y = Y(v);
        ctx.strokeStyle = GRID;
        ctx.beginPath();
        ctx.moveTo(padL, y);
        ctx.lineTo(w - padR, y);
        ctx.stroke();
        ctx.fillStyle = INK_MUTED;
        ctx.fillText(v.toFixed(Math.abs(vmax) > 20 ? 0 : 1), 4, y + 3);
      }
      for (let ti = Math.ceil(t0); ti <= t1; ti++) {
        const x = X(ti);
        ctx.strokeStyle = GRID_TIME;
        ctx.beginPath();
        ctx.moveTo(x, padT);
        ctx.lineTo(x, h - padB);
        ctx.stroke();
        ctx.fillStyle = INK_MUTED;
        ctx.fillText(`${ti}s`, x - 6, h - 5);
      }

      // 狀態色帶：圖頂 6px，相鄰段之間留 1px 面色間隙
      for (const band of bands) {
        const x0 = X(Math.max(band.t0, t0));
        const x1 = X(Math.min(band.t1, t1));
        if (x1 - x0 <= 0) continue;
        ctx.fillStyle = band.color;
        ctx.fillRect(x0, 4, Math.max(x1 - x0 - 1, 0.5), 6);
      }

      // 參考線（門檻）：虛線，讓它讀成「門檻」而不是格線
      for (const r of refLines) {
        const y = Y(r.value);
        ctx.strokeStyle = r.color;
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        ctx.moveTo(padL, y);
        ctx.lineTo(w - padR, y);
        ctx.stroke();
        ctx.setLineDash([]);
        if (r.label) {
          ctx.fillStyle = INK_MUTED;
          ctx.fillText(r.label, w - padR - 6 - ctx.measureText(r.label).width, y - 3);
        }
      }

      // 垂直標記
      for (const m of markers) {
        if (m.t < t0 || m.t > t1) continue;
        const x = X(m.t);
        ctx.strokeStyle = m.color;
        ctx.beginPath();
        ctx.moveTo(x, padT);
        ctx.lineTo(x, h - padB);
        ctx.stroke();
        ctx.fillStyle = m.color;
        ctx.fillRect(x - 2, padT, 4, 4);
        ctx.fillStyle = INK_MUTED;
        ctx.fillText(m.label, x + 4, padT + 9);
      }

      // 資料線：2px、圓角接合，null 斷開
      ctx.lineWidth = 2;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      for (const s of series) {
        ctx.strokeStyle = s.color;
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
      ctx.lineWidth = 1;

      // 游標：hover 時跟隨指標，否則跟播放時間
      const tCursor = hoverRef.current ?? Math.min(tPlay, t1);
      const xp = X(Math.min(Math.max(tCursor, t0), t1));
      ctx.strokeStyle = hoverRef.current !== null ? "#e2e6eacc" : "#e2e6ea66";
      ctx.beginPath();
      ctx.moveTo(xp, padT);
      ctx.lineTo(xp, h - padB);
      ctx.stroke();

      // 同時刻讀數：線頭帶顏色，數值主、標籤次，文字一律墨色
      const fi = Math.min(
        Math.max(Math.round(((tCursor - t0) / (t1 - t0)) * (time.length - 1)), 0),
        time.length - 1,
      );
      let ly = padT + 12;
      ctx.font = "10px sans-serif";
      ctx.fillStyle = INK_MUTED;
      ctx.fillText(`t = ${time[fi].toFixed(2)} s`, padL + 6, ly);
      ly += 13;
      ctx.font = "11px sans-serif";
      for (const s of series) {
        const v = s.data[fi];
        const valueText = v === null || v === undefined || !isFinite(v) ? "—" : `${v.toFixed(decimals)}${unit}`;
        ctx.strokeStyle = s.color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(padL + 6, ly - 4);
        ctx.lineTo(padL + 18, ly - 4);
        ctx.stroke();
        ctx.lineWidth = 1;
        ctx.fillStyle = INK;
        ctx.font = "bold 11px sans-serif";
        ctx.fillText(valueText, padL + 24, ly);
        const valueWidth = ctx.measureText(valueText).width;
        ctx.fillStyle = INK_MUTED;
        ctx.font = "11px sans-serif";
        ctx.fillText(s.label, padL + 24 + valueWidth + 6, ly);
        ly += 14;
      }
    };

    const timeAt = (clientX: number): number | null => {
      const { time } = stateRef.current;
      if (time.length < 2) return null;
      const rect = canvas.getBoundingClientRect();
      const { padL, pw } = geometry();
      const frac = (clientX - rect.left - padL) / pw;
      if (frac < 0 || frac > 1) return null;
      return time[0] + frac * (time[time.length - 1] - time[0]);
    };
    const onMove = (event: PointerEvent) => {
      hoverRef.current = timeAt(event.clientX);
      draw(playback.t);
    };
    const onLeave = () => {
      hoverRef.current = null;
      draw(playback.t);
    };
    const onClick = (event: MouseEvent) => {
      if (!seekOnClick) return;
      const t = timeAt(event.clientX);
      if (t === null) return;
      playback.seek(t - stateRef.current.time[0]);
      playback.playing = false;
      draw(playback.t);
    };
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerleave", onLeave);
    canvas.addEventListener("click", onClick);

    draw(playback.t);
    const unsub = playback.subscribe(draw);
    return () => {
      unsub();
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerleave", onLeave);
      canvas.removeEventListener("click", onClick);
    };
  }, [playback, seekOnClick]);

  return <canvas ref={canvasRef} style={{ width: "100%", height, cursor: "crosshair", display: "block" }} />;
}
