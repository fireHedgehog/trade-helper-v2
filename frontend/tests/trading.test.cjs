const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const ts = require("typescript");

// Run the pure TypeScript calculations with Node's test runner.
require.extensions[".ts"] = (module, filename) => {
  const { outputText } = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    fileName: filename,
  });
  module._compile(outputText, filename);
};
const { computeAllocation } = require("../src/features/sizing/engine.ts");
const { DEFAULT_PARAMS } = require("../src/features/sizing/types.ts");
const { filterDaily, filterState, compound, summariseView } = require("../src/features/timing/metrics.ts");
const close = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-8, `${actual} != ${expected}`);
const macro = { source: "none", score: null, zone: "neutral", label: "test" };
test("filtered-view CAGR uses calendar time for stocks and crypto, including cash periods", () => {
  for (const observations of [4, 1009, 1462]) {
    const growth = 1.1 ** 4;
    const daily = Array.from({ length: observations }, (_, i) => ({
      date: new Date(Date.UTC(2020, 0, 1) + Math.round(1461 * i / (observations - 1)) * 86400000).toISOString().slice(0, 10),
      state: i === observations - 1 ? 1 : 0,
      strat_ret: i === observations - 1 ? growth - 1 : 0,
      long_ret: i === observations - 1 ? growth - 1 : 0,
      short_ret: 0,
    }));
    const result = summariseView([], filterDaily(daily, true, false));
    close(result.strategy.total_return, growth - 1);
    close(result.strategy.cagr, .1);
  }
});
test("hiding shorts preserves the current long trailing stop", () => {
  const state = { state: "long", state_since: "2026-08-04", entry_price: 760.63,
    last_close: 773.17, unrealized_pct: .016, current_stop: 759.36 };
  const visible = [{ direction: "long", exit_date: null, initial_stop: 742.35 }];
  assert.equal(filterState(state, visible).current_stop, 759.36);
  assert.equal(filterState(state, []).current_stop, null);
});

test("direction filters retain exit-day costs and split a reversal day correctly", () => {
  const daily = [
    { date: "a", state: 1, strat_ret: -.01, long_ret: -.01, short_ret: 0 },
    { date: "b", state: -1, strat_ret: .8 * 1.1 - 1, long_ret: -.2, short_ret: .1 },
  ];
  close(compound(filterDaily(daily, true, false).map(d => d.strat_ret)).at(-1), .99 * .8);
  close(compound(filterDaily(daily, false, true).map(d => d.strat_ret)).at(-1), 1.1);
  close(compound(filterDaily(daily, true, true).map(d => d.strat_ret)).at(-1), .99 * .8 * 1.1);
  close(compound(filterDaily(daily, false, false).map(d => d.strat_ret)).at(-1), 1);
});


function allocationBoard() {
  return {status:'ok',computed_at:'2026-09-05T12:00:00Z',long:[],short:[],flat:[],watchlist:[],
    universe:Array.from({length:10},(_,i)=>({symbol:'TEST'+i,priority:true,bars:420,
      state:'long',state_since:'2026-08-01',last_date:'2026-09-05',last_close:100,
      atr_20:2,vol_60d:.1,asset_class:'Equities and other ETFs',quantity_increment:1,min_order_size:1}))};
}
test('flat allocations remain cash instead of concentrating the active signals',()=>{
  const b=allocationBoard();b.universe.slice(1).forEach(r=>r.state='flat');
  const r=computeAllocation(b,{...DEFAULT_PARAMS});
  assert.equal(r.eligible,10);assert.equal(r.rows.length,1);
  assert.ok(r.gross<10000 && r.free>90000);
  close(r.gross+r.costs+r.free,100000);
});
test('equal capital and inverse volatility use all eligible assets',()=>{
  const b=allocationBoard();b.universe[0].vol_60d=.2;
  const equal=computeAllocation(b,{...DEFAULT_PARAMS});
  const vol=computeAllocation(b,{...DEFAULT_PARAMS,method:'inverse-vol'});
  assert.equal(equal.rows[0].units,equal.rows[1].units);
  assert.ok(Math.abs(vol.rows[0].units*2-vol.rows[1].units)<=1);
});
test('both direction budgets coexist and aggregate symbol caps use gross exposure',()=>{
  const b=allocationBoard();b.universe=b.universe.slice(0,1);
  const row=b.universe[0];row.directions={long:{...row,state:'long'},short:{...row,state:'short'}};
  const r=computeAllocation(b,{...DEFAULT_PARAMS,book:'combined-initial',method:'capped-vol'});
  assert.equal(r.rows.length,2);assert.ok(r.rows[0].units>0&&r.rows[1].units<0);
  assert.ok(r.gross<=10000);close(r.gross+r.costs+r.free,100000);
});
test('pending exits are omitted and pending entries retain their side',()=>{
  const b=allocationBoard();
  b.universe[0].pending_action={action:'exit',direction:'long',signal_date:'2026-09-05'};
  b.universe[1].state='flat';b.universe[1].pending_action={action:'enter',direction:'long',signal_date:'2026-09-05'};
  const r=computeAllocation(b,{...DEFAULT_PARAMS});
  assert.ok(!r.rows.some(r=>r.symbol==='TEST0'));assert.ok(r.rows.find(r=>r.symbol==='TEST1').pending);
});
test('crypto increments and minimum sizes reconcile with unallocated capital',()=>{
  const b=allocationBoard();Object.assign(b.universe[0],{symbol:'BTC/USD',last_close:123456,quantity_increment:.0001,min_order_size:.001});
  const p={...DEFAULT_PARAMS};let r=computeAllocation(b,p);
  const btc=r.rows.find(r=>r.symbol==='BTC/USD');assert.ok(btc.units>0&&btc.units<1);
  close(btc.units/.0001,Math.round(btc.units/.0001));close(r.gross+r.costs+r.free,p.capital);
  b.universe[0].min_order_size=1;r=computeAllocation(b,p);assert.equal(r.rows.find(r=>r.symbol==='BTC/USD').units,0);
});
test('missing volatility and stale histories are excluded without an invented volatility',()=>{
  const b=allocationBoard();b.universe[0].vol_60d=null;b.universe[1].last_date='2020-01-01';
  const r=computeAllocation(b,{...DEFAULT_PARAMS});assert.equal(r.eligible,8);
});
test('independent direction views preserve the combined account return',()=>{
  const d=[{date:'2026-01-01',state:2,long_active:true,short_active:true,long_ret:.2,short_ret:-.2,strat_ret:0}];
  close(filterDaily(d,true,true)[0].strat_ret,0);
  close(filterDaily(d,true,false)[0].strat_ret,.2);
  close(filterDaily(d,false,true)[0].strat_ret,-.2);
});
