const report=__DATA__,meta=report.metadata,assets=report.assets,grid=report.grid,rules=meta.rules,findings=report.findings;
const el=id=>document.getElementById(id),pct=x=>x==null?'—':(100*x).toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1})+'%',
 pp=x=>x==null?'—':(x>=0?'+':'')+(100*x).toFixed(2)+' pp',money=x=>x==null?'—':'$'+x.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}),
 num=x=>x==null?'—':x.toLocaleString('en-US',{maximumFractionDigits:4}),cls=x=>x<0?'negative':'positive';
const ruleByKey=new Map(rules.map(r=>[r.key,r])),scenarioByKey=new Map(meta.scenarios.map(s=>[s[0],s]));
const modeName={both:'Combined account',long:'Long-only account',short:'Short-only account'};
const loading=new Map(),rowsByScenario=new Map();let selectedSymbol='BTC/USD',generation=0,detailGeneration=0,loadedPair=null;
const plotConfig={responsive:true,displaylogo:false,modeBarButtonsToRemove:['lasso2d','select2d']};
const baseLayout={paper_bgcolor:'white',plot_bgcolor:'white',font:{family:'Segoe UI,system-ui,sans-serif',size:11,color:'#536d72'},margin:{l:65,r:14,t:45,b:40},hovermode:'x unified',legend:{orientation:'h',x:0,y:1.16},xaxis:{showgrid:false},yaxis:{gridcolor:'#e7efea',tickformat:'.2s'}};
const pair=()=>el('long-rule').value+'_'+el('short-rule').value;
const selected=()=>el('mode').value==='both'?pair():el(el('mode').value+'-rule').value+'_'+el('mode').value;
const lookup=(key,scope=el('scope').value)=>grid.find(r=>r.scenario===key&&r.scope===scope);
const scenarioLabel=key=>{const [,l,s,m]=scenarioByKey.get(key);return m==='both'?`Long ${ruleByKey.get(l).name} / Short ${ruleByKey.get(s).name}`:`${modeName[m]} · ${ruleByKey.get(l||s).name}`};
const get=(symbol,key=selected())=>rowsByScenario.get(key)?.get(symbol);
const delta=(a,b)=>a?.common_cagr==null||b?.common_cagr==null?null:a.common_cagr-b.common_cagr;
el('scope').innerHTML=report.scopes.map(s=>`<option>${s}</option>`).join('');
for(const side of ['long','short'])el(side+'-rule').innerHTML=rules.map(r=>`<option value="${r.key}">${r.key.toUpperCase()} · ${r.name}</option>`).join('');
el('symbol').innerHTML=assets.map(s=>`<option>${s.symbol}</option>`).join('');el('symbol').value=selectedSymbol;
const initial=scenarioByKey.get(findings.shortlist[0].scenario);el('long-rule').value=initial[1];el('short-rule').value=initial[2];
el('stamp').textContent=`${meta.symbol_count} assets · ${meta.simulation_count.toLocaleString()} simulations · ${meta.generated_utc.slice(0,10)} UTC`;
el('selection-method').textContent=findings.selection_method;
el('priority-list').textContent='Priority assets: '+meta.priority_symbols.join(', ')+'.';
el('checks').textContent=`All ${meta.step3_fill_checks.toLocaleString()} shared-rule and standalone controls reproduce Step 3 fills. Their net and calendar metrics agree with a maximum relative difference of ${meta.step3_bridge_max_error.toExponential(2)}. A separate simulator checks its own indicators, fills and daily cash on ${meta.cash_audit_symbols.join(', ')}: ${meta.cash_audit_bars.toLocaleString()} daily observations, maximum relative difference ${meta.cash_max_error.toExponential(2)}. Every funded ledger and direction contribution reconciles. Maximum dollar identity error: $${meta.dollar_identity_max_error.toExponential(2)}.`;
el('hash').textContent=`Production engine: ${meta.engine_sha256} | Unchanged Step 3 cash accounting: ${meta.cash_sha256} | Frozen input: ${meta.inputs_sha256}`;

