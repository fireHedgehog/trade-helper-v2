"""Independent close/open/stop cash simulation for the research switches."""

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
                initial = op - order * p.atr_stop_mult * prior_a if p.initial_enabled else None
                position = {"date": bar["date"], "price": op, "side": order,
                            "stop": initial, "initial": initial, "high": op, "low": op}
            order = None

        if position:
            side, stop = position["side"], position["stop"]
            if stop is not None and ((side == 1 and lo <= stop) or (side == -1 and hi >= stop)):
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
            if p.channel_enabled and ((side == 1 and close < min(b["l"] for b in prior_exit)) or (side == -1 and close > max(b["h"] for b in prior_exit))):
                order = "exit"
            if not p.trailing_enabled:
                continue
            if p.trail_mode == "chandelier":
                trail = position["high"] - p.chandelier_k * a if side == 1 else position["low"] + p.chandelier_k * a
            elif p.trail_mode == "atr_trail":
                trail = close - side * p.atr_trail_k * a
            else:
                window = bars[i + 1 - p.exit_len:i + 1]
                trail = min(b["l"] for b in window) if side == 1 else max(b["h"] for b in window)
            position["stop"] = trail if position["stop"] is None else (max(position["stop"], trail) if side == 1 else min(position["stop"], trail))
    return equity, trades, exhausted

