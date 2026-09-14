"""Run only the six predefined controls after the two primary runs finish."""
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from snapshot import BASE, ROOT, dump, sha256, verify
from comparisons import CANDIDATES


def main():
    snapshot=Path(json.loads((BASE/'current-snapshot.json').read_text())['path'])
    manifest=verify(snapshot)
    root=ROOT/'docs/temp/results'/snapshot.name
    output=root/'controls-v1'; output.mkdir(exist_ok=False)
    selected=['sma200-stop','pullback-no-stop','sma150','sma250','pullback-rsi10','pullback-rsi30']
    state={'status':'waiting_for_primary_runs','snapshot_hash':manifest['database_sha256'],
           'started_at':datetime.now(timezone.utc).isoformat(),'completed':[],
           'parameters':{name:CANDIDATES[name][1] for name in selected},
           'runner_hash':sha256(BASE/'comparisons.py'),'strategy_hash':sha256(BASE/'strategies.py'),
           'max_parallel_runs':2}
    dump(output/'run.json',state)
    try:
        deadline=time.monotonic()+6*3600
        while True:
            statuses=[json.loads((root/name/'run.json').read_text())['status']
                      for name in ['sma-comparison-v2','pullback-v1']]
            if any(s=='failed' for s in statuses): raise RuntimeError('Primary run failed; controls not started')
            if all(s=='succeeded' for s in statuses): break
            if time.monotonic()>deadline: raise RuntimeError('Primary runs did not complete within six hours')
            time.sleep(5)
        state['status']='running';dump(output/'run.json',state)

        def execute(candidate):
            if sha256(BASE/'comparisons.py')!=state['runner_hash'] or sha256(BASE/'strategies.py')!=state['strategy_hash']:
                raise RuntimeError('Frozen control source changed before launch')
            name=f'control-{candidate}-v1'
            with (ROOT/'output/logs'/f'{name}.log').open('w',encoding='utf-8') as log:
                completed=subprocess.run([sys.executable,'-u',str(BASE/'comparisons.py'),'--candidate',candidate,'--name',name],
                                         cwd=ROOT/'backend',stdout=log,stderr=subprocess.STDOUT)
            run_file=root/name/'run.json'
            result=json.loads(run_file.read_text()) if run_file.exists() else {}
            if completed.returncode or result.get('status')!='succeeded': raise RuntimeError(f'{candidate} failed; inspect its retained log/run')
            if result['snapshot_hash']!=state['snapshot_hash']: raise RuntimeError('Control input mismatch')
            return name

        with ThreadPoolExecutor(max_workers=2) as pool:
            tasks=[pool.submit(execute,candidate) for candidate in selected]
            for task in as_completed(tasks):
                name=task.result(); state['completed'].append(name);dump(output/'run.json',state)
                print('COMPLETE',name,flush=True)
        state.update(status='succeeded',finished_at=datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        state.update(status='failed',error=f'{type(exc).__name__}: {exc}')
        raise
    finally: dump(output/'run.json',state)


if __name__=='__main__': main()