function selectScenario(key){const [,l,s,m]=scenarioByKey.get(key);if(l)el('long-rule').value=l;if(s)el('short-rule').value=s;el('mode').value=m;refresh()}
function renderOverview(){
 const rows=[['Step 3 long candidate · longs alone','r02_long'],['Same rule for long and short','r02_r02'],['Same long + slow short with 4× ATR trail','r02_r23'],['Highest shared-rule median in this grid',findings.best_shared.scenario],['Highest asymmetric median in this grid',findings.shortlist[0].scenario]];
 el('comparison-rows').innerHTML=rows.map(([label,key])=>{const a=lookup(key,'Priority assets'),b=lookup(key,'Whole universe');return `<tr data-pair="${key}"><td><b>${label}</b><small>${scenarioLabel(key)}</small></td><td class="${cls(a.median_cagr)}">${pct(a.median_cagr)}</td><td>${pct(a.median_drawdown)}</td><td>${a.positive_net}/${a.instruments}</td><td>${b.positive_net}/${b.instruments}</td></tr>`}).join('');
 el('comparison-rows').querySelectorAll('tr').forEach(t=>t.onclick=()=>selectScenario(t.dataset.pair));
 const best=findings.shortlist[0],long=lookup(best.long_rule+'_long','Priority assets');
 el('main-finding').textContent=`The highest asymmetric median is ${pct(best.median_cagr)}, versus ${pct(long.median_cagr)} for its own long rule alone. Across the 60 priority assets, it raises CAGR on ${best.improved_long}, reduces drawdown on ${best.less_drawdown_long}, and does both on ${best.improved_both_long}. This is a historical comparison, not an out-of-sample result.`;
 el('shortlist').innerHTML=findings.shortlist.map(r=>{const whole=lookup(r.scenario,'Whole universe');return `<article class="pick"><b>${r.selection}</b><p class="muted">Long: ${ruleByKey.get(r.long_rule).name}<br>Short: ${ruleByKey.get(r.short_rule).name}</p><div class="result">${pct(r.median_cagr)} <small class="muted" style="font-size:12px">median CAGR</small></div><p>Median drawdown ${pct(r.median_drawdown)}<br>Positive after costs: ${r.positive_net}/60 priority · ${whole.positive_net}/678 overall<br>Median change vs own long-only: <span class="${cls(r.median_delta_long)}">${pp(r.median_delta_long)}</span><br>${r.thin_short_full}/60 have fewer than 5 closed short trades</p><button class="small-button" data-pair="${r.scenario}">Inspect this combination</button></article>`}).join('');
 el('shortlist').querySelectorAll('button').forEach(b=>b.onclick=()=>{selectScenario(b.dataset.pair);el('long-rule').scrollIntoView({behavior:'smooth',block:'center'})});
}

