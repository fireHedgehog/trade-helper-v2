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
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";

import { FetchPanel } from "@/features/data-management/components/FetchPanel";

import { trendApi } from "./api";
import type { BoardRow, BoardResponse, WatchSection } from "./types";

const NA = "—";
const green = "#1f9d55";
const red = "#d64545";

const money = (v: number | null) => (v == null ? NA : v.toFixed(2));
const signedPct = (v: number | null) =>
  v == null ? NA : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
const daysSince = (iso: string | null) =>
  iso == null ? NA : Math.round((Date.now() - new Date(iso + "T00:00:00Z").getTime()) / 864e5);

export function TrendPage() {
  const [board, setBoard] = useState<BoardResponse | null>(null);
  const [showFlat, setShowFlat] = useState(false);

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
        <Typography variant="subtitle2" gutterBottom>
          Watchlist
        </Typography>
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
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.symbol}>
              <TableCell>
                <SymLink symbol={r.symbol} />
              </TableCell>
              <TableCell>{r.state_since ?? NA}</TableCell>
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
            <TableCell align="right">Stop</TableCell>
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
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
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

const WATCH_COLS = 8;

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
            <TableCell align="right">Stop</TableCell>
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
