import { useCallback, useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { ApiError } from "@/shared/api/client";
import { searchSymbols, type SymbolOption } from "@/features/timing/api";
import type { SignalParams } from "@/features/timing/types";

import { strategyApi } from "./api";
import type { Strategy } from "./types";

const PARAM_ORDER: (keyof SignalParams)[] = [
  "entry_len",
  "exit_len",
  "atr_len",
  "atr_stop_mult",
  "trail_mode",
  "chandelier_k",
  "atr_trail_k",
  "fill_at",
  "cost_bps",
  "slippage_atr",
  "use_ma_regime",
  "ma_regime",
  "stop_and_reverse",
  "warmup_buffer",
  "allow_long",
  "allow_short",
];

export function StrategiesPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [engineVersion, setEngineVersion] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    void strategyApi
      .list()
      .then((r) => {
        setStrategies(r.strategies);
        setEngineVersion(r.engine_version);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);
  useEffect(load, [load]);

  const defaultStrategy = strategies.find((s) => s.is_default) ?? strategies[0];

  return (
    <div>
      <Typography variant="h5" gutterBottom>
        Strategies
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2, maxWidth: 900 }}>
        The parameter sets the <b>Trend</b> run uses. Every symbol resolves to exactly one strategy;
        unassigned or newly-synced symbols fall back to the default. Editing a live strategy is
        deliberately not offered — a genuinely different parameter set is a new strategy (V3, V4…).
        Direction is <b>not</b> a strategy setting: the board computes long <i>and</i> short for every
        symbol regardless, so a future short-capable strategy needs no re-fetch. Engine{" "}
        {engineVersion}.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {strategies.map((s) => (
        <StrategyCard
          key={s.id}
          strategy={s}
          defaultParams={defaultStrategy?.params}
          onChanged={load}
        />
      ))}
    </div>
  );
}

function fmtParam(v: unknown): string {
  if (typeof v === "boolean") return v ? "on" : "off";
  return String(v);
}

function StrategyCard({
  strategy,
  defaultParams,
  onChanged,
}: {
  strategy: Strategy;
  defaultParams?: SignalParams;
  onChanged: () => void;
}) {
  const [picked, setPicked] = useState<SymbolOption[]>([]);
  const [options, setOptions] = useState<SymbolOption[]>([]);
  const [input, setInput] = useState("");
  const [applying, setApplying] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [showSymbols, setShowSymbols] = useState(false);
  const [symbols, setSymbols] = useState<string[] | null>(null);

  useEffect(() => {
    let alive = true;
    void searchSymbols(input.trim()).then((r) => alive && setOptions(r));
    return () => {
      alive = false;
    };
  }, [input]);

  const diffKeys = useMemo(() => {
    if (!defaultParams || strategy.is_default) return new Set<string>();
    return new Set(
      PARAM_ORDER.filter((k) => strategy.params[k] !== defaultParams[k]).map(String),
    );
  }, [defaultParams, strategy]);

  const apply = async () => {
    if (!picked.length) return;
    setApplying(true);
    setNote(null);
    try {
      const res = await strategyApi.assign(
        strategy.id,
        picked.map((p) => p.symbol),
      );
      setNote(`Assigned ${res.assigned} symbol${res.assigned === 1 ? "" : "s"} to ${strategy.name}.`);
      setPicked([]);
      setInput("");
      if (showSymbols) setSymbols(res.symbols);
      onChanged();
    } catch (e) {
      setNote(e instanceof ApiError ? e.message : String(e));
    } finally {
      setApplying(false);
    }
  };

  const toggleSymbols = async () => {
    const next = !showSymbols;
    setShowSymbols(next);
    if (next && symbols == null) {
      try {
        const d = await strategyApi.detail(strategy.id);
        setSymbols(d.symbols);
      } catch {
        setSymbols([]);
      }
    }
  };

  return (
    <Paper sx={{ p: 2, mb: 2 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
          {strategy.name}
        </Typography>
        <Chip size="small" variant="outlined" label={strategy.key} />
        {strategy.is_default && <Chip size="small" color="primary" label="default" />}
        <Chip
          size="small"
          variant="outlined"
          label={`${strategy.assigned_count} symbol${strategy.assigned_count === 1 ? "" : "s"}`}
          onClick={toggleSymbols}
        />
      </Stack>

      {strategy.note && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1, maxWidth: 900 }}>
          {strategy.note}
        </Typography>
      )}

      <Box sx={{ mt: 1.5, overflowX: "auto" }}>
        <Table size="small" sx={{ width: "auto", "& td, & th": { whiteSpace: "nowrap" } }}>
          <TableHead>
            <TableRow>
              <TableCell>Parameter</TableCell>
              <TableCell align="right">Value</TableCell>
              {defaultParams && !strategy.is_default && (
                <TableCell align="right">Default</TableCell>
              )}
            </TableRow>
          </TableHead>
          <TableBody>
            {PARAM_ORDER.map((k) => {
              const differs = diffKeys.has(String(k));
              return (
                <TableRow key={String(k)} sx={differs ? { bgcolor: "action.hover" } : undefined}>
                  <TableCell sx={{ fontWeight: differs ? 700 : 400 }}>{k}</TableCell>
                  <TableCell align="right" sx={{ fontWeight: differs ? 700 : 400 }}>
                    {fmtParam(strategy.params[k])}
                  </TableCell>
                  {defaultParams && !strategy.is_default && (
                    <TableCell align="right" sx={{ color: "text.secondary" }}>
                      {fmtParam(defaultParams[k])}
                    </TableCell>
                  )}
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Box>

      <Collapse in={showSymbols}>
        <Box sx={{ mt: 1, mb: 1 }}>
          <Typography variant="caption" color="text.secondary">
            Assigned symbols
          </Typography>
          <Typography variant="body2" sx={{ wordBreak: "break-word" }}>
            {symbols == null
              ? "loading…"
              : symbols.length === 0
                ? "none"
                : symbols.join(", ")}
          </Typography>
        </Box>
      </Collapse>

      <Divider sx={{ my: 1.5 }} />

      <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ alignItems: "center" }}>
        <Autocomplete
          multiple
          size="small"
          sx={{ minWidth: 360, flex: 1 }}
          options={options}
          value={picked}
          onChange={(_, v) => setPicked(v as SymbolOption[])}
          inputValue={input}
          onInputChange={(_, v) => setInput(v)}
          filterOptions={(x) => x}
          isOptionEqualToValue={(o, v) => o.symbol === v.symbol}
          getOptionLabel={(o) => o.symbol}
          renderInput={(p) => (
            <TextField {...p} label={`Apply "${strategy.name}" to…`} placeholder="type a symbol" />
          )}
        />
        <Button variant="contained" onClick={apply} disabled={applying || !picked.length}>
          {applying ? "Applying…" : "Apply"}
        </Button>
      </Stack>
      {note && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
          {note}
        </Typography>
      )}
    </Paper>
  );
}
