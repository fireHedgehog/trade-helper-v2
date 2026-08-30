import { api } from "@/shared/api/client";

import type { BudgetPreset, MacroOverview, ModelOption, RegimeRun } from "./types";

interface RunRegimeBody {
  model?: string;
  budget?: "small" | "medium" | "large";
  force?: boolean;
}

export const macroApi = {
  overview: () => api.get<MacroOverview>("/macro/overview"),

  models: () =>
    api.get<{ models: ModelOption[]; default: string; checked: boolean }>(
      "/macro/ai-regime/models?check=1",
    ),
  budgets: () => api.get<BudgetPreset[]>("/macro/ai-regime/budgets"),

  latestRegime: () =>
    api.get<RegimeRun | { run: null }>("/macro/ai-regime/latest"),
  runRegime: (body: RunRegimeBody) =>
    api.post<RegimeRun>("/macro/ai-regime/run", body),
};
