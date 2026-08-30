export interface RankingRow {
  symbol: string;
  name: string | null;
  category: string | null;
  as_of: string;
  price: number;
  score: number | null;
  technical_context_score: number | null;
  rs_3m: number | null;
  rs_6m: number | null;
  rs_12m: number | null;
  high_52w_distance: number | null;
  trend_distance: number | null;
  slope: number | null;
  above_all_mas: boolean;
  ordered_mas: boolean;
  median_dollar_volume_21d: number | null;
  liquidity_rank: number | null;
  is_liquid_top100: boolean;
  rs_3m_percentile: number | null;
  is_current_leader: boolean;
  leadership_appearances_13w: number | null;
  leadership_persistence: number | null;
  candidate_weight: number | null;
  return_5d: number | null;
  reversal_5d_percentile: number | null;
  sector_relative_return_5d: number | null;
  sector_relative_reversal_percentile: number | null;
  is_reversal_watch: boolean;
}

export interface RankingResponse {
  status: string; // "descriptive_research" | "not_computed"
  universe?: string;
  member_count?: number;
  eligible_count?: number;
  latest_price_date: string | null;
  benchmark?: string;
  leadership_formation_count?: number;
  liquid_top100_count?: number;
  current_leader_count?: number;
  active_sleeve_count?: number;
  reversal_watch_count?: number;
  composite_weights?: Record<string, number>;
  data_gaps?: string[];
  rows: RankingRow[];
  sources?: { role: string; table: string; selection: string }[];
  // caching
  computed_at: string | null;
  newest_price_date: string | null;
  stale: boolean;
}

export type ScreenKey = "liquid" | "leaders" | "portfolio" | "aligned" | "all";

export type SortKey =
  | "leadership_persistence"
  | "rs_3m_percentile"
  | "candidate_weight"
  | "liquidity_rank"
  | "score"
  | "rs_3m"
  | "rs_6m"
  | "rs_12m"
  | "high_52w_distance"
  | "trend_distance"
  | "slope"
  | "median_dollar_volume_21d";
