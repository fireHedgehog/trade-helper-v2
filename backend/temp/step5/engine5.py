"""Fixed or annually selected rule; an open position retains its entry rule."""
def run(bars, initial, prepared, start=0, schedule=None):
    atr, channels = prepared['atr'], prepared['channels']
    position = pending = None
    trades = []
    active_key, active = initial
    warm = active.warmup()

    def close(i,price,reason):
        nonlocal position
        trades.append({'direction':'long' if position['d']==1 else 'short',
                       'entry_date':bars[position['i']]['date'],'entry_price':position['price'],
                       'exit_date':bars[i]['date'] if reason else None,'exit_price':price if reason else None,
                       'exit_reason':reason,'rule':position['key']})
        position=None

    for i,b in enumerate(bars):
        if schedule:
            chosen=schedule.get(int(b['date'][:4]))
            if chosen and chosen[0]!=active_key:
                active_key,active=chosen
                warm=active.warmup()
        if pending:
            order,pending=pending,None
            if order[0]=='exit':close(i,b['o'],'channel_reversal')
            else:
                _,key,p=order
                d=1 if p.allow_long else -1
                stop=b['o']-d*p.atr_stop_mult*atr[i-1] if p.initial_enabled else None
                position={'key':key,'p':p,'d':d,'i':i,'price':b['o'],'initial':stop,'stop':stop,'high':b['o'],'low':b['o']}
        if position:
            d,stop=position['d'],position['stop']
            if stop is not None and (b['l']<=stop if d==1 else b['h']>=stop):
                close(i,min(b['o'],stop) if d==1 else max(b['o'],stop),
                      'stop_initial' if stop==position['initial'] else 'stop_trailing')
            else:
                position['high']=max(position['high'],b['h'])
                position['low']=min(position['low'],b['l'])
        if position:
            p,d=position['p'],position['d']
            up,down=channels[p.exit_len]
            if p.channel_enabled and ((d==1 and b['c']<down[i]) or (d==-1 and b['c']>up[i])):pending=('exit',)
            if p.trailing_enabled:
                trail=position['high']-p.chandelier_k*atr[i] if d==1 else position['low']+p.chandelier_k*atr[i]
                position['stop']=trail if position['stop'] is None else max(position['stop'],trail) if d==1 else min(position['stop'],trail)
        elif i>=max(start,warm) and atr[i] is not None:
            up,down=channels[active.entry_len]
            if (active.allow_long and b['c']>up[i]) or (active.allow_short and b['c']<down[i]):
                pending=('enter',active_key,active)
    if position:close(len(bars)-1,bars[-1]['c'],None)
    return trades


def signature(trades):
    return [(t['direction'],t['entry_date'],t['entry_price'],t['exit_date'],t['exit_price'],t['exit_reason']) for t in trades]
