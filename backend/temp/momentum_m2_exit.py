"""Cross-sectional momentum — Stage M2 (exit architecture).

Disposable research. Opens SQLite read-only, never writes app tables. Outputs
under docs/temp are disposable. See docs/temp/XSEC_MOMENTUM_RESEARCH_HANDOFF.md.

M1 is frozen for this stage:  composite score, N=20, monthly rebalance, skip=0.
M2 asks: does a hysteresis band beat plain rank-only turnover, and do the
"decorated" intra-month exits (trend gate / exhaustion / ATR trail) add
anything or just cut winners early?

    E0  rank-only      positions change only at the monthly rebalance; hold = top-20.
    E1  hysteresis     incumbents kept while rank <= 1.5*N (30); refill to 20 with new leaders.
    E2  E1 + trend     daily: a held name closing below its SMA_100 is exited at once (-> cash till rebalance).
    E3  E1 + exhaust   daily: a held name whose own trailing 21-session return turns negative is exited.
    E4  E1 + ATR trail daily: per-position Chandelier stop = max(adj_close since entry) - k*ATR20 (k=3).

Freed weight from an intra-month exit sits in cash (0 return) until the next
monthly rebalance refills the slot -- the honest cost of a defensive exit.

    backend/.venv/bin/python backend/temp/momentum_m2_exit.py
    backend/.venv/bin/python backend/temp/momentum_m2_exit.py --cost-mult 2
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TEMP_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEMP_DIR.parent.parent

ANN = 252.0
MIN_HISTORY = 252
N_BASKET = 20
HYST_MULT = 1.5           # incumbents kept while rank <= HYST_MULT * N_BASKET
CHANDELIER_K = 3.0
ATR_LEN = 20
SMA_TREND = 100
EXH_LOOKBACK = 21

PERIODS = [
    ("2016-2019", "2016-01-01", "2019-12-31"),
    ("2020-2022", "2020-01-01", "2022-12-31"),
    ("2023-present", "2023-01-01", "9999-12-31"),
]
VARIANTS = ["E0", "E1", "E2", "E3", "E4"]

WEIGHTS = {"rs_3m": .25, "rs_6m": .25, "rs_12m": .15, "high_52w_distance": .15,
           "trend_distance": .10, "slope": .10}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", type=Path, default=REPO_ROOT / "database" / "trade_helper.sqlite3")
    p.add_argument("--output-dir", type=Path, default=REPO_ROOT / "docs" / "temp")
    p.add_argument("--cost-bps", type=float, default=5.0, help="per-side cost, bps of turnover")
    p.add_argument("--cost-mult", type=float, default=1.0)
    return p.parse_args()


def read_only(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# --- data ------------------------------------------------------------------


@dataclass
class Series:
    close: list[float | None]
    high: list[float | None]
    low: list[float | None]
    sma100: list[float | None] = field(default_factory=list)
    atr20: list[float | None] = field(default_factory=list)


def load_aligned(conn: sqlite3.Connection) -> tuple[list[str], list[float], dict[str, Series]]:
    spy = conn.execute(
        "SELECT date, adj_close FROM price_bars WHERE symbol='SPY' AND adj_close IS NOT NULL ORDER BY date"
    ).fetchall()
    dates = [r["date"] for r in spy]
    spy_close = [float(r["adj_close"]) for r in spy]
    idx_of = {d: i for i, d in enumerate(dates)}
    n = len(dates)

    symbols = [r["symbol"] for r in conn.execute("SELECT symbol FROM assets WHERE active=1 ORDER BY symbol")]
    ph = ",".join("?" for _ in symbols)
    px: dict[str, Series] = {s: Series([None] * n, [None] * n, [None] * n) for s in symbols}
    for r in conn.execute(
        f"SELECT symbol, date, adj_close, adj_high, adj_low FROM price_bars "
        f"WHERE symbol IN ({ph}) AND adj_close IS NOT NULL AND date >= ? ORDER BY symbol, date",
        (*symbols, dates[0]),
    ):
        i = idx_of.get(r["date"])
        if i is None:
            continue
        s = px[r["symbol"]]
        s.close[i] = float(r["adj_close"])
        s.high[i] = float(r["adj_high"]) if r["adj_high"] is not None else float(r["adj_close"])
        s.low[i] = float(r["adj_low"]) if r["adj_low"] is not None else float(r["adj_close"])
    for s in px.values():
        s.sma100 = _rolling_mean(s.close, SMA_TREND)
        s.atr20 = _wilder_atr(s.high, s.low, s.close, ATR_LEN)
    return dates, spy_close, px


def _rolling_mean(series: list[float | None], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(series)
    win: list[float] = []
    for i, v in enumerate(series):
        if v is None:
            win.clear()
            continue
        win.append(v)
        if len(win) > n:
            win.pop(0)
        if len(win) == n:
            out[i] = sum(win) / n
    return out


def _wilder_atr(high, low, close, n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(close)
    trs: list[float] = []
    atr: float | None = None
    prev_close: float | None = None
    for i in range(len(close)):
        h, l, c = high[i], low[i], close[i]
        if c is None:
            trs.clear(); atr = None; prev_close = None
            continue
        if prev_close is None:
            tr = (h - l) if (h is not None and l is not None) else 0.0
        else:
            tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        prev_close = c
        if atr is None:
            trs.append(tr)
            if len(trs) == n:
                atr = sum(trs) / n
                out[i] = atr
        else:
            atr = (atr * (n - 1) + tr) / n
            out[i] = atr
    return out


# --- composite score as of a date index ---------------------------------


def _ret(series: list[float | None], i: int, n: int) -> float | None:
    if i - n < 0:
        return None
    a, b = series[i - n], series[i]
    return (b / a - 1.0) if a and b else None


def _sma_at(series: list[float | None], i: int, n: int) -> float | None:
    if i - n + 1 < 0:
        return None
    win = [v for v in series[i - n + 1:i + 1] if v]
    return sum(win) / len(win) if len(win) == n else None


def score_components(series: list[float | None], spy: list[float], i: int) -> dict[str, float] | None:
    price = series[i]
    if price is None:
        return None
    out: dict[str, float] = {}
    for label, n in (("rs_3m", 63), ("rs_6m", 126), ("rs_12m", 252)):
        rs = _ret(series, i, n)
        sp = spy[i] / spy[i - n] - 1.0 if i - n >= 0 else None
        if rs is not None and sp is not None:
            out[label] = rs - sp
    window = [v for v in series[i - 251:i + 1] if v]
    if len(window) >= 200:
        out["high_52w_distance"] = price / max(window) - 1.0
    tds = [math.log(price / s) for n in (20, 50, 100, 200) if (s := _sma_at(series, i, n))]
    if tds:
        out["trend_distance"] = statistics.fmean(tds)
    sl = []
    for n in (50, 200):
        a, b = _sma_at(series, i - 20, n), _sma_at(series, i, n)
        if a and b:
            sl.append(b / a - 1.0)
    if sl:
        out["slope"] = statistics.fmean(sl)
    return out or None


def rank_universe(comps: dict[str, dict[str, float]]) -> dict[str, float]:
    pct: dict[str, dict[str, float]] = {k: {} for k in WEIGHTS}
    for key in WEIGHTS:
        vals = sorted((c[key], s) for s, c in comps.items() if key in c)
        m = len(vals)
        for rank, (_, s) in enumerate(vals):
            pct[key][s] = 100.0 * rank / (m - 1) if m > 1 else 50.0
    out: dict[str, float] = {}
    for s in comps:
        num = sum(WEIGHTS[k] * pct[k][s] for k in WEIGHTS if s in pct[k])
        den = sum(WEIGHTS[k] for k in WEIGHTS if s in pct[k])
        if den > 0:
            out[s] = num / den
    return out


def rebalance_indices(dates: list[str], start: int) -> list[int]:
    out = [start]
    for i in range(start + 1, len(dates)):
        if dates[i][:7] != dates[i - 1][:7]:
            out.append(i)
    return out


# --- simulation --------------------------------------------------------


@dataclass
class Pos:
    entry_i: int
    peak_close: float


@dataclass
class SimResult:
    dates: list[str]
    port_ret: list[float]
    gross: list[float]          # invested fraction each day (1 - cash)
    turnover_events: int
    turnover_sum: float
    hold_spans: list[int]       # closed-position holding lengths (sessions)


def _intra_exit(variant: str, s: Series, i: int, pos: Pos) -> bool:
    """True if this held name should be dumped to cash today (variant E2/E3/E4)."""
    c = s.close[i]
    if c is None:
        return True
    if variant == "E2":
        sm = s.sma100[i]
        return sm is not None and c < sm
    if variant == "E3":
        r = _ret(s.close, i, EXH_LOOKBACK)
        return r is not None and r < 0.0
    if variant == "E4":
        atr = s.atr20[i]
        if atr is None:
            return False
        return c < pos.peak_close - CHANDELIER_K * atr
    return False


def simulate(variant: str, dates: list[str], spy: list[float], px: dict[str, Series],
             cost_bps: float) -> SimResult:
    start = MIN_HISTORY + EXH_LOOKBACK
    rb = set(rebalance_indices(dates, start))
    cost_frac = cost_bps / 1e4
    slot_w = 1.0 / N_BASKET

    held: dict[str, Pos] = {}
    out_ret: list[float] = []
    out_gross: list[float] = []
    turn_events = 0
    turn_sum = 0.0
    hold_spans: list[int] = []

    for i in range(start, len(dates)):
        turn_today = 0.0

        # 1) monthly rebalance: apply hysteresis (E1..E4) or plain top-N (E0)
        if i in rb:
            comps = {}
            for s, series in px.items():
                c = score_components(series.close, spy, i)
                if c is not None:
                    comps[s] = c
            scores = rank_universe(comps)
            ordered = sorted(scores, key=lambda s: scores[s], reverse=True)
            rank_of = {s: r for r, s in enumerate(ordered)}
            keep_cut = int(HYST_MULT * N_BASKET)

            if variant == "E0":
                target = set(ordered[:N_BASKET])
            else:
                target = {s for s in held if rank_of.get(s, 10 ** 9) < keep_cut}
                for s in ordered:
                    if len(target) >= N_BASKET:
                        break
                    target.add(s)

            for s in list(held):
                if s not in target:
                    hold_spans.append(i - held[s].entry_i)
                    del held[s]
                    turn_today += slot_w
            for s in target:
                if s not in held and px[s].close[i]:
                    held[s] = Pos(entry_i=i, peak_close=px[s].close[i])
                    turn_today += slot_w

        # 2) intra-month defensive exits (E2/E3/E4 only)
        if variant in ("E2", "E3", "E4") and i not in rb:
            for s in list(held):
                if _intra_exit(variant, px[s], i, held[s]):
                    hold_spans.append(i - held[s].entry_i)
                    del held[s]
                    turn_today += slot_w

        # 3) accrue return for names still held; update chandelier peak
        r = 0.0
        for s, pos in held.items():
            ser = px[s]
            a, b = ser.close[i - 1], ser.close[i]
            if a and b:
                r += slot_w * (b / a - 1.0)
            if b and b > pos.peak_close:
                pos.peak_close = b

        rc = cost_frac * turn_today
        if turn_today:
            turn_events += 1
            turn_sum += turn_today
        out_ret.append(r - rc)
        out_gross.append(len(held) * slot_w)

    return SimResult(dates[start:], out_ret, out_gross, turn_events, turn_sum, hold_spans)


# --- metrics ---------------------------------------------------------


def curve_stats(rets: list[float]) -> dict[str, float | None]:
    if len(rets) < 30:
        return {k: None for k in ("cagr", "vol", "sharpe", "max_drawdown", "calmar")}
    eq, peak, mdd = 1.0, 1.0, 0.0
    for r in rets:
        eq *= 1.0 + r
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1.0)
    years = len(rets) / ANN
    cagr = eq ** (1.0 / years) - 1.0 if eq > 0 else None
    sd = statistics.pstdev(rets)
    return {
        "cagr": cagr,
        "vol": sd * math.sqrt(ANN),
        "sharpe": statistics.fmean(rets) / sd * math.sqrt(ANN) if sd else None,
        "max_drawdown": mdd,
        "calmar": cagr / abs(mdd) if cagr is not None and mdd < 0 else None,
    }


def period_stats(dates: list[str], rets: list[float]) -> list[dict[str, Any]]:
    out = []
    for label, s, e in PERIODS:
        idx = [k for k, d in enumerate(dates) if s <= d <= e]
        if len(idx) >= 60:
            out.append({"period": label, **curve_stats([rets[k] for k in idx])})
    return out


def bench_series(dates: list[str], spy: list[float], px: dict[str, Series], start_date: str) -> dict[str, dict]:
    si = next(k for k, d in enumerate(dates) if d >= start_date)
    spy_r = [spy[k] / spy[k - 1] - 1.0 for k in range(si + 1, len(spy))]
    ew = []
    for k in range(si + 1, len(dates)):
        day = [px[s].close[k] / px[s].close[k - 1] - 1.0 for s in px if px[s].close[k] and px[s].close[k - 1]]
        ew.append(statistics.fmean(day) if day else 0.0)
    return {"SPY buy&hold": curve_stats(spy_r), "equal-weight universe": curve_stats(ew)}


def _p(v, d=1):
    return "—" if v is None or not math.isfinite(v) else f"{v*100:.{d}f}%"


def _f(v, d=2):
    return "—" if v is None or not math.isfinite(v) else f"{v:.{d}f}"


def write_report(path: Path, rows: list[dict], periods: list[dict], bench: dict, meta: dict) -> None:
    body = "".join(
        f"<tr><td>{r['variant']}</td><td>{_p(r['cagr'])}</td><td>{_p(r['vol'])}</td><td>{_f(r['sharpe'])}</td>"
        f"<td>{_p(r['max_drawdown'])}</td><td>{_f(r['calmar'])}</td><td>{_f(r['turnover_yr'],1)}</td>"
        f"<td>{_p(r['avg_gross'])}</td><td>{_f(r['avg_hold_days'],0)}</td></tr>"
        for r in rows
    )
    prows = "".join(
        f"<tr><td>{r['variant']}</td><td>{r['period']}</td><td>{_p(r['cagr'])}</td><td>{_f(r['sharpe'])}</td>"
        f"<td>{_p(r['max_drawdown'])}</td><td>{_f(r['calmar'])}</td></tr>"
        for r in periods
    )
    brows = "".join(
        f"<tr><td>{k}</td><td>{_p(v['cagr'])}</td><td>{_p(v['vol'])}</td><td>{_f(v['sharpe'])}</td>"
        f"<td>{_p(v['max_drawdown'])}</td><td>{_f(v['calmar'])}</td></tr>"
        for k, v in bench.items()
    )
    path.write_text(f"""<!doctype html><meta charset=utf-8><title>Momentum M2 — exit</title>
