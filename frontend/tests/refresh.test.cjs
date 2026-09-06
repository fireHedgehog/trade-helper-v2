const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const ts = require("typescript");
require.extensions[".ts"] = (module, filename) => {
  module._compile(ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    fileName: filename,
  }).outputText, filename);
};
const { createRefreshWorkflow, REFRESH_STEPS, refreshProgress } = require("../src/features/data-management/refresh.ts");

function fixture() {
  const calls = [], jobs = new Map();
  const api = {
    startRun: async (body) => {
      calls.push(body); const id = jobs.size + 1; jobs.set(id, body);
      return { run_id: id, deduped: false };
    },
    run: async (id) => ({ id, ...jobs.get(id), status: "succeeded", completed_targets: 1,
      planned_targets: 1, failed_targets: 0 }),
    baseline: async () => calls.push("baseline"),
    ranking: async () => calls.push("ranking"),
    wait: async () => {},
  };
  return { api, calls, jobs };
}

test("one click uses every existing fetch in dependency order, baseline and ranking before Trend, no AI", async () => {
  const { api, calls } = fixture();
  const flow = createRefreshWorkflow(api);
  await flow.start("incremental");
  assert.deepEqual(calls.map(c => typeof c === "string" ? c : c.kind), [
    "asset_catalog", "memberships", "asset_prices", "crypto_bars", "commodity_prices",
    "macro", "option_snapshots", "baseline", "ranking", "signal_universe",
  ]);
  assert.ok(calls.filter(c => typeof c === "object").every(c => c.mode === "incremental" && c.scope === "all"));
  assert.equal(flow.getSnapshot().phase, "done");
  assert.equal(refreshProgress(flow.getSnapshot()), 100);
});

test("full history choice reaches the existing fetch endpoints", async () => {
  const { api, calls } = fixture();
  await createRefreshWorkflow(api).start("full");
  assert.ok(calls.filter(c => typeof c === "object").every(c => c.mode === "full"));
});

test("a partial failure stops downstream computations and retry resumes that step", async () => {
  const { api, calls, jobs } = fixture();
  const success = api.run;
  api.run = async id => jobs.get(id).kind === "asset_prices"
    ? { ...await success(id), status: "failed", failed_targets: 1, error_summary: "One symbol failed" }
    : success(id);
  const flow = createRefreshWorkflow(api);
  await flow.start("incremental");
  assert.equal(flow.getSnapshot().phase, "failed");
  assert.equal(flow.getSnapshot().step, 2);
  assert.equal(calls.length, 3);
  api.run = success;
  await flow.resume();
  assert.equal(flow.getSnapshot().phase, "done");
  assert.equal(calls.filter(c => c.kind === "asset_catalog").length, 1);
  assert.equal(calls.filter(c => c.kind === "asset_prices").length, 2);
});

test("lost polling connection retains the run id so retry does not submit twice", async () => {
  const { api, calls } = fixture();
  const success = api.run;
  api.run = async () => { throw Error("Connection lost"); };
  const flow = createRefreshWorkflow(api);
  await flow.start("incremental");
  assert.equal(flow.getSnapshot().runId, 1);
  api.run = success;
  await flow.resume();
  assert.equal(flow.getSnapshot().phase, "done");
  assert.equal(calls.filter(c => c.kind === "asset_catalog").length, 1);
});

test("pause finishes the current step; resume continues without repeating it", async () => {
  const { api, calls } = fixture();
  const success = api.run;
  const flow = createRefreshWorkflow(api);
  api.run = async id => { flow.pause(); return success(id); };
  await flow.start("incremental");
  assert.equal(flow.getSnapshot().phase, "paused");
  assert.equal(flow.getSnapshot().step, 1);
  assert.equal(calls.length, 1);
  api.run = success;
  await flow.resume();
  assert.equal(flow.getSnapshot().phase, "done");
});

test("reloading pauses the sequence and resumes the submitted job without another fetch", async () => {
  const { api, calls } = fixture();
  const saved = { phase: "running", mode: "incremental", step: 2, runId: 42,
    run: null, error: null, pauseRequested: false };
  const flow = createRefreshWorkflow(api, saved);
  assert.equal(flow.getSnapshot().phase, "paused");
  assert.equal(calls.length, 0);
  await flow.resume();
  assert.equal(flow.getSnapshot().phase, "done");
  assert.equal(calls[0].kind, "crypto_bars");
});

test("an unrelated deduplicated fetch is not mistaken for this workflow's completed step", async () => {
  const { api, calls } = fixture();
  api.startRun = async () => ({ run_id: 99, deduped: true });
  const flow = createRefreshWorkflow(api);
  await flow.start("full");
  assert.equal(flow.getSnapshot().phase, "failed");
  assert.equal(flow.getSnapshot().step, 0);
  assert.equal(flow.getSnapshot().runId, null);
  assert.equal(calls.length, 0);
});

test("double clicks cannot launch duplicate workflows; queued targets contribute real progress", async () => {
  const { api, calls } = fixture();
  let release;
  api.wait = () => new Promise(resolve => { release = resolve; });
  const success = api.run;
  api.run = async id => ({ ...await success(id), status: "running", planned_targets: 10, completed_targets: 5 });
  const flow = createRefreshWorkflow(api);
  const started = flow.start("incremental");
  while (!release) await Promise.resolve();
  await flow.start("full");
  assert.equal(calls.length, 1);
  assert.equal(refreshProgress(flow.getSnapshot()), 50 / REFRESH_STEPS.length);
  api.run = success;
  release();
  await started;
  assert.equal(flow.getSnapshot().phase, "done");
});
