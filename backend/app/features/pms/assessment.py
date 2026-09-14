"""Descriptive family support. Contract in assessment-contract.md; no mutations."""
from __future__ import annotations
from collections import defaultdict
from datetime import date, datetime, timezone
import json
import zlib

from app.features.signals.params import ENGINE_VERSION
from app.features.signals.data import normalize_symbol
from . import repository as repo
from .contracts import content_hash

CONTRACT_VERSION = 'descriptive-1'
RECENT_BARS = 5
MAX_AGE_DAYS = 7


def assess(symbol, run_id, targets, bars, current_hash, assessed_on):
    dates=[b['date'] for b in bars]
    cutoff=dates[-1] if dates else None
    saved_hash=content_hash(bars) if bars else None
    indices={day:i for i,day in enumerate(dates)}
    recent_start=max(0,len(dates)-RECENT_BARS)
    rows=[]
    for target in targets:
        definition=target['definition']; result=target['result']
        reasons=[]
        if target['status']!='ok' or result is None:
            reasons.append(target.get('error') or f"PM result {target['status']}")
        if saved_hash is None: reasons.append('Saved chart inputs unavailable')
        elif target['input_hash']!=saved_hash: reasons.append('PM and saved chart input versions differ')
        if saved_hash!=current_hash: reasons.append('Stored prices changed since this run')
        if cutoff:
            age=(assessed_on-date.fromisoformat(cutoff)).days
            if age>MAX_AGE_DAYS: reasons.append(f'Saved prices are {age} calendar days old')
            if age<0: reasons.append('Saved cutoff is after the assessment date')
        if definition['engine_version']!=ENGINE_VERSION: reasons.append('PM engine version is outdated')
        if definition['horizon']!='daily': reasons.append('Unsupported comparison horizon')
        if result is not None and result.as_of!=cutoff: reasons.append('PM cutoff differs from saved asset cutoff')
        pending=result.pending_action if result is not None else None
        if pending and (pending.action=='reverse' or pending.signal_date!=cutoff):
            reasons.append('Pending action is unsupported or not confirmed at the cutoff')
        state=result.position.state if result is not None else None
        if not reasons and state is None: reasons.append('Position is unavailable')
        observation='unavailable'; support=None; recent=False
        if not reasons:
            if pending and pending.action=='exit': observation='exit'
            elif pending and pending.action=='enter':
                observation='fresh_entry'; support=definition['direction']; recent=True
            elif state in ('long','short'):
                observation='active_support'; support=state
                opened=next((t for t in reversed(result.trades) if t.get('exit_date') is None),None)
                fill_i=indices.get(opened['entry_date']) if opened else None
                recent=fill_i is not None and fill_i>0 and fill_i-1>=recent_start
            else: observation='abstain'
        rows.append({'key':definition['key'],'version':definition['version'],'name':definition['name'],
                     'family':definition['family'],'direction':definition['direction'],'horizon':definition['horizon'],
                     'benchmark':definition['benchmark'],'voting_enabled':definition['voting_enabled'],
                     'input_hash':target['input_hash'],'cutoff':result.as_of if result else None,
                     'position':state,'observation':observation,'support':support,'recent':recent,
                     'pending_action':pending.model_dump() if pending else None,
                     'reasons':reasons,'excluded_reason':'Benchmark: visible, excluded from support counts' if definition['benchmark'] else None})
    grouped=defaultdict(list)
    for row in rows:
        if not row['benchmark']: grouped[row['family']].append(row)
    families=[]
    for name,members in sorted(grouped.items()):
        available=sum(m['observation']!='unavailable' for m in members)
        directions={m['support'] for m in members}
        status=('unavailable' if available<len(members) else 'mixed' if len(directions)>1 else
                next(iter(directions)) or 'abstain')
        families.append({'family':name,'status':status,'expected':len(members),'available':available,
                         'recent':status in ('long','short') and all(m['recent'] for m in members),
                         'members':[{'key':m['key'],'version':m['version']} for m in members]})
    expected=sum(f['expected'] for f in families); available=sum(f['available'] for f in families)
    return {'contract_version':CONTRACT_VERSION,'symbol':symbol,'run_id':run_id,'cutoff':cutoff,
            'assessed_on':assessed_on.isoformat(),'status':'no_families' if not families else 'unavailable' if available<expected else 'ok',
            'recent_asset_bars':RECENT_BARS,'max_age_calendar_days':MAX_AGE_DAYS,
            'coverage':{'expected_pms':expected,'available_pms':available,'expected_families':len(families),
                        'available_families':sum(f['status']!='unavailable' for f in families)},
            'long_support':[f['family'] for f in families if f['status']=='long'],
            'short_support':[f['family'] for f in families if f['status']=='short'],
            'recent_long':[f['family'] for f in families if f['status']=='long' and f['recent']],
            'recent_short':[f['family'] for f in families if f['status']=='short' and f['recent']],
            'mixed':[f['family'] for f in families if f['status']=='mixed'],'families':families,'pms':rows}


def read(conn, symbol, run_id=None, assessed_on=None):
    from .service import load_bars
    symbol=normalize_symbol(symbol)
    with repo.atomic(conn):
        if run_id is None:
            run_id=conn.execute('SELECT MAX(run_id) FROM pm_targets WHERE symbol=?',(symbol,)).fetchone()[0]
        if run_id is None: return {'status':'not_computed','symbol':symbol}
        info=repo.get_run(conn,run_id)
        if not info: raise ValueError('PM run not found')
        targets=[]
        for row in conn.execute('''SELECT t.*,d.definition_json FROM pm_targets t JOIN pm_definitions d
            ON d.pm_key=t.pm_key AND d.version=t.version WHERE t.run_id=? AND t.symbol=? ORDER BY t.pm_key''',(run_id,symbol)):
            targets.append({'definition':json.loads(row['definition_json']), 'status':row['status'], 'error':row['error'],
                            'input_hash':row['input_hash'],
                            'result':repo.get_result(conn,run_id,symbol,row['pm_key'],row['version'])})
        if not targets: raise ValueError('Asset is not in this PM run')
        frozen=conn.execute('SELECT bars FROM pm_inputs WHERE run_id=? AND symbol=?',(run_id,symbol)).fetchone()
        bars=json.loads(zlib.decompress(frozen['bars'])) if frozen else []
        output=assess(symbol,run_id,targets,bars,content_hash(load_bars(conn,symbol)),
                      assessed_on or datetime.now(timezone.utc).date())
    return {**output,'run_status':info['status']}
