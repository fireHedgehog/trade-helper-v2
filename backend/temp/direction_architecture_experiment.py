"""Stage 3 - disposable direction-architecture experiment (isolated).

Runs AFTER stage 1 (entry) and stage 2 (exit), both frozen here:

- Entry cluster: Bond ETFs 100/50, everything else 20/10.
- Exit: c3_d20 = Chandelier 3 ATR trailing stop + Donchian-20 reversal backstop
  + always-on initial 2 ATR disaster stop.

Only the direction policy varies. For every symbol the engine runs three ways:

  both    allow_long + allow_short   (the two-sided rule)
  long    allow_long only
  short   allow_short only           (the short leg standalone)

Delta = both - long is the short side's marginal contribution. `short`
standalone is carried so a "short hurts" result can be told apart from "these
names just went up": if the short leg has no edge even on flat/declining names
the entry rule is weak; if it earns its keep on low-drift / high-volatility
names, that is real evidence for two-sided there.

Aggregations, all reported (no cherry-picking): by asset-class group; by
Individual-equity quintiles of realised volatility, dollar volume, and own
buy&hold drift; per predefined period. Operational note: `shortable` /
`borrow_status` from the asset table is attached so a backtest-only "keep
long/short" that is hard-to-borrow is visible.

Reuses the production engine, opens SQLite read-only, never writes app tables.

  python backend/temp/direction_architecture_experiment.py
  python backend/temp/direction_architecture_experiment.py --from-csv
  python backend/temp/direction_architecture_experiment.py --cost-mult 2
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

TEMP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TEMP_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TEMP_DIR))

from app.features.signals import data as ohlc  # noqa: E402
from app.features.signals import engine  # noqa: E402
from app.features.signals.params import SignalParams  # noqa: E402
from app.features.signals.watchlist import TREND_WATCHLIST_SECTIONS  # noqa: E402
from turtle_vs_buyhold import (  # noqa: E402
    GROUP_ORDER,
    Target,
    active_config,
    latest_universe_run,
    read_only_connection,
    universe_targets,
)

ANNUAL_PERIODS = 252.0
MIN_ENGINE_BARS = 200
PERIOD_MIN_BARS = 126
BOND_GROUP = "Bond ETF"

# Frozen stage 2 exit.
EXIT = {"trail_mode": "chandelier", "chandelier_k": 3.0, "exit_len": 20}

DIRECTIONS = ("both", "long", "short")
PERIODS = [
    ("2016-2019", "2016-01-01", "2019-12-31"),
    ("2020-2022", "2020-01-01", "2022-12-31"),
    ("2023-present", "2023-01-01", "9999-12-31"),
]
QUINTILE_DIMS = [
    ("realised_vol", "Realised volatility"),
    ("dollar_volume", "Dollar volume"),
    ("bh_cagr", "Own buy&hold drift"),
]

WATCHLIST_SECTION = {
    ohlc.normalize_symbol(symbol): section
    for section, symbols in TREND_WATCHLIST_SECTIONS
    for symbol in symbols
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=REPO_ROOT / "database" / "trade_helper.sqlite3")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "docs" / "temp")
    parser.add_argument("--primary-min-bars", type=int, default=756)
    parser.add_argument("--cost-mult", type=float, default=1.0,
                        help="Multiply modeled cost_bps and slippage_atr (use 2 for stage 5).")
    parser.add_argument("--from-csv", action="store_true",
                        help="Skip the engine sweep and re-roll from the existing symbol/period CSVs.")
    return parser.parse_args()


# --- small stat helpers ---------------------------------------------------


def finite(values: Iterable[float | None]) -> list[float]:
    return [float(v) for v in values if v is not None and math.isfinite(float(v))]


def median(values: Iterable[float | None]) -> float | None:
    xs = finite(values)
    return statistics.median(xs) if xs else None


def mean(values: Iterable[float | None]) -> float | None:
    xs = finite(values)
    return statistics.fmean(xs) if xs else None


def share(flags: Iterable[bool]) -> float | None:
    xs = list(flags)
    return sum(1 for f in xs if f) / len(xs) if xs else None


def curve_stats(returns: list[float]) -> dict[str, float | None]:
    if len(returns) < 2:
        return {k: None for k in ("cagr", "sharpe", "max_drawdown", "calmar")}
    equity = engine.compound(returns)
    years = len(returns) / ANNUAL_PERIODS
    cagr = equity[-1] ** (1.0 / years) - 1.0 if equity[-1] > 0 and years > 0 else None
    daily_mean = statistics.fmean(returns)
    daily_std = statistics.pstdev(returns)
    max_drawdown = min(engine.drawdown_curve(equity))
    return {
        "cagr": cagr,
        "sharpe": daily_mean / daily_std * math.sqrt(ANNUAL_PERIODS) if daily_std else None,
        "max_drawdown": max_drawdown,
        "calmar": cagr / abs(max_drawdown) if cagr is not None and max_drawdown < 0 else None,
    }


def turnover_per_year(states: list[float]) -> float | None:
    if len(states) < 2:
        return None
    t = sum(abs(states[i] - states[i - 1]) for i in range(1, len(states)))
    return t / (len(states) / ANNUAL_PERIODS)


def ddred(long_dd: float | None, both_dd: float | None) -> float | None:
    if long_dd is None or both_dd is None:
        return None
    return abs(long_dd) - abs(both_dd)


# --- per-symbol computation ---------------------------------------------


def entry_lengths(group: str) -> tuple[int, int]:
    return (100, 50) if group == BOND_GROUP else (20, 10)


def build_params(base: SignalParams, group: str, direction: str, cost_mult: float) -> SignalParams:
    entry_len, _ = entry_lengths(group)
    return base.model_copy(
        update={
            "entry_len": entry_len,
            "exit_len": EXIT["exit_len"],
            "trail_mode": EXIT["trail_mode"],
            "chandelier_k": EXIT["chandelier_k"],
            "allow_long": direction in ("both", "long"),
            "allow_short": direction in ("both", "short"),
            "cost_bps": min(50.0, base.cost_bps * cost_mult),
            "slippage_atr": min(1.0, base.slippage_atr * cost_mult),
        }
    )


def compute_symbol(
    target: Target, meta: dict[str, Any], bars: list[dict[str, Any]], base: SignalParams, cost_mult: float
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    dates = [b["date"] for b in bars]
    bh = engine.buy_hold_daily(bars)
    bh_stats = curve_stats(bh)
    bh_vol = statistics.pstdev(bh[1:]) * math.sqrt(ANNUAL_PERIODS) if len(bh) > 2 else None
    dollar_vol = median(float(b["c"]) * float(b["v"]) for b in bars if b.get("v"))

    row: dict[str, Any] = {
        "symbol": target.symbol,
        "name": target.name,
        "group": target.group,
        "watchlist_section": WATCHLIST_SECTION.get(target.symbol, ""),
        "shortable": meta.get("shortable"),
        "borrow_status": meta.get("borrow_status") or "",
        "bars": len(dates),
        "first_date": dates[0],
        "last_date": dates[-1],
        "realised_vol": bh_vol,
        "dollar_volume": dollar_vol,
        "bh_cagr": bh_stats["cagr"],
        "bh_max_drawdown": bh_stats["max_drawdown"],
    }
    per_dir_daily: dict[str, tuple[list[float], list[float]]] = {}
    for d in DIRECTIONS:
        result = engine.run(bars, build_params(base, target.group, d, cost_mult))
        states = [float(x["state"]) for x in result.daily]
        rets = [float(x["strat_ret"]) for x in result.daily]
        per_dir_daily[d] = (states, rets)
        s = curve_stats(rets)
        closed = [t for t in result.trades if t["exit_date"] is not None]
        row[f"{d}_cagr"] = s["cagr"]
        row[f"{d}_sharpe"] = s["sharpe"]
        row[f"{d}_calmar"] = s["calmar"]
        row[f"{d}_max_drawdown"] = s["max_drawdown"]
        row[f"{d}_exposure"] = sum(1 for st in states if st != 0) / len(states)
        row[f"{d}_turnover"] = turnover_per_year(states)
        row[f"{d}_trades"] = len(closed)

    row["d_cagr"] = _sub(row["both_cagr"], row["long_cagr"])
    row["d_sharpe"] = _sub(row["both_sharpe"], row["long_sharpe"])
    row["d_calmar"] = _sub(row["both_calmar"], row["long_calmar"])
    row["d_ddred"] = ddred(row["long_max_drawdown"], row["both_max_drawdown"])
    row["both_beats_bh"] = _beats(row["both_cagr"], row["bh_cagr"])
    row["long_beats_bh"] = _beats(row["long_cagr"], row["bh_cagr"])

    periods: list[dict[str, Any]] = []
    for period, start, end in PERIODS:
        idx = [i for i, dt in enumerate(dates) if start <= dt <= end]
        if len(idx) < PERIOD_MIN_BARS:
            continue
        prow: dict[str, Any] = {
            "symbol": target.symbol,
            "group": target.group,
            "watchlist_section": row["watchlist_section"],
            "period": period,
            "bars": len(idx),
        }
        for d in DIRECTIONS:
            states, rets = per_dir_daily[d]
            s = curve_stats([rets[i] for i in idx])
            prow[f"{d}_sharpe"] = s["sharpe"]
            prow[f"{d}_cagr"] = s["cagr"]
            prow[f"{d}_max_drawdown"] = s["max_drawdown"]
        prow["d_sharpe"] = _sub(prow["both_sharpe"], prow["long_sharpe"])
        prow["d_cagr"] = _sub(prow["both_cagr"], prow["long_cagr"])
        prow["d_ddred"] = ddred(prow["long_max_drawdown"], prow["both_max_drawdown"])
        periods.append(prow)
    return row, periods


def _sub(a: float | None, b: float | None) -> float | None:
    return a - b if a is not None and b is not None else None


def _beats(a: float | None, b: float | None) -> bool:
    return bool(a is not None and b is not None and a > b)


# --- aggregation ------------------------------------------------------


def classify_policy(d_sharpe, d_cagr, d_ddred, short_sharpe, share_helps_sharpe) -> str:
    d_sharpe = d_sharpe or 0.0
    d_cagr = d_cagr or 0.0
    d_ddred = d_ddred or 0.0
    short_sharpe = short_sharpe or 0.0
    keeps = d_sharpe > -0.10 and (
        d_cagr > 0.02 or d_ddred > 0.01 or short_sharpe > 0.0 or (share_helps_sharpe or 0) > 0.30
    )
    drops = d_sharpe <= -0.10 and d_cagr <= 0.01 and d_ddred <= 0.01 and short_sharpe <= 0.0
    return "long/short" if keeps else ("long only" if drops else "mixed")


def summarise_subset(name: str, subset: list[dict[str, Any]]) -> dict[str, Any]:
    med_d_sharpe = median(r["d_sharpe"] for r in subset)
    med_d_cagr = median(r["d_cagr"] for r in subset)
    med_d_ddred = median(r["d_ddred"] for r in subset)
    med_short_sharpe = median(r["short_sharpe"] for r in subset)
    sh_helps_sharpe = share((r["d_sharpe"] or 0) > 0 for r in subset)
    return {
        "bucket": name,
        "n": len(subset),
        "median_d_cagr": med_d_cagr,
        "median_d_sharpe": med_d_sharpe,
        "median_d_calmar": median(r["d_calmar"] for r in subset),
        "median_d_ddred": med_d_ddred,
        "median_short_sharpe": med_short_sharpe,
        "median_short_cagr": median(r["short_cagr"] for r in subset),
        "median_bh_cagr": median(r["bh_cagr"] for r in subset),
        "share_short_helps_sharpe": sh_helps_sharpe,
        "share_short_helps_dd": share((r["d_ddred"] or 0) > 0 for r in subset),
        "share_short_helps_cagr": share((r["d_cagr"] or 0) > 0 for r in subset),
        "share_short_pos_standalone": share((r["short_sharpe"] or 0) > 0 for r in subset),
        "both_beat_bh_rate": share(r["both_beats_bh"] for r in subset),
        "long_beat_bh_rate": share(r["long_beats_bh"] for r in subset),
        "hard_to_borrow": sum(1 for r in subset if r["borrow_status"] == "hard_to_borrow"),
        "policy": classify_policy(med_d_sharpe, med_d_cagr, med_d_ddred, med_short_sharpe, sh_helps_sharpe),
    }


def group_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    contexts = [("Full universe", lambda r: True), ("Watchlist", lambda r: bool(r["watchlist_section"]))]
    contexts += [(g, lambda r, e=g: r["group"] == e) for g in GROUP_ORDER if any(r["group"] == g for r in rows)]
    for name, pred in contexts:
        subset = [r for r in rows if pred(r)]
        if subset:
            out.append({"group": name, **summarise_subset(name, subset)})
    return out


def quintile_summaries(rows: list[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
    base = [r for r in rows if (scope == "Individual equity" and r["group"] == "Individual equity")
            or (scope == "Full universe")]
    out: list[dict[str, Any]] = []
    for key, label in QUINTILE_DIMS:
        ranked = sorted((r for r in base if r.get(key) is not None), key=lambda r: r[key])
        n = len(ranked)
        if n < 25:
            continue
        for q in range(5):
            lo, hi = q * n // 5, (q + 1) * n // 5
            chunk = ranked[lo:hi]
            if not chunk:
                continue
            s = summarise_subset(f"Q{q + 1}", chunk)
            s.update({
                "scope": scope, "dimension": key, "dimension_label": label, "quintile": q + 1,
                "range_lo": chunk[0][key], "range_hi": chunk[-1][key],
            })
            out.append(s)
    return out


def period_summaries(period_rows: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    groups = ["Full universe", "Watchlist"] + [g for g in GROUP_ORDER if any(r["group"] == g for r in rows)]
    for period, *_ in PERIODS:
        prs = [p for p in period_rows if p["period"] == period]
        for g in groups:
            subset = [
                p for p in prs
                if g == "Full universe" or (g == "Watchlist" and p["watchlist_section"]) or p["group"] == g
            ]
            if not subset:
                continue
            out.append({
                "group": g,
                "period": period,
                "n": len(subset),
                "median_d_sharpe": median(p["d_sharpe"] for p in subset),
                "median_d_ddred": median(p["d_ddred"] for p in subset),
                "median_d_cagr": median(p["d_cagr"] for p in subset),
                "median_short_sharpe": median(p["short_sharpe"] for p in subset),
            })
    return out


# --- output --------------------------------------------------------


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def escaped_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True).replace("</", "<\\/")


_NON_NUMERIC = {"symbol", "name", "group", "watchlist_section", "borrow_status", "first_date", "last_date", "period"}


def _coerce(row: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if k in _NON_NUMERIC:
            out[k] = v
        elif v in ("", "None", None):
            out[k] = None
        elif v in ("True", "False"):
            out[k] = v == "True"
        else:
            try:
                out[k] = float(v)
            except ValueError:
                out[k] = v
    return out


def load_from_csv(output_dir: Path):
    with (output_dir / "direction_arch_symbol_results.csv").open(encoding="utf-8") as h:
        rows = [_coerce(r) for r in csv.DictReader(h)]
    with (output_dir / "direction_arch_period_results.csv").open(encoding="utf-8") as h:
        periods = [_coerce(r) for r in csv.DictReader(h)]
    return rows, periods


def write_report(path: Path, ctx: dict[str, Any]) -> None:
    payload = {
        "groups": ctx["group_summary"],
        "quintiles": ctx["quintiles"],
        "periods": ctx["period_summary"],
        "periodLabels": [p[0] for p in PERIODS],
        "keepList": ctx["keep_list"],
        "hardToBorrowKeep": ctx["hard_to_borrow_keep"],
    }
    data = escaped_json(payload)
    params_text = html.escape(json.dumps(ctx["base_params"].model_dump(), indent=2))
    cost_note = "normal modeled cost" if ctx["cost_mult"] == 1.0 else f"modeled cost x{ctx['cost_mult']:g} (stage 5)"
    content = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Direction architecture experiment (stage 3)</title>
<style>
:root{{--bg:#f4f6f8;--panel:#fff;--ink:#172033;--muted:#667085;--line:#d9dee8;--pos:#16803c;--neg:#c0362c;--soft:#eef2f7;--keep:#0f766e;--lo:#b45309;--mix:#6b7280}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f1217;--panel:#171b22;--ink:#e8edf5;--muted:#a7b0bf;--line:#303744;--pos:#4ade80;--neg:#fb7185;--soft:#202630;--keep:#2dd4bf;--lo:#fbbf24;--mix:#9ca3af}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:1280px;margin:auto;padding:26px}}h1{{font-size:26px;margin:0 0 4px}}h2{{font-size:19px;margin:0 0 10px}}h3{{font-size:15px;margin:16px 0 6px}}
.muted{{color:var(--muted)}}.panel{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;margin:15px 0}}
.intro{{border-left:4px solid var(--keep)}}.warn{{border-left:4px solid var(--lo)}}
.controls{{display:flex;gap:12px;flex-wrap:wrap;margin:0 0 12px}}label{{display:grid;gap:4px;color:var(--muted);font-size:13px}}
select{{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:7px;padding:6px 26px 6px 8px;font:inherit}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}}.stat{{border:1px solid var(--line);border-radius:9px;padding:11px}}.stat b{{display:block;font-size:20px}}
.table-wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;white-space:nowrap;font-variant-numeric:tabular-nums}}
th,td{{padding:7px 10px;border-bottom:1px solid var(--line);text-align:right}}th:first-child,td:first-child{{text-align:left}}
th{{position:sticky;top:0;background:var(--panel);color:var(--muted);font-weight:500}}
.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}
.pill{{font-weight:600}}.pill.keep{{color:var(--keep)}}.pill.lo{{color:var(--lo)}}.pill.mix{{color:var(--mix)}}
pre{{overflow:auto;background:var(--soft);padding:11px;border-radius:8px}}code{{font-family:ui-monospace,Consolas,monospace}}ul{{margin:6px 0;padding-left:20px}}
</style></head><body><main>
<h1>Direction architecture experiment &middot; stage 3</h1>
<div class="muted">Disposable research &middot; generated {time.strftime('%Y-%m-%d %H:%M:%S')} &middot; SQLite opened read-only &middot; {cost_note}</div>

<section class="panel intro">
<h2>Isolation contract</h2>
<p>Frozen: stage 1 entry cluster (Bond ETFs 100/50, else 20/10) and the stage 2 exit <code>c3_d20</code> (Chandelier 3 ATR trail + Donchian-20 reversal backstop + initial 2 ATR stop). Only the direction policy moves. Each symbol runs <code>both</code>, <code>long</code>, and <code>short</code> (short leg standalone).</p>
<p><b>Delta = both - long</b> is the short side's marginal contribution: positive means adding the short leg helped. <b>short-only Sharpe/CAGR</b> is the standalone short leg - it separates &ldquo;the short entry rule is weak&rdquo; from &ldquo;these names simply rose&rdquo;. The <b>own buy&amp;hold drift</b> quintiles are the explicit de-bias control.</p>
<p><b>Read column</b>: <i>long/short</i> when &Delta;Sharpe &gt; -0.10 and the short side still adds value (&Delta;CAGR &gt; 2pp, or &Delta;DD-reduction &gt; 1pp, or standalone short Sharpe &gt; 0, or &gt;30&#37; of members improve on Sharpe); <i>long only</i> when &Delta;Sharpe &le; -0.10 with no CAGR/DD gain and a negative standalone short; <i>mixed</i> otherwise.</p>
</section>

<section class="panel">
<div class="stats">
<div class="stat"><span>Symbols</span><b>{ctx['computed']}</b><small>{ctx['skipped']} skipped</small></div>
<div class="stat"><span>Engine runs</span><b>{ctx['computed'] * 3:,}</b><small>3 direction policies</small></div>
<div class="stat"><span>Primary cohort</span><b>{ctx['n_primary']}</b><small>&ge; {ctx['min_bars']} obs</small></div>
<div class="stat"><span>Hard to borrow</span><b>{ctx['n_hard_to_borrow']}</b><small>of the active equities</small></div>
<div class="stat"><span>Compute time</span><b>{ctx['elapsed']:.1f}s</b></div>
</div>
<p class="muted">Config base: {html.escape(ctx['config_name'])}. Universe has no illiquid small caps: the least-liquid active name still trades about ${ctx['min_dollar_vol_m']:.0f}M/day.</p>
<details><summary>Shared parameters</summary><pre><code>{params_text}</code></pre></details>
</section>

<section class="panel warn">
<h2>Interpretation limits</h2>
<ul>
<li>Today's active universe: current-membership and survivor/selection bias (the drift quintiles are the control for it).</li>
<li>Borrow fees, borrow availability, and short funding are not modelled; <code>borrow_status</code> is shown but not charged.</li>
<li>Crypto is BTC and ETH only (n=1 each); read them as anecdotes, not a sleeve.</li>
</ul>
</section>

<section class="panel">
<h2>1. Short-side contribution by asset class</h2>
<div id="group-table" class="table-wrap"></div>
<p id="group-note" class="muted"></p>
</section>

<section class="panel">
<h2>2. De-bias control &mdash; Individual-equity quintiles</h2>
<div class="controls"><label>Dimension<select id="q-dim"></select></label></div>
<p class="muted">If the short side only hurts in the high-drift quintiles and is neutral or positive in the low-drift / high-volatility quintiles, "short is a drag" is mostly a survivorship artifact. If it hurts even in the bottom drift quintile, the short entry rule is genuinely weak.</p>
<div id="q-table" class="table-wrap"></div>
</section>

<section class="panel">
<h2>3. Stability across periods</h2>
<div class="controls"><label>Scope<select id="p-group"></select></label></div>
<div id="p-table" class="table-wrap"></div>
</section>

</main>
<script>
const DATA={data};
const fmt=(v,d=2)=>v==null||!Number.isFinite(+v)?'\\u2014':(+v).toFixed(d);
const pct=(v,d=1)=>v==null||!Number.isFinite(+v)?'\\u2014':(+v*100).toFixed(d)+'%';
const cls=v=>v==null?'':(+v>=0?'pos':'neg');
const pill=p=>`<span class="pill ${{p==='long/short'?'keep':p==='long only'?'lo':'mix'}}">${{p}}</span>`;

function groupTable(){{
 let h='<table><thead><tr><th>Scope</th><th>n</th><th>&Delta;CAGR</th><th>&Delta;Sharpe</th><th>&Delta;Calmar</th><th>&Delta;DD red</th><th>short-only Sharpe</th><th>short-only CAGR</th><th>short&gt;0 standalone</th><th>short helps Sharpe</th><th>short helps DD</th><th>hard-to-borrow</th><th>read</th></tr></thead><tbody>';
 DATA.groups.forEach(r=>{{
  h+=`<tr><td>${{r.group}}</td><td>${{r.n}}</td>`
   +`<td class="${{cls(r.median_d_cagr)}}">${{pct(r.median_d_cagr)}}</td>`
   +`<td class="${{cls(r.median_d_sharpe)}}">${{fmt(r.median_d_sharpe)}}</td>`
   +`<td class="${{cls(r.median_d_calmar)}}">${{fmt(r.median_d_calmar)}}</td>`
   +`<td class="${{cls(r.median_d_ddred)}}">${{pct(r.median_d_ddred)}}</td>`
   +`<td class="${{cls(r.median_short_sharpe)}}">${{fmt(r.median_short_sharpe)}}</td>`
   +`<td class="${{cls(r.median_short_cagr)}}">${{pct(r.median_short_cagr)}}</td>`
   +`<td>${{pct(r.share_short_pos_standalone)}}</td>`
   +`<td>${{pct(r.share_short_helps_sharpe)}}</td>`
   +`<td>${{pct(r.share_short_helps_dd)}}</td>`
   +`<td>${{r.hard_to_borrow||''}}</td>`
   +`<td>${{pill(r.policy)}}</td></tr>`;
 }});
 document.getElementById('group-table').innerHTML=h+'</tbody></table>';
 const keep=DATA.keepList.length?DATA.keepList.join(', '):'none';
 const htb=DATA.hardToBorrowKeep.length?` Of those, hard-to-borrow (not a practical long/short candidate): ${{DATA.hardToBorrowKeep.join(', ')}}.`:'';
 document.getElementById('group-note').textContent=`Keep long/short: ${{keep}}.${{htb}} Everything else defaults to long only.`;
}}

function qTable(){{
 const dim=document.getElementById('q-dim').value;
 const rows=DATA.quintiles.filter(r=>r.dimension===dim);
 let h='<table><thead><tr><th>Quintile</th><th>n</th><th>range</th><th>median B&amp;H CAGR</th><th>&Delta;CAGR</th><th>&Delta;Sharpe</th><th>&Delta;DD red</th><th>short-only Sharpe</th><th>short&gt;0 standalone</th><th>read</th></tr></thead><tbody>';
 rows.forEach(r=>{{
  const rng=dim==='dollar_volume'?`$${{(r.range_lo/1e6).toFixed(0)}}\\u2013${{(r.range_hi/1e6).toFixed(0)}}M`
    :dim==='bh_cagr'?`${{pct(r.range_lo)}}\\u2013${{pct(r.range_hi)}}`
    :`${{pct(r.range_lo)}}\\u2013${{pct(r.range_hi)}}`;
  h+=`<tr><td>${{r.dimension_label}} ${{r.quintile}}</td><td>${{r.n}}</td><td>${{rng}}</td>`
   +`<td>${{pct(r.median_bh_cagr)}}</td>`
   +`<td class="${{cls(r.median_d_cagr)}}">${{pct(r.median_d_cagr)}}</td>`
   +`<td class="${{cls(r.median_d_sharpe)}}">${{fmt(r.median_d_sharpe)}}</td>`
   +`<td class="${{cls(r.median_d_ddred)}}">${{pct(r.median_d_ddred)}}</td>`
   +`<td class="${{cls(r.median_short_sharpe)}}">${{fmt(r.median_short_sharpe)}}</td>`
   +`<td>${{pct(r.share_short_pos_standalone)}}</td>`
   +`<td>${{pill(r.policy)}}</td></tr>`;
 }});
 document.getElementById('q-table').innerHTML=h+'</tbody></table>';
}}

function pTable(){{
 const g=document.getElementById('p-group').value;
 const rows=DATA.periods.filter(r=>r.group===g);
 let h='<table><thead><tr><th>Period</th><th>n</th><th>&Delta;Sharpe</th><th>&Delta;DD red</th><th>&Delta;CAGR</th><th>short-only Sharpe</th></tr></thead><tbody>';
 DATA.periodLabels.forEach(p=>{{
  const r=rows.find(x=>x.period===p);
  if(!r)return;
  h+=`<tr><td>${{p}}</td><td>${{r.n}}</td>`
   +`<td class="${{cls(r.median_d_sharpe)}}">${{fmt(r.median_d_sharpe)}}</td>`
   +`<td class="${{cls(r.median_d_ddred)}}">${{pct(r.median_d_ddred)}}</td>`
   +`<td class="${{cls(r.median_d_cagr)}}">${{pct(r.median_d_cagr)}}</td>`
   +`<td class="${{cls(r.median_short_sharpe)}}">${{fmt(r.median_short_sharpe)}}</td></tr>`;
 }});
 document.getElementById('p-table').innerHTML=h+'</tbody></table>';
}}

[...new Set(DATA.quintiles.map(r=>r.dimension))].forEach(dim=>{{
 const o=document.createElement('option');o.value=dim;
 o.textContent=(DATA.quintiles.find(r=>r.dimension===dim)||{{}}).dimension_label||dim;
 document.getElementById('q-dim').appendChild(o);
}});
[...new Set(DATA.periods.map(r=>r.group))].forEach(g=>{{
 const o=document.createElement('option');o.value=g;o.textContent=g;document.getElementById('p-group').appendChild(o);
}});
document.getElementById('q-dim').addEventListener('change',qTable);
document.getElementById('p-group').addEventListener('change',pTable);
groupTable();qTable();pTable();
</script>
</body></html>'''
    path.write_text(content, encoding="utf-8")


def asset_meta(conn) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in conn.execute("SELECT symbol, shortable, borrow_status FROM assets WHERE active=1"):
        out[ohlc.normalize_symbol(r["symbol"])] = {
            "shortable": r["shortable"], "borrow_status": r["borrow_status"],
        }
    return out


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    sfx = "" if args.cost_mult == 1.0 else f"_cost{args.cost_mult:g}"
    outputs = {
        "symbols": args.output_dir / f"direction_arch_symbol_results{sfx}.csv",
        "periods": args.output_dir / f"direction_arch_period_results{sfx}.csv",
        "summary": args.output_dir / f"direction_arch_summary{sfx}.json",
        "report": args.output_dir / f"direction_arch_report{sfx}.html",
    }
    skipped = 0
    errors: list[dict[str, str]] = []
    with read_only_connection(args.database) as conn:
        config_name, base_params = active_config(conn)
        latest_run = latest_universe_run(conn)
        targets = universe_targets(conn)
        meta = asset_meta(conn)
        if args.from_csv:
            rows, period_rows = load_from_csv(args.output_dir)
            print(f"Reloaded {len(rows)} symbol rows from CSV; skipping compute", flush=True)
        else:
            rows, period_rows = [], []
            for i, target in enumerate(targets, start=1):
                try:
                    bars = ohlc.load_ohlc(conn, target.symbol)
                    if len(bars) < MIN_ENGINE_BARS:
                        skipped += 1
                    else:
                        row, prs = compute_symbol(target, meta.get(target.symbol, {}), bars, base_params, args.cost_mult)
                        rows.append(row)
                        period_rows.extend(prs)
                except Exception as exc:
                    errors.append({"symbol": target.symbol, "error": f"{type(exc).__name__}: {exc}"})
                if i % 25 == 0 or i == len(targets):
                    print(f"Computed {i}/{len(targets)} targets", flush=True)

    if not rows:
        raise RuntimeError("No symbols had enough bars")

    primary = [r for r in rows if r["bars"] >= args.primary_min_bars]
    rows.sort(key=lambda r: r["symbol"])
    period_rows.sort(key=lambda r: (r["symbol"], r["period"]))
    if not args.from_csv:
        write_csv(outputs["symbols"], rows)
        write_csv(outputs["periods"], period_rows)

    group_summary = group_summaries(primary)
    quintiles = quintile_summaries(primary, "Individual equity") + quintile_summaries(primary, "Full universe")
    period_summary = period_summaries(period_rows, primary)

    keep_list = [g["group"] for g in group_summary
                 if g["policy"] == "long/short" and g["group"] not in ("Full universe", "Watchlist")]
    hard_to_borrow_keep = sorted(
        r["symbol"] for r in primary
        if r["borrow_status"] == "hard_to_borrow" and r["group"] in keep_list
    )
    min_dollar_vol_m = min((r["dollar_volume"] for r in primary if r.get("dollar_volume")), default=0.0) / 1e6

    ctx = {
        "base_params": base_params, "config_name": config_name, "cost_mult": args.cost_mult,
        "computed": len(rows), "skipped": skipped + len(errors), "n_primary": len(primary),
        "min_bars": args.primary_min_bars, "elapsed": time.perf_counter() - started,
        "n_hard_to_borrow": sum(1 for r in rows if r["borrow_status"] == "hard_to_borrow"),
        "min_dollar_vol_m": min_dollar_vol_m,
        "group_summary": group_summary, "quintiles": quintiles, "period_summary": period_summary,
        "keep_list": keep_list, "hard_to_borrow_keep": hard_to_borrow_keep,
    }

    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "stage": "3 - direction architecture (isolated; entry cluster + c3_d20 exit frozen)",
        "database": str(args.database.resolve()),
        "config_name": config_name,
        "shared_params": base_params.model_dump(),
        "frozen_exit": EXIT,
        "cost_mult": args.cost_mult,
        "entry_cluster": {"Bond ETF": "100/50", "default": "20/10"},
        "directions": list(DIRECTIONS),
        "periods": [{"label": p[0], "start": p[1], "end": p[2]} for p in PERIODS],
        "primary_min_bars": args.primary_min_bars,
        "targets": len(targets),
        "computed": len(rows),
        "skipped_under_minimum": skipped,
        "errors": errors,
        "engine_runs": len(rows) * len(DIRECTIONS),
        "latest_universe_run": latest_run,
        "group_summary": group_summary,
        "quintile_summary": quintiles,
        "period_summary": period_summary,
        "keep_long_short": keep_list,
        "hard_to_borrow_in_keep": hard_to_borrow_keep,
    }
    outputs["summary"].write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(outputs["report"], ctx)
    for output in (outputs.values() if not args.from_csv else [outputs["summary"], outputs["report"]]):
        print(f"Wrote {output}")
    if errors:
        print(f"Completed with {len(errors)} symbol errors", file=sys.stderr)


if __name__ == "__main__":
    main()
