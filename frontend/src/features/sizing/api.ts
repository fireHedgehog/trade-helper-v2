import { api } from '@/shared/api/client';
import type { SizingBoard, SizingParams, PortfolioResult } from './types';
export const sizingApi = {
  board:()=>api.get<SizingBoard>('/signals/board'),
  latest:()=>api.get<PortfolioResult>('/sizing/latest'),
  run:(params:SizingParams)=>api.post<{run_id:number;deduped:boolean}>('/sizing/run',params),
};
