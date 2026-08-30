import type { Bar } from "./types";

export interface LinePoint {
  time: string;
  value: number;
}

// --- moving averages -----------------------------------------------------

export function sma(bars: Bar[], n: number): LinePoint[] {
  const out: LinePoint[] = [];
  let sum = 0;
  for (let i = 0; i < bars.length; i++) {
    sum += bars[i].close;
    if (i >= n) sum -= bars[i - n].close;
    if (i >= n - 1) out.push({ time: bars[i].time, value: sum / n });
  }
  return out;
}

function emaSeries(values: number[], n: number): (number | null)[] {
  const k = 2 / (n + 1);
  const out: (number | null)[] = new Array(values.length).fill(null);
  let prev: number | null = null;
  for (let i = 0; i < values.length; i++) {
    if (i === n - 1) {
      prev = values.slice(0, n).reduce((a, b) => a + b, 0) / n;
      out[i] = prev;
    } else if (prev !== null) {
      prev = values[i] * k + prev * (1 - k);
      out[i] = prev;
    }
  }
  return out;
}

export function ema(bars: Bar[], n: number): LinePoint[] {
  const e = emaSeries(bars.map((b) => b.close), n);
  const out: LinePoint[] = [];
  for (let i = 0; i < bars.length; i++) if (e[i] !== null) out.push({ time: bars[i].time, value: e[i] as number });
  return out;
}

// --- MACD (12, 26, 9) ---------------------------------------------------

export function macd(bars: Bar[], fast = 12, slow = 26, signal = 9) {
  const close = bars.map((b) => b.close);
  const ef = emaSeries(close, fast);
  const es = emaSeries(close, slow);
  const macdLine: (number | null)[] = close.map((_, i) =>
    ef[i] !== null && es[i] !== null ? (ef[i] as number) - (es[i] as number) : null,
  );
  const firstIdx = macdLine.findIndex((v) => v !== null);
  const compact = macdLine.slice(firstIdx).map((v) => v as number);
  const sig = emaSeries(compact, signal);
  const line: LinePoint[] = [];
  const signalLine: LinePoint[] = [];
  const hist: (LinePoint & { color: string })[] = [];
  for (let i = 0; i < compact.length; i++) {
    const time = bars[firstIdx + i].time;
    line.push({ time, value: compact[i] });
    if (sig[i] !== null) {
      signalLine.push({ time, value: sig[i] as number });
      const h = compact[i] - (sig[i] as number);
      hist.push({ time, value: h, color: h >= 0 ? "#1f9d5588" : "#d6454588" });
    }
  }
  return { line, signalLine, hist };
}

// --- RSI (Wilder, 14) -------------------------------------------------

export function rsi(bars: Bar[], n = 14): LinePoint[] {
  const out: LinePoint[] = [];
  let gain = 0;
  let loss = 0;
  for (let i = 1; i < bars.length; i++) {
    const ch = bars[i].close - bars[i - 1].close;
    const g = Math.max(ch, 0);
    const l = Math.max(-ch, 0);
    if (i <= n) {
      gain += g;
      loss += l;
      if (i === n) {
        gain /= n;
        loss /= n;
        out.push({ time: bars[i].time, value: 100 - 100 / (1 + gain / (loss || 1e-9)) });
      }
    } else {
      gain = (gain * (n - 1) + g) / n;
      loss = (loss * (n - 1) + l) / n;
      out.push({ time: bars[i].time, value: 100 - 100 / (1 + gain / (loss || 1e-9)) });
    }
  }
  return out;
}

// --- KDJ (9, 3, 3) ----------------------------------------------------

export function kdj(bars: Bar[], n = 9, kSmooth = 3, dSmooth = 3) {
  const k: LinePoint[] = [];
  const d: LinePoint[] = [];
  const j: LinePoint[] = [];
  let kv = 50;
  let dv = 50;
  for (let i = 0; i < bars.length; i++) {
    if (i < n - 1) continue;
    const win = bars.slice(i - n + 1, i + 1);
    const hh = Math.max(...win.map((b) => b.high));
    const ll = Math.min(...win.map((b) => b.low));
    const rsv = hh === ll ? 50 : ((bars[i].close - ll) / (hh - ll)) * 100;
    kv = (kv * (kSmooth - 1) + rsv) / kSmooth;
    dv = (dv * (dSmooth - 1) + kv) / dSmooth;
    k.push({ time: bars[i].time, value: kv });
    d.push({ time: bars[i].time, value: dv });
    j.push({ time: bars[i].time, value: 3 * kv - 2 * dv });
  }
  return { k, d, j };
}

// --- resample daily -> weekly / monthly -------------------------------

export function resample(bars: Bar[], tf: "D" | "W" | "M"): Bar[] {
  if (tf === "D" || bars.length === 0) return bars;
  const key = (t: string) => {
    const dt = new Date(t + "T00:00:00Z");
    if (tf === "M") return `${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, "0")}`;
    // ISO week bucket
    const d = new Date(dt);
    d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
    return d.toISOString().slice(0, 10);
  };
  const out: Bar[] = [];
  let cur: Bar | null = null;
  let curKey = "";
  for (const b of bars) {
    const k = key(b.time);
    if (k !== curKey) {
      if (cur) out.push(cur);
      cur = { ...b };
      curKey = k;
    } else if (cur) {
      cur.high = Math.max(cur.high, b.high);
      cur.low = Math.min(cur.low, b.low);
      cur.close = b.close;
      cur.volume += b.volume;
      cur.time = b.time; // last session's date in the bucket
    }
  }
  if (cur) out.push(cur);
  return out;
}
