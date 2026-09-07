"""Step 1: measure the current strategy, without changing app data or parameters.

Run: backend/.venv/Scripts/python.exe backend/temp/step1/baseline.py
Report dependency: plotly (installed in the local backend virtual environment).
All outputs go to docs/temp/step1. SQLite is opened read-only.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from contextlib import ExitStack
from datetime import date, datetime, timezone
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
ROOT = BACKEND.parent
OUTPUT = ROOT / "docs" / "temp" / "step1"

from app.core.config import get_settings
from app.features.signals import data, engine, indicators, repository
from app.features.signals.params import ENGINE_VERSION, SignalParams
from app.features.signals.watchlist import TREND_WATCHLIST_SECTIONS
from app.features.data_management import universe as stored_groups
from report import write_report
from audit_engine import reference


def curve_stats(dates, returns, annual_days):
    equity, drawdown = [], []
    value = peak = 1.0
    peak_date = date.fromisoformat(dates[0])
    longest_underwater = 0
    underwater = False
    insolvency_date = None
    for day, ret in zip(dates, returns):
        value *= 1 + ret
        if value <= 0 and insolvency_date is None:
            insolvency_date = day
        current_date = date.fromisoformat(day)
        if value >= peak:
            if underwater:
                longest_underwater = max(longest_underwater, (current_date - peak_date).days)
            peak, peak_date = value, current_date
            underwater = False
        else:
            underwater = True
            longest_underwater = max(longest_underwater, (current_date - peak_date).days)
        equity.append(value)
        drawdown.append(value / peak - 1)
    years = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days / 365.25
    sd = statistics.pstdev(returns)
    return {
        "total_return": value - 1,
        "cagr": value ** (1 / years) - 1 if years and insolvency_date is None else None,
        "insolvency_date": insolvency_date,
        "max_drawdown": min(drawdown),
        "vol_annual": sd * math.sqrt(annual_days),
        "sharpe_zero_cash": statistics.fmean(returns) / sd * math.sqrt(annual_days) if sd else None,
        "longest_underwater_calendar_days": longest_underwater,
        "unrecovered": drawdown[-1] < -1e-12,
        "years": years,
    }, equity, drawdown


def audit_trades(bars, params, result):
    """Rebuild fill P&L and costs independently of engine daily-return output."""
    index = {b["date"]: i for i, b in enumerate(bars)}
    atr = indicators.wilder_atr([b["h"] for b in bars], [b["l"] for b in bars],
                               [b["c"] for b in bars], params.atr_len)
    terminal = 1.0
    max_error = 0.0
    fill_costs = []
    audited = []
    for trade in result.trades:
        i = index[trade["entry_date"]]
        signal_i = i - 1 if params.fill_at == "open_next" else i
        entry = trade["entry_price"]
        entry_cost = params.cost_bps / 10000 + params.slippage_atr * (atr[signal_i] or 0) / entry
        fill_costs.append(entry_cost * 10000)
        exit_cost = 0.0
        exit_price = trade["exit_price"] if trade["exit_date"] else bars[-1]["c"]
        if trade["exit_date"]:
            j = index[trade["exit_date"]]
            known_i = j if params.fill_at == "close" and trade["exit_reason"] == "channel_reversal" else j - 1
            exit_cost = (exit_price * params.cost_bps / 10000
                         + params.slippage_atr * (atr[known_i] or 0)) / entry
            fill_costs.append(exit_cost * entry / exit_price * 10000)
        direction = 1 if trade["direction"] == "long" else -1
        gross = direction * (exit_price / entry - 1)
        net = gross - entry_cost - exit_cost
        if trade["return_pct"] is not None:
            max_error = max(max_error, abs(net - trade["return_pct"]))
        terminal *= 1 + net
        audited.append({**trade, "gross_return": gross, "marked_net_return": net,
                        "entry_cost_bps": entry_cost * 10000,
                        "exit_cost_bps": exit_cost * entry / exit_price * 10000 if trade["exit_date"] else None})
    daily_terminal = math.prod(1 + d["strat_ret"] for d in result.daily)
    terminal_error = abs(terminal - daily_terminal)
    assert max_error < 1e-10 and terminal_error < 1e-8, (max_error, terminal_error)
    return audited, fill_costs, {"trade_return_max_error": max_error,
                                "terminal_equity_error": terminal_error}


def validate_data(symbol, bars):
    assert len(bars) >= 2, (symbol, "Fewer than two usable bars")
    dates = [b["date"] for b in bars]
    assert dates == sorted(set(dates)), (symbol, "Duplicate or unordered dates")
    for b in bars:
        assert all(math.isfinite(b[k]) for k in ("o", "h", "l", "c")), (symbol, b)
        assert 0 < b["l"] <= min(b["o"], b["c"]) <= max(b["o"], b["c"]) <= b["h"], (symbol, b)
    if "/" in symbol:
        assert len(bars) == (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days + 1


def analyse(symbol, group, bars, strategy):
    validate_data(symbol, bars)
    params = SignalParams(**strategy["params"]).model_copy(update={"allow_long": True, "allow_short": True})
    result = engine.run(bars, params)
    gross_result = engine.run(bars, params.model_copy(update={"cost_bps": 0, "slippage_atr": 0}))
    fills = lambda r: [(t["direction"], t["entry_date"], t["entry_price"], t["exit_date"], t["exit_price"])
                       for t in r.trades]
    assert fills(result) == fills(gross_result), "Cost audit changed the trades"
    audits, fill_costs, checks = audit_trades(bars, params, result)
    reference_equity, reference_trades, exhausted = reference(bars, params)
    production_equity = engine.compound([d["strat_ret"] for d in result.daily])
    cash_error = max(abs(a - b) / max(1, abs(b))
                     for a, b in zip(production_equity, reference_equity))
    assert cash_error < 1e-9, (symbol, "Independent cash/units audit", cash_error)
    checks.update({"independent_cash_bars": len(reference_equity),
                   "independent_cash_max_relative_error": cash_error,
                   "independent_cash_exhausted": exhausted})
    cuts = sorted(cut for cut in {max(params.warmup() + 5, len(bars) // 4), len(bars) // 2, len(bars) - 5}
                  if 1 < cut < len(bars))
    for cut in cuts:
        prefix = engine.run(bars[:cut], params)
        assert len(prefix.daily) == cut
        for a, b in zip(prefix.daily, result.daily[:cut]):
            assert a["date"] == b["date"]
            assert abs(a["strat_ret"] - b["strat_ret"]) < 1e-10, (symbol, cut, a["date"])
    checks.update({"prefix_comparisons": len(cuts), "cost_runs_have_identical_fills": True})
    dates = [b["date"] for b in bars]
    annual_days = 365 if "/" in symbol else 252
    daily_returns = {
        "net": [d["strat_ret"] for d in result.daily],
        "gross": [d["strat_ret"] for d in gross_result.daily],
        "buy_hold": engine.buy_hold_daily(bars),
        "long": [d["long_ret"] for d in result.daily],
        "short": [d["short_ret"] for d in result.daily],
    }
    stats, curves, drawdowns = {}, {}, {}
    for key, returns in daily_returns.items():
        stats[key], curves[key], drawdowns[key] = curve_stats(dates, returns, annual_days)
    assert abs(curves["long"][-1] * curves["short"][-1] - curves["net"][-1]) < 1e-8
    annual = defaultdict(lambda: {k: 1.0 for k in daily_returns})
    for i, day in enumerate(dates):
        for key in daily_returns:
            annual[day[:4]][key] *= 1 + daily_returns[key][i]
    annual = [{"year": year, **{k: v - 1 for k, v in values.items()}} for year, values in annual.items()]
    closed = [t for t in audits if t["exit_date"]]
    side_stats = {}
    for side in ("long", "short"):
        trades = [t for t in closed if t["direction"] == side]
        side_stats[side] = {"closed_trades": len(trades),
                            "win_rate": sum(t["marked_net_return"] > 0 for t in trades) / len(trades) if trades else None,
                            "average_trade": statistics.fmean(t["marked_net_return"] for t in trades) if trades else None}
    summary = {
        "symbol": symbol, "group": group, "start": dates[0], "end": dates[-1], "bars": len(bars),
        "strategy": strategy["key"], "params": params.model_dump(), "stats": stats,
        "closed_trades": len(closed), "open_position": next((t["direction"] for t in audits if not t["exit_date"]), None),
        "win_rate": sum(t["marked_net_return"] > 0 for t in closed) / len(closed) if closed else None,
        "average_hold_bars": statistics.fmean(t["bars_held"] for t in closed) if closed else None,
        "occupied_bar_fraction": sum(d["state"] != 0 for d in result.daily) / len(bars),
        "median_fill_cost_bps": statistics.median(fill_costs) if fill_costs else None,
        "mean_fill_cost_bps": statistics.fmean(fill_costs) if fill_costs else None,
        "cost_drag_pp": 100 * (stats["gross"]["total_return"] - stats["net"]["total_return"]),
        "exit_reasons": dict(Counter(t["exit_reason"] for t in closed)),
        "side_trade_stats": side_stats, "checks": checks,
        "source": "Coinbase Exchange / USD trade candles" if "/" in symbol else "Alpaca / adjusted OHLC",
    }
    daily = [{"symbol": symbol, "date": day, "state": result.daily[i]["state"],
              **{key + "_return": vals[i] for key, vals in daily_returns.items()}}
             for i, day in enumerate(dates)]
    return summary, {"dates": dates, "equity": curves, "drawdown": drawdowns,
                     "annual": annual, "trades": audits}, daily


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "instruments").mkdir(exist_ok=True)
    watchlist = {s for _, symbols in TREND_WATCHLIST_SECTIONS for s in symbols} | {"TLT", "IEF", "ETH/USD"}
    groups = {s: label for label, names in [
        ("Broad-index ETFs", stored_groups.ETF_BROAD), ("Factor ETFs", stored_groups.ETF_FACTOR),
        ("Bond ETFs", stored_groups.ETF_BONDS), ("Sector ETFs", stored_groups.ETF_SECTOR),
        ("Theme ETFs", stored_groups.ETF_THEME), ("Commodity ETFs", stored_groups.ETF_COMMODITY),
        ("Crypto", ["BTC/USD", "ETH/USD"]),
    ] for s in names}
    database = get_settings().resolved_database_path()
    summaries, all_trades, detail_files = [], [], {}
    with ExitStack() as stack:
        conn = stack.enter_context(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        symbols = [r[0] for r in conn.execute(
            "SELECT symbol FROM price_bars UNION SELECT symbol FROM crypto_bars ORDER BY symbol"
        )]
        for symbol in ("BTC/USD", "ETH/USD"):
            sources = {r[0] for r in conn.execute("SELECT DISTINCT source FROM crypto_bars WHERE symbol=?", (symbol,))}
            assert sources == {"coinbase"}, (symbol, sources)
        input_csv = csv.DictWriter(stack.enter_context(gzip.open(OUTPUT / "inputs.csv.gz", "wt", encoding="utf-8", newline="")),
                                   fieldnames=["symbol", "date", "o", "h", "l", "c", "v"])
        daily_csv = csv.DictWriter(stack.enter_context(gzip.open(OUTPUT / "daily.csv.gz", "wt", encoding="utf-8", newline="")),
                                   fieldnames=["symbol", "date", "state", "net_return", "gross_return", "buy_hold_return", "long_return", "short_return"])
        archive = stack.enter_context(ZipFile(OUTPUT / "details.zip", "w", compression=ZIP_DEFLATED))
        input_csv.writeheader()
        daily_csv.writeheader()
        for number, symbol in enumerate(symbols, 1):
            bars, strategy = data.load_ohlc(conn, symbol), repository.resolve_one(conn, symbol)
            summary, detail, daily = analyse(symbol, groups.get(symbol, "Other equities"), bars, strategy)
            summary["watchlist"] = symbol in watchlist
            summaries.append(summary)
            all_trades.extend({"symbol": symbol, **t} for t in detail["trades"])
            input_csv.writerows({"symbol": symbol, **b} for b in bars)
            daily_csv.writerows(daily)
            filename = symbol.replace("/", "_")
            archive.writestr(filename + ".json", json.dumps(detail, allow_nan=False, separators=(",", ":")))
            # Display precision only; the ZIP and CSVs retain full precision.
            for family in ("equity", "drawdown"):
                detail[family] = {k: [round(v, 8) for v in vals] for k, vals in detail[family].items()}
            relative = f"instruments/{filename}.js"
            (OUTPUT / relative).write_text(
                "window.baselineDetails=window.baselineDetails||{};window.baselineDetails["
                + json.dumps(symbol) + "]=" + json.dumps(detail, allow_nan=False, separators=(",", ":")).replace("<", "\\u003c") + ";",
                encoding="utf-8",
            )
            detail_files[symbol] = relative
            if number % 25 == 0 or number == len(symbols):
                print(f"Completed {number}/{len(symbols)} instruments", flush=True)
    write_csv(OUTPUT / "trades.csv", all_trades)
    flat = []
    for s in summaries:
        flat.append({"symbol": s["symbol"], "group": s["group"], "start": s["start"], "end": s["end"],
                     **{key + "_" + metric: s["stats"][key][metric] for key in ("net", "gross", "buy_hold", "long", "short")
                        for metric in ("total_return", "cagr", "max_drawdown")},
                     "closed_trades": s["closed_trades"], "win_rate": s["win_rate"],
                     "median_fill_cost_bps": s["median_fill_cost_bps"], "cost_drag_pp": s["cost_drag_pp"]})
    write_csv(OUTPUT / "summary.csv", flat)
    metadata = {
        "stage": "1 / Current strategy baseline", "generated_utc": datetime.now(timezone.utc).isoformat(),
        "engine_version": ENGINE_VERSION,
        "engine_sha256": hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest(),
        "inputs_sha256": hashlib.sha256((OUTPUT / "inputs.csv.gz").read_bytes()).hexdigest(),
        "universe": "Every symbol with stored equity/ETF or crypto OHLC; no active flag or watchlist restriction",
        "excluded_symbols": [],
        "symbol_count": len(summaries), "closed_trades_checked": sum(s["closed_trades"] for s in summaries),
        "prefix_checks": sum(s["checks"]["prefix_comparisons"] for s in summaries),
        "independent_cash_bars": sum(s["checks"]["independent_cash_bars"] for s in summaries),
        "independent_cash_max_relative_error": max(s["checks"]["independent_cash_max_relative_error"] for s in summaries),
        "cost_status": "Configured assumptions; execution venue, fee tier and short financing not specified",
        "period": "Each instrument's full stored history; cross-instrument periods differ",
        "annualisation": "CAGR from elapsed calendar years; volatility/Sharpe use 252 equity sessions or 365 crypto days; zero cash return",
        "position_model": "One direction at a time; fixed units within a trade; next trade uses full current simulated equity; no portfolio allocation",
        "benchmark": "Buy at first stored close, hold to last close; adjusted equities, raw crypto; before execution costs",
        "direction_views": "Long and short contributions from the SAME two-sided run, not standalone one-direction simulations",
        "not_modelled": ["Borrow fees and availability", "Crypto funding and margin liquidation", "Cash interest", "Taxes", "Market impact"],
    }
    result = {"metadata": metadata, "summary": summaries, "detail_files": detail_files}
    (OUTPUT / "results.json").write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    write_report(result, OUTPUT / "report.html")
    print(json.dumps({"report": str(OUTPUT / "report.html"), "symbols": len(summaries),
                      "positive_net": sum(s["stats"]["net"]["total_return"] > 0 for s in summaries),
                      "beat_buy_hold": sum(s["stats"]["net"]["total_return"] > s["stats"]["buy_hold"]["total_return"] for s in summaries),
                      "smaller_drawdown": sum(s["stats"]["net"]["max_drawdown"] > s["stats"]["buy_hold"]["max_drawdown"] for s in summaries),
                      "closed_trades_checked": metadata["closed_trades_checked"]}), flush=True)


if __name__ == "__main__":
    main()
