import type { BoardResponse, BoardRow } from '../trend/types';
export interface SizingParams {
  scope: 'priority' | 'universe'; window: 'full' | 'recent';
  book: 'long-initial' | 'short-reference' | 'combined-initial';
  method: 'equal' | 'inverse-vol' | 'capped-vol'; cost: 'normal' | 'double'; capital: number;
}
export const DEFAULT_PARAMS: SizingParams = {scope:'priority',window:'recent',book:'long-initial',method:'equal',cost:'normal',capital:100000};
export const METHODS = {'equal':'Equal capital','inverse-vol':'Inverse volatility','capped-vol':'Inverse volatility + caps'};
export const BOOKS = {'long-initial':'Long strategy','short-reference':'Short benchmark','combined-initial':'Long + short · 50/50'};
export interface AllocationInput extends BoardRow {
  priority?: boolean; bars?: number; asset_class?: string; quantity_increment?: number; min_order_size?: number;
}
export interface SizingBoard extends BoardResponse { universe?: AllocationInput[] }
export interface AllocationRow {
  symbol:string; direction:'long'|'short'; group:string; price:number; vol:number;
  signalDate:string|null; pending:boolean; units:number; notional:number; costs:number; weight:number;
}
export interface Contribution {
  symbol:string; group:string; priority:boolean; long_pnl:number; short_pnl:number;
  net_pnl:number; contribution:number; fees:number; slippage:number; borrow:number;
  long_entries:number; short_entries:number; unfunded:number; open_long:number; open_short:number;
}
export interface PortfolioTrade {
  symbol:string; direction:'long'|'short'; entry_date:string; entry_price:number;
  units:number; exit_date:string|null; mark_date:string; mark_price:number;
  price_pnl:number; entry_fee:number; exit_fee:number; entry_slippage:number; exit_slippage:number;
  borrow:number; reason:string;
}
export interface PortfolioStats {
  ending:number; cagr:number|null; net:number; drawdown:number; average_gross:number;
  fees:number; slippage:number; borrow:number; entries:number; assets_funded:number;
  stale_position_days:number; maximum_stale_gross:number; funding_deficit_days:number;
  long_contribution:number; short_contribution:number;
  annual:{year:string;net:number;drawdown:number;start:string;end:string}[];
}
export interface PortfolioResult {
  status:'ok'|'not_computed'; params?:SizingParams; computed_at?:string; needs_recompute?:boolean;
  stats?:PortfolioStats; curve?:[string,...number[]][]; assets?:Contribution[]; trades?:PortfolioTrade[];
  benchmark?:{stats:PortfolioStats;curve:[string,number][]};
  audit?:{unfunded:number;sleeve_deficit_days:number};
}
