"""Independent PM identity, adaptation and persistence invariants."""
import math
import pytest
from pydantic import ValidationError

from app.features.pms.adapters import existing_pair
from app.features.pms.contracts import PMDefinition, PMResult
from app.features.signals import engine
from app.features.signals.params import LONG_PARAMS
from tests.test_signals import _bars
from app.features.pms import repository
from pathlib import Path
import sqlite3
import time
from app.features.pms import service as pm_service
from tests.test_signals import _seed_bars


@pytest.fixture
def pm_db(tmp_path):
    conn=sqlite3.connect(tmp_path/'pms.sqlite3',isolation_level=None)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    # An existing table/result represents pre-migration user data.
    conn.executescript("CREATE TABLE fetch_runs(id INTEGER PRIMARY KEY); CREATE TABLE signal_symbol_stats(symbol TEXT); INSERT INTO signal_symbol_stats VALUES ('KEPT');")
    conn.executescript((Path(__file__).resolve().parents[2]/'schema/migrations/0019_independent_pms.sql').read_text())
    conn.commit()
    conn.executescript((Path(__file__).resolve().parents[2]/'schema/migrations/0020_pm_frozen_inputs.sql').read_text())
    conn.commit()
    conn.executescript((Path(__file__).resolve().parents[2]/'schema/migrations/0021_pm_target_summaries.sql').read_text())
    conn.commit()
    yield conn
    conn.close()


def test_adapters_preserve_both_production_books_and_versions():
    bars=_bars([100+20*math.sin(i/18)+i*.03 for i in range(500)])
    pair=engine.run_pair(bars,LONG_PARAMS)
    adapted=existing_pair('TEST',bars,LONG_PARAMS)
    for result in adapted:
        original=pair.directions[result.pm.direction]
        assert result.trades==original.trades
        assert result.daily==original.daily
        assert result.overlays==original.overlays
        assert result.pending_action.model_dump() == original.pending_action if original.pending_action else result.pending_action is None
    changed=existing_pair('TEST',bars,LONG_PARAMS.model_copy(update={'entry_len':55}))
    assert changed[0].pm.version!=adapted[0].pm.version
    assert changed[1].pm==adapted[1].pm
    assert changed[1].trades==adapted[1].trades
    assert adapted[0].input_hash==adapted[1].input_hash
    assert adapted[1].pm.benchmark and not adapted[1].pm.voting_enabled


def test_missing_history_is_unknown_not_flat_and_definition_is_verified():
    for result in existing_pair('TEST',_bars([100.]*20),LONG_PARAMS):
        assert result.status=='insufficient_history'
        assert result.position.state is None
        assert not result.trades
    result=existing_pair('TEST',_bars([100.]*100),LONG_PARAMS)[0]
    bad=result.pm.model_dump()
    bad['parameters']['entry_len']=100
    with pytest.raises(ValidationError,match='frozen definition'): PMDefinition.model_validate(bad)
    bad=result.model_dump()
    bad['position']['state']='short'
    with pytest.raises(ValidationError,match='another PM'): PMResult.model_validate(bad)


def test_same_side_and_opposing_pms_survive_independent_saves(pm_db):
    a,short=existing_pair('TEST',_bars([100+20*math.sin(i/18) for i in range(400)]),LONG_PARAMS)
    b=a.model_copy(deep=True)
    b.pm=PMDefinition.create(**{**a.pm.model_dump(exclude={'version'}),'key':'another-long','name':'Another long'})
    run=repository.create_run(pm_db,[(r.symbol,r.pm,r.input_hash) for r in [a,b,short,a]])
    for r in [a,b,short]: repository.save_result(pm_db,run,r)
    assert repository.finish_run(pm_db,run)=='succeeded'
    for r in [a,b,short]:
        assert repository.get_result(pm_db,run,r.symbol,r.pm.key,r.pm.version)==r
    assert pm_db.execute('SELECT COUNT(*) FROM pm_targets').fetchone()[0]==3
    assert pm_db.execute('SELECT symbol FROM signal_symbol_stats').fetchone()[0]=='KEPT'
    with pytest.raises(ValueError,match='already final'): repository.save_result(pm_db,run,b)
    assert repository.get_result(pm_db,run,a.symbol,a.pm.key,a.pm.version)==a


