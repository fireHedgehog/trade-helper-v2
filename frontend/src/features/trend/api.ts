import { api } from "@/shared/api/client";

import type { BoardResponse } from "./types";

export const trendApi = {
  board: () => api.get<BoardResponse>("/signals/board"),
};
