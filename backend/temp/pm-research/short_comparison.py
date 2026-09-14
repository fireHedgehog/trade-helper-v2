"""Matched synthetic-short candidate / fixed-short / cash research accounts."""
import csv
import gzip
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from snapshot import BASE, ROOT, dump, sha256, verify
from references import prepare, KEY, portfolio, engine
from comparisons import event_index, standalone_data, diagnostics, flat_stats, write_csv
from short_candidate import failed_rally
from app.features.signals.params import SHORT_PARAMS

SHORT_KEY='baseline-short'


def short_data(data, window, cash=False):
    tape=data['tapes'][window].pop(KEY)
    data['tapes'][window][SHORT_KEY]=[[] for _ in data['dates']] if cash else tape
    for symbol in data['signals'][window]:
        count=data['signals'][window][symbol].pop(KEY)
        data['signals'][window][symbol][SHORT_KEY]=0 if cash else count
    return data


def run():
    snapshot=Path(json.loads((BASE/'current-snapshot.json').read_text())['path'])
    manifest=verify(snapshot); root=ROOT/'docs/temp/results'/snapshot.name
    quality=json.loads((root/'data-summary.json').read_text())
    assert quality['input_hash']==manifest['database_sha256']
    output=root/'short-comparison-v1';output.mkdir(exist_ok=False)
    sources=output/'sources';sources.mkdir()
    files=[Path(__file__),BASE/'short_candidate.py',BASE/'short-specification.md',BASE/'strategies.py',
           BASE/'references.py',BASE/'comparisons.py',BASE/'snapshot.py',
           ROOT/'backend/app/features/signals/engine.py',ROOT/'backend/app/features/signals/indicators.py',
           ROOT/'backend/app/features/signals/params.py',ROOT/'backend/app/features/sizing/portfolio.py',ROOT/'backend/app/features/sizing/params.py']
    hashes={}
    for p in files:
        relative=str(p.relative_to(ROOT)).replace('\\','/')
        hashes[relative]=sha256(p);shutil.copyfile(p,sources/relative.replace('/','__'))
    state={'status':'running','started_at':datetime.now(timezone.utc).isoformat(),
           'snapshot_hash':manifest['database_sha256'],'conventions_hash':manifest['conventions_sha256'],
           'source_hashes':hashes,'benchmark_parameters':SHORT_PARAMS.model_dump(),'completed':[],
           'provisional':True,'instrument_feasibility':'unknown; synthetic borrow/collateral only'}
    dump(output/'run.json',state)
    summary=[];standalone=[]
    try:
        for window in ['full','recent']:
            for candidate,runner in [('failed-rally',failed_rally),
                                     ('fixed-short',lambda bars,*,start: engine.run(bars,SHORT_PARAMS,start=start))]:
                data=short_data(prepare(snapshot,window,quality,runner,candidate),window)
                for scope in ['priority','universe']:
                    for cost in ['normal','double']:
                        result=diagnostics(portfolio.simulate(data,scope,window,'short-reference','equal',cost))
                        result.update(candidate=candidate,book=candidate,input_hash=manifest['database_sha256'],provisional=True)
                        artifact=f'{window}-{scope}-{cost}-{candidate}.json.gz'
                        with gzip.open(output/artifact,'wt',encoding='utf-8',compresslevel=1) as stream:
                            json.dump(result,stream,allow_nan=False)
                        summary.append({'window':window,'scope':scope,'cost':cost,'candidate':candidate,**flat_stats(result)})
                        state['completed'].append(artifact);dump(output/'run.json',state)
                        cagr=result['stats']['cagr']
                        print(artifact,'CAGR='+('undefined' if cagr is None else f'{cagr:.4%}'),
                              f"DD={result['stats']['drawdown']:.4%}",flush=True)
                indexed=event_index(data,window)
                artifact=f'{window}-{candidate}-standalone.jsonl.gz'
                with gzip.open(output/artifact,'wt',encoding='utf-8',compresslevel=1) as stream:
                    for number,symbol in enumerate(sorted(data['infos'])):
                        info=data['infos'][symbol];single=standalone_data(data,window,symbol,indexed)
                        for cost in ['normal','double']:
                            row={'symbol':symbol,'window':window,'candidate':candidate,'cost':cost,'priority':info['priority'],
                                 'decision_date':info.get('decision_date'),'earliest_execution':info.get('execution_date'),
                                 'end_date':info['last'],'status':'invalid_data' if symbol in quality['invalid_symbols'] else
                                 'insufficient_history' if single is None else 'ok','provisional':symbol in quality['flagged_symbols']}
                            if single:
                                result=diagnostics(portfolio.simulate(single,'single',window,'short-reference','equal',cost))
                                result.update(book=candidate,input_hash=manifest['database_sha256'],**row)
                                row.update(flat_stats(result));stream.write(json.dumps(result,allow_nan=False)+'\n')
                            else: stream.write(json.dumps(row)+'\n')
                            standalone.append(row)
                            if candidate=='fixed-short':
                                # Cash is analytic: identical comparison dates, no positions, interest or costs.
                                cash={**row,'candidate':'cash'}
                                if single:
                                    cash.update({k:0 for k in flat_stats(result) if k!='annual'})
                                    cash.update(ending=100000.,cash_only_fraction=1.,average_cash_fraction=1.,worst_closed_trade_pnl=None)
                                standalone.append(cash)
                        if number%100==0: print(window,candidate,'standalone',number+1,'/ 678',flush=True)
                state['completed'].append(artifact);dump(output/'run.json',state)
                write_csv(output/'standalone.csv',standalone)
                if candidate=='fixed-short':
                    data['tapes'][window][SHORT_KEY]=[[] for _ in data['dates']]
                    for symbol in data['signals'][window]: data['signals'][window][symbol][SHORT_KEY]=0
                    for scope in ['priority','universe']:
                        for cost in ['normal','double']:
                            result=diagnostics(portfolio.simulate(data,scope,window,'short-reference','equal',cost))
                            assert result['stats']['net']==0 and result['trades']==[]
                            result.update(candidate='cash',book='cash',input_hash=manifest['database_sha256'],provisional=True)
                            artifact=f'{window}-{scope}-{cost}-cash.json.gz'
                            with gzip.open(output/artifact,'wt',encoding='utf-8',compresslevel=1) as stream:
                                json.dump(result,stream,allow_nan=False)
                            summary.append({'window':window,'scope':scope,'cost':cost,'candidate':'cash',**flat_stats(result)})
                            state['completed'].append(artifact)
                del data,indexed
        write_csv(output/'funded-comparison.csv',summary)
        state.update(status='succeeded',finished_at=datetime.now(timezone.utc).isoformat(),standalone_rows=len(standalone))
    except Exception as exc:
        state.update(status='failed',error=f'{type(exc).__name__}: {exc}');raise
    finally: dump(output/'run.json',state)
    print('COMPLETE',output,flush=True)


if __name__=='__main__': run()
