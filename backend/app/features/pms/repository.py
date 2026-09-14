"""Immutable PM run results and versioned assignments; caller owns connection."""
from __future__ import annotations

import json
import sqlite3
import zlib
from contextlib import contextmanager
from datetime import datetime, timezone

from .contracts import PMDefinition, PMResult, content_hash


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def atomic(conn):
    conn.execute('SAVEPOINT pm_write')
    try:
        yield
        conn.execute('RELEASE SAVEPOINT pm_write')
    except Exception:
        conn.execute('ROLLBACK TO SAVEPOINT pm_write')
        conn.execute('RELEASE SAVEPOINT pm_write')
        raise


def register(conn, definition: PMDefinition):
    definition = PMDefinition.model_validate(definition.model_dump())
    conn.execute('INSERT INTO pm_definitions VALUES (?,?,?) ON CONFLICT DO NOTHING',
                 (definition.key,definition.version,definition.model_dump_json()))


def assign(conn, symbol, definition: PMDefinition, enabled=True):
    with atomic(conn):
        register(conn,definition)
        conn.execute('''INSERT INTO pm_assignments VALUES (?,?,?,?)
          ON CONFLICT(symbol,pm_key) DO UPDATE SET version=excluded.version,enabled=excluded.enabled''',
                     (symbol,definition.key,definition.version,int(enabled)))


def assignments(conn, symbol):
    return [(PMDefinition.model_validate_json(r['definition_json']),bool(r['enabled'])) for r in conn.execute('''
      SELECT d.definition_json,a.enabled FROM pm_assignments a
      JOIN pm_definitions d ON d.pm_key=a.pm_key AND d.version=a.version
      WHERE a.symbol=? ORDER BY a.pm_key''',(symbol,))]


def create_run(conn, plan: list[tuple[str, PMDefinition, str]], fetch_run_id=None):
    targets = {}
    for symbol,definition,input_hash in plan:
        key = (symbol,definition.key,definition.version)
        if key in targets and targets[key][2] != input_hash:
            raise ValueError('Duplicate assignment has inconsistent frozen input')
        targets[key] = (symbol,definition,input_hash)
    manifest=[{'symbol':s,'pm_key':d.key,'version':d.version,'input_hash':h}
              for s,d,h in (targets[k] for k in sorted(targets))]
    with atomic(conn):
        cursor=conn.execute('''INSERT INTO pm_runs(fetch_run_id,input_hash,manifest_json,status,created_at)
          VALUES (?,?,?,'running',?)''',(fetch_run_id,content_hash(manifest),json.dumps(manifest),now()))
        run_id=cursor.lastrowid
        for symbol,definition,input_hash in targets.values():
            register(conn,definition)
            conn.execute("INSERT INTO pm_targets(run_id,symbol,pm_key,version,input_hash,status,error) VALUES (?,?,?,?,?,'queued',NULL)",
                         (run_id,symbol,definition.key,definition.version,input_hash))
    return run_id


def save_result(conn, run_id: int, result: PMResult):
    result=PMResult.model_validate(result.model_dump())
    key=(run_id,result.symbol,result.pm.key,result.pm.version)
    with atomic(conn):
        target=conn.execute('''SELECT t.input_hash,t.status,r.status run_status FROM pm_targets t
          JOIN pm_runs r ON r.id=t.run_id
          WHERE t.run_id=? AND t.symbol=? AND t.pm_key=? AND t.version=?''',key).fetchone()
        if not target or target['run_status']!='running' or target['status']!='queued':
            raise ValueError('PM target is missing or already final; create a new run for retry')
        if target['input_hash']!=result.input_hash:
            raise ValueError('PM result does not match frozen target input')
        conn.execute('INSERT INTO pm_results VALUES (?,?,?,?,?)',
                     (*key,zlib.compress(result.model_dump_json().encode(),level=6)))
        summary={**result.position.model_dump(),'pending_action':result.pending_action.model_dump() if result.pending_action else None,
                 'last_date':result.as_of}
        conn.execute('UPDATE pm_targets SET status=?,error=?,summary_json=? WHERE run_id=? AND symbol=? AND pm_key=? AND version=?',
                     (result.status,result.status_reason,json.dumps(summary),*key))


def fail_target(conn, run_id, symbol, key, version, error):
    with atomic(conn):
        parent=conn.execute('SELECT status FROM pm_runs WHERE id=?',(run_id,)).fetchone()
        if not parent or parent['status']!='running': raise ValueError('Run is not active')
        cursor=conn.execute("""UPDATE pm_targets SET status='failed',error=?
          WHERE run_id=? AND symbol=? AND pm_key=? AND version=? AND status='queued'""",
          (str(error)[:500],run_id,symbol,key,version))
        if cursor.rowcount!=1: raise ValueError('Target is missing or already final')


def finish_run(conn, run_id, cancelled=False):
    with atomic(conn):
        parent=conn.execute('SELECT status FROM pm_runs WHERE id=?',(run_id,)).fetchone()
        if not parent or parent['status']!='running': raise ValueError('Run is not active')
        statuses=[r[0] for r in conn.execute('SELECT status FROM pm_targets WHERE run_id=?',(run_id,))]
        if cancelled:
            conn.execute("UPDATE pm_targets SET status='cancelled' WHERE run_id=? AND status='queued'",(run_id,))
            status='cancelled'
        else:
            if 'queued' in statuses: raise ValueError('Cannot finish a run with unresolved targets')
            errors=any(s in ('invalid_data','failed','cancelled') for s in statuses)
            status='partial' if errors and 'ok' in statuses else 'failed' if errors or not statuses else 'succeeded'
        conn.execute('UPDATE pm_runs SET status=?,finished_at=? WHERE id=?',(status,now(),run_id))
    return status


def get_result(conn, run_id, symbol, key, version):
    row=conn.execute('SELECT payload FROM pm_results WHERE run_id=? AND symbol=? AND pm_key=? AND version=?',
                     (run_id,symbol,key,version)).fetchone()
    return PMResult.model_validate_json(zlib.decompress(row['payload'])) if row else None


def get_run(conn, run_id):
    row=conn.execute('SELECT * FROM pm_runs WHERE id=?',(run_id,)).fetchone()
    if not row: return None
    result=dict(row)
    result['manifest']=json.loads(result.pop('manifest_json'))
    return result
