"""Independent direct cash simulation, with rules retained by open positions."""
from settings import LENGTHS

def prepare(bars):
    atr=[];tr=[]
    for i,b in enumerate(bars):
        previous=bars[i-1]['c'] if i else b['c']
        tr.append(max(b['h']-b['l'],abs(b['h']-previous),abs(b['l']-previous)))
        atr.append(sum(tr)/20 if i==19 else (atr[-1]*19+tr[-1])/20 if i>=20 else None)
    channels={n:([None]*min(n,len(bars))+[max(b['h'] for b in bars[i-n:i]) for i in range(n,len(bars))],
                 [None]*min(n,len(bars))+[min(b['l'] for b in bars[i-n:i]) for i in range(n,len(bars))]) for n in LENGTHS}
    return {'atr':atr,'channels':channels}


def run(bars,initial,prepared,start=0,schedule=None,bps=5.,slip=.05):
    cash,units=1.,0.
    held=order=None
    values=[]
    key,p=initial
    atr,channels=prepared['atr'],prepared['channels']
    def charge(price,a):return abs(units)*(price*bps/10000+a*slip)
    for i,b in enumerate(bars):
        key,p=(schedule or {}).get(int(b['date'][:4]),(key,p))
        if order:
            if order[0]=='exit':
                cash+=units*b['o']-charge(b['o'],atr[i-1]);units=0.;held=None
            else:
                old_key,old_p=order
                side=1 if old_p.allow_long else -1
                units=side*cash/b['o']
                cash-=units*b['o']+charge(b['o'],atr[i-1])
                stop=b['o']-side*old_p.atr_stop_mult*atr[i-1] if old_p.initial_enabled else None
                held={'p':old_p,'side':side,'stop':stop,'high':b['o'],'low':b['o']}
            order=None
        if held:
            stop,d=held['stop'],held['side']
            if stop is not None and ((d>0 and b['l']<=stop) or (d<0 and b['h']>=stop)):
                price=min(b['o'],stop) if d>0 else max(b['o'],stop)
                cash+=units*price-charge(price,atr[i-1]);units=0.;held=None
            else:
                held['high']=max(held['high'],b['h']);held['low']=min(held['low'],b['l'])
        value=cash+units*b['c'];values.append(value)
        if value<=0:return values+[value]*(len(bars)-len(values))
        if held:
            hp,d=held['p'],held['side'];up,dn=channels[hp.exit_len]
            if (d>0 and b['c']<dn[i]) or (d<0 and b['c']>up[i]):order=('exit',)
            if hp.trailing_enabled:
                trail=held['high']-hp.chandelier_k*atr[i] if d>0 else held['low']+hp.chandelier_k*atr[i]
                held['stop']=trail if held['stop'] is None else max(held['stop'],trail) if d>0 else min(held['stop'],trail)
        elif i>=max(start,p.warmup()):
            up,dn=channels[p.entry_len]
            if (p.allow_long and b['c']>up[i]) or (p.allow_short and b['c']<dn[i]):order=(key,p)
    return values
