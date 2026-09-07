"""Reviewed direction rules, funding and the persisted portfolio API."""
import math
import statistics
import time
import pytest

from app.features.signals import engine
from app.features.signals.params import LONG_PARAMS, SHORT_PARAMS
from app.features.sizing import portfolio
from app.features.sizing.data import rolling_vol
from app.features.sizing.params import COSTS
from tests.test_signals import _bars, _seed_bars


def test_short_benchmark_does_not_change_when_long_rules_change():
    bars=_bars([100+20*math.sin(i/18)+i*.03 for i in range(500)])
    a=engine.run_pair(bars,LONG_PARAMS)
    b=engine.run_pair(bars,LONG_PARAMS.model_copy(update={'initial_enabled':False}))
    assert a.directions['short'].trades==b.directions['short'].trades
    assert a.directions['short'].trades==engine.run(bars,SHORT_PARAMS,start=65).trades
    le=engine.compound([r['long_ret'] for r in a.daily])
    se=engine.compound([r['short_ret'] for r in a.daily])
    both=engine.compound([r['strat_ret'] for r in a.daily])
    assert both==pytest.approx([(l+s)/2 for l,s in zip(le,se)])


def test_initial_stop_stays_fixed_without_chandelier():
    bars=_bars([100.]*80+[101+i for i in range(60)])
    r=engine.run(bars,LONG_PARAMS)
    stop=r.trades[0]['initial_stop']
    assert stop is not None
    assert {s for s in r.overlays['stop_line'] if s is not None}=={stop}
    plain=engine.run(bars,LONG_PARAMS.model_copy(update={'initial_enabled':False}))
    assert plain.trades[0]['initial_stop'] is None
    assert all(s is None for s in plain.overlays['stop_line'])


def test_rolling_vol_matches_sample_statistic_and_is_past_only():
    closes=[100+7*math.sin(i/5)+i*.02 for i in range(500)]
    for crypto in [False,True]:
        vol=rolling_vol(closes,crypto)
        for i in [60,61,200,499]:
            rets=[closes[j]/closes[j-1]-1 for j in range(i-59,i+1)]
            expected=max(.01,statistics.stdev(rets)*math.sqrt(365 if crypto else 252))
            assert vol[i]==pytest.approx(expected,abs=1e-12)
        assert rolling_vol(closes[:201],crypto)==vol[:201]


def market_fixture(short=False,ending=80.):
    key='baseline-short' if short else 'e20-x55-s3'
    event={'symbol':'TEST','direction':'short' if short else 'long','rule':key,
           'entry_date':'2020-01-02','entry_price':100.,'entry_atr':1.,
           'exit_date':None,'exit_price':None,'exit_atr':None,'exit_t':None,'exit_reason':None}
    return {'dates':['2020-01-01','2020-01-02','2020-01-03'],
        'infos':{'TEST':{'priority':True,'asset_class':'Equities and other ETFs'}},
        'market':{'TEST':{'close':[100.,100.,ending],'inverse':[1.]*3,'age':[1]*3}},
        'sums':{'priority':{'members':['TEST'],'count':[1]*3,'inverse':[1.]*3}},
        'tapes':{'full':{key:[[],[event],[]]}},'signals':{'full':{'TEST':{key:1}}}}


@pytest.mark.parametrize('short,ending,expected',[(False,120.,120000.),(True,80.,120000.),(True,120.,80000.)])
def test_signed_units_cash_and_capital_scaling(monkeypatch,short,ending,expected):
    monkeypatch.setitem(COSTS,'normal',{'bps':0.,'atr':0.,'borrow':0.})
    data=market_fixture(short,ending);book='short-reference' if short else 'long-initial'
    result=portfolio.simulate(data,'priority','full',book,'equal','normal')
    assert result['stats']['ending']==pytest.approx(expected)
    assert result['curve'][1][6]==pytest.approx(0.)
    scaled=portfolio.simulate(data,'priority','full',book,'equal','normal',25000.)
    assert scaled['stats']['ending']==pytest.approx(expected/4)
    assert scaled['stats']['net']==pytest.approx(result['stats']['net'])


def test_portfolio_background_run_and_latest_result(client):
    from app.db.connection import get_connection
    with get_connection() as conn:_seed_bars(conn,'SPY',n=180)
    assert client.get('/api/sizing/latest').json()['status']=='not_computed'
    reply=client.post('/api/sizing/run',json={'book':'combined-initial','method':'capped-vol'}).json()
    for _ in range(120):
        run=client.get('/api/data/runs/'+str(reply['run_id'])).json()
        if run['status'] not in ('queued','running'):break
        time.sleep(.05)
    assert run['status']=='succeeded',run
    result=client.get('/api/sizing/latest').json()
    assert result['status']=='ok'
    assert result['params']['book']=='combined-initial'
    assert result['params']['method']=='capped-vol'
    assert len(result['assets'])==1
    assert result['stats']['ending']==pytest.approx(100000+sum(a['net_pnl'] for a in result['assets']))
    assert result['stats']['average_gross']<=.11
    assert result['benchmark']['stats']['ending']>0
    assert client.post('/api/sizing/run',json={'capital':-1}).status_code==422
