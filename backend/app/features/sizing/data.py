"""Past-only daily marks, volatility weights and production signal fills."""
import bisect
import math
from array import array
from datetime import date, timedelta

from app.features.signals import data as prices, engine, indicators, repository
from app.features.signals.params import SignalParams, LONG_PARAMS, SHORT_PARAMS
from app.features.sizing.params import (PRIORITY, RULES, WINDOWS, VOL_BARS, VOL_FLOOR,
    COMMON_WARMUP, MAX_STALE_DAYS, asset_class)


def rolling_vol(closes, crypto=False):
    """60-return sample volatility; an observation uses no later close."""
    result=[0.]*len(closes);returns=[0.]+[closes[i]/closes[i-1]-1 for i in range(1,len(closes))]
    total=squares=0.;annual=365 if crypto else 252
    for i in range(1,len(closes)):
        r=returns[i];total+=r;squares+=r*r
        if i>VOL_BARS:
            old=returns[i-VOL_BARS];total-=old;squares-=old*old
        if i>=VOL_BARS:
            variance=max(0.,(squares-total*total/VOL_BARS)/(VOL_BARS-1))
            result[i]=max(VOL_FLOOR,math.sqrt(variance*annual))
    return result


def prepare(conn, request, progress=None):
    info={}
    for table,condition in [('price_bars','WHERE adj_close IS NOT NULL'),('crypto_bars','')]:
        for r in conn.execute(f'SELECT symbol, MIN(date) first, MAX(date) last, COUNT(*) bars FROM {table} {condition} GROUP BY symbol'):
            s=r['symbol']
            if request.scope=='priority' and s not in PRIORITY:continue
            info[s]={'symbol':s,'start':r['first'],'end':r['last'],'bars':r['bars'],
                     'priority':s in PRIORITY,'group':asset_class(s),'asset_class':asset_class(s)}
    if not info:raise ValueError('No stored price history for this universe. Fetch prices first.')
    origin=date.fromisoformat(min(a['start'] for a in info.values()))
    end=date.fromisoformat(max(a['end'] for a in info.values()))
    dates=[(origin+timedelta(days=t)).isoformat() for t in range((end-origin).days+1)]
    n=len(dates);market={};window=request.window
    tapes={window:{key:[[] for _ in dates] for key in RULES+['buy-hold']}}
    signals={window:{s:{key:0 for key in RULES} for s in info}}
    assigned=repository.resolve_symbol_params(conn);default=repository.default_strategy(conn)
    for number,symbol in enumerate(sorted(info)):
        if progress:progress(symbol,number,len(info))
        bars=prices.load_ohlc(conn,symbol)
        if not bars:raise ValueError(f'{symbol}: stored history contains no usable OHLC bars')
        ds=[b['date'] for b in bars];indices={d:i for i,d in enumerate(ds)}
        h,l,c=([b[k] for b in bars] for k in ('h','l','c'))
        long=SignalParams(**(assigned.get(symbol) or default)['params']).model_copy(update={'allow_long':True,'allow_short':False})
        info[symbol]['long_params']=long.model_dump()
        atr=indicators.wilder_atr(h,l,c,20)
        vol=rolling_vol(c,'/' in symbol)
        closes,inverse,age=array('d',[0.])*n,array('d',[0.])*n,array('i',[99999])*n
        j=-1
        for t,day in enumerate(dates):
            while j+1<len(ds) and ds[j+1]<day:j+=1
            if j>=0:
                age[t]=(date.fromisoformat(day)-date.fromisoformat(ds[j])).days
                if j>=COMMON_WARMUP and age[t]<=MAX_STALE_DAYS:inverse[t]=1/vol[j]
            mark=j+1 if j+1<len(ds) and ds[j+1]==day else j
            if mark>=0:closes[t]=c[mark]
        market[symbol]={'close':closes,'inverse':inverse,'age':age}
        start=max(COMMON_WARMUP,bisect.bisect_left(ds,WINDOWS[window]))
        params={RULES[0]:long.model_copy(update={'initial_enabled':False,'trailing_enabled':False}),
                RULES[1]:long,RULES[2]:SHORT_PARAMS}
        for key,p in params.items():
            trades=engine.run(bars,p,start=start).trades
            signals[window][symbol][key]=len(trades)
            for tr in trades:
                i=indices[tr['entry_date']];j=indices[tr['exit_date']] if tr['exit_date'] else None
                t=(date.fromisoformat(tr['entry_date'])-origin).days
                tapes[window][key][t].append({**tr,'symbol':symbol,'rule':key,'entry_atr':atr[i-1],
                    'exit_atr':atr[j-1] if j is not None else None,
                    'exit_t':(date.fromisoformat(tr['exit_date'])-origin).days if j is not None else None})
        i=start+1
        if i<len(bars):
            t=(date.fromisoformat(ds[i])-origin).days
            tapes[window]['buy-hold'][t].append({'symbol':symbol,'direction':'long','rule':'buy-hold',
                'entry_date':ds[i],'entry_price':bars[i]['o'],'entry_atr':atr[i-1],
                'exit_date':None,'exit_price':None,'exit_atr':None,'exit_reason':None,'exit_t':None})
    counts,inverse=array('i',[0])*n,array('d',[0.])*n
    for values in market.values():
        for t,v in enumerate(values['inverse']):
            if v:counts[t]+=1;inverse[t]+=v
    return {'dates':dates,'infos':info,'market':market,'tapes':tapes,'signals':signals,
            'sums':{request.scope:{'members':sorted(info),'count':counts,'inverse':inverse}}}
