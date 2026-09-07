"""Read-only Bitstamp USD cross-check; no production data replacement."""
import csv,gzip,json,statistics,urllib.parse,urllib.request,sys
from pathlib import Path
from datetime import datetime,timezone
from settings import OUT,ANCHORS,BY_ID,ResearchParams
sys.path.insert(0,str(Path(__file__).parent))
from experiment import tasks,prepare
from calculations import evaluate,compact,eligible_years
import engine5


def main():
    folder=OUT/'second-source';folder.mkdir(exist_ok=True,parents=True)
    comparisons=[];stored=[]
    for symbol in ['BTC/USD','ETH/USD']:
        _,coinbase=next(tasks({symbol:{}},{symbol}))
        market=symbol.replace('/','').lower()
        start=int(datetime.fromisoformat(coinbase[0]['date']).replace(tzinfo=timezone.utc).timestamp())
        end=int(datetime.fromisoformat(coinbase[-1]['date']).replace(tzinfo=timezone.utc).timestamp())
        raw=[];requests=[]
        while start<=end:
            query=urllib.parse.urlencode({'step':86400,'limit':1000,'start':start,'exclude_current_candle':'true'})
            url=f'https://www.bitstamp.net/api/v2/ohlc/{market}/?{query}'
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'trade-helper-research/1.0'}),timeout=30) as f:data=json.load(f)
            candles=data['data']['ohlc'];requests.append(url)
            if not candles:break
            raw.extend(candles)
            last=max(int(b['timestamp']) for b in candles)
            if last<start:break
            start=last+86400
        (folder/f'{market}.json').write_text(json.dumps({'retrieved_utc':datetime.now(timezone.utc).isoformat(),'requests':requests,'ohlc':raw},separators=(',',':')),encoding='utf-8')
        secondary={datetime.fromtimestamp(int(b['timestamp']),timezone.utc).date().isoformat():
                   {'date':datetime.fromtimestamp(int(b['timestamp']),timezone.utc).date().isoformat(),
                    **{k:float(b[v]) for k,v in [('o','open'),('h','high'),('l','low'),('c','close'),('v','volume')]}} for b in raw if int(b['timestamp'])<=end}
        original={b['date']:b for b in coinbase}
        dates=sorted(original.keys()&secondary.keys())
        assert len(dates)>1000,(symbol,'insufficient matched history')
        assert all((datetime.fromisoformat(b)-datetime.fromisoformat(a)).days==1 for a,b in zip(dates,dates[1:])),(symbol,'gaps in matched data')
        differences=[abs(secondary[d]['c']/original[d]['c']-1) for d in dates]
        sources={name:[data[d] for d in dates] for name,data in [('Coinbase',original),('Bitstamp',secondary)]}
        row={'symbol':symbol,'start':dates[0],'end':dates[-1],'matched_days':len(dates),
             'coinbase_days_not_matched':len(original)-len(dates),'median_close_difference':statistics.median(differences),
             'p95_close_difference':sorted(differences)[int(.95*(len(differences)-1))],'max_close_difference':max(differences),'rules':{}}
        for source,bars in sources.items():
            prep=prepare(bars);eligible=eligible_years(dates)
            first=next(i for i,d in enumerate(dates) if d>=f'{eligible[0]}-01-01')
            for key in ANCHORS:
                p=ResearchParams(**BY_ID[key]['params'])
                row['rules'].setdefault(key,{})[source]={}
                for period,offset in [('full',0),('validation',first)]:
                    trades=engine5.run(bars,(key,p),prep,offset)
                    values=evaluate(bars,trades,prep['atr'],offset)
                    row['rules'][key][source][period]=compact(values)
            if source=='Bitstamp':stored.extend({'symbol':symbol,**b} for b in bars)
        comparisons.append(row)
        print(f'Second source: {symbol}, {len(dates)} matched daily bars, median close difference {100*row["median_close_difference"]:.4f}%',flush=True)
    with gzip.open(folder/'bitstamp-inputs.csv.gz','wt',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['symbol','date','o','h','l','c','v']);w.writeheader();w.writerows(stored)
    (OUT/'second-source.json').write_text(json.dumps({'source':'Bitstamp public USD daily OHLC','documentation':'https://www.bitstamp.net/api/',
        'scope':'Same matched calendar days and fixed long candidates, normal and doubled costs. Price-source sensitivity only; no production writes or parameter selection.',
        'comparisons':comparisons},allow_nan=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
