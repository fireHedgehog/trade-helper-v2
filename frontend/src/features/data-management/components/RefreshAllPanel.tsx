import { useEffect, useState, useSyncExternalStore } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import FormControlLabel from "@mui/material/FormControlLabel";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { macroApi } from "@/features/macro/api";
import { multisectionalApi } from "@/features/multisectional/api";
import { dataApi } from "../api";
import { createRefreshWorkflow, REFRESH_STEPS, refreshProgress, type RefreshState } from "../refresh";

const STORAGE_KEY = "trade-helper.refresh-workflow";
function restore(): RefreshState | undefined {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null") as RefreshState | null;
    if (saved && Number.isInteger(saved.step) && saved.step >= 0 && saved.step <= REFRESH_STEPS.length
      && ["incremental", "full"].includes(saved.mode)
      && ["idle", "running", "paused", "failed", "done"].includes(saved.phase)) return saved;
  } catch { /* No saved session. */ }
}

const workflow = createRefreshWorkflow({
  startRun: dataApi.startRun,
  run: dataApi.run,
  baseline: macroApi.overview,
  ranking: multisectionalApi.recompute,
  wait: () => new Promise((resolve) => window.setTimeout(resolve, 1000)),
  save: (state) => {
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch { /* Storage unavailable. */ }
  },
}, restore());

export function RefreshAllPanel({ onDone }: { onDone: () => void }) {
  const state = useSyncExternalStore(workflow.subscribe, workflow.getSnapshot);
  const [full, setFull] = useState(state.mode === "full");
  const busy = state.phase === "running";
  const resumable = state.phase === "paused" || state.phase === "failed";
  const current = REFRESH_STEPS[state.step];
  const pct = refreshProgress(state);
  useEffect(() => { if (state.phase === "done") onDone(); }, [state.phase, onDone]);

  return (
    <Paper sx={{ p: 2.5, mb: 2, border: 1, borderColor: "primary.main" }}>
      <Typography variant="h6">Refresh everything</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        Fetch all data, then refresh the Naive composite, Multisectional ranking and Trend.
        AI Macro is never run by this button.
      </Typography>
      <Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: "center", flexWrap: "wrap" }}>
        <Button variant="contained" disabled={busy || resumable} onClick={() => void workflow.start(full ? "full" : "incremental")}>
          Refresh everything
        </Button>
        <FormControlLabel control={<Checkbox checked={full} disabled={busy || resumable}
          onChange={(event) => setFull(event.target.checked)} />} label="Full history re-fetch" />
        {busy && <Button disabled={state.pauseRequested} onClick={workflow.pause}>
          {state.pauseRequested ? "Pausing after this step…" : "Pause after this step"}
        </Button>}
        {resumable && <Button variant="contained" onClick={() => void workflow.resume()}>
          {state.phase === "failed" ? "Retry current step" : "Resume refresh"}
        </Button>}
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 2 }}>
        Incremental checks recent adjusted prices and repairs changed symbols automatically.
        New symbols receive their available history. Full mode re-fetches
        history; option snapshots remain current snapshots.
      </Typography>
      <Stack direction="row" sx={{ justifyContent: "space-between", mb: 1 }}>
        <Typography variant="subtitle2" aria-live="polite">
          {state.phase === "idle" ? "Ready · 10 steps" : state.phase === "done" ? "Refresh complete · 10 / 10 steps"
            : `${state.phase === "paused" ? "Paused · " : state.phase === "failed" ? "Stopped · " : ""}Step ${state.step + 1} / 10 · ${current?.label}`}
        </Typography>
        <Typography variant="subtitle2">{Math.floor(pct)}%</Typography>
      </Stack>
      <LinearProgress aria-label="Overall refresh progress" variant="determinate" value={pct}
        color={state.phase === "failed" ? "error" : state.phase === "done" ? "success" : "primary"}
        sx={{ height: 14, borderRadius: 2 }} />
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, mt: 1.5 }}>
        {REFRESH_STEPS.map((step, i) => <Chip key={step.label} size="small"
          label={`${i < state.step ? "✓" : i + 1} ${step.label}`}
          color={i < state.step ? "success" : i === state.step && state.phase !== "idle" ? "primary" : "default"}
          variant={i < state.step || i === state.step && busy ? "filled" : "outlined"} />)}
      </Box>
      {state.run && <Typography variant="body2" sx={{ mt: 1 }}>
        {state.run.status} · {state.run.completed_targets} / {state.run.planned_targets} targets
        {state.run.current_target ? ` · ${state.run.current_target}` : ""}
        {state.run.failed_targets > 0 ? ` · ${state.run.failed_targets} failed` : ""}
      </Typography>}
      {busy && <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
        You can navigate within the app. After reloading this tab, return here and press Resume refresh.
        Progress measures steps and targets, not time remaining.
      </Typography>}
      {state.error && <Alert severity="error" sx={{ mt: 1.5 }}>
        {state.error} Later steps have not run.
      </Alert>}
      {state.phase === "paused" && <Alert severity="info" sx={{ mt: 1.5 }}>
        Resume continues from this step and checks any fetch already submitted.
      </Alert>}
      {state.phase === "done" && <Alert severity="success" sx={{ mt: 1.5 }}>
        Data, baseline macro, ranking and Trend refreshed. The saved AI assessment is unchanged.
      </Alert>}
    </Paper>
  );
}
