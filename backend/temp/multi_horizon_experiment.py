"""Disposable multi-horizon Donchian research infrastructure.

The production signal engine is reused without changing application code or
writing to SQLite. Every symbol receives the same pre-declared horizon set;
the report describes historical differences but never selects per-symbol
parameters. Outputs under docs/temp are disposable.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import sqlite3
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
from app.features.signals import engine, metrics  # noqa: E402
from app.features.signals.params import SignalParams  # noqa: E402
from app.features.signals.watchlist import (  # noqa: E402
    TREND_WATCHLIST,
    TREND_WATCHLIST_SECTIONS,
)
from turtle_vs_buyhold import (  # noqa: E402
    GROUP_ORDER,
    Target,
    active_config,
    latest_universe_run,
    read_only_connection,
    universe_targets,
)

ANNUAL_PERIODS = 252.0
MIN_ENGINE_BARS = 160
PERIOD_MIN_BARS = 126
CONFIRMATION_LIMIT = 126


@dataclass(frozen=True)
class Variant:
    key: str
    label: str
    entry_len: int
    exit_len: int


VARIANTS = [
    Variant("fast", "Fast 20/10", 20, 10),
    Variant("medium", "Medium 40/20", 40, 20),
    Variant("classic", "Classic 55/20", 55, 20),
    Variant("slow", "Slow 100/50", 100, 50),
]
ENSEMBLE_KEY = "ensemble"
ENSEMBLE_LABEL = "Equal horizon ensemble"
DIRECTIONS = ("both", "long")
PERIODS = [
    ("2016-2019", "2016-01-01", "2019-12-31"),
    ("2020-2022", "2020-01-01", "2022-12-31"),
    ("2023-present", "2023-01-01", "9999-12-31"),
]

WATCHLIST_SECTION = {
    ohlc.normalize_symbol(symbol): section
    for section, symbols in TREND_WATCHLIST_SECTIONS
    for symbol in symbols
}
WATCHLIST_ORDER = {
    ohlc.normalize_symbol(symbol): index
    for index, symbol in enumerate(TREND_WATCHLIST)
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=REPO_ROOT / "database" / "trade_helper.sqlite3",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "docs" / "temp",
    )
    parser.add_argument(
        "--primary-min-bars",
        type=int,
        default=756,
        help="Minimum observations for cross-sectional summaries.",
    )
    parser.add_argument(
        "--timeline-bars",
        type=int,
        default=756,
        help="Recent observations embedded for each watchlist timeline.",
    )
    return parser.parse_args()


def finite(values: Iterable[float | None]) -> list[float]:
    return [float(v) for v in values if v is not None and math.isfinite(float(v))]


def median(values: Iterable[float | None]) -> float | None:
    xs = finite(values)
    return statistics.median(xs) if xs else None


def mean(values: Iterable[float | None]) -> float | None:
    xs = finite(values)
    return statistics.fmean(xs) if xs else None


def percentile(values: Iterable[float | None], q: float) -> float | None:
    xs = sorted(finite(values))
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    position = (len(xs) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return xs[lower]
    weight = position - lower
    return xs[lower] * (1.0 - weight) + xs[upper] * weight


def curve_stats(returns: list[float]) -> dict[str, float | None]:
    if len(returns) < 2:
        return {
            "total_return": None,
            "cagr": None,
            "vol_annual": None,
            "sharpe": None,
            "max_drawdown": None,
            "calmar": None,
        }
    equity = engine.compound(returns)
    total_return = equity[-1] - 1.0
    years = len(returns) / ANNUAL_PERIODS
    cagr = equity[-1] ** (1.0 / years) - 1.0 if equity[-1] > 0 and years > 0 else None
    daily_mean = statistics.fmean(returns)
    daily_std = statistics.pstdev(returns)
    drawdown = engine.drawdown_curve(equity)
    max_drawdown = min(drawdown)
    return {
        "total_return": total_return,
        "cagr": cagr,
        "vol_annual": daily_std * math.sqrt(ANNUAL_PERIODS) if daily_std else None,
        "sharpe": daily_mean / daily_std * math.sqrt(ANNUAL_PERIODS) if daily_std else None,
        "max_drawdown": max_drawdown,
        "calmar": cagr / abs(max_drawdown) if cagr is not None and max_drawdown < 0 else None,
    }


def turnover_per_year(states: list[float]) -> float | None:
    if len(states) < 2:
        return None
    turnover = sum(abs(states[index] - states[index - 1]) for index in range(1, len(states)))
    years = len(states) / ANNUAL_PERIODS
    return turnover / years if years else None


def result_row(
    target: Target,
    direction: str,
    variant_key: str,
    variant_label: str,
    bars: list[dict[str, Any]],
    dates: list[str],
    states: list[float],
    returns: list[float],
    buy_hold_returns: list[float],
    trades: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    strategy = curve_stats(returns)
    buy_hold = curve_stats(buy_hold_returns)
    closed = [trade for trade in (trades or []) if trade["exit_date"] is not None]
    wins = [trade for trade in closed if trade["return_pct"] is not None and trade["return_pct"] > 0]
    cagr = strategy["cagr"]
    bh_cagr = buy_hold["cagr"]
    return {
        "symbol": target.symbol,
        "name": target.name,
        "group": target.group,
        "watchlist_section": WATCHLIST_SECTION.get(target.symbol, ""),
        "direction": direction,
        "variant": variant_key,
        "variant_label": variant_label,
        "bars": len(dates),
        "first_date": dates[0],
        "last_date": dates[-1],
        "cagr": cagr,
        "vol_annual": strategy["vol_annual"],
        "sharpe": strategy["sharpe"],
        "max_drawdown": strategy["max_drawdown"],
        "calmar": strategy["calmar"],
        "buy_hold_cagr": bh_cagr,
        "buy_hold_max_drawdown": buy_hold["max_drawdown"],
        "cagr_delta": cagr - bh_cagr if cagr is not None and bh_cagr is not None else None,
        "exposure": sum(1 for state in states if state != 0) / len(states),
        "average_abs_position": statistics.fmean(abs(state) for state in states),
        "turnover_per_year": turnover_per_year(states),
        "trades": len(closed) if trades is not None else None,
        "win_rate": len(wins) / len(closed) if closed else None,
        "average_hold_bars": mean(trade["bars_held"] for trade in closed),
        "long_return_sum": sum(ret for ret, state in zip(returns, states) if state > 0),
        "short_return_sum": sum(ret for ret, state in zip(returns, states) if state < 0),
    }


def period_rows(
    base: dict[str, Any],
    dates: list[str],
    states: list[float],
    returns: list[float],
    buy_hold_returns: list[float],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for period, start_date, end_date in PERIODS:
        indices = [index for index, date in enumerate(dates) if start_date <= date <= end_date]
        if len(indices) < PERIOD_MIN_BARS:
            continue
        selected_returns = [returns[index] for index in indices]
        selected_states = [states[index] for index in indices]
        selected_buy_hold = [buy_hold_returns[index] for index in indices]
        strategy = curve_stats(selected_returns)
        buy_hold = curve_stats(selected_buy_hold)
        output.append(
            {
                "symbol": base["symbol"],
                "group": base["group"],
                "watchlist_section": base["watchlist_section"],
                "direction": base["direction"],
                "variant": base["variant"],
                "variant_label": base["variant_label"],
                "period": period,
                "bars": len(indices),
                "first_date": dates[indices[0]],
                "last_date": dates[indices[-1]],
                "cagr": strategy["cagr"],
                "vol_annual": strategy["vol_annual"],
                "sharpe": strategy["sharpe"],
                "max_drawdown": strategy["max_drawdown"],
                "calmar": strategy["calmar"],
                "buy_hold_cagr": buy_hold["cagr"],
                "cagr_delta": (
                    strategy["cagr"] - buy_hold["cagr"]
                    if strategy["cagr"] is not None and buy_hold["cagr"] is not None
                    else None
                ),
                "average_abs_position": statistics.fmean(abs(state) for state in selected_states),
                "turnover_per_year": turnover_per_year(selected_states),
            }
        )
    return output


def confirmation_events(
    target: Target,
    dates: list[str],
    component_states: dict[str, list[float]],
) -> list[dict[str, Any]]:
    fast = component_states["fast"]
    events: list[dict[str, Any]] = []
    for index, state in enumerate(fast):
        previous = fast[index - 1] if index else 0
        if state == 0 or state == previous:
            continue
        direction = "long" if state > 0 else "short"
        for variant in VARIANTS[1:]:
            confirmation_index = next(
                (
                    future
                    for future in range(index, min(len(dates), index + CONFIRMATION_LIMIT + 1))
                    if component_states[variant.key][future] == state
                ),
                None,
            )
            events.append(
                {
                    "symbol": target.symbol,
                    "group": target.group,
                    "watchlist_section": WATCHLIST_SECTION.get(target.symbol, ""),
                    "fast_date": dates[index],
                    "fast_direction": direction,
                    "confirming_variant": variant.key,
                    "confirming_label": variant.label,
                    "confirmed": confirmation_index is not None,
                    "confirmation_date": dates[confirmation_index] if confirmation_index is not None else None,
                    "lag_bars": confirmation_index - index if confirmation_index is not None else None,
                }
            )
    return events


def variant_params(base: SignalParams, variant: Variant, direction: str) -> SignalParams:
    return base.model_copy(
        update={
            "entry_len": variant.entry_len,
            "exit_len": variant.exit_len,
            "trail_mode": "chandelier",
            "chandelier_k": 3.0,
            "allow_long": True,
            "allow_short": direction == "both",
        }
    )


def compute_symbol(
    target: Target,
    bars: list[dict[str, Any]],
    base: SignalParams,
    timeline_bars: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    dates = [bar["date"] for bar in bars]
    buy_hold_returns = engine.buy_hold_daily(bars)
    symbol_rows: list[dict[str, Any]] = []
    periods: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    timeline: dict[str, Any] | None = None
    direction_payload: dict[str, Any] = {}

    for direction in DIRECTIONS:
        daily_by_variant: dict[str, list[dict[str, Any]]] = {}
        result_by_variant: dict[str, Any] = {}
        for variant in VARIANTS:
            params = variant_params(base, variant, direction)
            result = engine.run(bars, params)
            daily_by_variant[variant.key] = result.daily
            result_by_variant[variant.key] = result

            states = [float(day["state"]) for day in result.daily]
            returns = [float(day["strat_ret"]) for day in result.daily]
            row = result_row(
                target,
                direction,
                variant.key,
                variant.label,
                bars,
                dates,
                states,
                returns,
                buy_hold_returns,
                result.trades,
            )
            symbol_rows.append(row)
            periods.extend(period_rows(row, dates, states, returns, buy_hold_returns))

        ensemble_states = [
            statistics.fmean(float(daily_by_variant[variant.key][index]["state"]) for variant in VARIANTS)
            for index in range(len(dates))
        ]
        ensemble_returns = [
            statistics.fmean(float(daily_by_variant[variant.key][index]["strat_ret"]) for variant in VARIANTS)
            for index in range(len(dates))
        ]
        ensemble_row = result_row(
            target,
            direction,
            ENSEMBLE_KEY,
            ENSEMBLE_LABEL,
            bars,
            dates,
            ensemble_states,
            ensemble_returns,
            buy_hold_returns,
            None,
        )
        symbol_rows.append(ensemble_row)
        periods.extend(period_rows(ensemble_row, dates, ensemble_states, ensemble_returns, buy_hold_returns))

        component_states = {
            variant.key: [float(day["state"]) for day in daily_by_variant[variant.key]]
            for variant in VARIANTS
        }
        if direction == "both":
            events.extend(confirmation_events(target, dates, component_states))

        if target.symbol in WATCHLIST_SECTION:
            start = max(0, len(dates) - timeline_bars)
            direction_payload[direction] = {
                "states": {key: values[start:] for key, values in component_states.items()},
                "ensemble": ensemble_states[start:],
            }

    if target.symbol in WATCHLIST_SECTION:
        start = max(0, len(dates) - timeline_bars)
        first_price = float(bars[start]["c"])
        timeline = {
            "symbol": target.symbol,
            "section": WATCHLIST_SECTION[target.symbol],
            "dates": dates[start:],
            "prices": [round(float(bar["c"]) / first_price * 100.0, 3) for bar in bars[start:]],
            "directions": direction_payload,
        }

    return symbol_rows, periods, events, timeline


def group_summaries(rows: list[dict[str, Any]], min_bars: int) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    variant_order = [variant.key for variant in VARIANTS] + [ENSEMBLE_KEY]
    contexts = [
        ("Full universe", lambda row: True),
        ("Watchlist", lambda row: bool(row["watchlist_section"])),
    ] + [
        (group, lambda row, expected=group: row["group"] == expected) for group in GROUP_ORDER
    ]
    for direction in DIRECTIONS:
        for group, predicate in contexts:
            for variant in variant_order:
                subset = [
                    row
                    for row in rows
                    if row["direction"] == direction
                    and predicate(row)
                    and row["variant"] == variant
                    and row["bars"] >= min_bars
                ]
                if not subset:
                    continue
                output.append(
                    {
                        "direction": direction,
                        "group": group,
                        "variant": variant,
                        "variant_label": subset[0]["variant_label"],
                        "n": len(subset),
                        "median_cagr": median(row["cagr"] for row in subset),
                        "median_cagr_delta": median(row["cagr_delta"] for row in subset),
                        "median_sharpe": median(row["sharpe"] for row in subset),
                        "median_calmar": median(row["calmar"] for row in subset),
                        "median_max_drawdown": median(row["max_drawdown"] for row in subset),
                        "median_abs_position": median(row["average_abs_position"] for row in subset),
                        "median_turnover": median(row["turnover_per_year"] for row in subset),
                        "median_trades": median(row["trades"] for row in subset),
                        "median_hold_bars": median(row["average_hold_bars"] for row in subset),
                        "buy_hold_beat_rate": sum(
                            row["cagr_delta"] is not None and row["cagr_delta"] > 0 for row in subset
                        )
                        / len(subset),
                    }
                )
    return output


def period_winner_summaries(periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_symbol: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in periods:
        if row["variant"] != ENSEMBLE_KEY and row["sharpe"] is not None:
            by_symbol[(row["symbol"], row["group"], row["direction"], row["period"])].append(row)

    winner_counts: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    symbol_period_winners: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    for (symbol, group, direction, period), candidates in by_symbol.items():
        winner = max(candidates, key=lambda row: row["sharpe"])["variant"]
        winner_counts[("Full universe", direction, period)][winner] += 1
        winner_counts[(group, direction, period)][winner] += 1
        if candidates[0]["watchlist_section"]:
            winner_counts[("Watchlist", direction, period)][winner] += 1
        symbol_period_winners[(symbol, direction)][period] = winner

    output: list[dict[str, Any]] = []
    for (group, direction, period), counts in sorted(winner_counts.items()):
        total = sum(counts.values())
        for variant in VARIANTS:
            output.append(
                {
                    "group": group,
                    "direction": direction,
                    "period": period,
                    "variant": variant.key,
                    "variant_label": variant.label,
                    "n": total,
                    "winner_count": counts[variant.key],
                    "winner_share": counts[variant.key] / total if total else None,
                }
            )

    for direction in DIRECTIONS:
        for group in ["Full universe", "Watchlist", *GROUP_ORDER]:
            stable = []
            for (symbol, symbol_direction), winners in symbol_period_winners.items():
                if symbol_direction != direction:
                    continue
                rows_for_symbol = [row for row in periods if row["symbol"] == symbol and row["direction"] == direction]
                if group == "Full universe":
                    belongs = bool(rows_for_symbol)
                elif group == "Watchlist":
                    belongs = bool(rows_for_symbol and rows_for_symbol[0]["watchlist_section"])
                else:
                    belongs = bool(rows_for_symbol and rows_for_symbol[0]["group"] == group)
                if not belongs or len(winners) < 2:
                    continue
                values = list(winners.values())
                stable.append(len(set(values)) == 1)
            if stable:
                output.append(
                    {
                        "group": group,
                        "direction": direction,
                        "period": "stable-across-periods",
                        "variant": "stable",
                        "variant_label": "Same Sharpe winner",
                        "n": len(stable),
                        "winner_count": sum(stable),
                        "winner_share": sum(stable) / len(stable),
                    }
                )
    return output


def lag_summaries(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    scopes = [("Universe", lambda row: True), ("Watchlist", lambda row: bool(row["watchlist_section"]))]
    for scope, predicate in scopes:
        for side in ("all", "long", "short"):
            for variant in VARIANTS[1:]:
                subset = [
                    row
                    for row in events
                    if predicate(row)
                    and row["confirming_variant"] == variant.key
                    and (side == "all" or row["fast_direction"] == side)
                ]
                if not subset:
                    continue
                confirmed = [row for row in subset if row["confirmed"]]
                output.append(
                    {
                        "scope": scope,
                        "side": side,
                        "variant": variant.key,
                        "variant_label": variant.label,
                        "events": len(subset),
                        "confirmed": len(confirmed),
                        "confirmation_rate": len(confirmed) / len(subset),
                        "median_lag_bars": median(row["lag_bars"] for row in confirmed),
                        "p75_lag_bars": percentile((row["lag_bars"] for row in confirmed), 0.75),
                    }
                )
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def escaped_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True).replace("</", "<\\/")


def write_report(
    path: Path,
    config_name: str,
    base_params: SignalParams,
    targets: int,
    computed: int,
    skipped: int,
    elapsed: float,
    min_bars: int,
    latest_run: dict[str, Any] | None,
    symbol_rows: list[dict[str, Any]],
    group_summary: list[dict[str, Any]],
    period_winners: list[dict[str, Any]],
    lag_summary: list[dict[str, Any]],
    timelines: list[dict[str, Any]],
) -> None:
    watchlist_rows = [row for row in symbol_rows if row["watchlist_section"]]
    watchlist_rows.sort(
        key=lambda row: (
            WATCHLIST_ORDER.get(row["symbol"], 999),
            DIRECTIONS.index(row["direction"]),
            ([variant.key for variant in VARIANTS] + [ENSEMBLE_KEY]).index(row["variant"]),
        )
    )
    payload = {
        "variants": [variant.__dict__ for variant in VARIANTS]
        + [{"key": ENSEMBLE_KEY, "label": ENSEMBLE_LABEL, "entry_len": None, "exit_len": None}],
        "groups": ["Full universe", "Watchlist"]
        + [group for group in GROUP_ORDER if any(row["group"] == group for row in group_summary)],
        "periods": [period[0] for period in PERIODS],
        "watchlistOrder": list(WATCHLIST_ORDER),
        "watchlistRows": watchlist_rows,
        "groupSummary": group_summary,
        "periodWinners": period_winners,
        "lagSummary": lag_summary,
        "timelines": timelines,
    }
    latest_text = (
        "none"
        if latest_run is None
        else f'run {latest_run["run_id"]}, {latest_run["n_symbols"]} symbols, finished {latest_run["finished_at"]}'
    )
    params_text = html.escape(json.dumps(base_params.model_dump(), indent=2))
    report_data = escaped_json(payload)
    content = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Multi-horizon Donchian experiment</title>
<style>
:root{{--bg:#f4f6f8;--panel:#ffffff;--ink:#172033;--muted:#667085;--line:#d9dee8;--grid:#e8ebf0;--fast:#2563eb;--medium:#7c3aed;--classic:#d97706;--slow:#dc2626;--ensemble:#059669;--positive:#16803c;--negative:#c0362c;--flat:#a1a8b3;--soft:#eef2f7}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f1217;--panel:#171b22;--ink:#e8edf5;--muted:#a7b0bf;--line:#303744;--grid:#242b35;--fast:#60a5fa;--medium:#a78bfa;--classic:#fbbf24;--slow:#f87171;--ensemble:#34d399;--positive:#4ade80;--negative:#fb7185;--flat:#737b89;--soft:#202630}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}main{{max-width:1440px;margin:auto;padding:28px}}h1{{font-size:30px;margin:0 0 4px}}h2{{font-size:20px;margin:0 0 12px}}h3{{font-size:16px;margin:0 0 8px}}p{{margin:8px 0}}.muted{{color:var(--muted)}}.panel{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:20px;margin:16px 0}}.intro{{border-left:4px solid var(--fast)}}.warning{{border-left:4px solid var(--classic)}}.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:10px}}.stat{{border:1px solid var(--line);border-radius:9px;padding:12px}}.stat b{{display:block;font-size:22px;font-weight:600}}.controls{{display:flex;gap:12px;align-items:end;flex-wrap:wrap;margin:0 0 14px}}label{{display:grid;gap:4px;color:var(--muted)}}select{{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:7px;padding:7px 30px 7px 9px;font:inherit}}.legend{{display:flex;flex-wrap:wrap;gap:14px;margin:8px 0;color:var(--muted)}}.legend span::before{{content:"";display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;background:var(--swatch)}}.chart{{width:100%;height:auto;display:block}}.chart text{{fill:var(--ink);font-size:12px}}.chart .muted-text{{fill:var(--muted)}}.chart .frame,.chart .grid{{stroke:var(--grid);fill:none}}.chart .axis{{stroke:var(--line)}}.heatmap-wrap{{overflow:auto}}.heatmap{{border-collapse:separate;border-spacing:4px;min-width:900px;width:100%}}.heatmap th{{text-align:left;color:var(--muted);font-weight:500;padding:5px}}.heatmap td{{padding:8px;border-radius:5px;text-align:center;font-variant-numeric:tabular-nums}}.heatmap td:first-child{{text-align:left;background:transparent!important;position:sticky;left:0;color:var(--ink);font-weight:600}}.table-wrap{{overflow:auto;max-height:620px}}table.data{{width:100%;border-collapse:collapse;white-space:nowrap}}table.data th,table.data td{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right}}table.data th{{position:sticky;top:0;background:var(--panel);color:var(--muted);font-weight:500;z-index:1}}table.data th:first-child,table.data td:first-child{{text-align:left}}.positive{{color:var(--positive)}}.negative{{color:var(--negative)}}.two-col{{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(390px,.9fr);gap:18px}}#profile-table table.data{{white-space:normal}}#profile-table table.data th,#profile-table table.data td{{padding-left:7px;padding-right:7px}}.timeline-tooltip{{min-height:24px;color:var(--muted);font-variant-numeric:tabular-nums}}details{{margin-top:10px}}pre{{overflow:auto;background:var(--soft);padding:12px;border-radius:8px}}code{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}}ul{{margin:8px 0;padding-left:20px}}@media(max-width:900px){{main{{padding:16px}}.two-col{{grid-template-columns:1fr}}h1{{font-size:25px}}}}
</style>
</head>
<body>
<main>
<h1>Multi-horizon Donchian experiment</h1>
<div class="muted">Disposable research · generated {time.strftime('%Y-%m-%d %H:%M:%S')} · SQLite opened read-only</div>

<section class="panel intro">
<h2>Research contract</h2>
<p>Every symbol runs the same four pre-declared horizons. Classification is used only for aggregation. No historical winner is promoted to a symbol-specific configuration.</p>
<div class="legend"><span style="--swatch:var(--fast)">Fast 20/10</span><span style="--swatch:var(--medium)">Medium 40/20</span><span style="--swatch:var(--classic)">Classic 55/20</span><span style="--swatch:var(--slow)">Slow 100/50</span><span style="--swatch:var(--ensemble)">Equal ensemble</span></div>
</section>

<section class="panel">
<div class="stats">
<div class="stat"><span>Universe targets</span><b>{targets}</b><small>{computed} computed · {skipped} skipped</small></div>
<div class="stat"><span>Engine runs</span><b>{computed * len(VARIANTS) * len(DIRECTIONS):,}</b><small>4 horizons × 2 direction policies</small></div>
<div class="stat"><span>Primary cohort</span><b>{sum(1 for row in symbol_rows if row['direction']=='both' and row['variant']=='fast' and row['bars'] >= min_bars)}</b><small>at least {min_bars} observations</small></div>
<div class="stat"><span>Watchlist</span><b>{len(timelines)}</b><small>dedicated signal timelines</small></div>
<div class="stat"><span>Compute time</span><b>{elapsed:.1f}s</b><small>database unchanged</small></div>
</div>
<p class="muted">Current config base: {html.escape(config_name)}. Latest persisted Trend universe: {html.escape(latest_text)}.</p>
<details><summary>Shared parameters</summary><pre><code>{params_text}</code></pre></details>
</section>

<section class="panel warning">
<h2>Interpretation limits</h2>
<ul><li>The full active universe is the primary research control sample. It contains current-membership and survivor/selection bias.</li><li>Bitcoin is reported as its own category. Ethereum remains in the full research universe.</li><li>“Winner” always means the highest historical Sharpe within a displayed period. It is diagnostic, never a parameter recommendation.</li><li>All horizon variants keep the same 3 ATR Chandelier trail so horizon is the primary changed dimension.</li><li>Long/short and long-only are separate fixed policies. Borrow fees, borrow availability, crypto funding, cash yield, portfolio sizing, and cross-market correlation are not modeled.</li><li>The production daily-return path books configured basis-point costs but does not book the ATR slippage estimate used in trade rows. Results inherit that engine behavior.</li><li>Crypto retains the app's 252-period annualisation. ETF proxies are not equivalent to futures, especially products with roll or structural decay.</li></ul>
</section>

<section class="panel">
<h2>Cross-sectional horizon profile</h2>
<div class="controls"><label>Direction policy<select id="profile-direction"><option value="both">Long / short</option><option value="long">Long only</option></select></label><label>Universe group<select id="profile-group"></select></label></div>
<div class="two-col"><svg id="profile-chart" class="chart" viewBox="0 0 860 400" role="img" aria-label="Median Sharpe and turnover by horizon"></svg><div><h3>How to read</h3><p class="muted">Sharpe compares return per unit of realised volatility. Turnover and average holding period reveal the economic meaning of “speed”: faster variants should trade more and confirm reversals earlier.</p><div id="profile-table"></div></div></div>
</section>

<section class="panel">
<h2>Which speed wins in different periods?</h2>
<div class="controls"><label>Direction policy<select id="winner-direction"><option value="both">Long / short</option><option value="long">Long only</option></select></label><label>Universe group<select id="winner-group"></select></label></div>
<svg id="winner-chart" class="chart" viewBox="0 0 1100 360" role="img" aria-label="Share of symbols won by each horizon in each period"></svg>
<p id="winner-note" class="muted"></p>
</section>

<section class="panel">
<h2>Fast-signal confirmation lag</h2>
<div class="controls"><label>Scope<select id="lag-scope"><option>Universe</option><option>Watchlist</option></select></label><label>Fast entry side<select id="lag-side"><option value="all">All</option><option value="long">Long</option><option value="short">Short</option></select></label></div>
<svg id="lag-chart" class="chart" viewBox="0 0 1000 320" role="img" aria-label="Confirmation lag after fast signal entries"></svg>
<p class="muted">For every new Fast 20/10 non-zero position, the experiment looks forward up to 126 bars for each slower horizon to hold the same direction. A zero-bar lag means it already agreed on the fast entry date.</p>
</section>

<section class="panel">
<h2>Watchlist horizon heatmap</h2>
<div class="controls"><label>Direction policy<select id="heat-direction"><option value="both">Long / short</option><option value="long">Long only</option></select></label><label>Metric<select id="heat-metric"><option value="sharpe">Sharpe</option><option value="cagr_delta">CAGR minus buy &amp; hold</option><option value="max_drawdown">Maximum drawdown</option><option value="turnover_per_year">Turnover per year</option></select></label></div>
<div id="watchlist-heatmap" class="heatmap-wrap"></div>
</section>

<section class="panel">
<h2>Watchlist signal-speed explorer</h2>
<div class="controls"><label>Symbol<select id="timeline-symbol"></select></label><label>Direction policy<select id="timeline-direction"><option value="both">Long / short</option><option value="long">Long only</option></select></label></div>
<svg id="timeline-chart" class="chart" viewBox="0 0 1200 520" role="img" aria-label="Price and trend position states across horizons"></svg>
<div id="timeline-tooltip" class="timeline-tooltip" aria-live="polite"></div>
</section>

<section class="panel">
<h2>Watchlist full-history detail</h2>
<div class="controls"><label>Direction policy<select id="table-direction"><option value="both">Long / short</option><option value="long">Long only</option></select></label></div>
<div id="watchlist-table" class="table-wrap"></div>
</section>

<section class="panel">
<h2>Next research gates</h2>
<ol><li>Keep the equal-horizon ensemble as the neutral benchmark; do not select the in-sample winner.</li><li>Add pure exit-channel variants as a separate stop-architecture experiment.</li><li>Add volatility-scaled position sizing only after the unscaled signal comparison is stable.</li><li>Build a cross-asset portfolio only after borrow, funding, cash yield, and ETF-versus-futures limitations are explicit.</li></ol>
</section>
</main>
<script>
const DATA={report_data};
const COLORS={{fast:'var(--fast)',medium:'var(--medium)',classic:'var(--classic)',slow:'var(--slow)',ensemble:'var(--ensemble)'}};
const HORIZONS=DATA.variants.filter(v=>v.key!=='ensemble');
const ALL_VARIANTS=DATA.variants;
const NS='http://www.w3.org/2000/svg';
const fmt=(value,digits=2)=>value==null||!Number.isFinite(Number(value))?'—':Number(value).toFixed(digits);
const pct=(value,digits=1)=>value==null||!Number.isFinite(Number(value))?'—':`${{(Number(value)*100).toFixed(digits)}}%`;
function svgEl(tag,attrs={{}},text=''){{const node=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([key,value])=>node.setAttribute(key,value));if(text)node.textContent=text;return node}}
function clear(node){{while(node.firstChild)node.removeChild(node.firstChild)}}
function fillGroupSelect(id){{const select=document.getElementById(id);DATA.groups.forEach(group=>{{const option=document.createElement('option');option.value=group;option.textContent=group;select.appendChild(option)}});select.value=DATA.groups.includes('Full universe')?'Full universe':DATA.groups[0]}}
['profile-group','winner-group'].forEach(fillGroupSelect);

function drawProfile(){{
 const direction=document.getElementById('profile-direction').value,group=document.getElementById('profile-group').value;
 const rows=DATA.groupSummary.filter(row=>row.direction===direction&&row.group===group);
 const svg=document.getElementById('profile-chart');clear(svg);const W=860,H=400,L=70,R=70,T=35,B=62,plotW=W-L-R,plotH=H-T-B;
 svg.append(svgEl('rect',{{x:L,y:T,width:plotW,height:plotH,class:'frame'}}));
 const sharpes=rows.map(r=>r.median_sharpe).filter(Number.isFinite);const lo=Math.min(0,...sharpes)-.1,hi=Math.max(.1,...sharpes)+.1;
 const x=i=>L+i*plotW/(ALL_VARIANTS.length-1),y=v=>T+(hi-v)/(hi-lo)*plotH;
 for(let i=0;i<=4;i++){{const v=lo+(hi-lo)*i/4,yy=y(v);svg.append(svgEl('line',{{x1:L,y1:yy,x2:W-R,y2:yy,class:'grid'}}));svg.append(svgEl('text',{{x:L-10,y:yy+4,'text-anchor':'end',class:'muted-text'}},fmt(v,1)))}}
 const points=[];ALL_VARIANTS.forEach((variant,index)=>{{const row=rows.find(r=>r.variant===variant.key);if(!row)return;points.push(`${{x(index)}},${{y(row.median_sharpe)}}`);svg.append(svgEl('circle',{{cx:x(index),cy:y(row.median_sharpe),r:6,fill:COLORS[variant.key]}}));svg.append(svgEl('text',{{x:x(index),y:H-36,'text-anchor':'middle'}},variant.label.replace('Equal horizon ','Equal ')));svg.append(svgEl('text',{{x:x(index),y:y(row.median_sharpe)-12,'text-anchor':'middle'}},fmt(row.median_sharpe,2)))}});svg.insertBefore(svgEl('polyline',{{points:points.join(' '),fill:'none',stroke:'var(--ink)','stroke-width':2}}),svg.lastChild);
 svg.append(svgEl('text',{{x:18,y:T+plotH/2,transform:`rotate(-90 18 ${{T+plotH/2}})`,'text-anchor':'middle'}},'Median Sharpe'));
 const body=ALL_VARIANTS.map(variant=>{{const row=rows.find(r=>r.variant===variant.key);if(!row)return'';return `<tr><td>${{variant.label}}</td><td>${{fmt(row.median_turnover,1)}}</td><td>${{row.median_hold_bars==null?'—':fmt(row.median_hold_bars,0)}}</td><td>${{pct(row.median_abs_position)}}</td></tr>`}}).join('');
 document.getElementById('profile-table').innerHTML=`<div class="table-wrap"><table class="data"><thead><tr><th>Variant</th><th>Turnover/yr</th><th>Avg hold</th><th>Avg |pos|</th></tr></thead><tbody>${{body}}</tbody></table></div>`;
}}

function drawWinners(){{
 const direction=document.getElementById('winner-direction').value,group=document.getElementById('winner-group').value,svg=document.getElementById('winner-chart');clear(svg);const W=1100,H=360,L=150,R=40,T=30,B=50,plotW=W-L-R,rowH=78;
 DATA.periods.forEach((period,rowIndex)=>{{const rows=DATA.periodWinners.filter(row=>row.direction===direction&&row.group===group&&row.period===period);const y=T+rowIndex*rowH;svg.append(svgEl('text',{{x:L-12,y:y+28,'text-anchor':'end'}},period));let cursor=L;HORIZONS.forEach(variant=>{{const row=rows.find(item=>item.variant===variant.key);const width=(row?.winner_share||0)*plotW;if(width>0){{svg.append(svgEl('rect',{{x:cursor,y,width,height:36,fill:COLORS[variant.key]}}));if(width>48)svg.append(svgEl('text',{{x:cursor+width/2,y:y+23,'text-anchor':'middle'}},pct(row.winner_share,0)))}}cursor+=width}})}});
 let legendX=L;HORIZONS.forEach(variant=>{{svg.append(svgEl('rect',{{x:legendX,y:H-30,width:12,height:12,fill:COLORS[variant.key]}}));svg.append(svgEl('text',{{x:legendX+18,y:H-20}},variant.label));legendX+=190}});
 const stable=DATA.periodWinners.find(row=>row.direction===direction&&row.group===group&&row.period==='stable-across-periods');document.getElementById('winner-note').textContent=stable?`Only ${{pct(stable.winner_share)}} of ${{stable.n}} eligible symbols kept the same historical Sharpe winner across their available periods.`:'Not enough multi-period coverage for a stability estimate.';
}}

function drawLag(){{
 const scope=document.getElementById('lag-scope').value,side=document.getElementById('lag-side').value,rows=DATA.lagSummary.filter(row=>row.scope===scope&&row.side===side),svg=document.getElementById('lag-chart');clear(svg);const W=1000,H=320,L=170,R=90,T=25,B=55,plotW=W-L-R,maxLag=Math.max(1,...rows.map(row=>row.p75_lag_bars||0));
 rows.forEach((row,index)=>{{const y=T+index*72;svg.append(svgEl('text',{{x:L-12,y:y+21,'text-anchor':'end'}},row.variant_label));svg.append(svgEl('rect',{{x:L,y,width:plotW,height:20,fill:'var(--soft)'}}));svg.append(svgEl('rect',{{x:L,y,width:(row.median_lag_bars||0)/maxLag*plotW,height:20,fill:COLORS[row.variant]}}));svg.append(svgEl('line',{{x1:L+(row.p75_lag_bars||0)/maxLag*plotW,y1:y-4,x2:L+(row.p75_lag_bars||0)/maxLag*plotW,y2:y+24,stroke:COLORS[row.variant],'stroke-width':2}}));svg.append(svgEl('text',{{x:W-R+8,y:y+16}},`${{fmt(row.median_lag_bars,0)}} bars · ${{pct(row.confirmation_rate)}} confirm`))}});
 svg.append(svgEl('text',{{x:L+plotW/2,y:H-15,'text-anchor':'middle'}},`Bars after Fast 20/10 entry (line marks 75th percentile; scale max ${{fmt(maxLag,0)}})`));
}}

function heatColor(value,metric){{if(value==null||!Number.isFinite(Number(value)))return'var(--soft)';const v=Number(value);let z=metric==='max_drawdown'?(v+.4)/.4:metric==='turnover_per_year'?v/20:metric==='cagr_delta'?(v+.15)/.3:(v+1)/2;z=Math.max(0,Math.min(1,z));if(z<.5)return`color-mix(in srgb,var(--negative) ${{Math.round((.5-z)*80)}}%,var(--soft))`;return`color-mix(in srgb,var(--positive) ${{Math.round((z-.5)*80)}}%,var(--soft))`}}
function drawHeatmap(){{
 const direction=document.getElementById('heat-direction').value,metric=document.getElementById('heat-metric').value;let htmlText='<table class="heatmap"><thead><tr><th>Symbol</th>'+ALL_VARIANTS.map(v=>`<th>${{v.label}}</th>`).join('')+'</tr></thead><tbody>';
 DATA.watchlistOrder.forEach(symbol=>{{const rows=DATA.watchlistRows.filter(row=>row.symbol===symbol&&row.direction===direction);if(!rows.length)return;htmlText+=`<tr><td>${{symbol}}</td>`;ALL_VARIANTS.forEach(variant=>{{const row=rows.find(item=>item.variant===variant.key),value=row?.[metric];const display=metric==='cagr_delta'||metric==='max_drawdown'?pct(value):fmt(value,2);htmlText+=`<td style="background:${{heatColor(value,metric)}}" aria-label="${{symbol}} ${{variant.label}} ${{display}}">${{display}}</td>`}});htmlText+='</tr>'}});htmlText+='</tbody></table>';document.getElementById('watchlist-heatmap').innerHTML=htmlText;
}}

function drawTimeline(){{
 const symbol=document.getElementById('timeline-symbol').value,direction=document.getElementById('timeline-direction').value,item=DATA.timelines.find(row=>row.symbol===symbol),svg=document.getElementById('timeline-chart');clear(svg);if(!item)return;const states=item.directions[direction].states,ensemble=item.directions[direction].ensemble,dates=item.dates,prices=item.prices,W=1200,H=520,L=72,R=28,T=30,priceH=210,laneTop=285,laneH=34,plotW=W-L-R;const x=index=>L+index/Math.max(1,dates.length-1)*plotW;const pMin=Math.min(...prices),pMax=Math.max(...prices),py=value=>T+(pMax-value)/Math.max(.001,pMax-pMin)*priceH;
 svg.append(svgEl('rect',{{x:L,y:T,width:plotW,height:priceH,class:'frame'}}));const path=prices.map((price,index)=>`${{index?'L':'M'}}${{x(index).toFixed(1)}},${{py(price).toFixed(1)}}`).join(' ');svg.append(svgEl('path',{{d:path,fill:'none',stroke:'var(--ink)','stroke-width':2}}));svg.append(svgEl('text',{{x:L,y:18}},`${{symbol}} normalized price · recent ${{dates.length}} bars`));svg.append(svgEl('text',{{x:L-10,y:py(pMax)+4,'text-anchor':'end',class:'muted-text'}},fmt(pMax,0)));svg.append(svgEl('text',{{x:L-10,y:py(pMin)+4,'text-anchor':'end',class:'muted-text'}},fmt(pMin,0)));
 HORIZONS.forEach((variant,rowIndex)=>{{const values=states[variant.key],y=laneTop+rowIndex*laneH;svg.append(svgEl('text',{{x:L-10,y:y+20,'text-anchor':'end'}},variant.label.split(' ')[0]));let start=0;for(let index=1;index<=values.length;index++){{if(index===values.length||values[index]!==values[start]){{const state=values[start],fill=state>0?'var(--positive)':state<0?'var(--negative)':'var(--flat)';svg.append(svgEl('rect',{{x:x(start),y,width:Math.max(1,x(Math.min(index,values.length-1))-x(start)+1),height:24,fill,opacity:state===0?.22:.72}}));start=index}}}}}});
 const ey=laneTop+HORIZONS.length*laneH+20,zeroY=ey+30;svg.append(svgEl('text',{{x:L-10,y:zeroY+4,'text-anchor':'end'}},'Ensemble'));svg.append(svgEl('line',{{x1:L,y1:zeroY,x2:W-R,y2:zeroY,class:'axis'}}));const ensemblePath=ensemble.map((value,index)=>`${{index?'L':'M'}}${{x(index).toFixed(1)}},${{(zeroY-value*24).toFixed(1)}}`).join(' ');svg.append(svgEl('path',{{d:ensemblePath,fill:'none',stroke:'var(--ensemble)','stroke-width':2}}));
 [0,Math.floor((dates.length-1)/2),dates.length-1].forEach(index=>svg.append(svgEl('text',{{x:x(index),y:H-10,'text-anchor':index===0?'start':index===dates.length-1?'end':'middle',class:'muted-text'}},dates[index])));
 const guide=svgEl('line',{{x1:L,y1:T,x2:L,y2:zeroY+30,stroke:'var(--muted)','stroke-width':1,visibility:'hidden'}}),overlay=svgEl('rect',{{x:L,y:T,width:plotW,height:zeroY+30-T,fill:'transparent'}});svg.append(guide,overlay);overlay.addEventListener('mousemove',event=>{{const box=svg.getBoundingClientRect(),svgX=(event.clientX-box.left)/box.width*W,index=Math.max(0,Math.min(dates.length-1,Math.round((svgX-L)/plotW*(dates.length-1))));const gx=x(index);guide.setAttribute('x1',gx);guide.setAttribute('x2',gx);guide.setAttribute('visibility','visible');const stateText=HORIZONS.map(v=>`${{v.key}} ${{states[v.key][index]>0?'+1':states[v.key][index]<0?'-1':'0'}}`).join(' · ');document.getElementById('timeline-tooltip').textContent=`${{dates[index]}} · price ${{fmt(prices[index],1)}} · ${{stateText}} · ensemble ${{fmt(ensemble[index],2)}}`}});overlay.addEventListener('mouseleave',()=>guide.setAttribute('visibility','hidden'));
}}

function drawWatchlistTable(){{
 const direction=document.getElementById('table-direction').value,rows=DATA.watchlistRows.filter(row=>row.direction===direction);let body='';rows.forEach(row=>{{body+=`<tr><td>${{row.symbol}}</td><td>${{row.variant_label}}</td><td>${{pct(row.cagr)}}</td><td class="${{row.cagr_delta>=0?'positive':'negative'}}">${{pct(row.cagr_delta)}}</td><td>${{fmt(row.sharpe,2)}}</td><td>${{pct(row.max_drawdown)}}</td><td>${{fmt(row.calmar,2)}}</td><td>${{pct(row.average_abs_position)}}</td><td>${{fmt(row.turnover_per_year,1)}}</td></tr>`}});document.getElementById('watchlist-table').innerHTML=`<table class="data"><thead><tr><th>Symbol</th><th>Variant</th><th>CAGR</th><th>vs B&amp;H</th><th>Sharpe</th><th>Max DD</th><th>Calmar</th><th>Avg |position|</th><th>Turnover/yr</th></tr></thead><tbody>${{body}}</tbody></table>`;
}}

const timelineSelect=document.getElementById('timeline-symbol');DATA.watchlistOrder.filter(symbol=>DATA.timelines.some(row=>row.symbol===symbol)).forEach(symbol=>{{const option=document.createElement('option');option.value=symbol;option.textContent=`${{symbol}} · ${{DATA.timelines.find(row=>row.symbol===symbol).section}}`;timelineSelect.appendChild(option)}});timelineSelect.value=DATA.timelines.some(row=>row.symbol==='QQQ')?'QQQ':timelineSelect.options[0]?.value;
[['profile-direction',drawProfile],['profile-group',drawProfile],['winner-direction',drawWinners],['winner-group',drawWinners],['lag-scope',drawLag],['lag-side',drawLag],['heat-direction',drawHeatmap],['heat-metric',drawHeatmap],['timeline-symbol',drawTimeline],['timeline-direction',drawTimeline],['table-direction',drawWatchlistTable]].forEach(([id,fn])=>document.getElementById(id).addEventListener('change',fn));
drawProfile();drawWinners();drawLag();drawHeatmap();drawTimeline();drawWatchlistTable();
</script>
</body>
</html>'''
    path.write_text(content, encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with read_only_connection(args.database) as conn:
        config_name, base_params = active_config(conn)
        latest_run = latest_universe_run(conn)
        targets = universe_targets(conn)
        symbol_rows: list[dict[str, Any]] = []
        period_results: list[dict[str, Any]] = []
        speed_events: list[dict[str, Any]] = []
        timelines: list[dict[str, Any]] = []
        skipped = 0
        errors: list[dict[str, str]] = []
        for index, target in enumerate(targets, start=1):
            try:
                bars = ohlc.load_ohlc(conn, target.symbol)
                if len(bars) < MIN_ENGINE_BARS:
                    skipped += 1
                else:
                    rows, periods, events, timeline = compute_symbol(
                        target, bars, base_params, args.timeline_bars
                    )
                    symbol_rows.extend(rows)
                    period_results.extend(periods)
                    speed_events.extend(events)
                    if timeline is not None:
                        timelines.append(timeline)
            except Exception as exc:  # disposable batch research should keep progressing
                errors.append({"symbol": target.symbol, "error": f"{type(exc).__name__}: {exc}"})
            if index % 25 == 0 or index == len(targets):
                print(f"Computed {index}/{len(targets)} targets", flush=True)

    if not symbol_rows:
        raise RuntimeError("No symbols had enough bars")
    symbol_rows.sort(key=lambda row: (row["symbol"], row["direction"], row["variant"]))
    period_results.sort(
        key=lambda row: (row["symbol"], row["direction"], row["period"], row["variant"])
    )
    speed_events.sort(
        key=lambda row: (row["symbol"], row["fast_date"], row["confirming_variant"])
    )
    timelines.sort(key=lambda row: WATCHLIST_ORDER.get(row["symbol"], 999))
    groups = group_summaries(symbol_rows, args.primary_min_bars)
    winners = period_winner_summaries(period_results)
    lags = lag_summaries(speed_events)
    elapsed = time.perf_counter() - started

    outputs = {
        "symbols": args.output_dir / "multi_horizon_symbol_results.csv",
        "periods": args.output_dir / "multi_horizon_period_results.csv",
        "events": args.output_dir / "multi_horizon_speed_events.csv",
        "summary": args.output_dir / "multi_horizon_summary.json",
        "report": args.output_dir / "multi_horizon_report.html",
    }
    write_csv(outputs["symbols"], symbol_rows)
    write_csv(outputs["periods"], period_results)
    write_csv(outputs["events"], speed_events)
    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "database": str(args.database.resolve()),
        "config_name": config_name,
        "shared_params": base_params.model_dump(),
        "variants": [variant.__dict__ for variant in VARIANTS],
        "directions": list(DIRECTIONS),
        "periods": [
            {"label": label, "start": start, "end": end} for label, start, end in PERIODS
        ],
        "primary_min_bars": args.primary_min_bars,
        "targets": len(targets),
        "computed": len({row["symbol"] for row in symbol_rows}),
        "skipped_under_minimum": skipped,
        "errors": errors,
        "engine_runs": len({row["symbol"] for row in symbol_rows}) * len(VARIANTS) * len(DIRECTIONS),
        "latest_universe_run": latest_run,
        "group_summary": groups,
        "period_winners": winners,
        "lag_summary": lags,
    }
    outputs["summary"].write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(
        outputs["report"],
        config_name,
        base_params,
        len(targets),
        len({row["symbol"] for row in symbol_rows}),
        skipped + len(errors),
        elapsed,
        args.primary_min_bars,
        latest_run,
        symbol_rows,
        groups,
        winners,
        lags,
        timelines,
    )
    for output in outputs.values():
        print(f"Wrote {output}")
    if errors:
        print(f"Completed with {len(errors)} symbol errors", file=sys.stderr)


if __name__ == "__main__":
    main()
