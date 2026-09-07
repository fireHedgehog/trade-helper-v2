-- The long strategy and fixed short benchmark share one symbol snapshot.
BEGIN;
ALTER TABLE signal_symbol_stats ADD COLUMN directions_json TEXT;
UPDATE signal_strategies SET is_default = 0;
INSERT INTO signal_strategies (key, name, params_json, is_default, note) VALUES (
    'trend-long-v2', 'Trend long 20/55',
    '{"model":"donchian","entry_len":20,"exit_len":55,"atr_len":20,"atr_stop_mult":3.0,"trail_mode":"chandelier","chandelier_k":3.0,"atr_trail_k":3.0,"initial_enabled":true,"channel_enabled":true,"trailing_enabled":false,"fill_at":"open_next","cost_bps":5.0,"slippage_atr":0.05,"use_ma_regime":false,"ma_regime":200,"stop_and_reverse":false,"warmup_buffer":10,"allow_long":true,"allow_short":false}',
    1, 'Long breakout: 20-bar entry, 55-bar channel exit, initial 3xATR stop; no Chandelier. Equal-capital sizing is the default. The independent short benchmark remains fixed at 20/20, initial 2xATR and Chandelier 3xATR.'
);
UPDATE assets SET strategy_id = (SELECT id FROM signal_strategies WHERE key = 'trend-long-v2')
 WHERE strategy_id IS NULL OR strategy_id IN (SELECT id FROM signal_strategies WHERE key IN ('naive-donchian-v1','naive-donchian-v1-slow-entry'));
UPDATE crypto_assets SET strategy_id = (SELECT id FROM signal_strategies WHERE key = 'trend-long-v2')
 WHERE strategy_id IS NULL OR strategy_id IN (SELECT id FROM signal_strategies WHERE key IN ('naive-donchian-v1','naive-donchian-v1-slow-entry'));
UPDATE signal_config SET name = 'Trend long 20/55', params_json = (SELECT params_json FROM signal_strategies WHERE key = 'trend-long-v2');
UPDATE signal_strategies SET note = 'Legacy long preset; available for comparison. The short benchmark is independent and fixed.'
 WHERE key IN ('naive-donchian-v1','naive-donchian-v1-slow-entry');
CREATE TABLE portfolio_result (
    id INTEGER PRIMARY KEY CHECK (id = 1), run_id INTEGER NOT NULL,
    engine_version TEXT NOT NULL, computed_at TEXT NOT NULL,
    params_json TEXT NOT NULL, result_gzip BLOB NOT NULL
);
