import { api } from "@/shared/api/client";
import { dataApi } from "@/features/data-management/api";

import type { ConfigResponse, SignalParams, TimingResponse } from "./types";

export const timingApi = {
  config: () => api.get<ConfigResponse>("/signals/config"),
  saveConfig: (params: SignalParams, name?: string) =>
    api.put<ConfigResponse>("/signals/config", { name, params }),
  run: (symbol: string) => api.post<TimingResponse>("/signals/run", { symbol }),
  timing: (symbol: string) =>
    api.get<TimingResponse>(`/signals/timing/${encodeURIComponent(symbol)}`),
};

export interface SymbolOption {
  symbol: string;
  name: string | null;
}

// Reuse the assets search for the picker; fold in the two crypto pairs.
// The API matches symbol OR name (so "MU" also matches every "...Communications"),
// so re-rank client-side: exact symbol, then symbol prefix, then symbol
// substring, then name-only matches.
export async function searchSymbols(q: string): Promise<SymbolOption[]> {
  const query = q.trim();
  const Q = query.toUpperCase();
  const crypto: SymbolOption[] = [
    { symbol: "BTC/USD", name: "Bitcoin" },
    { symbol: "ETH/USD", name: "Ethereum" },
  ].filter((c) => !Q || c.symbol.includes(Q));

  const page = await dataApi.assets({
    ...(query ? { q: query } : {}),
    page: 1,
    page_size: 50,
    active_only: true,
  });
  const rows = page.rows.map((r) => ({ symbol: r.symbol, name: r.name }));
  if (Q) {
    const rank = (s: string) => (s === Q ? 0 : s.startsWith(Q) ? 1 : s.includes(Q) ? 2 : 3);
    rows.sort((a, b) => rank(a.symbol) - rank(b.symbol) || a.symbol.localeCompare(b.symbol));
  }
  return [...crypto, ...rows];
}
