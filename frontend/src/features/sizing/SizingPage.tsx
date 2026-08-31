import { useCallback, useDeferredValue, useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import FormControlLabel from "@mui/material/FormControlLabel";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { ApiError } from "@/shared/api/client";

import { sizingApi } from "./api";
import { computeSizing } from "./engine";
import {
  DEFAULT_SLEEVE_BUDGET,
  amber,
  green,
  grey,
  zeroDeployed,
} from "./constants";
import { SizingControls } from "./components/SizingControls";
import { SizingTable } from "./components/SizingTable";
import { GrossBar, KmaxSensitivity, SectorBar } from "./components/SizingViz";
import type { MacroContext, SizingBoard, SizingParams, Verdict } from "./types";

const VERDICTS: Verdict[] = ["ADD", "LIGHT", "HOLD", "WAIT"];

const DEFAULT_PARAMS: SizingParams = {
  nav: 1_000_000,
  volTargetPct: 12,
  kMax: 1.0,
  perNameCapPct: 10,
  perSectorCapPct: 30,
  bookVolOverridePct: null,
  enforceSleeveBudget: false,
  sleeveBudget: { ...DEFAULT_SLEEVE_BUDGET },
  scopeLong: true,
  scopeShort: false,
  shortResearchOnly: false,
  scopeWatchlist: false,
  mode: "full",
  newDays: 10,
  macroEnabled: true,
  neutralScale: 0.65,
  riskOffScale: 0.35,
  deployed: zeroDeployed(),
};

const usd = (v: number) =>
  v >= 1e6 ? `$${(v / 1e6).toFixed(2)}M` : v >= 1e3 ? `$${(v / 1e3).toFixed(0)}k` : `$${v.toFixed(0)}`;

export function SizingPage() {
  const [board, setBoard] = useState<SizingBoard | null>(null);
  const [macro, setMacro] = useState<MacroContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [params, setParams] = useState<SizingParams>(DEFAULT_PARAMS);

  const load = useCallback(() => {
    setError(null);
    void Promise.all([sizingApi.board(), sizingApi.macro()])
      .then(([b, m]) => {
        setBoard(b);
        setMacro(m);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);
  useEffect(load, [load]);

  const patch = useCallback(
    (p: Partial<SizingParams>) => setParams((prev) => ({ ...prev, ...p })),
    [],
  );

  const [showVerdict, setShowVerdict] = useState<Record<Verdict, boolean>>({
    ADD: true,
    LIGHT: true,
    HOLD: true,
    WAIT: true,
  });

  const deferredParams = useDeferredValue(params);
  const result = useMemo(() => {
    if (!board || !macro) return null;
    return computeSizing(board, deferredParams, macro);
  }, [board, macro, deferredParams]);

  const verdictCounts = useMemo(() => {
    const c: Record<Verdict, number> = { ADD: 0, LIGHT: 0, HOLD: 0, WAIT: 0 };
    result?.rows.forEach((r) => (c[r.verdict] += 1));
    return c;
  }, [result]);
  const visibleRows = useMemo(
    () => (result ? result.rows.filter((r) => showVerdict[r.verdict]) : []),
    [result, showVerdict],
  );

  const notComputed = board?.status === "not_computed";
  const momentumMissing =
    !!board &&
    board.status === "ok" &&
    !board.long.some((r) => r.momentum) &&
    !board.short.some((r) => r.momentum);

  return (
    <div>
      <Typography variant="h5" gutterBottom>
        Sizing
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2, maxWidth: 920 }}>
        A real-time parameter sandbox for position sizing. It never places an order and adds no engine
        — it takes the Donchian board&apos;s on-signal names and answers <i>how big</i> under a set of
        risk-ladder assumptions you drag, and <i>what is holding each name back</i>. Drag a knob and
        the whole table re-computes.
      </Typography>

      <Alert severity="info" icon={false} sx={{ mb: 2, maxWidth: 920 }}>
        The <b>deployed-by-sleeve</b> table is a coarse proxy for your real book — it assumes your
        existing positions were themselves sized by these rules. If you are already concentrated,
        &quot;room to add&quot; here reads optimistic. Precise paste-your-holdings mode is a later
        add-on.
      </Alert>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      {notComputed && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          The Trend universe run has not been computed — run it on the <b>Trend</b> page. The sandbox
          works, but there are no board names to size yet.
        </Alert>
      )}
      {momentumMissing && (
        <Alert severity="info" sx={{ mb: 2 }}>
          No cross-sectional momentum on the board yet — recompute the <b>Multisectional</b> ranking
          once to light up the risk-off &quot;keep only the strongest&quot; filter and the mom.
          column.
        </Alert>
      )}
      {result && result.assumedVolCount > 0 && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {result.assumedVolCount} name{result.assumedVolCount === 1 ? " is" : "s are"} sized off a
          placeholder 25% vol — the last Trend universe run predates the 60-day-vol column. Re-run{" "}
          <b>Run trend backtest</b> on the Trend page for real inverse-vol weights.
        </Alert>
      )}

      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ alignItems: "flex-start" }}>
        <Paper
          sx={{
            p: 2,
            width: { xs: "100%", md: 360 },
            flexShrink: 0,
            position: { md: "sticky" },
            top: 16,
            maxHeight: { md: "calc(100vh - 32px)" },
            overflowY: { md: "auto" },
          }}
        >
          <Stack direction="row" sx={{ mb: 1, justifyContent: "space-between", alignItems: "center" }}>
            <Typography variant="subtitle2">Parameters</Typography>
            <Stack direction="row" spacing={1}>
              <Button size="small" onClick={() => setParams(DEFAULT_PARAMS)}>
                Reset
              </Button>
              <Button size="small" onClick={load}>
                Refresh
              </Button>
            </Stack>
          </Stack>
          {macro && <SizingControls params={params} onChange={patch} macro={macro} />}
        </Paper>

        <Box sx={{ flex: 1, minWidth: 0, width: "100%" }}>
          {!result || !macro ? (
            <Typography color="text.secondary">Loading board…</Typography>
          ) : (
            <Stack spacing={2}>
              <Hero result={result} params={params} macro={macro} />

              <Paper sx={{ p: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Gross exposure
                </Typography>
                <GrossBar result={result} kMaxPct={params.kMax * 100} />
                <Typography variant="body2" sx={{ mt: 1.5 }}>
                  {result.bindingConstraint}
                </Typography>
                <Stack direction="row" spacing={2} sx={{ mt: 1, flexWrap: "wrap" }}>
                  <Metric label="Deployed now" value={`${result.deployedGrossPct.toFixed(0)}%`} />
                  <Metric label="Target gross" value={`${result.targetGrossPct.toFixed(0)}%`} />
                  <Metric label="Cash after" value={`${result.cashAfterPct.toFixed(0)}%`} />
                  <Metric label="Max name" value={`${result.maxNamePct.toFixed(1)}%`} sub={`cap ${params.perNameCapPct}%`} />
                  <Metric
                    label="Est. book vol"
                    value={`${result.estBookVolPct.toFixed(0)}%`}
                    sub={`target ${params.volTargetPct}%`}
                  />
                </Stack>
              </Paper>

              <Stack direction={{ xs: "column", lg: "row" }} spacing={2}>
                <Paper sx={{ p: 2, flex: 2, minWidth: 0 }}>
                  <Typography variant="subtitle2" gutterBottom>
                    Sleeve load — deployed + proposed vs the {params.perSectorCapPct}% sector cap
                  </Typography>
                  {result.sleeveLoads.length ? (
                    <SectorBar result={result} />
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      Nothing deployed or proposed yet.
                    </Typography>
                  )}
                </Paper>
                <Paper sx={{ p: 2, flex: 1, minWidth: 200 }}>
                  <Typography variant="subtitle2" gutterBottom>
                    k_max sensitivity
                  </Typography>
                  <KmaxSensitivity result={result} current={params.kMax} />
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                    Resulting target gross as k_max moves.
                  </Typography>
                </Paper>
              </Stack>

              <Paper sx={{ p: 2 }}>
                <Stack direction="row" spacing={1} sx={{ mb: 0.5, flexWrap: "wrap", alignItems: "center" }}>
                  <Typography variant="subtitle2">Per-name sizing</Typography>
                  <Chip
                    size="small"
                    variant="outlined"
                    label={`${result.rows.length} names · ${result.rows.filter((r) => r.state === "long").length}L / ${result.rows.filter((r) => r.state === "short").length}S`}
                  />
                  {result.excluded.length > 0 && (
                    <Chip
                      size="small"
                      variant="outlined"
                      label={`${result.excluded.length} excluded`}
                    />
                  )}
                </Stack>
                <Stack
                  direction="row"
                  spacing={1}
                  sx={{ mb: 1, flexWrap: "wrap", alignItems: "center" }}
                >
                  <Typography variant="caption" color="text.secondary">
                    show:
                  </Typography>
                  {VERDICTS.map((v) => (
                    <FormControlLabel
                      key={v}
                      sx={{ mr: 0.5 }}
                      control={
                        <Checkbox
                          size="small"
                          checked={showVerdict[v]}
                          onChange={(e) =>
                            setShowVerdict((s) => ({ ...s, [v]: e.target.checked }))
                          }
                        />
                      }
                      label={
                        <Typography variant="caption" sx={{ fontVariantNumeric: "tabular-nums" }}>
                          {v} · {verdictCounts[v]}
                        </Typography>
                      }
                    />
                  ))}
                </Stack>
                {params.scopeShort &&
                  params.shortResearchOnly &&
                  result.rows.every((r) => r.state !== "short") && (
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                      Short board is on but restricted to bond ETFs &amp; BTC — the board has none
                      shorting right now. Untick that restriction on the left to size equity shorts.
                    </Typography>
                  )}
                {result.rows.length > 0 && visibleRows.length === 0 ? (
                  <Typography color="text.secondary" sx={{ p: 2 }}>
                    All {result.rows.length} rows hidden by the verdict filter.
                  </Typography>
                ) : (
                  <SizingTable rows={visibleRows} />
                )}
                {result.excluded.length > 0 && (
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                    Excluded: {result.excluded.map((e) => `${e.symbol} (${e.reason})`).join(", ")}
                  </Typography>
                )}
              </Paper>
            </Stack>
          )}
        </Box>
      </Stack>
    </div>
  );
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
        {label}
      </Typography>
      <Typography variant="body1" sx={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
        {value}
      </Typography>
      {sub && (
        <Typography variant="caption" color="text.secondary">
          {sub}
        </Typography>
      )}
    </Box>
  );
}

