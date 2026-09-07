"""Bridge the actual database preparation path to the retained Step 6 results."""
import gzip
import json
import pickle
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
from app.db.connection import get_connection
from app.features.sizing.data import prepare
from app.features.sizing.params import SizingRequest
from app.features.sizing.portfolio import simulate

started = time.monotonic()
with get_connection() as conn:
    data = prepare(conn, SizingRequest(scope='universe'),
        lambda symbol, i, total: print(f'Prepare {i}/{total}', flush=True) if i % 100 == 0 else None)
with (ROOT / 'backend/temp/step6/prepared.pkl').open('rb') as f:
    old = pickle.load(f)['data']
assert data['dates'] == old['dates']
assert set(data['infos']) == set(old['infos'])
vol_error = max(abs(a-b) for s in data['market'] for a,b in
                zip(data['market'][s]['inverse'], old['market'][s]['inverse']))
assert vol_error < 1e-8, vol_error
cases = json.loads((ROOT / 'docs/temp/step6/results.json').read_text(encoding='utf-8'))['cases']
cases = [c for c in cases if c['scope']=='universe' and c['window']=='recent'
         and c['cost']=='normal' and c['book'] in ['long-initial','short-reference','combined-initial']]
checks = []
for c in cases:
    expected = json.loads(gzip.decompress((ROOT / 'docs/temp/step6/cases' / (c['id']+'.json.gz')).read_bytes()))
    actual = simulate(data,c['scope'],c['window'],c['book'],c['method'],c['cost'])
    assert len(actual['trades']) == len(expected['trades'])
    assert len(actual['curve']) == len(expected['curve'])
    error = max(abs(a[1]-b[1]) for a,b in zip(actual['curve'],expected['curve']))
    assert error < .0001, (c['id'],error)
    checks.append({'id':c['id'],'maximum_equity_difference':error,'trades':len(actual['trades'])})
    print(checks[-1],flush=True)
out = {'symbols':len(data['infos']),'inverse_vol_max_error':vol_error,
       'cases':checks,'seconds':time.monotonic()-started}
(ROOT / 'docs/temp/integration/database-verification.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
