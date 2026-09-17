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
from . import repository as repo, registry
from .adapters import adapt
from .contracts import PMResult, Position, content_hash
from .versions import current_engine_version


def load_bars(conn, symbol):
    table='crypto_bars' if '/' in symbol else 'price_bars'
    fields='open o,high h,low l,close c' if '/' in symbol else 'adj_open o,adj_high h,adj_low l,adj_close c'
    return [dict(r) for r in conn.execute(f'SELECT date,{fields},volume v FROM {table} WHERE symbol=? ORDER BY date',(symbol,))]


def freeze(conn, symbols=None, family=None):
    """One SQLite read transaction freezes assignments and compressed asset inputs."""
    frozen,plan={},[]
    if family is not None: registry.get(family)
    with repo.atomic(conn):
        if symbols is None:
            symbols=[r[0] for r in conn.execute('SELECT symbol FROM price_bars UNION SELECT symbol FROM crypto_bars UNION SELECT symbol FROM pm_assignments')]
        for symbol in sorted({prices.normalize_symbol(s) for s in symbols}):
            params=SignalParams(**signals.resolve_one(conn,symbol)['params'])
            selected={d.key:d for strategy in registry.STRATEGIES.values() for d in strategy.definitions(params)}
            for definition,enabled in repo.assignments(conn,symbol):
                if enabled: selected[definition.key]=definition
                else: selected.pop(definition.key,None)
            if family is not None: selected={k:d for k,d in selected.items() if d.family==family}
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
    result,start=registry.get(definition.family).execute(bars,definition)
    return adapt(symbol,bars,definition,result,start)


def run(conn: sqlite3.Connection, fetch_run_id: int, scope_arg=None):
    selected=json.loads(scope_arg) if scope_arg else None
    family=selected.get('family') if isinstance(selected,dict) else None
    symbols=selected.get('symbols') if isinstance(selected,dict) else selected
    jobs.raise_if_cancelled(fetch_run_id)
    frozen,plan=freeze(conn,symbols,family)
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


def choices(conn,symbol,run_id=None,family=None):
    symbol=prices.normalize_symbol(symbol)
    if run_id is None:
        row=conn.execute('''SELECT MAX(t.run_id) FROM pm_targets t JOIN pm_definitions d
            ON d.pm_key=t.pm_key AND d.version=t.version WHERE t.symbol=?
            AND (? IS NULL OR json_extract(d.definition_json,'$.family')=?)''',(symbol,family,family)).fetchone()
        run_id=row[0]
    if run_id is None: return {'status':'not_computed','symbol':symbol,'choices':[]}
    run_info=repo.get_run(conn,run_id)
    if not run_info: raise ValueError('PM run not found')
    current_hash=content_hash(load_bars(conn,symbol))
    options=[]
    for row in conn.execute('''SELECT t.*,d.definition_json FROM pm_targets t JOIN pm_definitions d
        ON d.pm_key=t.pm_key AND d.version=t.version WHERE t.run_id=? AND t.symbol=? ORDER BY t.pm_key''',(run_id,symbol)):
        definition=json.loads(row['definition_json'])
        if family is not None and definition['family']!=family: continue
        options.append({'key':row['pm_key'],'version':row['version'],'name':definition['name'],
                        'family':definition['family'],'direction':definition['direction'],'status':row['status'],'error':row['error'],
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


def family_timing(conn,run_id,symbol,family):
    """Read both independent accounts from one saved run; never execute a strategy."""
    from app.features.signals.metrics import summarise
    options = choices(conn,symbol,run_id)
    members = [p for p in options['choices'] if p['family']==family]
    if not members: raise ValueError('This strategy has no results in the requested run')
    views = {}
    unavailable = {}
    for side in ('long','short'):
        member = next((p for p in members if p['direction']==side),None)
        if member is None:
            unavailable[side] = 'Not included in this saved run'
        elif member['status']!='ok':
            unavailable[side] = member['error'] or member['status']
        else:
            views[side] = timing(conn,run_id,symbol,member['key'],member['version'])
    base = {'symbol':options['symbol'],'pm_family':family,
            'pm_name':registry.get(family).name,
            'pm_run_id':run_id,'pm_run_status':options['run_status'],
            'computed_at':options['computed_at'],'unavailable_directions':unavailable}
    if not views:
        return {**base,'status':'not_computed','reason':'No usable direction results in this saved run'}
    first = next(iter(views.values()))
    result = {**first,**base,'directions':{side:v['directions'][side] for side,v in views.items()},
              'stale':any(v['stale'] for v in views.values()),
              'needs_recompute':any(v['needs_recompute'] for v in views.values()),
              'trades':sorted([t for v in views.values() for t in v['trades']],key=lambda t:(t['entry_date'],t['direction'])),
              'markers':sorted([m for v in views.values() for m in v['markers']],key=lambda m:(m['time'],m['side']))}
    for key in ('pm_key','pm_version','pm_direction','state','pending_action','metrics','equity','daily'):
        result.pop(key,None)
    if unavailable: return result  # Never report partial coverage as combined performance.
    long,short = views['long'],views['short']
    if long['equity']['dates'] != short['equity']['dates']:
        raise ValueError('Saved direction histories do not align')
    combined = [(l+s)/2 for l,s in zip(long['equity']['strat_equity'],short['equity']['strat_equity'])]
    previous = 1.0
    daily = []
    for l,s,value in zip(long['daily'],short['daily'],combined):
        la,sa = l['state']!=0,s['state']!=0
        daily.append({'date':l['date'],'state':2 if la and sa else 1 if la else -1 if sa else 0,
                      'long_active':la,'short_active':sa,'long_ret':l['strat_ret'],'short_ret':s['strat_ret'],
                      'strat_ret':value/previous-1 if previous else 0})
        previous = value
    bars = [{'date':b['time'],'o':b['open'],'h':b['high'],'l':b['low'],'c':b['close'],'v':b['volume']} for b in first['bars']]
    result.update(daily=daily,metrics=summarise(result['trades'],daily,bars),
                  equity={**long['equity'],'strat_equity':combined,'drawdown':engine.drawdown_curve(combined)})
    return result


def board(conn,run_id=None):
    if run_id is None: run_id=conn.execute('SELECT MAX(id) FROM pm_runs').fetchone()[0]
    if run_id is None: return {'status':'not_computed','rows':[],'pms':[]}
    info=repo.get_run(conn,run_id)
    if not info: raise ValueError('PM run not found')
    rows=[]; pms={}
    for target in conn.execute('''SELECT t.*,d.definition_json FROM pm_targets t JOIN pm_definitions d
        ON d.pm_key=t.pm_key AND d.version=t.version WHERE t.run_id=? ORDER BY t.symbol,t.pm_key''',(run_id,)):
        definition=json.loads(target['definition_json'])
        pms[target['pm_key']]={'key':target['pm_key'],'name':definition['name'],'family':definition['family'],'direction':definition['direction']}
        rows.append({**json.loads(target['summary_json'] or '{}'),'symbol':target['symbol'],
                     'pm_key':target['pm_key'],'pm_version':target['version'],'pm_name':definition['name'],
                     'family':definition['family'],'direction':definition['direction'],'status':target['status'],'error':target['error']})
    return {'status':'ok','run_id':run_id,'run_status':info['status'],'computed_at':info['finished_at'],
            'rows':rows,'pms':list(pms.values())}
