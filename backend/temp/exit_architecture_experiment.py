"""Stage 2 - disposable exit-architecture experiment (isolated).

Runs AFTER stage 1 (entry horizon) and BEFORE stage 3 (direction). Only the exit
trailing rule varies. Held fixed:

- Entry cluster from stage 1: Bond ETFs enter on the slow 100/50 Donchian
  channel, everything else on the fast 20/10 channel.
- Direction policy: long/short (the tree's pre-direction assumption; stage 3
  decides direction at the exit this experiment freezes).
- The initial 2 ATR disaster stop, always on in every variant.

Exit variants hold the give-back trailing rule at Chandelier 3 ATR and sweep the
Donchian reversal-channel width (the "decoration") from tight to almost-never-
binding, plus two reference points:

  channel   pure Donchian exit band (Turtle), width = entry cluster (10 / 50)
  c3_d10    Chandelier 3 ATR trail + Donchian-10 reversal   (~plain)
  c3_d20    Chandelier 3 ATR trail + Donchian-20 reversal   (decorated)
  c3_d55    Chandelier 3 ATR trail + Donchian-55 reversal   (decorated)
  c3_d100   Chandelier 3 ATR trail + Donchian-100 reversal  (~pure chandelier)
  c4_d10    Chandelier 4 ATR trail + Donchian-10 reversal   (looser trail)

Reuses the production signal engine, opens SQLite read-only, never writes to
application tables. Outputs under docs/temp are disposable.

  python backend/temp/exit_architecture_experiment.py
  python backend/temp/exit_architecture_experiment.py --from-csv     # re-roll only
  python backend/temp/exit_architecture_experiment.py --cost-mult 2  # stage 5 check
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

TEMP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TEMP_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TEMP_DIR))

from app.features.signals import data as ohlc  # noqa: E402
from app.features.signals import engine  # noqa: E402
from app.features.signals.params import SignalParams  # noqa: E402
from app.features.signals.watchlist import TREND_WATCHLIST_SECTIONS  # noqa: E402
from turtle_vs_buyhold import (  # noqa: E402
    GROUP_ORDER,
    Target,
    active_config,
    latest_universe_run,
    read_only_connection,
    universe_targets,
)

ANNUAL_PERIODS = 252.0
MIN_ENGINE_BARS = 200
PERIOD_MIN_BARS = 126
BOND_GROUP = "Bond ETF"
DIRECTION = "both"  # stage 2 holds direction at long/short

PERIODS = [
    ("2016-2019", "2016-01-01", "2019-12-31"),
    ("2020-2022", "2020-01-01", "2022-12-31"),
    ("2023-present", "2023-01-01", "9999-12-31"),
]


@dataclass(frozen=True)
class ExitVariant:
    key: str
    label: str
    trail_mode: str
    chandelier_k: float | None
    exit_len: int | None  # Donchian reversal/channel width; None = match entry cluster
    plain: bool


EXITS = [
    ExitVariant("channel", "Donchian exit channel (Turtle)", "exit_channel", None, None, True),
    ExitVariant("c3_d10", "Chandelier 3 ATR + Donchian-10", "chandelier", 3.0, 10, True),
    ExitVariant("c3_d20", "Chandelier 3 ATR + Donchian-20", "chandelier", 3.0, 20, False),
    ExitVariant("c3_d55", "Chandelier 3 ATR + Donchian-55", "chandelier", 3.0, 55, False),
    ExitVariant("c3_d100", "Chandelier 3 ATR + Donchian-100", "chandelier", 3.0, 100, False),
    ExitVariant("c4_d10", "Chandelier 4 ATR + Donchian-10", "chandelier", 4.0, 10, True),
]
EXIT_KEYS = [ev.key for ev in EXITS]

WATCHLIST_SECTION = {
    ohlc.normalize_symbol(symbol): section
    for section, symbols in TREND_WATCHLIST_SECTIONS
    for symbol in symbols
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=REPO_ROOT / "database" / "trade_helper.sqlite3")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "docs" / "temp")
    parser.add_argument("--primary-min-bars", type=int, default=756)
    parser.add_argument("--cost-mult", type=float, default=1.0,
                        help="Multiply modeled cost_bps and slippage_atr (use 2 for stage 5).")
    parser.add_argument("--from-csv", action="store_true",
                        help="Skip the engine sweep and re-roll from the existing symbol/period CSVs.")
    return parser.parse_args()


# --- small stat helpers (copied; disposable research) -----------------------


def finite(values: Iterable[float | None]) -> list[float]:
    return [float(v) for v in values if v is not None and math.isfinite(float(v))]


def median(values: Iterable[float | None]) -> float | None:
    xs = finite(values)
    return statistics.median(xs) if xs else None


def mean(values: Iterable[float | None]) -> float | None:
    xs = finite(values)
    return statistics.fmean(xs) if xs else None


def share(flags: Iterable[bool]) -> float | None:
    xs = list(flags)
    return sum(1 for f in xs if f) / len(xs) if xs else None


def curve_stats(returns: list[float]) -> dict[str, float | None]:
    if len(returns) < 2:
        return {k: None for k in ("cagr", "vol_annual", "sharpe", "max_drawdown", "calmar")}
    equity = engine.compound(returns)
    years = len(returns) / ANNUAL_PERIODS
    cagr = equity[-1] ** (1.0 / years) - 1.0 if equity[-1] > 0 and years > 0 else None
    daily_mean = statistics.fmean(returns)
    daily_std = statistics.pstdev(returns)
    max_drawdown = min(engine.drawdown_curve(equity))
    return {
        "cagr": cagr,
        "vol_annual": daily_std * math.sqrt(ANNUAL_PERIODS) if daily_std else None,
        "sharpe": daily_mean / daily_std * math.sqrt(ANNUAL_PERIODS) if daily_std else None,
        "max_drawdown": max_drawdown,
        "calmar": cagr / abs(max_drawdown) if cagr is not None and max_drawdown < 0 else None,
    }


def turnover_per_year(states: list[float]) -> float | None:
    if len(states) < 2:
        return None
    turnover = sum(abs(states[i] - states[i - 1]) for i in range(1, len(states)))
    years = len(states) / ANNUAL_PERIODS
    return turnover / years if years else None


# --- per-symbol computation ------------------------------------------------


def entry_lengths(group: str) -> tuple[int, int]:
    return (100, 50) if group == BOND_GROUP else (20, 10)


def build_params(base: SignalParams, target: Target, ev: ExitVariant, cost_mult: float) -> SignalParams:
    entry_len, entry_exit_len = entry_lengths(target.group)
    exit_len = entry_exit_len if ev.exit_len is None else ev.exit_len
    update: dict[str, Any] = {
        "entry_len": entry_len,
        "exit_len": exit_len,
        "trail_mode": ev.trail_mode,
        "allow_long": True,
        "allow_short": True,
        "cost_bps": min(50.0, base.cost_bps * cost_mult),
        "slippage_atr": min(1.0, base.slippage_atr * cost_mult),
    }
    if ev.chandelier_k is not None:
        update["chandelier_k"] = ev.chandelier_k
    return base.model_copy(update=update)


def result_row(
    target: Target, ev: ExitVariant, exit_len: int, dates: list[str], states: list[float],
    returns: list[float], buy_hold_returns: list[float], trades: list[dict[str, Any]],
) -> dict[str, Any]:
    strat = curve_stats(returns)
    bh = curve_stats(buy_hold_returns)
    closed = [t for t in trades if t["exit_date"] is not None]
    wins = [t for t in closed if t["return_pct"] is not None and t["return_pct"] > 0]
    cagr, bh_cagr = strat["cagr"], bh["cagr"]
    return {
        "symbol": target.symbol,
        "name": target.name,
        "group": target.group,
        "watchlist_section": WATCHLIST_SECTION.get(target.symbol, ""),
        "exit": ev.key,
        "exit_label": ev.label,
        "exit_len": exit_len,
        "bars": len(dates),
        "first_date": dates[0],
        "last_date": dates[-1],
        "cagr": cagr,
        "vol_annual": strat["vol_annual"],
        "sharpe": strat["sharpe"],
        "max_drawdown": strat["max_drawdown"],
        "calmar": strat["calmar"],
        "buy_hold_cagr": bh_cagr,
        "cagr_delta": cagr - bh_cagr if cagr is not None and bh_cagr is not None else None,
        "exposure": sum(1 for s in states if s != 0) / len(states),
        "turnover_per_year": turnover_per_year(states),
        "trades": len(closed),
        "win_rate": len(wins) / len(closed) if closed else None,
        "average_hold_bars": mean(t["bars_held"] for t in closed),
    }


def period_rows(base: dict[str, Any], dates: list[str], states: list[float], returns: list[float]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for period, start_date, end_date in PERIODS:
        idx = [i for i, d in enumerate(dates) if start_date <= d <= end_date]
        if len(idx) < PERIOD_MIN_BARS:
            continue
        strat = curve_stats([returns[i] for i in idx])
        out.append(
            {
                "symbol": base["symbol"],
                "group": base["group"],
                "watchlist_section": base["watchlist_section"],
                "exit": base["exit"],
                "exit_label": base["exit_label"],
                "period": period,
                "bars": len(idx),
                "cagr": strat["cagr"],
                "sharpe": strat["sharpe"],
                "max_drawdown": strat["max_drawdown"],
                "calmar": strat["calmar"],
                "turnover_per_year": turnover_per_year([states[i] for i in idx]),
            }
        )
    return out


def compute_symbol(target: Target, bars: list[dict[str, Any]], base: SignalParams, cost_mult: float):
    dates = [b["date"] for b in bars]
    buy_hold_returns = engine.buy_hold_daily(bars)
    symbol_rows: list[dict[str, Any]] = []
    periods: list[dict[str, Any]] = []
    for ev in EXITS:
        params = build_params(base, target, ev, cost_mult)
        result = engine.run(bars, params)
        states = [float(day["state"]) for day in result.daily]
        returns = [float(day["strat_ret"]) for day in result.daily]
        row = result_row(target, ev, params.exit_len, dates, states, returns, buy_hold_returns, result.trades)
        symbol_rows.append(row)
        periods.extend(period_rows(row, dates, states, returns))
    return symbol_rows, periods


# --- cross-sectional roll-ups -------------------------------------------------


def contexts_for(rows: list[dict[str, Any]]) -> list[tuple[str, Any]]:
    present = [g for g in GROUP_ORDER if any(r["group"] == g for r in rows)]
    return [
        ("Full universe", lambda r: True),
        ("Watchlist", lambda r: bool(r["watchlist_section"])),
    ] + [(g, lambda r, expected=g: r["group"] == expected) for g in present]


def group_summaries(rows: list[dict[str, Any]], min_bars: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for group, predicate in contexts_for(rows):
        for ev in EXITS:
            subset = [r for r in rows if predicate(r) and r["exit"] == ev.key and r["bars"] >= min_bars]
            if not subset:
                continue
            out.append(
                {
                    "group": group,
                    "exit": ev.key,
                    "exit_label": ev.label,
                    "n": len(subset),
                    "median_cagr": median(r["cagr"] for r in subset),
                    "median_cagr_delta": median(r["cagr_delta"] for r in subset),
                    "median_sharpe": median(r["sharpe"] for r in subset),
                    "median_calmar": median(r["calmar"] for r in subset),
                    "median_max_drawdown": median(r["max_drawdown"] for r in subset),
                    "median_turnover": median(r["turnover_per_year"] for r in subset),
                    "median_hold_bars": median(r["average_hold_bars"] for r in subset),
                    "median_trades": median(r["trades"] for r in subset),
                    "buy_hold_beat_rate": share(
                        r["cagr_delta"] is not None and r["cagr_delta"] > 0 for r in subset
                    ),
                }
            )
    return out


def _winner_counts(records: list[dict[str, Any]], key_period: str) -> list[dict[str, Any]]:
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        if r["sharpe"] is not None and math.isfinite(r["sharpe"]):
            by_symbol[r["symbol"]].append(r)
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for candidates in by_symbol.values():
        if len({c["exit"] for c in candidates}) < len(EXITS):
            continue
        winner = max(candidates, key=lambda c: c["sharpe"])["exit"]
        counts["Full universe"][winner] += 1
        counts[candidates[0]["group"]][winner] += 1
        if candidates[0]["watchlist_section"]:
            counts["Watchlist"][winner] += 1
    out: list[dict[str, Any]] = []
    for group, c in sorted(counts.items()):
        total = sum(c.values())
        for ev in EXITS:
            out.append(
                {
                    "group": group,
                    "period": key_period,
                    "exit": ev.key,
                    "exit_label": ev.label,
                    "n": total,
                    "winner_count": c[ev.key],
                    "winner_share": c[ev.key] / total if total else None,
                }
            )
    return out


def exit_winner_summaries(symbol_rows, period_results, min_bars: int) -> list[dict[str, Any]]:
    out = _winner_counts([r for r in symbol_rows if r["bars"] >= min_bars], "full-history")
    for period, *_ in PERIODS:
        out.extend(_winner_counts([r for r in period_results if r["period"] == period], period))

    by_symbol: dict[str, dict[str, str]] = defaultdict(dict)
    meta: dict[str, tuple[str, str]] = {}
    for period, *_ in PERIODS:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in period_results:
            if r["period"] == period and r["sharpe"] is not None and math.isfinite(r["sharpe"]):
                grouped[r["symbol"]].append(r)
        for symbol, candidates in grouped.items():
            if len({c["exit"] for c in candidates}) < len(EXITS):
                continue
            by_symbol[symbol][period] = max(candidates, key=lambda c: c["sharpe"])["exit"]
            meta[symbol] = (candidates[0]["group"], candidates[0]["watchlist_section"])
    for group in ["Full universe", "Watchlist", *GROUP_ORDER]:
        flags: list[bool] = []
        for symbol, winners in by_symbol.items():
            if len(winners) < 2:
                continue
            g, section = meta[symbol]
            belongs = group == "Full universe" or (group == "Watchlist" and section) or group == g
            if belongs:
                flags.append(len(set(winners.values())) == 1)
        if flags:
            out.append(
                {
                    "group": group,
                    "period": "stable-across-periods",
                    "exit": "stable",
                    "exit_label": "Same Sharpe winner",
                    "n": len(flags),
                    "winner_count": sum(flags),
                    "winner_share": sum(flags) / len(flags),
                }
            )
    return out


def plain_vs_decorated(rows: list[dict[str, Any]], min_bars: int) -> list[dict[str, Any]]:
    """Bucket the chandelier variants into plain (tight Donchian backstop) vs
    decorated (wide Donchian structure backstop) and compare, by scope."""
    plain_keys = {ev.key for ev in EXITS if ev.plain and ev.trail_mode == "chandelier"}
    deco_keys = {ev.key for ev in EXITS if not ev.plain}
    out: list[dict[str, Any]] = []
    for group, predicate in contexts_for(rows):
        base = [r for r in rows if predicate(r) and r["bars"] >= min_bars]
        if not base:
            continue
        for label, keys in (("plain (tight backstop)", plain_keys), ("decorated (wide backstop)", deco_keys)):
            subset = [r for r in base if r["exit"] in keys]
            out.append(
                {
                    "group": group,
                    "bucket": label,
                    "n_rows": len(subset),
                    "median_sharpe": median(r["sharpe"] for r in subset),
                    "median_cagr": median(r["cagr"] for r in subset),
                    "median_max_drawdown": median(r["max_drawdown"] for r in subset),
                    "median_calmar": median(r["calmar"] for r in subset),
                }
            )
    return out


# --- output ---------------------------------------------------------------


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def escaped_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True).replace("</", "<\\/")


_NUMERIC_FIELDS = {
    "exit_len", "bars", "cagr", "vol_annual", "sharpe", "max_drawdown", "calmar",
    "buy_hold_cagr", "cagr_delta", "exposure", "turnover_per_year", "trades",
    "win_rate", "average_hold_bars",
}


def _coerce(row: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key in _NUMERIC_FIELDS:
            out[key] = float(value) if value not in ("", None) else None
        else:
            out[key] = value
    return out


def load_from_csv(output_dir: Path):
    with (output_dir / "exit_arch_symbol_results.csv").open(encoding="utf-8") as handle:
        symbol_rows = [_coerce(r) for r in csv.DictReader(handle)]
    with (output_dir / "exit_arch_period_results.csv").open(encoding="utf-8") as handle:
        period_results = [_coerce(r) for r in csv.DictReader(handle)]
    return symbol_rows, period_results


def write_report(
    path: Path, config_name: str, base_params: SignalParams, cost_mult: float, targets: int,
    computed: int, skipped: int, elapsed: float, min_bars: int, latest_run: dict[str, Any] | None,
    group_summary: list[dict[str, Any]], exit_winners: list[dict[str, Any]],
    bucket_summary: list[dict[str, Any]],
) -> None:
    groups = ["Full universe", "Watchlist"] + [
        g for g in GROUP_ORDER if any(r["group"] == g for r in group_summary)
    ]
    payload = {
        "exits": [ev.__dict__ for ev in EXITS],
        "groups": groups,
        "periods": [p[0] for p in PERIODS] + ["full-history"],
        "groupSummary": group_summary,
        "exitWinners": exit_winners,
        "buckets": bucket_summary,
    }
    latest_text = (
        "none" if latest_run is None
        else f'run {latest_run["run_id"]}, {latest_run["n_symbols"]} symbols, finished {latest_run["finished_at"]}'
    )
    params_text = html.escape(json.dumps(base_params.model_dump(), indent=2))
    report_data = escaped_json(payload)
    cost_note = "normal modeled cost" if cost_mult == 1.0 else f"modeled cost x{cost_mult:g} (stage 5 robustness)"
    content = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Exit architecture experiment (stage 2)</title>
<style>
:root{{--bg:#f4f6f8;--panel:#fff;--ink:#172033;--muted:#667085;--line:#d9dee8;--pos:#16803c;--neg:#c0362c;--soft:#eef2f7;--c0:#2563eb;--c1:#0891b2;--c2:#059669;--c3:#65a30d;--c4:#d97706;--c5:#dc2626}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f1217;--panel:#171b22;--ink:#e8edf5;--muted:#a7b0bf;--line:#303744;--pos:#4ade80;--neg:#fb7185;--soft:#202630;--c0:#60a5fa;--c1:#22d3ee;--c2:#34d399;--c3:#a3e635;--c4:#fbbf24;--c5:#f87171}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:1280px;margin:auto;padding:26px}}h1{{font-size:26px;margin:0 0 4px}}h2{{font-size:19px;margin:0 0 10px}}h3{{font-size:15px;margin:14px 0 6px}}
.muted{{color:var(--muted)}}.panel{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;margin:15px 0}}
.intro{{border-left:4px solid var(--c0)}}.warn{{border-left:4px solid var(--c4)}}
.controls{{display:flex;gap:12px;flex-wrap:wrap;margin:0 0 12px}}label{{display:grid;gap:4px;color:var(--muted);font-size:13px}}
select{{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:7px;padding:6px 26px 6px 8px;font:inherit}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}}.stat{{border:1px solid var(--line);border-radius:9px;padding:11px}}.stat b{{display:block;font-size:20px}}
.table-wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;white-space:nowrap;font-variant-numeric:tabular-nums}}
th,td{{padding:7px 10px;border-bottom:1px solid var(--line);text-align:right}}th:first-child,td:first-child{{text-align:left}}
th{{position:sticky;top:0;background:var(--panel);color:var(--muted);font-weight:500}}
.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}
.bar{{display:flex;height:26px;border-radius:5px;overflow:hidden;border:1px solid var(--line);margin:3px 0}}
.bar span{{display:flex;align-items:center;justify-content:center;font-size:11px;color:#fff}}
.legend{{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:12px;margin:6px 0}}.legend i{{width:10px;height:10px;border-radius:2px;display:inline-block;margin-right:4px;vertical-align:middle}}
pre{{overflow:auto;background:var(--soft);padding:11px;border-radius:8px}}code{{font-family:ui-monospace,Consolas,monospace}}ul{{margin:6px 0;padding-left:20px}}
</style>
</head>
<body>
<main>
<h1>Exit architecture experiment &middot; stage 2</h1>
<div class="muted">Disposable research &middot; generated {time.strftime('%Y-%m-%d %H:%M:%S')} &middot; SQLite opened read-only &middot; {cost_note}</div>

<section class="panel intro">
<h2>Isolation contract</h2>
<p>Held fixed: stage 1 entry cluster (Bond ETFs 100/50, else 20/10), direction = long/short, initial 2 ATR disaster stop. Only the exit varies. The give-back trail is Chandelier 3 ATR throughout; the swept dimension is the Donchian reversal-channel width, from tight (<code>c3_d10</code>, nearly plain) to almost-never-binding (<code>c3_d100</code>, nearly pure chandelier). <code>channel</code> is the pure Turtle exit band; <code>c4_d10</code> is a looser trail reference.</p>
<div class="legend">
<span><i style="background:var(--c0)"></i>channel</span><span><i style="background:var(--c1)"></i>c3_d10</span><span><i style="background:var(--c2)"></i>c3_d20</span><span><i style="background:var(--c3)"></i>c3_d55</span><span><i style="background:var(--c4)"></i>c3_d100</span><span><i style="background:var(--c5)"></i>c4_d10</span>
</div>
</section>

<section class="panel">
<div class="stats">
<div class="stat"><span>Universe targets</span><b>{targets}</b><small>{computed} computed &middot; {skipped} skipped</small></div>
<div class="stat"><span>Engine runs</span><b>{computed * len(EXITS):,}</b><small>6 exits &times; long/short</small></div>
<div class="stat"><span>Primary cohort</span><b>{next((r['n'] for r in group_summary if r['group']=='Full universe' and r['exit']=='c3_d10'), 0)}</b><small>&ge; {min_bars} obs</small></div>
<div class="stat"><span>Compute time</span><b>{elapsed:.1f}s</b><small>database unchanged</small></div>
</div>
<p class="muted">Config base: {html.escape(config_name)}. Latest persisted Trend universe: {html.escape(latest_text)}.</p>
<details><summary>Shared parameters</summary><pre><code>{params_text}</code></pre></details>
</section>

<section class="panel warn">
<h2>Interpretation limits</h2>
<ul>
<li>Today's active universe: current-membership and survivor/selection bias.</li>
<li>&ldquo;Winner&rdquo; is the highest historical Sharpe among the six exits &mdash; diagnostic, never a per-symbol recommendation.</li>
<li>Warm-up length scales with the reversal width, so <code>c3_d100</code> evaluates a slightly shorter window per symbol than <code>c3_d10</code>; negligible in the &ge;756-bar cohort.</li>
<li>The daily-return path books configured basis-point cost but not the ATR slippage used in trade rows.</li>
</ul>
</section>

<section class="panel">
<h2>1. Exit comparison &mdash; cross-sectional medians</h2>
<div class="controls">
<label>Metric<select id="ex-metric">
<option value="median_sharpe">Median Sharpe</option>
<option value="median_cagr">Median CAGR</option>
<option value="median_cagr_delta">Median CAGR vs buy &amp; hold</option>
<option value="median_max_drawdown">Median max drawdown</option>
<option value="median_calmar">Median Calmar</option>
<option value="median_turnover">Median turnover / yr</option>
<option value="median_hold_bars">Median avg hold (bars)</option>
<option value="buy_hold_beat_rate">Buy &amp; hold beat rate</option>
</select></label>
</div>
<div id="ex-table" class="table-wrap"></div>
</section>

<section class="panel">
<h2>2. Plain vs decorated backstop</h2>
<p class="muted">Chandelier 3 ATR variants only. Plain = tight Donchian-10 reversal (<code>c3_d10</code>). Decorated = wide Donchian-20/55/100 structure backstop.</p>
<div id="bucket-table" class="table-wrap"></div>
</section>

<section class="panel">
<h2>3. Which exit wins? (highest Sharpe per symbol)</h2>
<div class="controls"><label>Scope<select id="win-group"></select></label></div>
<div id="win-bars"></div>
<p id="win-note" class="muted"></p>
</section>

</main>
<script>
const DATA={report_data};
const EXITS=DATA.exits;
const COLOR={{channel:'var(--c0)',c3_d10:'var(--c1)',c3_d20:'var(--c2)',c3_d55:'var(--c3)',c3_d100:'var(--c4)',c4_d10:'var(--c5)'}};
const fmt=(v,d=2)=>v==null||!Number.isFinite(+v)?'\\u2014':(+v).toFixed(d);
const pct=(v,d=1)=>v==null||!Number.isFinite(+v)?'\\u2014':(+v*100).toFixed(d)+'%';
const PCT_METRICS=new Set(['median_cagr','median_cagr_delta','median_max_drawdown','buy_hold_beat_rate']);

function fillGroups(id){{const s=document.getElementById(id);DATA.groups.forEach(g=>{{const o=document.createElement('option');o.value=g;o.textContent=g;s.appendChild(o)}});s.value='Full universe'}}
fillGroups('win-group');

function drawExitTable(){{
 const metric=document.getElementById('ex-metric').value,isPct=PCT_METRICS.has(metric);
 const higherBetter=metric!=='median_turnover'&&metric!=='median_hold_bars';
 let h='<table><thead><tr><th>Scope</th>'+EXITS.map(e=>`<th>${{e.key}}</th>`).join('')+'<th>n</th></tr></thead><tbody>';
 DATA.groups.forEach(g=>{{
  const rows=DATA.groupSummary.filter(r=>r.group===g);
  if(!rows.length)return;
  const vals=EXITS.map(e=>{{const r=rows.find(x=>x.exit===e.key);return r?r[metric]:null}});
  const fin=vals.filter(Number.isFinite);
  const best=higherBetter?Math.max(...fin):Math.min(...fin);
  h+=`<tr><td>${{g}}</td>`+vals.map(v=>{{
    const disp=isPct?pct(v):fmt(v,(metric==='median_turnover'||metric==='median_hold_bars')?1:2);
    const mark=(v!=null&&v===best&&higherBetter)?' style="font-weight:700"':'';
    return `<td${{mark}}>${{disp}}</td>`;
  }}).join('')+`<td>${{rows[0].n}}</td></tr>`;
 }});
 document.getElementById('ex-table').innerHTML=h+'</tbody></table>';
}}

function drawBuckets(){{
 let h='<table><thead><tr><th>Scope</th><th>plain Sharpe</th><th>deco Sharpe</th><th>plain CAGR</th><th>deco CAGR</th><th>plain maxDD</th><th>deco maxDD</th><th>plain Calmar</th><th>deco Calmar</th></tr></thead><tbody>';
 DATA.groups.forEach(g=>{{
  const p=DATA.buckets.find(b=>b.group===g&&b.bucket.startsWith('plain'));
  const d=DATA.buckets.find(b=>b.group===g&&b.bucket.startsWith('decorated'));
  if(!p||!d)return;
  const c=(a,b)=>a!=null&&b!=null?(a>=b?'pos':'neg'):'';
  h+=`<tr><td>${{g}}</td>`
   +`<td class="${{c(p.median_sharpe,d.median_sharpe)}}">${{fmt(p.median_sharpe)}}</td><td class="${{c(d.median_sharpe,p.median_sharpe)}}">${{fmt(d.median_sharpe)}}</td>`
   +`<td>${{pct(p.median_cagr)}}</td><td>${{pct(d.median_cagr)}}</td>`
   +`<td>${{pct(p.median_max_drawdown)}}</td><td>${{pct(d.median_max_drawdown)}}</td>`
   +`<td>${{fmt(p.median_calmar)}}</td><td>${{fmt(d.median_calmar)}}</td></tr>`;
 }});
 document.getElementById('bucket-table').innerHTML=h+'</tbody></table>';
}}

function drawWinners(){{
 const group=document.getElementById('win-group').value,box=document.getElementById('win-bars');box.innerHTML='';
 DATA.periods.forEach(period=>{{
  const rows=DATA.exitWinners.filter(r=>r.group===group&&r.period===period&&r.exit!=='stable');
  if(!rows.length)return;
  const total=rows[0].n;
  const label=document.createElement('div');label.className='muted';label.style.fontSize='12px';
  label.textContent=`${{period}} \\u00b7 n=${{total}}`;box.appendChild(label);
  const bar=document.createElement('div');bar.className='bar';
  EXITS.forEach(e=>{{
   const r=rows.find(x=>x.exit===e.key),s=r?r.winner_share:0;
   if(s>0){{const seg=document.createElement('span');seg.style.background=COLOR[e.key];seg.style.flexBasis=(s*100)+'%';seg.style.flexGrow=s;seg.textContent=s>0.10?e.key+' '+Math.round(s*100)+'%':'';bar.appendChild(seg)}}
  }});
  box.appendChild(bar);
 }});
 const stable=DATA.exitWinners.find(r=>r.group===group&&r.period==='stable-across-periods');
 document.getElementById('win-note').textContent=stable
   ?`Only ${{pct(stable.winner_share)}} of ${{stable.n}} multi-period symbols kept the same Sharpe winner across every covered period.`
   :'Not enough multi-period coverage for a stability estimate.';
}}

document.getElementById('ex-metric').addEventListener('change',drawExitTable);
document.getElementById('win-group').addEventListener('change',drawWinners);
drawExitTable();drawBuckets();drawWinners();
</script>
</body>
</html>'''
    path.write_text(content, encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    sfx = "" if args.cost_mult == 1.0 else f"_cost{args.cost_mult:g}"
    outputs = {
        "symbols": args.output_dir / f"exit_arch_symbol_results{sfx}.csv",
        "periods": args.output_dir / f"exit_arch_period_results{sfx}.csv",
        "summary": args.output_dir / f"exit_arch_summary{sfx}.json",
        "report": args.output_dir / f"exit_arch_report{sfx}.html",
    }
    skipped = 0
    errors: list[dict[str, str]] = []
    with read_only_connection(args.database) as conn:
        config_name, base_params = active_config(conn)
        latest_run = latest_universe_run(conn)
        targets = universe_targets(conn)
        if args.from_csv:
            symbol_rows, period_results = load_from_csv(args.output_dir)
            print(f"Reloaded {len(symbol_rows)} symbol rows from CSV; skipping compute", flush=True)
        else:
            symbol_rows, period_results = [], []
            for index, target in enumerate(targets, start=1):
                try:
                    bars = ohlc.load_ohlc(conn, target.symbol)
                    if len(bars) < MIN_ENGINE_BARS:
                        skipped += 1
                    else:
                        rows, periods = compute_symbol(target, bars, base_params, args.cost_mult)
                        symbol_rows.extend(rows)
                        period_results.extend(periods)
                except Exception as exc:
                    errors.append({"symbol": target.symbol, "error": f"{type(exc).__name__}: {exc}"})
                if index % 25 == 0 or index == len(targets):
                    print(f"Computed {index}/{len(targets)} targets", flush=True)

    if not symbol_rows:
        raise RuntimeError("No symbols had enough bars")
    symbol_rows.sort(key=lambda r: (r["symbol"], EXIT_KEYS.index(r["exit"])))
    period_results.sort(key=lambda r: (r["symbol"], r["period"], EXIT_KEYS.index(r["exit"])))
    if not args.from_csv:
        write_csv(outputs["symbols"], symbol_rows)
        write_csv(outputs["periods"], period_results)

    groups = group_summaries(symbol_rows, args.primary_min_bars)
    winners = exit_winner_summaries(symbol_rows, period_results, args.primary_min_bars)
    buckets = plain_vs_decorated(symbol_rows, args.primary_min_bars)
    elapsed = time.perf_counter() - started
    computed = len({r["symbol"] for r in symbol_rows})

    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "stage": "2 - exit architecture (isolated; direction held at long/short)",
        "database": str(args.database.resolve()),
        "config_name": config_name,
        "shared_params": base_params.model_dump(),
        "cost_mult": args.cost_mult,
        "entry_cluster": {"Bond ETF": "100/50", "default": "20/10"},
        "direction": DIRECTION,
        "exits": [ev.__dict__ for ev in EXITS],
        "periods": [{"label": p[0], "start": p[1], "end": p[2]} for p in PERIODS],
        "primary_min_bars": args.primary_min_bars,
        "targets": len(targets),
        "computed": computed,
        "skipped_under_minimum": skipped,
        "errors": errors,
        "engine_runs": computed * len(EXITS),
        "latest_universe_run": latest_run,
        "group_summary": groups,
        "exit_winners": winners,
        "plain_vs_decorated": buckets,
    }
    outputs["summary"].write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(
        outputs["report"], config_name, base_params, args.cost_mult, len(targets), computed,
        skipped + len(errors), elapsed, args.primary_min_bars, latest_run, groups, winners, buckets,
    )
    for output in (outputs.values() if not args.from_csv else [outputs["summary"], outputs["report"]]):
        print(f"Wrote {output}")
    if errors:
        print(f"Completed with {len(errors)} symbol errors", file=sys.stderr)


if __name__ == "__main__":
    main()
