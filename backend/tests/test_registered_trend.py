"""Shared app contract and full-history execution, using synthetic price fixtures."""
from dataclasses import replace
import math

import pytest

from app.db.connection import get_connection
from app.features.pms import registry, service, trend
from app.features.pms.contracts import PMDefinition
from tests.test_pms import wait_job
from tests.test_sma_pms import bars


def seed(symbol='QQQ'):
    xs = bars([100+12*math.sin(i/18)+i*.02 for i in range(300)])
    with get_connection() as conn:
        conn.executemany('''INSERT INTO price_bars
            (symbol,date,open,high,low,close,volume,adj_open,adj_high,adj_low,adj_close)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            [(symbol,b['date'],b['o'],b['h'],b['l'],b['c'],b['v'],b['o'],b['h'],b['l'],b['c']) for b in xs])
    return xs


def submit(client, family=None):
    reply = client.post('/api/pms/run',json={'family':family,'symbols':['QQQ']})
    assert reply.status_code==200
    job = wait_job(client, reply.json()['run_id'])
    assert job['status']=='succeeded' and job['mode']=='full'
    return job


def test_registered_strategy_gets_complete_trend_contract_and_runs(client, monkeypatch):
    xs = seed()
    calls = []
    sma = registry.get('sma')
    def definitions(assigned):
        return [PMDefinition.create(**{**d.model_dump(exclude={'version'}),
                'family':'fixture','key':'fixture-'+d.direction,'name':'Fixture '+d.direction})
                for d in sma.definitions(assigned)]
    def execute(history, definition):
        calls.append((definition.direction,len(history),history[0]['c']))
        return sma.execute(history, definition)
    monkeypatch.setitem(registry.STRATEGIES,'fixture',replace(sma,key='fixture',name='Fixture strategy',definitions=definitions,execute=execute))
    monkeypatch.setattr(trend.context,'_momentum_map',lambda conn:{'QQQ':{'score':72.,'leader':True,'persistence':.8}})
    assert {'key':'fixture','name':'Fixture strategy'} in client.get('/api/pms/strategies').json()
    assert submit(client,'fixture')['completed_targets']==2
    assert {(side,n) for side,n,_ in calls}=={('long',300),('short',300)}
    original = client.get('/api/pms/trend/fixture?charts=1').json()
    assert original['status']=='ok' and original['family']=='fixture'
    assert set(original) >= {'long','short','flat','watchlist','pending','unavailable','strategies','counts'}
    qqq = original['watchlist'][0]['rows'][0]
    assert qqq['symbol']=='QQQ' and qqq['momentum']['score']==72 and qqq['vol_60d'] > 0
    assert len(qqq['chart']['bars'])==300 and qqq['chart']['bars'][0]['t']==xs[0]['date']
    assert set(qqq['directions'])=={'long','short'}
    for side, state in qqq['directions'].items():
        assert state['vol_60d']==qqq['vol_60d'] and state['momentum']==qqq['momentum']
        assert state['family']=='fixture' and state['pm_key']=='fixture-'+side
        assert state['pm_run_id']==original['pm_run_id']
        saved = client.get('/api/pms/timing/QQQ',params={'run_id':state['pm_run_id'],'key':state['pm_key'],'version':state['pm_version']}).json()
        events = [e for e in qqq['chart']['events'] if e['dir']==side]
        assert [e['entry_date'] for e in events]==[t['entry_date'] for t in saved['trades'][-12:]]
    missing = original['watchlist'][0]['rows'][1]
    assert missing['symbol']=='SPY' and missing['state'] is None
    assert all(s['state'] is None for s in missing['directions'].values())
    assert all(r['symbol']!='SPY' for r in original['flat'])

    # A newer run of a different strategy does not erase this family's board.
    assert submit(client,'sma')['completed_targets']==2
    assert client.get('/api/pms/trend/fixture').json()['pm_run_id']==original['pm_run_id']
    choices=client.get('/api/pms/choices/QQQ?family=fixture').json()
    assert choices['run_id']==original['pm_run_id'] and len(choices['choices'])==2
    assert all(p['family']=='fixture' for p in choices['choices'])
    # Revising the first bar must still be replayed by both sides of a selected run.
    with get_connection() as conn:
        conn.execute("UPDATE price_bars SET adj_close=adj_close+.1 WHERE symbol='QQQ' AND date=?",(xs[0]['date'],))
    assert submit(client,'fixture')['completed_targets']==2
    assert calls[-2:]==[('long',300,xs[0]['c']+.1),('short',300,xs[0]['c']+.1)]
    assert submit(client)['completed_targets']==6  # Run all discovers the new registration.
    # These UI reads must never invoke execution or write/replace any saved result.
    monkeypatch.setattr(service,'evaluate',lambda *args:pytest.fail('View read executed a strategy'))
    with get_connection() as conn:
        count = conn.execute('SELECT COUNT(*) FROM pm_results').fetchone()[0]
    for family in registry.STRATEGIES:
        response = client.get('/api/pms/trend/'+family+'?charts=1')
        assert response.status_code==200 and response.json()['status']=='ok'
    old = client.get('/api/pms/trend/fixture',params={'charts':1,'run_id':original['pm_run_id']}).json()
    assert old['watchlist'][0]['rows'][0]['chart']==qqq['chart']
    with get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM pm_results').fetchone()[0]==count


def test_unavailable_direction_is_visible_in_shared_board(client):
    from app.features.pms import repository, sma
    seed()
    with get_connection() as conn:
        repository.assign(conn,'QQQ',sma.definitions()[1],enabled=False)
    assert submit(client,'sma')['completed_targets']==1
    result=client.get('/api/pms/trend/sma?charts=1').json()
    assert result['unavailable'][0]['direction']=='short'
    assert result['unavailable'][0]['state'] is None
    assert 'Not included' in result['unavailable'][0]['error']
    assert result['flat']==[] and result['short']==[]
