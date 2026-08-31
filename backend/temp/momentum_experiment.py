"""Cross-sectional momentum — Stage M1 (selection & holding rule).

Disposable research. Opens SQLite read-only, never writes app tables. Outputs
under docs/temp are disposable. See
docs/temp/XSEC_MOMENTUM_RESEARCH_HANDOFF.md.

Walk-forward: the composite momentum score is recomputed as of each rebalance
date from each symbol's price series truncated to that date (the app's
ranking.py only scores "now"). Metrics + weights match ranking.py:
  rs_3m .25  rs_6m .25  rs_12m .15  high_52w_distance .15
  trend_distance .10  slope .10
Leadership persistence is a later M1 variant, not in this first pass.

    python backend/temp/momentum_experiment.py
    python backend/temp/momentum_experiment.py --cost-mult 2
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

TEMP_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEMP_DIR.parent.parent

ANN = 252.0
MIN_HISTORY = 252
PERIODS = [
    ("2016-2019", "2016-01-01", "2019-12-31"),
    ("2020-2022", "2020-01-01", "2022-12-31"),
    ("2023-present", "2023-01-01", "9999-12-31"),
]

# M1 candidate grid.
BASKET_SIZES = [10, 20, 40]
CADENCES = ["weekly", "monthly", "quarterly"]
SKIP_RECENT = [0, 21]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", type=Path, default=REPO_ROOT / "database" / "trade_helper.sqlite3")
    p.add_argument("--output-dir", type=Path, default=REPO_ROOT / "docs" / "temp")
    p.add_argument("--cost-bps", type=float, default=5.0, help="per-side rebalance cost, bps of turnover")
    p.add_argument("--cost-mult", type=float, default=1.0)
    return p.parse_args()


def read_only(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# --- data ---------------------------------------------------------------


def load_aligned(conn: sqlite3.Connection) -> tuple[list[str], list[float], dict[str, list[float | None]]]:
    spy = conn.execute(
        "SELECT date, adj_close FROM price_bars WHERE symbol='SPY' AND adj_close IS NOT NULL ORDER BY date"
    ).fetchall()
    dates = [r["date"] for r in spy]
    spy_close = [float(r["adj_close"]) for r in spy]
    idx_of = {d: i for i, d in enumerate(dates)}

    symbols = [r["symbol"] for r in conn.execute("SELECT symbol FROM assets WHERE active=1 ORDER BY symbol")]
    ph = ",".join("?" for _ in symbols)
    px: dict[str, list[float | None]] = {s: [None] * len(dates) for s in symbols}
    for r in conn.execute(
        f"SELECT symbol, date, adj_close FROM price_bars "
        f"WHERE symbol IN ({ph}) AND adj_close IS NOT NULL AND date >= ? ORDER BY symbol, date",
        (*symbols, dates[0]),
    ):
        i = idx_of.get(r["date"])
        if i is not None:
            px[r["symbol"]][i] = float(r["adj_close"])
    return dates, spy_close, px


# --- composite score as of a date index -------------------------------


def _ret(series: list[float | None], i: int, n: int) -> float | None:
    if i - n < 0:
        return None
    a, b = series[i - n], series[i]
    return (b / a - 1.0) if a and b else None


def _sma(series: list[float | None], i: int, n: int) -> float | None:
    if i - n + 1 < 0:
        return None
    win = [v for v in series[i - n + 1:i + 1] if v]
    return sum(win) / len(win) if len(win) == n else None


def score_components(series: list[float | None], spy: list[float], i: int, skip: int) -> dict[str, float] | None:
    """The six ranking.py metrics for one symbol at date index i. `skip` shifts
    the momentum endpoints back (the JT 12-1 gap) but keeps trend/high on i."""
    price = series[i]
    if price is None:
        return None
    j = i - skip
    out: dict[str, float] = {}
    for label, n in (("rs_3m", 63), ("rs_6m", 126), ("rs_12m", 252)):
        rs = _ret(series, j, n)
        sp = spy[j] / spy[j - n] - 1.0 if j - n >= 0 else None
        if rs is not None and sp is not None:
            out[label] = rs - sp
    window = [v for v in series[i - 251:i + 1] if v]
    if len(window) >= 200:
        out["high_52w_distance"] = price / max(window) - 1.0
    tds = [math.log(price / s) for n in (20, 50, 100, 200) if (s := _sma(series, i, n))]
    if tds:
        out["trend_distance"] = statistics.fmean(tds)
    sl = []
    for n in (50, 200):
        a, b = _sma(series, i - 20, n), _sma(series, i, n)
        if a and b:
            sl.append(b / a - 1.0)
    if sl:
        out["slope"] = statistics.fmean(sl)
    return out or None


WEIGHTS = {"rs_3m": .25, "rs_6m": .25, "rs_12m": .15, "high_52w_distance": .15,
           "trend_distance": .10, "slope": .10}


def rank_universe(comps: dict[str, dict[str, float]]) -> dict[str, float]:
    """comps: symbol -> its metric dict. Returns symbol -> composite 0..100."""
    pct: dict[str, dict[str, float]] = {k: {} for k in WEIGHTS}
    for key in WEIGHTS:
        vals = sorted((c[key], s) for s, c in comps.items() if key in c)
        n = len(vals)
        for rank, (_, s) in enumerate(vals):
            pct[key][s] = 100.0 * rank / (n - 1) if n > 1 else 50.0
    out: dict[str, float] = {}
    for s in comps:
        num = sum(WEIGHTS[k] * pct[k][s] for k in WEIGHTS if s in pct[k])
        den = sum(WEIGHTS[k] for k in WEIGHTS if s in pct[k])
        if den > 0:
            out[s] = num / den
    return out


# --- rebalance calendar + simulation ---------------------------------


def rebalance_indices(dates: list[str], cadence: str, start: int) -> list[int]:
    keyfn = {
        "weekly": lambda d: _isoweek(d),
        "monthly": lambda d: d[:7],
        "quarterly": lambda d: (d[:4], (int(d[5:7]) - 1) // 3),
    }[cadence]
    out = [start]
    for i in range(start + 1, len(dates)):
        if keyfn(dates[i]) != keyfn(dates[i - 1]):
            out.append(i)
    return out


def _isoweek(date: str) -> tuple[int, int]:
    import datetime
    y, m, d = map(int, date.split("-"))
    iso = datetime.date(y, m, d).isocalendar()
    return (iso[0], iso[1])


@dataclass
class SimResult:
    dates: list[str]
    port_ret: list[float]
    n_held: list[int]
    turnover_events: int


def simulate(dates: list[str], spy: list[float], px: dict[str, list[float | None]],
             n_basket: int, cadence: str, skip: int, cost_bps: float) -> SimResult:
    start = MIN_HISTORY + skip + 21
    rb = set(rebalance_indices(dates, cadence, start))
    weights: dict[str, float] = {}
    cost_frac = cost_bps / 1e4
    out_ret: list[float] = []
    out_n: list[int] = []
    turn_events = 0
    for i in range(start, len(dates)):
        rc = 0.0
        if i in rb:
            comps = {}
            for s, series in px.items():
                c = score_components(series, spy, i, skip)
                if c is not None:
                    comps[s] = c
            scores = rank_universe(comps)
            top = sorted(scores, key=lambda s: scores[s], reverse=True)[:n_basket]
            new_w = {s: 1.0 / len(top) for s in top} if top else {}
            turn = sum(abs(new_w.get(s, 0.0) - weights.get(s, 0.0)) for s in set(new_w) | set(weights))
            rc = cost_frac * turn
            weights = new_w
            turn_events += 1
        r = 0.0
        for s, w in weights.items():
            a, b = px[s][i - 1], px[s][i]
            if a and b:
                r += w * (b / a - 1.0)
        out_ret.append(r - rc)
        out_n.append(len(weights))
    return SimResult(dates[start:], out_ret, out_n, turn_events)


# --- metrics --------------------------------------------------------


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


def bench_series(dates: list[str], spy: list[float], px, start_date: str) -> dict[str, list[float]]:
    si = next(k for k, d in enumerate(dates) if d >= start_date)
    spy_r = [0.0] + [spy[k] / spy[k - 1] - 1.0 for k in range(si + 1, len(spy))]
    ew = []
    for k in range(si + 1, len(dates)):
        day = [px[s][k] / px[s][k - 1] - 1.0 for s in px if px[s][k] and px[s][k - 1]]
        ew.append(statistics.fmean(day) if day else 0.0)
    return {"SPY buy&hold": spy_r[1:], "equal-weight universe": ew}


# --- output --------------------------------------------------------


def finite(xs: Iterable[float | None]) -> list[float]:
    return [float(v) for v in xs if v is not None and math.isfinite(float(v))]


def write_report(path: Path, rows: list[dict[str, Any]], bench: dict[str, dict], meta: dict[str, Any]) -> None:
    body = "".join(
        f"<tr><td>{r['signal']}</td><td>{r['n_basket']}</td><td>{r['cadence']}</td><td>{r['skip']}</td>"
        f"<td>{_p(r['cagr'])}</td><td>{_p(r['vol'])}</td><td>{_f(r['sharpe'])}</td>"
        f"<td>{_p(r['max_drawdown'])}</td><td>{_f(r['calmar'])}</td><td>{_f(r['turnover_yr'],1)}</td>"
        f"<td>{_f(r['avg_n'],0)}</td></tr>"
        for r in sorted(rows, key=lambda r: -(r["sharpe"] or -9))
    )
    brows = "".join(
        f"<tr><td>{k}</td><td>{_p(v['cagr'])}</td><td>{_p(v['vol'])}</td><td>{_f(v['sharpe'])}</td>"
        f"<td>{_p(v['max_drawdown'])}</td><td>{_f(v['calmar'])}</td></tr>"
        for k, v in bench.items()
    )
    path.write_text(f"""<!doctype html><meta charset=utf-8><title>Momentum M1</title>
