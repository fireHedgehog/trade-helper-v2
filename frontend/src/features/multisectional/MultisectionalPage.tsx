import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link as RouterLink } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import RefreshIcon from "@mui/icons-material/Refresh";

import { ApiError } from "@/shared/api/client";

import { compareRows, multisectionalApi, screenMatches } from "./api";
import { EvidenceBar } from "./components/EvidenceBar";
import type { RankingResponse, RankingRow, ScreenKey, SortKey } from "./types";

const NA = "—";
const pct = (v: number | null) => (v == null ? NA : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`);
const num = (v: number | null, d = 1) => (v == null ? NA : v.toFixed(d));

const SCREENS: { key: ScreenKey; label: string }[] = [
  { key: "liquid", label: "Liquid Top-100" },
  { key: "leaders", label: "Current leaders" },
  { key: "portfolio", label: "Active 13-week sleeves" },
  { key: "aligned", label: "Above all MAs" },
  { key: "all", label: "All eligible" },
];

const SORTS: { key: SortKey; label: string }[] = [
  { key: "leadership_persistence", label: "Leadership persistence" },
  { key: "rs_3m_percentile", label: "Current 3M percentile" },
  { key: "candidate_weight", label: "Candidate weight" },
  { key: "liquidity_rank", label: "Liquidity rank" },
  { key: "score", label: "Technical context score" },
  { key: "rs_3m", label: "3m vs SPY" },
  { key: "rs_6m", label: "6m vs SPY" },
  { key: "rs_12m", label: "12m vs SPY" },
  { key: "high_52w_distance", label: "52w high proximity" },
  { key: "trend_distance", label: "MA distance" },
  { key: "slope", label: "MA slope" },
  { key: "median_dollar_volume_21d", label: "Dollar volume" },
];

function SummaryTile({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Paper sx={{ p: 1.5, minWidth: 150, flex: "1 1 150px" }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
        {label}
      </Typography>
      <Typography variant="h6">{value}</Typography>
    </Paper>
  );
}

function EvidenceStatus({ row }: { row: RankingRow }) {
  if (row.is_current_leader)
    return <Chip size="small" color="success" label="Current leader" variant="outlined" />;
  if ((row.candidate_weight ?? 0) > 0)
    return <Chip size="small" color="info" label="Active sleeve" variant="outlined" />;
  return <Chip size="small" label="Context" variant="outlined" />;
}

function StructureChip({ row }: { row: RankingRow }) {
  const label = row.ordered_mas ? "Ordered" : row.above_all_mas ? "Above all" : "Mixed";
  const color = row.ordered_mas ? "success" : row.above_all_mas ? "info" : "default";
  return <Chip size="small" label={label} color={color} variant="outlined" />;
}

function SymbolCell({ symbol, name }: { symbol: string; name?: string | null }) {
  return (
    <Box>
      <Link
        component={RouterLink}
        to={`/timing/${encodeURIComponent(symbol)}`}
        sx={{ fontWeight: 700 }}
      >
        {symbol}
      </Link>
      {name ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
          {name}
        </Typography>
      ) : null}
    </Box>
  );
}

const MAIN_HEADERS = [
  "Rank", "Symbol", "Evidence", "3M %ile", "13W persistence", "Cand. weight", "Liquidity",
  "3m vs SPY", "Tech. context", "6m vs SPY", "12m vs SPY", "52w high", "MA distance", "MA slope",
  "Structure",
];

function fmtWhen(iso: string | null): string {
  if (!iso) return "never";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export function MultisectionalPage() {
  const [data, setData] = useState<RankingResponse | null>(null);
  const [loading, setLoading] = useState(true); // first cached fetch
  const [recomputing, setRecomputing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [screen, setScreen] = useState<ScreenKey>("liquid");
  const [sort, setSort] = useState<SortKey>("leadership_persistence");
  const [query, setQuery] = useState("");

  // On mount: read the last cached snapshot only — no recompute.
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await multisectionalApi.ranking());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load the ranking");
    } finally {
      setLoading(false);
    }
  }, []);

  // The button: run the ~2 s computation over the current price data + store it.
  const recompute = useCallback(async () => {
    setRecomputing(true);
    setError(null);
    try {
      setData(await multisectionalApi.recompute());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Recompute failed");
    } finally {
      setRecomputing(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const notComputed = data?.status === "not_computed";
  const formationCount = data?.leadership_formation_count ?? 0;

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return [...(data?.rows ?? [])]
      .filter((r) => screenMatches(r, screen))
      .filter((r) => !q || r.symbol.toLowerCase().includes(q) || (r.name ?? "").toLowerCase().includes(q))
      .sort((a, b) => compareRows(a, b, sort));
  }, [data, screen, sort, query]);

  const reversalRows = useMemo(
    () =>
      [...(data?.rows ?? [])]
        .filter((r) => r.is_reversal_watch)
        .sort(
          (a, b) =>
            Math.max(b.reversal_5d_percentile ?? -Infinity, b.sector_relative_reversal_percentile ?? -Infinity) -
            Math.max(a.reversal_5d_percentile ?? -Infinity, a.sector_relative_reversal_percentile ?? -Infinity),
        ),
    [data],
  );

  return (
    <div>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "flex-start", mb: 1 }}>
        <Box>
          <Typography variant="h5" gutterBottom>
            Multisectional — cross-sectional ranking
          </Typography>
          <Typography color="text.secondary" sx={{ maxWidth: 760 }}>
            Which names currently look strongest by price/volume alone, and how persistent that
            leadership has been. Descriptive research — not validated alpha or a trade
            recommendation. This is a stored snapshot; press <strong>Recompute</strong> after a
            price fetch to run it against the latest data.
          </Typography>
          {data && !notComputed && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
              Computed {fmtWhen(data.computed_at)} · price data through{" "}
              {data.latest_price_date || "—"}
            </Typography>
          )}
        </Box>
        <Button
          onClick={recompute}
          disabled={recomputing || loading}
          startIcon={recomputing ? <CircularProgress size={16} /> : <RefreshIcon />}
          variant={data?.stale || notComputed ? "contained" : "outlined"}
          sx={{ flexShrink: 0 }}
        >
          {recomputing ? "Computing…" : "Recompute"}
        </Button>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {loading && !data && <CircularProgress size={24} />}

      {notComputed && !loading && (
        <Alert severity="info" sx={{ mb: 2 }}>
          No ranking computed yet.{" "}
          {data?.newest_price_date
            ? `Price data goes through ${data.newest_price_date}. `
            : "Fetch asset prices first, then "}
          press <strong>Recompute</strong>.
        </Alert>
      )}

      {data && !notComputed && data.stale && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Newer price data is available (through {data.newest_price_date}, this snapshot used{" "}
          {data.latest_price_date}). Press <strong>Recompute</strong> to refresh.
        </Alert>
      )}

      {data && !notComputed && (
        <>
          {(data.data_gaps ?? []).length > 0 && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              <Typography variant="subtitle2">Degraded — missing data</Typography>
              <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                {(data.data_gaps ?? []).map((g, i) => (
                  <li key={i}>
                    <Typography variant="caption">{g}</Typography>
                  </li>
                ))}
              </ul>
            </Alert>
          )}

          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.5, mb: 2 }}>
            <SummaryTile label="Liquid evidence pool" value={data.liquid_top100_count} />
            <SummaryTile label="Current 3M leaders" value={data.current_leader_count} />
            <SummaryTile label="Active 13-week sleeves" value={data.active_sleeve_count} />
            <SummaryTile label="Latest price date" value={data.latest_price_date || NA} />
            <SummaryTile label="Weekly formations" value={data.leadership_formation_count} />
            <SummaryTile
              label="Model status"
              value={<Chip size="small" color="warning" label="Research only" />}
            />
          </Box>

          <Paper sx={{ p: 2.5, mb: 2 }}>
            <Typography variant="overline" color="text.secondary">
              Evidence-informed translation
            </Typography>
            <Typography variant="h6">Liquid 3M leadership and persistence</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              The liquid Top-100 is selected by trailing 21-session dollar volume with a $5 raw-price
              floor. Current leaders are the top decile of exact-date 3M excess return vs SPY.
              Persistence = how often a name entered the last {formationCount} weekly leader sleeves;
              candidate weight is the natural average of those equal-weight sleeves — not an
              authorised allocation.
            </Typography>

            <Stack direction="row" spacing={1.5} sx={{ mb: 2, flexWrap: "wrap" }} useFlexGap>
              <TextField
                size="small"
                placeholder="Symbol or company"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                sx={{ minWidth: 200 }}
              />
              <TextField
                select
                size="small"
                label="Screen"
                value={screen}
                onChange={(e) => setScreen(e.target.value as ScreenKey)}
                sx={{ minWidth: 200 }}
              >
                {SCREENS.map((s) => (
                  <MenuItem key={s.key} value={s.key}>
                    {s.label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                size="small"
                label="Sort by"
                value={sort}
                onChange={(e) => setSort(e.target.value as SortKey)}
                sx={{ minWidth: 220 }}
              >
                {SORTS.map((s) => (
                  <MenuItem key={s.key} value={s.key}>
                    {s.label}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>

            <TableContainer sx={{ maxHeight: 620, overflowX: "auto" }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    {MAIN_HEADERS.map((h) => (
                      <TableCell key={h} sx={{ whiteSpace: "nowrap" }}>
                        {h}
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rows.slice(0, 100).map((row, i) => (
                    <TableRow key={row.symbol} hover>
                      <TableCell>{i + 1}</TableCell>
                      <TableCell sx={{ minWidth: 140 }}>
                        <SymbolCell symbol={row.symbol} name={row.name} />
                      </TableCell>
                      <TableCell>
                        <EvidenceStatus row={row} />
                      </TableCell>
                      <TableCell>
                        <EvidenceBar value={row.rs_3m_percentile} />
                      </TableCell>
                      <TableCell>
                        <EvidenceBar
                          value={row.leadership_persistence == null ? null : row.leadership_persistence * 100}
                        />
                        <Typography variant="caption" color="text.secondary">
                          {row.leadership_appearances_13w ?? NA}/{formationCount}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">{pct(row.candidate_weight)}</TableCell>
                      <TableCell align="right">
                        {row.liquidity_rank == null ? NA : `#${row.liquidity_rank}`}
                      </TableCell>
                      <TableCell align="right">{pct(row.rs_3m)}</TableCell>
                      <TableCell align="right">
                        <strong>{num(row.technical_context_score, 1)}</strong>
                      </TableCell>
                      <TableCell align="right">{pct(row.rs_6m)}</TableCell>
                      <TableCell align="right">{pct(row.rs_12m)}</TableCell>
                      <TableCell align="right">{pct(row.high_52w_distance)}</TableCell>
                      <TableCell align="right">{pct(row.trend_distance)}</TableCell>
                      <TableCell align="right">{pct(row.slope)}</TableCell>
                      <TableCell>
                        <StructureChip row={row} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            {rows.length > 100 && (
              <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
                Showing the first 100 of {rows.length}; search or change the screen or sort to inspect
                another name.
              </Typography>
            )}
          </Paper>

          <Paper sx={{ p: 2.5, mb: 2 }}>
            <Typography variant="overline" color="text.secondary">
              {data.reversal_watch_count} current observations
            </Typography>
            <Typography variant="h6">Short-term rebound watch — execution fragile</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              The most negative 5-session returns, raw and relative to a sufficiently populated
              sector. It gets no momentum weight — a watchlist, not an allocation sleeve.
            </Typography>
            <TableContainer sx={{ overflowX: "auto" }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    {["Symbol", "5D return", "Loss %ile", "Sector-rel. 5D", "Sector loss %ile", "Boundary"].map(
                      (h) => (
                        <TableCell key={h} sx={{ whiteSpace: "nowrap" }}>
                          {h}
                        </TableCell>
                      ),
                    )}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {reversalRows.map((row) => (
                    <TableRow key={row.symbol} hover>
                      <TableCell>
                        <SymbolCell symbol={row.symbol} />
                      </TableCell>
                      <TableCell align="right">{pct(row.return_5d)}</TableCell>
                      <TableCell>
                        <EvidenceBar value={row.reversal_5d_percentile} tone="warning" />
                      </TableCell>
                      <TableCell align="right">{pct(row.sector_relative_return_5d)}</TableCell>
                      <TableCell>
                        <EvidenceBar value={row.sector_relative_reversal_percentile} tone="warning" />
                      </TableCell>
                      <TableCell>
                        <Chip size="small" color="warning" label="No weight" variant="outlined" />
                      </TableCell>
                    </TableRow>
                  ))}
                  {reversalRows.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={6}>
                        <Typography variant="body2" color="text.secondary" sx={{ py: 1 }}>
                          Nothing on the rebound watch right now.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          <Paper sx={{ p: 2.5, mb: 2 }}>
            <Typography variant="overline" color="text.secondary">
              Preserved product contract
            </Typography>
            <Typography variant="h6">Technical context score, not validated alpha</Typography>
            <Typography variant="body2" color="text.secondary">
              The composite in the table blends percentile ranks of 3m / 6m / 12m excess return vs
              SPY (
              {Object.entries(data.composite_weights ?? {})
                .filter(([k]) => k.startsWith("rs_"))
                .map(([, v]) => `${Math.round(v * 100)}%`)
                .join(" / ")}
              ), 52-week-high proximity ({Math.round((data.composite_weights?.high_52w_distance ?? 0) * 100)}%),
              four-MA distance ({Math.round((data.composite_weights?.trend_distance ?? 0) * 100)}%), and MA
              slope ({Math.round((data.composite_weights?.slope ?? 0) * 100)}%). Missing inputs are
              dropped and the remaining weights renormalise.
            </Typography>
          </Paper>

          <Paper sx={{ p: 2.5 }}>
            <Typography variant="overline" color="text.secondary">
              Read-only source inventory
            </Typography>
            <Typography variant="h6">Research data selection</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              No ranking table is persisted. This view selects the universe, price and benchmark
              layers and computes the ranking in memory. Recompute never fetches a provider.
            </Typography>
            <Divider sx={{ mb: 1 }} />
            <TableContainer sx={{ overflowX: "auto" }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Role</TableCell>
                    <TableCell>Table</TableCell>
                    <TableCell>Selection</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(data.sources ?? []).map((s) => (
                    <TableRow key={s.role}>
                      <TableCell>{s.role}</TableCell>
                      <TableCell>
                        <code>{s.table}</code>
                      </TableCell>
                      <TableCell>{s.selection}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </>
      )}
    </div>
  );
}
