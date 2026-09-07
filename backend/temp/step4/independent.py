"""Independent indicators, order state, fills and cash for asymmetric rules."""


def indicators(bars):
    ranges, atr = [], []
    for i, b in enumerate(bars):
        previous = bars[i - 1]['c'] if i else b['c']
        ranges.append(max(b['h'] - b['l'], abs(b['h'] - previous), abs(b['l'] - previous)))
        atr.append(sum(ranges) / 20 if i == 19 else (atr[-1] * 19 + ranges[-1]) / 20 if i >= 20 else None)
    channels = {}
    for n in (10, 20, 55, 200):
        channels[n] = ([None] * min(n, len(bars)) + [max(b['h'] for b in bars[i-n:i]) for i in range(n, len(bars))],
                       [None] * min(n, len(bars)) + [min(b['l'] for b in bars[i-n:i]) for i in range(n, len(bars))])
    return {'atr': atr, 'channels': channels}


def run(bars, long_p, short_p, prepared):
    cash, units = 1., 0.
    position = order = None
    values, trades = [], []
    atr, channels = prepared['atr'], prepared['channels']
    settings = {'long': long_p, 'short': short_p}

    def charge(price, a, p):
        return abs(units) * (price * p.cost_bps / 10000 + a * p.slippage_atr)

    def exit_trade(b, price, a):
        nonlocal cash, units, position
        cash += units * price - charge(price, a, position['p'])
        trades.append((position['side'], position['date'], position['price'], b['date'], price))
        units, position = 0., None

    for i, b in enumerate(bars):
        previous_atr = atr[i-1] if i else None
        if order:
            if order == 'close':
                exit_trade(b, b['o'], previous_atr)
            else:
                p = settings[order]
                d = 1 if order == 'long' else -1
                units = d * cash / b['o']
                cash -= units * b['o'] + charge(b['o'], previous_atr, p)
                stop = b['o'] - d * p.atr_stop_mult * previous_atr if p.initial_enabled else None
                position = {'p': p, 'side': order, 'd': d, 'stop': stop, 'top': b['o'],
                            'bottom': b['o'], 'date': b['date'], 'price': b['o']}
            order = None
        if position:
            stop = position['stop']
            if stop is not None and ((units > 0 and b['l'] <= stop) or (units < 0 and b['h'] >= stop)):
                exit_trade(b, min(b['o'], stop) if units > 0 else max(b['o'], stop), previous_atr)
            else:
                position['top'] = max(position['top'], b['h'])
                position['bottom'] = min(position['bottom'], b['l'])
        value = cash + units * b['c']
        values.append(value)
        if value <= 0:
            values.extend([value] * (len(bars) - len(values)))
            return values, trades, b['date']
        if position:
            p, d = position['p'], position['d']
            up, down = channels[p.exit_len]
            if p.channel_enabled and ((d > 0 and b['c'] < down[i]) or (d < 0 and b['c'] > up[i])):
                order = 'close'
            if p.trailing_enabled:
                candidate = position['top'] - p.chandelier_k * atr[i] if d > 0 else position['bottom'] + p.chandelier_k * atr[i]
                old = position['stop']
                position['stop'] = candidate if old is None else max(old, candidate) if d > 0 else min(old, candidate)
        else:
            if long_p and i >= long_p.warmup() and b['c'] > channels[long_p.entry_len][0][i]:
                order = 'long'
            if short_p and i >= short_p.warmup() and b['c'] < channels[short_p.entry_len][1][i]:
                assert order is None
                order = 'short'
    if position:
        trades.append((position['side'], position['date'], position['price'], None, None))
    return values, trades, None
