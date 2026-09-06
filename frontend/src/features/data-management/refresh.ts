import type { FetchKind, RunStatus } from "./types";

export const REFRESH_STEPS: { label: string; kind?: FetchKind }[] = [
  { label: "Asset catalog", kind: "asset_catalog" },
  { label: "Memberships", kind: "memberships" },
  { label: "Asset prices", kind: "asset_prices" },
  { label: "Crypto", kind: "crypto_bars" },
  { label: "Commodities", kind: "commodity_prices" },
  { label: "Macro data", kind: "macro" },
  { label: "Option snapshots", kind: "option_snapshots" },
  { label: "Naive composite" },
  { label: "Multisectional" },
  { label: "Trend", kind: "signal_universe" },
];

type Mode = "incremental" | "full";
export interface RefreshState {
  phase: "idle" | "running" | "paused" | "failed" | "done";
  mode: Mode;
  step: number;
  runId: number | null;
  run: RunStatus | null;
  error: string | null;
  pauseRequested: boolean;
}

interface Dependencies {
  startRun: (body: { kind: FetchKind; mode: Mode; scope: "all" }) => Promise<{ run_id: number; deduped: boolean }>;
  run: (id: number) => Promise<RunStatus>;
  baseline: () => Promise<unknown>;
  ranking: () => Promise<unknown>;
  wait: () => Promise<void>;
  save?: (state: RefreshState) => void;
}

// UI sequencing only. Fetches and calculations retain their existing endpoints.
// The controller outlives the page so navigating within the app does not stop it.
export function createRefreshWorkflow(api: Dependencies, saved?: RefreshState) {
  let state: RefreshState = saved ? { ...saved,
    phase: saved.phase === "running" ? "paused" : saved.phase,
    pauseRequested: false,
  } : { phase: "idle", mode: "incremental", step: 0, runId: null,
    run: null, error: null, pauseRequested: false };
  let busy = false;
  const listeners = new Set<() => void>();
  function update(patch: Partial<RefreshState>) {
    state = { ...state, ...patch };
    api.save?.(state);
    listeners.forEach((listener) => listener());
  }

  async function execute() {
    if (busy) return;
    busy = true;
    update({ phase: "running", error: null, pauseRequested: false });
    try {
      while (state.step < REFRESH_STEPS.length) {
        const step = REFRESH_STEPS[state.step];
        if (step.kind) {
          if (state.runId === null) {
            const started = await api.startRun({ kind: step.kind, mode: state.mode, scope: "all" });
            if (started.deduped) {
              throw new Error("A separate run of this step is already active. Let it finish, then retry this step.");
            }
            update({ runId: started.run_id });
          }
          while (true) {
            const run = await api.run(state.runId!);
            update({ run });
            if (run.status === "queued" || run.status === "running") {
              await api.wait();
              continue;
            }
            if (run.status !== "succeeded" || run.failed_targets > 0) {
              update({ runId: null });
              throw new Error(run.error_summary || `Run ${run.status}. See Run history for the affected targets.`);
            }
            break;
          }
        } else if (step.label === "Naive composite") {
          await api.baseline();
        } else {
          await api.ranking();
        }
        update({ step: state.step + 1, runId: null, run: null });
        if (state.pauseRequested && state.step < REFRESH_STEPS.length) {
          update({ phase: "paused", pauseRequested: false });
          return;
        }
      }
      update({ phase: "done", pauseRequested: false });
    } catch (error) {
      update({ phase: "failed", error: error instanceof Error ? error.message : String(error) });
    } finally {
      busy = false;
    }
  }

  return {
    getSnapshot: () => state,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    start: (mode: Mode) => {
      if (busy) return Promise.resolve();
      update({ phase: "idle", mode, step: 0, runId: null, run: null, error: null });
      return execute();
    },
    resume: execute,
    pause: () => { if (busy) update({ pauseRequested: true }); },
  };
}

export function refreshProgress(state: RefreshState): number {
  if (state.phase === "done") return 100;
  const run = state.run;
  const fraction = run && run.planned_targets > 0
    ? Math.min(.99, run.completed_targets / run.planned_targets) : 0;
  return Math.min(99, (state.step + fraction) / REFRESH_STEPS.length * 100);
}
