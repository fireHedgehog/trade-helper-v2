"""Interactive long validation report and complete machine-readable summaries."""
import csv,gzip,json,statistics
from pathlib import Path
from plotly.offline import get_plotlyjs
from settings import ROOT,OUT,RULES,ANCHORS,POLICIES,LABELS,YEARS
SCOPES=['Priority assets','Whole universe','Priority equities / ETFs','Bonds','Crypto']
median=lambda xs:statistics.median(xs) if xs else None

def within(s,scope):
    return scope=='Whole universe' or scope=='Priority assets' and s['priority'] or scope=='Priority equities / ETFs' and s['priority'] and s['asset_class']=='Equities and other ETFs' or s['asset_class']==scope

def stats(s,key,period,cost):return s['results'].get(key,{}).get(period,{}).get(cost,{}).get('stats')

def summarize(rows):
    return {'assets':len(rows),'median_cagr':median([r['cagr'] if r['cagr'] is not None else -1. for r in rows]),
            'median_drawdown':median([r['drawdown'] for r in rows]),'positive':sum(r['net'] is not None and r['net']>0 for r in rows),
            'median_net':median([r['net'] if r['net'] is not None else -1. for r in rows]),
            'thin':sum(r.get('trades',0)<5 for r in rows),'short_history':sum(r['days']<730.5 for r in rows),
            'failures':sum(bool(r.get('exhausted')) for r in rows)}

