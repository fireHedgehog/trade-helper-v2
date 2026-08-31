"""Cross-sectional momentum — Stage M4 (portfolio / sizing).

Disposable research. Read-only SQLite. See
docs/temp/XSEC_MOMENTUM_RESEARCH_HANDOFF.md.

Frozen: M1 (composite, N=20, monthly, skip=0) + M2 (E2 exit) + M3 (long only).
This stage layers the Turtle Stage-4 P4 ladder onto the long momentum book:

  S0  equal weight                        1/20 per slot                (= M3 long)
  S1  inverse-vol                         w_i ∝ 1/σ_i (σ = ann. 60d return vol)
  S2  S1 + vol-target scalar              L = clip(0.12 / port_vol_20d, 0, 1)   (de-lever only)
  S3  S2 + caps                           per-name ≤ 10% NAV, gross ≤ 1
  S4  S3 + sector cap                     ≤ 30% of gross in any one GICS sector
  S5  S3 + crash de-risk (Barroso)        extra L2 = min(1, median60(sleeveVol)/sleeveVol_now)

Freed weight (gate exits, cap trims, de-lever) sits in cash. Reports the
2020 and 2022 drawdowns explicitly -- that is what the ladder is bought for.

    backend/.venv/bin/python backend/temp/momentum_m4_sizing.py
    backend/.venv/bin/python backend/temp/momentum_m4_sizing.py --cost-mult 2
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
VOL_LOOKBACK = 60
TARGET_VOL = 0.12
PORT_VOL_LB = 20
SLEEVE_VOL_LB = 60
POS_CAP = 0.10
SECTOR_CAP = 0.30
K_MAX = 1.0

PERIODS = [
    ("2016-2019", "2016-01-01", "2019-12-31"),
    ("2020-2022", "2020-01-01", "2022-12-31"),
    ("2023-present", "2023-01-01", "9999-12-31"),
]
DD_WINDOWS = [("2020 covid", "2020-01-01", "2020-06-30"), ("2022 bear", "2022-01-01", "2022-12-31")]
WEIGHTS = {"rs_3m": .25, "rs_6m": .25, "rs_12m": .15, "high_52w_distance": .15,
           "trend_distance": .10, "slope": .10}
VARIANTS = ["S0", "S1", "S2", "S3", "S4", "S5"]


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


def load_aligned(conn: sqlite3.Connection):
    spy = conn.execute(
        "SELECT date, adj_close FROM price_bars WHERE symbol='SPY' AND adj_close IS NOT NULL ORDER BY date"
    ).fetchall()
    dates = [r["date"] for r in spy]
    spy_close = [float(r["adj_close"]) for r in spy]
    idx_of = {d: i for i, d in enumerate(dates)}
    n = len(dates)

    rows = conn.execute("SELECT symbol, sector FROM assets WHERE active=1 ORDER BY symbol").fetchall()
    symbols = [r["symbol"] for r in rows]
    sector_of = {r["symbol"]: (r["sector"] or "—") for r in rows}
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
    dret = {s: _daily_returns(v) for s, v in close.items()}
    return dates, spy_close, close, sma100, dret, sector_of


def _rolling_mean(series, n):
    out = [None] * len(series)
    win = []
    for i, v in enumerate(series):
        if v is None:
            win.clear(); continue
        win.append(v)
        if len(win) > n:
            win.pop(0)
        if len(win) == n:
            out[i] = sum(win) / n
    return out


def _daily_returns(series):
    out = [None] * len(series)
    for i in range(1, len(series)):
        a, b = series[i - 1], series[i]
        if a and b:
            out[i] = b / a - 1.0
    return out


def _vol_ann(dret, i, n):
    win = [r for r in dret[i - n + 1:i + 1] if r is not None]
    if len(win) < n * 3 // 4:
        return None
    return statistics.pstdev(win) * math.sqrt(ANN)


# --- composite score ---


def _ret(series, i, n):
    if i - n < 0:
        return None
    a, b = series[i - n], series[i]
    return (b / a - 1.0) if a and b else None


def _sma_at(series, i, n):
    if i - n + 1 < 0:
        return None
    win = [v for v in series[i - n + 1:i + 1] if v]
    return sum(win) / len(win) if len(win) == n else None


def score_components(series, spy, i):
    price = series[i]
    if price is None:
        return None
    out = {}
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


def rank_universe(comps):
    pct = {k: {} for k in WEIGHTS}
    for key in WEIGHTS:
        vals = sorted((c[key], s) for s, c in comps.items() if key in c)
        m = len(vals)
        for rank, (_, s) in enumerate(vals):
            pct[key][s] = 100.0 * rank / (m - 1) if m > 1 else 50.0
    out = {}
    for s in comps:
        num = sum(WEIGHTS[k] * pct[k][s] for k in WEIGHTS if s in pct[k])
        den = sum(WEIGHTS[k] for k in WEIGHTS if s in pct[k])
        if den > 0:
            out[s] = num / den
    return out


def rebalance_indices(dates, start):
    out = [start]
    for i in range(start + 1, len(dates)):
        if dates[i][:7] != dates[i - 1][:7]:
            out.append(i)
    return out


# --- simulation ---


@dataclass
class SimResult:
    dates: list[str]
    port_ret: list[float]
    gross: list[float]
    turnover_sum: float


def _target_weights(variant, held_syms, dret, sector_of, i):
    """Base per-name weights before portfolio-level scalars/caps."""
    if variant == "S0":
        return {s: 1.0 / N_BASKET for s in held_syms}
    inv = {}
    for s in held_syms:
        v = _vol_ann(dret[s], i, VOL_LOOKBACK)
        inv[s] = 1.0 / v if v and v > 0 else None
    good = {s: x for s, x in inv.items() if x is not None}
    if not good:
        return {s: 1.0 / N_BASKET for s in held_syms}
    tot = sum(good.values())
    w = {s: x / tot for s, x in good.items()}
    if variant in ("S3", "S4", "S5"):
        # per-name cap, then renormalise the uncapped remainder
        for _ in range(4):
            over = {s: x for s, x in w.items() if x > POS_CAP}
            if not over:
                break
            spill = sum(x - POS_CAP for s, x in over.items())
            for s in over:
                w[s] = POS_CAP
            under = {s: x for s, x in w.items() if x < POS_CAP}
            usum = sum(under.values())
            if usum <= 0:
                break
            for s in under:
                w[s] += spill * under[s] / usum
    if variant == "S4":
        for _ in range(4):
            bysec: dict[str, float] = {}
            for s, x in w.items():
                bysec[sector_of.get(s, "—")] = bysec.get(sector_of.get(s, "—"), 0.0) + x
            over = {sec: tot for sec, tot in bysec.items() if tot > SECTOR_CAP and sec != "—"}
            if not over:
                break
            for sec, tot_sec in over.items():
                scale = SECTOR_CAP / tot_sec
                for s in list(w):
                    if sector_of.get(s, "—") == sec:
                        w[s] *= scale
            # leave the freed weight as cash (do not force it back in)
            break
    return w


def simulate(variant, dates, spy, close, sma100, dret, sector_of, cost_bps):
    start = MIN_HISTORY + EXH_LOOKBACK
    rb = set(rebalance_indices(dates, start))
    cost_frac = cost_bps / 1e4
    weights: dict[str, float] = {}
    entry_i: dict[str, int] = {}
    out_ret: list[float] = []
    out_gross: list[float] = []
    turn_sum = 0.0

    for i in range(start, len(dates)):
        turn = 0.0
        if i in rb:
            comps = {}
            for s, series in close.items():
                c = score_components(series, spy, i)
                if c is not None:
                    comps[s] = c
            scores = rank_universe(comps)
            ordered = sorted(scores, key=lambda s: scores[s], reverse=True)
            rank_of = {s: r for r, s in enumerate(ordered)}
            keep = int(HYST_MULT * N_BASKET)
            target = {s for s in weights if rank_of.get(s, 10**9) < keep}
            for s in ordered:
                if len(target) >= N_BASKET:
                    break
                target.add(s)
            target = {s for s in target if close[s][i]}

            base_w = _target_weights(variant, target, dret, sector_of, i)

            L = 1.0
            if variant in ("S2", "S3", "S4", "S5") and len(out_ret) >= PORT_VOL_LB:
                pv = statistics.pstdev(out_ret[-PORT_VOL_LB:]) * math.sqrt(ANN)
                if pv > 0:
                    L = min(K_MAX, TARGET_VOL / pv)
            if variant == "S5" and len(out_ret) >= SLEEVE_VOL_LB * 2:
                hist = out_ret[-SLEEVE_VOL_LB * 3:]
                rolls = [statistics.pstdev(hist[j:j + SLEEVE_VOL_LB]) * math.sqrt(ANN)
                         for j in range(0, len(hist) - SLEEVE_VOL_LB, 5)]
                now = statistics.pstdev(out_ret[-SLEEVE_VOL_LB:]) * math.sqrt(ANN)
                if rolls and now > 0:
                    L *= min(1.0, statistics.median(rolls) / now)

            new_w = {s: w * L for s, w in base_w.items()}
            allsyms = set(new_w) | set(weights)
            turn += sum(abs(new_w.get(s, 0.0) - weights.get(s, 0.0)) for s in allsyms)
            weights = {s: w for s, w in new_w.items() if w > 1e-6}
            entry_i = {s: entry_i.get(s, i) for s in weights}

        if i not in rb:
            for s in list(weights):
                c, sm = close[s][i], sma100[s][i]
                if c is None or (sm is not None and c < sm):
                    turn += weights[s]
                    del weights[s]; entry_i.pop(s, None)

        r = 0.0
        for s, w in weights.items():
            a, b = close[s][i - 1], close[s][i]
            if a and b:
                r += w * (b / a - 1.0)
        turn_sum += turn
        out_ret.append(r - cost_frac * turn)
        out_gross.append(sum(weights.values()))

    return SimResult(dates[start:], out_ret, out_gross, turn_sum)


# --- metrics ---


def curve_stats(rets):
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


def window_dd(dates, rets, a, b):
    idx = [k for k, d in enumerate(dates) if a <= d <= b]
    if len(idx) < 20:
        return None
    eq, peak, mdd = 1.0, 1.0, 0.0
    for k in idx:
        eq *= 1.0 + rets[k]
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1.0)
    return mdd


def period_stats(dates, rets):
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


def write_report(path, rows, periods, meta):
    body = "".join(
        f"<tr><td>{r['variant']}</td><td>{_p(r['cagr'])}</td><td>{_p(r['vol'])}</td><td>{_f(r['sharpe'])}</td>"
        f"<td>{_p(r['max_drawdown'])}</td><td>{_f(r['calmar'])}</td><td>{_p(r['avg_gross'])}</td>"
        f"<td>{_p(r['dd_2020 covid'])}</td><td>{_p(r['dd_2022 bear'])}</td><td>{_f(r['turnover_yr'],1)}</td></tr>"
        for r in rows)
    prows = "".join(
        f"<tr><td>{r['variant']}</td><td>{r['period']}</td><td>{_p(r['cagr'])}</td><td>{_f(r['sharpe'])}</td>"
        f"<td>{_p(r['max_drawdown'])}</td><td>{_f(r['calmar'])}</td></tr>" for r in periods)
    path.write_text(f"""<!doctype html><meta charset=utf-8><title>Momentum M4 — sizing</title>
