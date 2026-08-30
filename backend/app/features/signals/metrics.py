"""Per-symbol performance metrics (docs/draft-design/04-trend-page.md §R7).

Single-symbol, rule-only, costs included, **not statistically validated** —
that label is attached to the output. No cross-symbol roll-up anywhere.
"""

from __future__ import annotations

import math
import statistics as st

from app.features.signals.engine import buy_hold_daily, compound, drawdown_curve

_TRADING_DAYS = 252.0
LABEL = "single-symbol, rule-only, costs included, not validated"


def _safe_mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _safe_std(xs: list[float]) -> float | None:
    return st.pstdev(xs) if len(xs) >= 2 else None


def _max_consec(flags: list[bool]) -> int:
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return best


def _max_dd_days(dd: list[float]) -> int:
    best = cur = 0
    for d in dd:
        cur = cur + 1 if d < 0 else 0
        best = max(best, cur)
    return best


def _curve_stats(rets: list[float]) -> dict:
    if len(rets) < 2:
        return {k: None for k in ("total_return", "cagr", "vol_annual", "sharpe",
                                  "sortino", "max_drawdown", "max_dd_days", "calmar")}
    equity = compound(rets)
    total = equity[-1] - 1.0
    years = len(rets) / _TRADING_DAYS
    cagr = (equity[-1] ** (1 / years) - 1.0) if equity[-1] > 0 and years > 0 else None
    mean = st.mean(rets)
    std = st.pstdev(rets)
    downside = [r for r in rets if r < 0]
    dstd = st.pstdev(downside) if len(downside) >= 2 else None
    dd = drawdown_curve(equity)
    max_dd = min(dd)
    return {
        "total_return": total,
        "cagr": cagr,
        "vol_annual": std * math.sqrt(_TRADING_DAYS) if std else None,
        "sharpe": (mean / std * math.sqrt(_TRADING_DAYS)) if std else None,
        "sortino": (mean / dstd * math.sqrt(_TRADING_DAYS)) if dstd else None,
        "max_drawdown": max_dd,
        "max_dd_days": _max_dd_days(dd),
        "calmar": (cagr / abs(max_dd)) if cagr is not None and max_dd < 0 else None,
    }


def summarise(trades: list[dict], daily: list[dict], bars: list[dict]) -> dict:
    closed = [t for t in trades if t["exit_date"] is not None]
    open_trade = next((t for t in trades if t["exit_date"] is None), None)

    rp = [t["return_pct"] for t in closed]
    rr = [t["return_r"] for t in closed if t["return_r"] is not None]
    wins = [x for x in rp if x > 0]
    losses = [x for x in rp if x <= 0]
    avg_win, avg_loss = _safe_mean(wins), _safe_mean(losses)
    gross_win, gross_loss = sum(wins), abs(sum(losses))
    rr_std = _safe_std(rr)

    trade_stats = {
        "trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "open_position": open_trade["direction"] if open_trade else None,
        "win_rate": (len(wins) / len(closed)) if closed else None,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "payoff_ratio": (avg_win / abs(avg_loss)) if avg_win and avg_loss else None,
        "expectancy_pct": _safe_mean(rp),
        "expectancy_r": _safe_mean(rr),
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else None,
        "sqn": (math.sqrt(len(rr)) * st.mean(rr) / rr_std) if rr_std else None,
        "avg_bars_held": _safe_mean([t["bars_held"] for t in closed]),
        "median_bars_held": (st.median([t["bars_held"] for t in closed]) if closed else None),
        "max_consec_losses": _max_consec([x <= 0 for x in rp]),
        "avg_mae_atr": _safe_mean([t["mae_atr"] for t in closed if t["mae_atr"] is not None]),
        "avg_mfe_atr": _safe_mean([t["mfe_atr"] for t in closed if t["mfe_atr"] is not None]),
        "exposure": (sum(1 for d in daily if d["state"] != 0) / len(daily)) if daily else None,
    }

    strat_rets = [d["strat_ret"] for d in daily]
    strat = _curve_stats(strat_rets)
    bh = _curve_stats(buy_hold_daily(bars))

    return {
        "label": LABEL,
        "trade_stats": trade_stats,
        "strategy": strat,
        "buy_hold": {k: bh[k] for k in ("total_return", "cagr", "max_drawdown")},
    }
