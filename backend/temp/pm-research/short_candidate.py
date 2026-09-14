"""One frozen failed-rally short hypothesis; see short-specification.md."""
from strategies import ResearchResult, indicators


def failed_rally(bars, *, start=250):
    if not bars: return ResearchResult([],None,{})
    closes=[b['c'] for b in bars]
    slow=indicators.sma(closes,200); fast=indicators.sma(closes,20)
    atr=indicators.wilder_atr([b['h'] for b in bars],[b['l'] for b in bars],closes,20)
    pos=None; pending=None; trades=[]; stops=[None]*len(bars)

    def close(t,price,reason):
        nonlocal pos
        trades.append({**pos,'exit_date':bars[t]['date'],'exit_price':price,'exit_reason':reason,
                       'bars_held':t-pos['entry_i'],'return_pct':None,'return_r':None,'mae_atr':None,'mfe_atr':None})
        pos=None

    for t,bar in enumerate(bars):
        if pending:
            if pending['action']=='exit': close(t,bar['o'],pending['reason'])
            else:
                pos={'direction':'short','entry_i':t,'entry_date':bar['date'],'entry_price':bar['o'],
                     'initial_stop':bar['o']+3*atr[t-1]}
            pending=None
        if pos and bar['h']>=pos['initial_stop']:
            stops[t]=pos['initial_stop']
            close(t,max(bar['o'],pos['initial_stop']),'stop_initial')
        if t<max(start,220) or slow[t-20] is None or atr[t] is None: continue
        action=None; reason=None
        if pos:
            if bar['c']>=slow[t]: reason='regime_exit'
            elif bar['c']>=fast[t]: reason='rally_exit'
            elif t-pos['entry_i']+1>=20: reason='time_exit'
            if reason: action='exit'
            stops[t]=pos['initial_stop']
        elif (bar['c']<slow[t] and slow[t]<slow[t-20] and
              bars[t-1]['h']>=fast[t-1] and bars[t-1]['c']<slow[t-1] and bar['c']<bars[t-1]['l']):
            action='enter'
        if action:
            pending={'action':action,'direction':'short','signal_date':bar['date'],'fill_at':'open_next','reason':reason}
    if pos:
        trades.append({**pos,'exit_date':None,'exit_price':None,'exit_reason':None,
                       'bars_held':len(bars)-1-pos['entry_i'],'return_pct':None,'return_r':None,'mae_atr':None,'mfe_atr':None})
    return ResearchResult(trades,pending,{'dates':[b['date'] for b in bars],'sma200':slow,'sma20':fast,
                                         'atr':atr,'stop_line':stops})
