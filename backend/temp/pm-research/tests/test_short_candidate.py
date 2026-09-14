import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from short_candidate import failed_rally
from test_strategies import bars
from test_accounting import fixture, portfolio


def example():
    xs=bars([150.-i*.2 for i in range(250)]+[105.,100.]+[99.-i*.01 for i in range(23)])
    xs[250].update(o=105.,h=110.,l=104.,c=105.)
    xs[251].update(o=103.,h=104.,l=99.,c=100.)
    return xs


def test_independent_failed_rally_entry_and_twentieth_bar_exit():
    xs=example(); result=failed_rally(xs)
    tr=result.trades[0]
    assert tr['entry_date']==xs[252]['date'] and tr['entry_price']==99.
    assert tr['exit_date']==xs[272]['date'] and tr['exit_reason']=='time_exit'
    assert failed_rally(xs[:252]).pending_action['signal_date']==xs[251]['date']
    assert failed_rally(xs[:272]).pending_action['reason']=='time_exit'
    assert failed_rally(xs[:271]).pending_action is None
    # A falling market without the defined rally attempt does not suffice.
    assert not failed_rally(bars([150.-i*.2 for i in range(400)])).trades
    equal=example()[:252]; equal[251].update(o=104.,h=105.,l=103.,c=104.)
    assert failed_rally(equal).pending_action is None


def test_short_entry_day_stop_adverse_gap_and_scheduled_exit():
    xs=example(); xs[252]['h']=110.
    result=failed_rally(xs[:253]); tr=result.trades[0]
    assert tr['entry_date']==tr['exit_date']
    assert tr['exit_price']==pytest.approx(99.+3*result.overlays['atr'][251])
    xs=example(); xs[253].update(o=115.,h=116.,l=114.,c=115.)
    tr=failed_rally(xs[:254]).trades[0]
    assert tr['exit_price']==115. and tr['exit_reason']=='stop_initial'
    xs=example(); xs[253].update(o=99.,h=103.,l=98.,c=102.5)
    xs[254].update(o=103.,h=150.,l=100.,c=105.)
    tr=failed_rally(xs[:255]).trades[0]
    assert tr['exit_price']==103. and tr['exit_reason']=='rally_exit'


def test_synthetic_short_rising_prices_and_borrow_reduce_equity():
    data=fixture(None); old='e20-x55-s3'; key='baseline-short'
    tape=data['tapes']['full'].pop(old); tape[1][0]['direction']='short';tape[1][0]['rule']=key
    data['tapes']['full'][key]=tape;data['signals']['full']['X']={key:1}
    result=portfolio.simulate(data,'priority','full','short-reference','equal','normal',1000.)
    units=1000/100.15
    borrow=units*110*.02/365
    assert result['trades'][0]['units']==pytest.approx(-units)
    assert result['stats']['ending']==pytest.approx(1000-units*20-units*.15-borrow)
    assert result['stats']['borrow']==pytest.approx(borrow)
    assert result['trades'][0]['exit_fee']==0. # terminal mark is not a fill
    assert result['curve'][-1][6]<0 # liability growth can exhaust collateral despite initial reservation