function renderGrid(){
 const key=pair(),r=lookup(selected()),both=lookup(key),measure=el('measure').value,l=el('long-rule').value,s=el('short-rule').value;
 el('selected-rules').textContent=scenarioLabel(selected())+'. Every trailing-stop profile includes a 2× ATR initial stop.';
 el('kpis').innerHTML=[['Positive · after costs',`${r.positive_net}/${r.instruments}`,'Full history, selected universe'],['Median CAGR',pct(r.median_cagr),`${r.eligible} assets · common window`],['Median drawdown',pct(r.median_drawdown),'Common window'],['Funded account failures',r.exhausted,`${r.thin} have fewer than 5 common-window trades`]].map(([a,b,c])=>`<div class="card"><span>${a}</span><strong>${b}</strong><small>${c}</small></div>`).join('');
 const rows=grid.filter(r=>r.scope===el('scope').value&&r.mode==='both'),byKey=new Map(rows.map(r=>[r.scenario,r]));
 const cells=rules.map(a=>rules.map(b=>byKey.get(a.key+'_'+b.key)));
 Plotly.react('heatmap',[{type:'heatmap',x:rules.map(r=>r.key.toUpperCase()),y:rules.map(r=>r.key.toUpperCase()),z:cells.map(row=>row.map(r=>100*r[measure])),customdata:cells.map(row=>row.map(r=>r.scenario)),text:cells.map(row=>row.map(r=>`Long: ${ruleByKey.get(r.long_rule).name}<br>Short: ${ruleByKey.get(r.short_rule).name}<br>${measure==='median_cagr'?pct(r[measure]):pp(r[measure])}`)),colorscale:[[0,'#b14b59'],[.5,'#f8f6ed'],[1,'#168778']],zmid:0,colorbar:{thickness:10,len:.7,ticksuffix:measure==='median_cagr'?'%':' pp'},hovertemplate:'%{text}<extra></extra>'}],{...baseLayout,margin:{l:60,r:65,t:12,b:68},hovermode:'closest',xaxis:{type:'category',title:{text:'Short rule →'},tickangle:-60,tickfont:{size:9}},yaxis:{type:'category',autorange:'reversed',title:{text:'Long rule →'},tickfont:{size:9}},shapes:[{type:'rect',xref:'x',yref:'y',x0:rules.findIndex(r=>r.key===s)-.48,x1:rules.findIndex(r=>r.key===s)+.48,y0:rules.findIndex(r=>r.key===l)-.48,y1:rules.findIndex(r=>r.key===l)+.48,line:{color:'#18333c',width:2},fillcolor:'transparent'}]},plotConfig);
 el('heatmap').removeAllListeners?.('plotly_click');el('heatmap').on('plotly_click',e=>selectScenario(e.points[0].customdata));
 const comparisons=[['Median CAGR change vs long-only',pp(both.median_delta_long)],['Assets with higher CAGR than long-only',`${both.improved_long}/${both.eligible}`],['Assets with less drawdown than long-only',`${both.less_drawdown_long}/${both.eligible}`],['Assets improving both',`${both.improved_both_long}/${both.eligible}`],['Median CAGR change vs same long rule on both sides',pp(both.median_delta_shared)],['Short trades earn positive dollars',`${both.short_contribution_positive}/${both.instruments}`],['Median closed short trades · full history',num(both.median_short_trades)],['Fewer than 5 closed short trades · full history',`${both.thin_short_full}/${both.eligible}`]];
 el('incremental').innerHTML='<table><tbody>'+comparisons.map(([a,b])=>`<tr><td>${a}</td><td>${b}</td></tr>`).join('')+'</tbody></table>';
 el('grid-rows').innerHTML=[...rows].sort((a,b)=>b.median_cagr-a.median_cagr||a.scenario.localeCompare(b.scenario)).map(r=>`<tr data-pair="${r.scenario}" class="${r.scenario===key?'selected':''}"><td class="pair-name"><b>${ruleByKey.get(r.long_rule).name}</b><small>Short: ${ruleByKey.get(r.short_rule).name}</small>${r.long_rule===r.short_rule?'<small>Shared rules</small>':''}</td><td class="${cls(r.median_cagr)}">${pct(r.median_cagr)}</td><td class="${cls(r.median_delta_long)}">${pp(r.median_delta_long)}</td><td>${pct(r.median_drawdown)}</td></tr>`).join('');
 el('grid-rows').querySelectorAll('tr').forEach(t=>t.onclick=()=>selectScenario(t.dataset.pair));
}

function loadScript(path){if(!loading.has(path))loading.set(path,new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=path;script.onload=resolve;script.onerror=reject;document.body.appendChild(script)}));return loading.get(path)}
async function loadRows(key){if(rowsByScenario.has(key))return;await loadScript('candidates/'+key+'.js');rowsByScenario.set(key,new Map(window.step4Summaries[key].map(r=>[r[0],Object.fromEntries(meta.fields.map((f,i)=>[f,r[i+1]]))])))}
async function refresh(){const token=++generation,l=el('long-rule').value,s=el('short-rule').value,key=pair();renderGrid();el('table-sub').textContent='Loading selected rules…';try{await Promise.all([key,l+'_long',s+'_short',l+'_'+l,s+'_'+s].map(loadRows))}catch(e){el('table-sub').textContent='Could not load the results. Keep the candidates folder beside this report.';return}if(token!==generation)return;loadedPair=key;renderTable();renderDetail()}

