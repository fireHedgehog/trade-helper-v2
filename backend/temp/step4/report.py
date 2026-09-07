"""Build the full-universe comparison, small review shortlist and dollar report."""
import csv
import json
import statistics
from pathlib import Path
from plotly.offline import get_plotlyjs
from plan import ROOT, OUTPUT, FIELDS, RULES, SCENARIOS

SCOPES = ['Priority assets', 'Whole universe', 'Watchlist ETFs & crypto', 'Bonds', 'Major companies', 'Other instruments']
IX = {f: i for i, f in enumerate(FIELDS)}
median = lambda xs: statistics.median(xs) if xs else None
get = lambda row, field: row[IX[field]]
score = lambda row: -1. if get(row, 'exhausted') else get(row, 'common_cagr')
drawdown = lambda row: -1. if get(row, 'exhausted') else get(row, 'common_drawdown')


def aggregate(assets):
    by_scenario = {s[0]: [] for s in SCENARIOS}
    for asset in assets:
        asset['lookup'] = {r[0]: r for r in asset['rows']}
        for r in asset['rows']:
            by_scenario[r[0]].append((asset, r))
    grid = []
    for scope in SCOPES:
        for key, lk, sk, mode in SCENARIOS:
            items = [(s, r) for s, r in by_scenario[key] if scope == 'Whole universe'
                     or scope == 'Priority assets' and s['priority']
                     or scope == 'Watchlist ETFs & crypto' and s['group'] == 'Watchlist'
                     or s['group'] == scope]
            eligible = [(s, r) for s, r in items if get(r, 'common_days') >= 730.5]
            rows = [r for _, r in items]
            out = {'scope': scope, 'scenario': key, 'long_rule': lk, 'short_rule': sk, 'mode': mode,
                   'instruments': len(rows), 'eligible': len(eligible),
                   'positive_net': sum(get(r, 'net') > 0 and not get(r, 'exhausted') for r in rows),
                   'positive_gross': sum(get(r, 'gross') > 0 and not get(r, 'gross_exhausted') for r in rows),
                   'median_cagr': median([score(r) for _, r in eligible]),
                   'median_drawdown': median([drawdown(r) for _, r in eligible]),
                   'median_full_return': median([get(r, 'net') for r in rows]),
                   'positive_common': sum(score(r) > 0 for _, r in eligible),
                   'thin': sum(get(r, 'common_trades') < 5 for _, r in eligible),
                   'thin_short_full': sum(get(r, 'short_trades') < 5 for _, r in eligible) if mode != 'long' else None,
                   'exhausted': sum(bool(get(r, 'exhausted')) for r in rows),
                   'trades': sum(get(r, 'trades') for r in rows),
                   'median_short_trades': median([get(r, 'short_trades') for _, r in eligible]),
                   'short_contribution_positive': sum(get(r, 'short_pnl') > 0 for r in rows) if mode != 'long' else None,
                   'median_delta_long': None, 'median_delta_shared': None, 'improved_long': None,
                   'improved_shared': None, 'less_drawdown_long': None, 'improved_both_long': None}
            if mode == 'both':
                long_rows = [(r, s['lookup'][lk+'_long']) for s, r in eligible]
                shared_rows = [(r, s['lookup'][lk+'_'+lk]) for s, r in eligible]
                out.update(median_delta_long=median([score(a)-score(b) for a, b in long_rows]),
                           median_delta_shared=median([score(a)-score(b) for a, b in shared_rows]),
                           improved_long=sum(score(a) > score(b) + 1e-12 for a, b in long_rows),
                           improved_shared=sum(score(a) > score(b) + 1e-12 for a, b in shared_rows),
                           less_drawdown_long=sum(drawdown(a) > drawdown(b) + 1e-12 for a, b in long_rows),
                           improved_both_long=sum(score(a) > score(b) + 1e-12 and drawdown(a) > drawdown(b) + 1e-12 for a, b in long_rows))
            grid.append(out)
    return grid, by_scenario


