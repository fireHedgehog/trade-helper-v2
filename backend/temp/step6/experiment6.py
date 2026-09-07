"""Run Step 6 and retain all results, including every asset and both directions."""
import csv,gzip,hashlib,json,pickle,time
from datetime import datetime,timezone
from settings6 import *
from prepare6 import prepare,sha
from portfolio6 import simulate,CURVE_FIELDS
from checks6 import check,verify


def dump(path,value):
    encoded=json.dumps(value,allow_nan=False,separators=(',',':')).encode()
    if str(path).endswith('.gz'):path.write_bytes(gzip.compress(encoded,compresslevel=6))
    else:path.write_bytes(encoded)


def main():
    started=time.monotonic();OUT.mkdir(parents=True,exist_ok=True);(OUT/'cases').mkdir(exist_ok=True)
    unit_checks=check()
    cache=Path(__file__).with_name('prepared.pkl')
    sources={p.name:sha(p) for p in [Path(__file__).with_name('prepare6.py'),Path(__file__).with_name('settings6.py'),
                                    ROOT/'backend/temp/step5/engine5.py',ROOT/'docs/temp/step1/inputs.csv.gz']}
    if cache.exists():
        with cache.open('rb') as f:cached=pickle.load(f)
        data=cached['data'] if cached['sources']==sources else None
    else:data=None
    if data is None:
        data=prepare()
        with cache.open('wb') as f:pickle.dump({'sources':sources,'data':data},f,pickle.HIGHEST_PROTOCOL)
    print(f'Prepared {len(data["infos"])} assets, {len(data["sums"]["priority"]["members"])} priority',flush=True)
    verification={'hand_checks':unit_checks,**data['checks'],'saved_trades':0,'daily_marks':0,'maximum_replay_error':0.}
    cases=[];jobs=[]
    for scope in ['priority','universe']:
        for window in WINDOWS:
            for cost in COSTS:
                jobs.extend((scope,window,book,method,cost) for book in BOOKS for method in METHODS)
                jobs.append((scope,window,'buy-hold','equal',cost))
    for i,args in enumerate(jobs):
        result=simulate(data,*args)
        key='__'.join(args)
        dump(OUT/'cases'/f'{key}.json.gz',result)
        # Verify what was actually written, rather than just the in-memory object.
        saved=json.loads(gzip.decompress((OUT/'cases'/f'{key}.json.gz').read_bytes()))
        checked=verify(saved,data)
        verification['saved_trades']+=checked['trades'];verification['daily_marks']+=checked['daily_marks']
        verification['maximum_replay_error']=max(verification['maximum_replay_error'],checked['maximum_error'])
        cases.append({k:v for k,v in result.items() if k not in ('curve','trades','assets')} | {'id':key})
        print(f'{i+1}/{len(jobs)} {key}: CAGR {result["stats"]["cagr"]:.2%}, DD {result["stats"]["drawdown"]:.2%}; {time.monotonic()-started:.0f}s',flush=True)
    metadata={'created_utc':datetime.now(timezone.utc).isoformat(),'assets':len(data['infos']),
              'priority_assets':len(data['sums']['priority']['members']),'cases':len(cases),'assumptions':ASSUMPTIONS,
              'inputs_sha256':data['inputs_sha256'],'code_sha256':{p.name:sha(p) for p in Path(__file__).parent.glob('*.py')},
              'elapsed_seconds':round(time.monotonic()-started,1),'curve_fields':CURVE_FIELDS,
              'start':data['dates'][0],'end':data['dates'][-1],
              'insufficient_warmup':[s for s,a in data['infos'].items() if a['bars']<=COMMON_WARMUP+1]}
    dump(OUT/'results.json',{'metadata':metadata,'cases':cases,'instruments':list(data['infos'].values())})
    dump(OUT/'verification.json',verification)
    rows=[]
    for r in cases:
        rows.append({k:r[k] for k in ['id','scope','window','book','method','cost']} |
                    {k:v for k,v in r['stats'].items() if k!='annual'} | r['audit'])
    with (OUT/'comparison.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with gzip.open(OUT/'asset-contributions.csv.gz','wt',encoding='utf-8',newline='') as f:
        writer=None
        for r in cases:
            d=json.loads(gzip.decompress((OUT/'cases'/f'{r["id"]}.json.gz').read_bytes()))
            for asset in d['assets']:
                row={'case':r['id'],**asset}
                if writer is None:writer=csv.DictWriter(f,fieldnames=list(row));writer.writeheader()
                writer.writerow(row)
    print(json.dumps(verification),flush=True)


if __name__=='__main__':main()
