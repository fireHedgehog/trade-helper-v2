"""Fixed research candidates. Native fills feed the reviewed funded accountant."""
from __future__ import annotations
from dataclasses import dataclass

from snapshot import BACKEND
from app.features.signals import indicators


@dataclass
class ResearchResult:
    trades: list[dict]
    pending_action: dict | None
    overlays: dict


def sma_trend(bars, *, start=250, period=200, initial_stop=False):
    """Close > SMA enters next open; close < SMA exits; equality does nothing."""
    if not bars: return ResearchResult([],None,{})
    closes=[b['c'] for b in bars]
    averages=indicators.sma(closes,period)
    atr=indicators.wilder_atr([b['h'] for b in bars],[b['l'] for b in bars],closes,20)
    pos=None; pending=None; trades=[]; stops=[None]*len(bars)

    def close(t,price,reason):
        nonlocal pos
        trades.append({**pos,'exit_date':bars[t]['date'],'exit_price':price,'exit_reason':reason,
                       'bars_held':t-pos['entry_i'],'return_pct':None,'return_r':None,'mae_atr':None,'mfe_atr':None})
        pos=None

    for t,bar in enumerate(bars):
        if pending:
            if pending['action']=='exit': close(t,bar['o'],'sma_exit')
            else:
                pos={'direction':'long','entry_i':t,'entry_date':bar['date'],'entry_price':bar['o'],
                     'initial_stop':bar['o']-3*atr[t-1] if initial_stop else None}
            pending=None
        if pos:
            stop=pos['initial_stop']
            if stop is not None and bar['l']<=stop:
                stops[t]=stop
                close(t,min(bar['o'],stop),'stop_initial')
        if t<start or averages[t] is None or (initial_stop and atr[t] is None): continue
        action=None
        if pos:
            if bar['c']<averages[t]: action='exit'
            stops[t]=pos['initial_stop']
        elif bar['c']>averages[t]: action='enter'
        if action:
            pending={'action':action,'direction':'long','signal_date':bar['date'],'fill_at':'open_next'}
    if pos:
        trades.append({**pos,'exit_date':None,'exit_price':None,'exit_reason':None,
                       'bars_held':len(bars)-1-pos['entry_i'],'return_pct':None,'return_r':None,'mae_atr':None,'mfe_atr':None})
    return ResearchResult(trades,pending,{'dates':[b['date'] for b in bars],'sma':averages,'atr':atr,'stop_line':stops})


def wilder_rsi(closes, period=2):
    """Seed with `period` close changes; explicitly handle flat/rising/falling."""
    if period<1: raise ValueError('RSI period must be positive')
    out=[None]*len(closes)
    if len(closes)<=period: return out
    changes=[closes[t]-closes[t-1] for t in range(1,len(closes))]
    gain=sum(max(0,x) for x in changes[:period])/period
    loss=sum(max(0,-x) for x in changes[:period])/period
    def value():
        return 50. if gain==loss==0 else 100. if loss==0 else 0. if gain==0 else 100*gain/(gain+loss)
    out[period]=value()
    for t in range(period+1,len(closes)):
        change=changes[t-1]
        gain+=(max(0,change)-gain)/period
        loss+=(max(0,-change)-loss)/period
        out[t]=value()
    return out


def pullback(bars, *, start=250, threshold=20, initial_stop=True):
    """Fixed SMA200/RSI2 entry; SMA5/regime/tenth-held-close exits next open."""
    if not bars: return ResearchResult([],None,{})
    closes=[b['c'] for b in bars]
    regime=indicators.sma(closes,200); fast=indicators.sma(closes,5)
    rsi=wilder_rsi(closes,2)
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
                pos={'direction':'long','entry_i':t,'entry_date':bar['date'],'entry_price':bar['o'],
                     'initial_stop':bar['o']-3*atr[t-1] if initial_stop else None}
            pending=None
        if pos:
            stop=pos['initial_stop']
            if stop is not None and bar['l']<=stop:
                stops[t]=stop
                close(t,min(bar['o'],stop),'stop_initial')
        if t<start or regime[t] is None or rsi[t] is None or atr[t] is None: continue
        action=None; reason=None
        if pos:
            # Ordered reason label when more than one close condition is true.
            if bar['c']>=fast[t]: reason='sma5_exit'
            elif bar['c']<=regime[t]: reason='regime_exit'
            elif t-pos['entry_i']+1>=10: reason='time_exit'
            if reason: action='exit'
            stops[t]=pos['initial_stop']
        elif bar['c']>regime[t] and rsi[t]<threshold: action='enter'
        if action:
            pending={'action':action,'direction':'long','signal_date':bar['date'],'fill_at':'open_next','reason':reason}
    if pos:
        trades.append({**pos,'exit_date':None,'exit_price':None,'exit_reason':None,
                       'bars_held':len(bars)-1-pos['entry_i'],'return_pct':None,'return_r':None,'mae_atr':None,'mfe_atr':None})
    return ResearchResult(trades,pending,{'dates':[b['date'] for b in bars],'sma200':regime,'sma5':fast,
                                         'rsi2':rsi,'atr':atr,'stop_line':stops})
