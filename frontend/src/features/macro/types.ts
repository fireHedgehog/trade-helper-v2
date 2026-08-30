export interface SparkPoint {
  date: string;
  value: number;
}

export interface MacroCardData {
  series_id: string;
  label: string;
  units_short: string | null;
  frequency: string | null;
  point_count: number;
  latest_value: number | null;
  latest_date: string | null;
  spark: SparkPoint[];
  change_1m_pct: number | null;
  change_12m_pct: number | null;
  next_release_estimate: string | null;
  next_release_in_days: number | null;
  composite_feature: string | null;
  composite_sign: number | null;
  composite_confidence: "high" | "medium" | "low" | null;
  composite_rationale: string | null;
  composite_caveat: string | null;
  composite_z: number | null;
  composite_contribution: number | null;
}

export interface MacroCategory {
  key: string;
  label: string;
  series: MacroCardData[];
}

export interface CompositeReadout {
  score: number | null;
  zone: "risk-off" | "neutral" | "risk-on";
  n_used: number;
  note: string;
}

export interface MacroFactor {
  series_id: string;
  feature: string;
  sign: number;
  z: number | null;
  contribution: number | null;
}

export interface MacroOverview {
  as_of: string | null;
  composite: CompositeReadout & { reading?: string };
  categories: MacroCategory[];
  factors: MacroFactor[];
}

// ---- AI regime ----

export interface ModelOption {
  id: string;
  label: string;
  family: string;
  tier: "economy" | "standard" | "premium";
  input_usd_per_1m: number;
  output_usd_per_1m: number;
  default: boolean;
  enabled: boolean;
  available_on_account: boolean | null;
}

export interface BudgetPreset {
  key: "small" | "medium" | "large";
  label: string;
  personas: string[];
  rebuttal_round: boolean;
  rate_series_points: number;
  est_total_tokens: number;
  snapshot_detail: string;
}

export interface RegimeMessage {
  seq: number;
  role: "persona" | "rebuttal" | "reconciler";
  persona: string | null;
  round: number;
  prompt: string;
  completion: string;
  parsed_json: string | null;
  vote: string | null;
  conviction: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
}

export interface RegimeRun {
  id: number;
  created_at: string;
  trading_date: string;
  model: string;
  budget: string;
  prompt_version: number;
  score_raw: number | null;
  score: number | null;
  confidence_raw: number | null;
  confidence: number | null;
  calibration_notes: string | null;
  code_weighted_score: number | null;
  reconciler_score: number | null;
  event_overlay: number | null;
  weights_json: string | null;
  on_votes: number;
  off_votes: number;
  neutral_votes: number;
  summary: string | null;
  naive_score: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  cost_estimate_usd: number | null;
  status: string;
  error: string | null;
  messages: RegimeMessage[];
}

