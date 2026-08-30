-- Signal engine (Trend / Timing pages). One rule family — Donchian-channel
-- breakout, two-sided — specified in docs/draft-design/04-trend-page.md §R0-R10.
-- Full wipe-and-recompute per symbol per Run (docs/draft-design/01-data-model.md).

-- Saved parameter presets. Exactly one row has is_active = 1; the Timing page
-- edits it and the Run uses it.
CREATE TABLE IF NOT EXISTS signal_config (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    params_json TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

INSERT INTO signal_config (name, params_json, is_active) VALUES (
    'Donchian 20/10 (v1)',
    '{"model":"donchian","entry_len":20,"exit_len":10,"atr_len":20,'
    || '"atr_stop_mult":2.0,"trail_mode":"chandelier","chandelier_k":3.0,'
    || '"fill_at":"open_next","cost_bps":5.0,"slippage_atr":0.05,'
    || '"use_ma_regime":false,"ma_regime":200,"stop_and_reverse":false,'
    || '"warmup_buffer":10}',
    1
);

-- One row per Run invocation (single symbol from the Timing page, or the
-- whole universe from the Trend page in phase B).
CREATE TABLE IF NOT EXISTS signal_runs (
    run_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    scope          TEXT NOT NULL,             -- 'single' | 'universe'
    symbol         TEXT,                      -- set when scope = 'single'
    params_json    TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'running',  -- running | succeeded | failed
    started_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    finished_at    TEXT,
    n_symbols      INTEGER NOT NULL DEFAULT 0,
    n_events       INTEGER NOT NULL DEFAULT 0,
    error          TEXT
);

-- The trade list. A still-open position writes an entry row with NULL exit_*.
CREATE TABLE IF NOT EXISTS signal_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER NOT NULL,
    symbol       TEXT NOT NULL,
    direction    TEXT NOT NULL,               -- 'long' | 'short'
    entry_date   TEXT NOT NULL,
    entry_price  REAL NOT NULL,
    exit_date    TEXT,
    exit_price   REAL,
    exit_reason  TEXT,                         -- stop_initial | stop_trailing | channel_reversal | end_of_data
    bars_held    INTEGER,
    return_pct   REAL,                         -- direction-aware, costs included
    return_r     REAL,                         -- return in initial-risk units
    mae_atr      REAL,                         -- max adverse excursion, ATR units
    mfe_atr      REAL,                         -- max favourable excursion, ATR units
    initial_stop REAL,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_signal_events_symbol ON signal_events(symbol, entry_date);
CREATE INDEX IF NOT EXISTS idx_signal_events_run ON signal_events(run_id);

-- Cached per-symbol metrics + current board state (Long / Short / Flat).
CREATE TABLE IF NOT EXISTS signal_symbol_stats (
    run_id         INTEGER NOT NULL,
    symbol         TEXT NOT NULL,
    params_json    TEXT NOT NULL,
    state          TEXT NOT NULL,              -- 'long' | 'short' | 'flat'
    state_since    TEXT,                       -- entry date of the open position, else last exit date
    entry_price    REAL,
    last_close     REAL,
    last_date      TEXT,
    unrealized_pct REAL,
    current_stop   REAL,
    metrics_json   TEXT NOT NULL,
    updated_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (run_id, symbol)
);

-- Chart payload for the Timing page (single-symbol runs only): the engine
-- overlays (Donchian channel, trailing-stop line), the equity curve, and the
-- auto-drawn key levels — so GET /timing is a pure cache read.
CREATE TABLE IF NOT EXISTS signal_chart (
    run_id       INTEGER NOT NULL,
    symbol       TEXT NOT NULL,
    payload_json TEXT NOT NULL,                -- {overlays:{...}, equity:{...}, key_levels:[...]}
    PRIMARY KEY (run_id, symbol)
);
