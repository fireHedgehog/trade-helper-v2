"""Build a reusable daily price matrix and native trade tapes from frozen data."""
import bisect, csv, gzip, hashlib, json, math, statistics
from array import array
from datetime import date, timedelta
from itertools import groupby
from settings6 import *
import engine5
import research_engine
from app.features.signals import indicators, engine as production


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare():
    previous = json.loads((ROOT/'docs/temp/step5/results.json').read_text(encoding='utf-8'))
    assert not previous['metadata']['partial']
    for path, key in [(ROOT/'docs/temp/step1/inputs.csv.gz', 'inputs_sha256'),
                      (production.__file__, 'engine_sha256')]:
        assert sha(path) == previous['metadata'][key], (path, 'changed since Step 5')
    infos = {s['symbol']: {k:s[k] for k in ['symbol','priority','group','asset_class','start','end','bars']}
             for s in previous['instruments']}
    origin = date.fromisoformat(min(s['start'] for s in infos.values()))
    end = date.fromisoformat(max(s['end'] for s in infos.values()))
    dates = [(origin+timedelta(days=i)).isoformat() for i in range((end-origin).days+1)]
    n = len(dates)
    market = {}
    tapes = {w:{k:[[] for _ in dates] for k in RULES+['buy-hold']} for w in WINDOWS}
    checks = {'unchanged_fill_bridges': 0, 'past_only_volatility': 0, 'prefix_signal_checks': 0}
    signals = {w:{s:{k:0 for k in RULES} for s in infos} for w in WINDOWS}
    with gzip.open(ROOT/'docs/temp/step1/inputs.csv.gz','rt',encoding='utf-8',newline='') as f:
        for symbol, rows in groupby(csv.DictReader(f), key=lambda r:r['symbol']):
            bars = [{k:float(v) if k in ('o','h','l','c') else v for k,v in r.items()
                     if k in ('date','o','h','l','c')} for r in rows]
            ds = [b['date'] for b in bars]
            index = {d:i for i,d in enumerate(ds)}
            h,l,c = ([b[k] for b in bars] for k in ('h','l','c'))
            atr = indicators.wilder_atr(h,l,c,20)
            prep = {'atr':atr, 'channels':{k:indicators.donchian(h,l,k) for k in (20,55)}}
            # The signal calculation itself is identical to the previous stage.
            for key,p in PARAMS.items():
                assert engine5.signature(engine5.run(bars,(key,p),prep)) == engine5.signature(research_engine.run(bars,p,prep).trades)
                checks['unchanged_fill_bridges'] += 1
            closes, inverse, age = array('d',[0.])*n, array('d',[0.])*n, array('i',[99999])*n
            returns = [0.]+[c[i]/c[i-1]-1 for i in range(1,len(c))]
            vol = [0.]*len(c)
            annual = 365 if '/' in symbol else 252
            for i in range(VOL_BARS,len(c)):
                vol[i] = max(VOL_FLOOR,statistics.stdev(returns[i-VOL_BARS+1:i+1])*math.sqrt(annual))
            j = -1
            for t,day in enumerate(dates):
                # Weight inputs use strictly earlier bars; closing marks may use today.
                while j+1<len(ds) and ds[j+1]<day:j+=1
                if j>=0:
                    age[t] = (date.fromisoformat(day)-date.fromisoformat(ds[j])).days
                    if j>=COMMON_WARMUP and age[t]<=MAX_STALE_DAYS:
                        inverse[t] = 1/vol[j]
                        assert ds[j]<day
                        checks['past_only_volatility'] += 1
                mark = j+1 if j+1<len(ds) and ds[j+1]==day else j
                if mark>=0:closes[t]=c[mark]
            market[symbol] = {'close':closes,'inverse':inverse,'age':age}
            for window,begin in WINDOWS.items():
                start = max(COMMON_WARMUP,bisect.bisect_left(ds,begin))
                for key,p in PARAMS.items():
                    trades = engine5.run(bars,(key,p),prep,start=start)
                    signals[window][symbol][key] = len(trades)
                    for tr in trades:
                        i=index[tr['entry_date']]
                        end_i=index[tr['exit_date']] if tr['exit_date'] else None
                        t=(date.fromisoformat(tr['entry_date'])-origin).days
                        assert i>start and ds[i-1]<tr['entry_date']
                        event={**tr,'symbol':symbol,'entry_atr':atr[i-1],
                               'exit_atr':atr[end_i-1] if end_i is not None else None,
                               'exit_t':(date.fromisoformat(tr['exit_date'])-origin).days if end_i is not None else None}
                        tapes[window][key][t].append(event)
                    if symbol in {'SPY','TLT','BTC/USD','ETH/USD'}:
                        cut=len(bars)-100
                        prefix=engine5.run(bars[:cut],(key,p),{k: v if k=='channels' else v[:cut] for k,v in prep.items()},start=start)
                        assert [t for t in engine5.signature(prefix) if t[3]] == [t for t in engine5.signature(trades) if t[3] and t[3]<=ds[cut-1]]
                        checks['prefix_signal_checks'] += 1
                i=start+1
                if i<len(bars):
                    t=(date.fromisoformat(ds[i])-origin).days
                    tapes[window]['buy-hold'][t].append({'symbol':symbol,'direction':'long','entry_date':ds[i],
                        'entry_price':bars[i]['o'],'entry_atr':atr[i-1],'exit_date':None,'exit_price':None,'exit_atr':None,
                        'exit_reason':None,'exit_t':None,'rule':'buy-hold'})
            if len(market)%100==0:print(f'Prepared {len(market)}/678 assets',flush=True)
    sums = {}
    for scope in ['priority','universe']:
        members=[s for s in infos if scope=='universe' or infos[s]['priority']]
        counts,inv = array('i',[0])*n,array('d',[0.])*n
        for s in members:
            for t,v in enumerate(market[s]['inverse']):
                if v:counts[t]+=1;inv[t]+=v
        sums[scope]={'members':members,'count':counts,'inverse':inv}
    return {'dates':dates,'infos':infos,'market':market,'tapes':tapes,'sums':sums,
            'signals':signals,'checks':checks,'inputs_sha256':previous['metadata']['inputs_sha256']}
