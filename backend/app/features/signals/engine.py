"""Donchian-channel trend engine (docs/draft-design/04-trend-page.md §R2.1-§R4).

Two-sided. Signal decided on the close of bar `t`, filled at `fill_at`
(default next open). Stop stack, evaluated every bar while open, first hit
wins: initial disaster stop (`entry ∓ atr_stop_mult × ATR_entry`) → monotonic
trailing stop (`trail_mode`) → model exit (exit-channel breach) → end of data
(still-open, no exit row).

Deterministic: same `bars` + `params` + `ENGINE_VERSION` → identical output.
Pure Python, no numpy — matches `multisectional/ranking.py`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.features.signals import indicators as ind
from app.features.signals.params import SignalParams

_DIR_NAME = {1: "long", -1: "short"}


@dataclass
class EngineResult:
    trades: list[dict] = field(default_factory=list)   # closed + one open (exit_* = None)
    daily: list[dict] = field(default_factory=list)     # {date, state (-1/0/1), strat_ret}
    overlays: dict = field(default_factory=dict)        # {dates, donchian_up, donchian_dn, stop_line}


def run(bars: list[dict], params: SignalParams) -> EngineResult:
    n = len(bars)
    dates = [b["date"] for b in bars]
    o = [float(b["o"]) for b in bars]
    h = [float(b["h"]) for b in bars]
    low = [float(b["l"]) for b in bars]
    c = [float(b["c"]) for b in bars]

    overlays = {"dates": dates, "donchian_up": [None] * n, "donchian_dn": [None] * n,
                "stop_line": [None] * n}
    warmup = params.warmup()
    if n <= warmup + 2:
        return EngineResult(overlays=overlays)

    atr = ind.wilder_atr(h, low, c, params.atr_len)
    dc_up_e, dc_dn_e = ind.donchian(h, low, params.entry_len)
    dc_up_x, dc_dn_x = ind.donchian(h, low, params.exit_len)
    ma_reg = ind.sma(c, params.ma_regime) if params.use_ma_regime else [None] * n
    overlays["donchian_up"] = dc_up_e
    overlays["donchian_dn"] = dc_dn_e

    exposure = [0] * n          # signed position held *during* bar t
    stop_series: list[float | None] = [None] * n
    trades: list[dict] = []

    pos: dict | None = None

    def per_side_cost(price: float, a: float | None) -> float:
        slip = (params.slippage_atr * a / price) if a and price else 0.0
        return params.cost_bps / 1e4 + slip

    def fill(t: int) -> tuple[int, float] | None:
        """(index, raw price) of the fill for a signal on the close of t."""
        if params.fill_at == "close":
            return t, c[t]
        return (t + 1, o[t + 1]) if t + 1 < n else None

    def open_position(direction: int, sig_t: int) -> None:
        nonlocal pos
        f = fill(sig_t)
        if f is None:
            return
        fi, fp = f
        a = atr[sig_t] or 0.0
        init_stop = fp - direction * params.atr_stop_mult * a
        pos = {
            "direction": direction, "sig_t": sig_t, "fill_i": fi, "entry_price": fp,
            "entry_atr": a, "initial_stop": init_stop, "stop": init_stop,
            "hh": h[fi], "ll": low[fi], "mae": 0.0, "mfe": 0.0,
            "entry_cost": per_side_cost(fp, a),
        }

    def close_position(exit_i: int, exit_price: float, reason: str | None) -> None:
        nonlocal pos
        assert pos is not None
        d = pos["direction"]
        a = pos["entry_atr"] or None
        exit_cost = per_side_cost(exit_price, atr[min(exit_i, n - 1)]) if reason else 0.0
        gross = d * (exit_price / pos["entry_price"] - 1.0)
        ret_pct = gross - pos["entry_cost"] - exit_cost
        risk_frac = abs(pos["entry_price"] - pos["initial_stop"]) / pos["entry_price"]
        ret_r = ret_pct / risk_frac if risk_frac > 0 else None
        trades.append({
            "direction": _DIR_NAME[d],
            "entry_date": dates[pos["fill_i"]], "entry_price": pos["entry_price"],
            "exit_date": dates[exit_i] if reason else None,
            "exit_price": exit_price if reason else None,
            "exit_reason": reason,
            "bars_held": (exit_i - pos["fill_i"]) if reason else (n - 1 - pos["fill_i"]),
            "return_pct": ret_pct if reason else None,
            "return_r": ret_r if reason else None,
            "mae_atr": abs(pos["mae"]) / a if a else None,
            "mfe_atr": pos["mfe"] / a if a else None,
            "initial_stop": pos["initial_stop"],
        })
        pos = None

    for t in range(warmup, n):
        if atr[t] is None or dc_up_e[t] is None:
            continue

        if pos is None:
            long_sig = c[t] > dc_up_e[t]
            short_sig = c[t] < dc_dn_e[t]
            if params.use_ma_regime and ma_reg[t] is not None:
                long_sig = long_sig and c[t] > ma_reg[t]
                short_sig = short_sig and c[t] < ma_reg[t]
            direction = 1 if long_sig else (-1 if short_sig else 0)
            if direction == 1 and not params.allow_long:
                direction = 0
            elif direction == -1 and not params.allow_short:
                direction = 0
            if direction != 0:
                open_position(direction, t)
            continue

        d = pos["direction"]
        pos["hh"] = max(pos["hh"], h[t])
        pos["ll"] = min(pos["ll"], low[t])
        if d == 1:
            pos["mae"] = min(pos["mae"], low[t] - pos["entry_price"])
            pos["mfe"] = max(pos["mfe"], h[t] - pos["entry_price"])
        else:
            pos["mae"] = min(pos["mae"], pos["entry_price"] - h[t])
            pos["mfe"] = max(pos["mfe"], pos["entry_price"] - low[t])

        # trailing stop candidate for bar t
        a = atr[t] or 0.0
        if params.trail_mode == "chandelier":
            trail = (pos["hh"] - params.chandelier_k * a) if d == 1 else (pos["ll"] + params.chandelier_k * a)
        elif params.trail_mode == "atr_trail":
            trail = (c[t] - params.atr_trail_k * a) if d == 1 else (c[t] + params.atr_trail_k * a)
        else:  # exit_channel
            trail = dc_dn_x[t] if d == 1 else dc_up_x[t]
            trail = pos["stop"] if trail is None else trail
        pos["stop"] = max(pos["stop"], trail) if d == 1 else min(pos["stop"], trail)
        stop_series[t] = pos["stop"]

        # exits in §R3 order
        reason = exit_i = exit_price = None
        if d == 1 and low[t] <= pos["stop"]:
            reason = "stop_trailing" if pos["stop"] > pos["initial_stop"] else "stop_initial"
            exit_i, exit_price = t, min(o[t], pos["stop"])
        elif d == -1 and h[t] >= pos["stop"]:
            reason = "stop_trailing" if pos["stop"] < pos["initial_stop"] else "stop_initial"
            exit_i, exit_price = t, max(o[t], pos["stop"])
        else:
            chan = (d == 1 and dc_dn_x[t] is not None and c[t] < dc_dn_x[t]) or \
                   (d == -1 and dc_up_x[t] is not None and c[t] > dc_up_x[t])
            if chan:
                f = fill(t)
                if f is not None:
                    reason, (exit_i, exit_price) = "channel_reversal", f

        if reason:
            rev_dir = -pos["direction"] if (params.stop_and_reverse and reason == "channel_reversal") else 0
            if (rev_dir == 1 and not params.allow_long) or (rev_dir == -1 and not params.allow_short):
                rev_dir = 0
            close_position(exit_i, exit_price, reason)
            if rev_dir:
                a2 = atr[t] or 0.0
                pos = {
                    "direction": rev_dir, "sig_t": t, "fill_i": exit_i, "entry_price": exit_price,
                    "entry_atr": a2, "initial_stop": exit_price - rev_dir * params.atr_stop_mult * a2,
                    "stop": exit_price - rev_dir * params.atr_stop_mult * a2,
                    "hh": h[t], "ll": low[t], "mae": 0.0, "mfe": 0.0,
                    "entry_cost": per_side_cost(exit_price, a2),
                }

    if pos is not None:
        close_position(n - 1, c[n - 1], None)  # still-open row

    # exposure during each bar + daily strategy return series
    for tr in trades:
        d = 1 if tr["direction"] == "long" else -1
        # locate fill indices by date
        ei = dates.index(tr["entry_date"])
        xi = dates.index(tr["exit_date"]) if tr["exit_date"] else n
        for t in range(ei, xi):
            exposure[t] = d

    daily: list[dict] = []
    fill_bars = set()
    for tr in trades:
        fill_bars.add(dates.index(tr["entry_date"]))
        if tr["exit_date"]:
            fill_bars.add(dates.index(tr["exit_date"]))
    for t in range(n):
        if t == 0:
            daily.append({"date": dates[t], "state": exposure[t], "strat_ret": 0.0})
            continue
        r = exposure[t] * (c[t] / c[t - 1] - 1.0)
        if t in fill_bars:
            r -= params.cost_bps / 1e4  # one side's cost booked on each fill bar
        daily.append({"date": dates[t], "state": exposure[t], "strat_ret": r})

    overlays["stop_line"] = stop_series
    return EngineResult(trades=trades, daily=daily, overlays=overlays)


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
