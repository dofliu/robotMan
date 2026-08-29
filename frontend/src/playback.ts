// 播放時脈：單一 rAF 迴圈驅動 3D 視圖與圖表游標，
// 避免以 React state 每秒 60 次重新渲染整個介面
export class Playback {
  t = 0;
  playing = true;
  speed = 1;
  duration = 0;
  private listeners = new Set<(t: number) => void>();
  private raf = 0;
  private last = 0;

  private interval = 0;

  start() {
    this.stop();
    this.last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min((now - this.last) / 1000, 0.25);
      this.last = now;
      if (this.playing && this.duration > 0) {
        this.t = (this.t + dt * this.speed) % this.duration;
      }
      this.listeners.forEach((fn) => fn(this.t));
    };
    const loop = (now: number) => {
      tick(now);
      this.raf = requestAnimationFrame(loop);
    };
    this.raf = requestAnimationFrame(loop);
    // 分頁隱藏時 rAF 不觸發，用 timer 後援維持更新（隱藏分頁會被降頻，可接受）
    this.interval = window.setInterval(() => {
      if (document.visibilityState === "hidden") tick(performance.now());
    }, 250);
  }

  stop() {
    cancelAnimationFrame(this.raf);
    clearInterval(this.interval);
  }

  seek(t: number) {
    this.t = Math.max(0, Math.min(t, this.duration));
  }

  subscribe(fn: (t: number) => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }
}
