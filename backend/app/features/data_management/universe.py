"""Price-fetch universe (`assets.active = 1`).

The active set is the **union** of:
  1. `SEED_ACTIVE_SYMBOLS` below — a hand-picked list of liquid, multi-sector /
     multi-theme / multi-"seesaw" names plus every ETF we track, organised
     into editable named groups; and
  2. the current constituents of the index / core-ETF membership groups in
     `AUTO_ACTIVE_GROUPS`, as scraped by the memberships sync — so a fresh
     IPO added to the Nasdaq-100 or S&P 500 starts being tracked on the next
     "Sync memberships" run, no code change needed.

`recompute_active_universe()` applies the union; it runs at the end of both
the asset-catalog sync and the memberships sync.

What belongs in the seed:
  - any ETF we want bars for (indices, factors, bonds, sectors, themes,
    commodities) — ETFs are not in the scraped constituent lists
  - a company that is NOT in any `AUTO_ACTIVE_GROUPS` group but still worth
    tracking (a foreign ADR, a recent IPO not yet index-included, a
    divergence-pair name)
  - avoid near-duplicates; liquidity still matters, but a young IPO is fine
    now — the point is to watch new names cross-sectionally
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

# =========================================================================
# ETFs
# =========================================================================

ETF_BROAD = [
    "SPY", "QQQ", "IWM", "DIA", "VTI", "RSP", "MDY", "IJR", "IWO", "IWN",
    "VEA", "VWO", "EFA", "EEM", "ACWI",
]

ETF_FACTOR = [
    "MTUM", "QUAL", "VLUE", "USMV", "SPLV", "VUG", "VTV", "IWF", "IWD",
    "SCHD", "NOBL", "MOAT", "ARKK",
]

ETF_BONDS = [
    "BIL", "SHV", "SHY", "IEF", "TLT", "GOVT",
    "LQD", "HYG", "JNK", "TIP", "AGG", "BND", "BNDX", "EMB", "MBB", "MUB", "FLOT",
]

ETF_SECTOR = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]

# Industry / thematic — the divergence "seesaws".
ETF_THEME = [
    "SMH", "SOXX", "IGV", "SKYY", "CIBR", "HACK",       # tech / cyber / cloud
    "XBI", "IBB",                                        # biotech
    "XOP", "OIH", "TAN", "ICLN", "URA", "LIT",           # energy / clean / battery
    "XME", "GDX", "GDXJ", "SIL", "COPX",                 # miners / metals
    "ITB", "XHB", "KRE", "KBE", "IYT", "XRT", "JETS",    # rate-sensitive cyclicals
    "PAVE",                                              # infrastructure
    "KWEB", "FXI", "EWJ", "EWZ", "INDA", "EWG",          # int'l single-country
    "IYR", "VNQ",                                        # real estate
    "IBIT", "VXX",                                       # crypto proxy / vol
]

ETF_COMMODITY = ["GLD", "SLV", "PPLT", "DBC", "PDBC", "USO", "BNO", "UNG", "DBA", "CPER"]

# =========================================================================
# Equities — by sector / industry
# =========================================================================

EQ_MEGA = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "AVGO", "TSLA", "BRK.B",
    "JPM", "LLY", "V", "MA", "XOM", "UNH", "COST", "WMT", "PG", "JNJ", "HD", "ORCL",
]

EQ_SEMIS_HW = [
    "AMD", "MU", "TXN", "QCOM", "INTC", "LRCX", "AMAT", "KLAC", "TER", "MRVL",
    "ADI", "NXPI", "ON", "MCHP", "SWKS", "ARM", "TSM", "ASML", "SKHY",
    "ANET", "SMCI", "DELL", "HPE", "CSCO", "GLW",
]

# AI build-out / GPU-cloud infrastructure — mostly recent listings, higher
# beta than the classic semis. NBIS/CRWV/ALAB are Nasdaq-100 members so they
# also arrive via AUTO_ACTIVE_GROUPS; kept here so the cluster is explicit.
EQ_AI_INFRA = ["NBIS", "CRWV", "ALAB", "VRT", "SMCI"]

EQ_SOFTWARE = [
    "CRM", "ADBE", "NOW", "INTU", "SNOW", "PLTR", "WDAY", "TEAM", "DDOG", "MDB",
    "NET", "HUBS", "SNPS", "CDNS", "ADSK", "ANSS", "MSTR", "COIN", "APP",
    "PANW", "CRWD", "FTNT", "ZS", "S", "OKTA", "SHOP", "IBM", "ACN",
]

EQ_INTERNET_MEDIA = [
    "NFLX", "DIS", "CMCSA", "TMUS", "T", "VZ", "CHTR", "WBD", "EA", "TTWO", "LYV",
    "SPOT", "UBER", "ABNB", "DASH", "BKNG", "EXPE", "RBLX", "PINS", "SNAP",
    "BABA", "PDD", "JD", "BIDU", "NTES",
]

EQ_CONSUMER_DISC = [
    "NKE", "MCD", "SBUX", "CMG", "DRI", "LOW", "TJX", "ROST", "LULU", "DECK",
    "ULTA", "ORLY", "AZO", "MAR", "HLT", "RCL", "CCL", "LVS", "YUM",
    "GM", "F", "RIVN", "APTV", "DHI", "LEN",
]

EQ_CONSUMER_STAPLES = [
    "KO", "PEP", "MDLZ", "MO", "PM", "CL", "KMB", "GIS", "KHC", "TGT", "DG",
    "KR", "STZ", "KDP", "KVUE", "ADM", "TSN",
]

EQ_FINANCIALS = [
    "BAC", "WFC", "C", "GS", "MS", "SCHW", "BLK", "SPGI", "MCO", "MSCI", "ICE",
    "CME", "NDAQ", "AXP", "PYPL", "COF", "USB", "PNC", "TFC", "TROW",
    "PGR", "TRV", "CB", "ALL", "AFL", "AIG", "MET", "PRU", "KKR", "BX", "APO",
]

EQ_HEALTHCARE = [
    "MRK", "PFE", "ABBV", "TMO", "ABT", "DHR", "BMY", "AMGN", "GILD", "VRTX",
    "REGN", "BIIB", "MRNA", "ALNY", "NVO", "AZN",
    "ISRG", "MDT", "SYK", "BSX", "BDX", "DXCM", "GEHC", "ZTS",
    "CI", "CVS", "HUM", "ELV", "CNC", "MCK", "HCA", "IQV",
]

EQ_INDUSTRIALS = [
    "GE", "HON", "RTX", "LMT", "GD", "NOC", "LHX", "TDG", "AXON", "BA",
    "CAT", "DE", "CMI", "ROK", "URI", "GWW", "PCAR", "ETN", "EMR", "PH",
    "ITW", "MMM", "UNP", "UPS", "FDX", "ODFL", "CSX", "NSC", "WM", "RSG", "GEV", "PWR",
]

EQ_ENERGY = [
    "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "VLO", "OXY", "WMB", "KMI", "OKE",
    "EPD", "ET", "TRGP", "LNG", "HES", "DVN", "FANG", "HAL", "BKR",
]

EQ_MATERIALS = [
    "LIN", "APD", "SHW", "ECL", "LYB", "FCX", "SCCO", "RIO", "NEM", "NUE", "STLD",
    "DOW", "DD", "CTVA", "CF", "MOS", "VMC", "MLM", "ALB",
]

EQ_UTILITIES = [
    "NEE", "SO", "DUK", "D", "AEP", "EXC", "SRE", "XEL", "PEG", "ED", "CEG", "VST",
    "NRG", "PCG",
]

EQ_REAL_ESTATE = [
    "PLD", "AMT", "EQIX", "DLR", "IRM", "SBAC", "WELL", "O", "SPG", "PSA", "CCI",
    "VICI", "EXR", "AVB", "VTR", "VRT",
]

EQ_CLEAN_ENERGY = ["ENPH", "FSLR", "SEDG", "RUN", "NEE"]  # solar (rate/oil seesaw)

# Airlines & travel-transport (oil / consumer-cyclical seesaw)
EQ_AIRLINES = ["DAL", "UAL", "AAL", "LUV", "ALK", "JBLU", "JETS"]

# Space & defense-innovation (the "航天板块" — ARKX-style names). Newer/
# higher-beta than the classic primes (BA, LMT, RTX, NOC, GD, LHX, TDG).
# SPCX (Space Exploration Technologies) is a Nasdaq-100 member too.
EQ_SPACE_DEFENSE = ["SPCX", "RKLB", "RDW", "ASTS", "LUNR", "KTOS", "AVAV", "PL", "ARKX"]


def _dedupe(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for sym in group:
            if sym not in seen:
                seen.add(sym)
                out.append(sym)
    return out


SEED_ACTIVE_SYMBOLS: list[str] = _dedupe(
    ETF_BROAD, ETF_FACTOR, ETF_BONDS, ETF_SECTOR, ETF_THEME, ETF_COMMODITY,
    EQ_MEGA, EQ_SEMIS_HW, EQ_AI_INFRA, EQ_SOFTWARE, EQ_INTERNET_MEDIA,
    EQ_CONSUMER_DISC, EQ_CONSUMER_STAPLES, EQ_FINANCIALS, EQ_HEALTHCARE,
    EQ_INDUSTRIALS, EQ_ENERGY, EQ_MATERIALS, EQ_UTILITIES, EQ_REAL_ESTATE,
    EQ_CLEAN_ENERGY, EQ_AIRLINES, EQ_SPACE_DEFENSE,
)

CRYPTO_ACTIVE_SYMBOLS: list[str] = ["BTC/USD", "ETH/USD"]

# Membership groups whose current constituents are folded into the active
# price-fetch set. The three US indices plus the 11 sector SPDRs give "the
# liquid US large/mid-cap market", self-updating as the indices rebalance;
# SOXX + ARKX add the semis and space names we care about. XBI (~130 micro
# biotechs) and IGV (~120 small software names) are deliberately left out —
# their memberships are still scraped, just not force-fetched.
AUTO_ACTIVE_GROUPS: tuple[str, ...] = (
    "SP500", "NDX", "DJIA",
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
    "SOXX", "ARKX",
)


def recompute_active_universe(conn: sqlite3.Connection) -> dict:
    """Set `assets.active` = seed ∪ current members of `AUTO_ACTIVE_GROUPS`.

    Idempotent; safe to run whenever the seed or the scraped memberships
    change. Returns a small summary for logging / the run item.
    """
    ph = ",".join("?" for _ in AUTO_ACTIVE_GROUPS)
    conn.execute("BEGIN")
    conn.execute("UPDATE assets SET active = 0")
    conn.executemany(
        "UPDATE assets SET active = 1 WHERE symbol = ?",
        [(s,) for s in SEED_ACTIVE_SYMBOLS],
    )
    conn.execute(
        f"""
        UPDATE assets SET active = 1
         WHERE symbol IN (
             SELECT DISTINCT symbol FROM symbol_memberships
              WHERE active = 1 AND group_key IN ({ph})
         )
        """,
        AUTO_ACTIVE_GROUPS,
    )
    conn.executemany(
        "UPDATE crypto_assets SET active = 1 WHERE symbol = ?",
        [(s,) for s in CRYPTO_ACTIVE_SYMBOLS],
    )
    conn.execute("COMMIT")

    active = conn.execute("SELECT COUNT(*) FROM assets WHERE active = 1").fetchone()[0]
    active_syms = {r["symbol"] for r in conn.execute("SELECT symbol FROM assets WHERE active = 1")}
    from_members = conn.execute(
        f"""SELECT COUNT(DISTINCT m.symbol) FROM symbol_memberships m
             JOIN assets a ON a.symbol = m.symbol
            WHERE m.active = 1 AND m.group_key IN ({ph})""",
        AUTO_ACTIVE_GROUPS,
    ).fetchone()[0]
    missing_seed = sorted(set(SEED_ACTIVE_SYMBOLS) - active_syms)
    unmatched_members = sorted(
        r["symbol"] for r in conn.execute(
            f"""SELECT DISTINCT m.symbol FROM symbol_memberships m
                 LEFT JOIN assets a ON a.symbol = m.symbol
                WHERE m.active = 1 AND m.group_key IN ({ph}) AND a.symbol IS NULL""",
            AUTO_ACTIVE_GROUPS,
        )
    )
    logger.info(
        "Active universe: %d symbols (%d via %d membership groups)%s%s",
        active, from_members, len(AUTO_ACTIVE_GROUPS),
        f"; seed not in Alpaca catalog: {', '.join(missing_seed)}" if missing_seed else "",
        f"; members not in Alpaca catalog: {', '.join(unmatched_members)}" if unmatched_members else "",
    )
    return {
        "active": active,
        "from_members": from_members,
        "missing_seed": missing_seed,
        "unmatched_members": unmatched_members,
    }