<style>body{{font:14px system-ui;margin:24px;max-width:1000px}}table{{border-collapse:collapse;width:100%;margin:12px 0}}
td,th{{border-bottom:1px solid #ccc;padding:6px 10px;text-align:right}}td:first-child,th:first-child{{text-align:left}}
h2{{font-size:16px}}</style>
<h1>Cross-sectional momentum — Stage M2 (exit architecture)</h1>
<p>{meta['universe']} active symbols · {meta['start']}–{meta['end']} · M1 frozen: composite, N=20, monthly, skip=0 ·
cost {meta['cost_bps']:g} bps/turnover{' (×'+str(meta['cost_mult'])+')' if meta['cost_mult']!=1 else ''} ·
generated {time.strftime('%Y-%m-%d %H:%M')}</p>
<p><b>Not validated.</b> Equal-weight slots (1/20), intra-month exits go to cash until the next rebalance.
Survivorship-inflated absolutes — read the <i>differences</i> between rows.</p>
<h2>Full period</h2>
<table><tr><th>Variant</th><th>CAGR</th><th>Vol</th><th>Sharpe</th><th>maxDD</th><th>Calmar</th>
<th>Turnover/yr</th><th>Avg gross</th><th>Avg hold (d)</th></tr>{body}</table>
<h2>By sub-period</h2>
<table><tr><th>Variant</th><th>Period</th><th>CAGR</th><th>Sharpe</th><th>maxDD</th><th>Calmar</th></tr>{prows}</table>
<h2>Benchmarks (same window)</h2>
<table><tr><th></th><th>CAGR</th><th>Vol</th><th>Sharpe</th><th>maxDD</th><th>Calmar</th></tr>{brows}</table>
""", encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cost_bps = args.cost_bps * args.cost_mult
    t0 = time.perf_counter()
    with read_only(args.database) as conn:
        dates, spy, px = load_aligned(conn)
    print(f"loaded {len(px)} symbols, {len(dates)} sessions", flush=True)

    rows: list[dict[str, Any]] = []
    periods_all: list[dict[str, Any]] = []
    start_date = None
    for v in VARIANTS:
        sim = simulate(v, dates, spy, px, cost_bps)
        start_date = start_date or sim.dates[0]
        cs = curve_stats(sim.port_ret)
        years = len(sim.port_ret) / ANN
        row = {
            "variant": v, **cs,
            "turnover_yr": sim.turnover_sum / years if years else None,
            "turnover_events_yr": sim.turnover_events / years if years else None,
            "avg_gross": statistics.fmean(sim.gross) if sim.gross else None,
            "avg_hold_days": statistics.fmean(sim.hold_spans) if sim.hold_spans else None,
            "n_closed": len(sim.hold_spans),
        }
        rows.append(row)
        for pr in period_stats(sim.dates, sim.port_ret):
            periods_all.append({"variant": v, **pr})
        print(f"  {v}: Sharpe {_f(cs['sharpe'])} CAGR {_p(cs['cagr'])} maxDD {_p(cs['max_drawdown'])} "
              f"Calmar {_f(cs['calmar'])} turn/yr {_f(row['turnover_yr'],1)} gross {_p(row['avg_gross'])}", flush=True)

    bench = bench_series(dates, spy, px, start_date)

    meta = {"universe": len(px), "start": dates[0], "end": dates[-1],
            "cost_bps": cost_bps, "cost_mult": args.cost_mult}
    sfx = "" if args.cost_mult == 1.0 else f"_cost{args.cost_mult:g}"
    (args.output_dir / f"momentum_m2_summary{sfx}.json").write_text(
        json.dumps({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "meta": meta,
                    "variants": rows, "periods": periods_all, "benchmarks": bench}, indent=2), encoding="utf-8")
    with (args.output_dir / f"momentum_m2_results{sfx}.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    write_report(args.output_dir / f"momentum_m2_report{sfx}.html", rows, periods_all, bench, meta)
    print(f"done in {time.perf_counter() - t0:.0f}s — wrote momentum_m2_* to {args.output_dir}")


if __name__ == "__main__":
    main()
