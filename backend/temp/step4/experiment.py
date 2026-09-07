"""Run all 625 pairs and 50 standalone directions on the frozen 678 assets."""
import argparse
import base64
import csv
import gzip
import hashlib
import io
import json
import math
import os
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
from itertools import groupby
from pathlib import Path

from plan import ROOT, OUTPUT, RULES, SCENARIOS, FIELDS, LEDGER_FIELDS, AUDIT_SYMBOLS, ResearchParams
from cash import account, curve_stats, COMMON_START
import cash as cash_module
import fills
import independent
import research_engine as step3_engine
from app.features.signals import engine as production, indicators

PARTITIONS = [r['key'] for r in RULES] + ['long', 'short']


def run_symbol(task):
    info, bars = task
    symbol = info['symbol']
    dates = [b['date'] for b in bars]
    index = {d: i for i, d in enumerate(dates)}
    sample = sorted({0, len(bars)-1, *range(4, len(bars), 5)})
    high, low, close = ([b[k] for b in bars] for k in ('h', 'l', 'c'))
    prepared = {'atr': indicators.wilder_atr(high, low, close, 20),
                'channels': {n: indicators.donchian(high, low, n) for n in (10, 20, 55, 200)}}
    independent_prepared = independent.indicators(bars) if symbol in AUDIT_SYMBOLS else None
    params = {r['key']: ResearchParams(**r['params']) for r in RULES}
    prior_rows = {tuple(r[:2]): dict(zip(info['fields'], r)) for r in info['rows']}
    prior_ids = {r['key']: r['id'] for r in RULES}
    buffers = {key: io.StringIO(newline='') for key in PARTITIONS}
    writers = {key: csv.writer(buf) for key, buf in buffers.items()}
    checks = {'identity_error': 0., 'cash_error': 0., 'cash_bars': 0, 'bridge_error': 0.,
              'bridge_checks': 0, 'fill_checks': 0, 'independent_fill_checks': 0, 'fill_price_error': 0.}
    summaries, detail = [], {}
    for scenario, lk, sk, mode in SCENARIOS:
        lp, sp = params.get(lk), params.get(sk)
        trades = fills.run(bars, lp, sp, prepared)
        # One position; an exit can seed a next-close signal, never an overlap.
        last_exit = -1
        for tr in trades:
            assert index[tr['entry_date']] > last_exit, (symbol, scenario, 'overlapping positions')
            last_exit = index[tr['exit_date']] if tr['exit_date'] else len(bars)
        net = account(bars, trades, prepared['atr'])
        gross = account(bars, trades, prepared['atr'], 0, 0)
        fee_only = account(bars, trades, prepared['atr'], 5, 0)
        stats = curve_stats(net['curve'], dates, net['exhausted'])
        if not net['exhausted']:
            assert gross['ending'] + 1e-7 >= fee_only['ending'] >= net['ending'] - 1e-7
        if lk == sk or mode != 'both':
            key = lk or sk
            p = params[key].model_copy(update={'allow_long': mode != 'short', 'allow_short': mode != 'long'})
            prior_trades = step3_engine.run(bars, p, prepared).trades
            assert fills.signature(trades) == fills.signature(prior_trades), (symbol, scenario, 'Step 3 fills')
            checks['fill_checks'] += 1
            prior = prior_rows[(prior_ids[key], mode)]
            for field in ('net', 'cagr', 'drawdown', 'common_net', 'common_cagr', 'common_drawdown', 'ending'):
                a = net['ending'] if field == 'ending' else stats[field]
                b = prior[field]
                if a is None or b is None:
                    assert a is b, (symbol, scenario, field)
                    continue
                error = abs(a-b) / max(1, abs(b))
                assert error < 1e-9, (symbol, scenario, field, error)
                checks['bridge_error'] = max(checks['bridge_error'], error)
            assert net['exhausted'] == prior['exhausted']
            checks['bridge_checks'] += 1
        if independent_prepared:
            ref_curve, ref_trades, exhausted = independent.run(bars, lp, sp, independent_prepared)
            error = max(abs(a/10000-b)/max(1, abs(b)) for a, b in zip(net['curve'], ref_curve))
            assert len(ref_curve) == len(bars) and error < 1e-9 and exhausted == net['exhausted'], (symbol, scenario, 'independent cash', error)
            original = [s[:5] for s in fills.signature(trades)]
            assert len(original) >= len(ref_trades)
            if not exhausted: assert len(original) == len(ref_trades)
            for actual, expected in zip(original, ref_trades):
                assert (actual[0], actual[1], actual[3]) == (expected[0], expected[1], expected[3]), (symbol, scenario, 'independent fill dates')
                for j in (2, 4):
                    if actual[j] is None or expected[j] is None:
                        assert actual[j] is expected[j]
                    else:
                        assert math.isclose(actual[j], expected[j], rel_tol=1e-12, abs_tol=1e-10), (symbol, scenario, 'independent fill price')
                        checks['fill_price_error'] = max(checks['fill_price_error'], abs(actual[j]-expected[j]))
            checks['cash_error'] = max(checks['cash_error'], error)
            checks['cash_bars'] += len(ref_curve)
            checks['independent_fill_checks'] += 1
        ledger = net['ledger']
        checks['identity_error'] = max(checks['identity_error'], net['identity_error'])
        reasons = Counter(t[5] for t in ledger if t[3])
        pnl = {side: sum(t[8]-t[9]-t[10] for t in ledger if t[0] == side) for side in ('long', 'short')}
        assert math.isclose(10000 + sum(pnl.values()), net['ending'], rel_tol=1e-10, abs_tol=1e-7)
        closed = {side: sum(t[0] == side and t[3] is not None for t in ledger) for side in ('long', 'short')}
        row = [scenario, stats['net'], stats['cagr'], stats['drawdown'], gross['ending']/10000-1,
               fee_only['ending']/10000-1, sum(closed.values()), stats['common_net'], stats['common_cagr'],
               stats['common_drawdown'], sum(t[3] is not None and index[t[3]] >= COMMON_START for t in ledger),
               stats['common_days'], net['exhausted'], gross['exhausted'], net['price_pnl'], net['fees'],
               net['slippage'], net['ending'], pnl['long'], pnl['short'], closed['long'], closed['short'],
               reasons['channel_reversal'], reasons['stop_initial'], reasons['stop_trailing'], net['unfunded_signals']]
        assert len(row) == len(FIELDS)
        summaries.append(row)
        detail[scenario] = {key: [round(obj['curve'][i], 6) for i in sample]
                            for key, obj in [('net', net), ('gross', gross), ('fee_only', fee_only)]}
        detail[scenario]['ledger'] = ledger
        for tr in ledger:
            writers[lk if mode == 'both' else mode].writerow([symbol, scenario, *tr])
    assert len(summaries) == 675
    safe = symbol.replace('/', '_')
    payload = {'symbol': symbol, 'dates': [dates[i] for i in sample],
               'buy_hold': [round(bars[i]['c']/bars[0]['c']*10000, 6) for i in sample], 'variants': detail}
    compressed = base64.b64encode(gzip.compress(json.dumps(payload, allow_nan=False, separators=(',', ':')).encode(), compresslevel=6)).decode()
    script = ('window.step4Ready=window.step4Ready||{};window.step4Ready['+json.dumps(symbol)+
              ']=new Response(new Blob([Uint8Array.from(atob('+json.dumps(compressed)+'),c=>c.charCodeAt(0))]).stream().pipeThrough(new DecompressionStream("gzip"))).json();')
    (OUTPUT/'instruments'/f'{safe}.js').write_text(script, encoding='utf-8')
    result = {'symbol': symbol, 'priority': info['priority'], 'group': info['group'], 'start': dates[0],
              'end': dates[-1], 'bars': len(bars), 'common_start': dates[COMMON_START] if len(dates)>COMMON_START else None,
              'rows': summaries, 'detail_file': f'instruments/{safe}.js', 'checks': checks}
    (OUTPUT/'summaries'/f'{safe}.json').write_text(json.dumps(result, allow_nan=False, separators=(',', ':')), encoding='utf-8')
    return {**{k: v for k, v in result.items() if k != 'rows'},
            'ledger_csv': {key: buf.getvalue() for key, buf in buffers.items()}}