def choose_shortlist(grid):
    priority = [r for r in grid if r['scope'] == 'Priority assets']
    asymmetric = sorted([r for r in priority if r['mode'] == 'both' and r['long_rule'] != r['short_rule']],
                        key=lambda r: (-r['median_cagr'], r['scenario']))
    best = asymmetric[0]
    low_dd = sorted([r for r in asymmetric if r['median_cagr'] >= best['median_cagr']-.02],
                    key=lambda r: (-r['median_drawdown'], -r['median_cagr'], r['scenario']))[0]
    incremental = sorted([r for r in asymmetric if r['median_cagr'] > 0],
                         key=lambda r: (-r['median_delta_long'], -r['median_cagr'], r['scenario']))[0]
    shortlist = []
    for label, row in [('Highest median CAGR', best), ('Lower drawdown · within 2 points of highest CAGR', low_dd),
                       ('Largest median change versus its own long-only rule', incremental)]:
        existing = next((r for r in shortlist if r['scenario'] == row['scenario']), None)
        if existing:
            existing['selection'] += '; '+label.lower()
        else:
            shortlist.append({**row, 'selection': label})
    shared = max([r for r in priority if r['mode'] == 'both' and r['long_rule'] == r['short_rule']], key=lambda r: r['median_cagr'])
    long_best = max([r for r in priority if r['mode'] == 'long'], key=lambda r: r['median_cagr'])
    return {'shortlist': shortlist, 'best_shared': shared, 'best_long': long_best,
            'selection_method': 'Priority-60 historical medians only; all 625 pairs remain visible. The shortlist selects highest median CAGR, shallowest median drawdown within 2 percentage points of that CAGR, and largest median paired CAGR change versus its own long-only rule among positive-median pairs. Duplicates are merged. No out-of-sample selection is claimed.'}


