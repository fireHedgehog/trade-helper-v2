-- 0004_drop_fred_gold.sql
-- FRED no longer serves a working daily gold series: GOLDPMGBD228NLBM returns
-- "series does not exist" from the API (LBMA/ICE licensing pulled the data).
-- Gold is covered by the GLD ETF in price_bars instead (same call as silver /
-- SLV). Remove the dead commodity_series row and any partial data.

DELETE FROM commodity_prices        WHERE instrument = 'GOLD';
DELETE FROM commodity_price_stats   WHERE instrument = 'GOLD';
DELETE FROM commodity_series        WHERE instrument = 'GOLD';
