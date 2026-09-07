import bisect
from datetime import date
from settings import YEARS,COSTS
from cash import account


def window(curve,dates,lo=0,hi=None,flat=False):
    hi=len(dates) if hi is None else hi
    if hi<=lo:return None
    base=10000. if flat or lo==0 else curve[lo-1]
    origin=dates[lo] if flat or lo==0 else dates[lo-1]
    days=(date.fromisoformat(dates[hi-1])-date.fromisoformat(origin)).days
    peak=base;dd=0.
    for value in curve[lo:hi]:
        peak=max(peak,value)
        dd=min(dd,value/peak-1 if peak>0 else -1.)
    value=curve[hi-1]/base if base>0 else None
    return {'net':value-1 if value is not None else None,
            'cagr':value**(365.25/days)-1 if value and value>0 and days>0 else None,
            'drawdown':dd,'days':days,'start':dates[lo],'end':dates[hi-1]}


def eligible_years(dates):
    result=[]
    for year in YEARS:
        train_start=f'{year-3}-01-01';test_start=f'{year}-01-01'
        lo,hi=bisect.bisect_left(dates,train_start),bisect.bisect_left(dates,test_start)
        if lo<81 or hi>=len(dates) or hi-lo<600:continue
        if (date.fromisoformat(dates[lo])-date(year-3,1,1)).days>7:continue
        if (date(year,1,1)-date.fromisoformat(dates[hi-1])).days>10:continue
        if (date.fromisoformat(dates[hi])-date(year,1,1)).days>10:continue
        result.append(year)
    return result


def evaluate(bars,trades,atr,start=0):
    dates=[b['date'] for b in bars]
    result={}
    for name,(bps,slip) in COSTS.items():
        a=account(bars,trades,atr,bps,slip)
        stat=window(a['curve'],dates,start,flat=True)
        stat.update({k:a[k] for k in ['ending','price_pnl','fees','slippage','exhausted','identity_error','unfunded_signals']})
        stat['trades']=sum(bool(t[3]) for t in a['ledger'])
        yearly={}
        for year in YEARS:
            lo=max(start,bisect.bisect_left(dates,f'{year}-01-01'))
            hi=bisect.bisect_left(dates,f'{year+1}-01-01')
            if hi>lo:
                y=window(a['curve'],dates,lo,hi,flat=lo==start)
                y['trades']=sum(t[3] is not None and dates[lo]<=t[3]<=dates[hi-1] for t in a['ledger'])
                yearly[str(year)]=y
        result[name]={'stats':stat,'years':yearly,'account':a}
    if not result['normal']['stats']['exhausted']:
        assert result['gross']['stats']['ending']+1e-7>=result['normal']['stats']['ending']>=result['double']['stats']['ending']-1e-7
    return result


def compact(result):
    return {cost:{'stats':v['stats'],'years':v['years']} for cost,v in result.items()}


def detail(result,dates,start=0):
    sample=sorted({start,len(dates)-1,*range(start+4,len(dates),5)})
    return {'dates':[dates[i] for i in sample],
            'curves':{c:[round(v['account']['curve'][i],6) for i in sample] for c,v in result.items()},
            'ledgers':{c:result[c]['account']['ledger'] for c in ['normal','double']}}
