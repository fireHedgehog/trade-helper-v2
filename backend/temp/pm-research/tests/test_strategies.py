import sys
from pathlib import Path
from datetime import date,timedelta

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from strategies import sma_trend
from strategies import pullback, wilder_rsi
import pytest


def bars(closes):
    return [{'date':(date(2020,1,1)+timedelta(days=i)).isoformat(),'o':c,'h':c+.5,'l':c-.5,'c':c,'v':100}
            for i,c in enumerate(closes)]


def test_sma_executes_after_close_and_equality_preserves_position():
    xs=bars([100.,100.,101.,102.,102.,100.,99.])
    result=sma_trend(xs,start=2,period=2)
    assert result.trades[0]['entry_date']==xs[3]['date']
    assert result.trades[0]['entry_price']==102.
    assert result.trades[0]['exit_date']==xs[6]['date']
    assert result.trades[0]['exit_price']==99.
    assert len(result.trades)==1
    prefix=sma_trend(xs[:3],start=2,period=2)
    assert prefix.trades==[] and prefix.pending_action['action']=='enter'
    equality=sma_trend(bars([100.]*10),start=2,period=2)
    assert equality.trades==[] and equality.pending_action is None


def test_sma_common_warmup_and_future_data_cannot_change_earlier_entry():
    xs=bars([100+i*.1 for i in range(260)])
    full=sma_trend(xs)
    assert full.trades[0]['entry_date']==xs[251]['date']
    truncated=sma_trend(xs[:255])
    for key in ['entry_date','entry_price','initial_stop']:
        assert full.trades[0][key]==truncated.trades[0][key]
    no_execution=sma_trend(xs[:251])
    assert not no_execution.trades and no_execution.pending_action['signal_date']==xs[250]['date']


def test_wilder_rsi_seed_smoothing_and_edges():
    assert wilder_rsi([1.,2.,3.])==[None,None,100.]
    assert wilder_rsi([3.,2.,1.])==[None,None,0.]
    assert wilder_rsi([1.,1.,1.,1.])==[None,None,50.,50.]
    assert wilder_rsi([10.,12.,11.,13.])[2:]==pytest.approx([200/3,100*1.5/1.75])
    assert wilder_rsi([])==[]
    assert wilder_rsi([1.,2.])==[None,None]


def pullback_bars():
    return bars([80.]*250+[140.,140.,130.,120.,110.]+[109.-i*.1 for i in range(12)])


def test_pullback_tenth_held_close_fills_eleventh_open_and_no_lookahead():
    xs=pullback_bars()
    trade=pullback(xs).trades[0]
    assert trade['entry_date']==xs[255]['date']
    assert trade['exit_date']==xs[265]['date']
    assert trade['exit_reason']=='time_exit'
    assert trade['exit_price']==xs[265]['o']
    nine=pullback(xs[:264]); ten=pullback(xs[:265])
    assert nine.trades[0]['exit_date'] is None and nine.pending_action is None
    assert ten.pending_action['signal_date']==xs[264]['date']
    assert ten.pending_action['reason']=='time_exit'
    assert ten.trades[0]['entry_date']==trade['entry_date']
    first=pullback(xs[:255])
    assert first.trades==[] and first.pending_action['action']=='enter'


def test_pullback_sma5_scheduled_exit_precedes_intraday_stop():
    xs=pullback_bars()
    xs[256].update(o=109.,h=121.,l=108.,c=120.)
    xs[257].update(o=119.,h=120.,l=50.,c=100.)
    tr=pullback(xs[:258]).trades[0]
    assert tr['exit_date']==xs[257]['date'] and tr['exit_price']==119.
    assert tr['exit_reason']=='sma5_exit'


def test_pullback_regime_exit_and_entry_day_protection_and_gap():
    xs=pullback_bars(); xs[256].update(o=109.,h=110.,l=79.,c=80.)
    tr=pullback(xs[:258],initial_stop=False).trades[0]
    assert tr['exit_reason']=='regime_exit' and tr['exit_date']==xs[257]['date']
    xs=pullback_bars(); xs[255]['l']=80.
    result=pullback(xs[:256]); tr=result.trades[0]
    assert tr['entry_date']==tr['exit_date']==xs[255]['date']
    assert tr['exit_price']==pytest.approx(109.-3*result.overlays['atr'][254])
    assert result.pending_action['fill_at']=='open_next' # never same-day intraday reentry
    xs=pullback_bars(); xs[256].update(o=80.,h=91.,l=79.,c=90.)
    tr=pullback(xs[:257]).trades[0]
    assert tr['exit_reason']=='stop_initial' and tr['exit_price']==80.


def test_predefined_stop_controls_change_only_protection():
    xs=bars([100.]*250+[110.,111.,80.])
    xs[252].update(h=82.,l=79.,c=81.)
    plain=sma_trend(xs).trades[0]
    protected=sma_trend(xs,initial_stop=True).trades[0]
    assert protected['entry_date']==plain['entry_date']==xs[251]['date']
    assert plain['exit_date'] is None # close schedules tomorrow, no invented final exit
    assert protected['exit_price']==80. and protected['exit_reason']=='stop_initial'
    xs=pullback_bars(); xs[255]['l']=80.
    protected=pullback(xs[:256]).trades[0]
    plain=pullback(xs[:256],initial_stop=False).trades[0]
    assert protected['entry_date']==plain['entry_date']
    assert protected['exit_date'] is not None and plain['exit_date'] is None


def test_pullback_threshold_is_strict_and_neighbours_are_frozen():
    xs=pullback_bars()[:255]
    exact=wilder_rsi([b['c'] for b in xs])[-1]
    assert pullback(xs,threshold=exact).pending_action is None
    assert pullback(xs,threshold=exact+1e-9).pending_action['action']=='enter'
    from comparisons import CANDIDATES
    assert set(CANDIDATES)=={'sma200','pullback','sma200-stop','pullback-no-stop',
                             'sma150','sma250','pullback-rsi10','pullback-rsi30'}
    for name in ['sma150','sma250']:
        fn,params=CANDIDATES[name]
        result=fn(bars([100+i*.1 for i in range(260)]),**params)
        assert result.trades[0]['entry_date']==bars([0.]*252)[251]['date']
