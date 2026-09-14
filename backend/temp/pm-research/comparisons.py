"""Frozen candidate runs; reuse funded references, add true asset-only accounts."""
from __future__ import annotations
import argparse
import bisect
import csv
import gzip
import json
import shutil
from functools import partial
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from references import prepare, KEY, portfolio
from snapshot import BASE, ROOT, dump, sha256, verify
from strategies import sma_trend, pullback

# Predefined primary candidates, stop controls and four neighbours; no search.
CANDIDATES = {
    'sma200': (sma_trend, {'period':200,'initial_stop':False}),
    'pullback': (pullback, {'threshold':20,'initial_stop':True}),
    'sma200-stop': (sma_trend, {'period':200,'initial_stop':True}),
    'pullback-no-stop': (pullback, {'threshold':20,'initial_stop':False}),
    'sma150': (sma_trend, {'period':150,'initial_stop':False}),
    'sma250': (sma_trend, {'period':250,'initial_stop':False}),
    'pullback-rsi10': (pullback, {'threshold':10,'initial_stop':True}),
    'pullback-rsi30': (pullback, {'threshold':30,'initial_stop':True}),
}


def event_index(data, window):
    indexed = {}
    for key, tape in data['tapes'][window].items():
        by_symbol = defaultdict(list)
        for t, events in enumerate(tape):
            for event in events:
                by_symbol[event['symbol']].append((t, event))
        indexed[key] = by_symbol
    return indexed


def standalone_data(data, window, symbol, indexed):
    """Slice all candidates to the same asset decision/last-close dates."""
    info = data['infos'][symbol]
    if not info.get('execution_date'): return None
    first = bisect.bisect_left(data['dates'], info['decision_date'])
    last = bisect.bisect_right(data['dates'], info['last'])
    dates = data['dates'][first:last]
    market = {k:v[first:last] for k,v in data['market'][symbol].items()}
    tapes = {}
    for key, events in indexed.items():
        tape = [[] for _ in dates]
        for t, event in events.get(symbol, []):
            assert first <= t < last
            tape[t-first].append({**event, 'exit_t':event['exit_t']-first if event['exit_t'] is not None else None})
        tapes[key] = tape
    return {'dates':dates, 'market':{symbol:market}, 'infos':{symbol:info},
            'sums':{'single':{'members':[symbol], 'count':market['inverse'], 'inverse':market['inverse']}},
            'tapes':{window:tapes}, 'signals':{window:{symbol:data['signals'][window][symbol]}}}


def diagnostics(result):
    curve, trades = result['curve'], result['trades']
    result['stats'].update(
        cash_only_fraction=sum(r[3]+r[4]<1e-8 for r in curve)/len(curve),
        average_cash_fraction=sum(r[2]/r[1] for r in curve)/len(curve),
        entry_turnover=sum(abs(t['units'])*t['entry_price'] for t in trades)/100000.,
        worst_closed_trade_pnl=min((t['price_pnl']-t['entry_fee']-t['entry_slippage']-t['exit_fee']-t['exit_slippage']-t['borrow']
                                    for t in trades if t['exit_date']), default=None))
    return result


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def flat_stats(result):
    return {k:v for k,v in result['stats'].items() if not isinstance(v,list)}


