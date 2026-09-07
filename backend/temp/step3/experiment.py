"""Step 3: stop architecture, full frozen universe, independent dollar ledger.

Run: backend/.venv/Scripts/python.exe backend/temp/step3/experiment.py
Then: backend/.venv/Scripts/python.exe backend/temp/step3/report.py
All code and outputs remain in temp. No production or database mutation.
"""
import argparse
import base64
import csv
import gzip
import hashlib
import io
import json
import math
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
from itertools import groupby
from pathlib import Path

from configs import BACKEND, ResearchParams, configurations, ARCHITECTURES
from cash import account, curve_stats, COMMON_START
from reference import reference
import research_engine
from app.features.signals import engine as production, indicators

ROOT = BACKEND.parent
OUTPUT = ROOT / 'docs/temp/step3'
STEP1 = ROOT / 'docs/temp/step1'
STEP2 = ROOT / 'docs/temp/step2'
MODES = ['both', 'long', 'short']
AUDIT_SYMBOLS = {'BTC/USD','ETH/USD','SPY','QQQ','TLT','NVDA','ECHO'}
FIELDS = ['config','mode','net','cagr','drawdown','gross','fee_only','trades',
          'common_net','common_cagr','common_drawdown','common_trades','common_days',
          'exhausted','gross_exhausted','price_pnl','fees','slippage','ending',
          'channel_exits','initial_exits','trailing_exits','long_contribution','short_contribution',
          'unfunded_signals']
LEDGER_FIELDS = ['direction','entry_date','entry_price','exit_date','mark_price','reason',
                 'signed_units','starting_equity','price_pnl','fees','slippage','ending_equity','mark_date']


def ledger_partition(config, mode):
    family = config['architecture']
    if family == 'all':
        family += '-e'+str(config['entry'])
    return family+'|'+mode


PARTITIONS = sorted({ledger_partition(c,m) for c in configurations() for m in MODES})


