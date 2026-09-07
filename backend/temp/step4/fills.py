"""One position, direction-specific rules. Next-open orders and prior-day stops.

The cash ledger is imported unchanged from Step 3. Opposite signals never
override an existing position or a pending exit. Each direction has its own
indicator warm-up; a slow short rule cannot delay a ready long entry.
"""
from plan import ResearchParams


def run(bars, long_p, short_p, prepared):
    for p in (long_p, short_p):
        if p:
            assert p.fill_at == 'open_next' and not p.stop_and_reverse
            assert not p.use_ma_regime and p.trail_mode == 'chandelier' and p.atr_len == 20
    atr, channels = prepared['atr'], prepared['channels']
    params = {1: long_p, -1: short_p}
    ready = [(side, p.warmup(), *channels[p.entry_len]) for side, p in params.items() if p]
    position = pending = None
    trades = []

    def finish(i, price, reason):
        nonlocal position
        trades.append({'direction': 'long' if position['side'] == 1 else 'short',
                       'entry_date': bars[position['entry_i']]['date'], 'entry_price': position['entry'],
                       'exit_date': bars[i]['date'] if reason else None,
                       'exit_price': price if reason else None, 'exit_reason': reason})
        position = None

    for i, b in enumerate(bars):
        op, high, low, close = (b[k] for k in ('o', 'h', 'l', 'c'))
        prior_atr = (atr[i - 1] or 0.) if i else 0.
        if pending:
            side, pending = pending, None
            if side == 'exit':
                finish(i, op, 'channel_reversal')
            else:
                p = params[side]
                initial = op - side * p.atr_stop_mult * prior_atr if p.initial_enabled else None
                position = {'side': side, 'entry_i': i, 'entry': op, 'initial': initial,
                            'stop': initial, 'high': op, 'low': op}

        if position:
            side, stop = position['side'], position['stop']
            if stop is not None and (low <= stop if side == 1 else high >= stop):
                price = min(op, stop) if side == 1 else max(op, stop)
                finish(i, price, 'stop_initial' if stop == position['initial'] else 'stop_trailing')
            else:
                position['high'] = max(position['high'], high)
                position['low'] = min(position['low'], low)

        if position:
            side = position['side']
            p = params[side]
            up, down = channels[p.exit_len]
            if p.channel_enabled and ((side == 1 and close < down[i]) or (side == -1 and close > up[i])):
                pending = 'exit'
            if p.trailing_enabled:
                trail = position['high'] - p.chandelier_k * atr[i] if side == 1 else position['low'] + p.chandelier_k * atr[i]
                position['stop'] = trail if position['stop'] is None else (max(position['stop'], trail) if side == 1 else min(position['stop'], trail))
        else:
            signals = []
            for side, warmup, up, down in ready:
                if i < warmup or atr[i] is None:
                    continue
                if (side == 1 and close > up[i]) or (side == -1 and close < down[i]):
                    signals.append(side)
            assert len(signals) <= 1, 'Opposite close breakouts cannot overlap on valid OHLC bars'
            if signals:
                pending = signals[0]
    if position:
        finish(len(bars) - 1, bars[-1]['c'], None)
    return trades


def signature(trades):
    return [(t['direction'], t['entry_date'], t['entry_price'], t['exit_date'],
             t['exit_price'], t['exit_reason']) for t in trades]
