"""Cross-sectional momentum — Stage M3 (direction), de-bias controlled.

Disposable research. Read-only SQLite, no app-table writes. See
docs/temp/XSEC_MOMENTUM_RESEARCH_HANDOFF.md.

Frozen from earlier stages:
  M1  composite score, N=20, monthly rebalance, skip=0
  M2  E2 exit  = hysteresis band (keep incumbent while rank within 1.5*N)
                 + per-name SMA_100 trend gate, applied symmetrically,
                 freed weight -> cash until the next monthly rebalance.

M3 asks: is this a long-only book?
  long        top-20 winners        (weights +1/20)
  long_short  + short bottom-20      (dollar-neutral, gross 2.0)
  short       bottom-20 losers only  (weights -1/20)   [de-bias leg]

De-bias control: split the universe into quintiles by each symbol's own
full-sample buy&hold CAGR ("drift") and re-run the LONG book inside each
quintile -- if momentum only "works" in the top drift quintile it is not an
edge, it is just owning the winners.

    backend/.venv/bin/python backend/temp/momentum_m3_direction.py
    backend/.venv/bin/python backend/temp/momentum_m3_direction.py --cost-mult 2
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TEMP_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEMP_DIR.parent.parent

ANN = 252.0
MIN_HISTORY = 252
N_BASKET = 20
HYST_MULT = 1.5
SMA_TREND = 100
EXH_LOOKBACK = 21

PERIODS = [
    ("2016-2019", "2016-01-01", "2019-12-31"),
    ("2020-2022", "2020-01-01", "2022-12-31"),
    ("2023-present", "2023-01-01", "9999-12-31"),
]
WEIGHTS = {"rs_3m": .25, "rs_6m": .25, "rs_12m": .15, "high_52w_distance": .15,
           "trend_distance": .10, "slope": .10}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", type=Path, default=REPO_ROOT / "database" / "trade_helper.sqlite3")
    p.add_argument("--output-dir", type=Path, default=REPO_ROOT / "docs" / "temp")
    p.add_argument("--cost-bps", type=float, default=5.0)
    p.add_argument("--cost-mult", type=float, default=1.0)
    return p.parse_args()


def read_only(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# --- data ------------------------------------------------------------------


def load_aligned(conn: sqlite3.Connection):
    spy = conn.execute(
        "SELECT date, adj_close FROM price_bars WHERE symbol='SPY' AND adj_close IS NOT NULL ORDER BY date"
    ).fetchall()
    dates = [r["date"] for r in spy]
    spy_close = [float(r["adj_close"]) for r in spy]
    idx_of = {d: i for i, d in enumerate(dates)}
    n = len(dates)

    symbols = [r["symbol"] for r in conn.execute("SELECT symbol FROM assets WHERE active=1 ORDER BY symbol")]
    ph = ",".join("?" for _ in symbols)
    close: dict[str, list[float | None]] = {s: [None] * n for s in symbols}
    for r in conn.execute(
        f"SELECT symbol, date, adj_close FROM price_bars "
        f"WHERE symbol IN ({ph}) AND adj_close IS NOT NULL AND date >= ? ORDER BY symbol, date",
        (*symbols, dates[0]),
    ):
        i = idx_of.get(r["date"])
        if i is not None:
            close[r["symbol"]][i] = float(r["adj_close"])
    sma100 = {s: _rolling_mean(v, SMA_TREND) for s, v in close.items()}
    return dates, spy_close, close, sma100


def _rolling_mean(series: list[float | None], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(series)
    win: list[float] = []
    for i, v in enumerate(series):
        if v is None:
            win.clear(); continue
        win.append(v)
        if len(win) > n:
            win.pop(0)
        if len(win) == n:
            out[i] = sum(win) / n
    return out


def drift_quintiles(close: dict[str, list[float | None]]) -> dict[str, int]:
    cagrs = []
    for s, v in close.items():
        pts = [(i, p) for i, p in enumerate(v) if p]
        if len(pts) < 252:
            continue
        (i0, p0), (i1, p1) = pts[0], pts[-1]
        yrs = (i1 - i0) / ANN
        if yrs > 0.5 and p0 > 0:
            cagrs.append((s, (p1 / p0) ** (1.0 / yrs) - 1.0))
    cagrs.sort(key=lambda t: t[1])
    m = len(cagrs)
    return {s: min(4, i * 5 // m) for i, (s, _) in enumerate(cagrs)}


# --- composite score ---------------------------------------------------


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


# --- simulation ------------------------------------------------------


@dataclass
class SimResult:
    dates: list[str]
    port_ret: list[float]
    gross: list[float]
    turnover_sum: float


def _gate_out(side: int, close_i: float | None, sma_i: float | None) -> bool:
    """SMA_100 trend gate, symmetric. Long exits below SMA; short exits above."""
    if close_i is None:
        return True
    if sma_i is None:
        return False
    return close_i < sma_i if side > 0 else close_i > sma_i


def simulate(direction: str, dates, spy, close, sma100, cost_bps: float,
             restrict: set[str] | None = None) -> SimResult:
    start = MIN_HISTORY + EXH_LOOKBACK
    rb = set(rebalance_indices(dates, start))
    cost_frac = cost_bps / 1e4
    slot = 1.0 / N_BASKET
    syms = [s for s in close if restrict is None or s in restrict]

    # held: symbol -> side (+1 / -1); a name is dropped to cash on gate/hysteresis.
    held: dict[str, int] = {}
    entry_i: dict[str, int] = {}
    out_ret: list[float] = []
    out_gross: list[float] = []
    turn_sum = 0.0

    for i in range(start, len(dates)):
        turn = 0.0
        if i in rb:
            comps = {}
            for s in syms:
                c = score_components(close[s], spy, i)
                if c is not None:
                    comps[s] = c
            scores = rank_universe(comps)
            ordered = sorted(scores, key=lambda s: scores[s], reverse=True)
            rank_of = {s: r for r, s in enumerate(ordered)}
            m = len(ordered)
            keep = int(HYST_MULT * N_BASKET)

            want_long: set[str] = set()
            want_short: set[str] = set()
            if direction in ("long", "long_short"):
                want_long = {s for s, sd in held.items() if sd > 0 and rank_of.get(s, 10**9) < keep}
                for s in ordered:
                    if len(want_long) >= N_BASKET:
                        break
                    want_long.add(s)
            if direction in ("short", "long_short"):
                want_short = {s for s, sd in held.items() if sd < 0 and rank_of.get(s, -1) >= m - keep}
                for s in reversed(ordered):
                    if len(want_short) >= N_BASKET:
                        break
                    want_short.add(s)

            target = {s: 1 for s in want_long}
            target.update({s: -1 for s in want_short})
            for s in list(held):
                if target.get(s) != held[s]:
                    turn += slot
                    del held[s]; entry_i.pop(s, None)
            for s, sd in target.items():
                if s not in held and close[s][i]:
                    held[s] = sd; entry_i[s] = i
                    turn += slot

        # intra-month SMA_100 gate (symmetric), freed weight -> cash
        if i not in rb:
            for s in list(held):
                if _gate_out(held[s], close[s][i], sma100[s][i]):
                    turn += slot
                    del held[s]; entry_i.pop(s, None)

        r = 0.0
        for s, sd in held.items():
            a, b = close[s][i - 1], close[s][i]
            if a and b:
                r += sd * slot * (b / a - 1.0)
        rc = cost_frac * turn
        turn_sum += turn
        out_ret.append(r - rc)
        out_gross.append(sum(slot for _ in held))

    return SimResult(dates[start:], out_ret, out_gross, turn_sum)


# --- metrics -------------------------------------------------------


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
    return {"cagr": cagr, "vol": sd * math.sqrt(ANN),
            "sharpe": statistics.fmean(rets) / sd * math.sqrt(ANN) if sd else None,
            "max_drawdown": mdd, "calmar": cagr / abs(mdd) if cagr is not None and mdd < 0 else None}


def period_stats(dates: list[str], rets: list[float]) -> list[dict[str, Any]]:
    out = []
    for label, s, e in PERIODS:
        idx = [k for k, d in enumerate(dates) if s <= d <= e]
        if len(idx) >= 60:
            out.append({"period": label, **curve_stats([rets[k] for k in idx])})
    return out


def _p(v, d=1):
    return "—" if v is None or not math.isfinite(v) else f"{v*100:.{d}f}%"


def _f(v, d=2):
    return "—" if v is None or not math.isfinite(v) else f"{v:.{d}f}"


def write_report(path: Path, direction_rows, dperiods, quint_rows, meta):
    drows = "".join(
        f"<tr><td>{r['direction']}</td><td>{_p(r['cagr'])}</td><td>{_p(r['vol'])}</td><td>{_f(r['sharpe'])}</td>"
        f"<td>{_p(r['max_drawdown'])}</td><td>{_f(r['calmar'])}</td><td>{_p(r['avg_gross'])}</td>"
        f"<td>{_f(r['turnover_yr'],1)}</td></tr>" for r in direction_rows)
    prows = "".join(
        f"<tr><td>{r['direction']}</td><td>{r['period']}</td><td>{_p(r['cagr'])}</td><td>{_f(r['sharpe'])}</td>"
        f"<td>{_p(r['max_drawdown'])}</td><td>{_f(r['calmar'])}</td></tr>" for r in dperiods)
    qrows = "".join(
        f"<tr><td>Q{r['quintile']+1}</td><td>{r['side']}</td><td>{_p(r['cagr'])}</td><td>{_f(r['sharpe'])}</td>"
        f"<td>{_p(r['max_drawdown'])}</td><td>{_f(r['calmar'])}</td><td>{r['n_symbols']}</td></tr>"
        for r in quint_rows)
    path.write_text(f"""<!doctype html><meta charset=utf-8><title>Momentum M3 — direction</title>
