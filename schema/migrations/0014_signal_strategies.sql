-- Naive Donchian V1 strategy registry (research handoff, docs/temp).
--
-- Several named strategies, each an immutable parameter snapshot. Every asset
-- and crypto_asset row points at exactly one (explicit id, no NULL-means-
-- default). The Trend / universe run resolves per-symbol parameters from here
-- instead of the single signal_config preset.
--
-- Direction is NOT a strategy filter. The board still computes long/short for
-- every symbol so a future short-capable strategy needs no re-fetch; the
-- long/short recommendation lives in the UI, not the engine.
--
-- signal_config and its GET /PUT /config route stay untouched as a vestigial
-- fallback — never delete its seed row.

CREATE TABLE IF NOT EXISTS signal_strategies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    params_json TEXT NOT NULL,
    is_default  INTEGER NOT NULL DEFAULT 0,   -- exactly one row = 1
    note        TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

INSERT INTO signal_strategies (key, name, params_json, is_default, note) VALUES
  ('naive-donchian-v1',
   'Naive Donchian V1',
   '{"model":"donchian","entry_len":20,"exit_len":20,"atr_len":20,'
   || '"atr_stop_mult":2.0,"trail_mode":"chandelier","chandelier_k":3.0,'
   || '"atr_trail_k":3.0,"fill_at":"open_next","cost_bps":5.0,"slippage_atr":0.05,'
   || '"use_ma_regime":false,"ma_regime":200,"stop_and_reverse":false,'
   || '"warmup_buffer":10,"allow_long":true,"allow_short":false}',
   1,
   'Frozen benchmark. Fast 20-day entry channel; c3_d20 exit = Chandelier 3xATR '
   || 'trailing stop + Donchian-20 reversal backstop + initial 2xATR disaster '
   || 'stop. Direction default is long only. Research (docs/temp handoff) shows '
   || 'Bond ETFs and BTC/USD gain materially from the short side, but the Trend '
   || 'board runs long/short for every symbol regardless — the recommendation is '
   || 'advisory only.'),
  ('naive-donchian-v1-slow-entry',
   'Naive Donchian V1 - slow entry (bonds)',
   '{"model":"donchian","entry_len":100,"exit_len":20,"atr_len":20,'
   || '"atr_stop_mult":2.0,"trail_mode":"chandelier","chandelier_k":3.0,'
   || '"atr_trail_k":3.0,"fill_at":"open_next","cost_bps":5.0,"slippage_atr":0.05,'
   || '"use_ma_regime":false,"ma_regime":200,"stop_and_reverse":false,'
   || '"warmup_buffer":10,"allow_long":true,"allow_short":true}',
   0,
   'Bond-ETF exception. Identical to V1 except the entry channel is a slow 100 '
   || 'days — bond trends are slower and the fast 20-day break whipsaws. Also '
   || 'long/short: for bonds the short side is roughly Sharpe-neutral and adds '
   || 'CAGR through rate-hike bear legs.');

ALTER TABLE assets        ADD COLUMN strategy_id INTEGER REFERENCES signal_strategies(id);
ALTER TABLE crypto_assets ADD COLUMN strategy_id INTEGER REFERENCES signal_strategies(id);
ALTER TABLE signal_symbol_stats ADD COLUMN strategy_id INTEGER;

-- Explicit assignment for the tradable universe (active assets + all crypto):
-- default V1, bond ETFs -> slow. Dormant assets stay NULL and fall back to the
-- default strategy if they are ever activated.
UPDATE assets        SET strategy_id = (SELECT id FROM signal_strategies WHERE key = 'naive-donchian-v1') WHERE active = 1;
UPDATE crypto_assets SET strategy_id = (SELECT id FROM signal_strategies WHERE key = 'naive-donchian-v1') WHERE active = 1;

UPDATE assets SET strategy_id = (SELECT id FROM signal_strategies WHERE key = 'naive-donchian-v1-slow-entry')
 WHERE active = 1 AND symbol IN (
   'BIL','SHV','SHY','IEF','TLT','GOVT',
   'LQD','HYG','JNK','TIP','AGG','BND','BNDX','EMB','MBB','MUB','FLOT'
 );

CREATE INDEX IF NOT EXISTS idx_assets_strategy        ON assets(strategy_id);
CREATE INDEX IF NOT EXISTS idx_crypto_assets_strategy ON crypto_assets(strategy_id);
