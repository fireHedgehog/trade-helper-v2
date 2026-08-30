"""Index / sector / theme membership sync.

Scrapes issuer holdings files — SSGA SPDR XLSX (SPY, DIA, the 11 sector
SPDRs, XBI), the Nasdaq-100 list API (QQQ→NDX, with market caps), iShares
CSV (SOXX, IGV) and ARK CSV (ARKX space & defense) — and writes
`symbol_memberships` + `membership_groups`. Also derives `assets.sector`
from which sector SPDR holds a name, and fills `assets.market_cap` for the
Nasdaq-100 constituents.

Ported from the previous app's `universe/compile_stage2_universe.py`. Polite:
one request at a time, ≥2 s apart, real User-Agent.
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
import time
import zipfile
from datetime import date
from xml.etree import ElementTree as ET

import httpx

from app.features.data_management import runs
from app.features.data_management.universe import recompute_active_universe
from app.pacing import get_limiter

_UA = {"User-Agent": "Mozilla/5.0"}
_A = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

# anchor ticker -> (group_key, group_type)
SSGA_GROUPS = {
    "SPY": ("SP500", "index"), "DIA": ("DJIA", "index"),
    "XLB": ("XLB", "sector_etf"), "XLC": ("XLC", "sector_etf"), "XLE": ("XLE", "sector_etf"),
    "XLF": ("XLF", "sector_etf"), "XLI": ("XLI", "sector_etf"), "XLK": ("XLK", "sector_etf"),
    "XLP": ("XLP", "sector_etf"), "XLRE": ("XLRE", "sector_etf"), "XLU": ("XLU", "sector_etf"),
    "XLV": ("XLV", "sector_etf"), "XLY": ("XLY", "sector_etf"), "XBI": ("XBI", "theme_etf"),
}
ISHARES_GROUPS = {
    "SOXX": "https://www.ishares.com/us/products/239705/ishares-semiconductor-etf/latest-holdings.csv",
    "IGV": "https://www.ishares.com/us/products/239771/ishares-expanded-tech-software-sector-etf/latest-holdings.csv",
}
ARK_GROUPS = {
    "ARKX": "https://assets.ark-funds.com/fund-documents/funds-etf-csv/"
            "ARK_SPACE_%26_DEFENSE_INNOVATION_ETF_ARKX_HOLDINGS.csv",
}
GROUP_NAMES = {
    "XBI": "SPDR S&P Biotech ETF", "ARKX": "ARK Space Exploration & Innovation ETF",
    "SOXX": "iShares Semiconductor ETF", "IGV": "iShares Expanded Tech-Software ETF",
}

_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}([.\-][A-Z])?$")


def _num(v: object) -> float | None:
    if v is None:
        return None
    t = str(v).strip().replace(",", "").replace("$", "").replace("%", "")
    if not t or t in {"-", "--", "N/A"}:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _clean_symbol(raw: str) -> str | None:
    s = (raw or "").strip().upper()
    return s if _SYMBOL_RE.fullmatch(s) else None


# ---- minimal stdlib XLSX reader (first worksheet) ----

def _xlsx_rows(data: bytes) -> list[list[str | None]]:
    with zipfile.ZipFile(io.BytesIO(data)) as wb:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in wb.namelist():
            root = ET.fromstring(wb.read("xl/sharedStrings.xml"))
            for si in root.findall("a:si", _A):
                shared.append("".join(t.text or "" for t in si.findall(".//a:t", _A)))
        names = sorted(n for n in wb.namelist() if n.startswith("xl/worksheets/") and n.endswith(".xml"))
        sheet = ET.fromstring(wb.read(names[0]))
        rows: list[list[str | None]] = []
        for r in sheet.findall(".//a:row", _A):
            cells: list[str | None] = []
            for c in r.findall("a:c", _A):
                v = c.find("a:v", _A)
                val = v.text if v is not None else None
                if c.get("t") == "s" and val is not None:
                    val = shared[int(val)]
                elif c.get("t") == "inlineStr":
                    val = "".join(t.text or "" for t in c.findall(".//a:is//a:t", _A))
                cells.append(val)
            rows.append(cells)
        return rows


# ---- scrapers ----

async def _get(client: httpx.AsyncClient, url: str, *, json_accept: bool = False):
    limiter = get_limiter("issuer", 2.0)
    headers = dict(_UA)
    if json_accept:
        headers["Accept"] = "application/json"
    async with limiter:
        resp = await client.get(url, headers=headers, follow_redirects=True, timeout=25.0)
    resp.raise_for_status()
    return resp


async def fetch_ssga(client: httpx.AsyncClient, ticker: str) -> list[dict]:
    url = ("https://www.ssga.com/us/en/individual/etfs/library-content/products/"
           f"fund-data/etfs/us/holdings-daily-us-en-{ticker.lower()}.xlsx")
    rows = _xlsx_rows((await _get(client, url)).content)
    hi = next((i for i, r in enumerate(rows) if r and "Name" in r and "Ticker" in r), None)
    if hi is None:
        raise ValueError(f"{ticker}: no Name/Ticker header")
    header = rows[hi]
    ni, ti = header.index("Name"), header.index("Ticker")
    wi = next((i for i, v in enumerate(header) if v and "weight" in str(v).lower()), None)
    out: list[dict] = []
    for r in rows[hi + 1:]:
        name = str(r[ni]).strip() if ni < len(r) and r[ni] else ""
        sym = _clean_symbol(str(r[ti]) if ti < len(r) and r[ti] else "")
        if not name and not sym:
            if out:
                break  # marketing prose after the table
            continue
        if not sym:
            continue
        out.append({"symbol": sym, "name": name,
                    "weight": _num(r[wi]) if wi is not None and wi < len(r) else None})
    return out


async def fetch_nasdaq100(client: httpx.AsyncClient) -> list[dict]:
    url = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
    payload = (await _get(client, url, json_accept=True)).json()
    rows = (((payload or {}).get("data") or {}).get("data") or {}).get("rows") or []
    out: list[dict] = []
    for r in rows:
        sym = _clean_symbol(str(r.get("symbol") or ""))
        if not sym:
            continue
        out.append({"symbol": sym, "name": str(r.get("companyName") or "").strip(),
                    "weight": None, "market_cap": _num(r.get("marketCap"))})
    return out


async def fetch_ishares(client: httpx.AsyncClient, url: str) -> list[dict]:
    text = (await _get(client, url)).content.decode("utf-8-sig", "ignore")
    lines = text.splitlines()
    hi = next((i for i, ln in enumerate(lines) if ln.startswith("Ticker,") or ",Ticker," in ln), None)
    if hi is None:
        raise ValueError("iShares: no Ticker header")
    reader = csv.DictReader(lines[hi:])
    out: list[dict] = []
    for row in reader:
        if (row.get("Asset Class") or "").strip() not in ("Equity", ""):
            continue
        sym = _clean_symbol(str(row.get("Ticker") or ""))
        if not sym:
            continue
        out.append({"symbol": sym, "name": str(row.get("Name") or "").strip(),
                    "weight": _num(row.get("Weight (%)"))})
    return out


async def fetch_ark(client: httpx.AsyncClient, url: str, fund: str) -> list[dict]:
    text = (await _get(client, url)).content.decode("utf-8-sig", "ignore")
    reader = csv.DictReader(text.splitlines())
    out: list[dict] = []
    for row in reader:
        if (row.get("fund") or "").strip() != fund:
            continue
        sym = _clean_symbol(str(row.get("ticker") or ""))
        if not sym:
            continue
        out.append({"symbol": sym, "name": str(row.get("company") or "").strip(),
                    "weight": _num(row.get("weight (%)"))})
    return out


# ---- persistence ----

def _known_assets(conn: sqlite3.Connection) -> set[str]:
    return {r["symbol"] for r in conn.execute("SELECT symbol FROM assets")}


def _write_group(conn: sqlite3.Connection, group_key: str, group_type: str,
                 holdings: list[dict], source: str, known: set[str], today: str) -> int:
    conn.execute("BEGIN")
    conn.execute(
        """
        INSERT INTO membership_groups (group_key, group_type, name, sponsor, source_url,
                                       member_count, last_source_as_of, last_synced_at)
        VALUES (?,?,?,?,?,?,?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        ON CONFLICT(group_key) DO UPDATE SET
            member_count=excluded.member_count, source_url=excluded.source_url,
            last_source_as_of=excluded.last_source_as_of,
            last_synced_at=excluded.last_synced_at
        """,
        (group_key, group_type, GROUP_NAMES.get(group_key, group_key), None, source,
         len(holdings), today),
    )
    conn.execute(
        "UPDATE symbol_memberships SET active = 0, last_seen = ? WHERE group_key = ?",
        (today, group_key),
    )
    written = 0
    for h in holdings:
        sym = h["symbol"]
        # tolerate class-share punctuation differences vs the assets catalog
        match = next((c for c in (sym, sym.replace(".", "-"), sym.replace(".", "")) if c in known), None)
        target = match or sym
        conn.execute(
            """
            INSERT INTO symbol_memberships (symbol, group_key, weight, source, source_as_of,
                                            active, last_seen)
            VALUES (?,?,?,?,?,1,?)
            ON CONFLICT(symbol, group_key) DO UPDATE SET
                weight=excluded.weight, source=excluded.source, source_as_of=excluded.source_as_of,
                active=1, last_seen=excluded.last_seen
            """,
            (target, group_key, h.get("weight"), source, today, today),
        )
        written += 1
    conn.execute("COMMIT")
    return written


_SECTOR_GROUPS = ("XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY")


def _derive_asset_sectors(conn: sqlite3.Connection) -> int:
    gics = {
        r["group_key"]: r["gics_sector"]
        for r in conn.execute(
            "SELECT group_key, gics_sector FROM membership_groups WHERE group_key IN "
            f"({','.join('?' for _ in _SECTOR_GROUPS)})",
            _SECTOR_GROUPS,
        )
    }
    rows = conn.execute(
        f"""
        SELECT symbol, group_key FROM symbol_memberships
         WHERE active = 1 AND group_key IN ({','.join('?' for _ in _SECTOR_GROUPS)})
        """,
        _SECTOR_GROUPS,
    ).fetchall()
    by_symbol: dict[str, set[str]] = {}
    for r in rows:
        by_symbol.setdefault(r["symbol"], set()).add(r["group_key"])
    conn.execute("BEGIN")
    n = 0
    for sym, groups in by_symbol.items():
        sector = gics[next(iter(groups))] if len(groups) == 1 else None
        if sector:
            conn.execute("UPDATE assets SET sector = ? WHERE symbol = ?", (sector, sym))
            n += 1
    conn.execute("COMMIT")
    return n


def _write_market_caps(conn: sqlite3.Connection, holdings: list[dict], known: set[str]) -> int:
    conn.execute("BEGIN")
    n = 0
    for h in holdings:
        mc = h.get("market_cap")
        if mc and h["symbol"] in known:
            conn.execute("UPDATE assets SET market_cap = ? WHERE symbol = ?", (int(mc), h["symbol"]))
            n += 1
    conn.execute("COMMIT")
    return n


# ---- handler ----

async def run_memberships(conn: sqlite3.Connection, run_id: int) -> None:
    targets = [("SSGA", t) for t in SSGA_GROUPS] + [("NDX", "QQQ")] + \
              [("ISHARES", t) for t in ISHARES_GROUPS] + [("ARK", t) for t in ARK_GROUPS]
    # + derive-sectors + recompute-universe
    runs.set_planned(conn, run_id, len(targets) + 2)
    known = _known_assets(conn)
    today = date.today().isoformat()

    async with httpx.AsyncClient() as client:
        for kind, ticker in targets:
            runs.raise_if_cancelled(run_id)
            runs.start_target(conn, run_id, ticker)
            t0 = time.monotonic()
            try:
                if kind == "SSGA":
                    group_key, group_type = SSGA_GROUPS[ticker]
                    holdings = await fetch_ssga(client, ticker)
                    src = f"ssga:{ticker}"
                elif kind == "NDX":
                    group_key, group_type = "NDX", "index"
                    holdings = await fetch_nasdaq100(client)
                    src = "nasdaq:nasdaq100"
                elif kind == "ISHARES":
                    group_key, group_type = ticker, "theme_etf"
                    holdings = await fetch_ishares(client, ISHARES_GROUPS[ticker])
                    src = f"ishares:{ticker}"
                else:  # ARK
                    group_key, group_type = ticker, "theme_etf"
                    holdings = await fetch_ark(client, ARK_GROUPS[ticker], ticker)
                    src = f"ark:{ticker}"

                rows_written = _write_group(conn, group_key, group_type, holdings, src, known, today)
                if kind == "NDX":
                    rows_written += _write_market_caps(conn, holdings, known)
                runs.finish_target(
                    conn, run_id, ticker, status="ok", rows=rows_written, requests=1,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
            except Exception as exc:  # noqa: BLE001 - one bad issuer must not abort the run
                runs.finish_target(conn, run_id, ticker, status="error", requests=1,
                                   duration_ms=int((time.monotonic() - t0) * 1000),
                                   error=str(exc)[:300])

    runs.raise_if_cancelled(run_id)
    runs.start_target(conn, run_id, "derive-sectors")
    t0 = time.monotonic()
    try:
        n = _derive_asset_sectors(conn)
        runs.finish_target(conn, run_id, "derive-sectors", status="ok", rows=n,
                           duration_ms=int((time.monotonic() - t0) * 1000))
    except Exception as exc:  # noqa: BLE001
        runs.finish_target(conn, run_id, "derive-sectors", status="error",
                           duration_ms=int((time.monotonic() - t0) * 1000), error=str(exc)[:300])

    # Fold the freshly-scraped index / core-ETF constituents into the active
    # price-fetch set, so a new index addition starts being tracked now.
    runs.raise_if_cancelled(run_id)
    runs.start_target(conn, run_id, "recompute-universe")
    t0 = time.monotonic()
    try:
        stats = recompute_active_universe(conn)
        runs.finish_target(conn, run_id, "recompute-universe", status="ok",
                           rows=stats["active"],
                           duration_ms=int((time.monotonic() - t0) * 1000))
    except Exception as exc:  # noqa: BLE001
        runs.finish_target(conn, run_id, "recompute-universe", status="error",
                           duration_ms=int((time.monotonic() - t0) * 1000), error=str(exc)[:300])
