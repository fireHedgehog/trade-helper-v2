import { api } from "@/shared/api/client";
import type { BoardRow } from "@/features/trend/types";
import type { TimingResponse } from "@/features/timing/types";

export interface PMChoice {
  key: string;
  version: string;
  name: string;
  direction: "long" | "short";
  status: string;
  error?: string | null;
  stale?: boolean;
  engine_stale?: boolean;
}
export interface PMChoices {
  status: "ok" | "not_computed";
  run_id?: number;
  run_status?: string;
  choices: PMChoice[];
}
export interface PMRow extends BoardRow {
  pm_key: string;
  pm_version: string;
  pm_name: string;
  status: string;
  error?: string | null;
}
export interface PMBoard {
  status: "ok" | "not_computed";
  run_id?: number;
  run_status?: string;
  computed_at?: string | null;
  pms: Pick<PMChoice, "key" | "name" | "direction">[];
  rows: PMRow[];
}
export const pmToken = (pm: Pick<PMChoice, "key" | "version">) => `${pm.key}@${pm.version}`;
export const pmApi = {
  board: () => api.get<PMBoard>("/pms/board"),
  choices: (symbol: string, runId?: number) => api.get<PMChoices>(`/pms/choices/${encodeURIComponent(symbol)}${runId ? `?run_id=${runId}` : ""}`),
  timing: (symbol: string, runId: number, choice: PMChoice) => api.get<TimingResponse>(
    `/pms/timing/${encodeURIComponent(symbol)}?${new URLSearchParams({ run_id: String(runId), key: choice.key, version: choice.version })}`),
};
