"""Market-only SQLite snapshot and transparent research coverage validation.

Run from backend: .venv/Scripts/python.exe temp/pm-research/snapshot.py create
or ... snapshot.py validate <snapshot-directory>. No source DB writes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
import subprocess
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
BACKEND = BASE.parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

TABLES = ('assets', 'crypto_assets', 'price_bars', 'crypto_bars',
          'symbol_memberships', 'membership_groups', 'signal_strategies')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_only(path):
    conn = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    return conn


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def create_snapshot(source, target, priority):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=False)
    output = target / 'market.sqlite3'
    manifest = {'version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
                'source_path': str(Path(source).resolve()), 'tables': {},
                'priority': sorted(priority), 'source_access': 'SQLite read-only transaction',
                'calendar_policy': 'asset observed sessions; peer-equity dates and continuous crypto dates used only to flag possible gaps'}
    try:
        manifest['git_revision'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        manifest['git_revision'] = None
    with read_only(source) as src, sqlite3.connect(output) as dst:
        src.execute('BEGIN')
        for table in TABLES:
            schema = src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if not schema:
                continue
            dst.execute(schema[0])
            columns = src.execute(f'PRAGMA table_info({table})').fetchall()
            pk = [r['name'] for r in sorted(columns, key=lambda r: r['pk']) if r['pk']]
            order = ','.join('"' + n + '"' for n in pk) or 'rowid'
            cursor = src.execute(f'SELECT * FROM {table} ORDER BY {order}')
            placeholders = ','.join('?' for _ in columns)
            count = 0
            while batch := cursor.fetchmany(5000):
                dst.executemany(f'INSERT INTO {table} VALUES ({placeholders})', batch)
                count += len(batch)
            manifest['tables'][table] = {'rows': count}
            if table in ('price_bars', 'crypto_bars'):
                first, last, symbols = src.execute(f'SELECT MIN(date),MAX(date),COUNT(DISTINCT symbol) FROM {table}').fetchone()
                sources = [dict(r) for r in src.execute(f'SELECT source,COUNT(*) bars FROM {table} GROUP BY source')]
                manifest['tables'][table].update(first=first, last=last, symbols=symbols, sources=sources)
            print(f'Exported {table}: {count:,}', flush=True)
        dst.commit()
        if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Snapshot integrity check failed')
        src.rollback()
    manifest['database_sha256'] = sha256(output)
    conventions = BASE / 'conventions.json'
    if conventions.exists():
        (target / 'conventions.json').write_bytes(conventions.read_bytes())
        manifest['conventions_sha256'] = sha256(target / 'conventions.json')
    manifest['snapshot_code_sha256'] = sha256(__file__)
    # Written last: an interrupted export without a manifest is incomplete.
    dump(target / 'manifest.json', manifest)
    return manifest


def verify(target):
    target = Path(target)
    manifest = json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
    if sha256(target / 'market.sqlite3') != manifest['database_sha256']:
        raise ValueError('Snapshot hash mismatch: do not use mutated research input')
    if manifest.get('conventions_sha256') and sha256(target / 'conventions.json') != manifest['conventions_sha256']:
        raise ValueError('Frozen conventions hash mismatch')
    return manifest


def validate(target, report):
    target, report = Path(target), Path(report)
    manifest = verify(target)
    report.mkdir(parents=True, exist_ok=True)
    priority = set(manifest['priority'])
    now = date.fromisoformat(manifest['created_at'][:10])
    counts, status_counts, members = Counter(), Counter(), []
    flagged_symbols, invalid_symbols = set(), set()
    with read_only(target / 'market.sqlite3') as conn, \
            (report / 'coverage.csv').open('w', encoding='utf-8', newline='') as cf, \
            (report / 'data-issues.csv').open('w', encoding='utf-8', newline='') as ff:
        coverage = csv.DictWriter(cf, fieldnames=['symbol','kind','priority','rows','valid_rows','first','last',
            'first_decision_full','first_fill_full','first_decision_recent','first_fill_recent','status','issues'])
        flags = csv.DictWriter(ff, fieldnames=['symbol','date','severity','issue','detail'])
        coverage.writeheader(); flags.writeheader()
        equity_days = {r[0] for r in conn.execute('SELECT DISTINCT date FROM price_bars')}
        for kind, table, catalog in [('equity','price_bars','assets'), ('crypto','crypto_bars','crypto_assets')]:
            symbols = [r[0] for r in conn.execute(f'SELECT symbol FROM {catalog} UNION SELECT symbol FROM {table} ORDER BY symbol')]
            cols = 'adj_open,adj_high,adj_low,adj_close' if kind == 'equity' else 'open,high,low,close'
            for symbol in symbols:
                bars = conn.execute(f'SELECT date,{cols},volume,source FROM {table} WHERE symbol=? ORDER BY date', (symbol,)).fetchall()
                dates, valid, issues = [], [], Counter()

                def flag(day, issue, detail, hard=False):
                    flags.writerow({'symbol': symbol, 'date': day, 'severity': 'invalid' if hard else 'review',
                                    'issue': issue, 'detail': detail})
                    counts[issue] += 1; issues[issue] += 1
                    flagged_symbols.add(symbol)
                    if hard: invalid_symbols.add(symbol)

                previous = None
                for row in bars:
                    day, o, h, low, close, volume, source = row
                    try:
                        parsed = date.fromisoformat(day)
                        if parsed.isoformat() != day: raise ValueError()
                    except (TypeError, ValueError):
                        flag(str(day), 'invalid_date', 'not canonical ISO date', True); continue
                    if parsed >= now:
                        flag(day, 'incomplete_or_future_bar', 'snapshot date or later; completed bar not established', True)
                    if day in dates[-1:]: flag(day, 'duplicate_date', 'duplicate symbol/date', True)
                    dates.append(day)
                    if any(v is None or not isinstance(v, (int,float)) or not math.isfinite(v) or v <= 0 for v in (o,h,low,close)):
                        flag(day, 'invalid_ohlc', repr(tuple(row[1:5])), True); continue
                    if low > min(o,close) or h < max(o,close) or low > h:
                        flag(day, 'ohlc_order', repr(tuple(row[1:5])), True); continue
                    if volume is None or not math.isfinite(volume) or volume < 0:
                        flag(day, 'invalid_volume', repr(volume), True)
                    if (h-low)/close > .30:
                        flag(day, 'extreme_range', f'OHLC={o},{h},{low},{close}; range/close={(h-low)/close:.6f}')
                    if previous and abs(close/previous-1) > .50:
                        flag(day, 'extreme_close_return', f'previous={previous}; close={close}')
                    if kind == 'crypto' and source != 'coinbase':
                        flag(day, 'crypto_source', str(source))
                    previous = close
                    valid.append(day)
                if dates:
                    members.append(symbol)
                    expected = equity_days if kind == 'equity' else {
                        (date.fromisoformat(dates[0])+timedelta(days=i)).isoformat()
                        for i in range((date.fromisoformat(dates[-1])-date.fromisoformat(dates[0])).days+1)}
                    observed = set(dates)
                    missing = sorted(d for d in expected if dates[0] <= d <= dates[-1] and d not in observed)
                    if missing:
                        flag(missing[0], 'calendar_gap', f'{len(missing)} missing observed-peer/crypto dates; sample={missing[:12]}')
                status = ('no_history' if not bars else 'invalid' if symbol in invalid_symbols else
                          'insufficient_history' if len(valid)<252 else 'provisional' if issues else 'comparable')
                status_counts[status] += 1
                start_full = 250
                start_recent = max(250, next((i for i,d in enumerate(valid) if d >= '2020-01-01'), len(valid)))
                row = {'symbol':symbol,'kind':kind,'priority':int(symbol in priority),'rows':len(bars),'valid_rows':len(valid),
                       'first':dates[0] if dates else '', 'last':dates[-1] if dates else '', 'status':status,
                       'issues':';'.join(f'{k}:{v}' for k,v in sorted(issues.items()))}
                for window,i in [('full',start_full),('recent',start_recent)]:
                    row['first_decision_'+window] = valid[i] if i < len(valid) else ''
                    row['first_fill_'+window] = valid[i+1] if i+1 < len(valid) else ''
                coverage.writerow(row)
        spy = conn.execute("SELECT date,open,low,close,adj_open,adj_low,adj_close,source FROM price_bars WHERE symbol='SPY' AND date='2026-02-02'").fetchone()
    summary = {'input_hash':manifest['database_sha256'], 'validation_code_sha256':sha256(__file__),
               'statuses':dict(status_counts), 'issue_counts':dict(counts),
               'stored_members':len(members),'priority_members':len(set(members)&priority),
               'flagged_symbols':sorted(flagged_symbols),'invalid_symbols':sorted(invalid_symbols),
               'known_spy_row':dict(spy) if spy else None,
               'disposition':'No prices corrected. Invalid symbols retained in coverage but not executable. Review flags make affected portfolios provisional.',
               'gap_note':'Peer session dates are screening, not an authoritative historical exchange calendar; investigate before classifying a gap as a defect.'}
    dump(report / 'data-summary.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['create','validate'])
    parser.add_argument('target', nargs='?')
    args = parser.parse_args()
    if args.action == 'create':
        from app.core.config import get_settings
        from app.features.sizing.params import PRIORITY
        target = Path(args.target) if args.target else BASE / 'inputs' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        manifest = create_snapshot(get_settings().resolved_database_path(), target, PRIORITY)
        dump(BASE / 'current-snapshot.json', {'path':str(target.resolve()),'sha256':manifest['database_sha256']})
        print(json.dumps({'snapshot':str(target), 'hash':manifest['database_sha256']}))
    else:
        target = Path(args.target) if args.target else Path(json.loads((BASE/'current-snapshot.json').read_text())['path'])
        summary = validate(target, ROOT/'docs/temp/results'/target.name)
        print(json.dumps({k:v for k,v in summary.items() if k not in ('flagged_symbols','invalid_symbols')}, indent=2))
