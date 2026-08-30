export type FetchKind =
  | "asset_catalog"
  | "asset_prices"
  | "crypto_bars"
  | "commodity_prices"
  | "macro"
  | "memberships"
  | "option_snapshots"
  | "signal_universe";

export interface RunStatus {
  id: number;
  kind: FetchKind;
  mode: string;
  scope: string;
  scope_arg: string | null;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  planned_targets: number;
  completed_targets: number;
  failed_targets: number;
  rows_written: number;
  requests_made: number;
  current_target: string | null;
  started_at: string;
  finished_at: string | null;
  error_summary: string | null;
  queue_depth: number;
}

export interface RunItem {
  run_id: number;
  target: string;
  status: "pending" | "ok" | "skipped" | "error";
  rows_written: number;
  requests_made: number;
  coverage_start: string | null;
  coverage_end: string | null;
  duration_ms: number | null;
  error: string | null;
}

export interface Page<T> {
  rows: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface AssetRow {
  symbol: string;
  name: string | null;
  asset_class: string;
  exchange: string | null;
  sector: string | null;
  status: string;
  has_options: number;
  active: number;
  bar_count: number | null;
  first_date: string | null;
  last_date: string | null;
  last_close: number | null;
  last_fetched: string | null;
  memberships: string | null;
}

export interface MacroRow {
  series_id: string;
  title: string | null;
  short_label: string | null;
  category: string;
  frequency: string | null;
  units_short: string | null;
  tracked: number;
  typical_lag_days: number;
  observation_end: string | null;
  last_fetched_at: string | null;
  point_count: number | null;
  first_date: string | null;
  last_date: string | null;
  last_value: number | null;
  last_fetched: string | null;
}

export interface CryptoRow {
  symbol: string;
  name: string | null;
  status: string;
  active: number;
  bar_count: number | null;
  first_date: string | null;
  last_date: string | null;
  last_close: number | null;
  last_fetched: string | null;
}

export interface MembershipGroupRow {
  group_key: string;
  group_type: string;
  name: string | null;
  gics_sector: string | null;
  source_url: string | null;
  last_source_as_of: string | null;
  last_synced_at: string | null;
  member_count: number;
  in_universe_count: number;
}

export interface OptionStatRow {
  underlying: string;
  bucket: string;
  last_snapshot: string | null;
  snapshot_rows: number | null;
  last_fetched: string | null;
  snapshot_days: number;
  last_day_rows: number;
}

export interface CommodityRow {
  instrument: string;
  name: string;
  fred_series_id: string;
  unit: string;
  category: string;
  observation_end: string | null;
  last_fetched_at: string | null;
  point_count: number | null;
  first_date: string | null;
  last_date: string | null;
  last_value: number | null;
  last_fetched: string | null;
}
