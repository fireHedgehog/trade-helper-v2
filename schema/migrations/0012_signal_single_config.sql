-- Reverting 0011's split. The Long / Short choice is now a pure VIEW FILTER
-- on the Timing page (which markers / trades / metrics to render) — it does
-- not affect tuning, the engine, or what is stored. Every Run computes the
-- full two-sided trade set and stores all of it. Back to one active config.

DELETE FROM signal_config;

INSERT INTO signal_config (name, params_json, is_active, profile) VALUES (
    'Donchian 20/10 (v1)',
    '{"model":"donchian","entry_len":20,"exit_len":10,"atr_len":20,'
    || '"atr_stop_mult":2.0,"trail_mode":"chandelier","chandelier_k":3.0,'
    || '"atr_trail_k":3.0,"fill_at":"open_next","cost_bps":5.0,"slippage_atr":0.05,'
    || '"use_ma_regime":false,"ma_regime":200,"stop_and_reverse":false,'
    || '"warmup_buffer":10,"allow_long":true,"allow_short":true}',
    1, 'both'
);

-- signal_runs.profile / .directions and signal_symbol_stats.profile stay as
-- nullable columns; runs stop populating them.