<style>body{{font:14px system-ui;margin:24px;max-width:1100px}}table{{border-collapse:collapse;width:100%;margin:12px 0}}
td,th{{border-bottom:1px solid #ccc;padding:6px 10px;text-align:right}}td:first-child,th:first-child{{text-align:left}}
h2{{font-size:16px}}code{{background:#eee;padding:1px 4px}}</style>
<h1>Cross-sectional momentum — Stage M1 (selection &amp; holding)</h1>
<p>{meta['universe']} active symbols · SPY calendar {meta['start']}–{meta['end']} ·
cost {meta['cost_bps']:g} bps/turnover{' (×'+str(meta['cost_mult'])+')' if meta['cost_mult']!=1 else ''} ·
generated {time.strftime('%Y-%m-%d %H:%M')}</p>
<p><b>Not validated.</b> Full-universe equal-weight basket, no sizing yet (that is M4). Composite score only;
leadership persistence deferred. Descriptive.</p>
<h2>M1 candidates (sorted by Sharpe)</h2>
<table><tr><th>Signal</th><th>N</th><th>Cadence</th><th>Skip</th><th>CAGR</th><th>Vol</th><th>Sharpe</th>
<th>maxDD</th><th>Calmar</th><th>Turnover/yr</th><th>Avg&nbsp;held</th></tr>{body}</table>
<h2>Benchmarks (same window)</h2>
<table><tr><th></th><th>CAGR</th><th>Vol</th><th>Sharpe</th><th>maxDD</th><th>Calmar</th></tr>{brows}</table>
""", encoding="utf-8")


def _p(v, d=1):
    return "—" if v is None or not math.isfinite(v) else f"{v*100:.{d}f}%"


def _f(v, d=2):
    return "—" if v is None or not math.isfinite(v) else f"{v:.{d}f}"


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
    n_runs = len(BASKET_SIZES) * len(CADENCES) * len(SKIP_RECENT)
    k = 0
    first_start_date = None
    for n_basket in BASKET_SIZES:
        for cadence in CADENCES:
            for skip in SKIP_RECENT:
                k += 1
                sim = simulate(dates, spy, px, n_basket, cadence, skip, cost_bps)
                first_start_date = first_start_date or sim.dates[0]
                cs = curve_stats(sim.port_ret)
                years = len(sim.port_ret) / ANN
                row = {
                    "signal": "composite", "n_basket": n_basket, "cadence": cadence, "skip": skip,
                    **cs,
                    "turnover_yr": sim.turnover_events / years if years else None,
                    "avg_n": statistics.fmean(sim.n_held) if sim.n_held else None,
                }
                rows.append(row)
                for pr in period_stats(sim.dates, sim.port_ret):
                    periods_all.append({"n_basket": n_basket, "cadence": cadence, "skip": skip, **pr})
                print(f"  [{k}/{n_runs}] N={n_basket} {cadence} skip={skip}: "
                      f"Sharpe {_f(cs['sharpe'])} CAGR {_p(cs['cagr'])} maxDD {_p(cs['max_drawdown'])}", flush=True)

    with read_only(args.database) as conn:
        _, spy2, px2 = load_aligned(conn)
    bench_raw = bench_series(dates, spy2, px2, first_start_date)
    bench = {k: curve_stats(v) for k, v in bench_raw.items()}

    meta = {"universe": len(px), "start": dates[0], "end": dates[-1],
            "cost_bps": cost_bps, "cost_mult": args.cost_mult}
    sfx = "" if args.cost_mult == 1.0 else f"_cost{args.cost_mult:g}"
    (args.output_dir / f"momentum_m1_summary{sfx}.json").write_text(
        json.dumps({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "meta": meta,
                    "candidates": rows, "periods": periods_all,
                    "benchmarks": bench}, indent=2), encoding="utf-8")
    with (args.output_dir / f"momentum_m1_results{sfx}.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    write_report(args.output_dir / f"momentum_m1_report{sfx}.html", rows, bench, meta)
    print(f"done in {time.perf_counter() - t0:.0f}s — wrote momentum_m1_* to {args.output_dir}")


if __name__ == "__main__":
    main()
