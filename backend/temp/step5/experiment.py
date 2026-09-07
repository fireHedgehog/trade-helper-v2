"""Full stored universe; frozen candidates, past-only selection and cost stress."""
import argparse,base64,bisect,csv,gzip,hashlib,io,json,math,os,time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor,wait,FIRST_COMPLETED
from datetime import datetime,timezone
from itertools import groupby
from pathlib import Path
from settings import ROOT,OUT,RULES,BY_ID,ANCHORS,POLICIES,LABELS,YEARS,LENGTHS,AUDIT,COSTS,LEDGER,ResearchParams,asset_class
from calculations import window,eligible_years,evaluate,compact,detail
import engine5,reference5
import research_engine as previous_engine
import cash as cash_module
from app.features.signals import engine as production,indicators

PARAMS={r['id']:ResearchParams(**r['params']) for r in RULES}
PARTITIONS=[f'e{n}' for n in [5,10,15,20,25,30]]+['baseline','adaptive']

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def prepare(bars):
    h,l,c=([b[k] for b in bars] for k in ('h','l','c'))
    return {'atr':indicators.wilder_atr(h,l,c,20),'channels':{n:indicators.donchian(h,l,n) for n in LENGTHS}}

def tasks(infos,subset=None):
    with gzip.open(ROOT/'docs/temp/step1/inputs.csv.gz','rt',encoding='utf-8',newline='') as f:
        for symbol,rows in groupby(csv.DictReader(f),key=lambda r:r['symbol']):
            bars=[{k:float(v) if k in ('o','h','l','c','v') else v for k,v in r.items() if k!='symbol'} for r in rows]
            if subset is None or symbol in subset:yield infos[symbol],bars

def write_display(symbol,data):
    zipped=base64.b64encode(gzip.compress(json.dumps(data,allow_nan=False,separators=(',',':')).encode(),compresslevel=6)).decode()
    script=('window.step5Ready=window.step5Ready||{};window.step5Ready['+json.dumps(symbol)+
            ']=new Response(new Blob([Uint8Array.from(atob('+json.dumps(zipped)+'),c=>c.charCodeAt(0))]).stream().pipeThrough(new DecompressionStream("gzip"))).json();')
    (OUT/'instruments'/(symbol.replace('/','_')+'.js')).write_text(script,encoding='utf-8')

def phase_one(task):
    info,bars=task;symbol=info['symbol'];dates=[b['date'] for b in bars]
    eligible=eligible_years(dates);start=bisect.bisect_left(dates,f'{eligible[0]}-01-01') if eligible else None
    prepared=prepare(bars);independent=reference5.prepare(bars) if symbol in AUDIT else None
    results={};training={str(y):{} for y in eligible};displays={}
    buffers={p:io.StringIO(newline='') for p in PARTITIONS};writers={p:csv.writer(b) for p,b in buffers.items()}
    checks={'fill_bridge':0,'cash_bars':0,'cash_error':0.,'identity_error':0.,'signal_runs':0}
    for r in RULES:
        key=r['id'];p=PARAMS[key]
        full_trades=engine5.run(bars,(key,p),prepared)
        assert engine5.signature(full_trades)==engine5.signature(previous_engine.run(bars,p,prepared).trades),(symbol,key,'Step 3 fill bridge')
        checks['fill_bridge']+=1
        periods={}
        for period,offset,trades in [('full',0,full_trades)]+([('validation',start,engine5.run(bars,(key,p),prepared,start))] if start is not None else []):
            checks['signal_runs']+=1
            values=evaluate(bars,trades,prepared['atr'],offset)
            periods[period]=compact(values)
            displays.setdefault(key,{})[period]=detail(values,dates,offset)
            if independent and key in ANCHORS+['baseline-long','baseline-short']:
                for cost in ['normal','double']:
                    ref=reference5.run(bars,(key,p),independent,offset,bps=COSTS[cost][0],slip=COSTS[cost][1])
                    curve=values[cost]['account']['curve']
                    error=max(abs(a/10000-b)/max(1,abs(b)) for a,b in zip(curve,ref))
                    assert error<1e-9,(symbol,key,period,cost,error)
                    checks['cash_error']=max(checks['cash_error'],error);checks['cash_bars']+=len(ref)
            partition='baseline' if not r['tuned'] else 'e'+str(r['entry'])
            for cost in ['normal','double']:
                a=values[cost]['account'];checks['identity_error']=max(checks['identity_error'],a['identity_error'])
                for tr,signal in zip(a['ledger'],trades):
                    writers[partition].writerow([symbol,key,period,cost,signal['rule'],*tr])
            if period=='full' and r['tuned']:
                for year in eligible:
                    lo=bisect.bisect_left(dates,f'{year-3}-01-01');hi=bisect.bisect_left(dates,f'{year}-01-01')
                    stat=window(values['normal']['account']['curve'],dates,lo,hi)
                    stat['trades']=sum(t[3] is not None and dates[lo]<=t[3]<f'{year}-01-01' for t in values['normal']['account']['ledger'])
                    assert stat['end']<f'{year}-01-01'
                    training[str(year)][key]=stat
        results[key]=periods
    asset={k:info[k] for k in ['symbol','priority','group']}
    asset.update(asset_class=asset_class(info),start=dates[0],end=dates[-1],bars=len(bars),eligible_years=eligible,
                 validation_start=dates[start] if start is not None else None,results=results,training=training,checks=checks)
    file=symbol.replace('/','_')
    (OUT/'summaries'/f'{file}.json').write_text(json.dumps(asset,allow_nan=False,separators=(',',':')),encoding='utf-8')
    (OUT/'details'/f'{file}.json.gz').write_bytes(gzip.compress(json.dumps({'symbol':symbol,'variants':displays},allow_nan=False,separators=(',',':')).encode(),compresslevel=6))
    return {**{k:v for k,v in asset.items() if k not in ['results','training']},'csv':{k:b.getvalue() for k,b in buffers.items()}}

