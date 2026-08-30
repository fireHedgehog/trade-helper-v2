import { api } from "@/shared/api/client";

import type { RankingResponse, RankingRow, ScreenKey, SortKey } from "./types";

export const multisectionalApi = {
  ranking: () => api.get<RankingResponse>("/multisectional/ranking"),
  recompute: () => api.post<RankingResponse>("/multisectional/ranking/recompute"),
};

// Faithful ports of the reference page's screen/sort predicates.

export function screenMatches(row: RankingRow, screen: ScreenKey): boolean {
  if (screen === "liquid") return row.is_liquid_top100;
  if (screen === "leaders") return row.is_current_leader;
  if (screen === "portfolio") return (row.candidate_weight ?? 0) > 0;
  if (screen === "aligned") return row.above_all_mas;
  return true;
}

export function compareRows(a: RankingRow, b: RankingRow, sort: SortKey): number {
  if (sort === "liquidity_rank") {
    return (
      (a.liquidity_rank ?? Infinity) - (b.liquidity_rank ?? Infinity) ||
      a.symbol.localeCompare(b.symbol)
    );
  }
  const primary = (b[sort] ?? -Infinity) - (a[sort] ?? -Infinity);
  if (primary) return primary;
  if (sort === "leadership_persistence") {
    const momentum = (b.rs_3m_percentile ?? -Infinity) - (a.rs_3m_percentile ?? -Infinity);
    if (momentum) return momentum;
  }
  return a.symbol.localeCompare(b.symbol);
}
