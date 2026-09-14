"""Hand-computed accounting oracles, independent of portfolio implementation."""
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.features.signals import engine
from app.features.signals.params import LONG_PARAMS
from app.features.sizing import portfolio


def bars():
    start = date(2020,1,1)
    return [{'date':(start+timedelta(days=i)).isoformat(),'o':100.,'h':101.,'l':99.,'c':100.,'v':1}
            for i in range(250)]


def extend(xs, prices):
    for o,h,low,c in prices:
        day = date.fromisoformat(xs[-1]['date'])+timedelta(days=1)
        xs.append({'date':day.isoformat(),'o':o,'h':h,'l':low,'c':c,'v':1})
    return xs


def test_entry_and_gap_stop_use_known_atr_and_actual_open():
    xs = extend(bars(),[(104,105,103,104),(105,106,104,105),(90,92,89,91)])
    result = engine.run(xs,LONG_PARAMS,start=250)
    trade = result.trades[0]
    # Prior TR=2; breakout TR=5 => ATR20=2.15. Entry ATR stays this value.
    assert trade['entry_date'] == xs[251]['date']
    assert trade['entry_price'] == 105
    assert trade['initial_stop'] == pytest.approx(98.55)
    assert trade['exit_price'] == 90   # adverse open, not the stop price
    # Next ATR=2.1425; fee/slippage per unit at entry=.16 and exit=.152125.
    expected = (90-105-.16-.152125)/105
    assert trade['return_pct'] == pytest.approx(expected)
    assert engine.compound([d['strat_ret'] for d in result.daily])[-1] == pytest.approx(1+expected)


def test_scheduled_exit_and_terminal_mark_do_not_invent_fills():
    xs = extend(bars(),[(104,105,103,104),(105,106,104,105),(100,101,94,95),(93,95,80,94)])
    result = engine.run(xs,LONG_PARAMS.model_copy(update={'initial_enabled':False}),start=250)
    assert result.trades[0]['exit_price'] == 93
    assert result.trades[0]['exit_date'] == xs[253]['date']
    held = engine.run(xs[:252],LONG_PARAMS,start=250)
    assert held.trades[0]['exit_date'] is None
    assert held.trades[0]['exit_price'] is None
    assert engine.compound([d['strat_ret'] for d in held.daily])[-1] == pytest.approx(1-.16/105)


def fixture(exit_price=None):
    key = 'e20-x55-s3'
    event = {'symbol':'X','direction':'long','rule':key,'entry_date':'2020-01-02',
             'entry_price':100.,'entry_atr':2.,'exit_date':'2020-01-03' if exit_price else None,
             'exit_price':exit_price,'exit_atr':3. if exit_price else None,
             'exit_t':2 if exit_price else None,'exit_reason':'scheduled' if exit_price else None}
    return {'dates':['2020-01-01','2020-01-02','2020-01-03'],
            'infos':{'X':{'priority':True,'asset_class':'Equities and other ETFs'}},
            'market':{'X':{'close':[100.,110.,120.],'inverse':[1.,1.,1.],'age':[1,1,1]}},
            'sums':{'priority':{'members':['X'],'count':[1,1,1],'inverse':[1.,1.,1.]}},
            'tapes':{'full':{key:[[],[event],[]]}},'signals':{'full':{'X':{key:1}}}}


@pytest.mark.parametrize('exit_price',[None,95.])
def test_funded_cash_costs_and_open_mark(exit_price):
    result = portfolio.simulate(fixture(exit_price),'priority','full','long-initial','equal','normal',1000)
    # $100 share + $.05 fee + $.10 ATR slip, with $1000 all-in cash budget.
    units = 1000/100.15
    expected = units*(95-.0475-.15) if exit_price else units*120
    assert result['trades'][0]['units'] == pytest.approx(units)
    assert result['curve'][1][2] == pytest.approx(0,abs=1e-10)
    assert result['stats']['ending'] == pytest.approx(expected)
    assert result['stats']['fees'] == pytest.approx(units*(.05+(.0475 if exit_price else 0)))
    assert result['stats']['slippage'] == pytest.approx(units*(.10+(.15 if exit_price else 0)))
    assert 1000+sum(r['net_pnl'] for r in result['assets']) == pytest.approx(expected)


def test_same_day_exit_cannot_fund_new_asset(monkeypatch):
    monkeypatch.setitem(portfolio.COSTS,'normal',{'bps':0.,'atr':0.,'borrow':0.})
    data = fixture(120.)
    key = 'e20-x55-s3'
    data['infos']['Y'] = data['infos']['X'].copy()
    data['market']['Y'] = {'close':[100.,100.,100.],'inverse':[0.,0.,1.],'age':[1,1,1]}
    data['sums']['priority'] = {'members':['X','Y'],'count':[1,1,2],'inverse':[1.,1.,2.]}
    data['signals']['full']['Y'] = {key:1}
    data['tapes']['full'][key][2] = [{**data['tapes']['full'][key][1][0], 'symbol':'Y',
         'entry_date':'2020-01-03','exit_date':None,'exit_t':None,'exit_price':None}]
    result = portfolio.simulate(data,'priority','full','long-initial','equal','normal',1000)
    assert result['stats']['ending'] == 1200
    assert result['stats']['entries'] == 1
    assert result['audit']['unfunded'] == 1
    assert result['curve'][-1][2] == 1200
