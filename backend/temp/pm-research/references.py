"""Common frozen-snapshot Donchian/BH funded references, production accounting."""
from __future__ import annotations
import bisect
import csv
import gzip
import json
from array import array
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
import sys

from snapshot import BASE, ROOT, dump, read_only, sha256, verify
from app.features.signals import engine, indicators
from app.features.signals.params import LONG_PARAMS
from app.features.sizing import portfolio
from app.features.sizing.params import asset_class

KEY = 'e20-x55-s3'


def prepare(snapshot, window, quality, signal_runner=None, candidate=KEY):
    manifest = verify(snapshot)
    priority = set(manifest['priority'])
    invalid = set(quality['invalid_symbols'])
    with read_only(snapshot/'market.sqlite3') as conn:
        infos = {}
        for table in ['price_bars','crypto_bars']:
            for row in conn.execute(f'SELECT symbol,MIN(date) first,MAX(date) last,COUNT(*) bars FROM {table} GROUP BY symbol'):
                infos[row['symbol']] = dict(row) | {'priority':row['symbol'] in priority,
                                                  'asset_class':asset_class(row['symbol'])}
        origin = date.fromisoformat(min(v['first'] for v in infos.values()))
        end = date.fromisoformat(max(v['last'] for v in infos.values()))
        dates = [(origin+timedelta(days=i)).isoformat() for i in range((end-origin).days+1)]
        n = len(dates)
        market = {}
        tapes = {window:{key:[[] for _ in dates] for key in [KEY,'buy-hold']}}
        signals = {window:{s:{KEY:0} for s in infos}}
        for number,symbol in enumerate(sorted(infos)):
            crypto = '/' in symbol
            table = 'crypto_bars' if crypto else 'price_bars'
            columns = 'open o, high h, low l, close c' if crypto else 'adj_open o, adj_high h, adj_low l, adj_close c'
            bars = [dict(r) for r in conn.execute(f'SELECT date,{columns},volume v FROM {table} WHERE symbol=? ORDER BY date',(symbol,))]
            closes,eligible,age = array('d',[0.])*n,array('d',[0.])*n,array('i',[99999])*n
            market[symbol] = {'close':closes,'inverse':eligible,'age':age}
            if symbol in invalid:
                continue   # retained member, no funding; never silently repair bars
            ds = [b['date'] for b in bars]
            indices = {d:i for i,d in enumerate(ds)}
            j = -1
            for t,day in enumerate(dates):
                while j+1<len(ds) and ds[j+1]<day: j+=1
                if j>=0:
                    age[t] = (date.fromisoformat(day)-date.fromisoformat(ds[j])).days
                    if j>=250 and age[t]<=7: eligible[t]=1.
                mark = j+1 if j+1<len(ds) and ds[j+1]==day else j
                if mark>=0: closes[t]=bars[mark]['c']
            start = max(250,bisect.bisect_left(ds,'2020-01-01' if window=='recent' else '1900-01-01'))
            infos[symbol]['decision_date']=ds[start] if start<len(ds) else None
            infos[symbol]['execution_date']=ds[start+1] if start+1<len(ds) else None
            atr = indicators.wilder_atr([b['h'] for b in bars],[b['l'] for b in bars],[b['c'] for b in bars],20)
            result = signal_runner(bars,start=start) if signal_runner else engine.run(bars,LONG_PARAMS,start=start)
            signals[window][symbol][KEY] = len(result.trades)
            for tr in result.trades:
                i = indices[tr['entry_date']]
                j = indices[tr['exit_date']] if tr['exit_date'] else None
                t = (date.fromisoformat(tr['entry_date'])-origin).days
                tapes[window][KEY][t].append({**tr,'symbol':symbol,'rule':candidate,'entry_atr':atr[i-1],
                    'exit_atr':atr[j-1] if j is not None else None,
                    'exit_t':(date.fromisoformat(tr['exit_date'])-origin).days if j is not None else None})
            i=start+1
            if i<len(bars):
                t=(date.fromisoformat(ds[i])-origin).days
                tapes[window]['buy-hold'][t].append({'symbol':symbol,'direction':'long','rule':'buy-hold',
                    'entry_date':ds[i],'entry_price':bars[i]['o'],'entry_atr':atr[i-1],
                    'exit_date':None,'exit_price':None,'exit_atr':None,'exit_reason':None,'exit_t':None})
            if number%100==0: print(f'{window} prepared {number+1}/{len(infos)} {symbol}',flush=True)
    sums = {}
    for scope in ['priority','universe']:
        members = sorted(s for s in infos if scope=='universe' or s in priority)
        counts=array('i',[0])*n
        for symbol in members:
            for t,value in enumerate(market[symbol]['inverse']):
                if value: counts[t]+=1
        sums[scope] = {'members':members,'count':counts,'inverse':counts}
    return {'dates':dates,'market':market,'infos':infos,'tapes':tapes,'signals':signals,'sums':sums}


def run(snapshot):
    snapshot = Path(snapshot)
    quality_dir = ROOT/'docs/temp/results'/snapshot.name
    quality=json.loads((quality_dir/'data-summary.json').read_text(encoding='utf-8'))
    manifest=verify(snapshot)
    if quality['input_hash']!=manifest['database_sha256']: raise ValueError('Quality report input mismatch')
    output=quality_dir/'references-v1'
    output.mkdir(exist_ok=False)
    run_manifest={'status':'running','started_at':datetime.now(timezone.utc).isoformat(),
                  'snapshot_hash':manifest['database_sha256'],'conventions_hash':manifest['conventions_sha256'],
                  'research_code_hash':sha256(__file__), 'params':LONG_PARAMS.model_dump(),
                  'production_code_hashes':{str(p.relative_to(ROOT)):sha256(p) for p in
                      [ROOT/'backend/app/features/signals/engine.py',ROOT/'backend/app/features/sizing/portfolio.py']},
                  'completed':[],'provisional':True,'quality_report':'../data-summary.json'}
    dump(output/'run.json',run_manifest)
    summary=[]
    for window in ['full','recent']:
        data=prepare(snapshot,window,quality)
        for scope in ['priority','universe']:
            for cost in ['normal','double']:
                for book in ['long-initial','buy-hold']:
                    name=f'{window}-{scope}-{cost}-{book}'
                    result=portfolio.simulate(data,scope,window,book,'equal',cost)
                    result['input_hash']=manifest['database_sha256']
                    result['provisional']=True
                    with gzip.open(output/(name+'.json.gz'),'wt',encoding='utf-8') as stream:
                        json.dump(result,stream,allow_nan=False)
                    row={'window':window,'scope':scope,'cost':cost,'book':book,'provisional':True,
                         **{k:v for k,v in result['stats'].items() if not isinstance(v,list)}}
                    summary.append(row)
                    run_manifest['completed'].append(name)
                    dump(output/'run.json',run_manifest)
                    print(name, f"CAGR={result['stats']['cagr']:.4%} DD={result['stats']['drawdown']:.4%}",flush=True)
        del data
    with (output/'summary.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(summary[0]));writer.writeheader();writer.writerows(summary)
    run_manifest.update(status='succeeded',finished_at=datetime.now(timezone.utc).isoformat())
    dump(output/'run.json',run_manifest)
    print('COMPLETE',output,flush=True)


if __name__=='__main__':
    current=json.loads((BASE/'current-snapshot.json').read_text(encoding='utf-8'))
    run(current['path'])
