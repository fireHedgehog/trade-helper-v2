"""SMA production rules and saved app workflow; synthetic functional fixtures only."""
from datetime import date, timedelta
import math

import pytest
from pydantic import ValidationError

from app.features.pms import assessment, repository, service, sma
from app.features.pms.contracts import PMDefinition
from app.features.signals import engine, indicators
from tests.test_pms import wait_job


def bars(closes):
    origin = date.today() - timedelta(days=len(closes) - 1)
    return [dict(date=(origin + timedelta(days=i)).isoformat(), o=float(c),
                 h=float(c)+0.5, l=float(c)-0.5, c=float(c), v=1000.)
            for i, c in enumerate(closes)]


def definition(side, **kwargs):
    return sma.definitions(sma.SMAParams(period=2, atr_len=5, **kwargs))[0 if side == 'long' else 1]


@pytest.mark.parametrize('side,sign', [('long', 1), ('short', -1)])
def test_close_signal_next_open_equality_exit_and_cost_reconciliation(side, sign):
    xs = bars([100.]*6 + [100.+2*sign]*3 + [100.+sign, 100.+sign])
    pm = definition(side, cost_bps=5, slippage_atr=.05)
    pending = service.evaluate('X', xs[:7], pm)
    assert pending.position.state == 'flat' and pending.trades == []
    assert pending.pending_action.action == 'enter'
    assert pending.pending_action.signal_date == xs[6]['date']
    held = service.evaluate('X', xs[:9], pm)
    assert held.position.state == side and held.pending_action is None  # equality retains holding
    exiting = service.evaluate('X', xs[:10], pm)
    assert exiting.position.state == side and exiting.pending_action.action == 'exit'
    result = service.evaluate('X', xs, pm)
    tr, = result.trades
    assert tr['entry_date'] == xs[7]['date'] and tr['exit_date'] == xs[10]['date']
    assert tr['entry_price'] == xs[7]['o'] and tr['exit_price'] == xs[10]['o']
    assert tr['exit_reason'] == 'sma_exit'
    atr = indicators.wilder_atr([b['h'] for b in xs], [b['l'] for b in xs], [b['c'] for b in xs], 5)
    assert tr['initial_stop'] == pytest.approx(tr['entry_price']-sign*3*atr[6])
    cost = ((tr['entry_price']+tr['exit_price'])*.0005 + .05*(atr[6]+atr[9]))/tr['entry_price']
    expected = sign*(tr['exit_price']/tr['entry_price']-1)-cost
    assert tr['return_pct'] == pytest.approx(expected)
    assert engine.compound([d['strat_ret'] for d in result.daily])[-1] == pytest.approx(1+expected)
    assert held.trades[0]['entry_date'] == tr['entry_date']  # future bars do not change entry
    assert held.overlays['sma'] == result.overlays['sma'][:9]


@pytest.mark.parametrize('side,sign', [('long', 1), ('short', -1)])
@pytest.mark.parametrize('gap', [False, True])
def test_resting_stop_uses_signal_atr_and_gap_price(side, sign, gap):
    xs = bars([100.]*6 + [100.+2*sign]*3)
    pm = definition(side, cost_bps=0, slippage_atr=0)
    held = service.evaluate('X', xs[:8], pm)
    stop = held.position.current_stop
    last = xs[8]
    stop_fill = stop-sign*2 if gap else stop
    last['o'] = stop_fill if gap else xs[7]['c']
    last['c'] = stop-sign
    last['l'] = min(last['o'], last['c'], stop)-.1
    last['h'] = max(last['o'], last['c'], stop)+.1
    result = service.evaluate('X', xs, pm)
    tr = result.trades[0]
    assert tr['exit_reason'] == 'stop_initial'
    assert tr['exit_price'] == pytest.approx(stop_fill)
    assert tr['initial_stop'] == stop
    assert result.overlays['stop_line'][7] == stop


@pytest.mark.parametrize('side,sign', [('long', 1), ('short', -1)])
def test_scheduled_exit_precedes_intraday_stop_and_entry_day_stop(side, sign):
    pm = definition(side)
    xs = bars([100.]*6 + [100.+2*sign]*2 + [100.+sign]*2)
    prior = service.evaluate('X', xs[:9], pm)
    assert prior.pending_action.action == 'exit'
    stop = prior.position.current_stop
    xs[9]['l'] = min(xs[9]['l'], stop-1)
    xs[9]['h'] = max(xs[9]['h'], stop+1)
    result = service.evaluate('X', xs, pm)
    assert result.trades[0]['exit_reason'] == 'sma_exit'
    assert result.trades[0]['exit_price'] == xs[9]['o']
    entry_day = xs[:8]
    entry_day[-1]['l'] = 80
    entry_day[-1]['h'] = 120
    stopped = service.evaluate('X', entry_day, pm)
    assert stopped.trades[0]['entry_date'] == stopped.trades[0]['exit_date']
    assert stopped.trades[0]['exit_reason'] == 'stop_initial'
    assert stopped.trades[0]['initial_stop'] == pytest.approx(stop)


def test_warmup_unavailable_equality_and_invalid_input():
    pm = sma.definitions()[0]
    assert service.evaluate('X', [], pm).status == 'insufficient_history'
    assert service.evaluate('X', bars([100.]*199), pm).position.state is None
    flat = service.evaluate('X', bars([100.]*200), pm)
    assert flat.status == 'ok' and flat.position.state == 'flat' and flat.pending_action is None
    ready = service.evaluate('X', bars([100.]*199+[102.]), pm)
    assert ready.pending_action.action == 'enter' and not ready.trades
    invalid = bars([100.]*210); invalid[-1]['l'] = 150
    assert service.evaluate('X', invalid, pm).status == 'invalid_data'