def run(snapshot, name, include_references=False, selected='sma200'):
    snapshot = Path(snapshot)
    manifest = verify(snapshot)
    root = ROOT/'docs/temp/results'/snapshot.name
    quality = json.loads((root/'data-summary.json').read_text(encoding='utf-8'))
    reference = json.loads((root/'references-v1/run.json').read_text(encoding='utf-8'))
    assert quality['input_hash'] == reference['snapshot_hash'] == manifest['database_sha256']
    assert reference['status'] == 'succeeded' and reference['conventions_hash'] == manifest['conventions_sha256']
    output = root/name
    output.mkdir(exist_ok=False)
    sources = output/'sources'; sources.mkdir()
    files = [Path(__file__), BASE/'references.py', BASE/'strategies.py', BASE/'snapshot.py',
             ROOT/'backend/app/features/signals/engine.py', ROOT/'backend/app/features/signals/indicators.py',
             ROOT/'backend/app/features/signals/params.py', ROOT/'backend/app/features/sizing/portfolio.py',
             ROOT/'backend/app/features/sizing/params.py']
    hashes = {}
    for p in files:
        relative = str(p.relative_to(ROOT)).replace('\\','/')
        hashes[relative] = sha256(p)
        shutil.copyfile(p, sources/relative.replace('/','__'))
    state = {'status':'running', 'started_at':datetime.now(timezone.utc).isoformat(),
             'snapshot_hash':manifest['database_sha256'], 'conventions_hash':manifest['conventions_sha256'],
             'source_hashes':hashes, 'candidate':selected, 'parameters':CANDIDATES[selected][1],
             'include_new_standalone_references':include_references,
             'funded_reference':'../references-v1', 'coverage':'../coverage.csv',
             'provisional':True, 'completed':[]}
    dump(output/'run.json',state)
    funded = []; standalone = []
    try:
        for window in ['full','recent']:
            fn, params = CANDIDATES[selected]
            runners = [(selected,partial(fn,**params))]
            if include_references: runners.insert(0,('donchian',None))
            for candidate, runner in runners:
                data = prepare(snapshot,window,quality,signal_runner=runner,candidate=candidate)
                indexed = event_index(data,window)
                books = [('long-initial',candidate)]
                if candidate=='donchian': books.append(('buy-hold','buy-hold'))
                if candidate!='donchian':
                    for scope in ['priority','universe']:
                        for cost in ['normal','double']:
                            result = diagnostics(portfolio.simulate(data,scope,window,'long-initial','equal',cost))
                            result.update(candidate=candidate, book=candidate, input_hash=manifest['database_sha256'],provisional=True)
                            artifact = f'{window}-{scope}-{cost}-{candidate}.json.gz'
                            with gzip.open(output/artifact,'wt',encoding='utf-8',compresslevel=1) as stream:
                                json.dump(result,stream,allow_nan=False)
                            funded.append({'window':window,'scope':scope,'cost':cost,'candidate':candidate,'provisional':True,**flat_stats(result)})
                            state['completed'].append(artifact); dump(output/'run.json',state)
                            print(artifact, f"CAGR={result['stats']['cagr']:.4%} DD={result['stats']['drawdown']:.4%}",flush=True)
                artifact = f'{window}-{candidate}-standalone.jsonl.gz'
                with gzip.open(output/artifact,'wt',encoding='utf-8',compresslevel=1) as stream:
                    for number,symbol in enumerate(sorted(data['infos'])):
                        info = data['infos'][symbol]
                        single = standalone_data(data,window,symbol,indexed)
                        for book,label in books:
                            for cost in ['normal','double']:
                                row = {'symbol':symbol,'window':window,'candidate':label,'cost':cost,
                                       'priority':info['priority'],'decision_date':info.get('decision_date'),
                                       'earliest_execution':info.get('execution_date'),'end_date':info['last'],
                                       'status':'invalid_data' if symbol in quality['invalid_symbols'] else
                                                'insufficient_history' if single is None else 'ok',
                                       'provisional':symbol in quality['flagged_symbols']}
                                if single:
                                    result = diagnostics(portfolio.simulate(single,'single',window,book,'equal',cost))
                                    result.update(book=label,input_hash=manifest['database_sha256'],**row)
                                    row.update(flat_stats(result))
                                    stream.write(json.dumps(result,allow_nan=False)+'\n')
                                else: stream.write(json.dumps(row)+'\n')
                                standalone.append(row)
                        if number%100==0: print(window,candidate,'standalone',number+1,'/',len(data['infos']),flush=True)
                state['completed'].append(artifact); dump(output/'run.json',state)
                write_csv(output/'standalone.csv',standalone)
                del data, indexed
        with (root/'references-v1/summary.csv').open(encoding='utf-8',newline='') as stream:
            for original in csv.DictReader(stream):
                row = dict(original); row['candidate'] = 'donchian' if row.pop('book')=='long-initial' else 'buy-hold'
                row['source'] = '../references-v1/summary.csv'
                funded.append(row)
        write_csv(output/'funded-comparison.csv',funded)
        state.update(status='succeeded',finished_at=datetime.now(timezone.utc).isoformat(),standalone_rows=len(standalone))
    except Exception as exc:
        state.update(status='failed',error=f'{type(exc).__name__}: {exc}')
        raise
    finally: dump(output/'run.json',state)
    print('COMPLETE',output,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--name',default='sma-comparison-v1')
    parser.add_argument('--include-references',action='store_true')
    parser.add_argument('--candidate',choices=list(CANDIDATES),default='sma200')
    args=parser.parse_args()
    current=json.loads((BASE/'current-snapshot.json').read_text(encoding='utf-8'))
    run(current['path'],args.name,args.include_references,args.candidate)
