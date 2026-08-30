"""Hard-coded Trend-page watchlist strip.

Not user-editable — the handful of names the operator always wants the current
signal state for, grouped into labelled sections (the board renders a divider
row per section). Spans equity indices, the semis/software pair, the full
sector-SPDR set, the mega-cap 7, and the cross-asset trio.
"""

TREND_WATCHLIST_SECTIONS: list[tuple[str, list[str]]] = [
    ("Indices", ["QQQ", "SPY", "DIA", "IWM"]),
    ("Semis / Software", ["SOXX", "IGV"]),
    ("Sector SPDRs", ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]),
    ("Mega-cap 7", ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]),
    ("Cross-asset", ["GLD", "USO", "BTC/USD"]),
]

# flat list, used to fold the watchlist into the universe run + stats lookups
TREND_WATCHLIST: list[str] = [s for _, syms in TREND_WATCHLIST_SECTIONS for s in syms]
