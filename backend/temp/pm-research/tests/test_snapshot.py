import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from snapshot import create_snapshot, read_only, validate, verify


def source_db(path):
    with sqlite3.connect(path) as conn:
        conn.executescript('''
        CREATE TABLE assets(symbol TEXT PRIMARY KEY);
        CREATE TABLE crypto_assets(symbol TEXT PRIMARY KEY);
        CREATE TABLE price_bars(symbol TEXT, date TEXT, open REAL, high REAL, low REAL,
          close REAL, adj_open REAL, adj_high REAL, adj_low REAL, adj_close REAL,
          volume REAL, source TEXT, PRIMARY KEY(symbol,date));
        CREATE TABLE crypto_bars(symbol TEXT, date TEXT, open REAL, high REAL, low REAL,
          close REAL, volume REAL, source TEXT, PRIMARY KEY(symbol,date));
        CREATE TABLE credentials(secret TEXT);
        INSERT INTO credentials VALUES ('do not export');
        INSERT INTO assets VALUES ('SPY'),('EMPTY'),('BROKEN');
        INSERT INTO crypto_assets VALUES ('BTC/USD');
        INSERT INTO price_bars VALUES ('SPY','2026-02-02',689.58,696,69.005,695.41,
          685.9,692,68.64,691.7,100,'alpaca');
        INSERT INTO price_bars VALUES ('BROKEN','2026-02-02',100,99,90,101,
          100,99,90,101,100,'alpaca');
        INSERT INTO crypto_bars VALUES ('BTC/USD','2026-02-01',100,101,99,100,1,'coinbase');
        INSERT INTO crypto_bars VALUES ('BTC/USD','2026-02-03',100,101,99,100,1,'coinbase');
        ''')


def test_snapshot_is_consistent_market_only_and_read_only(tmp_path):
    source = tmp_path/'source.sqlite3'
    source_db(source)
    target = tmp_path/'snapshot'
    manifest = create_snapshot(source, target, {'SPY'})
    with sqlite3.connect(source) as conn:
        conn.execute("UPDATE price_bars SET adj_close=800 WHERE symbol='SPY'")
    assert verify(target)['database_sha256'] == manifest['database_sha256']
    with read_only(target/'market.sqlite3') as conn:
        assert conn.execute("SELECT adj_close FROM price_bars WHERE symbol='SPY'").fetchone()[0] == 691.7
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name='credentials'").fetchone()
        with pytest.raises(sqlite3.OperationalError): conn.execute('DELETE FROM price_bars')


def test_validation_preserves_missing_history_and_flags_real_defects(tmp_path):
    source = tmp_path/'source.sqlite3'
    source_db(source)
    target = tmp_path/'snapshot'
    create_snapshot(source,target,{'SPY'})
    summary = validate(target,tmp_path/'report')
    assert summary['stored_members'] == 3
    assert summary['statuses']['no_history'] == 1
    assert summary['invalid_symbols'] == ['BROKEN']
    assert summary['issue_counts']['extreme_range'] == 1
    assert summary['issue_counts']['calendar_gap'] == 1
    assert summary['known_spy_row']['adj_low'] == 68.64
    with sqlite3.connect(target/'market.sqlite3') as conn:
        conn.execute("UPDATE price_bars SET adj_low=680 WHERE symbol='SPY'")
    with pytest.raises(ValueError,match='hash mismatch'): verify(target)
