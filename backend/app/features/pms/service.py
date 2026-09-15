"""Coherent frozen-input PM runs and read-only result selection."""
from __future__ import annotations

import json
import math
import sqlite3
import time
import zlib

from app.features.data_management import runs as jobs
from app.features.signals import data as prices, engine, repository as signals
from app.features.signals.params import SignalParams
from . import repository as repo, sma
from .adapters import adapt, definitions
from .contracts import PMResult, Position, content_hash
from .versions import current_engine_version


def load_bars(conn, symbol):
    table='crypto_bars' if '/' in symbol else 'price_bars'
    fields='open o,high h,low l,close c' if '/' in symbol else 'adj_open o,adj_high h,adj_low l,adj_close c'
    return [dict(r) for r in conn.execute(f'SELECT date,{fields},volume v FROM {table} WHERE symbol=? ORDER BY date',(symbol,))]


def freeze(conn, symbols=None):
    """One SQLite read transaction freezes assignments and compressed asset inputs."""
    frozen,plan={},[]
    with repo.atomic(conn):
        if symbols is None:
            symbols=[r[0] for r in conn.execute('SELECT symbol FROM price_bars UNION SELECT symbol FROM crypto_bars UNION SELECT symbol FROM pm_assignments')]
        for symbol in sorted({prices.normalize_symbol(s) for s in symbols}):
            params=SignalParams(**signals.resolve_one(conn,symbol)['params'])
            selected={d.key:d for d in (*definitions(params), *sma.definitions())}
            for definition,enabled in repo.assignments(conn,symbol):
                if enabled: selected[definition.key]=definition
                else: selected.pop(definition.key,None)
            if not selected: continue
            bars=load_bars(conn,symbol)
            digest=content_hash(bars)
            frozen[symbol]=(digest,zlib.compress(json.dumps(bars,allow_nan=False).encode(),6))
            plan.extend((symbol,d,digest) for d in selected.values())
    return frozen,plan


def evaluate(symbol,bars,definition):
    bad=any(any(b[k] is None or not isinstance(b[k],(int,float)) or not math.isfinite(b[k]) or b[k]<=0
                for k in ('o','h','l','c')) or b['l']>min(b['o'],b['c']) or b['h']<max(b['o'],b['c']) for b in bars)
    if bad:
        return PMResult(symbol=symbol,pm=definition,input_hash=content_hash(bars),
                        as_of=bars[-1]['date'] if bars else None,status='invalid_data',
                        status_reason='Invalid OHLC input; no rows silently removed',position=Position(state=None))
    expected_version=current_engine_version(definition.family)
    if expected_version is None: raise ValueError(f'Unsupported PM family: {definition.family}')
    if definition.engine_version!=expected_version: raise ValueError('PM engine version needs a new definition')
    if definition.family=='sma':
        params=sma.SMAParams(**definition.parameters)
        start=max(definition.start_bar,params.start_bar())
        return adapt(symbol,bars,definition,sma.run(bars,params,definition.direction,start=start),start)
    params=SignalParams(**definition.parameters)
    if params.allow_long!=(definition.direction=='long') or params.allow_short!=(definition.direction=='short'):
        raise ValueError('PM direction does not match its engine parameters')
    start=max(definition.start_bar,params.warmup())
    result=engine.run(bars,params,start=start)
    return adapt(symbol,bars,definition,result,start)


def run(conn: sqlite3.Connection, fetch_run_id: int, scope_arg=None):
    selected=json.loads(scope_arg) if scope_arg else None
    jobs.raise_if_cancelled(fetch_run_id)
    frozen,plan=freeze(conn,selected)
    if not plan: raise ValueError('No enabled PM targets with selected assets')
    jobs.set_planned(conn,fetch_run_id,len(plan))
    with repo.atomic(conn):
        pm_run=repo.create_run(conn,plan,fetch_run_id)
        for symbol,(digest,payload) in frozen.items():
            conn.execute('INSERT INTO pm_inputs VALUES (?,?,?,?)',(pm_run,symbol,digest,payload))
    try:
        for symbol,definition,_ in plan:
            jobs.raise_if_cancelled(fetch_run_id)
            target=f'{symbol} / {definition.key}'
            jobs.start_target(conn,fetch_run_id,target)
            started=time.monotonic()
            try:
                bars=json.loads(zlib.decompress(frozen[symbol][1]))
                result=evaluate(symbol,bars,definition)
                repo.save_result(conn,pm_run,result)
                state='ok' if result.status=='ok' else 'skipped' if result.status=='insufficient_history' else 'error'
                jobs.finish_target(conn,fetch_run_id,target,status=state,rows=len(result.trades),
                    duration_ms=int((time.monotonic()-started)*1000),error=result.status_reason)
            except Exception as exc:
                # Failed PM cannot overwrite another result or abort its sibling targets.
                current=conn.execute('SELECT status FROM pm_targets WHERE run_id=? AND symbol=? AND pm_key=? AND version=?',
                                     (pm_run,symbol,definition.key,definition.version)).fetchone()
                if current and current['status']=='queued':
                    repo.fail_target(conn,pm_run,symbol,definition.key,definition.version,exc)
                jobs.finish_target(conn,fetch_run_id,target,status='error',error=str(exc)[:500])
        repo.finish_run(conn,pm_run)
    except jobs.RunCancelled:
        repo.finish_run(conn,pm_run,cancelled=True)
        raise
    except Exception:
        with repo.atomic(conn):
            conn.execute("UPDATE pm_targets SET status='failed',error='run interrupted' WHERE run_id=? AND status='queued'",(pm_run,))
            repo.finish_run(conn,pm_run)
        raise
    return pm_run


