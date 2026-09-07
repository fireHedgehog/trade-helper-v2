"""Hand-calculated funding cases and independent saved-ledger reconstruction."""
import math
from collections import defaultdict
from settings6 import *
from portfolio6 import simulate


def fixture(prices,short=False,close=None):
    dates=['2020-01-01','2020-01-02','2020-01-03']
    event={'symbol':'TEST','direction':'short' if short else 'long','rule':'baseline-short' if short else RULES[0],
           'entry_date':dates[1],'entry_price':prices[0],'entry_atr':1.,'exit_date':dates[close] if close is not None else None,
           'exit_price':prices[close] if close is not None else None,'exit_atr':1. if close is not None else None,
           'exit_t':close,'exit_reason':'test_exit' if close is not None else None}
    return {'dates':dates,'infos':{'TEST':{'priority':True,'asset_class':'Equities and other ETFs'}},
            'market':{'TEST':{'close':prices,'inverse':[1.]*3,'age':[1]*3}},
            'sums':{'priority':{'members':['TEST'],'count':[1]*3,'inverse':[1.]*3}},
            'signals':{'full':{'TEST':{k:int(k==event['rule']) for k in RULES}}},
            'tapes':{'full':{k:[[],[event] if k==event['rule'] else [],[]] for k in RULES}}}


def check():
    original=COSTS['normal'].copy();COSTS['normal'].update(bps=0.,atr=0.,borrow=0.)
    count=0
    try:
        for short,prices,ending in [(False,[100.,100.,120.],120000.),(True,[100.,100.,80.],120000.),
                                    (True,[100.,100.,120.],80000.)]:
            data=fixture(prices,short)
            r=simulate(data,'priority','full','short-reference' if short else 'long-channel','equal','normal')
            assert abs(r['stats']['ending']-ending)<1e-7
            assert abs(r['trades'][0]['units'])==1000.
            if short:assert r['curve'][1][6]==0.,'sale proceeds incorrectly available'
            verify(r,data);count+=1
        data=fixture([100.,100.,120.])
        r=simulate(data,'priority','full','long-channel','capped-vol','normal')
        assert abs(r['trades'][0]['units']-100.)<1e-8
        assert r['stats']['ending']==102000.;verify(r,data);count+=1
        # Opposing views use separate 50k allocations, and their P&L reconciles.
        data=fixture([100.,100.,120.])
        data['tapes']['full']['baseline-short']=fixture([100.,100.,120.],True)['tapes']['full']['baseline-short']
        r=simulate(data,'priority','full','combined-channel','equal','normal')
        assert r['stats']['ending']==100000. and sorted(t['units'] for t in r['trades'])==[-500.,500.]
        verify(r,data);count+=1
        # A same-day protective exit has both fills and costs, never an open mark.
        data=fixture([100.,90.,90.],False,close=1)
        r=simulate(data,'priority','full','long-channel','equal','normal')
        assert r['stats']['ending']==90000. and r['audit']['same_day_round_trips']==1
        verify(r,data);count+=1
        COSTS['normal'].update(bps=5.,atr=.05,borrow=.02)
        data=fixture([100.,100.,80.],True,close=2)
        r=simulate(data,'priority','full','short-reference','equal','normal')
        trade=r['trades'][0]
        assert math.isclose(abs(trade['units']),100000/100.1)
        assert math.isclose(trade['borrow'],abs(trade['units'])*100*.02/365)
        verify(r,data);count+=1
        # Future price changes cannot resize an earlier entry.
        changed=fixture([100.,100.,200.],True,close=2)
        alt=simulate(changed,'priority','full','short-reference','equal','normal')
        assert alt['trades'][0]['units']==trade['units'];count+=1
    finally:COSTS['normal'].update(original)
    print(f'Passed {count} hand-calculated accounting / funding checks',flush=True)
    return count


def verify(result,data):
    """Replay fills as cash flows, independently recompute costs and daily equity."""
    config=COSTS[result['cost']];dates=data['dates'];idx={d:i for i,d in enumerate(dates)}
    enters=defaultdict(list);exits=defaultdict(list);checks=0;max_error=0.
    for number,tr in enumerate(result['trades']):
        q=tr['units'];ep=tr['entry_price'];mp=tr['mark_price']
        assert q>0 if tr['direction']=='long' else q<0
        assert math.isclose(tr['price_pnl'],q*(mp-ep),rel_tol=1e-10,abs_tol=1e-7)
        assert math.isclose(tr['entry_fee'],abs(q)*ep*config['bps']/10000,abs_tol=1e-7)
        assert math.isclose(tr['entry_slippage'],abs(q)*tr['entry_atr']*config['atr'],abs_tol=1e-7)
        if tr['exit_date']:
            assert math.isclose(tr['exit_fee'],abs(q)*mp*config['bps']/10000,abs_tol=1e-7)
            assert math.isclose(tr['exit_slippage'],abs(q)*tr['exit_atr']*config['atr'],abs_tol=1e-7)
        a=idx[tr['entry_date']];b=idx[tr['mark_date']]
        borrow=abs(q)*sum(data['market'][tr['symbol']]['close'][a:b])*config['borrow']/365 if q<0 else 0.
        assert math.isclose(tr['borrow'],borrow,rel_tol=1e-9,abs_tol=1e-6),(tr['symbol'],tr['borrow'],borrow)
        enters[tr['entry_date']].append((number,tr))
        if tr['exit_date']:exits[tr['exit_date']].append((number,tr))
        checks+=1
    cash=CAPITAL;active={};fees=slip=borrow_total=0.;previous_short=0.
    for row in result['curve']:
        day=row[0];t=idx[day]
        charge=previous_short*config['borrow']/365
        cash-=charge;borrow_total+=charge
        for number,tr in enters[day]:
            cash-=tr['units']*tr['entry_price']+tr['entry_fee']+tr['entry_slippage']
            fees+=tr['entry_fee'];slip+=tr['entry_slippage'];active[number]=tr
        for number,tr in exits[day]:
            cash+=tr['units']*tr['mark_price']-tr['exit_fee']-tr['exit_slippage']
            fees+=tr['exit_fee'];slip+=tr['exit_slippage'];del active[number]
        long=sum(tr['units']*data['market'][tr['symbol']]['close'][t] for tr in active.values() if tr['units']>0)
        short=-sum(tr['units']*data['market'][tr['symbol']]['close'][t] for tr in active.values() if tr['units']<0)
        expected=[cash+long-short,cash,long,short]
        error=max(abs(a-b) for a,b in zip(expected,row[1:5]))
        error=max(error,abs(fees-row[9]),abs(slip-row[10]),abs(borrow_total-row[11]))
        assert error<1e-5,(result['book'],day,error)
        max_error=max(max_error,error);previous_short=short
    return {'trades':checks,'daily_marks':len(result['curve']),'maximum_error':max_error}


if __name__=='__main__':check()