def phase_two(task):
    info,bars=task;symbol=info['symbol'];file=symbol.replace('/','_');dates=[b['date'] for b in bars]
    asset=json.loads((OUT/'summaries'/f'{file}.json').read_text(encoding='utf-8'))
    display=json.loads(gzip.decompress((OUT/'details'/f'{file}.json.gz').read_bytes()))
    prepared=prepare(bars);checks=asset['checks'];buf=io.StringIO(newline='');writer=csv.writer(buf)
    eligible=asset['eligible_years'];schedules={}
    if eligible:
        start=bisect.bisect_left(dates,asset['validation_start'])
        independent=reference5.prepare(bars) if symbol in AUDIT else None
        for policy in ['adaptive-common','adaptive-class']:
            picked={year:info['selections'][str(year)]['Common' if policy=='adaptive-common' else asset['asset_class']]['rule'] for year in eligible}
            schedule={year:(key,PARAMS[key]) for year,key in picked.items()}
            first=schedule[eligible[0]]
            trades=engine5.run(bars,first,prepared,start,schedule)
            checks['signal_runs']+=1
            values=evaluate(bars,trades,prepared['atr'],start)
            asset['results'][policy]={'validation':compact(values)}
            display['variants'][policy]={'validation':detail(values,dates,start)}
            schedules[policy]={str(y):key for y,key in picked.items()}
            for cost in ['normal','double']:
                a=values[cost]['account'];checks['identity_error']=max(checks['identity_error'],a['identity_error'])
                for tr,signal in zip(a['ledger'],trades):writer.writerow([symbol,policy,'validation',cost,signal['rule'],*tr])
                if independent:
                    ref=reference5.run(bars,first,independent,start,schedule,*COSTS[cost])
                    error=max(abs(a/10000-b)/max(1,abs(b)) for a,b in zip(values[cost]['account']['curve'],ref))
                    assert error<1e-9,(symbol,policy,cost,error)
                    checks['cash_error']=max(checks['cash_error'],error);checks['cash_bars']+=len(ref)
    asset['schedules']=schedules
    sample=sorted({0,len(bars)-1,*range(4,len(bars),5)})
    display['buy_hold']={'dates':[dates[i] for i in sample],'curve':[round(bars[i]['c']/bars[0]['c']*10000,6) for i in sample]}
    write_display(symbol,display)
    # This compressed payload is also the portable, non-browser JSON artifact.
    (OUT/'details'/f'{file}.json.gz').write_bytes(gzip.compress(json.dumps(display,allow_nan=False,separators=(',',':')).encode(),compresslevel=6))
    (OUT/'summaries'/f'{file}.json').write_text(json.dumps(asset,allow_nan=False,separators=(',',':')),encoding='utf-8')
    return {**{k:v for k,v in asset.items() if k not in ['results','training']},'csv':{'adaptive':buf.getvalue()}}