function renderTable(){if(loadedPair!==pair())return;const key=selected(),longKey=el('long-rule').value+'_long',search=el('search').value.toUpperCase(),sort=el('sort').value;
 const value=s=>sort==='delta_long'?delta(get(s.symbol,key),get(s.symbol,longKey)):get(s.symbol,key)[sort];
 const view=assets.filter(s=>(el('table-scope').value==='all'||s.priority)&&s.symbol.includes(search)).sort((a,b)=>sort==='symbol'?a.symbol.localeCompare(b.symbol):(value(b)??-Infinity)-(value(a)??-Infinity));
 el('table-sub').textContent=`${view.length} of ${assets.length} assets · ${modeName[el('mode').value]}. Click a row for the account and trade ledger.`;
 el('asset-rows').innerHTML=view.map(s=>{const r=get(s.symbol,key);return `<tr data-symbol="${s.symbol}" class="${s.symbol===selectedSymbol?'selected':''}"><td><b>${s.symbol}</b>${s.priority?' <span class="badge">Priority</span>':''}<small>${s.start} → ${s.end}</small>${r.exhausted?'<small class="negative">Account exhausted</small>':''}${r.common_days<730.5?'<small>Short history · outside ranking</small>':''}</td><td class="${cls(r.net)}">${pct(r.net)}</td><td>${pct(r.gross)}</td><td>${pct(r.cagr)}</td><td>${pct(r.common_cagr)}</td><td>${pct(r.drawdown)}</td><td>${r.trades}</td><td>${el('mode').value==='both'?pp(delta(r,get(s.symbol,longKey))):'—'}</td><td class="${cls(r.long_pnl)}">${money(r.long_pnl)}</td><td class="${cls(r.short_pnl)}">${money(r.short_pnl)}</td></tr>`}).join('');
 el('asset-rows').querySelectorAll('tr').forEach(t=>t.onclick=()=>{selectedSymbol=t.dataset.symbol;el('symbol').value=selectedSymbol;renderTable();renderDetail();el('instrument-panel').scrollIntoView({behavior:'smooth'})});
}