<style>body{{font:14px system-ui;margin:24px;max-width:1050px}}table{{border-collapse:collapse;width:100%;margin:12px 0}}
td,th{{border-bottom:1px solid #ccc;padding:6px 10px;text-align:right}}td:first-child,th:first-child{{text-align:left}}
h2{{font-size:16px}}</style>
<h1>Cross-sectional momentum — Stage M4 (portfolio / sizing)</h1>
<p>{meta['universe']} active symbols · {meta['start']}–{meta['end']} · M1+M2+M3 frozen (composite N=20 monthly skip=0, E2 exit, long only) ·
cost {meta['cost_bps']:g} bps{' (×'+str(meta['cost_mult'])+')' if meta['cost_mult']!=1 else ''} · {time.strftime('%Y-%m-%d %H:%M')}</p>
<p><b>Not validated.</b> k_max = 1 (de-lever only, never leverage). Freed weight -> cash.
Survivorship-inflated absolutes — read the ladder deltas and the two DD columns.</p>
<h2>Sizing ladder</h2>
<table><tr><th>Variant</th><th>CAGR</th><th>Vol</th><th>Sharpe</th><th>maxDD</th><th>Calmar</th><th>Avg gross</th>
<th>DD 2020</th><th>DD 2022</th><th>Turn/yr</th></tr>{body}</table>
<h2>By sub-period</h2>
<table><tr><th>Variant</th><th>Period</th><th>CAGR</th><th>Sharpe</th><th>maxDD</th><th>Calmar</th></tr>{prows}</table>
""", encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cost_bps = args.cost_bps * args.cost_mult
    t0 = time.perf_counter()
    with read_only(args.database) as conn:
        dates, spy, close, sma100, dret, sector_of = load_aligned(conn)
    print(f"loaded {len(close)} symbols, {len(dates)} sessions", flush=True)

    rows: list[dict[str, Any]] = []
    periods_all: list[dict[str, Any]] = []
    for v in VARIANTS:
        sim = simulate(v, dates, spy, close, sma100, dret, sector_of, cost_bps)
        cs = curve_stats(sim.port_ret)
        yrs = len(sim.port_ret) / ANN
        row = {"variant": v, **cs,
               "avg_gross": statistics.fmean(sim.gross) if sim.gross else None,
               "turnover_yr": sim.turnover_sum / yrs if yrs else None}
        for label, a, b in DD_WINDOWS:
            row[f"dd_{label}"] = window_dd(sim.dates, sim.port_ret, a, b)
        rows.append(row)
        for pr in period_stats(sim.dates, sim.port_ret):
            periods_all.append({"variant": v, **pr})
        print(f"  {v}: Sharpe {_f(cs['sharpe'])} CAGR {_p(cs['cagr'])} maxDD {_p(cs['max_drawdown'])} "
              f"Calmar {_f(cs['calmar'])} gross {_p(row['avg_gross'])} "
              f"DD20 {_p(row['dd_2020 covid'])} DD22 {_p(row['dd_2022 bear'])}", flush=True)

    meta = {"universe": len(close), "start": dates[0], "end": dates[-1],
            "cost_bps": cost_bps, "cost_mult": args.cost_mult}
    sfx = "" if args.cost_mult == 1.0 else f"_cost{args.cost_mult:g}"
    (args.output_dir / f"momentum_m4_summary{sfx}.json").write_text(
        json.dumps({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "meta": meta,
                    "variants": rows, "periods": periods_all}, indent=2), encoding="utf-8")
    with (args.output_dir / f"momentum_m4_results{sfx}.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    write_report(args.output_dir / f"momentum_m4_report{sfx}.html", rows, periods_all, meta)
    print(f"done in {time.perf_counter() - t0:.0f}s — wrote momentum_m4_* to {args.output_dir}")


if __name__ == "__main__":
    main()
