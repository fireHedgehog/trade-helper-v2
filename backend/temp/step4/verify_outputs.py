"""Check the saved full-universe results and every archived dollar ledger."""
import csv
import gzip
import hashlib
import json
import math
from collections import Counter
from itertools import groupby
from pathlib import Path
from plan import OUTPUT, SCENARIOS, FIELDS, RULES, ROOT


def main():
    manifest = json.loads((OUTPUT/'results.json').read_text(encoding='utf-8'))
    meta = manifest['metadata']
    assert not meta['partial'] and meta['symbol_count'] == 678 and meta['simulation_count'] == 457650
    assert meta['step3_bridge_checks'] == 678*75 and meta['step3_fill_checks'] == 678*75
    scenarios = {s[0] for s in SCENARIOS}
    expected = {}
    identity_max = 0.
    for s in manifest['instruments']:
        data = json.loads((OUTPUT/'summaries'/(s['symbol'].replace('/', '_')+'.json')).read_text(encoding='utf-8'))
        assert {r[0] for r in data['rows']} == scenarios and len(data['rows']) == 675
        assert (OUTPUT/data['detail_file']).exists()
        for row in data['rows']:
            r = dict(zip(FIELDS, row))
            assert math.isclose(10000+r['price_pnl']-r['fees']-r['slippage'], r['ending'], rel_tol=1e-10, abs_tol=1e-7)
            assert math.isclose(10000+r['long_pnl']+r['short_pnl'], r['ending'], rel_tol=1e-10, abs_tol=1e-7)
            if not r['exhausted']:
                assert r['gross']+1e-9 >= r['fee_only'] >= r['net']-1e-9
            expected[(s['symbol'],r['scenario'])] = (r['trades'],r['price_pnl'],r['fees'],r['slippage'],r['ending'])
    counts = Counter()
    with gzip.open(OUTPUT/'summary.csv.gz', 'rt', encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            counts[row['symbol']] += 1
    assert len(counts) == 678 and set(counts.values()) == {675}
    closed_total = open_total = checked = 0
    seen = set()
    for path in sorted(OUTPUT.glob('trades-*.csv.gz')):
        with gzip.open(path, 'rt', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for key, group in groupby(reader, key=lambda r: (r['symbol'], r['scenario'])):
                assert key not in seen, (key, 'duplicate archived ledger')
                seen.add(key)
                target = expected[key]
                count, pnl, fees, slip = 0, 0., 0., 0.
                last_date = None
                ending = 10000.
                for row in group:
                    before, price, fee, slippage, after = [float(row[k]) for k in ('starting_equity','price_pnl','fees','slippage','ending_equity')]
                    assert math.isclose(before, ending, rel_tol=1e-10, abs_tol=1e-7), key
                    assert last_date is None or row['entry_date'] > last_date, (key, 'position overlap')
                    error = abs(before+price-fee-slippage-after)
                    identity_max = max(identity_max, error)
                    assert math.isclose(before+price-fee-slippage, after, rel_tol=1e-10, abs_tol=1e-7), key
                    assert (float(row['signed_units']) > 0) == (row['direction'] == 'long')
                    count += bool(row['exit_date'])
                    closed_total += bool(row['exit_date'])
                    open_total += not bool(row['exit_date'])
                    pnl += price
                    fees += fee
                    slip += slippage
                    ending = after
                    last_date = row['mark_date']
                assert count == target[0], (key, count, target[0])
                for actual, wanted in zip((pnl,fees,slip,ending),target[1:]):
                    assert math.isclose(actual,wanted,rel_tol=1e-10,abs_tol=1e-6), (key,actual,wanted)
                checked += 1
        print(f'Checked {path.name}', flush=True)
    assert len(list(OUTPUT.glob('trades-*.csv.gz'))) == 27
    # Zero-trade scenarios have no ledger rows, but remain in every summary.
    expected_nonempty = sum(v[0]>0 or not math.isclose(v[4],10000.,abs_tol=1e-10) for v in expected.values())
    assert checked >= expected_nonempty and checked <= len(expected)
    assert all(key in seen for key,v in expected.items() if v[0]>0 or not math.isclose(v[4],10000.,abs_tol=1e-10))
    oversized = [(str(p.relative_to(OUTPUT)),p.stat().st_size) for p in OUTPUT.rglob('*') if p.is_file() and p.stat().st_size >= 100*1024*1024]
    assert not oversized, oversized
    assert hashlib.sha256((ROOT/'backend/app/features/signals/engine.py').read_bytes()).hexdigest() == meta['engine_sha256']
    print(json.dumps({'verified_simulations':sum(counts.values()),'closed_funded_trades':closed_total,
                      'open_or_exhaustion_marks':open_total,'verified_nonempty_ledgers':checked,
                      'max_dollar_identity_error':identity_max,'all_files_below_100MiB':True}),flush=True)


if __name__ == '__main__':
    main()
