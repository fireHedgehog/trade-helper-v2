"""Compare production fills and funded accounts with retained Step 6 evidence."""
import csv,gzip,json,pickle,sys,time
from pathlib import Path
from itertools import groupby
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'backend'))
from app.features.signals import engine
from app.features.signals.params import LONG_PARAMS,SHORT_PARAMS
from app.features.sizing.portfolio import simulate

def main():
    import bisect
    started=time.monotonic()
    with (ROOT/'backend/temp/step6/prepared.pkl').open('rb') as f:data=pickle.load(f)['data']
    params={'e20-x55-s0':LONG_PARAMS.model_copy(update={'initial_enabled':False}),
            'e20-x55-s3':LONG_PARAMS,'baseline-short':SHORT_PARAMS}
    expected={w:{k:{} for k in params} for w in ['full','recent']}
    for w in expected:
        for k in params:
            for events in data['tapes'][w][k]:
                for event in events:expected[w][k].setdefault(event['symbol'],[]).append(event)
    fields=['direction','entry_date','entry_price','exit_date','exit_price','exit_reason']
    signature=lambda trades:[[t[k] for k in fields] for t in trades]
    bridges=0
    with gzip.open(ROOT/'docs/temp/step1/inputs.csv.gz','rt',encoding='utf-8') as f:
        for symbol,rows in groupby(csv.DictReader(f),key=lambda r:r['symbol']):
            bars=[{k:float(v) if k in ('o','h','l','c') else v for k,v in r.items() if k in ('date','o','h','l','c')} for r in rows]
            dates=[b['date'] for b in bars]
            for w in expected:
                start=max(65,bisect.bisect_left(dates,'2020-01-01')) if w=='recent' else 65
                for k,p in params.items():
                    actual=engine.run(bars,p,start=start).trades
                    assert signature(actual)==signature(expected[w][k].get(symbol,[])),(symbol,w,k)
                    bridges+=1
            if bridges%600==0:print(f'Fill bridges {bridges}/4068',flush=True)
    cases=json.loads((ROOT/'docs/temp/step6/results.json').read_text(encoding='utf-8'))['cases']
    selected=[r for r in cases if r['book'] in ['long-initial','short-reference','combined-initial']]
    marks=0;error=0.
    for i,c in enumerate(selected):
        old=json.loads(gzip.decompress((ROOT/'docs/temp/step6/cases'/f'{c["id"]}.json.gz').read_bytes()))
        new=simulate(data,c['scope'],c['window'],c['book'],c['method'],c['cost'])
        assert new['trades']==old['trades'],c['id']
        assert new['assets']==old['assets'],c['id']
        e=max(abs(a[1]-b[1]) for a,b in zip(new['curve'],old['curve']))
        assert e<1e-6,(c['id'],e)
        error=max(error,e);marks+=len(new['curve'])
        if (i+1)%8==0:print(f'Portfolio bridges {i+1}/{len(selected)}',flush=True)
    result={'fill_bridges':bridges,'portfolio_bridges':len(selected),'daily_marks':marks,
            'maximum_equity_difference':error,'trade_ledgers_identical':True,'asset_contributions_identical':True,
            'seconds':round(time.monotonic()-started,1)}
    out=ROOT/'docs/temp/integration';out.mkdir(exist_ok=True)
    (out/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
