"""Oversold bounce (short-term mean reversion) — Stage R1 + R2 half-life.

Disposable research. Opens SQLite read-only, never writes app tables. Outputs
under docs/temp are disposable. See docs/temp/OVERSOLD_BOUNCE_RESEARCH_HANDOFF.md.

This first pass is an EVENT STUDY, not a portfolio sim. For every entry event
(signal on close of d, enter on close of d+1) it records the forward cumulative
return at horizons 1..20 sessions. That single computation answers both:

  R1  which entry bucket has the biggest, most reliable bounce
        (signal x threshold x quality gate x reversal window)
  R2  the alpha half-life -- the shape of the mean forward-return curve
        tells us where to anchor the fixed exit N (just past its peak)

`overbought_fade` (short the biggest 5d GAINERS) is reported alongside as a
symmetry check only -- the strategy stays long-only.

    backend/.venv/bin/python backend/temp/oversold_bounce_experiment.py
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import statistics
import time
from pathlib import Path
from typing import Any

TEMP_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEMP_DIR.parent.parent

ANN = 252.0
MIN_HISTORY = 220          # need SMA_200 + a little
LIQUID_POOL = 100
MIN_RAW_PRICE = 5.0
HORIZONS = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20]

PERIODS = [
    ("2016-2019", "2016-01-01", "2019-12-31"),
    ("2020-2022", "2020-01-01", "2022-12-31"),
    ("2023-present", "2023-01-01", "9999-12-31"),
]

# R1 grid
SIGNALS = ["raw", "sector_rel", "max"]      # sector_rel/max need sector tags; fall back to raw where absent
THRESHOLDS = [90.0, 95.0]
GATES = ["none", "liquid", "trend"]         # none | top-100 $vol + $5 | + above SMA_200
WINDOWS = [3, 5]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", type=Path, default=REPO_ROOT / "database" / "trade_helper.sqlite3")
    p.add_argument("--output-dir", type=Path, default=REPO_ROOT / "docs" / "temp")
    return p.parse_args()


def read_only(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# --- data ------------------------------------------------------------------


def load(conn: sqlite3.Connection):
    spy = conn.execute(
        "SELECT date FROM price_bars WHERE symbol='SPY' AND adj_close IS NOT NULL ORDER BY date"
    ).fetchall()
    dates = [r["date"] for r in spy]
    idx_of = {d: i for i, d in enumerate(dates)}
    n = len(dates)

    rows = conn.execute("SELECT symbol, sector FROM assets WHERE active=1").fetchall()
    symbols = sorted(r["symbol"] for r in rows)
    sector_of = {r["symbol"]: r["sector"] for r in rows if r["sector"]}
    ph = ",".join("?" for _ in symbols)

    adj: dict[str, list[float | None]] = {s: [None] * n for s in symbols}
    dv: dict[str, list[float | None]] = {s: [None] * n for s in symbols}   # raw close*vol
    rawok: dict[str, list[bool]] = {s: [False] * n for s in symbols}
    for r in conn.execute(
        f"SELECT symbol,date,adj_close,close,volume FROM price_bars "
        f"WHERE symbol IN ({ph}) AND adj_close IS NOT NULL AND date >= ? ORDER BY symbol,date",
        (*symbols, dates[0]),
    ):
        i = idx_of.get(r["date"])
        if i is None:
            continue
        adj[r["symbol"]][i] = float(r["adj_close"])
        if r["close"] and r["volume"]:
            dv[r["symbol"]][i] = float(r["close"]) * float(r["volume"])
            rawok[r["symbol"]][i] = float(r["close"]) >= MIN_RAW_PRICE
    return dates, symbols, sector_of, adj, dv, rawok


def median_dv(series: list[float | None], i: int, n: int = 20) -> float | None:
    win = [v for v in series[i - n + 1:i + 1] if v]
    return sorted(win)[len(win) // 2] if len(win) == n else None


def sma(series: list[float | None], i: int, n: int) -> float | None:
    win = [v for v in series[i - n + 1:i + 1] if v]
    return sum(win) / n if len(win) == n else None


def ret(series: list[float | None], i: int, n: int) -> float | None:
    a, b = series[i - n], series[i]
    return (b / a - 1.0) if (i - n >= 0 and a and b) else None


def pctile_map(pairs: list[tuple[str, float]]) -> dict[str, float]:
    """pairs: (symbol, value). Higher value -> higher percentile (0..100)."""
    sv = sorted(pairs, key=lambda t: t[1])
    m = len(sv)
    return {s: (100.0 * r / (m - 1) if m > 1 else 50.0) for r, (s, _) in enumerate(sv)}


# --- event collection ----------------------------------------------------


def collect_events(dates, symbols, sector_of, adj, dv, rawok, window: int):
    """One pass over the calendar. For each day d, build the liquid pool, compute
    -returnNd percentile (raw + sector-relative), and for every symbol emit an
    event dict with its percentiles + gate flags + the forward return path from
    the d+1 close. Reused across all (signal,threshold,gate) combos."""
    events: list[dict[str, Any]] = []
    n = len(dates)
    for d in range(MIN_HISTORY, n - 21):
        pool = []
        for s in symbols:
            mdv = median_dv(dv[s], d)
            if mdv is None or not rawok[s][d] or adj[s][d] is None:
                continue
            pool.append((s, mdv))
        pool.sort(key=lambda t: -t[1])
        liquid = {s for s, _ in pool[:LIQUID_POOL]}
        universe = [s for s, _ in pool]           # gate "none" uses the whole valid set
        if len(universe) < 30:
            continue

        r_by = {}
        for s in universe:
            r = ret(adj[s], d, window)
            if r is not None:
                r_by[s] = r
        if len(r_by) < 20:
            continue
        raw_pct = pctile_map([(s, -r) for s, r in r_by.items()])          # 100 = biggest loser
        gain_pct = pctile_map([(s, r) for s, r in r_by.items()])          # 100 = biggest gainer

        sec_members: dict[str, list[tuple[str, float]]] = {}
        for s, r in r_by.items():
            sec = sector_of.get(s)
            if sec:
                sec_members.setdefault(sec, []).append((s, r))
        sec_rel: dict[str, float] = {}
        for members in sec_members.values():
            if len(members) < 3:
                continue
            mean_r = statistics.fmean([v for _, v in members])
            for s, v in members:
                sec_rel[s] = v - mean_r
        sec_pct = pctile_map([(s, -v) for s, v in sec_rel.items()]) if sec_rel else {}

        e1 = d + 1
        for s in r_by:
            base = adj[s][e1]
            if base is None:
                continue
            fwd = {}
            for h in HORIZONS:
                p = adj[s][e1 + h] if e1 + h < n else None
                fwd[h] = (p / base - 1.0) if p else None
            events.append({
                "date": dates[d],
                "raw_pct": raw_pct.get(s),
                "sec_pct": sec_pct.get(s),
                "max_pct": max(x for x in (raw_pct.get(s), sec_pct.get(s)) if x is not None),
                "gain_pct": gain_pct.get(s),
                "in_liquid": s in liquid,
                "above_sma200": (lambda v, m: v is not None and m is not None and v > m)(
                    adj[s][d], sma(adj[s], d, 200)),
                "fwd": fwd,
            })
    return events


def gate_ok(ev: dict, gate: str) -> bool:
    if gate == "none":
        return True
    if gate == "liquid":
        return ev["in_liquid"]
    return ev["in_liquid"] and ev["above_sma200"]


def signal_pct(ev: dict, signal: str) -> float | None:
    return {"raw": ev["raw_pct"], "sector_rel": ev["sec_pct"], "max": ev["max_pct"]}[signal]


def summarise(evs: list[dict], years: float) -> dict[str, Any]:
    n = len(evs)
    out: dict[str, Any] = {"n_events": n, "events_yr": n / years if years else None}
    for h in HORIZONS:
        vals = [e["fwd"][h] for e in evs if e["fwd"].get(h) is not None]
        out[f"mean_{h}"] = statistics.fmean(vals) if vals else None
        out[f"med_{h}"] = statistics.median(vals) if vals else None
        if h in (3, 5, 10):
            out[f"hit_{h}"] = (sum(1 for v in vals if v > 0) / len(vals)) if vals else None
    means = [(h, out[f"mean_{h}"]) for h in HORIZONS if out[f"mean_{h}"] is not None]
    out["peak_h"] = max(means, key=lambda t: t[1])[0] if means else None
    out["peak_mean"] = max((m for _, m in means), default=None)
    return out


def _p(v, d=2):
    return "—" if v is None or not math.isfinite(v) else f"{v*100:.{d}f}%"


def write_report(path: Path, r1: list[dict], halflife: dict[str, list], overbought: dict, meta: dict):
    def row(r):
        cells = "".join(f"<td>{_p(r.get(f'mean_{h}'))}</td>" for h in (1, 3, 5, 7, 10, 20))
        return (f"<tr><td>{r['signal']}</td><td>{r['threshold']:g}</td><td>{r['gate']}</td><td>{r['window']}d</td>"
                f"<td>{r['n_events']}</td><td>{r.get('events_yr',0):.0f}</td>"
                f"<td>{_p(r.get('hit_5'))}</td>{cells}<td>{r.get('peak_h')}</td><td>{_p(r.get('peak_mean'))}</td></tr>")
    body = "".join(row(r) for r in sorted(r1, key=lambda r: -(r.get("peak_mean") or -9)))
    hl_hdr = "".join(f"<th>{h}</th>" for h in HORIZONS)
    hl_body = "".join(
        f"<tr><td>{k}</td>" + "".join(f"<td>{_p(v)}</td>" for v in vals) + "</tr>"
        for k, vals in halflife.items()
    )
    ob = "".join(f"<td>{_p(overbought.get(f'mean_{h}'))}</td>" for h in HORIZONS)
    path.write_text(f"""<!doctype html><meta charset=utf-8><title>Oversold bounce R1</title>