def test_changed_input_rejected_and_failed_attempt_does_not_replace_success(pm_db):
    a,b=existing_pair('TEST',_bars([100.]*100),LONG_PARAMS)
    good=repository.create_run(pm_db,[(a.symbol,a.pm,a.input_hash)])
    repository.save_result(pm_db,good,a);repository.finish_run(pm_db,good)
    later=repository.create_run(pm_db,[(r.symbol,r.pm,r.input_hash) for r in [a,b]])
    with pytest.raises(ValueError,match='frozen target input'):
        repository.save_result(pm_db,later,a.model_copy(update={'input_hash':'changed'}))
    with pytest.raises(ValueError,match='unresolved'): repository.finish_run(pm_db,later)
    repository.save_result(pm_db,later,a)
    repository.fail_target(pm_db,later,b.symbol,b.pm.key,b.pm.version,'example failure')
    assert repository.finish_run(pm_db,later)=='partial'
    assert repository.get_result(pm_db,good,a.symbol,a.pm.key,a.pm.version)==a
    assert repository.get_result(pm_db,later,b.symbol,b.pm.key,b.pm.version) is None


def test_assignment_versions_and_cancelled_targets(pm_db):
    a,_=existing_pair('TEST',_bars([100.]*100),LONG_PARAMS)
    repository.assign(pm_db,'TEST',a.pm)
    changed=existing_pair('TEST',_bars([100.]*100),LONG_PARAMS.model_copy(update={'entry_len':55}))[0]
    repository.assign(pm_db,'TEST',changed.pm,enabled=False)
    assert repository.assignments(pm_db,'TEST')==[(changed.pm,False)]
    assert pm_db.execute('SELECT COUNT(*) FROM pm_definitions').fetchone()[0]==2
    run=repository.create_run(pm_db,[(a.symbol,a.pm,a.input_hash)])
    assert repository.finish_run(pm_db,run,cancelled=True)=='cancelled'
    with pytest.raises(ValueError,match='already final'): repository.save_result(pm_db,run,a)


def wait_job(client, job_id):
    for _ in range(200):
        job=client.get(f'/api/data/runs/{job_id}').json()
        if job['status'] not in ('queued','running'): return job
        time.sleep(.02)
    pytest.fail('PM worker did not finish')


def test_worker_persists_both_pms_and_reads_frozen_charts_without_rerun(client):
    from app.db.connection import get_connection
    with get_connection() as conn: _seed_bars(conn,'SPY',n=180)
    assert client.get('/api/pms/choices/SPY').json()['status']=='not_computed'
    reply=client.post('/api/pms/run',json={'symbols':['SPY','SPY']}).json()
    job=wait_job(client,reply['run_id'])
    assert job['status']=='succeeded',job
    assert job['planned_targets']==job['completed_targets']==4
    choices=client.get('/api/pms/choices/SPY').json()
    assert choices['run_status']=='succeeded'
    assert len(choices['choices'])==4
    board=client.get('/api/pms/board').json()
    assert len(board['rows'])==4 and len(board['pms'])==4
    assert {r['status'] for r in board['rows'] if r['pm_key'].startswith('sma-')}=={'insufficient_history'}
    params={'run_id':choices['run_id'],'key':choices['choices'][0]['key'],'version':choices['choices'][0]['version']}
    selected=client.get('/api/pms/timing/SPY',params=params).json()
    assert selected['status']=='ok' and len(selected['bars'])==180
    assert not selected['stale']
    with get_connection() as conn:
        count=conn.execute('SELECT COUNT(*) FROM pm_results').fetchone()[0]
        conn.execute("UPDATE price_bars SET adj_close=adj_close+1 WHERE symbol='SPY'")
    read=client.get('/api/pms/timing/SPY',params=params).json()
    assert read['stale'] and read['bars']==selected['bars']
    assert client.get('/api/pms/timing/SPY',params={**params,'key':'missing'}).status_code==404
    with get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM pm_results').fetchone()[0]==count
        # Compatibility path still works; PM chart selection did not replace legacy persistence.
    assert client.post('/api/signals/run',json={'symbol':'SPY'}).status_code==200


