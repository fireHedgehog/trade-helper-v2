export interface MomentumInfo {
  score: number; // cross-sectional composite 0–100 from the last Multisectional ranking
  leader: boolean; // top-decile relative-strength leader
  persistence: number | null; // fraction of recent weekly formations spent in the lead
}

export interface MiniBar {
  t: string; // YYYY-MM-DD
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface MiniEvent {
  dir: "long" | "short";
  entry_date: string;
  entry_price: number | null;
  exit_date: string | null; // null → still open
  exit_price: number | null;
  exit_reason: string | null;
}

export interface BoardRow {
  symbol: string;
  state: "long" | "short" | "flat" | null;
  state_since: string | null;
  entry_price: number | null;
  last_close: number | null;
  unrealized_pct: number | null;
  current_stop: number | null;
  vol_60d?: number | null; // annualised 60-day return vol — watchlist rows only
  momentum?: MomentumInfo | null; // advisory peer-strength context, not a signal
  chart?: { bars: MiniBar[]; events: MiniEvent[] } | null; // only with ?charts=1
}

export interface WatchSection {
  title: string;
  rows: BoardRow[];
}

export interface BoardStrategy {
  id: number;
  key: string;
  name: string;
  is_default: boolean;
  note: string | null;
  assigned_count: number;
}

export interface BoardResponse {
  status: "ok" | "not_computed";
  computed_at?: string;
  engine_version?: string;
  counts?: { long: number; short: number; flat: number };
  long: BoardRow[];
  short: BoardRow[];
  flat: BoardRow[];
  watchlist: WatchSection[];
  strategies?: BoardStrategy[];
}
