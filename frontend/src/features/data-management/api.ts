import { api } from "@/shared/api/client";

import type {
  AssetRow,
  CommodityRow,
  CryptoRow,
  FetchKind,
  MacroRow,
  MembershipGroupRow,
  OptionStatRow,
  Page,
  RunItem,
  RunStatus,
} from "./types";

interface StartRunBody {
  kind: FetchKind;
  mode?: "incremental" | "full";
  scope?: "all" | "watchlist" | "single";
  scope_arg?: string;
}

export const dataApi = {
  startRun: (body: StartRunBody) =>
    api.post<{ run_id: number; deduped: boolean }>("/data/runs", body),
  run: (id: number) => api.get<RunStatus>(`/data/runs/${id}`),
  runs: (limit = 25) => api.get<RunStatus[]>(`/data/runs?limit=${limit}`),
  activeRuns: () => api.get<RunStatus[]>("/data/runs/active"),
  runItems: (id: number) => api.get<RunItem[]>(`/data/runs/${id}/items`),
  cancelRun: (id: number) => api.post<{ ok: boolean }>(`/data/runs/${id}/cancel`),

  assets: (params: { q?: string; page: number; page_size: number; active_only?: boolean }) => {
    const qs = new URLSearchParams({
      page: String(params.page),
      page_size: String(params.page_size),
      active_only: String(params.active_only ?? true),
    });
    if (params.q) qs.set("q", params.q);
    return api.get<Page<AssetRow>>(`/data/assets?${qs}`);
  },
  assetBars: (symbol: string, page: number, page_size: number) =>
    api.get<Page<Record<string, unknown>>>(
      `/data/assets/${encodeURIComponent(symbol)}/bars?page=${page}&page_size=${page_size}`,
    ),

  memberships: () => api.get<MembershipGroupRow[]>("/data/memberships"),
  groupMembers: (groupKey: string, page: number, page_size: number) =>
    api.get<Page<Record<string, unknown>>>(
      `/data/memberships/${encodeURIComponent(groupKey)}/members?page=${page}&page_size=${page_size}`,
    ),

  options: () => api.get<OptionStatRow[]>("/data/options"),

  macro: () => api.get<MacroRow[]>("/data/macro"),
  macroObservations: (seriesId: string, page: number, page_size: number) =>
    api.get<Page<Record<string, unknown>>>(
      `/data/macro/${encodeURIComponent(seriesId)}/observations?page=${page}&page_size=${page_size}`,
    ),

  crypto: () => api.get<CryptoRow[]>("/data/crypto"),
  cryptoBars: (symbol: string, page: number, page_size: number) =>
    api.get<Page<Record<string, unknown>>>(
      `/data/crypto/bars?symbol=${encodeURIComponent(symbol)}&page=${page}&page_size=${page_size}`,
    ),

  commodities: () => api.get<CommodityRow[]>("/data/commodities"),
  commodityPrices: (instrument: string, page: number, page_size: number) =>
    api.get<Page<Record<string, unknown>>>(
      `/data/commodities/${encodeURIComponent(instrument)}/prices?page=${page}&page_size=${page_size}`,
    ),
};
