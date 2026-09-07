"""Step 2: full-universe entry/exit grid using the unchanged production engine.

Run from the repository root:
  backend/.venv/Scripts/python.exe backend/temp/step2/experiment.py
  backend/.venv/Scripts/python.exe backend/temp/step2/report.py
Inputs are the frozen Step 1 prices. No database writes or provider calls.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from datetime import date, datetime, timezone
from itertools import groupby
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "temp/step1"))
from app.features.signals import engine, indicators
from app.features.signals.params import ENGINE_VERSION, SignalParams
from app.features.signals.watchlist import TREND_WATCHLIST
from app.features.data_management.universe import ETF_BONDS, EQ_MEGA
from audit_engine import reference

OUTPUT = ROOT / "docs/temp/step2"
STEP1 = ROOT / "docs/temp/step1"
ENTRIES = [10, 20, 55, 100, 200]
EXITS = [10, 20, 55, 100]
MODES = ["both", "long", "short"]
# Day 210 confirms the first possible signal for the longest lookback.
# Index 211 is its first possible next-open fill; returns thereafter have
# the same observation window for every candidate within an instrument.
COMMON_START = 211
AUDIT_SYMBOLS = {"BTC/USD", "ETH/USD", "SPY", "QQQ", "TLT", "NVDA", "ECHO"}
FIELDS = ["entry", "exit", "mode", "net", "cagr", "drawdown", "gross", "trades",
          "win_rate", "exposure", "long_contribution", "short_contribution",
          "common_net", "common_cagr", "common_drawdown", "common_trades",
          "exhausted", "channel_exits", "initial_exits", "trailing_exits", "common_days"]


def stats(returns, years):
    value = peak = 1.0
    worst = 0.0
    exhausted = False
    for r in returns:
        value *= 1 + r
        exhausted = exhausted or value <= 0
        peak = max(peak, value)
        worst = min(worst, value / peak - 1)
    return value - 1, value ** (1 / years) - 1 if years > 0 and not exhausted else None, worst, exhausted


def simulate(task):
    baseline, bars = task
    symbol = baseline["symbol"]
    dates = [b["date"] for b in bars]
    index = {day: i for i, day in enumerate(dates)}
    years = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days / 365.25
    common_days = ((date.fromisoformat(dates[-1]) - date.fromisoformat(dates[COMMON_START - 1])).days
                   if len(bars) > COMMON_START else 0)
    atr = indicators.wilder_atr([b["h"] for b in bars], [b["l"] for b in bars], [b["c"] for b in bars], 20)
    # Weekly chart sampling only; every metric and raw trade keeps full precision.
    sample = sorted({0, len(bars) - 1, *range(4, len(bars), 5)})
    summaries, variants = [], {}
    ledgers = {mode: io.StringIO(newline="") for mode in MODES}
    writers = {mode: csv.writer(ledgers[mode]) for mode in MODES}
    checked_bars = 0
    max_cash_error = max_ledger_error = 0.0
    bridge_error = None
    base_params = baseline["params"]
    for entry in ENTRIES:
        for exit_len in EXITS:
            for mode in MODES:
                p = SignalParams(**{**base_params, "entry_len": entry, "exit_len": exit_len,
                                    "allow_long": mode != "short", "allow_short": mode != "long"})
                result = engine.run(bars, p)
                returns = [d["strat_ret"] for d in result.daily]
                equity = engine.compound(returns)
                net, cagr, dd, exhausted = stats(returns, years)
                common = stats(returns[COMMON_START:], common_days / 365.25) if common_days else (None, None, None, False)
                # No annualised return is reported after exhaustion, even if
                # subsequent algebraic returns appear profitable.
                if exhausted:
                    common = (common[0], None, common[2], True)
                terminal = gross_terminal = 1.0
                trade_rows = []
                closed = [t for t in result.trades if t["exit_date"]]
                for tr in result.trades:
                    i = index[tr["entry_date"]]
                    d = 1 if tr["direction"] == "long" else -1
                    ep = tr["entry_price"]
                    xp = tr["exit_price"] if tr["exit_date"] else bars[-1]["c"]
                    ec = p.cost_bps / 10000 + p.slippage_atr * atr[i - 1] / ep
                    xc = ((xp * p.cost_bps / 10000 + p.slippage_atr * atr[index[tr["exit_date"]] - 1]) / ep
                          if tr["exit_date"] else 0.0)
                    gross = d * (xp / ep - 1)
                    net_trade = gross - ec - xc
                    if tr["exit_date"]:
                        assert abs(tr["return_pct"] - net_trade) < 1e-10
                    terminal *= 1 + net_trade
                    gross_terminal *= 1 + gross
                    row = [tr["direction"], tr["entry_date"], ep, tr["exit_date"],
                           tr["exit_price"], tr["exit_reason"], gross, ec, xc, net_trade]
                    trade_rows.append(row)
                    writers[mode].writerow([symbol, entry, exit_len, *row])
                # Reconcile until account exhaustion; continuation thereafter is
                # flagged and retained for signal research, with a ranking penalty.
                ledger_error = abs(terminal - equity[-1]) / max(1, abs(terminal))
                if not exhausted:
                    assert ledger_error < 1e-8, (symbol, entry, exit_len, mode, ledger_error)
                    max_ledger_error = max(max_ledger_error, ledger_error)
                if symbol in AUDIT_SYMBOLS:
                    cash_equity, _, _ = reference(bars, p)
                    err = max(abs(a - b) / max(1, abs(b)) for a, b in zip(equity, cash_equity))
                    assert err < 1e-9, (symbol, entry, exit_len, mode, "cash audit", err)
                    checked_bars += len(cash_equity)
                    max_cash_error = max(max_cash_error, err)
                if mode == "both" and entry == base_params["entry_len"] and exit_len == base_params["exit_len"]:
                    bridge_error = abs(net - baseline["stats"]["net"]["total_return"])
                    assert bridge_error < 1e-9, (symbol, "Step 1 bridge", bridge_error)
                long_ret = math.prod(1 + d["long_ret"] for d in result.daily) - 1
                short_ret = math.prod(1 + d["short_ret"] for d in result.daily) - 1
                reasons = Counter(t["exit_reason"] for t in closed)
                values = [entry, exit_len, mode, net, cagr, dd, gross_terminal - 1, len(closed),
                          sum(t["return_pct"] > 0 for t in closed) / len(closed) if closed else None,
                          sum(d["state"] != 0 for d in result.daily) / len(bars), long_ret, short_ret,
                          common[0], common[1], common[2],
                          sum(index[t["exit_date"]] >= COMMON_START for t in closed),
                          exhausted, reasons["channel_reversal"], reasons["stop_initial"], reasons["stop_trailing"], common_days]
                summaries.append(values)
                key = f"{entry}-{exit_len}-{mode}"
                variants[key] = {"equity": [round(equity[i], 8) for i in sample], "trades": trade_rows}
                if mode == "both":
                    for side in ("long", "short"):
                        curve = engine.compound([d[side + "_ret"] for d in result.daily])
                        variants[key][side] = [round(curve[i], 8) for i in sample]
    assert len(summaries) == 60 and bridge_error is not None
    detail = {"symbol": symbol, "dates": [dates[i] for i in sample], "variants": variants,
              "buy_hold": [round(bars[i]["c"] / bars[0]["c"], 8) for i in sample]}
    file = symbol.replace("/", "_") + ".js"
    (OUTPUT / "instruments" / file).write_text(
        "window.step2Details=window.step2Details||{};window.step2Details[" + json.dumps(symbol) + "]="
        + json.dumps(detail, allow_nan=False, separators=(",", ":")).replace("<", "\\u003c") + ";", encoding="utf-8")
    return {"symbol": symbol, "rows": summaries, "detail_file": "instruments/" + file,
            "bars": len(bars), "start": dates[0], "end": dates[-1],
            "common_start": dates[COMMON_START] if len(bars) > COMMON_START else None,
            "baseline_entry": base_params["entry_len"], "baseline_exit": base_params["exit_len"],
            "audit": {"cash_bars": checked_bars, "cash_error": max_cash_error,
                      "ledger_error": max_ledger_error, "step1_error": bridge_error},
            "ledger_csv": {mode: ledgers[mode].getvalue() for mode in MODES}}


def tasks(baselines, subset=None):
    with gzip.open(STEP1 / "inputs.csv.gz", "rt", encoding="utf-8", newline="") as f:
        for symbol, rows in groupby(csv.DictReader(f), key=lambda r: r["symbol"]):
            bars = [{k: float(v) if k in ("o", "h", "l", "c", "v") else v
                     for k, v in r.items() if k != "symbol"} for r in rows]
            if subset is None or symbol in subset:
                yield baselines[symbol], bars


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", help="Comma-separated smoke-check subset; omit for full universe")
    parser.add_argument("--workers", type=int, default=min(6, max(1, (os.cpu_count() or 2) - 2)))
    args = parser.parse_args()
    start = time.monotonic()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "instruments").mkdir(exist_ok=True)
    baseline = json.loads((STEP1 / "results.json").read_text(encoding="utf-8"))
    assert ENGINE_VERSION == baseline["metadata"]["engine_version"]
    assert hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest() == baseline["metadata"]["engine_sha256"]
    assert hashlib.sha256((STEP1 / "inputs.csv.gz").read_bytes()).hexdigest() == baseline["metadata"]["inputs_sha256"]
    by_symbol = {r["symbol"]: r for r in baseline["summary"]}
    fixed = lambda row: {k: v for k, v in row["params"].items()
                         if k not in ("entry_len", "exit_len", "allow_long", "allow_short")}
    assert all(fixed(row) == fixed(baseline["summary"][0]) for row in baseline["summary"]), "Step 2 requires identical non-grid rules"
    subset = set(args.symbols.split(",")) if args.symbols else None
    priority = set(TREND_WATCHLIST) | set(ETF_BONDS) | set(EQ_MEGA) | {"ETH/USD"}
    groups = {s: ("Bonds" if s in ETF_BONDS else "Major companies" if s in EQ_MEGA
                  else "Watchlist" if s in priority else "Other instruments") for s in by_symbol}
    streams = {m: gzip.open(OUTPUT / f"trades-{m}.csv.gz", "wt", encoding="utf-8", newline="") for m in MODES}
    for f in streams.values():
        csv.writer(f).writerow(["symbol", "entry_len", "exit_len", "direction", "entry_date", "entry_price",
                               "exit_date", "exit_price", "reason", "gross_return", "entry_cost", "exit_cost", "net_return"])
    output = []
    iterator = iter(tasks(by_symbol, subset))
    total = len(subset) if subset else len(by_symbol)
    try:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            pending = set()
            for _ in range(args.workers * 2):
                task = next(iterator, None)
                if task is not None:
                    pending.add(pool.submit(simulate, task))
            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    item = future.result()
                    for mode, content in item.pop("ledger_csv").items():
                        streams[mode].write(content)
                    item["priority"] = item["symbol"] in priority
                    item["group"] = groups[item["symbol"]]
                    output.append(item)
                    task = next(iterator, None)
                    if task is not None:
                        pending.add(pool.submit(simulate, task))
                    if len(output) % 20 == 0 or len(output) == total:
                        print(f"Step 2: {len(output)}/{total} instruments, {len(output)*60:,} simulations, {time.monotonic()-start:.0f}s", flush=True)
    finally:
        for f in streams.values():
            f.close()
    output.sort(key=lambda r: r["symbol"])
    assert len(output) == total
    metadata = {"stage": "2 / Entry x exit speed", "generated_utc": datetime.now(timezone.utc).isoformat(),
                "engine_version": ENGINE_VERSION, "engine_sha256": baseline["metadata"]["engine_sha256"],
                "inputs_sha256": baseline["metadata"]["inputs_sha256"], "inputs": "../step1/inputs.csv.gz",
                "symbol_count": total, "simulation_count": total * 60, "entries": ENTRIES, "exits": EXITS,
                "modes": MODES, "fields": FIELDS, "priority_symbols": sorted(priority & set(by_symbol)),
                "priority_definition": "Existing Trend watchlist + all ETF_BONDS + EQ_MEGA + ETH/USD; fixed before results",
                "ranking": "Median per-instrument CAGR in common post-warmup window; fixed universe with at least 2 calendar years in that window; exhausted accounts receive -100% for ranking only; fewer than 5 closed trades flagged, never excluded",
                "common_window": "Returns from bar index 211 through last bar; same dates across candidates per instrument, existing positions retained, periods differ across instruments",
                "fixed_rules": {k: v for k, v in baseline["summary"][0]["params"].items() if k not in ("entry_len", "exit_len", "allow_long", "allow_short")},
                "direction_views": "Long-only and short-only are independent runs; combined contributions filter the both-directions run",
                "evaluation": "In-sample exploration, no held-out claim or automatic production selection; native warmup preserved",
                "chart_sampling": "Every fifth observation plus first/last; metrics use every daily observation; raw trade ledgers retain full precision",
                "costs": baseline["metadata"]["cost_status"], "cash_audit_symbols": sorted(AUDIT_SYMBOLS),
                "cash_audit_bars": sum(r["audit"]["cash_bars"] for r in output),
                "cash_max_error": max(r["audit"]["cash_error"] for r in output),
                "ledger_max_error": max(r["audit"]["ledger_error"] for r in output),
                "step1_max_error": max(r["audit"]["step1_error"] for r in output),
                "elapsed_seconds": round(time.monotonic()-start, 1), "partial": subset is not None}
    result = {"metadata": metadata, "instruments": output}
    (OUTPUT / "results.json").write_text(json.dumps(result, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    with gzip.open(OUTPUT / "summary.csv.gz", "wt", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "priority", "group", "start", "end", "common_start", *FIELDS])
        for s in output:
            writer.writerows([s["symbol"], s["priority"], s["group"], s["start"], s["end"], s["common_start"], *r] for r in s["rows"])
    print(json.dumps(metadata), flush=True)


if __name__ == "__main__":
    main()