def choices(conn,symbol,run_id=None):
    symbol=prices.normalize_symbol(symbol)
    if run_id is None:
        row=conn.execute('SELECT MAX(run_id) FROM pm_targets WHERE symbol=?',(symbol,)).fetchone()
        run_id=row[0]
    if run_id is None: return {'status':'not_computed','symbol':symbol,'choices':[]}
    run_info=repo.get_run(conn,run_id)
    if not run_info: raise ValueError('PM run not found')
    current_hash=content_hash(load_bars(conn,symbol))
    options=[]
    for row in conn.execute('''SELECT t.*,d.definition_json FROM pm_targets t JOIN pm_definitions d
        ON d.pm_key=t.pm_key AND d.version=t.version WHERE t.run_id=? AND t.symbol=? ORDER BY t.pm_key''',(run_id,symbol)):
        definition=json.loads(row['definition_json'])
        options.append({'key':row['pm_key'],'version':row['version'],'name':definition['name'],
                        'direction':definition['direction'],'status':row['status'],'error':row['error'],
                        'stale':row['input_hash']!=current_hash,
                        'engine_stale':definition['engine_version']!=current_engine_version(definition['family'])})
    return {'status':'ok','symbol':symbol,'run_id':run_id,'run_status':run_info['status'],
            'computed_at':run_info['finished_at'],'choices':options}


def timing(conn,run_id,symbol,key,version):
    symbol=prices.normalize_symbol(symbol)
    result=repo.get_result(conn,run_id,symbol,key,version)
    if result is None: raise ValueError('This PM has no saved result in the requested run')
    run_info=repo.get_run(conn,run_id)
    base={'symbol':symbol,'pm_key':key,'pm_version':version,'pm_name':result.pm.name,'pm_direction':result.pm.direction,'pm_run_id':run_id,
          'pm_run_status':run_info['status'],'computed_at':run_info['finished_at'],
          'preview':False,'engine_version':result.pm.engine_version,'params':result.pm.parameters,
          'pm_family':result.pm.family}
    if result.status!='ok': return {**base,'status':'not_computed','pm_status':result.status,'reason':result.status_reason}
    frozen=conn.execute('SELECT bars FROM pm_inputs WHERE run_id=? AND symbol=?',(run_id,symbol)).fetchone()
    if frozen is None: raise ValueError('Original PM chart inputs are unavailable')
    bars=json.loads(zlib.decompress(frozen['bars']))
    equity={'dates':[r['date'] for r in result.daily],
            'strat_equity':engine.compound([r['strat_ret'] for r in result.daily]),
            'bh_equity':engine.compound(engine.buy_hold_daily(bars))}
    equity['drawdown']=engine.drawdown_curve(equity['strat_equity'])
    markers=[]
    for tr in result.trades:
        markers.append({'time':tr['entry_date'],'side':tr['direction'],'kind':'entry','label':result.pm.name})
        if tr['exit_date']: markers.append({'time':tr['exit_date'],'side':tr['direction'],'kind':'exit','label':tr['exit_reason']})
    state=result.position.model_dump()
    pending=result.pending_action.model_dump() if result.pending_action else None
    return {**base,'status':'ok','run_scope':'universe','chart_cached':True,
            'stale':content_hash(load_bars(conn,symbol))!=result.input_hash,
            'needs_recompute':result.pm.engine_version!=current_engine_version(result.pm.family),
            'run_through_date':result.as_of,'state':state,'pending_action':pending,'metrics':result.metrics,
            'trades':result.trades,'daily':result.daily,'overlays':result.overlays,'equity':equity,'markers':markers,
            'bars':[{'time':b['date'],'open':b['o'],'high':b['h'],'low':b['l'],'close':b['c'],'volume':b['v']} for b in bars],
            'key_levels':[], 'directions':{result.pm.direction:{'state':state,'pending_action':pending,
                'metrics':result.metrics,'overlays':result.overlays,'equity':equity,'params':result.pm.parameters}}}


def board(conn,run_id=None):
    if run_id is None: run_id=conn.execute('SELECT MAX(id) FROM pm_runs').fetchone()[0]
    if run_id is None: return {'status':'not_computed','rows':[],'pms':[]}
    info=repo.get_run(conn,run_id)
    if not info: raise ValueError('PM run not found')
    rows=[]; pms={}
    for target in conn.execute('''SELECT t.*,d.definition_json FROM pm_targets t JOIN pm_definitions d
        ON d.pm_key=t.pm_key AND d.version=t.version WHERE t.run_id=? ORDER BY t.symbol,t.pm_key''',(run_id,)):
        definition=json.loads(target['definition_json'])
        pms[target['pm_key']]={'key':target['pm_key'],'name':definition['name'],'direction':definition['direction']}
        rows.append({**json.loads(target['summary_json'] or '{}'),'symbol':target['symbol'],
                     'pm_key':target['pm_key'],'pm_version':target['version'],'pm_name':definition['name'],
                     'direction':definition['direction'],'status':target['status'],'error':target['error']})
    return {'status':'ok','run_id':run_id,'run_status':info['status'],'computed_at':info['finished_at'],
            'rows':rows,'pms':list(pms.values())}
