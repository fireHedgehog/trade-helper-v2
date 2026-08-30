export interface SignalParams {
  model: "donchian";
  entry_len: number;
  exit_len: number;
  atr_len: number;
  atr_stop_mult: number;
  trail_mode: "chandelier" | "exit_channel" | "atr_trail";
  chandelier_k: number;
  atr_trail_k: number;
  fill_at: "close" | "open_next";
  cost_bps: number;
  slippage_atr: number;
  use_ma_regime: boolean;
  ma_regime: number;
  stop_and_reverse: boolean;
  warmup_buffer: number;
  allow_long: boolean;
  allow_short: boolean;
}

export type Direction = "long" | "short";

export interface ConfigResponse {
  name: string;
  params: SignalParams;
  engine_version: string;
  updated_at: string;
}

export interface DailyPoint {
  date: string;
  state: -1 | 0 | 1; // signed exposure during that bar
  strat_ret: number; // that bar's contribution, costs included
}

export interface Bar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Marker {
  time: string;
  side: "long" | "short";
  kind: "entry" | "exit";
  label?: string;
}

export interface Trade {
  direction: "long" | "short";
  entry_date: string;
  entry_price: number;
  exit_date: string | null;
  exit_price: number | null;
  exit_reason: string | null;
  bars_held: number | null;
  return_pct: number | null;
  return_r: number | null;
  mae_atr: number | null;
  mfe_atr: number | null;
  initial_stop: number | null;
}

export interface KeyLevel {
  price: number;
  label: string;
  kind: string;
}

export interface Overlays {
  dates: string[];
  donchian_up: (number | null)[];
  donchian_dn: (number | null)[];
  stop_line: (number | null)[];
}

export interface EquityCurve {
  dates: string[];
  strat_equity: number[];
  bh_equity: number[];
  drawdown: number[];
}

export interface BoardState {
  state: "long" | "short" | "flat" | null;
  state_since: string | null;
  entry_price: number | null;
  last_close: number | null;
  unrealized_pct: number | null;
  current_stop: number | null;
}

export interface Metrics {
  label: string;
  trade_stats: Record<string, number | string | null>;
  strategy: Record<string, number | null>;
  buy_hold: Record<string, number | null>;
}

export interface TimingResponse {
  status: "ok" | "not_computed";
  symbol: string;
  computed_at?: string;
  engine_version?: string;
  params?: SignalParams;
  run_scope?: "single" | "universe";
  chart_cached?: boolean; // false after a Trend (universe) run — press Run for overlays/equity
  stale?: boolean;
  newest_price_date?: string | null;
  run_through_date?: string | null;
  bars?: Bar[];
  overlays?: Overlays;
  key_levels?: KeyLevel[];
  equity?: EquityCurve;
  daily?: DailyPoint[];
  markers?: Marker[];
  trades?: Trade[];
  state?: BoardState;
  metrics?: Metrics;
}
