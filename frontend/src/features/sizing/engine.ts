// A fresh-allocation estimate. Historical fixed-unit accounts run on the backend.
import type { AllocationInput, AllocationRow, SizingBoard, SizingParams } from './types';

export function computeAllocation(board:SizingBoard,p:SizingParams) {
  const source=board.universe ?? [...new Map([...board.long,...board.short,...board.flat].map(r=>[r.symbol,r])).values()] as AllocationInput[];
  const asOf=board.computed_at?.slice(0,10) ?? new Date().toISOString().slice(0,10);
  const eligible=source.filter(r=>(p.scope==='universe'||r.priority) && (r.bars??0)>65 &&
    (r.last_close??0)>0 && (r.vol_60d??0)>0 && r.last_date &&
    (Date.parse(asOf)-Date.parse(r.last_date))/86400000<=7);
  const invSum=eligible.reduce((a,r)=>a+1/Math.max(.01,r.vol_60d!),0);
  const sides:('long'|'short')[]=p.book==='combined-initial'?['long','short']:p.book==='short-reference'?['short']:['long'];
  const candidates:{row:AllocationInput;direction:'long'|'short';budget:number;pending:boolean;date:string|null;atr:number}[]=[];
  for(const r of eligible)for(const side of sides){
    const state=r.directions?.[side] ?? r;
    const pending=state.pending_action;
    const direction=pending?(pending.action==='exit'?'flat':pending.direction):state.state;
    if(direction!==side)continue;
    const weight=p.method==='equal'?1/eligible.length:(1/Math.max(.01,r.vol_60d!))/invSum;
    candidates.push({row:r,direction:side,budget:p.capital/sides.length*weight,
      pending:!!pending,date:pending?.signal_date??state.state_since,atr:state.atr_20??0});
  }
  const fee=p.cost==='normal'?.0005:.001,slip=p.cost==='normal'?.05:.1;
  const notionals=candidates.map(c=>c.budget/(1+fee+slip*c.atr/c.row.last_close!));
  if(p.method==='capped-vol'){
    const caps:Record<string,number>={'Equities and other ETFs':.70,'Bonds':.40,'Crypto':.10};
    for(const by of ['symbol','group']){
      const sums=new Map<string,number>();
      const key=(c:typeof candidates[number])=>by==='symbol'?c.row.symbol:c.row.asset_class??'Equities and other ETFs';
      candidates.forEach((c,i)=>sums.set(key(c),(sums.get(key(c))??0)+notionals[i]));
      candidates.forEach((c,i)=>{const cap=(by==='symbol'?.10:caps[key(c)]??.70)*p.capital;
        notionals[i]*=Math.min(1,cap/(sums.get(key(c))||1));});
    }
  }
  const rows:AllocationRow[]=candidates.map((c,i)=>{
    const price=c.row.last_close!,step=c.row.quantity_increment??(c.row.symbol.includes('/')?1e-8:1);
    let units=Math.floor(notionals[i]/price/step)*step;
    if(units<(c.row.min_order_size??step))units=0;
    const notional=units*price,costs=units*(price*fee+slip*c.atr);
    return {symbol:c.row.symbol,direction:c.direction,group:c.row.asset_class??'Equities and other ETFs',
      price,vol:c.row.vol_60d!,signalDate:c.date,pending:c.pending,units:c.direction==='short'?-units:units,
      notional,costs,weight:notional/p.capital};
  });
  const gross=rows.reduce((a,r)=>a+r.notional,0),costs=rows.reduce((a,r)=>a+r.costs,0);
  return {rows,eligible:eligible.length,gross,costs,free:Math.max(0,p.capital-gross-costs),asOf};
}
