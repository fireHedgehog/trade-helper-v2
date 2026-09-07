"""Annual choices read training records only; test returns never enter selection."""
import json,statistics
from settings import OUT,RULES,YEARS

def select_rules(assets,partial=False,data=None):
    if data is None:data=[json.loads((OUT/'summaries'/(s['symbol'].replace('/','_')+'.json')).read_text(encoding='utf-8')) for s in assets]
    selected={}
    for year in YEARS:
        priority=[s for s in data if s['priority'] and str(year) in s['training']]
        if not priority:continue
        selected[str(year)]={}
        for group in ['Common','Equities and other ETFs','Bonds','Crypto']:
            members=[s for s in priority if group=='Common' or s['asset_class']==group]
            minimum=2 if group=='Crypto' else 5
            if group!='Common' and len(members)<minimum:
                selected[str(year)][group]={**selected[str(year)]['Common'],'fallback':True,'group_members':len(members)}
                continue
            ranked=[]
            for r in RULES:
                if not r['tuned']:continue
                records=[s['training'][str(year)][r['id']] for s in members]
                assert records and all(x['end']<f'{year}-01-01' for x in records)
                median=statistics.median(x['cagr'] if x['cagr'] is not None else -1. for x in records)
                ranked.append((median,r['id']))
            ranked.sort(key=lambda v:(-v[0],v[1]))
            selected[str(year)][group]={'rule':ranked[0][1],'training_median_cagr':ranked[0][0],
                 'training_start':f'{year-3}-01-01','training_cutoff':f'{year-1}-12-31','fallback':False,
                 'group_members':len(members),'members':[s['symbol'] for s in members]}
    return selected