def execute(worker,iterator,total,workers,streams,stage):
    results=[];started=time.monotonic();iterator=iter(iterator)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending=set()
        for _ in range(workers*2):
            task=next(iterator,None)
            if task is not None:pending.add(pool.submit(worker,task))
        while pending:
            done,pending=wait(pending,return_when=FIRST_COMPLETED)
            for future in done:
                item=future.result()
                for key,value in item.pop('csv').items():streams[key].write(value)
                results.append(item)
                task=next(iterator,None)
                if task is not None:pending.add(pool.submit(worker,task))
                if len(results)%40==0 or len(results)==total:print(f'{stage}: {len(results)}/{total} assets, {time.monotonic()-started:.0f}s',flush=True)
    assert len(results)==total
    return sorted(results,key=lambda s:s['symbol'])

def main():
    from selection import select_rules
    parser=argparse.ArgumentParser();parser.add_argument('--symbols');parser.add_argument('--workers',type=int,default=6);args=parser.parse_args()
    started=time.monotonic()
    for p in [OUT,OUT/'summaries',OUT/'details',OUT/'instruments']:p.mkdir(parents=True,exist_ok=True)
    previous=json.loads((ROOT/'docs/temp/step4/results.json').read_text(encoding='utf-8'))
    assert not previous['metadata']['partial']
    assert sha(production.__file__)==previous['metadata']['engine_sha256']
    assert sha(cash_module.__file__)==previous['metadata']['cash_sha256']
    assert sha(ROOT/'docs/temp/step1/inputs.csv.gz')==previous['metadata']['inputs_sha256']
    infos={s['symbol']:s for s in previous['instruments']}
    subset=set(args.symbols.split(',')) if args.symbols else None;total=len(subset) if subset else len(infos)
    streams={key:gzip.open(OUT/f'trades-{key}.csv.gz','wt',encoding='utf-8',newline='',compresslevel=6) for key in PARTITIONS}
    for stream in streams.values():csv.writer(stream).writerow(['symbol','scenario','period','cost','entry_rule',*LEDGER])
    try:
        assets=execute(phase_one,tasks(infos,subset),total,args.workers,streams,'Fixed rules and training windows')
        selections=select_rules(assets,partial=bool(subset))
        (OUT/'selections.json').write_text(json.dumps(selections,allow_nan=False,indent=2),encoding='utf-8')
        infos={s['symbol']:{**s,'selections':selections} for s in assets}
        assets=execute(phase_two,tasks(infos,subset),total,args.workers,streams,'Rolling common / class policies')
    finally:
        for stream in streams.values():stream.close()
    meta={'stage':'5 / Long strategy validation','generated_utc':datetime.now(timezone.utc).isoformat(),'partial':bool(subset),
          'symbol_count':total,'validation_assets':sum(bool(s['eligible_years']) for s in assets),'rules':RULES,'policies':POLICIES,
          'labels':LABELS,'years':YEARS,'costs':COSTS,'ledger_fields':LEDGER,'priority_symbols':previous['metadata']['priority_symbols'],
          'signal_runs':sum(s['checks']['signal_runs'] for s in assets),'account_scenarios':3*sum(s['checks']['signal_runs'] for s in assets),
          'fill_bridge_checks':sum(s['checks']['fill_bridge'] for s in assets),'cash_audit_bars':sum(s['checks']['cash_bars'] for s in assets),
          'cash_max_error':max(s['checks']['cash_error'] for s in assets),'identity_max_error':max(s['checks']['identity_error'] for s in assets),
          'engine_sha256':sha(production.__file__),'cash_sha256':sha(cash_module.__file__),'research_sha256':sha(engine5.__file__),
          'inputs_sha256':previous['metadata']['inputs_sha256'],'elapsed_seconds':round(time.monotonic()-started,1)}
    (OUT/'results.json').write_text(json.dumps({'metadata':meta,'instruments':assets},allow_nan=False,separators=(',',':')),encoding='utf-8')
    assert meta['engine_sha256']==previous['metadata']['engine_sha256'] and meta['cash_sha256']==previous['metadata']['cash_sha256']
    print(json.dumps({k:v for k,v in meta.items() if k not in ['rules','policies','labels','years','costs','ledger_fields','priority_symbols']}),flush=True)

if __name__=='__main__':main()
