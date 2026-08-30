-- 0006_macro_add_oil.sql
-- Crude oil is a genuine macro-financial variable (energy is a large CPI
-- component; oil shocks drive inflation expectations and are recessionary),
-- so it belongs on the Macro page under Inflation — not the equity/crypto
-- price action that was (wrongly) leaking into the AI regime read.
--
-- Add WTI + Brent as tracked macro series (FRED ids, same as the others) and
-- backfill their history from the already-fetched commodity_prices so they
-- show up immediately. commodity_prices / commodity_series stay as the
-- Data-management "Commodities" family — this is an intentional, small dup:
-- the same numbers serve macro-regime input here and tradable-price reference
-- there.

INSERT OR IGNORE INTO macro_series_catalog
    (series_id, category, short_label, frequency, typical_lag_days) VALUES
    ('DCOILWTICO',   'inflation', 'Crude Oil WTI',   'Daily', 1),
    ('DCOILBRENTEU', 'inflation', 'Crude Oil Brent', 'Daily', 1);

INSERT OR IGNORE INTO macro_observations (series_id, date, value, fetched_at)
SELECT 'DCOILWTICO', date, price, fetched_at
  FROM commodity_prices WHERE instrument = 'WTI' AND price IS NOT NULL;

INSERT OR IGNORE INTO macro_observations (series_id, date, value, fetched_at)
SELECT 'DCOILBRENTEU', date, price, fetched_at
  FROM commodity_prices WHERE instrument = 'BRENT' AND price IS NOT NULL;

INSERT OR REPLACE INTO macro_obs_stats (series_id, point_count, first_date, last_date, last_value, last_fetched)
SELECT 'DCOILWTICO', COUNT(*), MIN(date), MAX(date),
       (SELECT value FROM macro_observations WHERE series_id = 'DCOILWTICO' ORDER BY date DESC LIMIT 1),
       strftime('%Y-%m-%dT%H:%M:%fZ','now')
  FROM macro_observations WHERE series_id = 'DCOILWTICO';

INSERT OR REPLACE INTO macro_obs_stats (series_id, point_count, first_date, last_date, last_value, last_fetched)
SELECT 'DCOILBRENTEU', COUNT(*), MIN(date), MAX(date),
       (SELECT value FROM macro_observations WHERE series_id = 'DCOILBRENTEU' ORDER BY date DESC LIMIT 1),
       strftime('%Y-%m-%dT%H:%M:%fZ','now')
  FROM macro_observations WHERE series_id = 'DCOILBRENTEU';