def tasks(instruments, subset):
    with gzip.open(ROOT/'docs/temp/step1/inputs.csv.gz', 'rt', encoding='utf-8', newline='') as f:
        for symbol, rows in groupby(csv.DictReader(f), key=lambda r: r['symbol']):
            bars = [{k: float(v) if k in ('o', 'h', 'l', 'c', 'v') else v for k, v in r.items() if k != 'symbol'} for r in rows]
            if subset is None or symbol in subset:
                yield instruments[symbol], bars


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbols')
    parser.add_argument('--workers', type=int, default=min(6, max(1, (os.cpu_count() or 2)-2)))
    args = parser.parse_args()
    started = time.monotonic()
    for path in (OUTPUT, OUTPUT/'instruments', OUTPUT/'summaries'):
        path.mkdir(exist_ok=True, parents=True)
    previous = json.loads((ROOT/'docs/temp/step3/results.json').read_text(encoding='utf-8'))
    assert not previous['metadata']['partial']
    assert sha(production.__file__) == previous['metadata']['engine_sha256']
    assert sha(ROOT/'docs/temp/step1/inputs.csv.gz') == previous['metadata']['inputs_sha256']
    instruments = {s['symbol']: {**s, 'fields': previous['metadata']['fields']} for s in previous['instruments']}
    subset = set(args.symbols.split(',')) if args.symbols else None
    total = len(subset) if subset else len(instruments)
    iterator = iter(tasks(instruments, subset))
    streams = {key: gzip.open(OUTPUT/f'trades-{key}.csv.gz', 'wt', encoding='utf-8', newline='') for key in PARTITIONS}
    for stream in streams.values():
        csv.writer(stream).writerow(['symbol', 'scenario', *LEDGER_FIELDS])
    results = []
    try:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            pending = set()
            for _ in range(args.workers*2):
                task = next(iterator, None)
                if task is not None: pending.add(pool.submit(run_symbol, task))
            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    result = future.result()
                    for key, content in result.pop('ledger_csv').items(): streams[key].write(content)
                    results.append(result)
                    task = next(iterator, None)
                    if task is not None: pending.add(pool.submit(run_symbol, task))
                    if len(results) % 20 == 0 or len(results) == total:
                        print(f'Step 4: {len(results)}/{total} assets, {len(results)*675:,} simulations, {time.monotonic()-started:.0f}s', flush=True)
    finally:
        for stream in streams.values(): stream.close()
    results.sort(key=lambda s: s['symbol'])
    assert len(results) == total
    meta = {'stage': '4 / Different rules by direction', 'generated_utc': datetime.now(timezone.utc).isoformat(),
            'symbol_count': total, 'simulation_count': total*675, 'rules': RULES, 'scenarios': SCENARIOS,
            'fields': FIELDS, 'ledger_fields': LEDGER_FIELDS, 'priority_symbols': previous['metadata']['priority_symbols'],
            'engine_sha256': sha(production.__file__), 'inputs_sha256': previous['metadata']['inputs_sha256'],
            'cash_sha256': sha(cash_module.__file__), 'fills_sha256': sha(fills.__file__),
            'independent_sha256': sha(independent.__file__), 'common_start_index': COMMON_START,
            'cash_audit_symbols': sorted(AUDIT_SYMBOLS), 'cash_audit_bars': sum(s['checks']['cash_bars'] for s in results),
            'cash_max_error': max(s['checks']['cash_error'] for s in results),
            'dollar_identity_max_error': max(s['checks']['identity_error'] for s in results),
            'step3_bridge_checks': sum(s['checks']['bridge_checks'] for s in results),
            'step3_bridge_max_error': max(s['checks']['bridge_error'] for s in results),
            'step3_fill_checks': sum(s['checks']['fill_checks'] for s in results),
            'independent_fill_checks': sum(s['checks']['independent_fill_checks'] for s in results),
            'independent_fill_price_max_error': max(s['checks']['fill_price_error'] for s in results),
            'partial': subset is not None, 'elapsed_seconds': round(time.monotonic()-started, 1)}
    (OUTPUT/'results.json').write_text(json.dumps({'metadata': meta, 'instruments': results}, allow_nan=False, separators=(',', ':')), encoding='utf-8')
    with gzip.open(OUTPUT/'summary.csv.gz', 'wt', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['symbol', 'priority', 'group', 'start', 'end', *FIELDS])
        for s in results:
            item = json.loads((OUTPUT/'summaries'/(s['symbol'].replace('/', '_')+'.json')).read_text(encoding='utf-8'))
            writer.writerows([s['symbol'], s['priority'], s['group'], s['start'], s['end'], *r] for r in item['rows'])
    assert sha(production.__file__) == meta['engine_sha256']
    print(json.dumps({k: v for k, v in meta.items() if k not in ('rules', 'scenarios', 'priority_symbols', 'fields', 'ledger_fields')}), flush=True)


if __name__ == '__main__':
    main()
