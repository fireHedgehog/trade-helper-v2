"""Disposable, read-only cross-sectional Donchian versus buy-and-hold study.

This script deliberately lives outside the application package. It reuses the
production signal engine but never writes to SQLite. Outputs are disposable
files under docs/temp/.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import sqlite3
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

TEMP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TEMP_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.features.data_management.universe import (  # noqa: E402
    ETF_BONDS,
    ETF_BROAD,
    ETF_COMMODITY,
    ETF_FACTOR,
    ETF_SECTOR,
    ETF_THEME,
)
from app.features.signals import data as ohlc  # noqa: E402
from app.features.signals import engine, metrics  # noqa: E402
from app.features.signals.params import SignalParams  # noqa: E402
from app.features.signals.watchlist import TREND_WATCHLIST  # noqa: E402

GROUP_ORDER = [
    "Individual equity",
    "Broad index ETF",
    "Factor/style ETF",
    "Sector ETF",
    "Thematic/industry ETF",
    "Bond ETF",
    "Commodity ETF",
    "Bitcoin",
    "Crypto",
    "Other",
]

ETF_GROUPS = {
    **{s: "Broad index ETF" for s in ETF_BROAD},
    **{s: "Factor/style ETF" for s in ETF_FACTOR},
    **{s: "Bond ETF" for s in ETF_BONDS},
    **{s: "Sector ETF" for s in ETF_SECTOR},
    **{s: "Thematic/industry ETF" for s in ETF_THEME},
    **{s: "Commodity ETF" for s in ETF_COMMODITY},
}


@dataclass(frozen=True)
class Target:
    symbol: str
    name: str
    group: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=REPO_ROOT / "database" / "trade_helper.sqlite3",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "docs" / "temp",
    )
    parser.add_argument(
        "--primary-min-bars",
        type=int,
        default=756,
        help="Minimum observations for headline group comparisons (default: ~3 equity years).",
    )
    return parser.parse_args()


def read_only_connection(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def active_config(conn: sqlite3.Connection) -> tuple[str, SignalParams]:
    row = conn.execute(
        "SELECT name, params_json FROM signal_config WHERE is_active = 1 ORDER BY id LIMIT 1"
    ).fetchone()
    if row is None:
        raise RuntimeError("No active signal configuration")
    params = SignalParams(**json.loads(row["params_json"]))
    return row["name"], params


def latest_universe_run(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM signal_runs WHERE scope='universe' AND status='succeeded' "
        "ORDER BY run_id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def classify(symbol: str, *, crypto: bool = False) -> str:
    if crypto:
        if symbol == "BTC/USD":
            return "Bitcoin"
        return "Crypto"
    return ETF_GROUPS.get(symbol, "Individual equity")


def universe_targets(conn: sqlite3.Connection) -> list[Target]:
    metadata: dict[str, Target] = {}
    for row in conn.execute("SELECT symbol, COALESCE(name, symbol) name FROM assets WHERE active=1"):
        symbol = ohlc.normalize_symbol(row["symbol"])
        metadata[symbol] = Target(symbol, row["name"], classify(symbol))
    crypto_rows = list(
        conn.execute("SELECT symbol, COALESCE(name, symbol) name FROM crypto_assets WHERE active=1")
    )
    if not crypto_rows:
        crypto_rows = [{"symbol": "BTC/USD", "name": "Bitcoin"}, {"symbol": "ETH/USD", "name": "Ethereum"}]
    for row in crypto_rows:
        symbol = ohlc.normalize_symbol(row["symbol"])
        metadata[symbol] = Target(symbol, row["name"], classify(symbol, crypto=True))
    for raw_symbol in TREND_WATCHLIST:
        symbol = ohlc.normalize_symbol(raw_symbol)
        if symbol in metadata:
            continue
        row = conn.execute(
            "SELECT COALESCE(name, symbol) name FROM assets WHERE symbol=?", (symbol,)
        ).fetchone()
        metadata[symbol] = Target(symbol, row["name"] if row else symbol, classify(symbol))
    return [metadata[symbol] for symbol in sorted(metadata)]


def value(d: dict[str, Any], *path: str) -> Any:
    current: Any = d
    for key in path:
        current = current.get(key) if isinstance(current, dict) else None
    return current


def calmar(cagr: float | None, max_drawdown: float | None) -> float | None:
    if cagr is None or max_drawdown is None or max_drawdown >= 0:
        return None
    return cagr / abs(max_drawdown)


def compute_row(
    conn: sqlite3.Connection,
    target: Target,
    both_params: SignalParams,
    long_params: SignalParams,
) -> dict[str, Any] | None:
    bars = ohlc.load_ohlc(conn, target.symbol)
    if len(bars) < 60:
        return None
    both_result = engine.run(bars, both_params)
    both_metrics = metrics.summarise(both_result.trades, both_result.daily, bars)
    long_result = engine.run(bars, long_params)
    long_metrics = metrics.summarise(long_result.trades, long_result.daily, bars)

    bh_cagr = value(both_metrics, "buy_hold", "cagr")
    bh_dd = value(both_metrics, "buy_hold", "max_drawdown")
    both_cagr = value(both_metrics, "strategy", "cagr")
    both_dd = value(both_metrics, "strategy", "max_drawdown")
    long_cagr = value(long_metrics, "strategy", "cagr")
    long_dd = value(long_metrics, "strategy", "max_drawdown")
    first_date, last_date = bars[0]["date"], bars[-1]["date"]
    return {
        "symbol": target.symbol,
        "name": target.name,
        "group": target.group,
        "bars": len(bars),
        "years_252": len(bars) / 252.0,
        "first_date": first_date,
        "last_date": last_date,
        "bh_cagr": bh_cagr,
        "bh_max_dd": bh_dd,
        "bh_calmar": calmar(bh_cagr, bh_dd),
        "both_cagr": both_cagr,
        "both_cagr_delta": both_cagr - bh_cagr if both_cagr is not None and bh_cagr is not None else None,
        "both_max_dd": both_dd,
        "both_dd_reduction": abs(bh_dd) - abs(both_dd) if both_dd is not None and bh_dd is not None else None,
        "both_sharpe": value(both_metrics, "strategy", "sharpe"),
        "both_calmar": value(both_metrics, "strategy", "calmar"),
        "both_exposure": value(both_metrics, "trade_stats", "exposure"),
        "both_trades": value(both_metrics, "trade_stats", "trades"),
        "both_win_rate": value(both_metrics, "trade_stats", "win_rate"),
        "both_beats_bh": bool(both_cagr is not None and bh_cagr is not None and both_cagr > bh_cagr),
        "both_calmar_beats_bh": bool(
            value(both_metrics, "strategy", "calmar") is not None
            and calmar(bh_cagr, bh_dd) is not None
            and value(both_metrics, "strategy", "calmar") > calmar(bh_cagr, bh_dd)
        ),
        "long_cagr": long_cagr,
        "long_cagr_delta": long_cagr - bh_cagr if long_cagr is not None and bh_cagr is not None else None,
        "long_max_dd": long_dd,
        "long_dd_reduction": abs(bh_dd) - abs(long_dd) if long_dd is not None and bh_dd is not None else None,
        "long_sharpe": value(long_metrics, "strategy", "sharpe"),
        "long_calmar": value(long_metrics, "strategy", "calmar"),
        "long_exposure": value(long_metrics, "trade_stats", "exposure"),
        "long_trades": value(long_metrics, "trade_stats", "trades"),
        "long_win_rate": value(long_metrics, "trade_stats", "win_rate"),
        "long_beats_bh": bool(long_cagr is not None and bh_cagr is not None and long_cagr > bh_cagr),
    }


def finite(values: Iterable[float | None]) -> list[float]:
    return [float(v) for v in values if v is not None and math.isfinite(float(v))]


def median(values: Iterable[float | None]) -> float | None:
    xs = finite(values)
    return statistics.median(xs) if xs else None


def group_summary(rows: list[dict[str, Any]], min_bars: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for group in GROUP_ORDER:
        subset = [r for r in rows if r["group"] == group and r["bars"] >= min_bars]
        if not subset:
            continue
        out.append(
            {
                "group": group,
                "n": len(subset),
                "both_beat_rate": sum(r["both_beats_bh"] for r in subset) / len(subset),
                "long_beat_rate": sum(r["long_beats_bh"] for r in subset) / len(subset),
                "both_calmar_beat_rate": sum(r["both_calmar_beats_bh"] for r in subset) / len(subset),
                "median_bh_cagr": median(r["bh_cagr"] for r in subset),
                "median_both_cagr": median(r["both_cagr"] for r in subset),
                "median_both_delta": median(r["both_cagr_delta"] for r in subset),
                "median_long_delta": median(r["long_cagr_delta"] for r in subset),
                "median_both_dd_reduction": median(r["both_dd_reduction"] for r in subset),
                "median_both_exposure": median(r["both_exposure"] for r in subset),
            }
        )
    return out


def pct(v: float | None, digits: int = 1) -> str:
    return "—" if v is None else f"{v * 100:.{digits}f}%"


def num(v: float | None, digits: int = 2) -> str:
    return "—" if v is None else f"{v:.{digits}f}"


def esc(v: Any) -> str:
    return html.escape(str(v))


def table(headers: list[str], body: list[list[Any]], classes: str = "") -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    rows = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in body
    )
    return f'<div class="table-wrap"><table class="{classes}"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'


def bar_chart(summary: list[dict[str, Any]], field: str, title: str, percent: bool) -> str:
    width, row_h, label_w, plot_w = 820, 34, 190, 560
    height = 50 + row_h * len(summary)
    vals = [float(r[field]) for r in summary]
    if percent:
        lo, hi = 0.0, 1.0
    else:
        lo = min(0.0, min(vals, default=0.0))
        hi = max(0.0, max(vals, default=0.0))
        pad = max(0.01, (hi - lo) * 0.1)
        lo, hi = lo - pad, hi + pad
    span = hi - lo or 1.0
    zero_x = label_w + (-lo / span) * plot_w
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">']
    parts.append(f'<text x="0" y="18" class="chart-title">{esc(title)}</text>')
    parts.append(f'<line x1="{zero_x:.1f}" y1="30" x2="{zero_x:.1f}" y2="{height-8}" class="zero"/>')
    for i, row in enumerate(summary):
        y = 40 + i * row_h
        v = float(row[field])
        x = label_w + ((min(v, 0.0) - lo) / span) * plot_w
        end = label_w + ((max(v, 0.0) - lo) / span) * plot_w
        bar_x, bar_w = min(x, end), max(2.0, abs(end - x))
        color = "#2e7d32" if v >= 0 else "#c62828"
        label = pct(v) if percent else pct(v)
        parts.append(f'<text x="0" y="{y+17}" class="axis-label">{esc(row["group"])}</text>')
        parts.append(f'<rect x="{bar_x:.1f}" y="{y+3}" width="{bar_w:.1f}" height="20" rx="3" fill="{color}"/>')
        text_x = end + 7 if v >= 0 else end - 7
        anchor = "start" if v >= 0 else "end"
        parts.append(f'<text x="{text_x:.1f}" y="{y+18}" text-anchor="{anchor}" class="value-label">{label}</text>')
    parts.append("</svg>")
    return "".join(parts)


def scatter_chart(rows: list[dict[str, Any]], min_bars: int) -> str:
    points = [
        r for r in rows
        if r["bars"] >= min_bars and r["group"] in {"Individual equity", "Broad index ETF"}
        and r["bh_cagr"] is not None and r["both_cagr"] is not None
    ]
    width, height, left, top, plot_w, plot_h = 820, 500, 70, 40, 690, 390
    values = finite([r["bh_cagr"] for r in points] + [r["both_cagr"] for r in points])
    values.sort()
    if not values:
        return ""
    lo = max(-0.5, values[max(0, int(len(values) * 0.01) - 1)] - 0.03)
    hi = min(1.0, values[min(len(values) - 1, int(len(values) * 0.99))] + 0.03)
    if hi <= lo:
        hi = lo + 0.1
    def sx(v: float) -> float:
        return left + (max(lo, min(hi, v)) - lo) / (hi - lo) * plot_w
    def sy(v: float) -> float:
        return top + plot_h - (max(lo, min(hi, v)) - lo) / (hi - lo) * plot_h
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Strategy CAGR versus buy-and-hold CAGR">']
    parts.append('<text x="0" y="18" class="chart-title">Two-sided strategy CAGR vs buy-and-hold CAGR</text>')
    parts.append(f'<line x1="{sx(lo):.1f}" y1="{sy(lo):.1f}" x2="{sx(hi):.1f}" y2="{sy(hi):.1f}" class="diagonal"/>')
    for r in points:
        color = "#1565c0" if r["group"] == "Individual equity" else "#ef6c00"
        parts.append(
            f'<circle cx="{sx(r["bh_cagr"]):.1f}" cy="{sy(r["both_cagr"]):.1f}" r="3" fill="{color}" opacity="0.62">'
            f'<title>{esc(r["symbol"])} · B&H {pct(r["bh_cagr"])} · strategy {pct(r["both_cagr"])}</title></circle>'
        )
    parts.append(f'<text x="{left + plot_w/2:.1f}" y="{height-15}" text-anchor="middle" class="axis-label">Buy-and-hold CAGR</text>')
    parts.append(f'<text x="15" y="{top + plot_h/2:.1f}" transform="rotate(-90 15 {top + plot_h/2:.1f})" text-anchor="middle" class="axis-label">Strategy CAGR</text>')
    parts.append('<circle cx="590" cy="18" r="4" fill="#1565c0"/><text x="600" y="22" class="value-label">Individual equity</text>')
    parts.append('<circle cx="700" cy="18" r="4" fill="#ef6c00"/><text x="710" y="22" class="value-label">Broad index ETF</text>')
    parts.append("</svg>")
    return "".join(parts)


def result_cells(r: dict[str, Any]) -> list[str]:
    delta_class = "pos" if (r["both_cagr_delta"] or 0) > 0 else "neg"
    return [
        f'<strong>{esc(r["symbol"])}</strong>',
        esc(r["group"]),
        f'{r["years_252"]:.1f}',
        pct(r["bh_cagr"]),
        pct(r["both_cagr"]),
        f'<span class="{delta_class}">{pct(r["both_cagr_delta"])}</span>',
        pct(r["both_max_dd"]),
        pct(r["bh_max_dd"]),
        pct(r["both_exposure"]),
        num(r["both_calmar"]),
        pct(r["long_cagr_delta"]),
    ]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(
    path: Path,
    rows: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    config_name: str,
    params: SignalParams,
    latest_run: dict[str, Any] | None,
    min_bars: int,
    elapsed: float,
) -> None:
    eligible = [r for r in rows if r["bars"] >= min_bars]
    stocks = next((r for r in summary if r["group"] == "Individual equity"), None)
    broad = next((r for r in summary if r["group"] == "Broad index ETF"), None)
    comparison = "Insufficient group coverage for the stock-versus-index comparison."
    if stocks and broad:
        direction = "higher" if stocks["both_beat_rate"] > broad["both_beat_rate"] else "not higher"
        comparison = (
            f'Individual equities had a {pct(stocks["both_beat_rate"])} CAGR beat rate versus '
            f'{pct(broad["both_beat_rate"])} for broad index ETFs; the stock beat rate was {direction}. '
            f'Median CAGR alpha was {pct(stocks["median_both_delta"])} for stocks and '
            f'{pct(broad["median_both_delta"])} for broad index ETFs.'
        )
    group_rows = [
        [
            esc(s["group"]), str(s["n"]), pct(s["both_beat_rate"]), pct(s["long_beat_rate"]),
            pct(s["both_calmar_beat_rate"]), pct(s["median_bh_cagr"]),
            pct(s["median_both_cagr"]), pct(s["median_both_delta"]),
            pct(s["median_both_dd_reduction"]), pct(s["median_both_exposure"]),
        ]
        for s in summary
    ]
    ranked = sorted(eligible, key=lambda r: r["both_cagr_delta"] if r["both_cagr_delta"] is not None else -999, reverse=True)
    broad_rows = [r for r in ranked if r["group"] == "Broad index ETF"]
    headers = ["Symbol", "Group", "Years", "B&H CAGR", "Strategy CAGR", "CAGR delta", "Strategy DD", "B&H DD", "Exposure", "Calmar", "Long-only delta"]
    css = """
    :root{color-scheme:light dark;--bg:#f5f7fa;--card:#fff;--text:#18212f;--muted:#667085;--line:#d8dee8}
    @media(prefers-color-scheme:dark){:root{--bg:#101318;--card:#171b22;--text:#e8edf5;--muted:#a8b0bd;--line:#303744}}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
    main{max-width:1280px;margin:auto;padding:28px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;margin:16px 0}
    h1{margin:0 0 4px;font-size:28px}h2{margin:0 0 12px;font-size:20px}.muted{color:var(--muted)}.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
    .kpi{padding:14px;border:1px solid var(--line);border-radius:9px}.kpi strong{display:block;font-size:22px}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;white-space:nowrap}
    th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right}th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left}th{position:sticky;top:0;background:var(--card)}
    .pos{color:#2e7d32;font-weight:650}.neg{color:#c62828;font-weight:650}.chart-title{font-size:15px;font-weight:650;fill:currentColor}.axis-label,.value-label{font-size:12px;fill:currentColor}.zero{stroke:#7c8798;stroke-width:1}.diagonal{stroke:#7c8798;stroke-dasharray:5 4}svg{width:100%;height:auto;overflow:visible}
    code{background:color-mix(in srgb,var(--card),var(--text) 8%);padding:2px 5px;border-radius:4px}.warning{border-left:4px solid #ef6c00}
    """
    latest_text = "none" if latest_run is None else f'run {latest_run["run_id"]}, {latest_run["n_symbols"]} symbols, finished {latest_run["finished_at"]}'
    content = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Donchian vs Buy & Hold — Disposable Research</title><style>{css}</style></head><body><main>
    <h1>Donchian vs Buy &amp; Hold</h1><div class="muted">Disposable cross-sectional research · generated {time.strftime('%Y-%m-%d %H:%M:%S')} · database opened read-only</div>
    <section class="card"><h2>Question</h2><p>Does the current baseline two-sided Donchian strategy beat same-symbol buy-and-hold more often on individual equities than on broad composite-index ETFs, or are AAPL/BTC attractive exceptions?</p><p><strong>Descriptive answer:</strong> {esc(comparison)}</p></section>
    <section class="card"><div class="kpis"><div class="kpi"><span>Targets computed</span><strong>{len(rows)}</strong></div><div class="kpi"><span>Primary cohort</span><strong>{len(eligible)}</strong><small>≥ {min_bars} observations</small></div><div class="kpi"><span>Current config</span><strong>{esc(config_name)}</strong></div><div class="kpi"><span>Compute time</span><strong>{elapsed:.1f}s</strong></div></div><p class="muted">Latest persisted Trend universe: {esc(latest_text)}. This report independently recomputes all current targets and does not trust mutable cached ownership.</p><details><summary>Exact parameters</summary><pre>{esc(json.dumps(params.model_dump(), indent=2))}</pre></details></section>
    <section class="card warning"><h2>Interpretation limits</h2><ul><li>The universe is today's active seed + current memberships, not a point-in-time historical universe. Individual-equity results therefore contain survivor/selection bias.</li><li>Each symbol is compared with buy-and-hold over its own available window. The headline group table requires at least {min_bars} observations, but start dates still differ.</li><li>The primary strategy is the app's two-sided 20/10 Donchian + initial ATR + Chandelier hybrid, not the original Turtle portfolio system.</li><li>Costs and slippage are included; borrow availability/fees, dividends beyond adjusted bars, tax, cash yield, and portfolio sizing are not.</li><li>Crypto uses the app's existing 252-period annualisation and is shown separately; do not compare it mechanically with equity groups.</li><li>This is a rough descriptive screen, not a statistical validation or an optimisation.</li></ul></section>
    <section class="card"><h2>Group comparison</h2>{table(["Group","N","Two-sided beats B&H","Long-only beats B&H","Calmar beats B&H","Median B&H CAGR","Median strategy CAGR","Median CAGR delta","Median DD reduction","Median exposure"],group_rows)}</section>
    <section class="card">{bar_chart(summary,"both_beat_rate","Share beating buy-and-hold CAGR (two-sided)",True)}</section>
    <section class="card">{bar_chart(summary,"median_both_delta","Median strategy CAGR minus buy-and-hold",False)}</section>
    <section class="card">{scatter_chart(rows,min_bars)}<p class="muted">Above the diagonal means the strategy CAGR beat buy-and-hold. Points are clipped at the 1st/99th percentile for readability; tooltips retain each displayed value.</p></section>
    <section class="card"><h2>Broad index ETFs</h2>{table(headers,[result_cells(r) for r in broad_rows])}</section>
    <section class="card"><h2>Top 25 CAGR improvements</h2>{table(headers,[result_cells(r) for r in ranked[:25]])}</section>
    <section class="card"><h2>Bottom 25 CAGR improvements</h2>{table(headers,[result_cells(r) for r in ranked[-25:]])}</section>
    <section class="card"><h2>How to read this</h2><p>A negative CAGR delta does not automatically make timing useless. Check drawdown reduction and Calmar: an index ETF may lose raw CAGR because it spends less time exposed to a strong positive drift, yet still deliver materially better drawdown-adjusted returns. Conversely, a high stock beat rate is only a hypothesis generator because the current active-stock universe is not survivorship-free.</p></section>
    </main></body></html>"""
    path.write_text(content, encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with read_only_connection(args.database) as conn:
        config_name, configured = active_config(conn)
        both_params = configured.model_copy(update={"allow_long": True, "allow_short": True})
        long_params = configured.model_copy(update={"allow_long": True, "allow_short": False})
        latest_run = latest_universe_run(conn)
        targets = universe_targets(conn)
        rows: list[dict[str, Any]] = []
        skipped = 0
        for index, target in enumerate(targets, start=1):
            row = compute_row(conn, target, both_params, long_params)
            if row is None:
                skipped += 1
            else:
                rows.append(row)
            if index % 50 == 0 or index == len(targets):
                print(f"Computed {index}/{len(targets)} targets", flush=True)
    rows.sort(key=lambda r: r["symbol"])
    if not rows:
        raise RuntimeError("No symbols had enough bars")
    summary = group_summary(rows, args.primary_min_bars)
    elapsed = time.perf_counter() - started
    csv_path = args.output_dir / "turtle_vs_buyhold_results.csv"
    json_path = args.output_dir / "turtle_vs_buyhold_summary.json"
    html_path = args.output_dir / "turtle_vs_buyhold_report.html"
    write_csv(csv_path, rows)
    json_path.write_text(
        json.dumps(
            {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "database": str(args.database.resolve()),
                "config_name": config_name,
                "params": both_params.model_dump(),
                "primary_min_bars": args.primary_min_bars,
                "targets": len(targets),
                "computed": len(rows),
                "skipped_under_60_bars": skipped,
                "latest_universe_run": latest_run,
                "groups": summary,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    write_report(
        html_path, rows, summary, config_name, both_params, latest_run,
        args.primary_min_bars, elapsed,
    )
    print(f"Wrote {csv_path}")
    print(f"Wrote {json_path}")
    print(f"Wrote {html_path}")


if __name__ == "__main__":
    main()
