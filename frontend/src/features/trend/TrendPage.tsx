import { Fragment, useCallback, useEffect, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import AirRounded from "@mui/icons-material/AirRounded";
import GrainRounded from "@mui/icons-material/GrainRounded";
import ThunderstormRounded from "@mui/icons-material/ThunderstormRounded";
import WbCloudyRounded from "@mui/icons-material/WbCloudyRounded";
import WbSunnyRounded from "@mui/icons-material/WbSunnyRounded";

import { FetchPanel } from "@/features/data-management/components/FetchPanel";

import { trendApi } from "./api";
import type { BoardResponse, BoardRow, BoardStrategy, WatchSection } from "./types";

const NA = "—";
const green = "#1f9d55";
const red = "#d64545";

const money = (v: number | null) => (v == null ? NA : v.toFixed(2));
const signedPct = (v: number | null) =>
  v == null ? NA : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
const daysSince = (iso: string | null) =>
  iso == null ? NA : Math.round((Date.now() - new Date(iso + "T00:00:00Z").getTime()) / 864e5);

// 60-day annualised return vol → a calm→turbulent severity scale. The icon
// escalates (sun → cloud → drizzle → wind → storm); the colour ramps green →
// red. Deliberately restrained: colour on the glyph + number only, no cell fill
// except the top bucket. Thresholds are round numbers, not tuned.
const VOL_STEPS = [
  { max: 0.15, label: "calm", color: "#1f9d55", Icon: WbSunnyRounded },
  { max: 0.25, label: "steady", color: "#7a9e1f", Icon: WbCloudyRounded },
  { max: 0.4, label: "choppy", color: "#c98a12", Icon: GrainRounded },
  { max: 0.6, label: "volatile", color: "#dd6b20", Icon: AirRounded },
  { max: Infinity, label: "wild", color: "#d64545", Icon: ThunderstormRounded },
] as const;
const volStep = (v: number) => VOL_STEPS.find((s) => v < s.max) ?? VOL_STEPS[VOL_STEPS.length - 1];

function VolCell({ v }: { v: number | null | undefined }) {
  if (v == null)
    return (
      <TableCell align="right" sx={{ color: "text.disabled" }}>
        {NA}
      </TableCell>
    );
  const s = volStep(v);
  const pct = `${Math.round(v * 100)}%`;
  return (
    <Tooltip title={`${s.label} · ${pct} annualised 60-day volatility`} arrow>
      <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
        <Box
          component="span"
          sx={{
            display: "inline-flex",
            alignItems: "center",
            gap: 0.5,
            color: s.color,
            fontWeight: 600,
            fontVariantNumeric: "tabular-nums",
            ...(s.label === "wild" && {
              bgcolor: "rgba(214,69,69,0.12)",
              borderRadius: 1,
              px: 0.75,
            }),
          }}
        >
          <s.Icon sx={{ fontSize: 15 }} />
          {pct}
        </Box>
      </TableCell>
    </Tooltip>
  );
}

export function TrendPage() {
  const [board, setBoard] = useState<BoardResponse | null>(null);
  const [showFlat, setShowFlat] = useState(false);
  const [showAlloc, setShowAlloc] = useState(false);

  const loadBoard = useCallback(() => {
    void trendApi.board().then(setBoard);
  }, []);
  useEffect(loadBoard, [loadBoard]);

  const notComputed = board?.status === "not_computed";

  return (
    <div>
      <Typography variant="h5" gutterBottom>
        Trend
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        The same rule as the Timing page, run once over the whole database (every active symbol plus
        gold / oil / BTC). Afterwards every symbol is in one of three states — holding long, holding
        short, or flat — sorted so the freshest entries sit on top. A ranking only, not a
        recommendation.
      </Typography>

      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={2}
        useFlexGap
        sx={{ mb: 2, alignItems: "center", flexWrap: "wrap" }}
      >
        <TextField select size="small" label="Model" sx={{ width: 240 }} value="donchian">
          <MenuItem value="donchian">Donchian breakout (Turtle)</MenuItem>
        </TextField>
        <FetchPanel kind="signal_universe" buttonLabel="Run trend backtest" onDone={loadBoard} />
        {board?.computed_at && (
          <Typography variant="caption" color="text.secondary">
            last run {new Date(board.computed_at).toLocaleString()}
          </Typography>
        )}
      </Stack>

      {notComputed && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Not computed yet — press <b>Run trend backtest</b>. It walks ~700 symbols and takes a few
          seconds.
        </Alert>
      )}

      <Paper sx={{ p: 2, mb: 2 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1 }}>
          <Typography variant="subtitle2">Watchlist</Typography>
          <Button size="small" onClick={() => setShowAlloc((s) => !s)}>
            {showAlloc ? "Hide position allocation ▾" : "Position allocation (advisory) ▸"}
          </Button>
        </Stack>
        <Collapse in={showAlloc}>
          <AllocationNote strategies={board?.strategies ?? []} />
        </Collapse>
        <WatchlistTable sections={board?.watchlist ?? []} />
      </Paper>

      {board?.status === "ok" && (
        <>
          <Paper sx={{ p: 2, mb: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              Holding long ({board.counts?.long ?? board.long.length}){" "}
              <Typography component="span" variant="caption" color="text.secondary">
                — newest entry first
              </Typography>
            </Typography>
            <BoardTable rows={board.long} rankFrom={1} />
          </Paper>

          <Paper sx={{ p: 2, mb: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              Holding short ({board.counts?.short ?? board.short.length}){" "}
              <Typography component="span" variant="caption" color="text.secondary">
                — newest entry first
              </Typography>
            </Typography>
            <BoardTable rows={board.short} rankFrom={1} />
          </Paper>

          <Paper sx={{ p: 2 }}>
            <Button size="small" onClick={() => setShowFlat((s) => !s)}>
              {showFlat ? "Hide" : "Show"} flat ({board.counts?.flat ?? board.flat.length})
            </Button>
            <Collapse in={showFlat}>
              <Box sx={{ mt: 1 }}>
                <BoardTable rows={board.flat.slice(0, 200)} rankFrom={null} flatOnly />
                {board.flat.length > 200 && (
                  <Typography variant="caption" color="text.secondary">
                    showing first 200 of {board.flat.length}
                  </Typography>
                )}
              </Box>
            </Collapse>
          </Paper>
        </>
      )}
    </div>
  );
}

function StateCell({ row }: { row: BoardRow }) {
  if (!row.state || row.state === "flat")
    return <Chip size="small" variant="outlined" label="flat" />;
  return (
    <Chip
      size="small"
      color={row.state === "long" ? "success" : "error"}
      label={row.state}
    />
  );
}

function BoardTable({
  rows,
  rankFrom,
  showFlatCols,
  flatOnly,
}: {
  rows: BoardRow[];
  rankFrom: number | null;
  showFlatCols?: boolean;
  flatOnly?: boolean;
}) {
  if (flatOnly) {
    return (
      <Table size="small" sx={{ "& td, & th": { whiteSpace: "nowrap" } }}>
        <TableHead>
          <TableRow>
            <TableCell>Symbol</TableCell>
            <TableCell>Flat since</TableCell>
            <TableCell align="right">Vol 60d</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.symbol}>
              <TableCell>
                <SymLink symbol={r.symbol} />
              </TableCell>
              <TableCell>{r.state_since ?? NA}</TableCell>
              <VolCell v={r.vol_60d} />
            </TableRow>
          ))}
        </TableBody>
      </Table>
    );
  }
  return (
    <Box sx={{ overflowX: "auto" }}>
      <Table size="small" sx={{ "& td, & th": { whiteSpace: "nowrap" } }}>
        <TableHead>
          <TableRow>
            {rankFrom != null && <TableCell align="right">#</TableCell>}
            <TableCell>Symbol</TableCell>
            {showFlatCols && <TableCell>State</TableCell>}
            <TableCell>Since</TableCell>
            <TableCell align="right">Days</TableCell>
            <TableCell align="right">Entry</TableCell>
            <TableCell align="right">Last</TableCell>
            <TableCell align="right">Unreal.</TableCell>
            <Tooltip title="Current stop-loss price - the engine's trailing or initial stop" arrow><TableCell align="right">Stop</TableCell></Tooltip>
            <TableCell align="right">Vol 60d</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((r, i) => {
            const flat = !r.state || r.state === "flat";
            const up = (r.unrealized_pct ?? 0) >= 0;
            return (
              <TableRow key={r.symbol}>
                {rankFrom != null && <TableCell align="right">{rankFrom + i}</TableCell>}
                <TableCell>
                  <SymLink symbol={r.symbol} />
                </TableCell>
                {showFlatCols && (
                  <TableCell>
                    <StateCell row={r} />
                  </TableCell>
                )}
                <TableCell>{r.state_since ?? NA}</TableCell>
                <TableCell align="right">{flat ? NA : daysSince(r.state_since)}</TableCell>
                <TableCell align="right">{flat ? NA : money(r.entry_price)}</TableCell>
                <TableCell align="right">{money(r.last_close)}</TableCell>
                <TableCell align="right" sx={{ color: flat ? undefined : up ? green : red }}>
                  {flat ? NA : signedPct(r.unrealized_pct)}
                </TableCell>
                <TableCell align="right">{flat ? NA : money(r.current_stop)}</TableCell>
                <VolCell v={r.vol_60d} />
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Box>
  );
}

function AllocationNote({ strategies }: { strategies: BoardStrategy[] }) {
  return (
    <Box
      sx={{
        mb: 2,
        p: 1.5,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        bgcolor: "action.hover",
        maxWidth: 900,
        fontSize: 13,
        color: "text.secondary",
      }}
    >
      <Typography variant="caption" sx={{ fontWeight: 700, letterSpacing: 0.5 }}>
        HOW YOU&apos;D ROUGHLY ALLOCATE — advisory only, nothing here holds a real position
      </Typography>
      <Box component="ul" sx={{ mt: 0.5, mb: 0, pl: 3 }}>
        <li>
          Every symbol is always in one of three states: <b>long position</b>, <b>short position</b>,
          or <b>no position</b>. Trade the entries and exits shown above; size them, don&apos;t just
          equal-weight.
        </li>
        <li>
          <b>Size by volatility</b>: smaller position in a jumpy name, larger in a calm one, so each
          risks about the same. Aim for a whole-book volatility near <b>~12% a year</b>; cap any one
          name around <b>10%</b> of the account.
        </li>
        <li>
          <b>Spread across sleeves</b>, don&apos;t let equities dominate: roughly equities 50 / bonds
          20 / commodities 15 / crypto 5 / other 10 of the risk budget.
        </li>
        <li>
          <b>Direction</b>: default <b>long only</b>. The research says the short side earns its keep
          only for <b>bond ETFs</b> and <b>BTC/USD</b> (it pays in their bear legs at little Sharpe
          cost). The board still shows every short setup so you can watch them.
        </li>
        <li>
          Re-check sizing about <b>weekly</b>, not every day. These are reference numbers from the
          frozen research, not a live optimiser — see the handoff doc.
        </li>
      </Box>
      {strategies.length > 0 && (
        <Box sx={{ mt: 1 }}>
          {strategies.map((s) => (
            <div key={s.id}>
              <b>{s.name}</b> — {s.assigned_count} symbol
              {s.assigned_count === 1 ? "" : "s"}
              {s.is_default ? " (default)" : ""}
            </div>
          ))}
        </Box>
      )}
    </Box>
  );
}

function SymLink({ symbol }: { symbol: string }) {
  return (
    <Link component={RouterLink} to={`/timing/${encodeURIComponent(symbol)}`} sx={{ fontWeight: 600 }}>
      {symbol}
    </Link>
  );
}

const WATCH_COLS = 9;

function WatchRow({ r }: { r: BoardRow }) {
  const flat = !r.state || r.state === "flat";
  const up = (r.unrealized_pct ?? 0) >= 0;
  return (
    <TableRow>
      <TableCell>
        <SymLink symbol={r.symbol} />
      </TableCell>
      <TableCell>
        <StateCell row={r} />
      </TableCell>
      <TableCell>{r.state_since ?? NA}</TableCell>
      <TableCell align="right">{flat ? NA : daysSince(r.state_since)}</TableCell>
      <TableCell align="right">{flat ? NA : money(r.entry_price)}</TableCell>
      <TableCell align="right">{money(r.last_close)}</TableCell>
      <TableCell align="right" sx={{ color: flat ? undefined : up ? green : red }}>
        {flat ? NA : signedPct(r.unrealized_pct)}
      </TableCell>
      <TableCell align="right">{flat ? NA : money(r.current_stop)}</TableCell>
      <VolCell v={r.vol_60d} />
    </TableRow>
  );
}

function WatchlistTable({ sections }: { sections: WatchSection[] }) {
  return (
    <Box sx={{ overflowX: "auto" }}>
      <Table size="small" sx={{ "& td, & th": { whiteSpace: "nowrap" } }}>
        <TableHead>
          <TableRow>
            <TableCell>Symbol</TableCell>
            <TableCell>State</TableCell>
            <TableCell>Since</TableCell>
            <TableCell align="right">Days</TableCell>
            <TableCell align="right">Entry</TableCell>
            <TableCell align="right">Last</TableCell>
            <TableCell align="right">Unreal.</TableCell>
            <Tooltip title="Current stop-loss price - the engine's trailing or initial stop" arrow><TableCell align="right">Stop</TableCell></Tooltip>
            <TableCell align="right">Vol 60d</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {sections.map((s) => (
            <Fragment key={s.title}>
              <TableRow>
                <TableCell
                  colSpan={WATCH_COLS}
                  sx={{
                    py: 0.25,
                    bgcolor: "action.hover",
                    fontSize: 11,
                    fontWeight: 700,
                    letterSpacing: 0.6,
                    textTransform: "uppercase",
                    color: "text.secondary",
                    borderBottom: "none",
                  }}
                >
                  {s.title}
                </TableCell>
              </TableRow>
              {s.rows.map((r) => (
                <WatchRow key={r.symbol} r={r} />
              ))}
            </Fragment>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}
