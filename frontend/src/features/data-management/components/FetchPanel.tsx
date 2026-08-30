import { useCallback, useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { ApiError } from "@/shared/api/client";

import { dataApi } from "../api";
import type { FetchKind, RunStatus } from "../types";

interface FetchPanelProps {
  kind: FetchKind;
  allowFullMode?: boolean;
  scope?: "all" | "watchlist" | "single";
  scopeArg?: string;
  buttonLabel?: string;
  onDone?: () => void;
}

const STATUS_COLOR = {
  succeeded: "success",
  failed: "error",
  cancelled: "warning",
  running: "info",
  queued: "default",
} as const;

const fmt = (n: number) => n.toLocaleString();
const ACTIVE = (s: string) => s === "running" || s === "queued";

export function FetchPanel({
  kind,
  allowFullMode = false,
  scope = "all",
  scopeArg,
  buttonLabel = "Fetch",
  onDone,
}: FetchPanelProps) {
  const [run, setRun] = useState<RunStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const doneNotified = useRef(false);

  const poll = useCallback(
    async (id: number) => {
      try {
        const status = await dataApi.run(id);
        setRun(status);
        if (ACTIVE(status.status)) {
          timer.current = window.setTimeout(() => poll(id), 1000);
        } else if (!doneNotified.current) {
          doneNotified.current = true;
          onDone?.();
        }
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Lost track of the run");
      }
    },
    [onDone],
  );

  // On mount / kind change: re-attach to a run of this kind that is still going
  // (survives a page refresh).
  useEffect(() => {
    let cancelled = false;
    dataApi
      .activeRuns()
      .then((runs) => {
        const mine = runs.find((r) => r.kind === kind && ACTIVE(r.status));
        if (mine && !cancelled) {
          doneNotified.current = false;
          setRun(mine);
          setNote("Reattached to a fetch already in progress.");
          poll(mine.id);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
      window.clearTimeout(timer.current);
    };
  }, [kind, poll]);

  async function start(mode: "incremental" | "full") {
    setError(null);
    setNote(null);
    setRun(null);
    doneNotified.current = false;
    try {
      const { run_id, deduped } = await dataApi.startRun({
        kind,
        mode,
        scope,
        scope_arg: scopeArg,
      });
      if (deduped) setNote("A fetch of this kind is already running — showing that one.");
      poll(run_id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the fetch");
    }
  }

  async function cancel() {
    if (run) await dataApi.cancelRun(run.id).catch(() => undefined);
  }

  const busy = run ? ACTIVE(run.status) : false;
  const pct =
    run && run.planned_targets > 0
      ? Math.round((run.completed_targets / run.planned_targets) * 100)
      : 0;

  return (
    <Box>
      <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
        <Button variant="contained" disabled={busy} onClick={() => start("incremental")}>
          {busy ? (run?.status === "queued" ? "Queued…" : "Running…") : buttonLabel}
        </Button>
        {allowFullMode && (
          <Button variant="outlined" disabled={busy} onClick={() => start("full")}>
            Full re-fetch
          </Button>
        )}
        {busy && (
          <Button color="inherit" onClick={cancel}>
            Cancel
          </Button>
        )}
        {run && !busy && (
          <Chip
            size="small"
            color={STATUS_COLOR[run.status]}
            label={`${run.status} · ${fmt(run.completed_targets)}/${fmt(run.planned_targets)} · ${fmt(
              run.rows_written,
            )} rows`}
          />
        )}
      </Stack>

      {run && run.status === "queued" && (
        <Box sx={{ mt: 1.5 }}>
          <LinearProgress />
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
            Queued behind another fetch — the worker runs one at a time.
            {run.queue_depth > 0 ? ` ${run.queue_depth} ahead.` : ""}
          </Typography>
        </Box>
      )}

      {run && run.status === "running" && (
        <Box sx={{ mt: 1.5 }}>
          <LinearProgress variant={run.planned_targets ? "determinate" : "indeterminate"} value={pct} />
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
            {fmt(run.completed_targets)} / {fmt(run.planned_targets)} targets
            {run.failed_targets > 0 ? ` · ${run.failed_targets} failed` : ""} · {fmt(run.rows_written)}{" "}
            rows · {fmt(run.requests_made)} requests
            {run.current_target ? ` · now: ${run.current_target}` : ""}
          </Typography>
        </Box>
      )}

      {note && (
        <Alert severity="info" sx={{ mt: 1 }} onClose={() => setNote(null)}>
          {note}
        </Alert>
      )}
      {run && run.status === "failed" && run.error_summary && (
        <Alert severity="warning" sx={{ mt: 1 }}>
          {run.error_summary} — see Run history for per-target errors.
        </Alert>
      )}
      {error && (
        <Alert severity="error" sx={{ mt: 1 }}>
          {error}
        </Alert>
      )}
    </Box>
  );
}
