"""Additional allocation checks and a compact interpretation of saved portfolios."""
import copy,gzip,json,math,pickle
from collections import defaultdict
from settings6 import *
from checks6 import fixture,verify
from portfolio6 import simulate


def allocation_checks():
    original=COSTS['normal'].copy();COSTS['normal'].update(bps=0.,atr=0.,borrow=0.)
    count=0
    try:
        # The symbol cap aggregates two opposing books instead of netting them.
        data=fixture([100.,100.,100.])
        data['tapes']['full']['baseline-short']=fixture([100.,100.,100.],True)['tapes']['full']['baseline-short']
        r=simulate(data,'priority','full','combined-channel','capped-vol','normal')
        assert sorted(t['units'] for t in r['trades'])==[-50.,50.]
        verify(r,data);count+=1
        # Ten same-class entries share a 70% class ceiling proportionally.
        template=fixture([100.,100.,100.]);data=copy.deepcopy(template)
        symbols=[f'TEST{i}' for i in range(10)]
        data['infos']={s:copy.deepcopy(template['infos']['TEST']) for s in symbols}
        data['market']={s:copy.deepcopy(template['market']['TEST']) for s in symbols}
        data['signals']['full']={s:copy.deepcopy(template['signals']['full']['TEST']) for s in symbols}
        data['sums']['priority']={'members':symbols,'count':[10]*3,'inverse':[10.]*3}
        event=template['tapes']['full'][RULES[0]][1][0]
        data['tapes']['full'][RULES[0]][1]=[{**event,'symbol':s} for s in symbols]
        first=simulate(data,'priority','full','long-channel','capped-vol','normal')
        assert all(abs(t['units']-70.)<1e-10 for t in first['trades'])
        assert abs(first['curve'][1][3]-70000.)<1e-8;verify(first,data);count+=1
        data['tapes']['full'][RULES[0]][1].reverse()
        second=simulate(data,'priority','full','long-channel','capped-vol','normal')
        assert {t['symbol']:t['units'] for t in first['trades']}=={t['symbol']:t['units'] for t in second['trades']};count+=1
        # Today's exit cannot fund another symbol's earlier daily open.
        data=fixture([100.,100.,100.],close=2)
        data['infos']['ALT']=copy.deepcopy(data['infos']['TEST'])
        data['market']['ALT']={'close':[100.,100.,100.],'inverse':[0.,0.,1.],'age':[1]*3}
        data['sums']['priority']={'members':['TEST','ALT'],'count':[1,1,2],'inverse':[1.,1.,2.]}
        data['signals']['full']['ALT']=copy.deepcopy(data['signals']['full']['TEST'])
        alt={**data['tapes']['full'][RULES[0]][1][0],'symbol':'ALT','entry_date':'2020-01-03',
             'exit_date':None,'exit_price':None,'exit_atr':None,'exit_t':None,'exit_reason':None}
        data['tapes']['full'][RULES[0]][2]=[alt]
        r=simulate(data,'priority','full','long-channel','equal','normal')
        assert len(r['trades'])==1 and r['audit']['unfunded']==1 and r['stats']['ending']==100000.
        verify(r,data);count+=1
    finally:COSTS['normal'].update(original)
    return count


def read(key):
    return json.loads(gzip.decompress((OUT/'cases'/f'{key}.json.gz').read_bytes()))


def main():
    extra=allocation_checks()
    results=json.loads((OUT/'results.json').read_text(encoding='utf-8'))
    verification=json.loads((OUT/'verification.json').read_text(encoding='utf-8'))
    bridges=0;error=0.
    for scope in ['priority','universe']:
        for window in WINDOWS:
            for cost in COSTS:
                for method in ['equal','inverse-vol']:
                    short=read('__'.join([scope,window,'short-reference',method,cost]))
                    for version in ['channel','initial']:
                        long=read('__'.join([scope,window,'long-'+version,method,cost]))
                        both=read('__'.join([scope,window,'combined-'+version,method,cost]))
                        e=max(abs((l[1]+s[1])/2-b[1]) for l,s,b in zip(long['curve'],short['curve'],both['curve']))
                        assert e<1e-5,(scope,window,method,cost,version,e)
                        error=max(error,e);bridges+=1
    with Path(__file__).with_name('prepared.pkl').open('rb') as f:data=pickle.load(f)['data']
    idx={d:i for i,d in enumerate(data['dates'])}
    exposure=[]
    for window in WINDOWS:
        for book in ['long-channel','long-initial']:
            for method in METHODS:
                key='__'.join(['priority',window,book,method,'normal']);r=read(key)
                equity={p[0]:p[1] for p in r['curve']};groups=defaultdict(float)
                for tr in r['trades']:
                    a=idx[tr['entry_date']];b=idx[tr['exit_date']] if tr['exit_date'] else len(data['dates'])
                    symbol=tr['symbol'];prices=data['market'][symbol]['close'];q=abs(tr['units'])
                    groups[data['infos'][symbol]['asset_class']]+=sum(q*prices[t]/equity[data['dates'][t]] for t in range(a,b))/len(r['curve'])
                assert math.isclose(sum(groups.values()),r['stats']['average_gross'],abs_tol=1e-8)
                exposure.append({'id':key,'average_exposure_by_class':dict(groups)})
    verification.update({'additional_allocation_checks':extra,'combined_sleeve_bridges':bridges,
                         'combined_maximum_error':error,'exposure_reconciliations':len(exposure),
                         'all_case_asset_counts_correct':all(len(read(r['id'])['assets'])==(60 if r['scope']=='priority' else 678) for r in results['cases'])})
    assert verification['all_case_asset_counts_correct']
    (OUT/'verification.json').write_text(json.dumps(verification,indent=2),encoding='utf-8')
    findings={'priority_comparison':[r for r in results['cases'] if r['scope']=='priority' and r['cost']=='normal'],
              'priority_exposure':exposure,
              'review_position':'Equal capital with 20/55 + initial 3 ATR is a reasonable balanced candidate for review. Channel-only remains a close comparison; no production rule is changed.',
              'interpretation':['Inverse volatility materially changes asset mix as well as drawdown; unspent cap allocations remain cash.',
                                'Short benchmark is retained with full sizing and ledger support; its losses do not justify optimising it during this long-focused stage.',
                                'Full-history and fresh-2020 portfolios share capital and dates within each window; these numbers are not directly comparable to Step 5 median instrument CAGRs or its asset-specific validation starts.',
                                'The fixed cap levels and initial 50/50 reference are demonstration choices, not optimised allocation recommendations.']}
    (OUT/'findings.json').write_text(json.dumps(findings,indent=2),encoding='utf-8')
    print(json.dumps(verification,indent=2))
    for e in exposure:
        if '__recent__' in e['id']:print(e['id'],e['average_exposure_by_class'])


if __name__=='__main__':main()
