-- Two independent parameter libraries: 'long' (tuned for long-only names —
-- US large caps that are rarely shortable in size) and 'short' (tuned for a
-- book that also shorts — small caps, semis, BTC). The Timing-page Run has
-- Long / Short checkboxes; only-Long uses the 'long' library, anything with
-- Short uses the 'short' library. Each run records which library + directions
-- it used.

ALTER TABLE signal_config ADD COLUMN profile TEXT NOT NULL DEFAULT 'long';
ALTER TABLE signal_runs ADD COLUMN profile TEXT;
ALTER TABLE signal_runs ADD COLUMN directions TEXT;
ALTER TABLE signal_symbol_stats ADD COLUMN profile TEXT;

-- Configs are disposable (docs/01-data-model.md) — reseed the two libraries.
DELETE FROM signal_config;

INSERT INTO signal_config (name, params_json, is_active, profile) VALUES
  ('Long-only (Donchian 20/10)',
   '{"model":"donchian","entry_len":20,"exit_len":10,"atr_len":20,'
   || '"atr_stop_mult":2.0,"trail_mode":"chandelier","chandelier_k":3.0,'
   || '"atr_trail_k":3.0,"fill_at":"open_next","cost_bps":5.0,"slippage_atr":0.05,'
   || '"use_ma_regime":false,"ma_regime":200,"stop_and_reverse":false,'
   || '"warmup_buffer":10,"allow_long":true,"allow_short":false}',
   1, 'long'),
  ('Long + Short (Donchian 20/10)',
   '{"model":"donchian","entry_len":20,"exit_len":10,"atr_len":20,'
   || '"atr_stop_mult":2.0,"trail_mode":"chandelier","chandelier_k":3.0,'
   || '"atr_trail_k":3.0,"fill_at":"open_next","cost_bps":5.0,"slippage_atr":0.05,'
   || '"use_ma_regime":false,"ma_regime":200,"stop_and_reverse":false,'
   || '"warmup_buffer":10,"allow_long":true,"allow_short":true}',
   1, 'short');
