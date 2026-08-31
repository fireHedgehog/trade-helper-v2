-- Board reference column: annualised 60-day return volatility, stored per run
-- alongside the other cached per-symbol board fields. Distinct from the
-- engine's 20-day ATR (which sizes stops); this is the position-sizing sigma
-- from the frozen research (docs/strategy-experiments/naive-donchian-v1-result.md).

ALTER TABLE signal_symbol_stats ADD COLUMN vol_60d REAL;
