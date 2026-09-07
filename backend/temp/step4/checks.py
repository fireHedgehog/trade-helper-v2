"""Hand cases for direction-specific warm-up, exits, stops and one account."""
from datetime import date, timedelta
from plan import ResearchParams
import fills
import independent
from cash import account


def prices(values):
    return [{'date': (date(2020, 1, 1) + timedelta(days=i)).isoformat(),
             'o': o, 'h': h, 'l': l, 'c': c} for i, (o, h, l, c) in enumerate(values)]


def check():
    flat = [(100., 101., 99., 100.)] * 70
    bars = prices(flat + [(100., 104., 100., 103.), (103., 104., 102., 103.),
                          (103., 104., 90., 103.), (103., 104., 102., 103.)])
    loose = ResearchParams(entry_len=10, exit_len=55, initial_enabled=False, trailing_enabled=False)
    tight = ResearchParams(entry_len=200, exit_len=10, trailing_enabled=False)
    prepared = independent.indicators(bars)
    # Adding a slow opposite side neither delays the long nor supplies its stop.
    both = fills.run(bars, loose, tight, prepared)
    solo = fills.run(bars, loose, None, prepared)
    assert fills.signature(both) == fills.signature(solo)
    assert both[0]['entry_date'] == bars[71]['date'] and both[0]['exit_date'] is None
    assert fills.run(bars, loose.model_copy(update={'initial_enabled': True}), tight, prepared)[0]['exit_reason'] == 'stop_initial'
    # Mirror the case: the short must use its own stop and fast warm-up.
    mirrored = [{**b, 'o': 200-b['o'], 'h': 200-b['l'], 'l': 200-b['h'], 'c': 200-b['c']} for b in bars]
    prep = independent.indicators(mirrored)
    assert fills.signature(fills.run(mirrored, tight, loose, prep)) == fills.signature(fills.run(mirrored, None, loose, prep))
    assert fills.run(mirrored, tight, loose.model_copy(update={'initial_enabled': True}), prep)[0]['exit_reason'] == 'stop_initial'
    # Initial stop gap: execution uses the open, never an unreachable stop price.
    gapped = bars[:72] + [dict(bars[72], o=80., h=82., l=79., c=81.)]
    assert fills.run(gapped, loose.model_copy(update={'initial_enabled': True}), None, independent.indicators(gapped))[0]['exit_price'] == 80.
    # A channel exit is filled next open; the opposite breakout on the exit
    # signal date does not create a simultaneous short. Later signals can enter.
    reversal = prices(flat + [(100., 104., 100., 103.), (103., 104., 102., 103.),
                              (103., 104., 95., 96.), (96., 97., 93., 94.),
                              (94., 95., 90., 91.), (91., 93., 90., 92.)])
    p = loose.model_copy(update={'exit_len': 10})
    prep = independent.indicators(reversal)
    trades = fills.run(reversal, p, p, prep)
    assert trades[0]['exit_date'] == reversal[73]['date']
    assert trades[1]['direction'] == 'short' and trades[1]['entry_date'] == reversal[74]['date']
    cash = account(reversal, trades, prep['atr'])
    ref, _, _ = independent.run(reversal, p, p, prep)
    assert max(abs(a/10000-b) for a, b in zip(cash['curve'], ref)) < 1e-12
    assert abs(sum(t[8]-t[9]-t[10] for t in cash['ledger']) - (cash['ending']-10000)) < 1e-8
    print('Passed: separate warm-ups and stops, mirrored short, gap fill, next-open exit, single position, exact cash reconciliation.', flush=True)


def check_history_prefixes():
    from experiment import tasks
    from plan import RULES
    from app.features.signals import indicators

    def prepare(bars):
        high, low, close = ([b[k] for b in bars] for k in ('h', 'l', 'c'))
        return {'atr': indicators.wilder_atr(high, low, close, 20),
                'channels': {n: indicators.donchian(high, low, n) for n in (10, 20, 55, 200)}}

    checks = 0
    for symbol in ['BTC/USD', 'ETH/USD', 'SPY', 'TLT']:
        _, bars = next(tasks({symbol: {}}, {symbol}))
        prepared = prepare(bars)
        for lk, sk in [(2, 23), (0, 9), (15, 20), (24, 24)]:
            lp, sp = ResearchParams(**RULES[lk]['params']), ResearchParams(**RULES[sk]['params'])
            original = fills.signature(fills.run(bars, lp, sp, prepared))
            for cut in [500, 1000, 1500]:
                prefix = bars[:cut]
                shorter = fills.signature(fills.run(prefix, lp, sp, prepare(prefix)))
                completed = lambda rows: [r for r in rows if r[3] is not None and r[3] <= prefix[-1]['date']]
                assert completed(shorter) == completed(original), (symbol, lk, sk, cut)
                checks += 1
    print(f'Passed: {checks} truncated-history checks; later prices cannot alter earlier completed fills.', flush=True)


if __name__ == '__main__':
    check()
    check_history_prefixes()