def run_symbol(task):
    info,bars = task
    symbol = info['symbol']
    dates = [b['date'] for b in bars]
    index = {d:i for i,d in enumerate(dates)}
    sample = sorted({0,len(bars)-1,*range(4,len(bars),5)})
    high,low,close = ([b[k] for b in bars] for k in ('h','l','c'))
    prepared = {'atr':indicators.wilder_atr(high,low,close,20),
                'channels':{n:indicators.donchian(high,low,n) for n in (10,20,55,200)}}
    atr = prepared['atr']
    summaries,details = [],{}
    ledger_buffers = {key:io.StringIO(newline='') for key in PARTITIONS}
    writers = {mode:csv.writer(buffer) for mode,buffer in ledger_buffers.items()}
    checks = {'identity_error':0., 'cash_error':0., 'cash_bars':0, 'bridge_error':0., 'bridge_checks':0}
    previous = {tuple(r[:3]):dict(zip(info['step2_fields'],r)) for r in info['rows']}
    for config in configurations():
        for mode in MODES:
            p = ResearchParams(**{**config['params'],'allow_long':mode!='short','allow_short':mode!='long'})
            result = research_engine.run(bars,p,prepared)
            net = account(bars,result.trades,atr,p.cost_bps,p.slippage_atr)
            gross = account(bars,result.trades,atr,0,0)
            fee_only = account(bars,result.trades,atr,p.cost_bps,0)
            stats = curve_stats(net['curve'],dates,net['exhausted'])
            if symbol in AUDIT_SYMBOLS:
                reference_curve, _, _ = reference(bars,p)
                error = max(abs(a/10000-b)/max(1,abs(b)) for a,b in zip(net['curve'],reference_curve))
                assert error < 1e-9,(symbol,config['id'],mode,error)
                checks['cash_bars'] += len(reference_curve)
                checks['cash_error'] = max(checks['cash_error'],error)
            if config['architecture']=='all' and config['initial']==2 and config['trailing']==3:
                old = previous[(config['entry'],config['exit'],mode)]
                if not net['exhausted']:
                    error = abs(stats['net']-old['net'])/max(1,abs(old['net']))
                    assert error < 1e-9,(symbol,config['id'],mode,'Step 2 bridge',error)
                    checks['bridge_error'] = max(checks['bridge_error'],error)
                    checks['bridge_checks'] += 1
            # Independent zero-cost execution on the audit symbols checks that
            # eliminating charges changes accounting, never signals or fill prices.
            if symbol in AUDIT_SYMBOLS:
                zero = research_engine.run(bars,p.model_copy(update={'cost_bps':0,'slippage_atr':0}),prepared)
                fills = lambda trades:[(t['direction'],t['entry_date'],t['entry_price'],t['exit_date'],t['exit_price']) for t in trades]
                assert fills(zero.trades)==fills(result.trades)
            checks['identity_error'] = max(checks['identity_error'],net['identity_error'])
            reasons = Counter(t[5] for t in net['ledger'] if t[3])
            closed = sum(reasons.values())
            common_closed = sum(t[3] is not None and index[t[3]]>=COMMON_START for t in net['ledger'])
            sides = {mode:net} if mode!='both' else {side:account(bars,[t for t in result.trades if t['direction']==side],atr,p.cost_bps,p.slippage_atr) for side in ('long','short')}
            long_contribution = sides['long']['ending']/10000-1 if 'long' in sides else 0.
            short_contribution = sides['short']['ending']/10000-1 if 'short' in sides else 0.
            if not net['exhausted']:
                assert math.isclose((1+long_contribution)*(1+short_contribution),1+stats['net'],rel_tol=1e-9,abs_tol=1e-9)
            row = [config['id'],mode,stats['net'],stats['cagr'],stats['drawdown'],gross['ending']/10000-1,
                   fee_only['ending']/10000-1,closed,stats['common_net'],stats['common_cagr'],stats['common_drawdown'],
                   common_closed,stats['common_days'],net['exhausted'],gross['exhausted'],net['price_pnl'],net['fees'],
                   net['slippage'],net['ending'],reasons['channel_reversal'],reasons['stop_initial'],reasons['stop_trailing'],
                   long_contribution,short_contribution,net['unfunded_signals']]
            summaries.append(row)
            key = config['id']+'|'+mode
            details[key] = {'net':[round(net['curve'][i],6) for i in sample],
                            'gross':[round(gross['curve'][i],6) for i in sample],
                            'fee_only':[round(fee_only['curve'][i],6) for i in sample],
                            'ledger':net['ledger']}
            if mode=='both':
                for side in ('long','short'):
                    details[key][side]=[round(sides[side]['curve'][i],6) for i in sample]
            for tr in net['ledger']:
                writers[ledger_partition(config,mode)].writerow([symbol,config['id'],*tr])
    assert len(summaries)==300
    detail = {'symbol':symbol,'dates':[dates[i] for i in sample],
              'buy_hold':[round(bars[i]['c']/bars[0]['c']*10000,6) for i in sample],'variants':details}
    # Gzip local display data keeps the final experiment archive practical.
    # The browser decodes it once after loading the selected instrument script.
    compressed = base64.b64encode(gzip.compress(json.dumps(detail,allow_nan=False,separators=(',',':')).encode(),compresslevel=6)).decode()
    file = symbol.replace('/','_')+'.js'
    script = "window.step3Ready=window.step3Ready||{};window.step3Ready["+json.dumps(symbol)+"]=new Response(new Blob([Uint8Array.from(atob('"+compressed+"'),c=>c.charCodeAt(0))]).stream().pipeThrough(new DecompressionStream('gzip'))).json();"
    (OUTPUT/'instruments'/file).write_text(script,encoding='utf-8')
    return {'symbol':symbol,'priority':info['priority'],'group':info['group'],'start':dates[0],'end':dates[-1],
            'bars':len(bars),'common_start':dates[COMMON_START] if len(dates)>COMMON_START else None,
            'rows':summaries,'detail_file':'instruments/'+file,'checks':checks,
            'ledger_csv':{mode:buf.getvalue() for mode,buf in ledger_buffers.items()}}


