"""Assessment counts never mutate or replace the underlying independent PMs."""
from datetime import date, timedelta
import json
import zlib

from app.features.pms.assessment import assess, read
from app.features.pms.contracts import PMDefinition, PMResult, Position, PendingAction, content_hash
from app.features.pms import repository
from app.features.signals.params import ENGINE_VERSION
from tests.test_pms import pm_db

BARS=[{'date':(date(2026,9,1)+timedelta(days=i)).isoformat(),'o':100.,'h':101.,'l':99.,'c':100.,'v':1.} for i in range(12)]
DIGEST=content_hash(BARS)


def target(key='a',family='trend',direction='long',state='long',pending=None,benchmark=False,entry=9):
    pm=PMDefinition.create(key=key,name=key,family=family,direction=direction,parameters={},
                           engine_version=ENGINE_VERSION,benchmark=benchmark)
    result=PMResult(symbol='X',pm=pm,input_hash=DIGEST,as_of=BARS[-1]['date'],status='ok',
                    position=Position(state=state),
                    pending_action=PendingAction(action=pending,direction=direction,signal_date=BARS[-1]['date'],fill_at='open_next') if pending else None,
                    trades=[{'direction':direction,'entry_date':BARS[entry]['date'],'exit_date':None}] if state!='flat' else [])
    return {'definition':pm.model_dump(),'result':result,'status':'ok','error':None,'input_hash':DIGEST}


def calculate(targets,**kwargs):
    return assess('X',1,targets,BARS,kwargs.get('current_hash',DIGEST),kwargs.get('assessed_on',date(2026,9,14)))


def test_family_deduplication_benchmark_exclusion_and_no_mutation():
    inputs=[target(),target('b'),target('c','pullback'),target('bench',direction='short',state='short',benchmark=True)]
    before=[t['result'].model_dump_json() for t in inputs]
    out=calculate(inputs)
    assert out['long_support']==['pullback','trend'] and out['short_support']==[]
    assert out['coverage']==dict(expected_pms=3,available_pms=3,expected_families=2,available_families=2)
    assert out['recent_long']==['pullback','trend']
    assert out['pms'][-1]['excluded_reason'] and out['pms'][-1]['support']=='short'
    assert [t['result'].model_dump_json() for t in inputs]==before


def test_flat_is_abstention_opposition_is_explicit_and_mixed_is_not_two_votes():
    out=calculate([target(),target('b',state='flat')])
    assert out['mixed']==['trend'] and not out['long_support'] and not out['short_support']
    out=calculate([target(),target('b','failed-rally',direction='short',state='short')])
    assert out['long_support']==['trend'] and out['short_support']==['failed-rally']
    out=calculate([target(state='flat')])
    assert out['families'][0]['status']=='abstain' and out['status']=='ok'


def test_fresh_old_hold_exit_and_five_asset_bar_boundary():
    out=calculate([target('fresh','new',state='flat',pending='enter'),target('old','old',entry=2),
                   target('exiting','exit',pending='exit'),target('edge','edge',entry=8),
                   target('outside','outside',entry=7)])
    rows={r['key']:r for r in out['pms']}
    assert rows['fresh']['observation']=='fresh_entry' and rows['fresh']['recent']
    assert rows['old']['observation']=='active_support' and not rows['old']['recent']
    assert rows['exiting']['position']=='long' and rows['exiting']['support'] is None
    assert rows['edge']['recent'] and not rows['outside']['recent']


def test_missing_changed_and_old_inputs_preserve_required_denominator():
    missing=target('missing'); missing.update(status='failed',error='failed fixture',result=None)
    out=calculate([target(),missing])
    assert out['status']=='unavailable' and out['coverage']['expected_pms']==2
    assert out['coverage']['available_pms']==1 and not out['long_support']
    assert out['families'][0]['status']=='unavailable'
    changed=calculate([target()],current_hash='changed')
    assert changed['pms'][0]['observation']=='unavailable'
    assert 'Stored prices changed' in changed['pms'][0]['reasons'][0]
    old=calculate([target()],assessed_on=date(2026,9,20))
    assert old['status']=='unavailable'
    assert calculate([target()],assessed_on=date(2026,9,19))['status']=='ok'


def test_read_uses_exact_latest_attempt_and_is_read_only(pm_db):
    pm_db.execute('CREATE TABLE price_bars(symbol TEXT,date TEXT,adj_open REAL,adj_high REAL,adj_low REAL,adj_close REAL,volume REAL)')
    pm_db.executemany('INSERT INTO price_bars VALUES (?,?,?,?,?,?,?)',
                      [('X',b['date'],b['o'],b['h'],b['l'],b['c'],b['v']) for b in BARS])
    t=target(); pm=t['result'].pm
    first=repository.create_run(pm_db,[('X',pm,DIGEST)])
    pm_db.execute('INSERT INTO pm_inputs VALUES (?,?,?,?)',(first,'X',DIGEST,zlib.compress(json.dumps(BARS).encode())))
    repository.save_result(pm_db,first,t['result']);repository.finish_run(pm_db,first)
    before=pm_db.total_changes
    out=read(pm_db,'x',first,assessed_on=date(2026,9,14))
    assert out['status']=='ok' and pm_db.total_changes==before
    second=repository.create_run(pm_db,[('X',pm,DIGEST)])
    repository.fail_target(pm_db,second,'X',pm.key,pm.version,'new attempt failed');repository.finish_run(pm_db,second)
    out=read(pm_db,'X',assessed_on=date(2026,9,14))
    assert out['run_id']==second and out['status']=='unavailable'
    assert out['pms'][0]['observation']=='unavailable'
    assert repository.get_result(pm_db,first,'X',pm.key,pm.version)==t['result']
