import type { Sleeve, SleeveGroup } from "./constants";

// The board rows this page consumes. A subset of the Trend board response
// (src/features/trend/types.ts) — re-declared here so the sizing feature owns
// its contract. `sector` was added to the board response for this page.
export interface SizingBoardRow {
  symbol: string;
  state: "long" | "short" | "flat" | null;
  state_since: string | null;
  last_close: number | null;
  vol_60d?: number | null;
  sector?: string | null;
  momentum?: { score: number; leader: boolean } | null;
}

export interface SizingBoard {
  status: "ok" | "not_computed";
  computed_at?: string;
  long: SizingBoardRow[];
  short: SizingBoardRow[];
  flat: SizingBoardRow[];
  watchlist: { title: string; rows: SizingBoardRow[] }[];
}

export type RegimeZone = "risk-on" | "neutral" | "risk-off";

export interface MacroContext {
  source: "ai-regime" | "naive-composite" | "none";
  score: number | null; // 0–100 where available
  zone: RegimeZone;
  label: string; // e.g. "AI regime 58.7"
}

export interface SizingParams {
  nav: number;
  volTargetPct: number; // portfolio annualised vol target, %
  kMax: number; // gross-exposure cap, × NAV
  perNameCapPct: number; // % of NAV
  perSectorCapPct: number; // % of target gross
  bookVolOverridePct: number | null; // null → estimate from the names in scope
  enforceSleeveBudget: boolean;
  sleeveBudget: Record<SleeveGroup, number>; // fractions, ~sum 1
  scopeLong: boolean;
  scopeShort: boolean; // include the board's short bucket
  shortResearchOnly: boolean; // ...but restrict it to bond ETFs + BTC (the research verdict)
  scopeWatchlist: boolean;
  mode: "full" | "new";
  newDays: number;
  macroEnabled: boolean;
  neutralScale: number; // gross multiplier when regime is neutral
  riskOffScale: number; // gross multiplier when regime is risk-off
  deployed: Record<Sleeve, number>; // already-held % of NAV per sleeve
}

export type Verdict = "ADD" | "LIGHT" | "BLOCKED" | "TRIM" | "WAIT";

export interface SizingRow {
  symbol: string;
  state: "long" | "short";
  sleeve: Sleeve;
  vol60d: number; // annualised fraction
  lastClose: number;
  momentum: number | null;
  daysSinceEntry: number | null;
  invVolRawPct: number; // step 1 — inverse-vol, scaled so gross = k_max
  afterNameCapPct: number; // step 2 — per-name cap
  afterSectorCapPct: number; // step 3 — per-sector cap + sleeve budget
  afterVolTargetPct: number; // step 4 — whole-book vol target
  targetPct: number; // step 5 — macro overlay → final
  targetUsd: number;
  shares: number;
  verdict: Verdict;
  notes: string[];
}

export interface SleeveLoad {
  sleeve: Sleeve;
  deployedPct: number;
  newPct: number;
  capPct: number;
  trimPct: number; // deployed above this sleeve's cap — how much to cut here
  over: boolean;
}

export interface SizingResult {
  rows: SizingRow[];
  excluded: { symbol: string; reason: string }[];
  assumedVolCount: number; // rows sized off the placeholder σ (pre-0015 board run)
  otherNoSectorCount: number; // rows with no sector tag, bucketed to Other
  targetGrossPct: number;
  deployedGrossPct: number;
  headroomPct: number;
  headroomUsd: number;
  overshootPct: number; // deployed above the target book — trim, don't add
  overshootUsd: number;
  addCount: number;
  cashAfterPct: number;
  maxNamePct: number;
  sleeveLoads: SleeveLoad[];
  estBookVolPct: number;
  volScale: number;
  macroScale: number;
  bindingConstraint: string;
  kmaxSensitivity: { k: number; grossPct: number }[];
  // segmented-gross-bar inputs (all % of NAV). `held` = deployed up to target;
  // `over` = deployed above target (the trim band).
  bar: { held: number; over: number; canAdd: number; roomToKmax: number; macroBlocked: number };
}
