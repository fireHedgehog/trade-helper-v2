-- 0003_data_management.sql
-- Data-management data model. One CREATE TABLE per instrument "family" — never
-- mixed (see docs/draft-design/09-data-management-fetch-audit.md §0). Seed rows
-- for the fixed catalogs (macro series, commodities, membership groups, the
-- options research set).
--
-- Families:
--   equities/ETFs : assets, price_bars, price_bar_stats
--   crypto        : crypto_assets, crypto_bars, crypto_bar_stats
--   commodities   : commodity_series, commodity_prices, commodity_price_stats
--   macro         : macro_series_catalog, macro_observations, macro_obs_stats
--   options       : option_contracts, option_chain_snapshots, option_snapshot_stats
--   classification: membership_groups, symbol_memberships
--   AI regime     : ai_regime_runs, ai_regime_votes
--   operational   : fetch_runs, fetch_run_items

-- ---------------------------------------------------------------------------
-- Equities & ETFs
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS assets (
    symbol                   TEXT PRIMARY KEY,
    alpaca_asset_id          TEXT,
    name                     TEXT,
    asset_class              TEXT NOT NULL DEFAULT 'us_equity',
    exchange                 TEXT,
    status                   TEXT NOT NULL DEFAULT 'active',
    tradable                 INTEGER NOT NULL DEFAULT 0,
    marginable               INTEGER NOT NULL DEFAULT 0,
    shortable                INTEGER NOT NULL DEFAULT 0,
    fractionable             INTEGER NOT NULL DEFAULT 0,
    borrow_status            TEXT,
    margin_requirement_long  TEXT,
    margin_requirement_short TEXT,
    cusip                    TEXT,
    has_options              INTEGER NOT NULL DEFAULT 0,
    attributes_json          TEXT,
    sector                   TEXT,
    industry                 TEXT,
    market_cap               INTEGER,          -- reserved; NULL in v1
    active                   INTEGER NOT NULL DEFAULT 0,   -- our price-fetch flag
    first_seen_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_synced_at           TEXT
);
CREATE INDEX IF NOT EXISTS idx_assets_active ON assets(active);
CREATE INDEX IF NOT EXISTS idx_assets_sector ON assets(sector);
CREATE INDEX IF NOT EXISTS idx_assets_class  ON assets(asset_class);