function Hero({
  result,
  params,
  macro,
}: {
  result: ReturnType<typeof computeSizing>;
  params: SizingParams;
  macro: MacroContext;
}) {
  const combined = result.macroScale * result.volScale;
  const scaled = result.macroScale < 1 || result.volScale < 0.995;

  let tone: "add" | "hold" | "empty";
  if (!result.rows.length) tone = "empty";
  else if (result.headroomPct >= 1) tone = "add";
  else tone = "hold";

  const color = tone === "add" ? green : scaled && tone === "hold" ? amber : grey;
  const big =
    tone === "add"
      ? usd(result.headroomUsd)
      : tone === "empty"
        ? "—"
        : result.deployedGrossPct >= 1
          ? `${result.deployedGrossPct.toFixed(0)}%`
          : `×${combined.toFixed(2)}`;
  const line =
    tone === "add"
      ? `Add across ${result.addCount} ADD name${result.addCount === 1 ? "" : "s"} · +${result.headroomPct.toFixed(0)}% of NAV`
      : tone === "empty"
        ? "No on-signal names in scope"
        : result.deployedGrossPct >= 1
          ? "Deployed ≈ target — nothing to add right now"
          : "The regime has the book near flat — hold";

  return (
    <Paper sx={{ p: 2.5, borderLeft: `4px solid ${color}` }}>
      <Typography variant="overline" color="text.secondary">
        {tone === "add" ? "Head-room" : "Status"}
      </Typography>
      <Typography sx={{ fontSize: 40, fontWeight: 800, lineHeight: 1.1, color, fontVariantNumeric: "tabular-nums" }}>
        {big}
      </Typography>
      <Typography variant="body1" sx={{ mt: 0.5 }}>
        {line}
      </Typography>
      {scaled && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          Whole book scaled ×{combined.toFixed(2)}
          {params.macroEnabled && result.macroScale < 1
            ? ` · ${macro.zone} regime ×${result.macroScale.toFixed(2)}`
            : ""}
          {result.volScale < 0.995 ? ` · vol-target ×${result.volScale.toFixed(2)}` : ""}. Every
          target below is already scaled — this is normal, not a stop.
        </Typography>
      )}
      <Typography variant="caption" color="text.secondary">
        NAV {usd(params.nav)} · k_max {params.kMax.toFixed(2)}× · {result.bindingConstraint}
      </Typography>
    </Paper>
  );
}
