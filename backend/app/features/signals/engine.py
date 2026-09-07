"""Daily Donchian simulation: close signals, scheduled fills, and resting stops.

A close-derived trailing stop becomes effective next session. Each trade uses
fixed units at entry; its marked value, fill costs and daily equity reconcile.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.features.signals import indicators as ind
from app.features.signals.params import SignalParams

_DIR_NAME = {1: "long", -1: "short"}


@dataclass
class EngineResult:
    trades: list[dict] = field(default_factory=list)
    daily: list[dict] = field(default_factory=list)
    overlays: dict = field(default_factory=dict)
    pending_action: dict | None = None
    directions: dict[str, EngineResult] = field(default_factory=dict)


def run(bars: list[dict], params: SignalParams, *, start: int = 0) -> EngineResult:
    n = len(bars)
    dates = [b["date"] for b in bars]
    o = [float(b["o"]) for b in bars]
    h = [float(b["h"]) for b in bars]
    low = [float(b["l"]) for b in bars]
    c = [float(b["c"]) for b in bars]
    if not n:
        return EngineResult(overlays={"dates": [], "donchian_up": [], "donchian_dn": [], "stop_line": []})
    atr = ind.wilder_atr(h, low, c, params.atr_len)
    dc_up_e, dc_dn_e = ind.donchian(h, low, params.entry_len)
    dc_up_x, dc_dn_x = ind.donchian(h, low, params.exit_len)
    ma_reg = ind.sma(c, params.ma_regime) if params.use_ma_regime else [None] * n
    stops: list[float | None] = [None] * n
    overlays = {"dates": dates, "donchian_up": dc_up_e, "donchian_dn": dc_dn_e,
                "stop_line": stops, "atr": atr}
    trades: list[dict] = []
    ledger: list[dict] = []
    pos: dict | None = None
    pending: dict | None = None

    def allowed(d: int) -> bool:
        return params.allow_long if d == 1 else params.allow_short

    def cost(price: float, a: float) -> float:
        # Cost per unit: bps on the fill notional plus absolute ATR slippage.
        return price * params.cost_bps / 1e4 + params.slippage_atr * a

    def open_position(d: int, t: int, price: float, signal_i: int) -> None:
        nonlocal pos
        a = atr[signal_i] or 0.0
        stop = price - d * params.atr_stop_mult * a if params.initial_enabled else None
        pos = {"direction": d, "fill_i": t, "entry_price": price, "entry_atr": a,
               "initial_stop": stop, "stop": stop, "hh": price, "ll": price,
               "mae": 0.0, "mfe": 0.0, "entry_cost": cost(price, a) / price}

    def close_position(t: int, price: float, reason: str | None, known_atr: float) -> None:
        nonlocal pos
        assert pos is not None
        d, entry = pos["direction"], pos["entry_price"]
        exit_cost = cost(price, known_atr) / entry if reason else 0.0
        ret = d * (price / entry - 1) - pos["entry_cost"] - exit_cost
        risk = abs(entry - pos["initial_stop"]) / entry if pos["initial_stop"] is not None else 0.0
        a = pos["entry_atr"]
        trades.append({
            "direction": _DIR_NAME[d], "entry_date": dates[pos["fill_i"]],
            "entry_price": entry, "exit_date": dates[t] if reason else None,
            "exit_price": price if reason else None, "exit_reason": reason,
            "bars_held": t - pos["fill_i"], "return_pct": ret if reason else None,
            "return_r": ret / risk if reason and risk > 0 else None,
            "mae_atr": abs(pos["mae"]) / a if a else None,
            "mfe_atr": pos["mfe"] / a if a else None,
            "initial_stop": pos["initial_stop"],
        })
        ledger.append({**pos, "exit_i": t, "exit_price": price,
                       "exit_cost": exit_cost})
        pos = None

    for t in range(n):
        prior_atr = (atr[t - 1] or 0.0) if t else 0.0
        exited = False
        # Orders confirmed at the previous close execute before this bar's range.
        if pending is not None:
            order, pending = pending, None
            if order["action"] in ("exit", "reverse"):
                close_position(t, o[t], "channel_reversal", prior_atr)
                exited = True
            if order["action"] in ("enter", "reverse"):
                open_position(order["direction"], t, o[t], order["signal_i"])

        if pos is not None:
            d = pos["direction"]
            active_stop = pos["stop"]
            hit = active_stop is not None and (low[t] <= active_stop if d == 1 else h[t] >= active_stop)
            if hit:
                price = min(o[t], active_stop) if d == 1 else max(o[t], active_stop)
                # Daily bars do not establish the favorable excursion before a stop.
                excursion = d * (price - pos["entry_price"])
                pos["mae"] = min(pos["mae"], excursion)
                pos["mfe"] = max(pos["mfe"], excursion)
                reason = "stop_initial" if active_stop == pos["initial_stop"] else "stop_trailing"
                stops[t] = active_stop
                close_position(t, price, reason, prior_atr)
                exited = True
            else:
                pos["hh"] = max(pos["hh"], h[t])
                pos["ll"] = min(pos["ll"], low[t])
                adverse = low[t] - pos["entry_price"] if d == 1 else pos["entry_price"] - h[t]
                favorable = h[t] - pos["entry_price"] if d == 1 else pos["entry_price"] - low[t]
                pos["mae"] = min(pos["mae"], adverse)
                pos["mfe"] = max(pos["mfe"], favorable)

        if t < max(start, params.warmup()) or atr[t] is None or dc_up_e[t] is None:
            continue

        if pos is not None:
            d = pos["direction"]
            channel_exit = (d == 1 and dc_dn_x[t] is not None and c[t] < dc_dn_x[t]) or (
                d == -1 and dc_up_x[t] is not None and c[t] > dc_up_x[t])
            if params.channel_enabled and channel_exit:
                reverse = params.stop_and_reverse and allowed(-d)
                if params.fill_at == "close":
                    close_position(t, c[t], "channel_reversal", atr[t])
                    if reverse:
                        open_position(-d, t, c[t], t)
                else:
                    pending = {"action": "reverse" if reverse else "exit",
                               "direction": -d if reverse else d, "signal_i": t,
                               "reason": "channel_reversal"}
        elif not exited or params.fill_at == "open_next":
            # A stop prevents another fill today, but today's closing breakout
            # can still confirm an order for the following session.
            d = 1 if c[t] > dc_up_e[t] else (-1 if c[t] < dc_dn_e[t] else 0)
            if d and params.use_ma_regime and ma_reg[t] is not None:
                if (d == 1 and c[t] <= ma_reg[t]) or (d == -1 and c[t] >= ma_reg[t]):
                    d = 0
            if d and allowed(d):
                if params.fill_at == "close":
                    open_position(d, t, c[t], t)
                else:
                    pending = {"action": "enter", "direction": d, "signal_i": t,
                               "reason": "breakout"}

        if pos is not None and params.trailing_enabled:
            # Revise after the close; never test this revised stop on today's range.
            d, a = pos["direction"], atr[t]
            if params.trail_mode == "chandelier":
                trail = pos["hh"] - params.chandelier_k * a if d == 1 else pos["ll"] + params.chandelier_k * a
            elif params.trail_mode == "atr_trail":
                trail = c[t] - params.atr_trail_k * a if d == 1 else c[t] + params.atr_trail_k * a
            else:
                # Tomorrow's channel includes the just-completed bar.
                trail = min(low[max(0, t - params.exit_len + 1):t + 1]) if d == 1 else max(h[max(0, t - params.exit_len + 1):t + 1])
            pos["stop"] = trail if pos["stop"] is None else max(pos["stop"], trail) if d == 1 else min(pos["stop"], trail)
        if pos is not None:
            stops[t] = pos["stop"]

    if pos is not None:
        close_position(n - 1, c[-1], None, 0.0)

    # Fixed entry units: mark each trade net of its fill costs. Ratios between
    # successive marks telescope to the exact trade return, also for shorts.
    side_factors = {1: [1.0] * n, -1: [1.0] * n}
    exposure = [0] * n
    for tr in ledger:
        previous = 1.0
        d, entry = tr["direction"], tr["entry_price"]
        for t in range(tr["fill_i"], tr["exit_i"] + 1):
            last = t == tr["exit_i"]
            mark = tr["exit_price"] if last else c[t]
            value = 1 + d * (mark / entry - 1) - tr["entry_cost"]
            if last:
                value -= tr["exit_cost"]
            factor = value / previous if previous > 0 else 1.0
            side_factors[d][t] *= factor
            previous = value
            exposure[t] = d
    daily = [{"date": dates[t], "state": exposure[t],
              "long_ret": side_factors[1][t] - 1,
              "short_ret": side_factors[-1][t] - 1,
              "strat_ret": side_factors[1][t] * side_factors[-1][t] - 1}
             for t in range(n)]
    action = ({"action": pending["action"], "direction": _DIR_NAME[pending["direction"]],
               "signal_date": dates[pending["signal_i"]], "fill_at": "open_next",
               "reason": pending["reason"]} if pending else None)
    return EngineResult(trades=trades, daily=daily, overlays=overlays, pending_action=action)


def run_pair(bars: list[dict], long_params: SignalParams) -> EngineResult:
    """Independent long strategy and fixed short benchmark; equal initial books."""
    from app.features.signals.params import SHORT_PARAMS

    start = max(65, long_params.warmup(), SHORT_PARAMS.warmup())
    long = run(bars, long_params.model_copy(update={"allow_long": True, "allow_short": False}), start=start)
    short = run(bars, SHORT_PARAMS, start=start)
    long_equity = short_equity = previous = 1.0
    daily = []
    for l, s in zip(long.daily, short.daily):
        long_equity *= 1 + l["strat_ret"]
        short_equity *= 1 + s["strat_ret"]
        combined = (long_equity + short_equity) / 2
        daily.append({"date": l["date"], "state": 2 if l["state"] and s["state"] else l["state"] or s["state"],
                      "long_active": bool(l["state"]), "short_active": bool(s["state"]),
                      "long_ret": l["strat_ret"], "short_ret": s["strat_ret"],
                      "strat_ret": combined / previous - 1 if previous > 0 else 0.0})
        previous = combined
    trades = sorted(long.trades + short.trades, key=lambda t: (t["entry_date"], t["direction"]))
    return EngineResult(trades=trades, daily=daily, overlays=long.overlays,
                        pending_action=long.pending_action or short.pending_action,
                        directions={"long": long, "short": short})


def buy_hold_daily(bars: list[dict]) -> list[float]:
    c = [float(b["c"]) for b in bars]
    return [0.0] + [c[t] / c[t - 1] - 1.0 for t in range(1, len(c))]


def compound(returns: list[float]) -> list[float]:
    eq = 1.0
    out = []
    for r in returns:
        eq *= (1.0 + r)
        out.append(eq)
    return out


def drawdown_curve(equity: list[float]) -> list[float]:
    peak = -math.inf
    out = []
    for e in equity:
        peak = max(peak, e)
        out.append(e / peak - 1.0 if peak > 0 else 0.0)
    return out
