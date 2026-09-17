import { api } from "@/shared/api/client";
import type { BoardRow } from "@/features/trend/types";
import type { TimingResponse } from "@/features/timing/types";

export interface PMChoice {
  key: string;
  version: string;
  name: string;
  family: string;
  direction: "long" | "short";
  status: string;
  error?: string | null;
  stale?: boolean;
  engine_stale?: boolean;
}
export interface PMChoices {
  computed_at?: string | null;
  status: "ok" | "not_computed";
  run_id?: number;
  run_status?: string;
  choices: PMChoice[];
}
export interface PMRow extends BoardRow {
  pm_key: string;
  pm_version: string;
  pm_name: string;
  family: string;
  status: string;
  error?: string | null;
}
export interface PMBoard {
  status: "ok" | "not_computed";
  run_id?: number;
  run_status?: string;
  computed_at?: string | null;
  pms: Pick<PMChoice, "key" | "name" | "family" | "direction">[];
  rows: PMRow[];
}
export const pmToken = (pm: Pick<PMChoice, "key" | "version">) => `${pm.key}@${pm.version}`;
export const pmApi = {
  strategies: () => api.get<RegisteredStrategy[]>("/pms/strategies"),
  familyTiming: (symbol: string, runId: number, family: string) => api.get<TimingResponse>(
    `/pms/family-timing/${encodeURIComponent(symbol)}?${new URLSearchParams({run_id: String(runId), family})}`),
  board: () => api.get<PMBoard>("/pms/board"),
  choices: (symbol: string, runId?: number, family?: string) => api.get<PMChoices>(
    `/pms/choices/${encodeURIComponent(symbol)}?${new URLSearchParams({...runId ? {run_id:String(runId)} : {}, ...family ? {family} : {}})}`),
  timing: (symbol: string, runId: number, choice: PMChoice) => api.get<TimingResponse>(
    `/pms/timing/${encodeURIComponent(symbol)}?${new URLSearchParams({ run_id: String(runId), key: choice.key, version: choice.version })}`),
};

export interface RegisteredStrategy { key: string; name: string }
