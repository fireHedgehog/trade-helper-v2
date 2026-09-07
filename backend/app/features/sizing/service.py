"""Background portfolio calculation and latest successful result."""
import gzip
import json
from datetime import datetime, timezone
from app.features.data_management import runs
from app.features.signals.params import ENGINE_VERSION
from app.features.sizing.data import prepare
from app.features.sizing.params import SizingRequest, COSTS, GROUP_CAPS, SYMBOL_CAP
from app.features.sizing.portfolio import simulate, CURVE_FIELDS


def run(conn,run_id,body):
    request=SizingRequest.model_validate_json(body)
    last=None
    def progress(symbol,index,total):
        nonlocal last
        runs.raise_if_cancelled(run_id)
        if index==0:runs.set_planned(conn,run_id,total+2)
        if last is not None:runs.finish_target(conn,run_id,last,status='ok')
        runs.start_target(conn,run_id,symbol);last=symbol
    data=prepare(conn,request,progress)
    if last is not None:runs.finish_target(conn,run_id,last,status='ok')
    runs.start_target(conn,run_id,'Portfolio accounting')
    result=simulate(data,request.scope,request.window,request.book,request.method,request.cost,request.capital,
                    progress=lambda *_:runs.raise_if_cancelled(run_id))
    runs.finish_target(conn,run_id,'Portfolio accounting',status='ok',rows=len(result['trades']))
    runs.start_target(conn,run_id,'Buy and hold reference')
    benchmark=simulate(data,request.scope,request.window,'buy-hold','equal',request.cost,request.capital,
                       progress=lambda *_:runs.raise_if_cancelled(run_id))
    result['benchmark']={'stats':benchmark['stats'],'curve':[[p[0],p[1]] for p in benchmark['curve']]}
    result.update(status='ok',params=request.model_dump(),curve_fields=CURVE_FIELDS,
                  computed_at=datetime.now(timezone.utc).isoformat(),engine_version=ENGINE_VERSION,
                  run_id=run_id,assumptions={'costs':COSTS[request.cost],'symbol_cap':SYMBOL_CAP,
                    'group_caps':GROUP_CAPS,'long_short_split':'50/50 initial capital; no transfers',
                    'borrow':'Synthetic short benchmark; assumed annual borrow, availability not verified',
                    'capital':'Fixed units until exit; flat allocations and cap reductions remain cash; short proceeds reserved',
                    'weights':'All eligible assets, including flat assets; prior-bar 60-return volatility, 1% floor',
                    'universe':'Current stored universe, not historical index membership'},
                  instruments=list(data['infos'].values()))
    runs.raise_if_cancelled(run_id)
    encoded=gzip.compress(json.dumps(result,allow_nan=False,separators=(',',':')).encode(),compresslevel=4)
    conn.execute('INSERT INTO portfolio_result VALUES (1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET '
                 'run_id=excluded.run_id,engine_version=excluded.engine_version,computed_at=excluded.computed_at,'
                 'params_json=excluded.params_json,result_gzip=excluded.result_gzip',
                 (run_id,ENGINE_VERSION,result['computed_at'],request.model_dump_json(),encoded))
    runs.finish_target(conn,run_id,'Buy and hold reference',status='ok')


def latest(conn):
    row=conn.execute('SELECT * FROM portfolio_result WHERE id=1').fetchone()
    if not row:return {'status':'not_computed'}
    result=json.loads(gzip.decompress(row['result_gzip']))
    result['needs_recompute']=row['engine_version']!=ENGINE_VERSION
    return result