def tasks(instruments,subset):
    with gzip.open(STEP1/'inputs.csv.gz','rt',encoding='utf-8',newline='') as f:
        for symbol,rows in groupby(csv.DictReader(f),key=lambda r:r['symbol']):
            bars=[{k:float(v) if k in ('o','h','l','c','v') else v for k,v in r.items() if k!='symbol'} for r in rows]
            if subset is None or symbol in subset:
                yield instruments[symbol],bars


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--symbols',help='Comma-separated smoke check; omit for the full universe')
    parser.add_argument('--workers',type=int,default=min(6,max(1,(os.cpu_count() or 2)-2)))
    args=parser.parse_args()
    started=time.monotonic()
    OUTPUT.mkdir(exist_ok=True,parents=True)
    (OUTPUT/'instruments').mkdir(exist_ok=True)
    previous=json.loads((STEP2/'results.json').read_text(encoding='utf-8'))
    assert not previous['metadata']['partial']
    assert hashlib.sha256(Path(production.__file__).read_bytes()).hexdigest()==previous['metadata']['engine_sha256']
    assert hashlib.sha256((STEP1/'inputs.csv.gz').read_bytes()).hexdigest()==previous['metadata']['inputs_sha256']
    instruments={s['symbol']:{**s,'step2_fields':previous['metadata']['fields']} for s in previous['instruments']}
    subset=set(args.symbols.split(',')) if args.symbols else None
    total=len(subset) if subset else len(instruments)
    iterator=iter(tasks(instruments,subset))
    streams={key:gzip.open(OUTPUT/('trades-'+key.replace('|','-')+'.csv.gz'),'wt',encoding='utf-8',newline='')
             for key in PARTITIONS}
    for stream in streams.values():
        csv.writer(stream).writerow(['symbol','config',*LEDGER_FIELDS])
    results=[]
    try:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            pending=set()
            for _ in range(args.workers*2):
                task=next(iterator,None)
                if task is not None: pending.add(pool.submit(run_symbol,task))
            while pending:
                done,pending=wait(pending,return_when=FIRST_COMPLETED)
                for future in done:
                    result=future.result()
                    for key,content in result.pop('ledger_csv').items(): streams[key].write(content)
                    results.append(result)
                    task=next(iterator,None)
                    if task is not None: pending.add(pool.submit(run_symbol,task))
                    if len(results)%20==0 or len(results)==total:
                        print(f'Step 3: {len(results)}/{total} instruments, {len(results)*300:,} simulations, {time.monotonic()-started:.0f}s',flush=True)
    finally:
        for stream in streams.values(): stream.close()
    results.sort(key=lambda s:s['symbol'])
    assert len(results)==total
    metadata={'stage':'3 / Stop architecture','generated_utc':datetime.now(timezone.utc).isoformat(),
              'symbol_count':total,'simulation_count':total*300,'configurations':configurations(),'modes':MODES,
              'fields':FIELDS,'ledger_fields':LEDGER_FIELDS,'priority_symbols':previous['metadata']['priority_symbols'],
              'engine_sha256':previous['metadata']['engine_sha256'],'inputs_sha256':previous['metadata']['inputs_sha256'],
              'research_engine_sha256':hashlib.sha256(Path(research_engine.__file__).read_bytes()).hexdigest(),
              'architecture_labels':ARCHITECTURES,'common_start_index':COMMON_START,
              'ranking':'Median CAGR over the same continuing-strategy post-warmup window as Step 2. Fixed eligibility: >=2 calendar years. Exhausted accounts receive -100% ranking score. Thin samples (<5 closed trades) remain included and flagged.',
              'accounting':'Daily cash plus signed units; each entry deploys current equity; fixed units within each trade. $10,000 + gross price P&L - fees - ATR slippage = final net value.',
              'exhaustion':'Funded measurement stops at the first nonpositive daily mark or exit value; no fictitious later funded trades or liquidation fill. Signal generation remains two-sided. Gross and fee-only counterfactuals stop at their own exhaustion dates.',
              'costs':'5 bps and 0.05 prior-day ATR per fill; gross and fee-only use the identical signal trade schedule. Short borrow, financing and market impact are not modelled.',
              'chart_sampling':'Every fifth observation plus first/last, daily metrics and full-precision dollar ledgers.',
              'cash_audit_symbols':sorted(AUDIT_SYMBOLS),'cash_audit_bars':sum(s['checks']['cash_bars'] for s in results),
              'cash_max_error':max(s['checks']['cash_error'] for s in results),
              'dollar_identity_max_error':max(s['checks']['identity_error'] for s in results),
              'step2_bridge_checks':sum(s['checks']['bridge_checks'] for s in results),
              'step2_bridge_max_error':max(s['checks']['bridge_error'] for s in results),
              'partial':subset is not None,'elapsed_seconds':round(time.monotonic()-started,1)}
    (OUTPUT/'results.json').write_text(json.dumps({'metadata':metadata,'instruments':results},allow_nan=False,separators=(',',':')),encoding='utf-8')
    with gzip.open(OUTPUT/'summary.csv.gz','wt',encoding='utf-8',newline='') as f:
        writer=csv.writer(f);writer.writerow(['symbol','priority','group','start','end','common_start',*FIELDS])
        for s in results:
            writer.writerows([s['symbol'],s['priority'],s['group'],s['start'],s['end'],s['common_start'],*r] for r in s['rows'])
    print(json.dumps({k:v for k,v in metadata.items() if k not in ('configurations','priority_symbols')}),flush=True)


if __name__=='__main__':
    main()
