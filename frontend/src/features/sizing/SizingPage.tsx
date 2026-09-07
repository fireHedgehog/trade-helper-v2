import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { Alert, Box, Button, Checkbox, Chip, FormControlLabel, LinearProgress, MenuItem,
  Paper, Stack, Tab, Tabs, Table, TableBody, TableCell, TableHead, TableRow,
  TextField, Typography } from '@mui/material';
import { BarChart } from '@mui/x-charts/BarChart';
import { dataApi } from '@/features/data-management/api';
import type { RunStatus } from '@/features/data-management/types';
import { EquityChart } from '@/features/timing/EquityChart';
import { sizingApi } from './api';
import { computeAllocation } from './engine';
import { BOOKS, DEFAULT_PARAMS, METHODS, type PortfolioResult, type SizingBoard, type SizingParams } from './types';

const money=(v:number)=>v.toLocaleString('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0});
const pct=(v:number|null|undefined)=>v==null?'—':(v*100).toFixed(2)+'%';
const units=(v:number)=>v.toLocaleString('en-US',{maximumFractionDigits:8});

export function SizingPage(){
  const [params,setParams]=useState<SizingParams>(DEFAULT_PARAMS);
  const [board,setBoard]=useState<SizingBoard|null>(null);
  const [result,setResult]=useState<PortfolioResult|null>(null);
  const [tab,setTab]=useState('today');
  const [runId,setRunId]=useState<number|null>(null);
  const [run,setRun]=useState<RunStatus|null>(null);
  const [starting,setStarting]=useState(false);
  const [error,setError]=useState<string|null>(null);
  const [query,setQuery]=useState('');
  const [symbol,setSymbol]=useState('SPY');
  const [showLong,setShowLong]=useState(true);
  const [showShort,setShowShort]=useState(true);
  const [page,setPage]=useState(0);
  const load=useCallback(async()=>{
    try{
      const [b,r,active]=await Promise.all([sizingApi.board(),sizingApi.latest(),dataApi.activeRuns()]);
      setBoard(b);setResult(r);
      const pending=active.find(x=>x.kind==='portfolio_simulation');
      if(pending){setRunId(pending.id);setRun(pending);}
    }catch(e){setError(String(e));}
  },[]);
  useEffect(()=>{void load();},[load]);
  useEffect(()=>{
    if(runId==null)return;
    let alive=true;
    const poll=async()=>{
      try{
        const r=await dataApi.run(runId);if(!alive)return;setRun(r);
        if(['succeeded','failed','cancelled'].includes(r.status)){
          setRunId(null);
          if(r.status==='succeeded')setResult(await sizingApi.latest());
          else setError(r.error_summary??'Simulation '+r.status);
        }
      }catch(e){if(alive)setError(String(e));}
    };
    void poll();const timer=setInterval(()=>void poll(),1200);
    return()=>{alive=false;clearInterval(timer);};
  },[runId]);
  const patch=(p:Partial<SizingParams>)=>setParams(v=>({...v,...p}));
  const validCapital=Number.isFinite(params.capital)&&params.capital>=100&&params.capital<=1e10;
  const allocation=useMemo(()=>board&&validCapital?computeAllocation(board,params):null,[board,params,validCapital]);
  const start=async()=>{
    setError(null);setStarting(true);setTab('history');
    try{const r=await sizingApi.run(params);setRunId(r.run_id);}
    catch(e){setError(String(e));}finally{setStarting(false);}
  };
  const dirty=!!result?.params&&JSON.stringify(params)!==JSON.stringify(result.params);
  const stat=result?.stats;
  const equity=useMemo(()=>{
    if(!result?.curve?.length)return null;
    let peak=result.params?.capital??100000;
    const bh=new Map(result.benchmark?.curve??[]);
    return {dates:result.curve.map(p=>p[0]),strat_equity:result.curve.map(p=>p[1]),
      bh_equity:result.curve.map(p=>bh.get(p[0])??0),
      drawdown:result.curve.map(p=>{peak=Math.max(peak,p[1]);return p[1]/peak-1;})};
  },[result]);
  const assets=(result?.assets??[]).filter(a=>a.symbol.includes(query.toUpperCase())).sort((a,b)=>b.net_pnl-a.net_pnl);
  const trades=(result?.trades??[]).filter(t=>t.symbol===symbol&&(t.direction==='long'?showLong:showShort))
    .sort((a,b)=>b.entry_date.localeCompare(a.entry_date));
  const top=[...(result?.assets??[])].sort((a,b)=>Math.abs(b.net_pnl)-Math.abs(a.net_pnl)).slice(0,12);
  const last=result?.curve?.at(-1);
  const download=()=>{
    const rows=result?.assets??[];if(!rows.length)return;
    const keys=Object.keys(rows[0]) as (keyof typeof rows[number])[];
    const quote=(x:unknown)=>'"'+String(x).replaceAll('"','""')+'"';
    const csv=[keys.join(','),...rows.map(r=>keys.map(k=>quote(r[k])).join(','))].join('\r\n');
    const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));
    a.download='sizing-asset-contributions.csv';a.click();URL.revokeObjectURL(a.href);
  };
  return <Box>
    <Typography variant="h5" gutterBottom>Sizing</Typography>
    <Typography color="text.secondary" sx={{mb:2,maxWidth:1000}}>
      Long 20/55 with an initial 3×ATR stop and no Chandelier. Short is the independent fixed
      20/20 benchmark with initial 2×ATR and Chandelier 3×ATR. Equal capital is the default;
      volatility sizing and concentration limits are alternatives.
    </Typography>
    {error&&<Alert severity="error" sx={{mb:2}}>{error}</Alert>}
    <Paper sx={{p:2,mb:2}}>
      <Stack direction="row" useFlexGap sx={{gap:2,flexWrap:'wrap',alignItems:'center'}}>
        <TextField select label="Universe" size="small" value={params.scope} onChange={e=>patch({scope:e.target.value as SizingParams['scope']})}>
          <MenuItem value="priority">Priority assets</MenuItem><MenuItem value="universe">Whole database</MenuItem>
        </TextField>
        <TextField select label="Allocation direction" size="small" value={params.book} onChange={e=>patch({book:e.target.value as SizingParams['book']})}>
          {Object.entries(BOOKS).map(([k,v])=><MenuItem key={k} value={k}>{v}</MenuItem>)}
        </TextField>
        <TextField select label="Sizing method" size="small" value={params.method} onChange={e=>patch({method:e.target.value as SizingParams['method']})}>
          {Object.entries(METHODS).map(([k,v])=><MenuItem key={k} value={k}>{v}</MenuItem>)}
        </TextField>
        <TextField label="Capital (USD)" type="number" size="small" value={params.capital} onChange={e=>patch({capital:Number(e.target.value)})} sx={{width:170}}/>
        <TextField select label="Costs" size="small" value={params.cost} onChange={e=>patch({cost:e.target.value as SizingParams['cost']})}>
          <MenuItem value="normal">Normal</MenuItem><MenuItem value="double">Doubled</MenuItem>
        </TextField>
        <TextField select label="History window" size="small" value={params.window} onChange={e=>patch({window:e.target.value as SizingParams['window']})}>
          <MenuItem value="recent">2020 onward</MenuItem><MenuItem value="full">Full available history</MenuItem>
        </TextField>
      </Stack>
      <Stack direction="row" useFlexGap spacing={1} sx={{mt:2,flexWrap:'wrap'}}>
        <Button variant="contained" onClick={()=>void start()} disabled={starting||runId!=null||!validCapital}>Run portfolio simulation</Button>
        <Button onClick={()=>void load()}>Refresh saved data</Button>
        {runId!=null&&<Button onClick={()=>void dataApi.cancelRun(runId)}>Cancel</Button>}
      </Stack>
      {runId!=null&&<Box sx={{mt:2}}><LinearProgress variant={run?.planned_targets?'determinate':'indeterminate'} value={run?.planned_targets?100*run.completed_targets/run.planned_targets:0}/>
        <Typography variant="body2" sx={{mt:1}}>{run?.status??'queued'} · {run?.completed_targets??0}/{run?.planned_targets??'…'} · {run?.current_target??'Preparing simulation'}</Typography></Box>}
      <Typography variant="caption" color="text.secondary" sx={{display:'block',mt:1}}>
        Direction changes the allocation. Historical results change only when you run the simulation.
        Combined starts 50/50 with no transfers; short-sale proceeds remain reserved. No macro AI calls.
      </Typography>
    </Paper>
    <Tabs value={tab} onChange={(_,v)=>setTab(v)} variant="scrollable" scrollButtons="auto" sx={{mb:2}}><Tab value="today" label="Allocation today"/><Tab value="history" label="Historical simulation"/></Tabs>
    {tab==='today'&&<>
      {board?.needs_recompute&&<Alert severity="warning" sx={{mb:2}}>Refresh the Trend run to use the current long strategy and short benchmark.</Alert>}
      {board?.status==='not_computed'&&<Alert severity="info">Run <RouterLink to="/trend">Trend</RouterLink> to prepare the current signals.</Alert>}
      {allocation&&<Paper sx={{p:2}}>
        <Typography variant="h6">Fresh allocation estimate</Typography>
        <Typography color="text.secondary" variant="body2" sx={{mb:2}}>
          Total holdings for a fresh allocation using the latest saved signals and closing prices.
          Existing simulated positions keep their entry units until exit. Quantities here are rounded
          to instrument increments; actual next-open prices will differ.
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{display:'block',mb:1}}>
          Saved Trend run: {board?.computed_at ? new Date(board.computed_at).toLocaleString() : 'unavailable'}.
          Fetch prices and rerun Trend to update this estimate.
        </Typography>
        <Stack direction="row" useFlexGap sx={{gap:2,flexWrap:'wrap',mb:2}}>
          <Chip label={allocation.eligible+' eligible assets, including flat names'}/>
          <Chip label={'Gross '+money(allocation.gross)}/>
          <Chip label={'Unallocated capital '+money(allocation.free)}/>
          <Chip label={'Estimated entry costs '+money(allocation.costs)}/>
        </Stack>
        <TextField size="small" label="Find asset" value={query} onChange={e=>setQuery(e.target.value)} sx={{mb:2}}/>
        <ScrollTable headers={['Asset','Direction','Signal','Vol 60d','Signed units','Gross value','Weight']}>
          {allocation.rows.filter(r=>r.symbol.includes(query.toUpperCase())).map(r=><TableRow key={r.symbol+r.direction}>
            <TableCell><RouterLink to={'/timing/'+encodeURIComponent(r.symbol)}>{r.symbol}</RouterLink></TableCell>
            <TableCell>{r.direction}</TableCell><TableCell>{r.pending?'Pending entry':'Holding'} · {r.signalDate}</TableCell>
            <TableCell>{pct(r.vol)}</TableCell><TableCell>{units(r.units)}</TableCell><TableCell>{money(r.notional)}</TableCell><TableCell>{pct(r.weight)}</TableCell>
          </TableRow>)}
        </ScrollTable>
        <Typography variant="caption" color="text.secondary">Flat allocations stay cash. Capped volatility uses 10% per symbol, 70% equities/other ETFs, 40% bonds and 10% crypto, with no redistribution. Short borrowing is additional over the holding period.</Typography>
      </Paper>}
    </>}
    {tab==='history'&&<>
      {(!stat||!result?.curve)&&<Alert severity="info">Run a portfolio simulation to see shared-capital returns, both direction contributions and funded trades.</Alert>}
      {stat&&result?.params&&<>
        {dirty&&<Alert severity="info" sx={{mb:2}}>Controls differ from the displayed result. Run the simulation to apply them.</Alert>}
        {result.needs_recompute&&<Alert severity="warning" sx={{mb:2}}>This saved simulation uses an earlier engine. Run it again with the current rules.</Alert>}
        <Typography variant="body2" color="text.secondary" sx={{mb:2}}>
          Displayed: {BOOKS[result.params.book]} · {METHODS[result.params.method]} · {result.params.scope} · {result.params.cost} costs · {result.curve?.[0][0]} to {last?.[0]}.
        </Typography>
        <Stack direction="row" useFlexGap sx={{gap:2,flexWrap:'wrap',mb:2}}>
          <Metric label="Portfolio CAGR" value={pct(stat.cagr)}/><Metric label="Maximum drawdown" value={pct(stat.drawdown)}/>
          <Metric label="Ending equity" value={money(stat.ending)}/><Metric label="Average gross invested" value={pct(stat.average_gross)}/>
          <Metric label="Fees + slippage + borrow" value={money(stat.fees+stat.slippage+stat.borrow)}/>
        </Stack>
        <Paper sx={{p:2,mb:2}}><Typography variant="h6">Portfolio equity · USD</Typography>
          <Typography variant="caption" color="text.secondary">Blue: strategy. Grey: equal-capital buy and hold. Red: drawdown. Reference CAGR {pct(result.benchmark?.stats.cagr)}; drawdown {pct(result.benchmark?.stats.drawdown)}.</Typography>
          {equity&&<EquityChart equity={equity}/>}
        </Paper>
        <Paper sx={{p:2,mb:2}}>
          <Typography variant="h6">Capital and direction contributions</Typography>
          <Stack direction="row" useFlexGap sx={{gap:2,flexWrap:'wrap',my:2}}>
            <Metric label="Long price P&L" value={money(stat.long_contribution*result.params.capital)}/>
            <Metric label="Short price P&L" value={money(stat.short_contribution*result.params.capital)}/>
            <Metric label="Short borrowing costs" value={money(stat.borrow)}/>
            <Metric label="Final free capital" value={money(last?.[6]??0)}/>
          </Stack>
          <Typography variant="body2">Long and short price P&amp;L, less fees, slippage and borrow, reconcile to {money(stat.ending-result.params.capital)} net profit. {result.audit?.unfunded??0} native entries received no funding.</Typography>
          {(stat.stale_position_days>0||stat.funding_deficit_days>0)&&<Alert severity="warning" sx={{mt:1}}>Stale held-price days: {stat.stale_position_days}. Funding deficit days: {stat.funding_deficit_days}. Stale positions retain their last known mark; no exit is invented.</Alert>}
        </Paper>
        <Paper sx={{p:2,mb:2}}><Typography variant="h6">Calendar years</Typography>
          <ScrollTable headers={['Year / coverage','Return','Drawdown']}>{stat.annual.map(a=><TableRow key={a.year}><TableCell>{a.start} → {a.end}</TableCell><TableCell>{pct(a.net)}</TableCell><TableCell>{pct(a.drawdown)}</TableCell></TableRow>)}</ScrollTable>
        </Paper>
        <Paper sx={{p:2,mb:2}}>
          <Stack direction="row" sx={{justifyContent:'space-between',gap:2,flexWrap:'wrap'}}><Typography variant="h6">Every asset's contribution</Typography><Button onClick={download}>Download all assets CSV</Button></Stack>
          <Typography variant="caption" color="text.secondary">Net dollars include open marked positions and all costs. All {result.assets?.length} assets remain available, including those without funded trades.</Typography>
          <BarChart layout="horizontal" yAxis={[{scaleType:'band',data:top.map(a=>a.symbol)}]} series={[{data:top.map(a=>a.net_pnl),label:'Net P&L (USD)',color:'#2f6fed'}]} height={350}/>
          <TextField size="small" label="Find asset" value={query} onChange={e=>setQuery(e.target.value)} sx={{mb:2}}/>
          <ScrollTable headers={['Asset','Long price P&L','Short price P&L','Costs','Net contribution','Account pp','Entries']}>
            {assets.slice(0,80).map(a=><TableRow key={a.symbol} hover onClick={()=>{setSymbol(a.symbol);setPage(0);}} sx={{cursor:'pointer'}}>
              <TableCell>{a.symbol}</TableCell><TableCell>{money(a.long_pnl)}</TableCell><TableCell>{money(a.short_pnl)}</TableCell>
              <TableCell>{money(a.fees+a.slippage+a.borrow)}</TableCell><TableCell>{money(a.net_pnl)}</TableCell><TableCell>{pct(a.contribution)}</TableCell><TableCell>{a.long_entries+a.short_entries}</TableCell>
            </TableRow>)}
          </ScrollTable>
          <Typography variant="caption">Showing {Math.min(assets.length,80)} of {assets.length} matches. Search any symbol or download the complete table.</Typography>
        </Paper>
        <Paper sx={{p:2,mb:2}}>
          <Typography variant="h6">Funded trade history</Typography>
          <Stack direction="row" useFlexGap sx={{gap:2,alignItems:'center',flexWrap:'wrap',my:2}}>
            <TextField select label="Asset ledger" size="small" value={(result.assets??[]).some(a=>a.symbol===symbol)?symbol:''} onChange={e=>{setSymbol(e.target.value);setPage(0);}} sx={{minWidth:160}}>
              {(result.assets??[]).map(a=><MenuItem key={a.symbol} value={a.symbol}>{a.symbol}</MenuItem>)}
            </TextField>
            <FormControlLabel label="Show long trades" control={<Checkbox checked={showLong} onChange={e=>{setShowLong(e.target.checked);setPage(0);}}/>}/>
            <FormControlLabel label="Show short trades" control={<Checkbox checked={showShort} onChange={e=>{setShowShort(e.target.checked);setPage(0);}}/>}/>
            <Button disabled={page===0} onClick={()=>setPage(p=>p-1)}>Previous</Button><Button disabled={(page+1)*30>=trades.length} onClick={()=>setPage(p=>p+1)}>Next</Button>
          </Stack>
          <ScrollTable headers={['Direction','Entry','Price','Signed units','Exit / mark','Price P&L','Costs','Net P&L','Reason']}>
            {trades.slice(page*30,page*30+30).map((t,i)=>{const cost=t.entry_fee+t.exit_fee+t.entry_slippage+t.exit_slippage+t.borrow;return <TableRow key={i}>
              <TableCell>{t.direction}</TableCell><TableCell>{t.entry_date}</TableCell><TableCell>{units(t.entry_price)}</TableCell><TableCell>{units(t.units)}</TableCell>
              <TableCell>{t.exit_date??t.mark_date+' (open)'}</TableCell><TableCell>{money(t.price_pnl)}</TableCell><TableCell>{money(cost)}</TableCell><TableCell>{money(t.price_pnl-cost)}</TableCell><TableCell>{t.reason}</TableCell>
            </TableRow>;})}
          </ScrollTable>
          <Typography variant="caption">{trades.length} matching trades. These checkboxes only filter the ledger; account returns and allocations remain the saved result.</Typography>
        </Paper>
      </>}
      <Alert severity="info" icon={false}>
        Historical accounts use fractional fixed units, next-open entries and prior-bar volatility.
        Normal costs are 5 bps + 0.05×ATR each side; short borrow assumes 2% annually (all doubled under stress).
        Short results are a synthetic benchmark: borrowing availability and crypto funding are not verified.
        Caps apply at entry and can drift with prices. The universe is today's stored database, not historical index membership.
      </Alert>
    </>}
  </Box>;
}
function Metric({label,value}:{label:string;value:string}){
  return <Paper variant="outlined" sx={{p:1.5,minWidth:160,flex:1}}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="h6">{value}</Typography></Paper>;
}
function ScrollTable({headers,children}:{headers:string[];children:React.ReactNode}){
  return <Box sx={{overflowX:'auto'}}><Table size="small" sx={{'& td, & th':{whiteSpace:'nowrap'}}}><TableHead><TableRow>{headers.map(h=><TableCell key={h}>{h}</TableCell>)}</TableRow></TableHead><TableBody>{children}</TableBody></Table></Box>;
}
