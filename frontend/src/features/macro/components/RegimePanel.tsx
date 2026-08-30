import { useCallback, useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import LinearProgress from "@mui/material/LinearProgress";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import TuneIcon from "@mui/icons-material/Tune";

import { ApiError } from "@/shared/api/client";

import { macroApi } from "../api";
import type { BudgetPreset, ModelOption, RegimeMessage, RegimeRun } from "../types";
import { RegimeControls } from "./RegimeControls";
import { RegimeGauge } from "./RegimeGauge";

const LS_MODEL = "th.regime.model";
const LS_BUDGET = "th.regime.budget";
const LS_CONTROLS = "th.regime.controls";

function readLS(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function writeLS(key: string, v: string) {
  try {
    localStorage.setItem(key, v);
  } catch {
    /* ignore */
  }
}

function personaLabel(m: RegimeMessage): string {
  const p = m.persona ?? "reconciler";
  return m.role === "rebuttal" ? `${p} (rebuttal)` : p;
}

function PersonaRow({ m }: { m: RegimeMessage }) {
  let parsed: Record<string, unknown> = {};
  try {
    parsed = JSON.parse(m.parsed_json ?? "{}");
  } catch {
    /* ignore */
  }
  const evidence = Array.isArray(parsed.key_evidence) ? (parsed.key_evidence as string[]) : [];
  return (
    <Box sx={{ py: 1 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {personaLabel(m)}
        </Typography>
        {m.vote && (
          <Chip
            size="small"
            label={`${m.vote}${m.conviction != null ? ` · ${Math.round(m.conviction)}` : ""}`}
            color={m.vote === "ON" ? "success" : m.vote === "OFF" ? "error" : "default"}
            variant="outlined"
          />
        )}
      </Stack>
      {typeof parsed.rationale === "string" && (
        <Typography variant="body2" color="text.secondary">
          {parsed.rationale}
        </Typography>
      )}
      {evidence.length > 0 && (
        <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
          {evidence.map((e, i) => (
            <li key={i}>
              <Typography variant="caption" color="text.secondary">
                {e}
              </Typography>
            </li>
          ))}
        </ul>
      )}
    </Box>
  );
}

export function RegimePanel({ naiveScore }: { naiveScore: number | null }) {
  const [models, setModels] = useState<ModelOption[]>([]);
  const [budgets, setBudgets] = useState<BudgetPreset[]>([]);
  const [model, setModel] = useState<string>(readLS(LS_MODEL) ?? "");
  const [budget, setBudget] = useState<"small" | "medium" | "large">(
    (readLS(LS_BUDGET) as "small" | "medium" | "large") ?? "medium",
  );
  const [run, setRun] = useState<RegimeRun | null>(null);
  const [loadedRun, setLoadedRun] = useState(false);
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [showControls, setShowControls] = useState(readLS(LS_CONTROLS) === "1");
  const [showDetails, setShowDetails] = useState(false);
  const tick = useRef<number | undefined>(undefined);
  const loadedControls = useRef(false);

  // The dashboard is always shown — fetch the last run on mount (cheap, local).
  useEffect(() => {
    void macroApi.latestRegime().then((r) => {
      if (r && "id" in r) setRun(r as RegimeRun);
      setLoadedRun(true);
    });
  }, []);

  // If there is no run yet, open the controls so it is obvious how to run one.
  useEffect(() => {
    if (loadedRun && !run && readLS(LS_CONTROLS) === null) setShowControls(true);
  }, [loadedRun, run]);

  // Model/budget lists (the models call pings OpenAI /v1/models) — only when
  // the operable area is first shown.
  useEffect(() => {
    if (!showControls || loadedControls.current) return;
    loadedControls.current = true;
    void macroApi.models().then((r) => {
      setModels(r.models);
      setModel((cur) => (cur && r.models.some((m) => m.id === cur) ? cur : r.default));
    });
    void macroApi.budgets().then(setBudgets);
  }, [showControls]);

  useEffect(() => {
    if (running) {
      setElapsed(0);
      tick.current = window.setInterval(() => setElapsed((e) => e + 1), 1000);
    } else {
      window.clearInterval(tick.current);
    }
    return () => window.clearInterval(tick.current);
  }, [running]);

  const today = new Date().toISOString().slice(0, 10);
  const hasRunToday = run?.trading_date === today;

  const toggleControls = () => {
    const next = !showControls;
    setShowControls(next);
    writeLS(LS_CONTROLS, next ? "1" : "0");
  };

  const doRun = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      const result = await macroApi.runRegime({ model, budget, force: hasRunToday });
      setRun(result);
      writeLS(LS_MODEL, model);
      writeLS(LS_BUDGET, budget);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The AI run failed");
    } finally {
      setRunning(false);
    }
  }, [model, budget, hasRunToday]);

  const personaMsgs = (run?.messages ?? []).filter((m) => m.role !== "reconciler");

  return (
    <Paper sx={{ p: 2.5, width: "100%" }}>
      <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between" }}>
        <Typography variant="overline" color="text.secondary">
          AI regime estimate — adversarial voting
        </Typography>
        <Button
          size="small"
          startIcon={<TuneIcon fontSize="small" />}
          onClick={toggleControls}
          color="inherit"
        >
          {showControls ? "Hide" : "Re-run / model"}
        </Button>
      </Stack>

      {/* ---- dashboard (always visible) ---- */}
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 3, mt: 1, alignItems: "flex-start" }}>
        <RegimeGauge
          score={run?.score ?? null}
          confidence={run?.confidence ?? null}
          onVotes={run?.on_votes ?? 0}
          offVotes={run?.off_votes ?? 0}
          neutralVotes={run?.neutral_votes ?? 0}
        />

        <Box sx={{ flex: 1, minWidth: 280 }}>
          {run?.summary ? (
            <Typography variant="body2" sx={{ mb: 1 }}>
              {run.summary}
            </Typography>
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              No AI estimate yet — open <strong>Re-run / model</strong> and run one.
            </Typography>
          )}

          {run && (run.code_weighted_score != null || run.reconciler_score != null) && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
              Score = ½ weighted-vote ({run.code_weighted_score ?? "—"}) + ½ reconciler (
              {run.reconciler_score ?? "—"}) → {run.score_raw}
              {(() => {
                if (!run.weights_json) return "";
                try {
                  const w = JSON.parse(run.weights_json) as Record<string, number>;
                  return ` · weights: ${Object.entries(w)
                    .map(([k, v]) => `${k.replace("_", "/")} ${Math.round(v * 100)}%`)
                    .join(", ")}`;
                } catch {
                  return "";
                }
              })()}
            </Typography>
          )}

          {run?.calibration_notes && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
              Calibration: {run.score_raw} → {run.score}; confidence {run.confidence_raw} →{" "}
              {run.confidence}. {run.calibration_notes}.
            </Typography>
          )}

          {run && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              {run.model} · {run.budget} · prompt v{run.prompt_version} · {run.trading_date} ·{" "}
              {run.prompt_tokens ?? 0}+{run.completion_tokens ?? 0} tok
              {run.cost_estimate_usd != null
                ? ` · ~$${run.cost_estimate_usd.toFixed(4)}`
                : " · cost est. n/a"}
              {naiveScore != null ? ` · naive composite ${naiveScore}` : ""}
            </Typography>
          )}

          {personaMsgs.length > 0 && (
            <>
              <Link
                component="button"
                variant="caption"
                onClick={() => setShowDetails((v) => !v)}
                sx={{ mt: 1, display: "inline-block" }}
              >
                {showDetails ? "Hide" : "Show"} each analyst's vote & reasoning
              </Link>
              <Collapse in={showDetails}>
                <Box sx={{ mt: 1 }}>
                  {personaMsgs.map((m) => (
                    <PersonaRow key={m.seq} m={m} />
                  ))}
                </Box>
              </Collapse>
            </>
          )}
        </Box>
      </Box>

      {running && (
        <Box sx={{ mt: 2 }}>
          <LinearProgress />
          <Typography variant="caption" color="text.secondary">
            Asking {budgets.find((b) => b.key === budget)?.personas.length ?? 5} analysts + a
            reconciler… {elapsed}s
          </Typography>
        </Box>
      )}

      {error && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {error}
        </Alert>
      )}

      {/* ---- operable area (hidden by default) ---- */}
      <Collapse in={showControls}>
        <Divider sx={{ my: 2 }} />
        <RegimeControls
          models={models}
          budgets={budgets}
          model={model}
          budget={budget}
          onModel={setModel}
          onBudget={setBudget}
          onRun={doRun}
          running={running}
          hasRunToday={hasRunToday}
        />
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>
          Cached once per day — “Re-run” forces a fresh run (e.g. to try a pricier model).
        </Typography>
      </Collapse>

      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2 }}>
        AI-generated estimate. It may be wrong. Not investment advice. Naive-v1, not
        statistically validated.
      </Typography>
    </Paper>
  );
}