def main():
    manifest=json.loads((OUT/'results.json').read_text(encoding='utf-8'));meta=manifest['metadata']
    assert not meta['partial']
    assets=[json.loads((OUT/'summaries'/(s['symbol'].replace('/','_')+'.json')).read_text(encoding='utf-8')) for s in manifest['instruments']]
    keys=[r['id'] for r in RULES]+['adaptive-common','adaptive-class'];grid=[];annual=[];classes=[]
    for scope in SCOPES:
        members=[s for s in assets if within(s,scope)]
        for key in keys:
            for period in ['full','validation']:
                for cost in ['normal','double','gross']:
                    rows=[r for s in members if (r:=stats(s,key,period,cost)) is not None]
                    if rows:grid.append({'scope':scope,'scenario':key,'period':period,'cost':cost,**summarize(rows)})
            if key in POLICIES:
                for cost in ['normal','double']:
                    for year in YEARS:
                        rows=[r for s in members if (r:=s['results'].get(key,{}).get('validation',{}).get(cost,{}).get('years',{}).get(str(year))) is not None]
                        if rows:annual.append({'scope':scope,'scenario':key,'cost':cost,'year':year,**summarize(rows)})
        for cost in ['normal','double']:
            pairs=[(a,b) for s in members if (a:=stats(s,'adaptive-class','validation',cost)) and (b:=stats(s,'adaptive-common','validation',cost))]
            deltas=[(a['cagr'] if a['cagr'] is not None else -1)-(b['cagr'] if b['cagr'] is not None else -1) for a,b in pairs]
            folds=[]
            for year in YEARS:
                if year==2026:continue
                diffs=[]
                for s in members:
                    a=s['results'].get('adaptive-class',{}).get('validation',{}).get(cost,{}).get('years',{}).get(str(year))
                    b=s['results'].get('adaptive-common',{}).get('validation',{}).get(cost,{}).get('years',{}).get(str(year))
                    if a and b and a['net'] is not None and b['net'] is not None:diffs.append(a['net']-b['net'])
                if diffs:folds.append({'year':year,'median_net_difference':median(diffs),'assets':len(diffs)})
            classes.append({'scope':scope,'cost':cost,'assets':len(pairs),'median_cagr_difference':median(deltas),
                            'higher_cagr':sum(d>1e-12 for d in deltas),'less_drawdown':sum(a['drawdown']>b['drawdown']+1e-12 for a,b in pairs),
                            'positive_completed_folds':sum(f['median_net_difference']>1e-12 for f in folds),'completed_folds':len(folds),'folds':folds})
    neighbourhoods=[]
    for key in ANCHORS:
        r=next(x for x in RULES if x['id']==key);entries=[5,10,15,20,25,30];idx=entries.index(r['entry'])
        neighbours=[x['id'] for x in RULES if x['tuned'] and x['stop']==r['stop'] and x['entry'] in entries[max(0,idx-1):idx+2]]
        for cost in ['normal','double']:
            rows=[x for x in grid if x['scope']=='Priority assets' and x['period']=='validation' and x['cost']==cost and x['scenario'] in neighbours]
            values=[x['median_cagr'] for x in rows]
            neighbourhoods.append({'anchor':key,'cost':cost,'count':len(values),'minimum':min(values),'median':median(values),'maximum':max(values),'positive':sum(v>0 for v in values)})
    findings={'priority_policies':[r for r in grid if r['scope']=='Priority assets' and r['period']=='validation' and r['scenario'] in POLICIES],
              'class_comparison':classes,'neighbourhoods':neighbourhoods}
    (OUT/'findings.json').write_text(json.dumps(findings,allow_nan=False,indent=2),encoding='utf-8')
    for name,rows in [('grid.csv',grid),('annual.csv',annual)]:
        with (OUT/name).open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    with gzip.open(OUT/'summary.csv.gz','wt',encoding='utf-8',newline='') as f:
        fields=['symbol','priority','asset_class','scenario','period','cost','net','cagr','drawdown','days','start','end','ending','price_pnl','fees','slippage','exhausted','identity_error','unfunded_signals','trades']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for s in assets:
            for key,periods in s['results'].items():
                for period,costs in periods.items():
                    for cost,values in costs.items():w.writerow({'symbol':s['symbol'],'priority':s['priority'],'asset_class':s['asset_class'],'scenario':key,'period':period,'cost':cost,**values['stats']})
    (OUT/'candidates').mkdir(exist_ok=True)
    for key in keys:
        rows={s['symbol']:s['results'][key] for s in assets if key in s['results']}
        script='window.step5Rows=window.step5Rows||{};window.step5Rows['+json.dumps(key)+']='+json.dumps(rows,allow_nan=False,separators=(',',':'))+';'
        (OUT/'candidates'/f'{key}.js').write_text(script,encoding='utf-8')
    payload={'metadata':meta,'assets':[{k:v for k,v in s.items() if k not in ['results','training','checks']} for s in assets],
             'grid':grid,'annual':annual,'findings':findings,'selections':json.loads((OUT/'selections.json').read_text(encoding='utf-8')),
             'second_source':json.loads((OUT/'second-source.json').read_text(encoding='utf-8')),'scopes':SCOPES}
    css=(ROOT/'backend/temp/step3/report.py').read_text(encoding='utf-8').split('<style>',1)[1].split('</style>',1)[0]
    html=TEMPLATE.replace('__CSS__',css).replace('__PLOTLY__',get_plotlyjs()).replace('__APP__',Path(__file__).with_name('report_app.js').read_text(encoding='utf-8'))
    html=html.replace('__DATA__',json.dumps(payload,allow_nan=False,separators=(',',':')).replace('<','\\u003c'))
    (OUT/'report.html').write_text(html,encoding='utf-8')
    print(json.dumps({'report':str(OUT/'report.html'),'priority': [r for r in findings['priority_policies'] if r['cost']!='gross'],
                      'class_comparison':[r for r in classes if r['scope']=='Priority assets'],'neighbourhoods':neighbourhoods}),flush=True)

