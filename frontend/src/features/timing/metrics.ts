// Client-side recompute of the trade + equity-curve metrics for a
// long-only / short-only *view* on the Timing page. Mirrors the backend
// `signals/metrics.py`. The isolated-side view is an approximation — it is
// that side's own contribution, not a fresh engine run.

import type { DailyPoint, Trade } from "./types";

const TD = 252;

export function compound(rets: number[]): number[] {
  let eq = 1;
  return rets.map((r) => (eq *= 1 + r));
}

export function drawdownCurve(equity: number[]): number[] {
  let peak = -Infinity;
  return equity.map((e) => {
    peak = Math.max(peak, e);
    return peak > 0 ? e / peak - 1 : 0;
  });
}

const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

function pstd(xs: number[]): number | null {
  if (xs.length < 2) return null;
  const m = xs.reduce((a, b) => a + b, 0) / xs.length;
  return Math.sqrt(xs.reduce((a, b) => a + (b - m) ** 2, 0) / xs.length);
}

function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const n = s.length;
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
}

function maxConsec(flags: boolean[]): number {
  let best = 0;
  let cur = 0;
  for (const f of flags) {
    cur = f ? cur + 1 : 0;
    best = Math.max(best, cur);
  }
  return best;
}

function maxDdDays(dd: number[]): number {
  let best = 0;
  let cur = 0;
  for (const d of dd) {
    cur = d < 0 ? cur + 1 : 0;
    best = Math.max(best, cur);
  }
  return best;
}

export function curveStats(rets: number[]): Record<string, number | null> {
  if (rets.length < 2) {
    return {
      total_return: null, cagr: null, vol_annual: null, sharpe: null,
      sortino: null, max_drawdown: null, max_dd_days: null, calmar: null,
    };
  }
  const equity = compound(rets);
  const last = equity[equity.length - 1];
  const years = rets.length / TD;
  const cagr = last > 0 && years > 0 ? last ** (1 / years) - 1 : null;
  const m = mean(rets) as number;
  const s = pstd(rets);
  const downside = rets.filter((r) => r < 0);
  const dstd = downside.length >= 2 ? pstd(downside) : null;
  const dd = drawdownCurve(equity);
  const maxDd = Math.min(...dd);
  return {
    total_return: last - 1,
    cagr,
    vol_annual: s ? s * Math.sqrt(TD) : null,
    sharpe: s ? (m / s) * Math.sqrt(TD) : null,
    sortino: dstd ? (m / dstd) * Math.sqrt(TD) : null,
    max_drawdown: maxDd,
    max_dd_days: maxDdDays(dd),
    calmar: cagr != null && maxDd < 0 ? cagr / Math.abs(maxDd) : null,
  };
}

export function summariseView(trades: Trade[], daily: DailyPoint[]) {
  const closed = trades.filter((t) => t.exit_date != null);
  const open = trades.find((t) => t.exit_date == null);
  const rp = closed.map((t) => t.return_pct as number);
  const rr = closed.map((t) => t.return_r).filter((x): x is number => x != null);
  const wins = rp.filter((x) => x > 0);
  const losses = rp.filter((x) => x <= 0);
  const avgWin = mean(wins);
  const avgLoss = mean(losses);
  const grossWin = wins.reduce((a, b) => a + b, 0);
  const grossLoss = Math.abs(losses.reduce((a, b) => a + b, 0));
  const rrStd = pstd(rr);

  return {
    trade_stats: {
      trades: closed.length,
      wins: wins.length,
      losses: losses.length,
      open_position: open ? open.direction : null,
      win_rate: closed.length ? wins.length / closed.length : null,
      avg_win_pct: avgWin,
      avg_loss_pct: avgLoss,
      payoff_ratio: avgWin && avgLoss ? avgWin / Math.abs(avgLoss) : null,
      expectancy_pct: mean(rp),
      expectancy_r: mean(rr),
      profit_factor: grossLoss > 0 ? grossWin / grossLoss : null,
      sqn: rrStd ? (Math.sqrt(rr.length) * (mean(rr) as number)) / rrStd : null,
      avg_bars_held: mean(closed.map((t) => t.bars_held as number)),
      median_bars_held: median(closed.map((t) => t.bars_held as number)),
      max_consec_losses: maxConsec(rp.map((x) => x <= 0)),
      avg_mae_atr: mean(closed.map((t) => t.mae_atr).filter((x): x is number => x != null)),
      avg_mfe_atr: mean(closed.map((t) => t.mfe_atr).filter((x): x is number => x != null)),
      exposure: daily.length ? daily.filter((d) => d.state !== 0).length / daily.length : null,
    } as Record<string, number | string | null>,
    strategy: curveStats(daily.map((d) => d.strat_ret)),
  };
}
