import { api } from "@/shared/api/client";

import type { AssignResponse, StrategyDetail, StrategyListResponse } from "./types";

export const strategyApi = {
  list: () => api.get<StrategyListResponse>("/signals/strategies"),
  detail: (id: number) => api.get<StrategyDetail>(`/signals/strategies/${id}`),
  assign: (id: number, symbols: string[]) =>
    api.post<AssignResponse>(`/signals/strategies/${id}/assign`, { symbols }),
};