TEMPLATE=r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Step 5 · Long strategy validation</title><link rel="icon" href="data:,"><style>__CSS__
.chart.tall{height:460px}.method-line{border-left:4px solid #4bb69e;background:#eaf5ef;padding:15px 18px;font-size:13px;margin:18px 0}.key-label{white-space:normal;min-width:200px;max-width:330px}.status{font-size:12px;color:#62777a}.benchmark{background:#f5f2ee}.panel h3{margin-top:14px}button{background:#e9f4ed;border:1px solid #bad3c4;border-radius:7px;padding:8px 12px;color:#17343c;cursor:pointer}tr[data-key]:hover{cursor:pointer;background:#edf7f0}.two.wide{grid-template-columns:minmax(0,1.2fr) minmax(0,1fr)}@media(max-width:950px){.two.wide{grid-template-columns:minmax(0,1fr)}}
</style></head><body><header><div class="eyebrow">Trading research · 05 / Long strategy validation</div><h1>Which long rules hold up?</h1><p>Compare the leading long settings, nearby alternatives and annual parameter selection. Keep costs, drawdowns and weaker periods visible.</p><div class="meta"><span id="stamp"></span><nav><a href="grid.csv">Comparison grid ↗</a><a href="summary.csv.gz">Every asset result ↗</a><a href="../step4/report.html">Step 4 ↗</a></nav></div></header><main>
<section class="panel"><h2>The long strategy decision</h2><p class="sub">Priority assets · identical evaluation dates across strategies within each asset. The three fixed candidates were shortlisted before this stage.</p><div class="cards" id="top-cards"></div><div class="table-wrap"><table><thead><tr><th>Strategy</th><th>Median CAGR</th><th>Doubled-cost CAGR</th><th>Median drawdown</th><th>Positive · priority</th><th>Positive · full universe</th></tr></thead><tbody id="decision-rows"></tbody></table></div><div class="method-line">Annual choices use the previous three calendar years only. Evaluation starts flat in each asset’s first eligible test year; later years carry existing positions and capital. An open position keeps its entry rule until exit. Fixed candidates use the same start date and starting cash. Full-history results are available separately below.</div><p class="note">This is chronological historical evaluation, not a pristine unseen holdout: the underlying history was already inspected in earlier stages. Medians describe individual-asset accounts, not portfolio returns. 2026 is partial.</p></section>
<section class="panel"><div class="top"><div><h2>Strategy comparison</h2><p class="sub">The fixed short breakout is a reference for future short strategies. It is not tuned or selected here.</p></div><div class="controls"><label>Decision universe<select id="scope"></select></label><label>Costs<select id="cost"><option value="normal">Normal costs</option><option value="double">Doubled costs</option><option value="gross">Zero costs</option></select></label></div></div><div class="chart tall" id="strategy-bars"></div><h3>Good years and difficult years</h3><div class="chart" id="annual"></div><p class="note">Annual cells show total return, not annualised partial-year returns. Each cell uses assets with an eligible evaluation window that year. Charts and rankings retain thin samples and show the full coverage below.</p></section>
<section class="panel"><h2>Does each asset class need its own settings?</h2><p class="sub">The common policy selects one rule from the priority assets. The class policy selects separately for equities/other ETFs, bonds and crypto using the same past-only procedure.</p><div class="table-wrap"><table><thead><tr><th>Group / costs</th><th>Median CAGR change</th><th>Higher CAGR</th><th>Less drawdown</th><th>Positive completed years</th></tr></thead><tbody id="class-rows"></tbody></table></div><p class="note">Changes are paired asset by asset against the common policy. Crypto has only two instruments and begins evaluation in 2025; one completed year cannot establish durable superiority. Groups with too few training assets use the common choice.</p><details><summary>See exactly which settings were selected before each year</summary><div class="table-wrap"><table><thead><tr><th>Test year / training period</th><th>Common rule</th><th>Equities / ETFs</th><th>Bonds</th><th>Crypto</th></tr></thead><tbody id="selection-rows"></tbody></table></div><p class="note">Training selects the highest median normal-cost CAGR among the 54 long candidates. Ties use the rule ID in alphabetical order. Selection uses eligible priority assets only; all eligible stored assets are evaluated. No symbol receives its own optimised rule. Doubled-cost tests retain the normal-cost selections.</p></details></section>
<section class="panel"><div class="top"><div><h2>Is there a useful range of settings?</h2><p class="sub">A nearby setting should not need to land on one exact winning number. These fixed-rule comparisons use the same evaluation start within each asset.</p></div><div class="controls"><label>Initial stop<select id="stop"><option value="2">2× ATR</option><option value="3">3× ATR</option><option value="0">No initial stop</option></select></label></div></div><div class="two"><div class="chart" id="neighbours"></div><div><h3>Neighbourhoods around the three candidates</h3><div class="table-wrap"><table><thead><tr><th>Candidate / costs</th><th>Low CAGR</th><th>Median</th><th>High</th><th>Positive settings</th></tr></thead><tbody id="neighbour-rows"></tbody></table></div><p class="note">Priority-assets medians across nine settings: the adjacent entry lookbacks, crossed with 40/55/70-bar exits, holding the initial stop fixed. These ranges describe historical sensitivity; selecting their maximum would reuse the evaluation data.</p></div></div></section>
<section class="panel"><div class="top"><div><h2>Every stored asset</h2><p class="sub" id="table-sub">Loading…</p></div><div class="controls"><label>Strategy<select id="strategy"></select></label><label>Period<select id="period"><option value="validation">Chronological evaluation</option><option value="full">Full available history</option></select></label><label>Find asset<input id="search" size="13" placeholder="BTC, TLT, SPY…"></label></div></div><p class="status" id="view-note"></p><div class="table-wrap scroll"><table><thead><tr><th>Asset</th><th>Net total</th><th>CAGR</th><th>Drawdown</th><th>Closed trades</th><th>Evaluation period</th><th>Ending $10,000</th></tr></thead><tbody id="asset-rows"></tbody></table></div><p class="note">All 678 assets remain listed. A blank validation result means there is insufficient preceding history for the required training window; the full-history simulation is still available. Short evaluation histories and low trade counts remain visible.</p></section>
<section class="panel" id="instrument-panel"><div class="top"><div><h2 id="instrument-title">Instrument review</h2><p class="sub" id="instrument-meta"></p></div><label>Instrument<select id="symbol"></select></label></div><div class="notice hidden" id="unavailable"></div><div id="instrument-content"><div class="cards" id="instrument-cards"></div><div class="chart" id="equity"></div><p class="note">Normal and doubled costs follow the identical fills. Each scenario funds trades from its own available equity. Open trades use the last stored close without an exit fee. Charts sample every fifth observation; metrics use every daily mark.</p><p class="money-line" id="money-equation"></p><p class="note" id="calendar-equation"></p><div class="table-wrap" id="policy-years"></div><details open><summary>Actual trades and dollar costs</summary><p id="ledger-note"></p><div class="table-wrap scroll"><table><thead><tr><th>Direction / entry</th><th>Entry</th><th>Exit / mark</th><th>Exit / mark date</th><th>Signed units</th><th>Starting equity</th><th>Price P&amp;L</th><th>Fees</th><th>Slippage</th><th>Ending equity</th></tr></thead><tbody id="trade-rows"></tbody></table></div><p><a id="ledger-download">Download dollar ledgers ↗</a></p></details></div></section>
<section class="panel"><h2>Crypto: does the price source change the result?</h2><p class="sub">Coinbase and Bitstamp USD daily prices, matched to the same calendar days. The three long candidates are fixed; this check does not choose new crypto parameters.</p><div class="table-wrap"><table><thead><tr><th>Asset / candidate</th><th>Coinbase CAGR¹</th><th>Bitstamp CAGR¹</th><th>Coinbase drawdown¹</th><th>Bitstamp drawdown¹</th></tr></thead><tbody id="source-rows"></tbody></table></div><p class="note" id="source-note"></p><p class="note">¹ Normal costs, matched chronological evaluation window. Venue prices can differ; small OHLC differences can change a breakout or stop. <a href="second-source.json">All source comparison results</a> · <a href="https://www.bitstamp.net/api/">Bitstamp public API documentation</a></p></section>
<section class="panel"><h2>Scope and calculation checks</h2><p id="checks"></p><p class="note">Normal costs: 5 basis points plus 0.05 prior-day ATR per fill. Doubled costs: 10 basis points plus 0.10 ATR. Short borrowing, funding and market impact are not modelled. Initial and trailing stops use completed data; signals fill at the next open. Nonpositive equity ends funded measurement at that value.</p><p class="note">The universe and priority membership are frozen from earlier stages. This is a current-universe study, not a historical index-membership reconstruction. Training needs three calendar years with sufficient preceding indicator history. Crypto qualifies from 2025. Nothing here changes production parameters, saved simulations or AI macro processing.</p><p class="note">The next decision is whether a fixed long preset is sufficient or class-specific selection adds consistent value. The Donchian short rule remains an infrastructure baseline, available for comparison with future short strategies.</p><p><a href="results.json">Manifest and verification</a> · <a href="findings.json">Summary findings</a> · <a href="selections.json">Annual selections and training membership</a> · <a href="annual.csv">Year-by-year results</a></p><p class="mono" id="hash"></p></section><footer>Research code: backend/temp/step5 · Reports and data: docs/temp/step5 · No production selection or commit.</footer></main><script>__PLOTLY__</script><script>__APP__</script></body></html>'''

if __name__=='__main__':main()
