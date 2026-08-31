export interface BoardRow {
  symbol: string;
  state: "long" | "short" | "flat" | null;
  state_since: string | null;
  entry_price: number | null;
  last_close: number | null;
  unrealized_pct: number | null;
  current_stop: number | null;
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