<style>body{{font:14px system-ui;margin:24px;max-width:1000px}}table{{border-collapse:collapse;width:100%;margin:12px 0}}
td,th{{border-bottom:1px solid #ccc;padding:6px 10px;text-align:right}}td:first-child,th:first-child{{text-align:left}}
h2{{font-size:16px}}</style>
<h1>Cross-sectional momentum — Stage M3 (direction)</h1>
<p>{meta['universe']} active symbols · {meta['start']}–{meta['end']} · M1+M2 frozen (composite, N=20, monthly, skip=0, E2 exit) ·
cost {meta['cost_bps']:g} bps{' (×'+str(meta['cost_mult'])+')' if meta['cost_mult']!=1 else ''} · {time.strftime('%Y-%m-%d %H:%M')}</p>
<p><b>Not validated.</b> long_short is dollar-neutral, gross ~2.0 (CAGR/vol scale with it; Sharpe does not).
Survivorship-inflated absolutes — read the long-vs-short <i>gap</i>.</p>
<h2>Direction</h2>
<table><tr><th>Direction</th><th>CAGR</th><th>Vol</th><th>Sharpe</th><th>maxDD</th><th>Calmar</th><th>Avg gross</th><th>Turn/yr</th></tr>{drows}</table>
<h2>By sub-period</h2>
<table><tr><th>Direction</th><th>Period</th><th>CAGR</th><th>Sharpe</th><th>maxDD</th><th>Calmar</th></tr>{prows}</table>
<h2>Drift-quintile control (Q1 = weakest buy&amp;hold drift, Q5 = strongest)</h2>
<table><tr><th>Quintile</th><th>Side</th><th>CAGR</th><th>Sharpe</th><th>maxDD</th><th>Calmar</th><th>N symbols</th></tr>{qrows}</table>
<p>If the long book is positive across Q1–Q4 too, the edge is momentum, not drift.</p>
""", encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cost_bps = args.cost_bps * args.cost_mult
    t0 = time.perf_counter()
    with read_only(args.database) as conn:
        dates, spy, close, sma100 = load_aligned(conn)
    quint = drift_quintiles(close)
    print(f"loaded {len(close)} symbols, {len(dates)} sessions; quintile sizes "
          f"{[sum(1 for q in quint.values() if q==k) for k in range(5)]}", flush=True)

    direction_rows: list[dict[str, Any]] = []
    dperiods: list[dict[str, Any]] = []
    for direction in ("long", "long_short", "short"):
        sim = simulate(direction, dates, spy, close, sma100, cost_bps)
        cs = curve_stats(sim.port_ret)
        yrs = len(sim.port_ret) / ANN
        row = {"direction": direction, **cs,
               "avg_gross": statistics.fmean(sim.gross) if sim.gross else None,
               "turnover_yr": sim.turnover_sum / yrs if yrs else None}
        direction_rows.append(row)
        for pr in period_stats(sim.dates, sim.port_ret):
            dperiods.append({"direction": direction, **pr})
        print(f"  {direction:11s}: Sharpe {_f(cs['sharpe'])} CAGR {_p(cs['cagr'])} maxDD {_p(cs['max_drawdown'])} "
              f"Calmar {_f(cs['calmar'])} gross {_p(row['avg_gross'])}", flush=True)

    quint_rows: list[dict[str, Any]] = []
    for k in range(5):
        restrict = {s for s, q in quint.items() if q == k}
        for direction, side in (("long", "long"), ("short", "short")):
            sim = simulate(direction, dates, spy, close, sma100, cost_bps, restrict=restrict)
            cs = curve_stats(sim.port_ret)
            quint_rows.append({"quintile": k, "side": side, "n_symbols": len(restrict), **cs})
            print(f"  Q{k+1} {side:5s}: Sharpe {_f(cs['sharpe'])} CAGR {_p(cs['cagr'])} maxDD {_p(cs['max_drawdown'])}", flush=True)

    meta = {"universe": len(close), "start": dates[0], "end": dates[-1],
            "cost_bps": cost_bps, "cost_mult": args.cost_mult}
    sfx = "" if args.cost_mult == 1.0 else f"_cost{args.cost_mult:g}"
    (args.output_dir / f"momentum_m3_summary{sfx}.json").write_text(
        json.dumps({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "meta": meta,
                    "direction": direction_rows, "periods": dperiods, "quintiles": quint_rows}, indent=2),
        encoding="utf-8")
    with (args.output_dir / f"momentum_m3_results{sfx}.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(direction_rows[0]))
        w.writeheader()
        w.writerows(direction_rows)
    write_report(args.output_dir / f"momentum_m3_report{sfx}.html", direction_rows, dperiods, quint_rows, meta)
    print(f"done in {time.perf_counter() - t0:.0f}s — wrote momentum_m3_* to {args.output_dir}")


if __name__ == "__main__":
    main()
