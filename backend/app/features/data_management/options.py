"""Daily option snapshots — a small IV-surface grid, not the whole chain.

For each underlying in `options_research_set` (a trimmed core: SPY/QQQ + the
MAG7 names + SMH), one Alpaca snapshot request pulls the near-the-money band
(quote + greeks + implied vol, `feed=indicative`, 15-min delayed). From it we
keep a fixed grid — 6 tenors x 7 moneyness points — so a day's pull is a few
hundred rows, not the several thousand a full chain would be.

No backfill is possible: the snapshot endpoint only returns *today's* chain,
so history accumulates forward one `snapshot_date` per run. Re-running the
same day is idempotent (PK = underlying + snapshot_date + contract).
"""

from __future__ import annotations

import sqlite3
import time
from datetime import date, datetime, timedelta, timezone

from app.features.data_management import runs
from app.providers.clients.alpaca_client import AlpacaClient

# Target days-to-expiry for the tenor ladder; each maps to the nearest listed
# expiration.
TENOR_DAYS = (7, 30, 60, 90, 120, 180)
# Moneyness points (strike / spot - 1). Below spot -> puts, above -> calls,
# 0.0 -> both (ATM straddle).
PUT_MONEYNESS = (-0.15, -0.10, -0.05)
CALL_MONEYNESS = (0.05, 0.10, 0.15)
# Snapshot request band — a little wider than the grid so the nearest-strike
# pick at +/-15% has candidates on both sides.
REQUEST_BAND = 0.20
MAX_DTE = 190


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _targets(conn: sqlite3.Connection) -> list[str]:
    return [r["underlying"] for r in conn.execute(
        "SELECT underlying FROM options_research_set ORDER BY underlying"
    )]


def _spot(conn: sqlite3.Connection, symbol: str) -> float | None:
    row = conn.execute(
        "SELECT close FROM price_bars WHERE symbol = ? ORDER BY date DESC LIMIT 1", (symbol,)
    ).fetchone()
    return float(row["close"]) if row and row["close"] is not None else None


def _parse_occ(occ: str) -> tuple[str, str, float] | None:
    """`...{YYMMDD}{C|P}{strike*1000:08d}` -> (expiration, type, strike)."""
    if len(occ) < 15 or not occ[-8:].isdigit() or not occ[-15:-9].isdigit():
        return None
    strike = int(occ[-8:]) / 1000.0
    cp = occ[-9]
    ymd = occ[-15:-9]
    exp = f"20{ymd[0:2]}-{ymd[2:4]}-{ymd[4:6]}"
    try:
        date.fromisoformat(exp)
    except ValueError:
        return None
    typ = {"C": "call", "P": "put"}.get(cp)
    return (exp, typ, strike) if typ else None


def _pick_expirations(expirations: set[str], today: date) -> list[str]:
    picks: list[str] = []
    if not expirations:
        return picks
    for dte in TENOR_DAYS:
        target = today + timedelta(days=dte)
        best = min(expirations, key=lambda e: abs((date.fromisoformat(e) - target).days))
        if best not in picks:
            picks.append(best)
    return picks


def _nearest(strikes: list[float], target: float) -> float | None:
    return min(strikes, key=lambda k: abs(k - target)) if strikes else None


def _pick_grid(
    contracts: dict[str, tuple[str, str, float]], expirations: list[str], spot: float
) -> set[str]:
    """Return the OCC symbols on the 7-point grid for each chosen expiration."""
    by_exp: dict[str, dict[str, dict[float, str]]] = {}
    for occ, (exp, typ, strike) in contracts.items():
        by_exp.setdefault(exp, {"call": {}, "put": {}})[typ][strike] = occ

    keep: set[str] = set()
    for exp in expirations:
        legs = by_exp.get(exp)
        if not legs:
            continue
        puts = sorted(legs["put"])
        calls = sorted(legs["call"])
        for m in PUT_MONEYNESS:
            k = _nearest(puts, spot * (1 + m))
            if k is not None:
                keep.add(legs["put"][k])
        atm_p = _nearest(puts, spot)
        atm_c = _nearest(calls, spot)
        if atm_p is not None:
            keep.add(legs["put"][atm_p])
        if atm_c is not None:
            keep.add(legs["call"][atm_c])
        for m in CALL_MONEYNESS:
            k = _nearest(calls, spot * (1 + m))
            if k is not None:
                keep.add(legs["call"][k])
    return keep