async function renderDetail(){
 const token=++detailGeneration,symbol=selectedSymbol,key=selected(),l=el('long-rule').value,s=el('short-rule').value,asset=assets.find(a=>a.symbol===symbol);
 if(loadedPair!==pair())return;
 el('instrument-meta').textContent='Loading '+symbol+' account details…';
 let data;try{await loadScript(asset.detail_file);data=await window.step4Ready[symbol]}catch(e){el('instrument-meta').textContent='Could not decode the instrument data. Keep the instruments folder beside the report and use a browser with gzip DecompressionStream support.';return}
 if(token!==detailGeneration||selectedSymbol!==symbol||selected()!==key)return;
 const r=get(symbol,key),detail=data.variants[key],mode=el('mode').value;
 el('instrument-title').textContent=symbol+' · '+modeName[mode];
 el('instrument-meta').textContent=`${scenarioLabel(key)} · ${asset.start} → ${asset.end} · ${asset.bars.toLocaleString()} bars · Common window starts ${asset.common_start??'outside history'}`;
 el('exhaustion').classList.toggle('hidden',!r.exhausted);el('exhaustion').textContent=`The funded account reaches a nonpositive value on ${r.exhausted}. The measured value is retained; ${r.unfunded_signals} later signals are unfunded.`;
 el('instrument-cards').innerHTML=[['Net total · full history',pct(r.net)],['CAGR · full history',pct(r.cagr)],['CAGR · common window',pct(r.common_cagr)],['Worst daily drawdown',pct(r.drawdown)]].map(([a,b])=>`<div class="card"><span>${a}</span><strong>${b}</strong></div>`).join('');
 const traces=[['net','Selected · net','#087f7a'],['fee_only','Selected · fees only','#779aa7'],['gross','Selected · zero costs','#ba873e']].map(([field,name,color])=>({x:data.dates,y:detail[field],name,type:'scatter',mode:'lines',visible:field==='fee_only'?'legendonly':true,line:{color,width:2,dash:field==='gross'?'dot':'solid'}}));
 const alternatives=[[l+'_long','Long rule alone','#4b7caf'],[s+'_short','Short rule alone','#b36178'],[l+'_'+l,'Both sides use the long rule','#949653'],[s+'_'+s,'Both sides use the short rule','#9694aa']];
 const seen=new Set([key]);
 for(const [other,name,color] of alternatives){if(seen.has(other))continue;seen.add(other);traces.push({x:data.dates,y:data.variants[other].net,name,type:'scatter',mode:'lines',visible:mode==='both'&&other===l+'_long'?true:'legendonly',line:{color,width:1.6}})}
 traces.push({x:data.dates,y:data.buy_hold,name:'Buy & hold',type:'scatter',mode:'lines',visible:'legendonly',line:{color:'#8f949b',width:1.5}});
 Plotly.react('equity',traces,{...baseLayout,yaxis:{...baseLayout.yaxis,title:{text:'Account value ($)'}},uirevision:symbol+'|'+key},plotConfig);
 const comparisons=[[pair(),'Combined account'],...alternatives.map(([a,b])=>[a,b])];
 el('direction-table').innerHTML='<table><thead><tr><th>Simulation</th><th>Net total</th><th>Zero costs</th><th>Full CAGR</th><th>Common CAGR</th><th>Full drawdown</th><th>Closed trades</th></tr></thead><tbody>'+comparisons.map(([k,name])=>{const a=get(symbol,k);return `<tr class="${k===key?'selected':''}"><td>${name}</td><td class="${cls(a.net)}">${pct(a.net)}</td><td>${pct(a.gross)}</td><td>${pct(a.cagr)}</td><td>${pct(a.common_cagr)}</td><td>${pct(a.drawdown)}</td><td>${a.trades}</td></tr>`}).join('')+'</tbody></table>';
 el('money-equation').textContent=`$10,000 ${r.price_pnl>=0?'+':'−'} ${money(Math.abs(r.price_pnl))} price P&L − ${money(r.fees)} fees − ${money(r.slippage)} slippage ≈ ${money(r.ending)}`;
 Plotly.react('waterfall',[{type:'waterfall',x:['Starting cash','Price P&L','Fees','Slippage','Ending value'],measure:['absolute','relative','relative','relative','total'],y:[10000,r.price_pnl,-r.fees,-r.slippage,0],connector:{line:{color:'#bdcac3'}},increasing:{marker:{color:'#168879'}},decreasing:{marker:{color:'#b9545a'}},totals:{marker:{color:'#254a58'}},hovertemplate:'%{x}<br>$%{y:,.2f}<extra></extra>'}],{...baseLayout,margin:{l:55,r:12,t:18,b:50},showlegend:false,hovermode:'closest'},plotConfig);
 el('contribution-table').innerHTML=`<table><tbody><tr><td>Long trades · net dollars</td><td class="${cls(r.long_pnl)}">${money(r.long_pnl)}</td></tr><tr><td>Short trades · net dollars</td><td class="${cls(r.short_pnl)}">${money(r.short_pnl)}</td></tr><tr><td>Total account profit</td><td>${money(r.ending-10000)}</td></tr><tr><td>Closed long / short trades</td><td>${r.long_trades} / ${r.short_trades}</td></tr></tbody></table>`;
 const years=(Date.parse(asset.end)-Date.parse(asset.start))/(86400000*365.25);
 el('cagr-equation').textContent=r.cagr==null?'CAGR is undefined after account exhaustion.':`Full-history CAGR = (${money(r.ending)} / $10,000)^(1 / ${years.toFixed(3)} calendar years) − 1 = ${pct(r.cagr)}. Time in cash is included.`;
 el('ledger-download').href='trades-'+(mode==='both'?l:mode)+'.csv.gz';
 el('ledger-download').textContent=mode==='both'?`Download combined ledgers for ${l.toUpperCase()} · all 25 short alternatives ↗`:`Download all ${mode}-only trade ledgers ↗`;
 el('ledger-summary').textContent=`${detail.ledger.length} funded trades, including any final open or exhaustion mark. Newest first. Every row reconciles at full precision; displayed dollars are rounded to cents.`;
 el('trade-rows').innerHTML=[...detail.ledger].reverse().map(t=>`<tr><td>${t[0]}<small>${t[1]}</small></td><td>${num(t[2])}</td><td>${num(t[4])}</td><td>${t[12]}<small>${t[5]}</small></td><td>${num(t[6])}</td><td>${money(t[7])}</td><td class="${cls(t[8])}">${money(t[8])}</td><td>${money(t[9])}</td><td>${money(t[10])}</td><td>${money(t[11])}</td></tr>`).join('');
}

for(const id of ['scope','long-rule','short-rule','mode'])el(id).onchange=refresh;
el('measure').onchange=renderGrid;
for(const id of ['table-scope','sort'])el(id).onchange=renderTable;
el('search').oninput=renderTable;
el('symbol').onchange=()=>{selectedSymbol=el('symbol').value;renderTable();renderDetail()};
renderOverview();refresh();