<style>body{{font:13px system-ui;margin:24px;max-width:1200px}}table{{border-collapse:collapse;width:100%;margin:12px 0}}
td,th{{border-bottom:1px solid #ccc;padding:5px 8px;text-align:right}}td:first-child,th:first-child{{text-align:left}}
h2{{font-size:15px}}</style>
<h1>Oversold bounce — Stage R1 (entry) + R2 half-life</h1>
<p>{meta['universe']} active symbols · {meta['start']}–{meta['end']} · signal on close of d, enter close of d+1,
forward return from there · generated {time.strftime('%Y-%m-%d %H:%M')}</p>
<p><b>Event study, not a portfolio.</b> No costs, no concurrency cap, overlapping events. Survivorship-inflated.
Read the shape and the ranking, not the absolutes.</p>
<h2>R1 — entry buckets (mean forward cumulative return by horizon)</h2>
<table><tr><th>Signal</th><th>Thr</th><th>Gate</th><th>Win</th><th>N events</th><th>/yr</th><th>hit@5</th>
<th>+1</th><th>+3</th><th>+5</th><th>+7</th><th>+10</th><th>+20</th><th>peak h</th><th>peak mean</th></tr>{body}</table>
<h2>R2 — half-life curve (mean forward cum. return, selected buckets)</h2>
<table><tr><th>Bucket</th>{hl_hdr}</tr>{hl_body}</table>
<h2>Symmetry check — overbought fade (short biggest 5d gainers, raw, top 10%)</h2>
<table><tr><th></th>{hl_hdr}</tr><tr><td>mean fwd (long the gainer)</td>{ob}</tr></table>
<p>Negative here = a short would profit. Report only; the strategy is long-only.</p>
""", encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    with read_only(args.database) as conn:
        dates, symbols, sector_of, adj, dv, rawok = load(conn)
    print(f"loaded {len(symbols)} symbols, {len(dates)} sessions, {len(sector_of)} with sector tags", flush=True)

    ev_cache: dict[int, list[dict]] = {}
    for w in WINDOWS:
        ev_cache[w] = collect_events(dates, symbols, sector_of, adj, dv, rawok, w)
        print(f"  window {w}d: {len(ev_cache[w])} raw events", flush=True)

    span_years = (len(dates) - MIN_HISTORY - 21) / ANN

    r1: list[dict[str, Any]] = []
    for w in WINDOWS:
        for signal in SIGNALS:
            for thr in THRESHOLDS:
                for gate in GATES:
                    sel = [e for e in ev_cache[w]
                           if gate_ok(e, gate)
                           and (sp := signal_pct(e, signal)) is not None and sp >= thr]
                    rec = {"signal": signal, "threshold": thr, "gate": gate, "window": w,
                           **summarise(sel, span_years)}
                    r1.append(rec)
                    print(f"  {signal:10s} thr{thr:g} {gate:6s} {w}d: n={rec['n_events']:5d} "
                          f"peak h={rec['peak_h']} mean={_p(rec['peak_mean'])} hit@5={_p(rec.get('hit_5'))}", flush=True)

    # R2 half-life curves for a few representative buckets
    halflife: dict[str, list] = {}
    for signal, thr, gate, w in [
        ("raw", 90, "none", 5), ("raw", 95, "none", 5), ("raw", 90, "liquid", 5),
        ("raw", 90, "trend", 5), ("max", 90, "liquid", 5), ("raw", 90, "none", 3),
    ]:
        sel = [e for e in ev_cache[w]
               if gate_ok(e, gate) and (sp := signal_pct(e, signal)) is not None and sp >= thr]
        s = summarise(sel, span_years)
        halflife[f"{signal} thr{thr} {gate} {w}d"] = [s[f"mean_{h}"] for h in HORIZONS]

    # per-period stability for the headline bucket
    head = [e for e in ev_cache[5]
            if gate_ok(e, "liquid") and e["raw_pct"] is not None and e["raw_pct"] >= 90]
    per_period = {}
    for label, a, b in PERIODS:
        pe = [e for e in head if a <= e["date"] <= b]
        per_period[label] = summarise(pe, max(1, len([d for d in dates if a <= d <= b]) / ANN))

    # overbought symmetry
    ob = [e for e in ev_cache[5] if e["gain_pct"] is not None and e["gain_pct"] >= 90]
    ob_sum = summarise(ob, span_years)

    meta = {"universe": len(symbols), "start": dates[0], "end": dates[-1]}
    (args.output_dir / "oversold_bounce_r1_summary.json").write_text(
        json.dumps({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "meta": meta,
                    "r1": r1, "halflife": halflife, "headline_by_period": per_period,
                    "overbought_fade": ob_sum}, indent=2, default=str), encoding="utf-8")
    with (args.output_dir / "oversold_bounce_r1_results.csv").open("w", newline="", encoding="utf-8") as fh:
        cols = ["signal", "threshold", "gate", "window", "n_events", "events_yr",
                "hit_3", "hit_5", "hit_10", "peak_h", "peak_mean"] + [f"mean_{h}" for h in HORIZONS]
        wri = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        wri.writeheader()
        wri.writerows(r1)
    write_report(args.output_dir / "oversold_bounce_r1_report.html", r1, halflife, ob_sum, meta)
    print(f"\nheadline bucket (raw thr90 liquid 5d) by period:")
    for k, v in per_period.items():
        print(f"  {k}: n={v['n_events']} peak h={v['peak_h']} mean={_p(v['peak_mean'])} "
              f"hit@5={_p(v.get('hit_5'))} mean@5={_p(v.get('mean_5'))}")
    print(f"done in {time.perf_counter() - t0:.0f}s — wrote oversold_bounce_r1_* to {args.output_dir}")


if __name__ == "__main__":
    main()
