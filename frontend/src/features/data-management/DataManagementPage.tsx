import { useCallback, useEffect, useMemo, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { dataApi } from "./api";
import { ActiveRunsBanner } from "./components/ActiveRunsBanner";
import { DetailDialog } from "./components/DetailDialog";
import { FetchPanel } from "./components/FetchPanel";
import { ServerTable, type Column } from "./components/ServerTable";
import { SimpleTable } from "./components/SimpleTable";
import type {
  AssetRow,
  CommodityRow,
  CryptoRow,
  MacroRow,
  MembershipGroupRow,
  OptionStatRow,
  Page,
  RunItem,
  RunStatus,
} from "./types";

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <Paper sx={{ p: 2.5, mb: 2 }}>
      <Typography variant="h6">{title}</Typography>
      {description && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          {description}
        </Typography>
      )}
      {children}
    </Paper>
  );
}

const num = (v: unknown, digits = 2) =>
  typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: digits }) : "—";

const BAR_COLUMNS: Column<Record<string, unknown>>[] = [
  { key: "date", label: "Date" },
  { key: "close", label: "Close", align: "right", render: (r) => num(r.close) },
  { key: "adj_close", label: "Adj close", align: "right", render: (r) => num(r.adj_close) },
  { key: "volume", label: "Volume", align: "right", render: (r) => num(r.volume, 0) },
  { key: "trade_count", label: "Trades", align: "right", render: (r) => num(r.trade_count, 0) },
  { key: "vwap", label: "VWAP", align: "right", render: (r) => num(r.vwap) },
  { key: "fetched_at", label: "Fetched" },
];

const OBS_COLUMNS: Column<Record<string, unknown>>[] = [
  { key: "date", label: "Date" },
  { key: "value", label: "Value", align: "right", render: (r) => num(r.value, 4) },
  { key: "realtime_start", label: "Vintage start" },
  { key: "realtime_end", label: "Vintage end" },
  { key: "fetched_at", label: "Fetched" },
];

const MEMBER_COLUMNS: Column<Record<string, unknown>>[] = [
  { key: "symbol", label: "Symbol" },
  { key: "name", label: "Name" },
  { key: "sector", label: "Sector" },
  { key: "weight", label: "Weight %", align: "right", render: (r) => num(r.weight, 3) },
  { key: "in_universe", label: "In catalog", render: (r) => (r.in_universe ? "yes" : "no") },
  { key: "source", label: "Source" },
];

// --- Panels -----------------------------------------------------------------

function AssetsPanel({ tick, bump }: { tick: number; bump: () => void }) {
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<AssetRow | null>(null);

  const fetcher = useCallback(
    (page: number, pageSize: number): Promise<Page<AssetRow>> =>
      dataApi.assets({ q: q || undefined, page, page_size: pageSize, active_only: true }),
    [q],
  );

  const columns: Column<AssetRow>[] = useMemo(
    () => [
      { key: "symbol", label: "Symbol" },
      { key: "name", label: "Name" },
      { key: "exchange", label: "Exch." },
      { key: "sector", label: "Sector" },
      {
        key: "memberships",
        label: "Tags",
        render: (r) =>
          r.memberships
            ? r.memberships
                .split(",")
                .slice(0, 4)
                .map((g) => <Chip key={g} size="small" label={g} sx={{ mr: 0.5 }} />)
            : "—",
      },
      { key: "bar_count", label: "Bars", align: "right", render: (r) => num(r.bar_count, 0) },
      { key: "first_date", label: "First" },
      { key: "last_date", label: "Last" },
      { key: "last_close", label: "Last close", align: "right", render: (r) => num(r.last_close) },
      { key: "last_fetched", label: "Fetched" },
    ],
    [],
  );

  return (
    <Section
      title="Asset price data"
      description="Daily bars (raw + adjusted) for the active universe. Incremental by default — pulls only the missing tail. Click a row for its full history."
    >
      <FetchPanel kind="asset_prices" allowFullMode buttonLabel="Fetch asset prices" onDone={bump} />
      <TextField
        size="small"
        placeholder="Search symbol / name"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        sx={{ mt: 2, mb: 1, maxWidth: 320 }}
      />
      <ServerTable
        columns={columns}
        fetcher={fetcher}
        rowKey={(r) => r.symbol}
        onRowClick={setSelected}
        refreshKey={tick}
      />
      {selected && (
        <DetailDialog
          open
          onClose={() => setSelected(null)}
          title={`${selected.symbol} — ${selected.name ?? ""}`}
          header={selected as unknown as Record<string, unknown>}
          columns={BAR_COLUMNS}
          fetcher={(page, pageSize) => dataApi.assetBars(selected.symbol, page, pageSize)}
          rowKey={(r) => String(r.date)}
        />
      )}
    </Section>
  );
}