CREATE TABLE IF NOT EXISTS price_bars (
    symbol       TEXT NOT NULL,
    date         TEXT NOT NULL,               -- YYYY-MM-DD
    open         REAL NOT NULL,
    high         REAL NOT NULL,
    low          REAL NOT NULL,
    close        REAL NOT NULL,
    volume       INTEGER NOT NULL,
    adj_open     REAL,
    adj_high     REAL,
    adj_low      REAL,
    adj_close    REAL,
    adj_volume   INTEGER,
    trade_count  INTEGER,
    vwap         REAL,
    feed         TEXT NOT NULL DEFAULT 'iex',
    source       TEXT NOT NULL DEFAULT 'alpaca',
    fetched_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_bars_symbol_date ON price_bars(symbol, date DESC);

-- Maintained summary so list views never scan price_bars.
CREATE TABLE IF NOT EXISTS price_bar_stats (
    symbol        TEXT PRIMARY KEY,
    bar_count     INTEGER NOT NULL DEFAULT 0,
    first_date    TEXT,
    last_date     TEXT,
    last_close    REAL,
    adv20_dollar  REAL,                        -- trailing 20-day avg dollar volume
    last_fetched  TEXT
);

-- ---------------------------------------------------------------------------
-- Crypto  (24/7, no adjustment concept)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS crypto_assets (
    symbol              TEXT PRIMARY KEY,      -- e.g. BTC/USD
    alpaca_asset_id     TEXT,
    name                TEXT,
    status              TEXT NOT NULL DEFAULT 'active',
    tradable            INTEGER NOT NULL DEFAULT 0,
    min_order_size      TEXT,
    min_trade_increment TEXT,
    price_increment     TEXT,
    active              INTEGER NOT NULL DEFAULT 0,
    first_seen_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_synced_at      TEXT
);

CREATE TABLE IF NOT EXISTS crypto_bars (
    symbol       TEXT NOT NULL,
    date         TEXT NOT NULL,
    open         REAL NOT NULL,
    high         REAL NOT NULL,
    low          REAL NOT NULL,
    close        REAL NOT NULL,
    volume       REAL NOT NULL,
    trade_count  INTEGER,
    vwap         REAL,
    source       TEXT NOT NULL DEFAULT 'alpaca',
    fetched_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_crypto_symbol_date ON crypto_bars(symbol, date DESC);

CREATE TABLE IF NOT EXISTS crypto_bar_stats (
    symbol       TEXT PRIMARY KEY,
    bar_count    INTEGER NOT NULL DEFAULT 0,
    first_date   TEXT,
    last_date    TEXT,
    last_close   REAL,
    last_fetched TEXT
);

-- ---------------------------------------------------------------------------
-- Commodities  (FRED daily single-value price fixings)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS commodity_series (
    instrument         TEXT PRIMARY KEY,       -- WTI / BRENT / GOLD / NATGAS
    name               TEXT NOT NULL,
    fred_series_id     TEXT NOT NULL,
    unit               TEXT NOT NULL,
    category           TEXT NOT NULL,          -- energy / metal
    observation_start  TEXT,
    observation_end    TEXT,
    fred_last_updated  TEXT,
    last_fetched_at    TEXT
);

CREATE TABLE IF NOT EXISTS commodity_prices (
    instrument     TEXT NOT NULL,
    date           TEXT NOT NULL,
    price          REAL,                       -- NULL when FRED returns "."
    realtime_start TEXT,
    realtime_end   TEXT,
    fetched_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (instrument, date)
);
CREATE INDEX IF NOT EXISTS idx_comm_instr_date ON commodity_prices(instrument, date DESC);

CREATE TABLE IF NOT EXISTS commodity_price_stats (
    instrument   TEXT PRIMARY KEY,
    point_count  INTEGER NOT NULL DEFAULT 0,
    first_date   TEXT,
    last_date    TEXT,
    last_value   REAL,
    last_fetched TEXT
);

INSERT OR IGNORE INTO commodity_series (instrument, name, fred_series_id, unit, category) VALUES
    ('WTI',    'Crude Oil WTI (Cushing)',        'DCOILWTICO',       'USD/barrel',  'energy'),
    ('BRENT',  'Crude Oil Brent (Europe)',       'DCOILBRENTEU',     'USD/barrel',  'energy'),
    ('GOLD',   'Gold, LBMA PM fix (London)',     'GOLDPMGBD228NLBM', 'USD/troy oz', 'metal'),
    ('NATGAS', 'Natural Gas, Henry Hub spot',    'DHHNGSP',          'USD/MMBtu',   'energy');

-- ---------------------------------------------------------------------------
-- Macro  (FRED)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS macro_series_catalog (
    series_id           TEXT PRIMARY KEY,
    title               TEXT,
    units               TEXT,
    units_short         TEXT,
    frequency           TEXT,
    seasonal_adjustment TEXT,
    observation_start   TEXT,
    observation_end     TEXT,
    fred_last_updated   TEXT,
    popularity          INTEGER,
    category            TEXT NOT NULL,         -- inflation/rates/growth/labor/risk/money-fx
    short_label         TEXT,                  -- for the Macro card title
    typical_lag_days    INTEGER NOT NULL DEFAULT 14,  -- release delay estimate
    tracked             INTEGER NOT NULL DEFAULT 1,
    notes               TEXT,
    last_fetched_at     TEXT
);

CREATE TABLE IF NOT EXISTS macro_observations (
    series_id      TEXT NOT NULL,
    date           TEXT NOT NULL,
    value          REAL,                       -- NULL when FRED returns "."
    realtime_start TEXT,
    realtime_end   TEXT,
    fetched_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (series_id, date)
);
CREATE INDEX IF NOT EXISTS idx_obs_series_date ON macro_observations(series_id, date DESC);

CREATE TABLE IF NOT EXISTS macro_obs_stats (
    series_id    TEXT PRIMARY KEY,
    point_count  INTEGER NOT NULL DEFAULT 0,
    first_date   TEXT,
    last_date    TEXT,
    last_value   REAL,
    last_fetched TEXT
);

INSERT OR IGNORE INTO macro_series_catalog
    (series_id, category, short_label, frequency, typical_lag_days) VALUES
    ('CPIAUCSL',     'inflation', 'CPI (all items, SA)',        'Monthly',   13),
    ('CPILFESL',     'inflation', 'Core CPI (SA)',              'Monthly',   13),
    ('PCEPI',        'inflation', 'PCE price index',            'Monthly',   28),
    ('PCEPILFE',     'inflation', 'Core PCE price index',       'Monthly',   28),
    ('T10YIE',       'inflation', '10y breakeven inflation',    'Daily',      1),
    ('T5YIFR',       'inflation', '5y5y forward inflation',     'Daily',      1),
    ('FEDFUNDS',     'rates',     'Effective fed funds rate',   'Monthly',    2),
    ('DGS2',         'rates',     '2y Treasury yield',          'Daily',      1),
    ('DGS10',        'rates',     '10y Treasury yield',         'Daily',      1),
    ('DGS30',        'rates',     '30y Treasury yield',         'Daily',      1),
    ('T10Y2Y',       'rates',     '10y minus 2y spread',        'Daily',      1),
    ('T10Y3M',       'rates',     '10y minus 3m spread',        'Daily',      1),
    ('MORTGAGE30US', 'rates',     '30y fixed mortgage rate',    'Weekly',     1),
    ('GDPC1',        'growth',    'Real GDP (chained)',         'Quarterly', 30),
    ('INDPRO',       'growth',    'Industrial production',      'Monthly',   16),
    ('RSAFS',        'growth',    'Retail sales',               'Monthly',   14),
    ('HOUST',        'growth',    'Housing starts',             'Monthly',   17),
    ('UMCSENT',      'growth',    'Consumer sentiment (UMich)', 'Monthly',    0),
    ('PAYEMS',       'labor',     'Nonfarm payrolls',           'Monthly',    7),
    ('UNRATE',       'labor',     'Unemployment rate',          'Monthly',    7),
    ('ICSA',         'labor',     'Initial jobless claims',     'Weekly',     5),
    ('VIXCLS',       'risk',      'CBOE VIX close',             'Daily',      1),
    ('BAMLH0A0HYM2', 'risk',      'US high-yield OAS',          'Daily',      1),
    ('NFCI',         'risk',      'Financial conditions (NFCI)','Weekly',     3),
    ('STLFSI4',      'risk',      'Financial stress index',     'Weekly',     4),
    ('M2SL',         'money-fx',  'M2 money stock',             'Monthly',   25),
    ('WALCL',        'money-fx',  'Fed total assets',           'Weekly',     1),
    ('DTWEXBGS',     'money-fx',  'Broad trade-weighted USD',   'Weekly',     4);

-- ---------------------------------------------------------------------------
-- Classification  (populated by a later "Sync memberships" action)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS membership_groups (
    group_key          TEXT PRIMARY KEY,       -- SP500 / NDX / DJIA / XLK / SMH ...
    group_type         TEXT NOT NULL,          -- index / sector_etf / theme_etf
    name               TEXT NOT NULL,
    sponsor            TEXT,
    gics_sector        TEXT,
    source_url         TEXT,
    member_count       INTEGER,
    last_source_as_of  TEXT,
    last_synced_at     TEXT
);

CREATE TABLE IF NOT EXISTS symbol_memberships (
    symbol       TEXT NOT NULL,
    group_key    TEXT NOT NULL,
    weight       REAL,
    source       TEXT NOT NULL,
    source_as_of TEXT,
    active       INTEGER NOT NULL DEFAULT 1,
    first_seen   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_seen    TEXT,
    PRIMARY KEY (symbol, group_key)
);
CREATE INDEX IF NOT EXISTS idx_mem_group  ON symbol_memberships(group_key, active);
CREATE INDEX IF NOT EXISTS idx_mem_symbol ON symbol_memberships(symbol, active);

INSERT OR IGNORE INTO membership_groups (group_key, group_type, name, sponsor, gics_sector) VALUES
    ('SP500', 'index', 'S&P 500',        'S&P DJI', NULL),
    ('NDX',   'index', 'Nasdaq-100',     'Nasdaq',  NULL),
    ('DJIA',  'index', 'Dow Jones Industrial Average', 'S&P DJI', NULL),
    ('XLB',   'sector_etf', 'Materials Select Sector SPDR',              'SSGA', 'Materials'),
    ('XLC',   'sector_etf', 'Communication Services Select Sector SPDR', 'SSGA', 'Communication Services'),
    ('XLE',   'sector_etf', 'Energy Select Sector SPDR',                 'SSGA', 'Energy'),
    ('XLF',   'sector_etf', 'Financial Select Sector SPDR',              'SSGA', 'Financials'),
    ('XLI',   'sector_etf', 'Industrial Select Sector SPDR',             'SSGA', 'Industrials'),
    ('XLK',   'sector_etf', 'Technology Select Sector SPDR',             'SSGA', 'Information Technology'),
    ('XLP',   'sector_etf', 'Consumer Staples Select Sector SPDR',       'SSGA', 'Consumer Staples'),
    ('XLRE',  'sector_etf', 'Real Estate Select Sector SPDR',            'SSGA', 'Real Estate'),
    ('XLU',   'sector_etf', 'Utilities Select Sector SPDR',              'SSGA', 'Utilities'),
    ('XLV',   'sector_etf', 'Health Care Select Sector SPDR',            'SSGA', 'Health Care'),
    ('XLY',   'sector_etf', 'Consumer Discretionary Select Sector SPDR', 'SSGA', 'Consumer Discretionary'),
    ('SMH',   'theme_etf', 'VanEck Semiconductor ETF', 'VanEck',  NULL),
    ('IGV',   'theme_etf', 'iShares Expanded Tech-Software ETF', 'iShares', NULL),
    ('SOXX',  'theme_etf', 'iShares Semiconductor ETF', 'iShares', NULL);

-- ---------------------------------------------------------------------------
-- Options  (fixed research set; snapshots populated later)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS options_research_set (
    underlying TEXT PRIMARY KEY,
    bucket     TEXT NOT NULL                   -- index_etf / sector_spdr / mag7 / software_semis
);
INSERT OR IGNORE INTO options_research_set (underlying, bucket) VALUES
    ('SPY','index_etf'),('QQQ','index_etf'),('DIA','index_etf'),
    ('XLB','sector_spdr'),('XLC','sector_spdr'),('XLE','sector_spdr'),('XLF','sector_spdr'),
    ('XLI','sector_spdr'),('XLK','sector_spdr'),('XLP','sector_spdr'),('XLRE','sector_spdr'),
    ('XLU','sector_spdr'),('XLV','sector_spdr'),('XLY','sector_spdr'),
    ('AAPL','mag7'),('MSFT','mag7'),('GOOGL','mag7'),('AMZN','mag7'),
    ('NVDA','mag7'),('META','mag7'),('TSLA','mag7'),
    ('IGV','software_semis'),('SMH','software_semis'),('SOXX','software_semis');

CREATE TABLE IF NOT EXISTS option_contracts (
    contract_symbol    TEXT PRIMARY KEY,       -- OCC symbol
    underlying          TEXT NOT NULL,
    expiration         TEXT NOT NULL,
    strike             REAL NOT NULL,
    type               TEXT NOT NULL,          -- call / put
    style              TEXT,
    size               INTEGER,
    status             TEXT NOT NULL DEFAULT 'active',
    open_interest      INTEGER,
    open_interest_date TEXT,
    close_price        REAL,
    close_price_date   TEXT,
    first_seen_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_synced_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_optc_underlying_exp ON option_contracts(underlying, expiration);

CREATE TABLE IF NOT EXISTS option_chain_snapshots (
    underlying       TEXT NOT NULL,
    snapshot_date    TEXT NOT NULL,
    contract_symbol  TEXT NOT NULL,
    expiration       TEXT NOT NULL,
    strike           REAL NOT NULL,
    type             TEXT NOT NULL,
    bid              REAL,
    ask              REAL,
    last             REAL,
    mid              REAL,
    volume           INTEGER,
    open_interest    INTEGER,
    iv               REAL,
    delta            REAL,
    gamma            REAL,
    theta            REAL,
    vega             REAL,
    rho              REAL,
    underlying_price REAL,
    feed             TEXT NOT NULL DEFAULT 'indicative',
    fetched_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (underlying, snapshot_date, contract_symbol)
);
CREATE INDEX IF NOT EXISTS idx_snap_underlying_date ON option_chain_snapshots(underlying, snapshot_date);

CREATE TABLE IF NOT EXISTS option_snapshot_stats (
    underlying      TEXT PRIMARY KEY,
    contract_count  INTEGER NOT NULL DEFAULT 0,
    last_snapshot   TEXT,
    snapshot_rows   INTEGER NOT NULL DEFAULT 0,
    last_fetched    TEXT
);

-- ---------------------------------------------------------------------------
-- AI regime (Macro page)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ai_regime_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    trading_date        TEXT NOT NULL,
    model               TEXT NOT NULL,
    prompt_version      INTEGER NOT NULL DEFAULT 1,
    score               REAL,                  -- 0..100 (gauge)
    confidence          REAL,                  -- 0..100
    on_votes            INTEGER NOT NULL DEFAULT 0,
    off_votes           INTEGER NOT NULL DEFAULT 0,
    neutral_votes       INTEGER NOT NULL DEFAULT 0,
    summary             TEXT,
    naive_score         REAL,
    input_snapshot_json TEXT,
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    cost_estimate_usd   REAL,
    status              TEXT NOT NULL DEFAULT 'ok',
    error               TEXT
);
CREATE INDEX IF NOT EXISTS idx_ai_regime_date ON ai_regime_runs(trading_date DESC);

CREATE TABLE IF NOT EXISTS ai_regime_votes (
    run_id     INTEGER NOT NULL,
    persona    TEXT NOT NULL,
    vote       TEXT NOT NULL,                  -- ON / OFF / NEUTRAL
    conviction REAL,
    rationale  TEXT,
    PRIMARY KEY (run_id, persona)
);

-- ---------------------------------------------------------------------------
-- Operational: fetch runs
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS fetch_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    kind              TEXT NOT NULL,           -- asset_catalog / asset_prices / crypto_bars / commodity_prices / macro / memberships / option_contracts / option_snapshots
    mode              TEXT NOT NULL DEFAULT 'incremental',
    scope             TEXT NOT NULL DEFAULT 'all',
    scope_arg         TEXT,
    status            TEXT NOT NULL DEFAULT 'running',  -- running / succeeded / failed / cancelled
    planned_targets   INTEGER NOT NULL DEFAULT 0,
    completed_targets INTEGER NOT NULL DEFAULT 0,
    failed_targets    INTEGER NOT NULL DEFAULT 0,
    rows_written      INTEGER NOT NULL DEFAULT 0,
    requests_made     INTEGER NOT NULL DEFAULT 0,
    current_target    TEXT,
    started_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    finished_at       TEXT,
    error_summary     TEXT
);
CREATE INDEX IF NOT EXISTS idx_fetch_runs_started ON fetch_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS fetch_run_items (
    run_id         INTEGER NOT NULL,
    target         TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',  -- pending / ok / skipped / error
    rows_written   INTEGER NOT NULL DEFAULT 0,
    requests_made  INTEGER NOT NULL DEFAULT 0,
    coverage_start TEXT,
    coverage_end   TEXT,
    duration_ms    INTEGER,
    error          TEXT,
    PRIMARY KEY (run_id, target)
);
