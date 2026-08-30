-- Disposable research queries for the current Donchian universe.
-- Run against database/trade_helper.sqlite3. These statements are read-only.

-- Latest successful universe run and its exact stored parameters.
SELECT run_id, started_at, finished_at, n_symbols, n_events,
       engine_version, params_json
  FROM signal_runs
 WHERE scope = 'universe' AND status = 'succeeded'
 ORDER BY run_id DESC
 LIMIT 1;

-- Coverage caveat: a later single-symbol Timing run deletes that symbol's
-- cached universe row, so this count can be lower than signal_runs.n_symbols.
WITH latest AS (
    SELECT run_id
      FROM signal_runs
     WHERE scope = 'universe' AND status = 'succeeded'
     ORDER BY run_id DESC
     LIMIT 1
)
SELECT r.n_symbols AS universe_run_symbols,
       COUNT(s.symbol) AS cached_rows_still_owned_by_run
  FROM latest l
  JOIN signal_runs r ON r.run_id = l.run_id
  LEFT JOIN signal_symbol_stats s ON s.run_id = l.run_id;

-- Current active equity/ETF universe with bar coverage.
SELECT a.symbol, a.name, a.exchange, a.sector,
       COUNT(p.date) AS bars,
       MIN(p.date) AS first_date,
       MAX(p.date) AS last_date
  FROM assets a
  LEFT JOIN price_bars p ON p.symbol = a.symbol
 WHERE a.active = 1
 GROUP BY a.symbol
 ORDER BY a.symbol;

-- Cached two-sided strategy versus same-symbol buy-and-hold, latest universe
-- run only. The Python report recomputes this independently because cached rows
-- can be superseded by later Timing runs.
WITH latest AS (
    SELECT run_id
      FROM signal_runs
     WHERE scope = 'universe' AND status = 'succeeded'
     ORDER BY run_id DESC
     LIMIT 1
)
SELECT s.symbol,
       json_extract(s.metrics_json, '$.strategy.cagr') AS strategy_cagr,
       json_extract(s.metrics_json, '$.buy_hold.cagr') AS buy_hold_cagr,
       json_extract(s.metrics_json, '$.strategy.cagr')
         - json_extract(s.metrics_json, '$.buy_hold.cagr') AS cagr_delta,
       json_extract(s.metrics_json, '$.strategy.max_drawdown') AS strategy_max_dd,
       json_extract(s.metrics_json, '$.buy_hold.max_drawdown') AS buy_hold_max_dd,
       json_extract(s.metrics_json, '$.trade_stats.exposure') AS exposure,
       json_extract(s.metrics_json, '$.trade_stats.trades') AS closed_trades
  FROM signal_symbol_stats s
  JOIN latest l ON l.run_id = s.run_id
 ORDER BY cagr_delta DESC;