function MacroPanel({ tick, bump }: { tick: number; bump: () => void }) {
  const [rows, setRows] = useState<MacroRow[]>([]);
  const [selected, setSelected] = useState<MacroRow | null>(null);

  useEffect(() => {
    void dataApi.macro().then(setRows);
  }, [tick]);

  const columns: Column<MacroRow>[] = [
    { key: "series_id", label: "Series" },
    { key: "short_label", label: "Label" },
    { key: "category", label: "Category" },
    { key: "frequency", label: "Freq" },
    { key: "point_count", label: "Obs", align: "right", render: (r) => num(r.point_count, 0) },
    { key: "first_date", label: "First" },
    { key: "last_date", label: "Last" },
    { key: "last_value", label: "Latest", align: "right", render: (r) => num(r.last_value, 4) },
    { key: "last_fetched", label: "Fetched" },
  ];

  return (
    <Section
      title="Macro data"
      description="FRED series for the Macro page. Incremental runs also re-fetch the trailing 90 days to catch revisions."
    >
      <FetchPanel kind="macro" allowFullMode buttonLabel="Fetch macro data" onDone={bump} />
      <Box sx={{ mt: 2 }}>
        <SimpleTable
          columns={columns}
          rows={rows}
          rowKey={(r) => r.series_id}
          onRowClick={setSelected}
          emptyText="Catalog is seeded; press Fetch macro data to pull observations."
        />
      </Box>
      {selected && (
        <DetailDialog
          open
          onClose={() => setSelected(null)}
          title={`${selected.series_id} — ${selected.short_label ?? selected.title ?? ""}`}
          header={selected as unknown as Record<string, unknown>}
          columns={OBS_COLUMNS}
          fetcher={(page, pageSize) =>
            dataApi.macroObservations(selected.series_id, page, pageSize)
          }
          rowKey={(r) => String(r.date)}
        />
      )}
    </Section>
  );
}

function MembershipsPanel({ tick, bump }: { tick: number; bump: () => void }) {
  const [rows, setRows] = useState<MembershipGroupRow[]>([]);
  const [selected, setSelected] = useState<MembershipGroupRow | null>(null);
  useEffect(() => {
    void dataApi.memberships().then(setRows);
  }, [tick]);

  const columns: Column<MembershipGroupRow>[] = [
    { key: "group_key", label: "Group" },
    { key: "group_type", label: "Type" },
    { key: "name", label: "Name" },
    { key: "gics_sector", label: "GICS sector" },
    { key: "member_count", label: "Members", align: "right", render: (r) => num(r.member_count, 0) },
    {
      key: "in_universe_count",
      label: "In catalog",
      align: "right",
      render: (r) => num(r.in_universe_count, 0),
    },
    { key: "last_source_as_of", label: "Source as-of" },
    { key: "last_synced_at", label: "Synced" },
  ];

  return (
    <Section
      title="Index & sector tags"
      description="Constituents of the S&P 500 / Nasdaq-100 / Dow, the 11 sector SPDRs (→ GICS sector on each asset), and theme ETFs (XBI, SOXX, IGV, ARKX). Scraped from issuer holdings files. Also fills assets.sector and Nasdaq-100 market caps."
    >
      <FetchPanel kind="memberships" buttonLabel="Sync memberships" onDone={bump} />
      <Box sx={{ mt: 2 }}>
        <SimpleTable
          columns={columns}
          rows={rows}
          rowKey={(r) => r.group_key}
          onRowClick={setSelected}
          emptyText="Not synced yet — press Sync memberships."
        />
      </Box>
      {selected && (
        <DetailDialog
          open
          onClose={() => setSelected(null)}
          title={`${selected.group_key} — ${selected.name ?? ""}`}
          header={selected as unknown as Record<string, unknown>}
          columns={MEMBER_COLUMNS}
          fetcher={(page, pageSize) => dataApi.groupMembers(selected.group_key, page, pageSize)}
          rowKey={(r) => String(r.symbol)}
        />
      )}
    </Section>
  );
}