def test_params_and_engine_changes_require_new_versions():
    a = definition('long'); b = definition('long', atr_stop_mult=2)
    assert a.version != b.version and a.key == b.key
    obsolete = PMDefinition.create(**{**a.model_dump(exclude={'version'}), 'engine_version':'old-sma'})
    with pytest.raises(ValueError, match='engine version'):
        service.evaluate('X', bars([100.]*10), obsolete)
    for values in ({'period':1}, {'atr_stop_mult':float('nan')}, {'fill_at':'close'}, {'unexpected':1}):
        with pytest.raises(ValidationError): sma.SMAParams(**values)


def test_worker_saves_all_families_and_read_only_sma_charts(client):
    from app.db.connection import get_connection
    xs = bars([100.+10*math.sin(i/30) for i in range(260)])
    with get_connection() as conn:
        conn.executemany('''INSERT INTO price_bars
            (symbol,date,open,high,low,close,volume,adj_open,adj_high,adj_low,adj_close)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            [('SMAFIX',b['date'],b['o'],b['h'],b['l'],b['c'],b['v'],b['o'],b['h'],b['l'],b['c']) for b in xs])
    reply = client.post('/api/pms/run', json={'symbols':['SMAFIX']}).json()
    job = wait_job(client, reply['run_id'])
    assert job['status'] == 'succeeded' and job['completed_targets'] == 4
    choices = client.get('/api/pms/choices/SMAFIX').json()
    assert len(choices['choices']) == 4
    assert all(p['status']=='ok' and not p['engine_stale'] for p in choices['choices'])
    saved = []
    for choice in choices['choices']:
        params = dict(run_id=choices['run_id'], key=choice['key'], version=choice['version'])
        selected = client.get('/api/pms/timing/SMAFIX', params=params).json()
        assert not selected['needs_recompute'] and selected['bars'][-1]['time']==xs[-1]['date']
        if choice['key'].startswith('sma-'):
            assert selected['pm_family']=='sma' and selected['params']['period']==200
            assert len(selected['overlays']['sma'])==260
            assert 'donchian_up' not in selected['overlays']
            assert all(t['direction']==choice['direction'] for t in selected['trades'])
            saved.append((params, selected))
    out = client.get('/api/pms/assessment/SMAFIX').json()
    for family in ('sma','donchian'):
        paired = client.get('/api/pms/family-timing/SMAFIX', params={'run_id':choices['run_id'],'family':family}).json()
        assert paired['status']=='ok' and set(paired['directions'])=={'long','short'}
        assert paired['unavailable_directions']=={} and 'pm_direction' not in paired
        sides = paired['directions']
        expected = [(l+s)/2 for l,s in zip(sides['long']['equity']['strat_equity'], sides['short']['equity']['strat_equity'])]
        assert paired['equity']['strat_equity'] == pytest.approx(expected)
        assert engine.compound([d['strat_ret'] for d in paired['daily']]) == pytest.approx(expected)
        assert paired['metrics']['strategy']['total_return'] == pytest.approx(expected[-1]-1)
        assert len(paired['bars'])==len(xs)
        if family=='sma':
            assert paired['trades']==sorted([t for _,v in saved for t in v['trades']],key=lambda t:(t['entry_date'],t['direction']))
            assert all(paired['directions'][v['pm_direction']]==v['directions'][v['pm_direction']] for _,v in saved)
    assert out['coverage']['expected_families']==2 and out['coverage']['available_families']==2
    assert all('PM engine version is outdated' not in p['reasons'] for p in out['pms'])
    with get_connection() as conn:
        count = conn.execute('SELECT COUNT(*) FROM pm_results').fetchone()[0]
        conn.execute("UPDATE price_bars SET adj_close=adj_close+.01 WHERE symbol='SMAFIX'")
        # Disabling one direction changes future plans, never its sibling or saved run.
        repository.assign(conn, 'SMAFIX', sma.definitions()[1], enabled=False)
        _, plan = service.freeze(conn, ['SMAFIX'])
        assert {d.key for _, d, _ in plan} == {'donchian-long','donchian-short-benchmark','sma-trend-long'}
    for params, selected in saved:
        reread = client.get('/api/pms/timing/SMAFIX', params=params).json()
        assert reread['stale'] and reread['bars']==selected['bars'] and reread['trades']==selected['trades']
    with get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM pm_results').fetchone()[0]==count
    # A disabled direction remains unavailable, never fabricated as a flat account.
    reply = client.post('/api/pms/run', json={'symbols':['SMAFIX']}).json()
    assert wait_job(client, reply['run_id'])['status']=='succeeded'
    latest = client.get('/api/pms/choices/SMAFIX').json()
    partial = client.get('/api/pms/family-timing/SMAFIX', params={'run_id':latest['run_id'],'family':'sma'}).json()
    assert partial['status']=='ok' and set(partial['directions'])=={'long'}
    assert partial['unavailable_directions']=={'short':'Not included in this saved run'}
    assert 'metrics' not in partial and 'equity' not in partial
    original = client.get('/api/pms/family-timing/SMAFIX', params={'run_id':choices['run_id'],'family':'sma'}).json()
    assert set(original['directions'])=={'long','short'} and original['stale']
