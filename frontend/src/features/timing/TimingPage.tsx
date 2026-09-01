import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";

import { ApiError } from "@/shared/api/client";
import { fmtTs } from "@/shared/format";

import { EquityChart } from "./EquityChart";
import { searchSymbols, timingApi, type SymbolOption } from "./api";
import { compound, drawdownCurve, summariseView } from "./metrics";
import { TimingChart, type RangeKey, type Timeframe } from "./TimingChart";
import type { BoardState, EquityCurve, Metrics, SignalParams, TimingResponse, Trade } from "./types";

const LS_SYMBOL = "timing.symbol";
const LS_VIEW = "timing.view"; // which side(s) to render — pure display filter
const RANGES: RangeKey[] = ["5D", "1M", "6M", "1Y", "5Y", "MAX"];
const MA_CHOICES = [5, 20, 50, 200];

const NA = "—";
const pct = (v: number | null | undefined, d = 1) =>
  v == null ? NA : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(d)}%`;
const num = (v: number | null | undefined, d = 2) => (v == null ? NA : Number(v).toFixed(d));
const money = (v: number | null | undefined) => (v == null ? NA : Number(v).toFixed(2));
const green = "#1f9d55";
const red = "#d64545";

const MODELS: { value: SignalParams["model"]; label: string }[] = [
  { value: "donchian", label: "Donchian breakout (Turtle)" },
];

const NUM_FIELDS: { key: keyof SignalParams; label: string; step?: number; help: string }[] = [
  {
    key: "entry_len",
    label: "Entry channel",
    help: "Breakout window. Go long when price closes above the highest high of the last N days (short on the lowest low). Larger = fewer, more selective entries.",
  },
  {
    key: "exit_len",
    label: "Exit channel",
    help: "Exit window, deliberately shorter than the entry channel. Leave when price closes back to an N-day extreme against you. Smaller = exits sooner, gives back less profit.",
  },
  {
    key: "atr_len",
    label: "ATR length",
    help: "Days used to measure the typical daily range (volatility). Every stop distance is a multiple of this.",
  },
  {
    key: "atr_stop_mult",
    label: "Initial stop ×ATR",
    step: 0.1,
    help: "Disaster stop, set at entry: entry ∓ this × ATR. Caps the loss on a failed breakout. Larger = more breathing room but a bigger worst-case loss per trade.",
  },
  {
    key: "chandelier_k",
    label: "Chandelier ×ATR",
    step: 0.1,
    help: "Trailing stop: best price since entry ∓ this × ATR, ratchets one way only. Larger = looser trail, rides trends longer but hands back more at the turn.",
  },
  {
    key: "cost_bps",
    label: "Cost bps/side",
    step: 1,
    help: "Assumed trading friction per side, in basis points (1 bp = 0.01%). Applied to the return maths only, not the stop levels.",
  },
  {
    key: "slippage_atr",
    label: "Slippage ×ATR",
    step: 0.01,
    help: "Extra fill slippage as a fraction of ATR — added to the entry price, subtracted from the exit.",
  },
  {
    key: "ma_regime",
    label: "Regime MA",
    help: "Length of the slow trend filter. Only used when the MA regime gate below is on.",
  },
];

export function TimingPage() {
  const { symbol: routeSymbol } = useParams();
  const navigate = useNavigate();

  const initialSymbol = (routeSymbol || localStorage.getItem(LS_SYMBOL) || "QQQ").toUpperCase();

  const [symbol, setSymbol] = useState(initialSymbol);
  const [data, setData] = useState<TimingResponse | null>(null);
  const [params, setParams] = useState<SignalParams | null>(null);
  const [strategyLabel, setStrategyLabel] = useState("");
  const [engineVersion, setEngineVersion] = useState("");
  const [showParams, setShowParams] = useState(false);
  const [showGuide, setShowGuide] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [timeframe, setTimeframe] = useState<Timeframe>("D");
  const [range, setRange] = useState<RangeKey>("1Y");
  const [mas, setMas] = useState<number[]>([20, 50]);
  const [showKeyLevels, setShowKeyLevels] = useState(true);

  // Long / short is a VIEW filter — every Run stores both sides; this only
  // controls which markers / trades / metrics are rendered.
  const savedView = (localStorage.getItem(LS_VIEW) ?? "long,short").split(",");
  const [dirLong, setDirLong] = useState(savedView.includes("long"));
  const [dirShort, setDirShort] = useState(savedView.includes("short"));
  const bothOff = !dirLong && !dirShort;
  const effLong = dirLong || bothOff; // "neither" is meaningless -> show both
  const effShort = dirShort || bothOff;
  const showBoth = effLong && effShort;
  useEffect(() => {
    localStorage.setItem(LS_VIEW, [effLong && "long", effShort && "short"].filter(Boolean).join(","));
  }, [effLong, effShort]);

  // --- symbol picker (remote search-as-you-type) ---
  // `symValue` is the picked option, held in state — NOT derived from the
  // results list, or a keystroke that drops the current pick out of the
  // results would snap the field back to it.
  const [symValue, setSymValue] = useState<SymbolOption>({ symbol: initialSymbol, name: null });
  const [symInput, setSymInput] = useState(initialSymbol);
  const [symResults, setSymResults] = useState<SymbolOption[]>([]);

  useEffect(() => {
    // if the symbol changed from elsewhere (route nav), follow it
    setSymValue((cur) => (cur.symbol === symbol ? cur : { symbol, name: null }));
    setSymInput((cur) => (cur === symbol ? cur : symbol));
  }, [symbol]);

  useEffect(() => {
    let alive = true;
    // showing the current pick verbatim -> browse the top names instead
    const q = symInput.trim().toUpperCase() === symbol ? "" : symInput.trim();
    void searchSymbols(q).then((r) => alive && setSymResults(r));
    return () => {
      alive = false;
    };
  }, [symInput, symbol]);

  const symOptions = useMemo(
    () =>
      symResults.some((o) => o.symbol === symValue.symbol)
        ? symResults
        : [symValue, ...symResults],
    [symResults, symValue],
  );

  // Pre-fill the form from the symbol's assigned strategy. Re-resolve when the
  // symbol changes so a bond ETF shows its slow-entry parameters.
  useEffect(() => {
    void timingApi.resolved(symbol).then((r) => {
      setParams(r.strategy.params);
      setStrategyLabel(r.strategy.name);
      setEngineVersion(r.engine_version);
    });
  }, [symbol]);

  const load = useCallback((sym: string) => {
    setError(null);
    void timingApi
      .timing(sym)
      .then(setData)
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);

  useEffect(() => {
    localStorage.setItem(LS_SYMBOL, symbol);
    load(symbol);
  }, [symbol, load]);

  const onPickSymbol = (s: string) => {
    const up = s.toUpperCase();
    setSymbol(up);
    navigate(`/timing/${encodeURIComponent(up)}`, { replace: true });
  };

  const doRun = async () => {
    if (!params) return;
    setRunning(true);
    setError(null);
    try {
      setData(await timingApi.preview(symbol, params));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  const setParam = <K extends keyof SignalParams>(k: K, v: SignalParams[K]) =>
    setParams((p) => (p ? { ...p, [k]: v } : p));

  const notComputed = data?.status === "not_computed";

  // --- apply the view filter (display only) ---
  const view = useMemo(() => {
    const trades = data?.trades ?? [];
    const markers = data?.markers ?? [];
    const daily = data?.daily ?? [];
    const keep = (dir: string) => (dir === "long" ? effLong : effShort);

    const visibleTrades = trades.filter((t) => keep(t.direction));
    const visibleMarkers = markers.filter((m) => keep(m.side));

    if (showBoth || !data || data.status !== "ok") {
      return {
        trades: visibleTrades,
        markers: visibleMarkers,
        metrics: data?.metrics as Metrics | undefined,
        equity: data?.equity as EquityCurve | undefined,
        state: data?.state as BoardState | undefined,
        filtered: false,
      };
    }

    // isolate one side's contribution
    const filteredDaily = daily.map((d) =>
      (d.state === 1 && !effLong) || (d.state === -1 && !effShort)
        ? { ...d, state: 0 as const, strat_ret: 0 }
        : d,
    );
    const sv = summariseView(visibleTrades, filteredDaily);
    const metrics: Metrics = {
      label: `${data.metrics?.label ?? ""} · ${effLong ? "long" : "short"}-only view`,
      trade_stats: sv.trade_stats,
      strategy: sv.strategy,
      buy_hold: data.metrics?.buy_hold ?? {},
    };
    const stratEq = compound(filteredDaily.map((d) => d.strat_ret));
    const equity: EquityCurve = {
      dates: data.equity?.dates ?? filteredDaily.map((d) => d.date),
      strat_equity: stratEq,
      bh_equity: data.equity?.bh_equity ?? [],
      drawdown: drawdownCurve(stratEq),
    };

    // board state from the visible trades
    const open = visibleTrades.find((t) => t.exit_date === null);
    const lastClose = data.state?.last_close ?? null;
    const state: BoardState = open
      ? {
          state: open.direction,
          state_since: open.entry_date,
          entry_price: open.entry_price,
          last_close: lastClose,
          unrealized_pct:
            lastClose != null
              ? (open.direction === "long" ? 1 : -1) * (lastClose / open.entry_price - 1)
              : null,
          current_stop: open.initial_stop,
        }
      : {
          state: "flat",
          state_since: visibleTrades.at(-1)?.exit_date ?? null,
          entry_price: null,
          last_close: lastClose,
          unrealized_pct: null,
          current_stop: null,
        };

    return { trades: visibleTrades, markers: visibleMarkers, metrics, equity, state, filtered: true };
  }, [data, effLong, effShort, showBoth]);

  const m = view.metrics;

  return (
    <div>
      <Typography variant="h5" gutterBottom>
        Timing
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        The trend rule ({strategyLabel || "Naive Donchian V1"}) drilled into one symbol: its long /
        short entries and exits over the full price history, plus rule-only performance metrics. Run
        recomputes live with the parameters below and is <b>not saved</b> — the Trend board always
        uses the symbol&apos;s assigned strategy. Every run computes both directions; the Long /
        Short toggles below only change what is shown.
      </Typography>

      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={2}
        useFlexGap
        sx={{ mb: 2, alignItems: "center", flexWrap: "wrap" }}
      >
        <Autocomplete
          sx={{ width: 340 }}
          size="small"
          options={symOptions}
          filterOptions={(x) => x}
          autoHighlight
          selectOnFocus
          handleHomeEndKeys
          value={symValue}
          onChange={(_, v) => {
            if (v && typeof v !== "string") {
              setSymValue(v);
              setSymInput(v.symbol);
              onPickSymbol(v.symbol);
            }
          }}
          inputValue={symInput}
          onInputChange={(_, v) => setSymInput(v)}
          isOptionEqualToValue={(o, v) => o.symbol === v.symbol}
          getOptionLabel={(o) => (typeof o === "string" ? o : o.symbol)}
          renderOption={(props, o) => {
            const { key, ...rest } = props;
            return (
              <Box component="li" key={key} {...rest} sx={{ display: "flex", gap: 1 }}>
                <span style={{ fontWeight: 600, minWidth: 60 }}>{o.symbol}</span>
                <span style={{ opacity: 0.7, overflow: "hidden", textOverflow: "ellipsis" }}>
                  {o.name}
                </span>
              </Box>
            );
          }}
          slotProps={{ listbox: { sx: { maxHeight: 420 } } }}
          renderInput={(p) => <TextField {...p} label="Symbol" placeholder="type e.g. MU" />}
        />
        <TextField
          select
          size="small"
          label="Model"
          sx={{ width: 220 }}
          value={params?.model ?? "donchian"}
          onChange={(e) => setParam("model", e.target.value as SignalParams["model"])}
        >
          {MODELS.map((mdl) => (
            <MenuItem key={mdl.value} value={mdl.value}>
              {mdl.label}
            </MenuItem>
          ))}
        </TextField>
        <Button variant="contained" onClick={doRun} disabled={running}>
          {running ? "Running…" : `Run ${symbol}`}
        </Button>
        <Button size="small" onClick={() => setShowParams((s) => !s)}>
          {showParams ? "Hide parameters & guide" : "Parameters & guide"}
        </Button>
        {data?.computed_at && (
          <Typography variant="caption" color="text.secondary">
            last run {fmtTs(data.computed_at)}
          </Typography>
        )}
        {data?.stale && <Chip size="small" color="warning" label="newer bars — re-run" />}
      </Stack>

      <Collapse in={showParams}>
        <Paper sx={{ p: 2, mb: 2 }}>
          {params && (
            <>
              <Typography variant="subtitle2" gutterBottom>
                What this strategy is
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 900 }}>
                <b>Donchian channel breakout</b> — the classic <i>Turtle</i> trend-following rule. It
                assumes that once price clears its recent extreme, a trend has likely begun and tends
                to continue. So it <b>enters long when the close makes a new {params.entry_len}-day
                high</b> (and short on a new {params.entry_len}-day low), then rides the position with
                a trailing stop and <b>exits</b> when price closes back to a shorter{" "}
                {params.exit_len}-day extreme against it, or a volatility-based stop is hit. It never
                forecasts — it only reacts to price. Slow to get in, quick to get out.
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1, maxWidth: 900 }}>
                This is a <b>naive, unvalidated v1</b> and right now the <b>only model — a placeholder
                to get the app working</b>. Later models (MA-ensemble à la Man / AHL; chart-formation
                entries — base breakout, double top / bottom, right-side breakout-with-stop) will each
                get their own long / short parameters and appear in the <b>Model</b> dropdown.
              </Typography>

              <Button size="small" sx={{ mt: 1, px: 0 }} onClick={() => setShowGuide((s) => !s)}>
                {showGuide ? "Hide the rule detail ▾" : "Why enter / why exit? ▸"}
              </Button>
              <Collapse in={showGuide}>
                <Box
                  component="ul"
                  sx={{ mt: 0.5, pl: 3, color: "text.secondary", fontSize: 13, maxWidth: 900 }}
                >
                  <li>
                    <b>Entry</b> — a close above the highest high of the last <i>entry channel</i> days
                    means buyers just overwhelmed every seller from that whole window; historically
                    that is where sustained moves start. Mirrored on the low side for shorts.
                  </li>
                  <li>
                    <b>Model exit</b> — a close back below the lowest low of the last (shorter)
                    <i> exit channel</i> days: the trend has rolled over. Shorter than the entry
                    window on purpose, so you give back less of the run.
                  </li>
                  <li>
                    <b>Initial stop</b> — <code>entry ∓ (initial-stop ×ATR)</code>. A fixed,
                    volatility-scaled cap on the loss if the breakout immediately fails.
                  </li>
                  <li>
                    <b>Trailing stop (Chandelier)</b> — <code>best price since entry ∓ (chandelier
                    ×ATR)</code>, and it only ever tightens. Locks in profit as the trend runs; the
                    wider you set it, the longer you stay but the more you hand back at the turn.
                  </li>
                  <li>
                    <b>ATR</b> is the average daily range — every stop distance is measured in ATRs so
                    the rule adapts to each symbol&apos;s volatility.
                  </li>
                  <li>
                    <b>Fills</b> happen at the next session&apos;s open by default (you see the signal
                    at the close, you act next day). Costs and slippage are applied to the returns
                    only, never to the stop levels.
                  </li>
                </Box>
              </Collapse>

              <Typography variant="subtitle2" gutterBottom sx={{ mt: 2 }}>
                Parameters
                <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                  — pre-filled from {symbol}&apos;s assigned strategy ({strategyLabel || "V1"}); engine{" "}
                  {engineVersion}. Edits run live only and are never saved.
                </Typography>
              </Typography>
              <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 2 }}>
                {NUM_FIELDS.map((f) => (
                  <TextField
                    key={f.key}
                    label={f.label}
                    size="small"
                    type="number"
                    sx={{ width: 230 }}
                    slotProps={{ htmlInput: { step: f.step ?? 1 } }}
                    helperText={f.help}
                    value={params[f.key] as number}
                    onChange={(e) => setParam(f.key, Number(e.target.value) as never)}
                  />
                ))}
                <TextField
                  select
                  label="Trail mode"
                  size="small"
                  sx={{ width: 230 }}
                  helperText="How the trailing stop is computed: chandelier (best price ∓ k×ATR), exit_channel (the exit Donchian), or atr_trail (close ∓ k×ATR)."
                  value={params.trail_mode}
                  onChange={(e) => setParam("trail_mode", e.target.value as SignalParams["trail_mode"])}
                >
                  {["chandelier", "exit_channel", "atr_trail"].map((o) => (
                    <MenuItem key={o} value={o}>
                      {o}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  select
                  label="Fill at"
                  size="small"
                  sx={{ width: 230 }}
                  helperText="When a signal becomes a fill: next session's open (realistic) or the signal bar's close."
                  value={params.fill_at}
                  onChange={(e) => setParam("fill_at", e.target.value as SignalParams["fill_at"])}
                >
                  {["open_next", "close"].map((o) => (
                    <MenuItem key={o} value={o}>
                      {o}
                    </MenuItem>
                  ))}
                </TextField>
                <Box sx={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={params.use_ma_regime}
                        onChange={(e) => setParam("use_ma_regime", e.target.checked)}
                      />
                    }
                    label="MA regime gate"
                  />
                  <Typography variant="caption" color="text.secondary" sx={{ ml: 1.5, maxWidth: 260 }}>
                    Only take longs above the regime MA, shorts below it — filters counter-trend trades.
                  </Typography>
                </Box>
                <Box sx={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={params.stop_and_reverse}
                        onChange={(e) => setParam("stop_and_reverse", e.target.checked)}
                      />
                    }
                    label="Stop & reverse"
                  />
                  <Typography variant="caption" color="text.secondary" sx={{ ml: 1.5, maxWidth: 260 }}>
                    On an opposite breakout, flip straight into the reverse position instead of going flat.
                  </Typography>
                </Box>
              </Stack>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2 }}>
                These parameters run live in this page only — nothing is saved. To change what the
                Trend board uses for a symbol, assign it a strategy on the <b>Strategies</b> page.
              </Typography>
            </>
          )}
        </Paper>
      </Collapse>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {notComputed && (
        <Alert severity="info" sx={{ mb: 2 }}>
          No run stored for {symbol} yet — press <b>Run {symbol}</b>.
        </Alert>
      )}

      {data?.status === "ok" && data.chart_cached === false && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Computed by the last <b>Trend</b> run — trades, markers and combined metrics are shown, but
          press <b>Run {symbol}</b> for the Donchian channel &amp; stop overlay, the equity curve, and
          the long/short metric split.
        </Alert>
      )}

      {data?.status === "ok" && (
        <>
          <Stack
            direction="row"
            spacing={2}
            useFlexGap
            sx={{ mb: 1, alignItems: "center", flexWrap: "wrap" }}
          >
            {view.state && <StateChip state={view.state} />}
            <Box sx={{ display: "flex", alignItems: "center" }}>
              <Typography variant="body2" color="text.secondary" sx={{ mr: 0.5 }}>
                Show
              </Typography>
              <FormControlLabel
                control={<Checkbox size="small" checked={effLong} onChange={(e) => setDirLong(e.target.checked)} />}
                label="Long"
              />
              <FormControlLabel
                control={<Checkbox size="small" checked={effShort} onChange={(e) => setDirShort(e.target.checked)} />}
                label="Short"
              />
            </Box>
            <ToggleButtonGroup size="small" exclusive value={timeframe} onChange={(_, v) => v && setTimeframe(v)}>
              {(["D", "W", "M"] as Timeframe[]).map((t) => (
                <ToggleButton key={t} value={t}>
                  {t}
                </ToggleButton>
              ))}
            </ToggleButtonGroup>
            <ToggleButtonGroup size="small" exclusive value={range} onChange={(_, v) => v && setRange(v)}>
              {RANGES.map((r) => (
                <ToggleButton key={r} value={r}>
                  {r}
                </ToggleButton>
              ))}
            </ToggleButtonGroup>
            <ToggleButtonGroup size="small" value={mas} onChange={(_, v: number[]) => setMas(v)}>
              {MA_CHOICES.map((n) => (
                <ToggleButton key={n} value={n}>
                  MA{n}
                </ToggleButton>
              ))}
            </ToggleButtonGroup>
            <FormControlLabel
              control={
                <Switch
                  size="small"
                  checked={showKeyLevels}
                  onChange={(e) => setShowKeyLevels(e.target.checked)}
                />
              }
              label="Key levels"
            />
          </Stack>

          <Paper sx={{ p: 1, mb: 2 }}>
            <TimingChart
              bars={data.bars ?? []}
              overlays={data.overlays}
              markers={view.markers}
              keyLevels={data.key_levels ?? []}
              timeframe={timeframe}
              range={range}
              mas={mas}
              showKeyLevels={showKeyLevels}
            />
            {timeframe !== "D" && (
              <Typography variant="caption" color="text.secondary" sx={{ pl: 1 }}>
                Donchian channel, stop line and entry/exit markers show on the Daily timeframe only.
              </Typography>
            )}
          </Paper>

          {m && (
            <Paper sx={{ p: 2, mb: 2 }}>
              <Typography variant="subtitle2" gutterBottom>
                Performance — {m.label}
              </Typography>
              {view.filtered && (
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                  {effLong ? "Long" : "Short"}-only view: that side&apos;s isolated contribution, not a
                  re-run — check both boxes for the real combined result.
                </Typography>
              )}
              <Stack direction={{ xs: "column", md: "row" }} spacing={4}>
                <StatGrid
                  title="Trade stats"
                  rows={[
                    ["Trades", num(m.trade_stats.trades as number, 0)],
                    ["Win rate", pct(m.trade_stats.win_rate as number, 0)],
                    ["Payoff ratio", num(m.trade_stats.payoff_ratio as number)],
                    ["Expectancy / trade", pct(m.trade_stats.expectancy_pct as number, 2)],
                    ["Expectancy (R)", num(m.trade_stats.expectancy_r as number)],
                    ["Profit factor", num(m.trade_stats.profit_factor as number)],
                    ["SQN", num(m.trade_stats.sqn as number)],
                    ["Avg bars held", num(m.trade_stats.avg_bars_held as number, 0)],
                    ["Max consec. losses", num(m.trade_stats.max_consec_losses as number, 0)],
                    [
                      "Avg MAE / MFE (ATR)",
                      `${num(m.trade_stats.avg_mae_atr as number)} / ${num(m.trade_stats.avg_mfe_atr as number)}`,
                    ],
                    ["Exposure", pct(m.trade_stats.exposure as number, 0)],
                  ]}
                />
                <StatGrid
                  title="Risk / return (strategy)"
                  rows={[
                    ["Total return", pct(m.strategy.total_return, 0)],
                    ["CAGR", pct(m.strategy.cagr, 1)],
                    ["Volatility (ann.)", pct(m.strategy.vol_annual, 1)],
                    ["Sharpe", num(m.strategy.sharpe)],
                    ["Sortino", num(m.strategy.sortino)],
                    ["Max drawdown", pct(m.strategy.max_drawdown, 1)],
                    ["Max DD length (days)", num(m.strategy.max_dd_days, 0)],
                    ["Calmar / MAR", num(m.strategy.calmar)],
                  ]}
                />
                <StatGrid
                  title="vs Buy & hold"
                  rows={[
                    ["B&H total return", pct(m.buy_hold.total_return, 0)],
                    ["B&H CAGR", pct(m.buy_hold.cagr, 1)],
                    ["B&H max drawdown", pct(m.buy_hold.max_drawdown, 1)],
                  ]}
                />
              </Stack>
              {view.equity?.dates?.length ? (
                <Box sx={{ mt: 2 }}>
                  <Typography variant="caption" color="text.secondary">
                    Equity curve — strategy (blue) vs buy & hold (grey), drawdown shaded
                  </Typography>
                  <EquityChart equity={view.equity} />
                </Box>
              ) : null}
            </Paper>
          )}

          <Paper sx={{ p: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              Trade history ({view.trades.length}
              {view.filtered ? ` of ${data.trades?.length ?? 0}` : ""})
            </Typography>
            <Box sx={{ overflowX: "auto" }}>
              <TradeTable trades={view.trades} />
            </Box>
          </Paper>
        </>
      )}
    </div>
  );
}

function StateChip({ state: s }: { state: BoardState }) {
  if (!s?.state) return null;
  if (s.state === "flat") {
    return <Chip label={`Flat since ${s.state_since ?? NA}`} variant="outlined" />;
  }
  const up = (s.unrealized_pct ?? 0) >= 0;
  return (
    <Chip
      color={s.state === "long" ? "success" : "error"}
      label={`${s.state.toUpperCase()} since ${s.state_since} · entry ${money(s.entry_price)} · ${
        s.unrealized_pct == null ? NA : (up ? "+" : "") + (s.unrealized_pct * 100).toFixed(1) + "%"
      } · stop ${money(s.current_stop)}`}
    />
  );
}

function StatGrid({ title, rows }: { title: string; rows: [string, string][] }) {
  return (
    <Box sx={{ minWidth: 220 }}>
      <Typography variant="overline" color="text.secondary">
        {title}
      </Typography>
      {rows.map(([k, v]) => (
        <Stack key={k} direction="row" sx={{ py: 0.25, justifyContent: "space-between" }}>
          <Typography variant="body2" color="text.secondary">
            {k}
          </Typography>
          <Typography variant="body2" sx={{ fontVariantNumeric: "tabular-nums" }}>
            {v}
          </Typography>
        </Stack>
      ))}
    </Box>
  );
}

function TradeTable({ trades }: { trades: Trade[] }) {
  return (
    <Table size="small" sx={{ "& td, & th": { whiteSpace: "nowrap" } }}>
      <TableHead>
        <TableRow>
          {["Dir", "Entry", "Entry px", "Exit", "Exit px", "Reason", "Bars", "Return", "R", "Result"].map(
            (h) => (
              <TableCell
                key={h}
                align={
                  h === "Dir" || h === "Entry" || h === "Exit" || h === "Reason" || h === "Result"
                    ? "left"
                    : "right"
                }
              >
                {h}
              </TableCell>
            ),
          )}
        </TableRow>
      </TableHead>
      <TableBody>
        {trades.map((t, i) => {
          const open = t.exit_date == null;
          const win = (t.return_pct ?? 0) > 0;
          return (
            <TableRow key={i}>
              <TableCell sx={{ color: t.direction === "long" ? green : red, fontWeight: 600 }}>
                {t.direction}
              </TableCell>
              <TableCell>{t.entry_date}</TableCell>
              <TableCell align="right">{money(t.entry_price)}</TableCell>
              <TableCell>{t.exit_date ?? "—"}</TableCell>
              <TableCell align="right">{money(t.exit_price)}</TableCell>
              <TableCell>{t.exit_reason ?? "—"}</TableCell>
              <TableCell align="right">{t.bars_held ?? "—"}</TableCell>
              <TableCell align="right" sx={{ color: t.return_pct == null ? undefined : win ? green : red }}>
                {t.return_pct == null ? "—" : `${win ? "+" : ""}${(t.return_pct * 100).toFixed(2)}%`}
              </TableCell>
              <TableCell align="right">{t.return_r == null ? "—" : t.return_r.toFixed(2)}</TableCell>
              <TableCell>{open ? <Chip size="small" label="Open" /> : win ? "Win" : "Loss"}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
