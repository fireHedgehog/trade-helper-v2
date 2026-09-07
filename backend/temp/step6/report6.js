const $=id=>document.getElementById(id), pct=x=>x==null?'—':(x*100).toFixed(2)+'%', money=x=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(x), num=x=>new Intl.NumberFormat('en-US',{maximumFractionDigits:3}).format(x);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const colours={'equal':'#185c79','inverse-vol':'#ad7737','capped-vol':'#268170','buy-hold':'#9aa4aa'};
const chartNames={'equal':'Equal capital','inverse-vol':'Volatility','capped-vol':'Vol + caps'};
const config={responsive:true,displayModeBar:false};
const layout={paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{family:'system-ui',size:12,color:'#526670'},margin:{t:55,r:16,b:45,l:62},legend:{orientation:'h',y:1.03,yanchor:'bottom',x:0,font:{size:10}},xaxis:{gridcolor:'#edf0ef'},yaxis:{gridcolor:'#e6eeec'},hovermode:'x unified'};
let current,epoch=0,tradePage=0;
for(const [k,v] of Object.entries(DATA.labels))$('book').add(new Option(v,k));
for(const [k,v] of Object.entries(DATA.methods))$('method').add(new Option(v,k));
$('book').value='long-initial';$('method').value='equal';
function state(){return Object.fromEntries(['scope','window','book','method','cost'].map(k=>[k,$(k).value]));}
function key(s){return [s.scope,s.window,s.book,s.method,s.cost].join('__');}
async function load(id){
 if(!window.step6Cases?.[id]){
  await new Promise((resolve,reject)=>{const el=document.createElement('script');el.src='display/'+encodeURIComponent(id)+'.js';el.onload=resolve;el.onerror=()=>reject(new Error('Could not load '+id));document.head.append(el);});
 }
 return await window.step6Cases[id];
}
function table(headers,rows){return '<table><thead><tr>'+headers.map(h=>'<th>'+esc(h)+'</th>').join('')+'</tr></thead><tbody>'+rows.join('')+'</tbody></table>';}
function cells(values){return values.map(v=>'<td>'+v+'</td>').join('');}
function renderComparison(s){
 const rows=DATA.cases.filter(r=>r.scope===s.scope&&r.window===s.window&&r.cost===s.cost);
 $('comparison').innerHTML=table(['Strategy / direction','Sizing','CAGR','Worst drawdown','Average invested','Net return','Trades'],rows.map(r=>'<tr data-key="'+r.id+'" class="'+(r.id===key(s)?'selected':'')+'">'+cells([esc(DATA.labels[r.book]),esc(DATA.methods[r.method]),pct(r.stats.cagr),pct(r.stats.drawdown),pct(r.stats.average_gross),pct(r.stats.net),num(r.stats.entries)])+'</tr>'));
 $('comparison').querySelectorAll('[data-key]').forEach(el=>el.onclick=()=>{const r=DATA.cases.find(v=>v.id===el.dataset.key);$('book').value=r.book;$('method').value=r.method;refresh();});
}
function renderKpis(r){
 const a=r.stats;
 const mix=DATA.findings.priority_exposure.find(v=>v.id===key(r));
 $('allocationMix').textContent=mix?'Average invested exposure for this case: '+Object.entries(mix.average_exposure_by_class).map(([name,value])=>name+' '+pct(value)).join(' · ')+'. These are shares of account equity, not shares of only the invested capital.':'Inverse-volatility sizing changes the asset mix as well as risk. Compare invested exposure and drawdown alongside CAGR; cap reductions are left in cash.';
 $('kpis').innerHTML=[['Portfolio CAGR',pct(a.cagr),'Calendar-time annualisation'],['Worst drawdown',pct(a.drawdown),'Account equity peak to trough'],['Ending equity',money(a.ending),'Started with $100,000'],['Average invested',pct(a.average_gross),'Gross long + short exposure'],['Total costs',money(a.fees+a.slippage+a.borrow),'Fees + slippage + borrow'],['Assets funded',a.assets_funded+' / '+r.assets.length,num(a.entries)+' entries']].map(([label,value,sub])=>'<div class="kpi"><span>'+label+'</span><strong>'+value+'</strong><small>'+sub+'</small></div>').join('');
 let text='Fixed units remain in place until their native exit. '+num(r.audit.unfunded)+' signals received no funding. '+num(r.audit.scaled_funding_requests)+' requests were reduced by the capital budget.';
 if(r.method==='capped-vol')text+=' '+num(r.audit.scaled_cap_requests)+' cap reductions occurred (one request can encounter both a symbol and a class limit).';
 if(a.funding_deficit_days||r.audit.sleeve_deficit_days)text+=' Collateral/funding deficits occurred on '+num(r.audit.sleeve_deficit_days)+' sleeve-days after market moves; no new borrowing or invented liquidation was added.';
 if(a.stale_position_days)text+=' Held prices were stale on '+num(a.stale_position_days)+' calendar days; maximum stale marked exposure '+money(a.maximum_stale_gross)+'.';
 $('reading').textContent=text;
 $('reading').className='note'+(a.stale_position_days||r.audit.sleeve_deficit_days?' warn':'');
}
async function charts(r,s,token){
 const variants=r.book==='buy-hold'?[r]:await Promise.all(Object.keys(DATA.methods).map(method=>load(key({...s,method}))));
 const bh=await load(key({...s,book:'buy-hold',method:'equal'}));
 if(token!==epoch)return;
 const plotted=r.book==='buy-hold'?variants:[...variants,bh];
 const traces=plotted.map(v=>({x:v.curve.map(p=>p[0]),y:v.curve.map(p=>p[1]),name:v.book==='buy-hold'?'Buy & hold':chartNames[v.method],mode:'lines',line:{color:colours[v.book==='buy-hold'?'buy-hold':v.method],width:v.method===s.method&&v.book===s.book?2.8:1.6,dash:v.book==='buy-hold'?'dot':'solid'}}));
 Plotly.react('equity',traces,{...layout,yaxis:{...layout.yaxis,tickprefix:'$'}},config);
 const dd=plotted.map((v,i)=>{let peak=100000;return {...traces[i],y:v.curve.map(p=>{peak=Math.max(peak,p[1]);return p[1]/peak-1;})};});
 Plotly.react('drawdown',dd,{...layout,yaxis:{...layout.yaxis,tickformat:'.0%'}},config);
 const x=r.curve.map(p=>p[0]);
 Plotly.react('exposure',[{x,y:r.curve.map(p=>p[3]/p[1]),name:'Long',mode:'lines',line:{color:'#23765d'}},{x,y:r.curve.map(p=>p[4]/p[1]),name:'Short gross',mode:'lines',line:{color:'#b04c4f'}},{x,y:r.curve.map(p=>p[6]/p[1]),name:'Free capital',mode:'lines',line:{color:'#718291',dash:'dot'}}],{...layout,yaxis:{...layout.yaxis,tickformat:'.0%'}},config);
 const a=r.stats;
 Plotly.react('waterfall',[{type:'waterfall',x:['Long P&L','Short P&L','Fees','Slippage','Borrow','Net P&L'],y:[a.long_contribution*100000,a.short_contribution*100000,-a.fees,-a.slippage,-a.borrow,0],measure:['relative','relative','relative','relative','relative','total'],increasing:{marker:{color:'#23765d'}},decreasing:{marker:{color:'#b04c4f'}},totals:{marker:{color:'#185c79'}}}],{...layout,showlegend:false,yaxis:{...layout.yaxis,tickprefix:'$'}},config);
 $('annual').innerHTML=table(['Year / coverage','Portfolio return','Within-year drawdown'],a.annual.map(y=>'<tr>'+cells([y.year+' · '+y.start+' → '+y.end,pct(y.net),pct(y.drawdown)])+'</tr>'));
 const top=[...r.assets].sort((a,b)=>Math.abs(b.net_pnl)-Math.abs(a.net_pnl)).slice(0,15).reverse();
 Plotly.react('contributions',[{type:'bar',orientation:'h',x:top.map(a=>a.net_pnl),y:top.map(a=>a.symbol),marker:{color:top.map(a=>a.net_pnl>=0?'#23765d':'#b04c4f')},hovertemplate:'%{y}: $%{x:,.0f}<extra></extra>'}],{...layout,margin:{t:5,r:20,b:35,l:85},xaxis:{...layout.xaxis,tickprefix:'$'},yaxis:{automargin:true},height:330},config);
}
function renderAssets(){
 const query=$('search').value.trim().toUpperCase();
 const rows=current.assets.filter(a=>a.symbol.includes(query)).sort((a,b)=>b.net_pnl-a.net_pnl);
 $('assetTable').innerHTML=table(['Asset','Class','Long P&L','Short P&L','All costs','Net contribution','Account pp','Entries','Unfunded'],rows.slice(0,60).map(a=>'<tr data-symbol="'+esc(a.symbol)+'">'+cells([esc(a.symbol),esc(a.group),money(a.long_pnl),money(a.short_pnl),money(a.fees+a.slippage+a.borrow),'<span class="'+(a.net_pnl>=0?'positive':'negative')+'">'+money(a.net_pnl)+'</span>',pct(a.contribution),num(a.long_entries+a.short_entries),num(a.unfunded)])+'</tr>'));
 $('assetCount').textContent='Showing '+Math.min(rows.length,60)+' of '+rows.length+' matching assets. Search or use the asset selector to inspect any member; the download contains all '+current.assets.length+'.';
 $('assetTable').querySelectorAll('[data-symbol]').forEach(el=>el.onclick=()=>{$('asset').value=el.dataset.symbol;tradePage=0;renderLedger();});
}
function renderLedger(){
 const symbol=$('asset').value,a=current.assets.find(v=>v.symbol===symbol);if(!a)return;
 const trades=current.trades.filter(t=>t.symbol===symbol).sort((a,b)=>a.entry_date.localeCompare(b.entry_date));
 const pages=Math.max(1,Math.ceil(trades.length/30));tradePage=Math.max(0,Math.min(tradePage,pages-1));
 $('assetStats').innerHTML=[['Net contribution',money(a.net_pnl)],['Account percentage points',pct(a.contribution)],['Long / short entries',a.long_entries+' / '+a.short_entries],['Unfunded native signals',a.unfunded],['Open gross',money(a.open_long+a.open_short)]].map(([k,v])=>'<div>'+esc(k)+'<strong>'+esc(v)+'</strong></div>').join('');
 $('trades').innerHTML=table(['Direction','Entry','Entry price','Signed units','Exit / mark','Exit / mark price','Price P&L','Fees','Slippage','Borrow','Net P&L','Reason'],trades.slice(tradePage*30,tradePage*30+30).map(t=>'<tr>'+cells([t.direction,t.entry_date,num(t.entry_price),num(t.units),t.exit_date||t.mark_date+' (open)',num(t.mark_price),money(t.price_pnl),money(t.entry_fee+t.exit_fee),money(t.entry_slippage+t.exit_slippage),money(t.borrow),money(t.price_pnl-t.entry_fee-t.exit_fee-t.entry_slippage-t.exit_slippage-t.borrow),esc(t.reason)])+'</tr>'));
 $('tradePage').textContent=(tradePage+1)+' / '+pages+' · '+trades.length+' trades';$('previous').disabled=tradePage===0;$('next').disabled=tradePage>=pages-1;
}
async function refresh(){
 const token=++epoch,s=state();
 if(s.book==='buy-hold'){s.method='equal';$('method').value='equal';$('method').disabled=true;}else $('method').disabled=false;
 $('status').textContent='Loading saved portfolio…';
 try{
  const r=await load(key(s));if(token!==epoch)return;current=r;tradePage=0;
  renderComparison(s);renderKpis(r);
  const old=$('asset').value;$('asset').innerHTML='';r.assets.forEach(a=>$('asset').add(new Option(a.symbol,a.symbol)));
  $('asset').value=r.assets.some(a=>a.symbol===old)?old:(r.assets.some(a=>a.symbol==='SPY')?'SPY':r.assets[0].symbol);
  renderAssets();renderLedger();await charts(r,s,token);if(token!==epoch)return;
  $('status').textContent=r.curve[0][0]+' → '+r.curve.at(-1)[0]+' · '+DATA.labels[r.book]+' · '+DATA.methods[r.method]+' · '+r.assets.length+' assets retained';
 }catch(e){$('status').textContent='Report loading failed: '+e.message;console.error(e);}
}
for(const id of ['scope','window','book','method','cost'])$(id).onchange=refresh;
$('search').oninput=renderAssets;$('asset').onchange=()=>{tradePage=0;renderLedger();};
$('previous').onclick=()=>{tradePage--;renderLedger();};$('next').onclick=()=>{tradePage++;renderLedger();};
$('download').onclick=()=>{const cols=Object.keys(current.assets[0]),quote=v=>'"'+String(v).replaceAll('"','""')+'"';const csv=[cols.join(','),...current.assets.map(a=>cols.map(k=>quote(a[k])).join(','))].join('\r\n');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));a.download=key(state())+'-assets.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
$('footer').innerHTML='Verified '+num(DATA.verification.saved_trades)+' saved trades and '+num(DATA.verification.daily_marks)+' daily portfolio marks. Maximum cash-replay difference '+money(DATA.verification.maximum_replay_error)+'. <a href="comparison.csv">All portfolio comparisons (CSV)</a> · <a href="asset-contributions.csv.gz">All asset contributions (CSV.gz)</a> · <a href="verification.json">Verification</a> · <a href="results.json">Results & assumptions</a>. Inputs through '+DATA.metadata.end+'.';
refresh();
