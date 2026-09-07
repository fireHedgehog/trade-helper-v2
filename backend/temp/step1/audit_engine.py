"""Independent daily cash/units simulation of the stored Step 1 parameters.

No production indicators, trades or returns are used to build the reference.
Run before regenerating baseline.py to retain the measured change in results.
"""
import json
import math
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
from app.core.config import get_settings
from app.features.signals import data, engine
from app.features.signals.params import SignalParams

OUTPUT = BACKEND.parent / "docs/temp/step1"


def reference(bars, p):
    # The stored presets use next-open fills, with no automatic reversal.
    assert p.fill_at == "open_next" and not p.stop_and_reverse
    cash, units, capital = 1.0, 0.0, 1.0
    position = order = None
    equity, trades, ranges, atrs = [], [], [], []
    exhausted = None
    for i, bar in enumerate(bars):
        op, hi, lo, close = (bar[k] for k in ("o", "h", "l", "c"))
        prev_close = bars[i - 1]["c"] if i else close
        ranges.append(max(hi - lo, abs(hi - prev_close), abs(lo - prev_close)))
        a = None
        if i == p.atr_len - 1:
            a = sum(ranges) / p.atr_len
        elif i >= p.atr_len:
            a = (atrs[-1] * (p.atr_len - 1) + ranges[-1]) / p.atr_len
        atrs.append(a)
        prior_a = atrs[i - 1] if i else None

        def fee(price, known_atr):
            return abs(units) * (price * p.cost_bps / 10000 + known_atr * p.slippage_atr)

        def sell_out(price, reason):
            nonlocal cash, units, position
            cash += units * price - fee(price, prior_a)
            trades.append({"direction": "long" if units > 0 else "short",
                           "entry_date": position["date"], "entry_price": position["price"],
                           "exit_date": bar["date"], "exit_price": price,
                           "return_pct": cash / capital - 1, "exit_reason": reason})
            units, position = 0.0, None

        if order:
            if order == "exit":
                sell_out(op, "channel_reversal")
            else:
                capital = cash
                units = order * capital / op
                cash -= units * op + fee(op, prior_a)
                initial = op - order * p.atr_stop_mult * prior_a
                position = {"date": bar["date"], "price": op, "side": order,
                            "stop": initial, "initial": initial, "high": op, "low": op}
            order = None

        if position:
            side, stop = position["side"], position["stop"]
            if (side == 1 and lo <= stop) or (side == -1 and hi >= stop):
                fill = min(op, stop) if side == 1 else max(op, stop)
                sell_out(fill, "stop_initial" if stop == position["initial"] else "stop_trailing")
            else:
                position["high"] = max(position["high"], hi)
                position["low"] = min(position["low"], lo)

        value = cash + units * close
        equity.append(value)
        if value <= 0:
            exhausted = bar["date"]
            break  # A funded account cannot start another trade after exhaustion.
        if i < p.warmup():
            continue
        prior = bars[i - p.entry_len:i]
        if not position:
            side = 1 if close > max(b["h"] for b in prior) else -1 if close < min(b["l"] for b in prior) else 0
            if p.use_ma_regime:
                ma = sum(b["c"] for b in bars[i + 1 - p.ma_regime:i + 1]) / p.ma_regime
                if (side == 1 and close <= ma) or (side == -1 and close >= ma):
                    side = 0
            if (side == 1 and p.allow_long) or (side == -1 and p.allow_short):
                order = side
        else:
            side = position["side"]
            prior_exit = bars[i - p.exit_len:i]
            if (side == 1 and close < min(b["l"] for b in prior_exit)) or (side == -1 and close > max(b["h"] for b in prior_exit)):
                order = "exit"
            if p.trail_mode == "chandelier":
                trail = position["high"] - p.chandelier_k * a if side == 1 else position["low"] + p.chandelier_k * a
            elif p.trail_mode == "atr_trail":
                trail = close - side * p.atr_trail_k * a
            else:
                window = bars[i + 1 - p.exit_len:i + 1]
                trail = min(b["l"] for b in window) if side == 1 else max(b["h"] for b in window)
            position["stop"] = max(position["stop"], trail) if side == 1 else min(position["stop"], trail)
    return equity, trades, exhausted


def main():
    old = json.loads((OUTPUT / "results.json").read_text(encoding="utf-8"))
    results = []
    conn = sqlite3.connect(get_settings().resolved_database_path().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("BEGIN")
    for n, row in enumerate(old["summary"], 1):
        symbol, p = row["symbol"], SignalParams(**row["params"])
        bars = data.load_ohlc(conn, symbol)
        actual = engine.run(bars, p)
        expected, trades, exhausted = reference(bars, p)
        curve = engine.compound([d["strat_ret"] for d in actual.daily])
        error = max(abs(a - b) / max(1, abs(b)) for a, b in zip(curve, expected))
        assert error < 1e-9, (symbol, "cash equity", error)
        actual_closed = [t for t in actual.trades if t["exit_date"] and t["exit_date"] <= bars[len(expected) - 1]["date"]]
        assert len(actual_closed) == len(trades), (symbol, "trade count")
        for a, b in zip(actual_closed, trades):
            for key in b:
                if isinstance(b[key], float):
                    assert math.isclose(a[key], b[key], rel_tol=1e-9, abs_tol=1e-9), (symbol, key, a, b)
                else:
                    assert a[key] == b[key], (symbol, key, a, b)
        net = curve[-1] - 1
        results.append({"symbol": symbol, "previous_net": row["stats"]["net"]["total_return"],
                        "net": net, "long": math.prod(1+d["long_ret"] for d in actual.daily)-1,
                        "short": math.prod(1+d["short_ret"] for d in actual.daily)-1,
                        "bars_checked": len(expected), "closed_trades_checked": len(trades),
                        "max_relative_cash_equity_error": error, "cash_exhausted": exhausted})
        if n % 100 == 0:
            print(f"Independent cash/units audit: {n}/{len(old['summary'])}", flush=True)
    conn.close()
    summary = {"symbols": len(results), "bars_checked": sum(r["bars_checked"] for r in results),
               "closed_trades_checked": sum(r["closed_trades_checked"] for r in results),
               "previous_positive_net": sum(r["previous_net"] > 0 for r in results),
               "positive_net": sum(r["net"] > 0 for r in results),
               "positive_long_contribution": sum(r["long"] > 0 for r in results),
               "positive_short_contribution": sum(r["short"] > 0 for r in results),
               "changed_symbols": sum(abs(r["net"] - r["previous_net"]) > 1e-9 for r in results),
               "max_relative_cash_equity_error": max(r["max_relative_cash_equity_error"] for r in results),
               "scope": "Independent indicators, signals, fills and signed cash/units ledger; stops at cash exhaustion",
               "symbols_exhausting_cash": [r["symbol"] for r in results if r["cash_exhausted"]]}
    (OUTPUT / "engine-audit.json").write_text(json.dumps({"summary": summary, "instruments": results}, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)
    for r in results:
        if r["symbol"] in ("SPY", "QQQ", "BTC/USD", "ETH/USD", "TLT"):
            print(json.dumps(r), flush=True)


if __name__ == "__main__":
    main()
