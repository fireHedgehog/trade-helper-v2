"""Fixed-unit dollar accounting independent of the engine's return series.

Equity starts at $10,000. Cash plus signed units defines each daily mark.
After nonpositive equity, funded measurement stops at that actual mark;
later hypothetical signals are not funded. No invented liquidation fill.
"""
import math
from datetime import date

STARTING_CASH = 10000.0
COMMON_START = 211


def account(bars, trades, atr, bps=5.0, slippage=.05):
    dates = [b["date"] for b in bars]
    index = {d: i for i, d in enumerate(dates)}
    curve = [STARTING_CASH] * len(bars)
    cash, cursor = STARTING_CASH, 0
    gross_pnl = fees = slip = 0.0
    ledger = []
    exhausted = None
    for tr in trades:
        i = index[tr["entry_date"]]
        j = index[tr["exit_date"]] if tr["exit_date"] else len(bars) - 1
        curve[cursor:i] = [cash] * max(0, i-cursor)
        before = cash
        ep = tr["entry_price"]
        direction = 1 if tr["direction"] == "long" else -1
        units = direction * cash / ep
        entry_fee = abs(units) * ep * bps / 10000
        entry_slip = abs(units) * atr[i-1] * slippage
        position_cash = cash - units * ep - entry_fee - entry_slip
        exit_fee = exit_slip = 0.0
        marked = None
        actual_j = j
        for t in range(i, j + 1):
            is_exit = t == j and tr["exit_date"] is not None
            marked = tr["exit_price"] if is_exit else bars[t]["c"]
            exit_fee = abs(units) * marked * bps / 10000 if is_exit else 0.0
            exit_slip = abs(units) * atr[t-1] * slippage if is_exit else 0.0
            curve[t] = position_cash + units * marked - exit_fee - exit_slip
            if curve[t] <= 0:
                exhausted = dates[t]
                actual_j = t
                break
        cash = curve[actual_j]
        pnl = units * (marked - ep)
        fee = entry_fee + exit_fee
        slip_cost = entry_slip + exit_slip
        gross_pnl += pnl
        fees += fee
        slip += slip_cost
        assert math.isclose(before + pnl - fee - slip_cost, cash, rel_tol=1e-10, abs_tol=1e-7)
        actual_exit = tr["exit_date"] if actual_j == j else None
        ledger.append([tr["direction"], tr["entry_date"], ep, actual_exit, marked,
                       tr["exit_reason"] if actual_exit else "exhaustion_mark" if exhausted else "open_mark",
                       units, before, pnl, fee, slip_cost, cash, dates[actual_j]])
        cursor = actual_j + 1
        if exhausted:
            break
    curve[cursor:] = [cash] * (len(bars)-cursor)
    error = abs(STARTING_CASH + gross_pnl - fees - slip - cash)
    assert error <= 1e-6 * max(1, abs(cash) / STARTING_CASH), error
    return {"curve": curve, "ledger": ledger, "ending": cash, "price_pnl": gross_pnl,
            "fees": fees, "slippage": slip, "identity_error": error, "exhausted": exhausted,
            "unfunded_signals": len(trades) - len(ledger)}


def curve_stats(curve, dates, exhausted):
    value = curve[-1] / STARTING_CASH
    years = (date.fromisoformat(dates[-1])-date.fromisoformat(dates[0])).days/365.25
    peak = STARTING_CASH
    dd = 0.0
    for v in curve:
        peak = max(peak, v)
        dd = min(dd, v/peak-1)
    net = value-1
    cagr = value ** (1/years)-1 if years > 0 and not exhausted else None
    common_days = ((date.fromisoformat(dates[-1])-date.fromisoformat(dates[COMMON_START-1])).days
                   if len(dates)>COMMON_START else 0)
    common_net = common_cagr = common_dd = None
    if common_days and not exhausted:
        base = curve[COMMON_START-1]
        common_net = curve[-1]/base-1
        common_cagr = (1+common_net)**(365.25/common_days)-1
        peak = base
        common_dd = 0.0
        for v in curve[COMMON_START:]:
            peak = max(peak, v)
            common_dd = min(common_dd, v/peak-1)
    return {"net": net, "cagr": cagr, "drawdown": dd, "common_net": common_net,
            "common_cagr": common_cagr, "common_drawdown": common_dd, "common_days": common_days}
