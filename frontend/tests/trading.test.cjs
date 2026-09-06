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
const { computeSizing } = require("../src/features/sizing/engine.ts");
const { zeroDeployed } = require("../src/features/sizing/constants.ts");
const { filterDaily, filterState, compound } = require("../src/features/timing/metrics.ts");
const close = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-8, `${actual} != ${expected}`);
const macro = { source: "none", score: null, zone: "neutral", label: "test" };
const params = () => ({ nav: 1e6, volTargetPct: 12, kMax: 1, perNameCapPct: 10,
  perSectorCapPct: 30, bookVolOverridePct: null, enforceSleeveBudget: false, sleeveBudget: {},
  scopeLong: true, scopeShort: false, shortResearchOnly: false, scopeWatchlist: false,
  mode: "full", newDays: 10, macroEnabled: false, neutralScale: .65, riskOffScale: .35,
  deployed: zeroDeployed() });
function board() {
  const sectors = ["Information Technology", "Energy", "Financials", "Health Care", "Industrials"];
  return { status: "ok", computed_at: "2026-09-05T12:00:00Z", short: [], flat: [], watchlist: [],
    long: Array.from({ length: 10 }, (_, i) => ({ symbol: `TEST${i}`, state: "long",
      state_since: "2026-09-01", last_close: 100, vol_60d: .10, sector: sectors[i % 5] })) };
}

test("entering the proposed holdings does not shrink the target or tell you to sell half", () => {
  const b = board(), p = params();
  const flat = computeSizing(b, p, macro);
  close(flat.targetGrossPct, 100);
  for (const l of flat.sleeveLoads) p.deployed[l.sleeve] = l.targetPct;
  const held = computeSizing(b, p, macro);
  close(held.targetGrossPct, 100);
  close(held.headroomPct, 0);
  close(held.overshootPct, 0);
  assert.ok(held.rows.every(r => r.verdict === "BLOCKED"));
  for (const l of held.sleeveLoads) { close(l.newPct, 0); close(l.trimPct, 0); }
});

test("crowded holdings change add/trim cues, not total target weights", () => {
  const b = board(), p = params();
  const flat = computeSizing(b, p, macro);
  p.deployed.Energy = 40;
  const held = computeSizing(b, p, macro);
  assert.deepEqual(held.rows.map(r => r.targetUsd), flat.rows.map(r => r.targetUsd));
  const energy = held.sleeveLoads.find(l => l.sleeve === "Energy");
  close(energy.targetPct, 20); close(energy.trimPct, 20); close(energy.newPct, 0);
  assert.ok(held.rows.filter(r => r.sleeve === "Energy").every(r => r.verdict === "TRIM"));
});

test("quantity rounding and cash agree; zero-unit targets never say ADD", () => {
  const b = board(), p = params();
  b.long[0].last_close = 200000;
  const r = computeSizing(b, p, macro);
  const zero = r.rows.find(r => r.symbol === "TEST0");
  assert.equal(zero.shares, 0); assert.equal(zero.verdict, "WAIT"); close(zero.targetUsd, 0);
  close(r.targetGrossPct, r.rows.reduce((a, r) => a + r.shares * r.lastClose / p.nav * 100, 0));
  close(r.cashAfterPct, 100 - r.targetGrossPct);
});

test("crypto uses fractional provider increments and minimum size", () => {
  const b = board(), p = params();
  b.long[0] = { ...b.long[0], symbol: "BTC/USD", last_close: 123456,
    quantity_increment: .0001, min_order_size: .001 };
  const r = computeSizing(b, p, macro).rows.find(r => r.symbol === "BTC/USD");
  assert.ok(r.shares > 0 && r.shares < 1);
  close(r.shares / .0001, Math.round(r.shares / .0001));
  close(r.targetUsd, r.shares * 123456);
  b.long[0].min_order_size = 1;
  const blocked = computeSizing(b, p, macro).rows.find(r => r.symbol === "BTC/USD");
  assert.equal(blocked.shares, 0); assert.equal(blocked.verdict, "WAIT");
});

test("recent-entry view preserves full-book targets and comparisons", () => {
  const b = board(), p = params();
  b.long[0].state_since = "2020-01-01";
  const all = computeSizing(b, p, macro);
  p.mode = "new";
  const recent = computeSizing(b, p, macro);
  assert.equal(recent.rows.length, 9);
  close(recent.targetGrossPct, all.targetGrossPct);
  assert.deepEqual(recent.sleeveLoads, all.sleeveLoads);
});

test("pending entries can be sized and pending exits leave the target", () => {
  const b = board(), p = params();
  b.long[0].pending_action = { action: "exit", direction: "long", signal_date: "2026-09-05" };
  b.pending = [{ ...b.long[1], symbol: "NEW", state: "flat", state_since: null,
    pending_action: { action: "enter", direction: "long", signal_date: "2026-09-05" } }];
  const r = computeSizing(b, p, macro);
  assert.ok(!r.rows.some(r => r.symbol === "TEST0"));
  assert.ok(r.rows.some(r => r.symbol === "NEW" && r.state === "long" && r.shares > 0));
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