function CryptoPanel({ tick, bump }: { tick: number; bump: () => void }) {
  const [rows, setRows] = useState<CryptoRow[]>([]);
  const [selected, setSelected] = useState<CryptoRow | null>(null);
  useEffect(() => {
    void dataApi.crypto().then(setRows);
  }, [tick]);

  const columns: Column<CryptoRow>[] = [
    { key: "symbol", label: "Pair" },
    { key: "name", label: "Name" },
    { key: "active", label: "Active", render: (r) => (r.active ? "yes" : "no") },
    { key: "bar_count", label: "Bars", align: "right", render: (r) => num(r.bar_count, 0) },
    { key: "first_date", label: "First" },
    { key: "last_date", label: "Last" },
    { key: "last_close", label: "Last close", align: "right", render: (r) => num(r.last_close) },
    { key: "last_fetched", label: "Fetched" },
  ];

  return (
    <Section title="Crypto" description="BTC/USD and ETH/USD daily bars (Alpaca crypto, 24/7).">
      <FetchPanel kind="crypto_bars" allowFullMode buttonLabel="Fetch crypto bars" onDone={bump} />
      <Box sx={{ mt: 2 }}>
        <SimpleTable columns={columns} rows={rows} rowKey={(r) => r.symbol} onRowClick={setSelected} />
      </Box>
      {selected && (
        <DetailDialog
          open
          onClose={() => setSelected(null)}
          title={selected.symbol}
          header={selected as unknown as Record<string, unknown>}
          columns={BAR_COLUMNS.filter((c) => c.key !== "adj_close")}
          fetcher={(page, pageSize) => dataApi.cryptoBars(selected.symbol, page, pageSize)}
          rowKey={(r) => String(r.date)}
        />
      )}
    </Section>
  );
}

function CommoditiesPanel({ tick, bump }: { tick: number; bump: () => void }) {
  const [rows, setRows] = useState<CommodityRow[]>([]);
  const [selected, setSelected] = useState<CommodityRow | null>(null);
  useEffect(() => {
    void dataApi.commodities().then(setRows);
  }, [tick]);

  const columns: Column<CommodityRow>[] = [
    { key: "instrument", label: "Instrument" },
    { key: "name", label: "Name" },
    { key: "fred_series_id", label: "FRED id" },
    { key: "unit", label: "Unit" },
    { key: "point_count", label: "Points", align: "right", render: (r) => num(r.point_count, 0) },
    { key: "first_date", label: "First" },
    { key: "last_date", label: "Last" },
    { key: "last_value", label: "Latest", align: "right", render: (r) => num(r.last_value, 3) },
    { key: "last_fetched", label: "Fetched" },
  ];

  const OBS: Column<Record<string, unknown>>[] = [
    { key: "date", label: "Date" },
    { key: "price", label: "Price", align: "right", render: (r) => num(r.price, 3) },
    { key: "fetched_at", label: "Fetched" },
  ];

  return (
    <Section
      title="Commodities"
      description="WTI, Brent, Natural Gas spot from FRED (daily). Gold & silver are covered by the GLD / SLV ETFs in the asset table."
    >
      <FetchPanel
        kind="commodity_prices"
        allowFullMode
        buttonLabel="Fetch commodity prices"
        onDone={bump}
      />
      <Box sx={{ mt: 2 }}>
        <SimpleTable
          columns={columns}
          rows={rows}
          rowKey={(r) => r.instrument}
          onRowClick={setSelected}
        />
      </Box>
      {selected && (
        <DetailDialog
          open
          onClose={() => setSelected(null)}
          title={`${selected.instrument} — ${selected.name}`}
          header={selected as unknown as Record<string, unknown>}
          columns={OBS}
          fetcher={(page, pageSize) =>
            dataApi.commodityPrices(selected.instrument, page, pageSize)
          }
          rowKey={(r) => String(r.date)}
        />
      )}
    </Section>
  );
}

function OptionsPanel({ tick, bump }: { tick: number; bump: () => void }) {
  const [rows, setRows] = useState<OptionStatRow[]>([]);
  useEffect(() => {
    void dataApi.options().then(setRows);
  }, [tick]);

  const columns: Column<OptionStatRow>[] = [
    { key: "underlying", label: "Underlying" },
    { key: "bucket", label: "Bucket" },
    {
      key: "snapshot_days",
      label: "Days stored",
      align: "right",
      render: (r) => num(r.snapshot_days, 0),
    },
    { key: "last_snapshot", label: "Last snapshot" },
    {
      key: "last_day_rows",
      label: "Grid rows / day",
      align: "right",
      render: (r) => num(r.last_day_rows, 0),
    },
    {
      key: "snapshot_rows",
      label: "Rows total",
      align: "right",
      render: (r) => num(r.snapshot_rows, 0),
    },
    { key: "last_fetched", label: "Fetched" },
  ];

  return (
    <Section
      title="Options (IV-surface grid)"
      description="Daily chain snapshot for a small core set (SPY/QQQ + MAG7 + SMH). Per name per day we keep a fixed grid — 6 tenors × 7 moneyness points, nearest listed contract each — with quote + greeks + implied vol (Alpaca indicative feed, 15-min delayed). No backfill: history builds forward one snapshot per run. Run once a day on trading days."
    >
      <FetchPanel kind="option_snapshots" buttonLabel="Fetch option snapshots" onDone={bump} />
      <Box sx={{ mt: 2 }}>
        <SimpleTable
          columns={columns}
          rows={rows}
          rowKey={(r) => r.underlying}
          emptyText="No snapshots yet — press Fetch option snapshots."
        />
      </Box>
    </Section>
  );
}