def test_disabled_assignments_and_partial_pm_failure_are_visible(client):
    from app.db.connection import get_connection
    with get_connection() as conn:
        _seed_bars(conn,'SPY',n=180)
        defs=existing_pair('SPY',_bars([100.]*180),LONG_PARAMS)
        repository.assign(conn,'SPY',defs[1].pm,enabled=False)
        bad=PMDefinition.create(**{**defs[0].pm.model_dump(exclude={'version'}),
                                  'key':'unsupported-pm','name':'Unsupported','family':'future-family'})
        repository.assign(conn,'SPY',bad)
    reply=client.post('/api/pms/run',json={'symbols':['SPY']}).json()
    job=wait_job(client,reply['run_id'])
    assert job['status']=='failed' and job['failed_targets']==1
    choices=client.get('/api/pms/choices/SPY').json()
    assert choices['run_status']=='partial'
    assert {r['key']:r['status'] for r in choices['choices']}=={
        'donchian-long':'ok','unsupported-pm':'failed',
        'sma-trend-long':'insufficient_history','sma-trend-short':'insufficient_history'}


def test_frozen_definitions_and_inputs_do_not_change_during_run(client):
    from app.db.connection import get_connection
    import zlib,json
    with get_connection() as conn:
        _seed_bars(conn,'SPY',n=180)
        frozen,plan=pm_service.freeze(conn,['SPY'])
        conn.execute("UPDATE price_bars SET adj_close=1 WHERE symbol='SPY'")
        for symbol,definition,input_hash in plan:
            bars=json.loads(zlib.decompress(frozen[symbol][1]))
            result=pm_service.evaluate(symbol,bars,definition)
            assert result.input_hash==input_hash
            assert result.status==('insufficient_history' if definition.family=='sma' else 'ok')


def test_worker_cancellation_preserves_completed_pm_and_marks_remaining(client,monkeypatch):
    from app.db.connection import get_connection
    from app.features.data_management import runs
    with get_connection() as conn: _seed_bars(conn,'SPY',n=180)
    calls=0
    def cancel_after_one(_):
        nonlocal calls
        calls+=1
        if calls>=3: raise runs.RunCancelled()
    monkeypatch.setattr(runs,'raise_if_cancelled',cancel_after_one)
    reply=client.post('/api/pms/run',json={'symbols':['SPY']}).json()
    job=wait_job(client,reply['run_id'])
    assert job['status']=='cancelled' and job['completed_targets']==1
    choices=client.get('/api/pms/choices/SPY').json()
    assert choices['run_status']=='cancelled'
    assert sorted(r['status'] for r in choices['choices'])==['cancelled','cancelled','cancelled','ok']


def test_worker_deduplicates_a_queued_pm_job(client,monkeypatch):
    from app.features.data_management import worker
    queued=[]
    class Queue:
        def put_nowait(self,job): queued.append(job)
    monkeypatch.setattr(worker,'_queue',Queue())
    a,first=worker.submit('pm_universe')
    b,second=worker.submit('pm_universe')
    assert a==b and first is False and second is True
    assert len(queued)==1


def test_held_pm_new_entry_other_exit_and_opposite_side_roundtrip(pm_db):
    from app.features.pms.adapters import definitions
    bars=_bars([100.]*100+[110.]*20+[121.,121.,108.,108.])
    for bar in bars:
        bar['h']=max(bar['o'],bar['c'])+.5
        bar['l']=min(bar['o'],bar['c'])-.5
    bars[70]['h']=120  # Older high blocks the 55-bar entry but not the 20-bar entry.
    long,short=definitions(LONG_PARAMS)
    slower=PMDefinition.create(**{**long.model_dump(exclude={'version'}),'key':'slow-long','name':'Slow long',
                                 'parameters':{**long.parameters,'entry_len':55}})
    saved=[]
    for length in [121,122,124]:
        results=[pm_service.evaluate('TEST',bars[:length],definition) for definition in (long,slower,short)]
        run=repository.create_run(pm_db,[(r.symbol,r.pm,r.input_hash) for r in results])
        for result in results: repository.save_result(pm_db,run,result)
        repository.finish_run(pm_db,run)
        saved.append((run,results))
    first,second,last=[entry[1] for entry in saved]
    assert first[0].position.state=='long'
    assert first[1].position.state=='flat' and first[1].pending_action.action=='enter'
    assert second[0].position.state==second[1].position.state=='long'
    assert second[0].position.state_since!=second[1].position.state_since
    assert last[0].position.state=='long' and last[1].position.state=='flat'
    assert last[2].position.state=='short'
    assert first[0].position.state_since==last[0].position.state_since
    assert first[0].position.current_stop==last[0].position.current_stop
    for run,results in saved:
        for result in results:
            assert repository.get_result(pm_db,run,result.symbol,result.pm.key,result.pm.version)==result
