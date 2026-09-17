import { api } from "@/shared/api/client";

import type { BoardResponse } from "./types";

export const trendApi = {
  // charts=true attaches per-watchlist-row mini-chart bars + trade markers
  // (~1.3 MB) — only the Trend page's "graph mode" asks for it.
  board: (family: string, charts = false) =>
    api.get<BoardResponse>(`/pms/trend/${encodeURIComponent(family)}${charts ? "?charts=1" : ""}`),
};
