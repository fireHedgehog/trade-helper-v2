"""Adapt any registered strategy's saved results to the original Trend contract."""
import json
import zlib

from app.features.signals import service as context
from app.features.signals.watchlist import TREND_WATCHLIST_SECTIONS
from . import registry, repository


def latest_run(conn, family):
    return conn.execute('''SELECT MAX(t.run_id) FROM pm_targets t JOIN pm_definitions d
        ON d.pm_key=t.pm_key AND d.version=t.version
        WHERE json_extract(d.definition_json,'$.family')=?''', (family,)).fetchone()[0]


def board(conn, family, charts=False, run_id=None):
    strategy = registry.get(family)
    explicit_run = run_id is not None
    run_id = run_id if explicit_run else latest_run(conn, family)
    info = repository.get_run(conn, run_id) if run_id else None
    if explicit_run and not info: raise ValueError('PM run not found')
    # Compatibility is a data adapter, never a second set of UI components.
    if strategy.legacy_board and not explicit_run:
        legacy = strategy.legacy_board(conn, charts)
        if not info or (legacy.get('computed_at') or '') > (info['finished_at'] or info['created_at']):
            for row in [r for key in ('long','short','flat','pending') for r in legacy.get(key,[])] + [r for s in legacy['watchlist'] for r in s['rows']]:
                row['family'] = family
            return {**legacy, 'family':family, 'strategy_name':strategy.name, 'source':'assigned'}

    momentum = context._momentum_map(conn)
    instruments = context._instrument_map(conn)
    rows = {}
    targets = [] if not run_id else conn.execute('''SELECT t.*, d.definition_json
        FROM pm_targets t JOIN pm_definitions d ON d.pm_key=t.pm_key AND d.version=t.version
        WHERE t.run_id=? AND json_extract(d.definition_json,'$.family')=?
        ORDER BY t.symbol,t.pm_key''', (run_id, family)).fetchall()
    watch_symbols = {s for _, symbols in TREND_WATCHLIST_SECTIONS for s in symbols}
    price_context = {}
    needs_recompute = False

    def empty(symbol):
        return {**context._empty_entry(symbol), 'family':family, 'pm_run_id':run_id,
                'status':'not_computed', 'error':'Not included in this saved run', 'pending_action':None}

    for target in targets:
        symbol = target['symbol']
        definition = json.loads(target['definition_json'])
        needs_recompute |= definition['engine_version'] != strategy.engine_version
        if symbol not in price_context:
            frozen = conn.execute('SELECT bars FROM pm_inputs WHERE run_id=? AND symbol=?', (run_id,symbol)).fetchone()
            bars = json.loads(zlib.decompress(frozen['bars'])) if frozen else []
            valid = all(isinstance(b.get('c'), (int,float)) and b['c'] > 0 for b in bars[-61:])
            price_context[symbol] = {
                'last_close':bars[-1]['c'] if bars else None,
                'last_date':bars[-1]['date'] if bars else None,
                'vol_60d':context._vol_60d(bars, '/' in symbol) if valid else None,
                'chart':{'bars':[{'t':b['date'], **{k:b[k] for k in ('o','h','l','c','v')}} for b in bars[-480:]], 'events':[]}
                        if charts and symbol in watch_symbols and bars else None,
            }
        asset = rows.setdefault(symbol, {**empty(symbol), **price_context[symbol],
                                        'directions':{side:{**empty(symbol),'direction':side} for side in ('long','short')}})
        side = definition['direction']
        entry = {**empty(symbol), **json.loads(target['summary_json'] or '{}'),
                 'direction':side, 'pm_key':target['pm_key'], 'pm_version':target['version'],
                 'status':target['status'], 'error':target['error']}
        asset['directions'][side] = entry
        if asset['chart'] and target['status']=='ok':
            result = repository.get_result(conn, run_id, symbol, target['pm_key'], target['version'])
            if result:
                asset['chart']['events'].extend({'dir':side, **{k:t[k] for k in
                    ('entry_date','entry_price','exit_date','exit_price','exit_reason')}} for t in result.trades[-12:])

    buckets = {'long':[], 'short':[], 'flat':[]}
    pending, unavailable = [], []
    for symbol, asset in rows.items():
        context._with_instrument(context._with_momentum(asset, momentum), instruments)
        states = asset['directions']
        for side, state in states.items():
            state['vol_60d'] = asset['vol_60d']
            context._with_instrument(context._with_momentum(state, momentum), instruments)
            entry = {**asset, **state}
            if state['status']!='ok': unavailable.append(entry)
            elif state['state']==side: buckets[side].append(entry)
            if state.get('pending_action'): pending.append(entry)
        if all(s['status']=='ok' and s['state']=='flat' for s in states.values()):
            buckets['flat'].append({**asset, 'state':'flat','status':'ok','error':None,
                'state_since':max((s['state_since'] or '') for s in states.values()) or None})
        if asset['chart']: asset['chart']['events'].sort(key=lambda e:e['entry_date'])
    for bucket in buckets.values(): bucket.sort(key=lambda r:r['state_since'] or '', reverse=True)
    watchlist = [{'title':title, 'rows':[rows.get(s) or {
        **context._with_instrument(context._with_momentum(empty(s), momentum), instruments),
        'directions':{side:{**empty(s),'direction':side} for side in ('long','short')},
    } for s in symbols]} for title,symbols in TREND_WATCHLIST_SECTIONS]
    presets = {}
    for target in targets:
        d = json.loads(target['definition_json'])
        preset = presets.setdefault((d['key'],d['version']), {'id':d['key']+'@'+d['version'],
            'key':d['key'],'name':d['name'],'is_default':False,'note':None,'assigned_count':0})
        preset['assigned_count'] += 1
    return {'status':'ok' if targets else 'not_computed','family':family,'strategy_name':strategy.name,
            'source':'saved','pm_run_id':run_id,'run_status':info['status'] if info else None,
            'computed_at':info['finished_at'] if info else None,'needs_recompute':needs_recompute,
            'pending':pending,'unavailable':unavailable,'universe':list(rows.values()),'watchlist':watchlist,
            'strategies':list(presets.values()),'counts':{k:len(v) for k,v in buckets.items()}, **buckets}