_SNAP_UPSERT = """
INSERT INTO option_chain_snapshots (
    underlying, snapshot_date, contract_symbol, expiration, strike, type,
    bid, ask, last, mid, volume, open_interest, iv, delta, gamma, theta, vega, rho,
    underlying_price, feed, fetched_at
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'indicative', strftime('%Y-%m-%dT%H:%M:%fZ','now'))
ON CONFLICT(underlying, snapshot_date, contract_symbol) DO UPDATE SET
    bid=excluded.bid, ask=excluded.ask, last=excluded.last, mid=excluded.mid,
    volume=excluded.volume, iv=excluded.iv, delta=excluded.delta, gamma=excluded.gamma,
    theta=excluded.theta, vega=excluded.vega, rho=excluded.rho,
    underlying_price=excluded.underlying_price, fetched_at=excluded.fetched_at
"""

_CONTRACT_UPSERT = """
INSERT INTO option_contracts (contract_symbol, underlying, expiration, strike, type,
                              style, status, last_synced_at)
VALUES (?,?,?,?,?, 'american', 'active', strftime('%Y-%m-%dT%H:%M:%fZ','now'))
ON CONFLICT(contract_symbol) DO UPDATE SET last_synced_at = excluded.last_synced_at
"""


def _write(
    conn: sqlite3.Connection, underlying: str, snap_date: str, spot: float,
    picked: set[str], contracts: dict[str, tuple[str, str, float]], snapshots: dict[str, dict],
) -> int:
    conn.execute("BEGIN")
    n = 0
    for occ in sorted(picked):
        exp, typ, strike = contracts[occ]
        s = snapshots.get(occ) or {}
        q = s.get("latestQuote") or {}
        tr = s.get("latestTrade") or {}
        db = s.get("dailyBar") or {}
        g = s.get("greeks") or {}
        bid, ask = q.get("bp"), q.get("ap")
        mid = (bid + ask) / 2 if bid is not None and ask is not None else None
        iv = s.get("impliedVolatility")
        if bid is None and ask is None and iv is None and not g:
            continue  # nothing quoted or modelled — skip the empty row
        conn.execute(_CONTRACT_UPSERT, (occ, underlying, exp, strike, typ))
        conn.execute(_SNAP_UPSERT, (
            underlying, snap_date, occ, exp, strike, typ,
            bid, ask, tr.get("p"), mid, db.get("v"), None, iv,
            g.get("delta"), g.get("gamma"), g.get("theta"), g.get("vega"), g.get("rho"),
            spot,
        ))
        n += 1
    conn.execute(
        """
        INSERT INTO option_snapshot_stats (underlying, contract_count, last_snapshot,
                                           snapshot_rows, last_fetched)
        VALUES (?, ?, ?,
                (SELECT COUNT(*) FROM option_chain_snapshots WHERE underlying = ?),
                strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        ON CONFLICT(underlying) DO UPDATE SET
            contract_count=excluded.contract_count, last_snapshot=excluded.last_snapshot,
            snapshot_rows=excluded.snapshot_rows, last_fetched=excluded.last_fetched
        """,
        (underlying, n, snap_date, underlying),
    )
    conn.execute("COMMIT")
    return n


async def run_option_snapshots(conn: sqlite3.Connection, run_id: int, mode: str) -> None:
    targets = _targets(conn)
    runs.set_planned(conn, run_id, len(targets))
    today = _today()
    snap_date = today.isoformat()
    exp_hi = (today + timedelta(days=MAX_DTE)).isoformat()

    async with AlpacaClient() as client:
        for underlying in targets:
            runs.raise_if_cancelled(run_id)
            runs.start_target(conn, run_id, underlying)
            t0 = time.monotonic()
            spot = _spot(conn, underlying)
            if spot is None:
                # No underlying bar yet — nothing to anchor the grid to. Skip
                # (not an error) so one un-fetched name doesn't fail the run.
                runs.finish_target(conn, run_id, underlying, status="skipped",
                                   duration_ms=int((time.monotonic() - t0) * 1000))
                continue
            try:
                raw = await client.get_option_snapshots(underlying, {
                    "strike_price_gte": round(spot * (1 - REQUEST_BAND), 2),
                    "strike_price_lte": round(spot * (1 + REQUEST_BAND), 2),
                    "expiration_date_gte": snap_date,
                    "expiration_date_lte": exp_hi,
                })
                contracts: dict[str, tuple[str, str, float]] = {}
                for occ in raw:
                    parsed = _parse_occ(occ)
                    if parsed:
                        contracts[occ] = parsed
                expirations = _pick_expirations({c[0] for c in contracts.values()}, today)
                picked = _pick_grid(contracts, expirations, spot)
                rows = _write(conn, underlying, snap_date, spot, picked, contracts, raw)
                runs.finish_target(
                    conn, run_id, underlying, status="ok", rows=rows, requests=1,
                    coverage_start=expirations[0] if expirations else None,
                    coverage_end=expirations[-1] if expirations else None,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
            except Exception as exc:  # noqa: BLE001 - one bad underlying must not abort the run
                runs.finish_target(conn, run_id, underlying, status="error", requests=1,
                                   duration_ms=int((time.monotonic() - t0) * 1000),
                                   error=str(exc)[:300])
