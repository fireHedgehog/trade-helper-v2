import type { SignalParams } from "@/features/timing/types";

export interface Strategy {
  id: number;
  key: string;
  name: string;
  params: SignalParams;
  is_default: boolean;
  note: string | null;
  assigned_count: number;
  created_at?: string;
  updated_at?: string;
}

export interface StrategyListResponse {
  strategies: Strategy[];
  engine_version: string;
}

export interface StrategyDetail extends Strategy {
  symbols: string[];
}

export interface AssignResponse {
  assigned: number;
  symbols: string[];
}
