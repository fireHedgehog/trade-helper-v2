"""Stage 4 - disposable portfolio-aggregation experiment.

The signal rules are frozen (stages 1-3):

- entry: Bond ETFs 100/50, everything else 20/10
- exit:  c3_d20  (Chandelier 3 ATR trail + Donchian-20 reversal + initial 2 ATR)
- direction: long only, except Bond ETFs and Bitcoin which are long/short

This turns the per-symbol daily signal into ONE cross-asset benchmark equity
curve by adding a risk layer, evaluated over a pre-declared rule ladder. It is a
robustness demonstration, NOT an optimisation - nothing here retouches the
signal.

Signal -> P&L with no re-simulation: the engine already returns a daily costed
one-unit strategy return `strat_ret_i(t)`. The portfolio holds `w_i(t)` units:

    portfolio_ret(t) = sum_i w_i(t-1) * strat_ret_i(t) - rebal_cost(t)

`w_i(t)` uses only data through t-1. `rebal_cost` is booked on scheduled
rebalance days as `cost_bps * sum_i |dw_i|`.

Rule ladder (each adds one layer):

    P0   equal-notional, split 100% gross across on-signals
    P1   inverse-vol weights, 100% gross
    P2   P1 * portfolio vol-target scalar k(t) = clip(vt / trailing_vol, 0, k_max)
    P3   P2 + per-position cap w_max + gross cap G_max
    P4   fixed sleeve risk budgets (equity/bond/commodity/crypto/other),
         inverse-vol within sleeve, then P3 caps        <- candidate canonical
    P4c  P4 + trailing-correlation crowding haircut       <- robustness only

Reported at k_max in {1.0 unlevered, 2.0 moderate}, on two universes (full; and
"restricted" = drop single-name equities, keep ETFs + crypto + watchlist names)
as the survivorship control. Benchmarks: SPY, 60/40 SPY/AGG, equal-weight
buy&hold. Crash windows: 2018 Q4, 2020 Feb-Apr, 2022.

    python backend/temp/portfolio_aggregation_experiment.py
    python backend/temp/portfolio_aggregation_experiment.py --from-cache
    python backend/temp/portfolio_aggregation_experiment.py --cost-mult 2
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import pickle
import statistics
import sys
import time
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
from turtle_vs_buyhold import (  # noqa: E402
    Target,
    active_config,
    latest_universe_run,
    read_only_connection,
    universe_targets,
)

ANN = 252.0
MIN_ENGINE_BARS = 200
VOL_MIN_OBS = 20
MIN_START_SYMBOLS = 30
LONG_SHORT_GROUPS = {"Bond ETF", "Bitcoin"}

SLEEVE_OF_GROUP = {
    "Individual equity": "equity",
    "Broad index ETF": "equity",
    "Factor/style ETF": "equity",
    "Sector ETF": "equity",
    "Thematic/industry ETF": "equity",
    "Bond ETF": "bond",
    "Commodity ETF": "commodity",
    "Bitcoin": "crypto",
    "Crypto": "crypto",
}
SLEEVE_BUDGET = {"equity": 0.50, "bond": 0.20, "commodity": 0.15, "crypto": 0.05, "other": 0.10}
SLEEVE_ORDER = ["equity", "bond", "commodity", "crypto", "other"]

CRASH_WINDOWS = [
    ("2018 Q4", "2018-10-01", "2018-12-31"),
    ("2020 COVID", "2020-02-15", "2020-04-30"),
    ("2022", "2022-01-01", "2022-12-31"),
]
PERIODS = [
    ("2016-2019", "2016-01-01", "2019-12-31"),
    ("2020-2022", "2020-01-01", "2022-12-31"),
    ("2023-present", "2023-01-01", "9999-12-31"),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", type=Path, default=REPO_ROOT / "database" / "trade_helper.sqlite3")
    p.add_argument("--output-dir", type=Path, default=REPO_ROOT / "docs" / "temp")
    p.add_argument("--vol-target", type=float, default=0.12)
    p.add_argument("--vol-lookback", type=int, default=60)
    p.add_argument("--w-max", type=float, default=0.10, help="Max single position, fraction of NAV.")
    p.add_argument("--rebalance", default="weekly", choices=["daily", "weekly", "monthly"])
    p.add_argument("--cost-mult", type=float, default=1.0)
    p.add_argument("--from-cache", action="store_true",
                   help="Reload the per-symbol engine output from the pickle cache; skip the engine.")
    return p.parse_args()


# --- metric helpers -----------------------------------------------------


def finite(xs: Iterable[float | None]) -> list[float]:
    return [float(v) for v in xs if v is not None and math.isfinite(float(v))]


def compound(rets: list[float]) -> list[float]:
    eq, out = 1.0, []
    for r in rets:
        eq *= 1.0 + r
        out.append(eq)
    return out


def drawdown_curve(equity: list[float]) -> list[float]:
    peak, out = -math.inf, []
    for e in equity:
        peak = max(peak, e)
        out.append(e / peak - 1.0 if peak > 0 else 0.0)
    return out


def rolling_min_compound(rets: list[float], window: int) -> float | None:
    if len(rets) < window:
        return None
    worst = math.inf
    acc = compound(rets)
    acc = [1.0] + acc
    for i in range(window, len(acc)):
        worst = min(worst, acc[i] / acc[i - window] - 1.0)
    return worst if worst != math.inf else None


def metrics(rets: list[float], gross: list[float], net: list[float]) -> dict[str, Any]:
    if len(rets) < 30:
        return {}
    eq = compound(rets)
    years = len(rets) / ANN
    cagr = eq[-1] ** (1.0 / years) - 1.0 if eq[-1] > 0 else None
    mean, sd = statistics.fmean(rets), statistics.pstdev(rets)
    downs = [r for r in rets if r < 0]
    dsd = statistics.pstdev(downs) if len(downs) > 2 else None
    dd = drawdown_curve(eq)
    mdd = min(dd)
    ulcer = math.sqrt(statistics.fmean([d * d for d in dd])) * 100.0
    return {
        "cagr": cagr,
        "vol_annual": sd * math.sqrt(ANN),
        "sharpe": mean / sd * math.sqrt(ANN) if sd else None,
        "sortino": mean / dsd * math.sqrt(ANN) if dsd else None,
        "max_drawdown": mdd,
        "calmar": cagr / abs(mdd) if cagr is not None and mdd < 0 else None,
        "ulcer_index": ulcer,
        "worst_1d": min(rets),
        "worst_5d": rolling_min_compound(rets, 5),
        "worst_252d": rolling_min_compound(rets, 252),
        "pct_underwater": sum(1 for d in dd if d < 0) / len(dd),
        "avg_gross": statistics.fmean(gross) if gross else None,
        "avg_net": statistics.fmean(net) if net else None,
    }


def window_drawdown(dates: list[str], rets: list[float], start: str, end: str) -> float | None:
    idx = [i for i, d in enumerate(dates) if start <= d <= end]
    if len(idx) < 5:
        return None
    seg = compound([rets[i] for i in idx])
    return min(drawdown_curve(seg))


def period_metrics(dates: list[str], rets: list[float], gross: list[float], net: list[float]) -> list[dict[str, Any]]:
    out = []
    for label, s, e in PERIODS:
        idx = [i for i, d in enumerate(dates) if s <= d <= e]
        if len(idx) < 60:
            continue
        m = metrics([rets[i] for i in idx], [gross[i] for i in idx], [net[i] for i in idx])
        if m:
            out.append({"period": label, **m})
    return out


# --- signal layer -----------------------------------------------------


def frozen_params(base: SignalParams, group: str, cost_mult: float) -> SignalParams:
    entry_len = 100 if group == "Bond ETF" else 20
    return base.model_copy(update={
        "entry_len": entry_len,
        "exit_len": 20,
        "trail_mode": "chandelier",
        "chandelier_k": 3.0,
        "allow_long": True,
        "allow_short": group in LONG_SHORT_GROUPS,
        "cost_bps": min(50.0, base.cost_bps * cost_mult),
        "slippage_atr": min(1.0, base.slippage_atr * cost_mult),
    })


def build_signal_cache(conn, targets: list[Target], base: SignalParams, cost_mult: float) -> dict[str, Any]:
    per_symbol: dict[str, dict[str, Any]] = {}
    skipped = 0
    for i, t in enumerate(targets, 1):
        try:
            bars = ohlc.load_ohlc(conn, t.symbol)
        except Exception:
            bars = []
        if len(bars) < MIN_ENGINE_BARS:
            skipped += 1
            continue
        res = engine.run(bars, frozen_params(base, t.group, cost_mult))
        if not res.daily:
            skipped += 1
            continue
        dates = [d["date"] for d in res.daily]
        uret = engine.buy_hold_daily(bars)
        per_symbol[t.symbol] = {
            "group": t.group,
            "sleeve": SLEEVE_OF_GROUP.get(t.group, "other"),
            "dates": dates,
            "strat_ret": [float(d["strat_ret"]) for d in res.daily],
            "state": [int(d["state"]) for d in res.daily],
            "uret": [float(x) for x in uret],
        }
        if i % 50 == 0 or i == len(targets):
            print(f"  engine {i}/{len(targets)}", flush=True)
    return {"per_symbol": per_symbol, "skipped": skipped}


# --- alignment ------------------------------------------------------


class Aligned:
    """Everything on one master calendar, pre-indexed for a fast simulate loop."""

    def __init__(self, per_symbol: dict[str, Any], lookback: int):
        self.lookback = lookback
        all_dates = sorted({d for s in per_symbol.values() for d in s["dates"]})
        self.dates = all_dates
        self.idx_of = {d: i for i, d in enumerate(all_dates)}
        n = len(all_dates)
        self.symbols = sorted(per_symbol)
        self.group = {s: per_symbol[s]["group"] for s in self.symbols}
        self.sleeve = {s: per_symbol[s]["sleeve"] for s in self.symbols}

        self.strat: dict[str, list[float]] = {}
        self.state: dict[str, list[int]] = {}
        self.sigma: dict[str, list[float | None]] = {}   # trailing ann vol as of START of day t
        self.uret: dict[str, list[float]] = {}
        for s, rec in per_symbol.items():
            strat = [0.0] * n
            state = [0] * n
            uret = [0.0] * n
            sig = [None] * n
            hist: list[float] = []
            for j, d in enumerate(rec["dates"]):
                t = self.idx_of[d]
                strat[t] = rec["strat_ret"][j]
                state[t] = rec["state"][j]
                uret[t] = rec["uret"][j]
                sig[t] = self._vol(hist)          # uses returns strictly before day t
                hist.append(rec["uret"][j])
                if len(hist) > lookback:
                    hist.pop(0)
            self.strat[s], self.state[s], self.uret[s], self.sigma[s] = strat, state, uret, sig

        # equal-weight underlying universe return per day (benchmark + crowding base)
        self.ew_uret = [0.0] * n
        for t in range(n):
            live = [self.uret[s][t] for s in self.symbols if _has_bar(per_symbol[s], all_dates[t])]
            self.ew_uret[t] = statistics.fmean(live) if live else 0.0

        # first day with enough sized names to start the book
        self.start = next(
            (t for t in range(n) if sum(1 for s in self.symbols if self.sigma[s][t]) >= MIN_START_SYMBOLS),
            n,
        )

    def _vol(self, hist: list[float]) -> float | None:
        if len(hist) < VOL_MIN_OBS:
            return None
        sd = statistics.pstdev(hist)
        return sd * math.sqrt(ANN) if sd > 0 else None


def _has_bar(rec: dict[str, Any], date: str) -> bool:
    return rec["dates"][0] <= date <= rec["dates"][-1]


# --- weight construction --------------------------------------------


def _cap_and_gross(w: dict[str, float], w_max: float, g_max: float) -> dict[str, float]:
    """Clip each |w_i| <= w_max, hand the removed weight back to uncapped names so
    the incoming gross is preserved, then clamp total gross <= g_max."""
    if not w:
        return w
    target = sum(abs(v) for v in w.values())
    for _ in range(4):
        capped = {s: math.copysign(min(abs(v), w_max), v) for s, v in w.items()}
        deficit = target - sum(abs(v) for v in capped.values())
        room = {s: w_max - abs(v) for s, v in capped.items() if abs(v) < w_max - 1e-12}
        tot = sum(room.values())
        if deficit <= 1e-9 or tot <= 1e-9:
            w = capped
            break
        w = dict(capped)
        for s, rm in room.items():
            w[s] += math.copysign(deficit * rm / tot, w[s])
    gross = sum(abs(v) for v in w.values())
    if g_max > 0 and gross > g_max:
        w = {s: v * g_max / gross for s, v in w.items()}
    return w


def make_weights(
    A: Aligned, subset: list[str], t: int, variant: str, k: float, w_max: float, crowd: dict[str, list[float | None]] | None,
) -> dict[str, float]:
    on = [s for s in subset if A.state[s][t] != 0 and A.sigma[s][t]]
    if not on:
        return {}
    sign = {s: (1.0 if A.state[s][t] > 0 else -1.0) for s in on}

    if variant == "P0":
        return {s: sign[s] / len(on) for s in on}

    if variant in ("P1", "P2", "P3"):
        inv = {s: 1.0 / A.sigma[s][t] for s in on}
        z = sum(inv.values())
        w = {s: sign[s] * inv[s] / z for s in on}          # gross 1.0
        if variant == "P1":
            return w
        w = {s: v * k for s, v in w.items()}               # P2: vol-target scalar
        if variant == "P2":
            return w
        return _cap_and_gross(w, w_max, k or 1.0)          # P3 caps, gross <= k

    # P4 / P4c : fixed sleeve risk budgets
    by_sleeve: dict[str, list[str]] = {sl: [] for sl in SLEEVE_ORDER}
    for s in on:
        by_sleeve[A.sleeve[s]].append(s)
    active = [sl for sl in SLEEVE_ORDER if by_sleeve[sl]]
    if not active:
        return {}
    budget_z = sum(SLEEVE_BUDGET[sl] for sl in active)
    w: dict[str, float] = {}
    for sl in active:
        names = by_sleeve[sl]
        inv = {s: 1.0 / A.sigma[s][t] for s in names}
        z = sum(inv.values())
        target = SLEEVE_BUDGET[sl] / budget_z               # sleeve share of 100% gross
        for s in names:
            w[s] = sign[s] * target * inv[s] / z
    if variant == "P4c" and crowd is not None:
        for s in list(w):
            c = crowd[s][t]
            if c and c > 0:
                w[s] /= 1.0 + c
        z = sum(abs(v) for v in w.values())
        if z > 0:
            w = {s: v / z for s, v in w.items()}
    w = {s: v * k for s, v in w.items()}
    return _cap_and_gross(w, w_max, k or 1.0)


REBALANCE_FIRST_OF = {"weekly": "week", "monthly": "month"}


def rebalance_days(dates: list[str], start: int, mode: str) -> set[int]:
    if mode == "daily":
        return set(range(start, len(dates)))
    out = {start}
    for t in range(start + 1, len(dates)):
        prev, cur = dates[t - 1], dates[t]
        if mode == "weekly":
            iso_prev = _isoweek(prev)
            iso_cur = _isoweek(cur)
            if iso_cur != iso_prev:
                out.add(t)
        else:  # monthly
            if cur[:7] != prev[:7]:
                out.add(t)
    return out


def _isoweek(date: str) -> tuple[int, int]:
    import datetime
    y, m, d = map(int, date.split("-"))
    iso = datetime.date(y, m, d).isocalendar()
    return (iso[0], iso[1])


def crowding_series(A: Aligned) -> dict[str, list[float | None]]:
    """Trailing Pearson corr of each symbol's underlying return to the equal-weight
    book, as of the start of each day. O(1) rolling update per day."""
    lb = A.lookback
    n = len(A.dates)
    ew = A.ew_uret
    out: dict[str, list[float | None]] = {}
    for s in A.symbols:
        u = A.uret[s]
        series: list[float | None] = [None] * n
        sx = sy = sxx = syy = sxy = 0.0
        buf: list[tuple[float, float]] = []
        for t in range(n):
            series[t] = _corr_from_sums(len(buf), sx, sy, sxx, syy, sxy) if len(buf) >= VOL_MIN_OBS else None
            if u[t] != 0.0:  # only count days the symbol actually traded
                x, y = u[t], ew[t]
                buf.append((x, y))
                sx += x; sy += y; sxx += x * x; syy += y * y; sxy += x * y
                if len(buf) > lb:
                    ox, oy = buf.pop(0)
                    sx -= ox; sy -= oy; sxx -= ox * ox; syy -= oy * oy; sxy -= ox * oy
        out[s] = series
    return out


def _corr_from_sums(m: int, sx: float, sy: float, sxx: float, syy: float, sxy: float) -> float | None:
    if m < 3:
        return None
    cov = sxy - sx * sy / m
    vx = sxx - sx * sx / m
    vy = syy - sy * sy / m
    if vx <= 0 or vy <= 0:
        return None
    return cov / math.sqrt(vx * vy)


# --- simulation ------------------------------------------------------


def simulate(
    A: Aligned, subset: list[str], variant: str, k_max: float, vt: float, w_max: float,
    rebal: set[int], cost_bps: float, crowd: dict[str, list[float | None]] | None,
) -> dict[str, list[float]]:
    n = len(A.dates)
    port_ret = [0.0] * n
    gross = [0.0] * n
    net = [0.0] * n
    w: dict[str, float] = {}
    hist: list[float] = []
    cost_frac = cost_bps / 1e4
    for t in range(A.start, n):
        if t in rebal:
            if variant in ("P0", "P1"):
                k = 1.0
            else:
                if len(hist) >= VOL_MIN_OBS:
                    sd = statistics.pstdev(hist[-A.lookback:])
                    tv = sd * math.sqrt(ANN)
                    k = min(k_max, vt / tv) if tv > 0 else k_max
                    k = max(0.0, k)
                else:
                    k = 1.0
            new_w = make_weights(A, subset, t, variant, k, w_max, crowd)
            turn = sum(abs(new_w.get(s, 0.0) - w.get(s, 0.0)) for s in set(new_w) | set(w))
            w = new_w
            rc = cost_frac * turn
        else:
            rc = 0.0
        r = sum(wt * A.strat[s][t] for s, wt in w.items()) - rc
        port_ret[t] = r
        hist.append(r)
        gross[t] = sum(abs(v) for v in w.values())
        net[t] = sum(v for v in w.values())
    return {"ret": port_ret[A.start:], "gross": gross[A.start:], "net": net[A.start:],
            "dates": A.dates[A.start:]}


# --- benchmarks -----------------------------------------------------


def series_uret(conn, symbol: str, master: list[str]) -> list[float]:
    try:
        bars = ohlc.load_ohlc(conn, symbol)
    except Exception:
        return [0.0] * len(master)
    by_date = {}
    prev = None
    for b in bars:
        if prev is not None:
            by_date[b["date"]] = float(b["c"]) / prev - 1.0
        prev = float(b["c"])
    return [by_date.get(d, 0.0) for d in master]


# --- output --------------------------------------------------------


def write_report(path: Path, payload: dict[str, Any], base_params: SignalParams, meta: dict[str, Any]) -> None:
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).replace("</", "<\\/")
    params_text = html.escape(json.dumps(base_params.model_dump(), indent=2))
    cost_note = "normal cost" if meta["cost_mult"] == 1.0 else f"cost x{meta['cost_mult']:g} (stage 5)"
    content = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Portfolio aggregation experiment (stage 4)</title>
<style>
:root{{--bg:#f4f6f8;--panel:#fff;--ink:#172033;--muted:#667085;--line:#d9dee8;--pos:#16803c;--neg:#c0362c;--soft:#eef2f7;--accent:#2563eb}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f1217;--panel:#171b22;--ink:#e8edf5;--muted:#a7b0bf;--line:#303744;--pos:#4ade80;--neg:#fb7185;--soft:#202630;--accent:#60a5fa}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:1280px;margin:auto;padding:26px}}h1{{font-size:26px;margin:0 0 4px}}h2{{font-size:19px;margin:0 0 10px}}h3{{font-size:15px;margin:14px 0 6px}}
.muted{{color:var(--muted)}}.panel{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;margin:15px 0}}
.intro{{border-left:4px solid var(--accent)}}.warn{{border-left:4px solid #d97706}}
.controls{{display:flex;gap:12px;flex-wrap:wrap;margin:0 0 12px}}label{{display:grid;gap:4px;color:var(--muted);font-size:13px}}
select{{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:7px;padding:6px 26px 6px 8px;font:inherit}}
.table-wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;white-space:nowrap;font-variant-numeric:tabular-nums}}
th,td{{padding:7px 10px;border-bottom:1px solid var(--line);text-align:right}}th:first-child,td:first-child{{text-align:left}}
th{{position:sticky;top:0;background:var(--panel);color:var(--muted);font-weight:500}}
.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}.hi{{font-weight:700}}
svg{{width:100%;height:auto;display:block}}.chart .grid{{stroke:var(--line);fill:none}}.chart text{{fill:var(--muted);font-size:11px}}
pre{{overflow:auto;background:var(--soft);padding:11px;border-radius:8px}}code{{font-family:ui-monospace,Consolas,monospace}}ul{{margin:6px 0;padding-left:20px}}
</style></head><body><main>
<h1>Portfolio aggregation experiment &middot; stage 4</h1>
<div class="muted">Disposable research &middot; {time.strftime('%Y-%m-%d %H:%M:%S')} &middot; SQLite read-only &middot; {cost_note} &middot; vol target {meta['vol_target']*100:.0f}% &middot; {meta['rebalance']} rebalance</div>

<section class="panel intro">
<h2>What this is</h2>
<p>The frozen per-symbol signal (entry cluster, <code>c3_d20</code> exit, long-only except Bond ETFs + BTC) is turned into one equity curve by a rule ladder. Each variant adds one risk layer; the goal is the <b>simplest</b> variant that captures the tail benefit, not the highest CAGR. Portfolio return = &Sigma; w<sub>i</sub>(t-1)&middot;strat_ret<sub>i</sub>(t) &minus; rebalance cost; weights use only past data.</p>
<ul>
<li><b>P0</b> equal-notional &middot; <b>P1</b> inverse-vol &middot; <b>P2</b> +vol-target scalar &middot; <b>P3</b> +position/gross caps &middot; <b>P4</b> +fixed sleeve risk budgets &middot; <b>P4c</b> +correlation haircut (robustness)</li>
<li>Reported at <b>k_max = 1.0</b> (unlevered) and <b>k_max = 2.0</b> (moderate). Two universes: full, and restricted (no single-name equities) as the survivorship control.</li>
</ul>
</section>

<section class="panel">
<h2>1. Rule ladder</h2>
<div class="controls">
<label>Universe<select id="lad-univ"></select></label>
<label>Leverage<select id="lad-k"></select></label>
</div>
<div id="ladder" class="table-wrap"></div>
<p class="muted">Bold = best in column. "vol hit" is realised annualised vol vs the {meta['vol_target']*100:.0f}% target.</p>
</section>

<section class="panel">
<h2>2. Equity &amp; drawdown</h2>
<div class="controls">
<label>Universe<select id="cv-univ"></select></label>
<label>Leverage<select id="cv-k"></select></label>
</div>
<svg id="equity-chart" class="chart" viewBox="0 0 1000 340" preserveAspectRatio="none"></svg>
<svg id="dd-chart" class="chart" viewBox="0 0 1000 200" preserveAspectRatio="none"></svg>
<div id="cv-legend" class="muted" style="font-size:12px"></div>
</section>

<section class="panel">
<h2>3. Crash-window drawdowns</h2>
<div class="controls"><label>Leverage<select id="cw-k"></select></label></div>
<div id="crash" class="table-wrap"></div>
</section>

<section class="panel">
<h2>4. Per-period (headline P4)</h2>
<div id="periods" class="table-wrap"></div>
</section>

<section class="panel">
<h2>5. Robustness grid (P4, full universe)</h2>
<p class="muted">One parameter varied at a time around the default. The headline should not be knife-edge.</p>
<div id="grid" class="table-wrap"></div>
</section>

<section class="panel warn">
<h2>Interpretation limits</h2>
<ul>
<li>Survivorship / current-membership bias in the underlying universe; the restricted universe is the control, not a fix.</li>
<li>Financing on gross &gt; 100% and borrow on the short sleeves are not charged; only rebalance turnover cost is added on top of the engine's per-trade cost.</li>
<li>Cash yield 0%. 60/40 is daily-rebalanced constant-mix.</li>
</ul>
<details><summary>Frozen signal parameters</summary><pre><code>{params_text}</code></pre></details>
</section>

</main>
<script>
const D={data};
const fmt=(v,d=2)=>v==null||!Number.isFinite(+v)?'\\u2014':(+v).toFixed(d);
const pct=(v,d=1)=>v==null||!Number.isFinite(+v)?'\\u2014':(+v*100).toFixed(d)+'%';
const cls=v=>v==null?'':(+v>=0?'pos':'neg');
const LAD=['P0','P1','P2','P3','P4','P4c'];
const COLORS={{P0:'#9ca3af',P1:'#60a5fa',P2:'#34d399',P3:'#fbbf24',P4:'#2563eb','P4c':'#a78bfa','SPY buy&hold':'#f87171','60/40 SPY/AGG':'#94a3b8'}};

function opts(id,arr,val){{const s=document.getElementById(id);arr.forEach(v=>{{const o=document.createElement('option');o.value=v;o.textContent=v;s.appendChild(o)}});if(val!=null)s.value=val;}}
opts('lad-univ',D.universes,'full');opts('lad-k',D.kmax);
opts('cv-univ',D.universes,'full');opts('cv-k',D.kmax);
opts('cw-k',D.kmax);

function ladder(){{
 const u=document.getElementById('lad-univ').value,k=document.getElementById('lad-k').value;
 const rows=LAD.map(v=>({{v,m:(D.ladder[u]&&D.ladder[u][k]&&D.ladder[u][k][v])||null}})).filter(r=>r.m);
 const cols=[['cagr','CAGR',true,true],['vol_annual','vol',true,false],['sharpe','Sharpe',false,true],['sortino','Sortino',false,true],['max_drawdown','maxDD',true,true],['calmar','Calmar',false,true],['ulcer_index','Ulcer',false,false],['worst_252d','worst 12m',true,true],['pct_underwater','%uw',true,false],['avg_gross','avg gross',true,false]];
 const best={{}};
 cols.forEach(([key,,,better])=>{{const vals=rows.map(r=>r.m[key]).filter(Number.isFinite);if(!vals.length)return;best[key]=(key==='max_drawdown'||key==='worst_252d')?Math.max(...vals):(key==='ulcer_index'||key==='pct_underwater'||key==='vol_annual'||key==='avg_gross')?Math.min(...vals):Math.max(...vals);}});
 let h='<table><thead><tr><th>Variant</th>'+cols.map(c=>`<th>${{c[1]}}</th>`).join('')+'<th>vol hit</th></tr></thead><tbody>';
 rows.forEach(r=>{{
  h+=`<tr><td>${{r.v}}</td>`+cols.map(([key,,isPct])=>{{
    const val=r.m[key];const disp=isPct?pct(val):fmt(val, key==='ulcer_index'?1:2);
    const hi=best[key]!=null&&val===best[key]?' class="hi"':'';
    return `<td${{hi}}>${{disp}}</td>`;
  }}).join('')+`<td>${{fmt(r.m.vol_annual/D.volTarget,2)}}x</td></tr>`;
 }});
 document.getElementById('ladder').innerHTML=h+'</tbody></table>';
}}

function path(series,x0,x1,y0,y1,vlo,vhi){{
 const n=series.length;return series.map((v,i)=>{{
  const x=x0+(x1-x0)*i/(n-1);const y=y1-(y1-y0)*(v-vlo)/(vhi-vlo||1);
  return (i?'L':'M')+x.toFixed(1)+','+y.toFixed(1);
 }}).join(' ');
}}
function curves(){{
 const u=document.getElementById('cv-univ').value,k=document.getElementById('cv-k').value;
 const bundle=D.curves[u]&&D.curves[u][k];if(!bundle)return;
 const names=['P4','P3','P1','SPY buy&hold','60/40 SPY/AGG'].filter(nm=>bundle[nm]);
 const eq=document.getElementById('equity-chart');const dd=document.getElementById('dd-chart');
 eq.innerHTML='';dd.innerHTML='';
 let elo=Infinity,ehi=-Infinity,dlo=0;
 names.forEach(nm=>{{bundle[nm].equity.forEach(v=>{{elo=Math.min(elo,v);ehi=Math.max(ehi,v)}});bundle[nm].dd.forEach(v=>{{dlo=Math.min(dlo,v)}})}});
 elo=Math.max(elo,0.2);
 const W=1000;
 names.forEach(nm=>{{
  eq.insertAdjacentHTML('beforeend',`<path d="${{path(bundle[nm].equity,40,W-8,20,320,elo,ehi)}}" fill="none" stroke="${{COLORS[nm]||'#888'}}" stroke-width="1.5"/>`);
  dd.insertAdjacentHTML('beforeend',`<path d="${{path(bundle[nm].dd,40,W-8,10,180,dlo,0)}}" fill="none" stroke="${{COLORS[nm]||'#888'}}" stroke-width="1.5"/>`);
 }});
 eq.insertAdjacentHTML('beforeend',`<text x="40" y="14">equity (log-ish scale ${{elo.toFixed(1)}}\\u2013${{ehi.toFixed(1)}}x)</text>`);
 dd.insertAdjacentHTML('beforeend',`<text x="40" y="12">drawdown (0 to ${{pct(dlo)}})</text>`);
 document.getElementById('cv-legend').innerHTML=names.map(nm=>`<span style="color:${{COLORS[nm]||'#888'}}">\\u25a0 ${{nm}}</span>`).join(' &nbsp; ');
}}

function crash(){{
 const k=document.getElementById('cw-k').value;
 let h='<table><thead><tr><th>Window</th>'+D.crashWindows.map(w=>`<th>${{w}}</th>`).join('')+'</tr></thead><tbody>';
 ['P1','P3','P4','P4c'].forEach(v=>{{
  const row=D.crash.full&&D.crash.full[k]&&D.crash.full[k][v];if(!row)return;
  h+=`<tr><td>${{v}} (full)</td>`+D.crashWindows.map(w=>`<td class="${{cls(row[w])}}">${{pct(row[w])}}</td>`).join('')+'</tr>';
 }});
 ['SPY buy&hold','60/40 SPY/AGG'].forEach(b=>{{
  const row=D.benchCrash[b];if(!row)return;
  h+=`<tr><td>${{b}}</td>`+D.crashWindows.map(w=>`<td class="${{cls(row[w])}}">${{pct(row[w])}}</td>`).join('')+'</tr>';
 }});
 document.getElementById('crash').innerHTML=h+'</tbody></table>';
}}

function periods(){{
 const rows=D.periods||[];
 let h='<table><thead><tr><th>Period</th><th>CAGR</th><th>vol</th><th>Sharpe</th><th>maxDD</th><th>Calmar</th></tr></thead><tbody>';
 rows.forEach(r=>{{h+=`<tr><td>${{r.period}}</td><td>${{pct(r.cagr)}}</td><td>${{pct(r.vol_annual)}}</td><td>${{fmt(r.sharpe)}}</td><td class="neg">${{pct(r.max_drawdown)}}</td><td>${{fmt(r.calmar)}}</td></tr>`}});
 document.getElementById('periods').innerHTML=h+'</tbody></table>';
}}

function grid(){{
 const rows=D.robustness||[];
 let h='<table><thead><tr><th>Change</th><th>k_max</th><th>CAGR</th><th>vol</th><th>Sharpe</th><th>maxDD</th><th>Calmar</th></tr></thead><tbody>';
 rows.forEach(r=>{{h+=`<tr><td>${{r.label}}</td><td>${{r.k_max}}</td><td>${{pct(r.cagr)}}</td><td>${{pct(r.vol_annual)}}</td><td>${{fmt(r.sharpe)}}</td><td class="neg">${{pct(r.max_drawdown)}}</td><td>${{fmt(r.calmar)}}</td></tr>`}});
 document.getElementById('grid').innerHTML=h+'</tbody></table>';
}}

['lad-univ','lad-k'].forEach(id=>document.getElementById(id).addEventListener('change',ladder));
['cv-univ','cv-k'].forEach(id=>document.getElementById(id).addEventListener('change',curves));
document.getElementById('cw-k').addEventListener('change',crash);
ladder();curves();crash();periods();grid();
</script></body></html>'''
    path.write_text(content, encoding="utf-8")


# --- main ---------------------------------------------------------


def downsample(xs: list[float], target: int = 400) -> list[float]:
    if len(xs) <= target:
        return [round(x, 4) for x in xs]
    step = len(xs) / target
    return [round(xs[min(len(xs) - 1, int(i * step))], 4) for i in range(target)]


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sfx = "" if args.cost_mult == 1.0 else f"_cost{args.cost_mult:g}"
    cache_path = args.output_dir / f"portfolio_signal_cache{sfx}.pkl"
    started = time.perf_counter()

    with read_only_connection(args.database) as conn:
        config_name, base_params = active_config(conn)
        latest_run = latest_universe_run(conn)
        targets = universe_targets(conn)
        if args.from_cache and cache_path.exists():
            cache = pickle.loads(cache_path.read_bytes())
            print(f"Reloaded engine cache ({len(cache['per_symbol'])} symbols, cost x{args.cost_mult:g})", flush=True)
        else:
            print("Running the frozen engine per symbol...", flush=True)
            cache = build_signal_cache(conn, targets, base_params, args.cost_mult)
            cache_path.write_bytes(pickle.dumps(cache))
        per_symbol = cache["per_symbol"]
        A = Aligned(per_symbol, args.vol_lookback)
        master = A.dates[A.start:]
        spy = series_uret(conn, "SPY", master)
        agg = series_uret(conn, "AGG", master)

    cost_bps = min(50.0, base_params.cost_bps * args.cost_mult)
    bench_window = {
        "SPY buy&hold": spy,
        "60/40 SPY/AGG": [0.6 * a + 0.4 * b for a, b in zip(spy, agg)],
    }
    bench_full = {
        name: metrics(r, [1.0] * len(r), [1.0] * len(r)) for name, r in bench_window.items()
    }
    bench_crash = {
        b: {w[0]: window_drawdown(master, r, w[1], w[2]) for w in CRASH_WINDOWS}
        for b, r in bench_window.items()
    }

    universes = {
        "full": A.symbols,
        "restricted": [s for s in A.symbols if A.group[s] != "Individual equity"],
    }
    kmax_list = [1.0, 2.0]
    variants = ["P0", "P1", "P2", "P3", "P4", "P4c"]
    crowd = crowding_series(A)  # needed only by P4c
    rebal = rebalance_days(A.dates, A.start, args.rebalance)

    ladder: dict[str, dict[str, dict[str, Any]]] = {}
    curves: dict[str, dict[str, dict[str, Any]]] = {}
    crash: dict[str, dict[str, dict[str, Any]]] = {}
    sims: dict[tuple[str, float, str], dict[str, list[float]]] = {}
    for uname, subset in universes.items():
        ladder[uname], curves[uname], crash[uname] = {}, {}, {}
        for k in kmax_list:
            kk = f"{k:g}"
            ladder[uname][kk], crash[uname][kk] = {}, {}
            curve_bundle: dict[str, Any] = {}
            for v in variants:
                sim = simulate(A, subset, v, k, args.vol_target, args.w_max, rebal, cost_bps,
                               crowd if v == "P4c" else None)
                sims[(uname, k, v)] = sim
                m = metrics(sim["ret"], sim["gross"], sim["net"])
                ladder[uname][kk][v] = m
                crash[uname][kk][v] = {
                    w[0]: window_drawdown(sim["dates"], sim["ret"], w[1], w[2]) for w in CRASH_WINDOWS
                }
                if v in ("P1", "P3", "P4", "P4c"):
                    eq = compound(sim["ret"])
                    curve_bundle[v] = {"equity": downsample(eq), "dd": downsample(drawdown_curve(eq))}
            for bname, r in bench_window.items():
                eq = compound(r)
                curve_bundle[bname] = {"equity": downsample(eq), "dd": downsample(drawdown_curve(eq))}
            curves[uname][kk] = curve_bundle

    headline = sims[("full", 2.0, "P4")]
    period_rows = period_metrics(headline["dates"], headline["ret"], headline["gross"], headline["net"])

    # robustness grid: vary one parameter around P4 / full
    robustness: list[dict[str, Any]] = []
    grid = [
        ("default", {}),
        ("vol lookback 40", {"vol_lookback": 40}),
        ("vol lookback 120", {"vol_lookback": 120}),
        ("vol target 10%", {"vol_target": 0.10}),
        ("vol target 15%", {"vol_target": 0.15}),
        ("w_max 5%", {"w_max": 0.05}),
        ("w_max 15%", {"w_max": 0.15}),
        ("daily rebalance", {"rebalance": "daily"}),
        ("monthly rebalance", {"rebalance": "monthly"}),
    ]
    for label, ov in grid:
        lb = ov.get("vol_lookback", args.vol_lookback)
        A2 = A if lb == args.vol_lookback else Aligned(per_symbol, lb)
        rb = rebalance_days(A2.dates, A2.start, ov.get("rebalance", args.rebalance))
        for k in kmax_list:
            sim = simulate(A2, universes["full"], "P4", k, ov.get("vol_target", args.vol_target),
                           ov.get("w_max", args.w_max), rb, cost_bps, None)
            m = metrics(sim["ret"], sim["gross"], sim["net"])
            robustness.append({"label": label, "k_max": f"{k:g}", **{x: m.get(x) for x in
                              ("cagr", "vol_annual", "sharpe", "max_drawdown", "calmar")}})

    elapsed = time.perf_counter() - started
    n_primary = len(per_symbol)
    payload = {
        "universes": list(universes),
        "kmax": [f"{k:g}" for k in kmax_list],
        "volTarget": args.vol_target,
        "crashWindows": [w[0] for w in CRASH_WINDOWS],
        "ladder": ladder,
        "curves": curves,
        "crash": crash,
        "benchCrash": bench_crash,
        "periods": period_rows,
        "robustness": robustness,
    }
    meta = {"cost_mult": args.cost_mult, "vol_target": args.vol_target, "rebalance": args.rebalance}

    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "stage": "4 - portfolio aggregation",
        "config_name": config_name,
        "frozen_signal": {"entry": "20/10 (bonds 100/50)", "exit": "c3_d20",
                          "direction": "long only; long/short for Bond ETF + Bitcoin"},
        "params": {"vol_target": args.vol_target, "vol_lookback": args.vol_lookback,
                   "w_max": args.w_max, "rebalance": args.rebalance, "cost_bps": cost_bps,
                   "sleeve_budget": SLEEVE_BUDGET, "k_max_reported": kmax_list},
        "cost_mult": args.cost_mult,
        "n_symbols": n_primary,
        "skipped": cache["skipped"],
        "start_date": master[0],
        "end_date": master[-1],
        "latest_universe_run": latest_run,
        "ladder": ladder,
        "crash_windows": {w[0]: {"start": w[1], "end": w[2]} for w in CRASH_WINDOWS},
        "crash": crash,
        "benchmark_full_history": bench_full,
        "benchmark_crash": bench_crash,
        "headline_periods": period_rows,
        "robustness": robustness,
        "elapsed_sec": round(elapsed, 1),
    }
    (args.output_dir / f"portfolio_agg_summary{sfx}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # long-format daily csv for P1/P3/P4 headline curves
    with (args.output_dir / f"portfolio_agg_daily{sfx}.csv").open("w", newline="", encoding="utf-8") as fh:
        wtr = csv.writer(fh)
        wtr.writerow(["date", "universe", "k_max", "variant", "port_ret", "gross", "net"])
        for (uname, k, v), sim in sims.items():
            if v not in ("P1", "P3", "P4"):
                continue
            for d, r, g, nx in zip(sim["dates"], sim["ret"], sim["gross"], sim["net"]):
                wtr.writerow([d, uname, f"{k:g}", v, f"{r:.6f}", f"{g:.4f}", f"{nx:.4f}"])

    write_report(args.output_dir / f"portfolio_agg_report{sfx}.html", payload, base_params, meta)
    for name in (f"portfolio_agg_summary{sfx}.json", f"portfolio_agg_daily{sfx}.csv", f"portfolio_agg_report{sfx}.html"):
        print(f"Wrote {args.output_dir / name}")
    print(f"{n_primary} symbols, window {master[0]}..{master[-1]}, {elapsed:.1f}s")


if __name__ == "__main__":
    main()