def main():
    manifest = json.loads((OUTPUT/'results.json').read_text(encoding='utf-8'))
    assert not manifest['metadata']['partial']
    assets = [json.loads((OUTPUT/'summaries'/(s['symbol'].replace('/', '_')+'.json')).read_text(encoding='utf-8')) for s in manifest['instruments']]
    grid, by_scenario = aggregate(assets)
    findings = choose_shortlist(grid)
    (OUTPUT/'findings.json').write_text(json.dumps(findings, allow_nan=False, indent=2), encoding='utf-8')
    with (OUTPUT/'grid.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(grid[0]))
        writer.writeheader()
        writer.writerows(grid)
    (OUTPUT/'candidates').mkdir(exist_ok=True)
    for key, items in by_scenario.items():
        payload = [[s['symbol'], *row] for s, row in items]
        script = 'window.step4Summaries=window.step4Summaries||{};window.step4Summaries['+json.dumps(key)+']='+json.dumps(payload, allow_nan=False, separators=(',', ':'))+';'
        (OUTPUT/'candidates'/f'{key}.js').write_text(script, encoding='utf-8')
    payload = {'metadata': manifest['metadata'], 'assets': [{k: v for k, v in s.items() if k not in ('rows', 'lookup', 'checks')} for s in assets],
               'grid': grid, 'findings': findings, 'scopes': SCOPES}
    css = (ROOT/'backend/temp/step3/report.py').read_text(encoding='utf-8').split('<style>', 1)[1].split('</style>', 1)[0]
    app = Path(__file__).with_name('report_app.js').read_text(encoding='utf-8')
    html = TEMPLATE.replace('__CSS__', css).replace('__PLOTLY__', get_plotlyjs()).replace('__APP__', app)
    html = html.replace('__DATA__', json.dumps(payload, allow_nan=False, separators=(',', ':')).replace('<', '\\u003c'))
    (OUTPUT/'report.html').write_text(html, encoding='utf-8')
    print(json.dumps({'report': str(OUTPUT/'report.html'), **findings}, allow_nan=False), flush=True)


TEMPLATE = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Step 4 · Long and short rules</title><link rel="icon" href="data:,"><style>__CSS__
.hero-tag{display:inline-block;border:1px solid #67998d;border-radius:20px;padding:5px 12px;font-size:11px;color:#cfede5}.rule-box{flex:1;min-width:230px;background:#f4f8f5;border:1px solid var(--line);border-radius:9px;padding:14px}.rule-box select{width:100%;font-size:12px}.rule-box b{display:block;margin-bottom:8px}.rule-box.short b{color:#a25563}.table-wrap tr[data-pair]{cursor:pointer}.table-wrap tr[data-pair]:hover{background:#e8f4ed}.heatmap{height:660px}.pair-name{white-space:normal;min-width:210px;max-width:340px}.comparison td:first-child{white-space:normal;min-width:200px}.small-button{border:1px solid #bdd4ca;border-radius:7px;padding:8px 12px;background:#ecf6ef;color:var(--ink);cursor:pointer;font:inherit;font-size:12px}.status{font-size:12px;color:var(--muted);margin:8px 0}.comparison{font-size:12px}.shortlist{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.pick{border:1px solid #d1e4d8;border-radius:9px;padding:17px;background:#f4f9f5}.pick b{display:block;font-size:15px}.pick .result{font-size:28px;letter-spacing:-.6px;margin:10px 0}.pick p{font-size:12px}.muted{color:var(--muted)}.rule-key{font-size:10px;font-family:ui-monospace,monospace;color:#58736c}.long-color{color:#087f7a}.short-color{color:#af5866}
.shortlist{grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}
@media(max-width:950px){.shortlist{grid-template-columns:1fr}.heatmap{height:550px}}@media(max-width:550px){.heatmap{height:480px}.rule-box{min-width:0;width:100%;flex-basis:100%}}
</style></head><body><header><div class="eyebrow">Trading research · 04 / Direction-specific rules</div><h1>Do shorts earn their place?</h1><p>Give longs and shorts different entry and exit rules. Compare the combined account with each side on its own, and see exactly what the short trades contribute.</p><span class="hero-tag">One account · one position at a time · unchanged cash calculation</span><div class="meta"><span id="stamp"></span><nav><a href="grid.csv">Comparison grid ↗</a><a href="summary.csv.gz">All asset results ↗</a><a href="../step3/report.html">Step 3 ↗</a></nav></div></header>
<main><section class="panel"><h2>The comparisons that matter</h2><p class="sub">These fixed rows use the 60 priority assets. The first three keep the Step 3 long candidate fixed: 10-bar entry, 55-bar channel exit, 2× ATR initial stop. The final rows show the strongest historical medians found in this grid.</p><div class="table-wrap"><table class="comparison"><thead><tr><th>Test</th><th>Median CAGR¹</th><th>Median drawdown¹</th><th>Positive · priority²</th><th>Positive · full universe²</th></tr></thead><tbody id="comparison-rows"></tbody></table></div><p class="note">¹ Same post-warm-up dates within each asset. ² Full available history after costs. These are medians of individual asset simulations, not portfolio returns. Click a row to inspect it.</p><div class="notice" id="main-finding"></div></section>
<section class="panel"><h2>A small shortlist for review</h2><p class="sub">Selected from the priority assets, with the complete universe retained below. These are historical candidates for Step 5 stability checks.</p><div class="shortlist" id="shortlist" style="margin-top:18px"></div><details><summary>How this shortlist was selected</summary><p id="selection-method"></p><p>The grid reuses Step 3 candidates: entry lengths 10, 20, 55 and 200; channel exits of 10 or 55; optional 2× ATR initial protection; optional 3× or 4× ATR Chandelier. A shared 20/20 reference is also included. It covers 25 rules per direction, 625 combined pairs and 50 standalone cases. It is not every possible parameter combination, and no rule is selected separately for each symbol.</p></details></section>
<section class="panel"><div class="top"><div><h2>Explore the long × short grid</h2><p class="sub">Diagonal cells use identical rules. Other cells change the short rule while holding the row’s long rule fixed.</p></div><div class="controls"><label>Decision universe<select id="scope"></select></label><label>Heatmap measure<select id="measure"><option value="median_cagr">Combined median CAGR</option><option value="median_delta_long">CAGR change vs long-only</option><option value="median_delta_shared">CAGR change vs shared rules</option></select></label></div></div><div class="controls" style="margin-top:18px"><div class="rule-box"><b class="long-color">Long rule</b><label>Long entry and exit settings<select id="long-rule"></select></label></div><div class="rule-box short"><b>Short rule</b><label>Short entry and exit settings<select id="short-rule"></select></label></div><label>View simulation<select id="mode"><option value="both">Combined account</option><option value="long">Long-only account</option><option value="short">Short-only account</option></select></label></div><p class="status" id="selected-rules"></p><div class="cards" id="kpis"></div><div class="chart heatmap" id="heatmap"></div><p class="note">Cells always describe the combined account. CAGR changes are median paired differences across the same eligible assets, in percentage points per year. Hover for the complete rules; click to select a pair.</p><div class="two"><div><h3>Does the selected short rule help?</h3><div class="table-wrap" id="incremental"></div><p class="note">Compare the combined strategy with a separate run of the same long rule. A short can make money itself yet block a later long opportunity; the whole-account comparison includes that effect.</p></div><div><h3>All 625 combinations</h3><div class="table-wrap scroll"><table><thead><tr><th>Long / short rules</th><th>CAGR</th><th>Δ vs long</th><th>Drawdown</th></tr></thead><tbody id="grid-rows"></tbody></table></div></div></div></section>
<section class="panel"><div class="top"><div><h2>Every stored asset</h2><p class="sub" id="table-sub">Loading results…</p></div><div class="controls"><label>Table coverage<select id="table-scope"><option value="all">All 678 assets</option><option value="priority">Priority assets</option></select></label><label>Sort<select id="sort"><option value="symbol">Symbol</option><option value="net">Net total return</option><option value="common_cagr">Common-window CAGR</option><option value="delta_long">Change vs long-only</option></select></label><label>Find asset<input id="search" placeholder="BTC, TLT, SPY…" size="14"></label></div></div><div class="table-wrap scroll" style="margin-top:18px"><table><thead><tr><th>Asset</th><th>Net total</th><th>Zero costs</th><th>Full CAGR</th><th>Common CAGR</th><th>Full drawdown</th><th>Trades</th><th>Δ CAGR vs long¹</th><th>Long contribution²</th><th>Short contribution²</th></tr></thead><tbody id="asset-rows"></tbody></table></div><p class="note">¹ Combined-account change versus a standalone long run; blank in standalone views or after exhaustion. ² Actual dollar profit after costs on each side’s trades in the selected account. These contributions add to the account’s net dollar profit. They are different from independently funded long-only or short-only returns.</p></section>
<section class="panel" id="instrument-panel"><div class="top"><div><h2 id="instrument-title">Instrument review</h2><p class="sub" id="instrument-meta"></p></div><label>Instrument<select id="symbol"></select></label></div><div class="notice hidden" id="exhaustion"></div><div class="cards" id="instrument-cards"></div><div class="chart" id="equity"></div><p class="note">Net, fee-only and zero-cost curves use the same fill schedule, with units sized from each account’s available equity. Standalone directions and shared-rule controls are separate simulations. Use the legend to compare them. Charts sample every fifth observation; metrics use every day.</p><div class="table-wrap" id="direction-table"></div><h3 style="margin-top:24px">Where did the money go?</h3><p class="money-line" id="money-equation"></p><div class="two"><div class="chart compact" id="waterfall"></div><div><h3>Actual contributions inside this account</h3><div id="contribution-table" class="table-wrap"></div><p class="note">Each entry uses one times the account’s equity as notional, with fixed signed units until exit. Price P&amp;L uses those actual units. Charges are 5 basis points plus 0.05 prior-day ATR per fill.</p><p class="note" id="cagr-equation"></p><a id="ledger-download">Download the full dollar ledger ↗</a></div></div><details open><summary>Inspect every funded trade</summary><p id="ledger-summary"></p><div class="table-wrap scroll"><table><thead><tr><th>Direction / entry</th><th>Entry price</th><th>Exit / marked price</th><th>Exit / mark date</th><th>Signed units</th><th>Starting equity</th><th>Price P&amp;L</th><th>Fees</th><th>Slippage</th><th>Ending equity</th></tr></thead><tbody id="trade-rows"></tbody></table></div><p class="note">Open trades use the last stored close, with no exit fee. If equity becomes nonpositive, funded measurement ends at that value; later signals cannot fund new trades. No assumed broker liquidation price or subsequent recovery is introduced.</p></details></section>
<section class="panel"><h2>What this stage establishes</h2><div class="reading"><p><strong>Separate rules can be assessed directly.</strong>Every pair has shared-rule and standalone controls. The same prices, execution timing, costs and return calculation apply throughout.</p><p><strong>Direction remains a choice.</strong>The combined strategy has one position at a time. Both directions remain supported; standalone experiments measure what changes when a side is disabled.</p><p><strong>Step 5 decides what survives.</strong>Rolling historical evaluation, neighbouring parameters and higher costs come next. The current grid uses historical data already seen in the earlier stages.</p></div><details open><summary>Calculation checks and scope</summary><p id="checks"></p><p>Prices and universe are frozen from Steps 1–3: all 678 stored assets, including Coinbase BTC/USD and ETH/USD. Each direction keeps its own native warm-up. Common-window metrics begin after bar 210, retaining any existing position; comparison dates are identical across candidates within each asset. At least two calendar years are required for ranking. The 16 shorter histories remain in full results. Thin samples stay included and flagged; exhausted accounts receive a −100% ranking score.</p><p>No simultaneous long/short positions, automatic reversals, regime filters or AI macro calls. Short borrow fees, funding, market impact and broker liquidation are not modelled. No production parameter or stored simulation is changed.</p><p id="priority-list"></p><p><a href="results.json">Manifest and calculation checks</a> · <a href="findings.json">Shortlist data</a> · <a href="../step1/inputs.csv.gz">Frozen input prices</a></p><p class="mono" id="hash"></p></details></section><footer>Step 4 is ready for review. Code and reports remain in the temp folders; no production selection or commit.</footer></main><script>__PLOTLY__</script><script>__APP__</script></body></html>'''


if __name__ == '__main__':
    main()
