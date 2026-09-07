"""Saved-ledger checks, unchanged-history bridge and past-only selection audit."""
import csv,gzip,json,math,hashlib
from collections import Counter
from itertools import groupby
from settings import ROOT,OUT,RULES,ANCHORS,YEARS
from selection import select_rules

def main():
    manifest=json.loads((OUT/'results.json').read_text(encoding='utf-8'));meta=manifest['metadata']
    assert not meta['partial'] and meta['symbol_count']==678
    assets=[json.loads((OUT/'summaries'/(s['symbol'].replace('/','_')+'.json')).read_text(encoding='utf-8')) for s in manifest['instruments']]
    original=json.loads((OUT/'selections.json').read_text(encoding='utf-8'))
    assert select_rules([],data=assets)==original
    # Remove every evaluation result and corrupt later training windows. An
    # earlier choice must remain identical because none of those fields is read.
    changed=[]
    for s in assets:
        training={year:{key:{**r,'cagr':1000000. if year>'2023' else r['cagr']} for key,r in rows.items()} for year,rows in s['training'].items()}
        changed.append({**s,'results':{},'training':training})
    altered=select_rules([],data=changed)
    assert all(original[y]==altered[y] for y in original if y<='2023')
    prior=json.loads((ROOT/'docs/temp/step3/results.json').read_text(encoding='utf-8'))
    old={s['symbol']:{(r[0],r[1]):dict(zip(prior['metadata']['fields'],r)) for r in s['rows']} for s in prior['instruments']}
    bridge=0;expected={};all_scenarios=0
    old_ids={'e10-x55-s2':'channel_initial-e10-x55-i2-t3','e20-x55-s3':'channel_initial-e20-x55-i3-t3','e20-x55-s0':'channel-e20-x55-i2-t3'}
    for s in assets:
        assert len([k for k in s['results'] if k not in ['adaptive-common','adaptive-class']])==56
        for key,old_id in old_ids.items():
            new=s['results'][key]['full']['normal']['stats'];previous=old[s['symbol']][(old_id,'long')]
            for field in ['net','cagr','drawdown','ending','fees','slippage']:
                assert math.isclose(new[field],previous[field],rel_tol=1e-10,abs_tol=1e-7),(s['symbol'],key,field)
            bridge+=1
        display=json.loads(gzip.decompress((OUT/'details'/(s['symbol'].replace('/','_')+'.json.gz')).read_bytes()))
        assert set(display['variants'])==set(s['results'])
        for key,periods in s['results'].items():
            for period,costs in periods.items():
                for cost,value in costs.items():
                    all_scenarios+=1;r=value['stats']
                    assert math.isclose(10000+r['price_pnl']-r['fees']-r['slippage'],r['ending'],rel_tol=1e-10,abs_tol=1e-7)
                    if cost=='gross':continue
                    ledger=display['variants'][key][period]['ledgers'][cost]
                    curve=display['variants'][key][period]['curves'][cost]
                    assert abs(curve[-1]-r['ending'])<=.000001
                    assert sum(bool(t[3]) for t in ledger)==r['trades']
                    assert math.isclose(ledger[-1][11] if ledger else 10000.,r['ending'],rel_tol=1e-10,abs_tol=1e-7)
                    expected[(s['symbol'],key,period,cost)]=(len(ledger),r['trades'],r['price_pnl'],r['fees'],r['slippage'],r['ending'])
    assert all_scenarios==meta['account_scenarios']
    with gzip.open(OUT/'summary.csv.gz','rt',encoding='utf-8',newline='') as f:assert sum(1 for _ in csv.DictReader(f))==all_scenarios
    seen=set();closed_total=marks=0
    for path in sorted(OUT.glob('trades-*.csv.gz')):
        with gzip.open(path,'rt',encoding='utf-8',newline='') as f:
            for key,rows in groupby(csv.DictReader(f),key=lambda r:(r['symbol'],r['scenario'],r['period'],r['cost'])):
                assert key not in seen;seen.add(key);target=expected[key]
                count=closed=0;pnl=fees=slip=0.;ending=10000.;last=None
                for row in rows:
                    assert last is None or row['entry_date']>last
                    assert row['entry_rule'] in {r['id'] for r in RULES}
                    before=float(row['starting_equity']);after=float(row['ending_equity']);price=float(row['price_pnl']);fee=float(row['fees']);charge=float(row['slippage'])
                    assert math.isclose(before,ending,rel_tol=1e-10,abs_tol=1e-7)
                    assert math.isclose(before+price-fee-charge,after,rel_tol=1e-10,abs_tol=1e-7)
                    ending=after;pnl+=price;fees+=fee;slip+=charge;count+=1;closed+=bool(row['exit_date']);last=row['mark_date']
                assert (count,closed)==target[:2],key
                for a,b in zip((pnl,fees,slip,ending),target[2:]):assert math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-6),key
                closed_total+=closed;marks+=count-closed
        print('Verified '+path.name,flush=True)
    assert seen=={key for key,value in expected.items() if value[0]}
    assert all(p.stat().st_size<100*1024*1024 for p in OUT.rglob('*') if p.is_file())
    assert hashlib.sha256((ROOT/'backend/app/features/signals/engine.py').read_bytes()).hexdigest()==meta['engine_sha256']
    result={'account_scenarios':all_scenarios,'closed_trades_across_cost_scenarios':closed_total,'open_or_exhaustion_marks':marks,
            'saved_step3_anchor_bridges':bridge,'past_only_selection_check':True,'portable_json_and_csv_reconcile':True,'all_files_under_100MiB':True}
    (OUT/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
