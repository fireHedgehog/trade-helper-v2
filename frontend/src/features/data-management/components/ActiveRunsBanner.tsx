import { useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import LinearProgress from "@mui/material/LinearProgress";
import Typography from "@mui/material/Typography";

import { dataApi } from "../api";
import type { RunStatus } from "../types";

const fmt = (n: number) => n.toLocaleString();

/** Always-visible summary of whatever the fetch worker is doing right now,
 *  so a page refresh never loses track of an in-flight fetch. */
export function ActiveRunsBanner({ onSettled }: { onSettled?: () => void }) {
  const [runs, setRuns] = useState<RunStatus[]>([]);
  const hadRuns = useRef(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const active = await dataApi.activeRuns();
        if (stop) return;
        setRuns(active);
        if (hadRuns.current && active.length === 0) onSettled?.();
        hadRuns.current = active.length > 0;
      } catch {
        /* ignore */
      }
      if (!stop) timer.current = window.setTimeout(tick, 2000);
    };
    void tick();
    return () => {
      stop = true;
      window.clearTimeout(timer.current);
    };
  }, [onSettled]);

  if (runs.length === 0) return null;

  return (
    <Alert severity="info" icon={false} sx={{ mb: 2 }}>
      <Typography variant="subtitle2">Fetch worker is busy</Typography>
      {runs.map((r) => (
        <Box key={r.id} sx={{ mt: 1 }}>
          <Typography variant="caption" color="text.secondary">
            #{r.id} {r.kind} ({r.mode}) — {r.status}
            {r.status === "running"
              ? ` · ${fmt(r.completed_targets)}/${fmt(r.planned_targets)} · ${fmt(
                  r.rows_written,
                )} rows${r.current_target ? ` · now ${r.current_target}` : ""}`
              : " · waiting for the worker"}
          </Typography>
          <LinearProgress
            variant={
              r.status === "running" && r.planned_targets
                ? "determinate"
                : "indeterminate"
            }
            value={
              r.planned_targets ? (r.completed_targets / r.planned_targets) * 100 : 0
            }
          />
        </Box>
      ))}
    </Alert>
  );
}