function RunHistoryPanel({ tick }: { tick: number }) {
  const [rows, setRows] = useState<RunStatus[]>([]);
  const [items, setItems] = useState<{ run: RunStatus; items: RunItem[] } | null>(null);

  const load = useCallback(() => {
    void dataApi.runs(25).then(setRows);
  }, []);
  useEffect(load, [load, tick]);

  const columns: Column<RunStatus>[] = [
    { key: "id", label: "#" },
    { key: "kind", label: "Kind" },
    { key: "mode", label: "Mode" },
    { key: "scope", label: "Scope" },
    {
      key: "status",
      label: "Status",
      render: (r) => (
        <Chip
          size="small"
          label={r.status}
          color={
            r.status === "succeeded"
              ? "success"
              : r.status === "failed"
                ? "error"
                : r.status === "cancelled"
                  ? "warning"
                  : "info"
          }
        />
      ),
    },
    {
      key: "progress",
      label: "Targets",
      align: "right",
      render: (r) => `${r.completed_targets}/${r.planned_targets}`,
    },
    { key: "rows_written", label: "Rows", align: "right", render: (r) => num(r.rows_written, 0) },
    { key: "started_at", label: "Started" },
  ];

  return (
    <Section title="Run history">
      <Button size="small" onClick={load} sx={{ mb: 1 }}>
        Refresh
      </Button>
      <SimpleTable
        columns={columns}
        rows={rows}
        rowKey={(r) => String(r.id)}
        onRowClick={(r) =>
          dataApi.runItems(r.id).then((its) => setItems({ run: r, items: its }))
        }
      />
      {items && (
        <DetailDialog
          open
          onClose={() => setItems(null)}
          title={`Run #${items.run.id} — ${items.run.kind}`}
          header={items.run as unknown as Record<string, unknown>}
          columns={[
            { key: "target", label: "Target" },
            { key: "status", label: "Status" },
            { key: "rows_written", label: "Rows", align: "right" },
            { key: "coverage_start", label: "From" },
            { key: "coverage_end", label: "To" },
            { key: "duration_ms", label: "ms", align: "right" },
            { key: "error", label: "Error" },
          ]}
          fetcher={(page, pageSize) =>
            Promise.resolve({
              rows: items.items.slice((page - 1) * pageSize, page * pageSize),
              total: items.items.length,
              page,
              page_size: pageSize,
            })
          }
          rowKey={(r) => String((r as unknown as RunItem).target)}
        />
      )}
    </Section>
  );
}

// --- Page -----------------------------------------------------------------

export function DataManagementPage() {
  const [tick, setTick] = useState(0);
  const bump = useCallback(() => setTick((t) => t + 1), []);

  return (
    <div>
      <Typography variant="h5" gutterBottom>
        Data management
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        The only place data enters this app. Fetches are paced (one request at a time, well under
        each provider's rate limit) and run in the foreground with a live progress bar. First full
        pull is slow; later runs are incremental.
      </Typography>

      <Alert severity="info" sx={{ mb: 2 }}>
        Needs the Alpaca and FRED keys — set them on the{" "}
        <Link component={RouterLink} to="/credentials">
          Credentials
        </Link>{" "}
        page.
      </Alert>

      <ActiveRunsBanner onSettled={bump} />

      <Section
        title="Asset catalog"
        description="Sync the Alpaca asset list (active + inactive US equities, plus crypto). Metadata only — this does not fetch prices. It also marks the Phase-1 active price-fetch universe."
      >
        <FetchPanel kind="asset_catalog" buttonLabel="Sync asset catalog" onDone={bump} />
      </Section>

      <MembershipsPanel tick={tick} bump={bump} />
      <AssetsPanel tick={tick} bump={bump} />
      <MacroPanel tick={tick} bump={bump} />
      <CryptoPanel tick={tick} bump={bump} />
      <CommoditiesPanel tick={tick} bump={bump} />
      <OptionsPanel tick={tick} bump={bump} />
      <RunHistoryPanel tick={tick} />
    </div>
  );
}
