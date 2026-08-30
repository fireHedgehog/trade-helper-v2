-- Trim the options research set to a small core (user: "少一点，不要太多").
-- Daily IV-surface-grid snapshots are stored for these underlyings only:
-- SPY/QQQ + the 7 MAG7 names + SMH. The 11 sector SPDRs, DIA, and IGX/SOXX
-- are dropped for now (thinner option liquidity, lower signal value) — add
-- back by re-inserting rows here if wanted later.

DELETE FROM options_research_set
 WHERE underlying NOT IN (
    'SPY', 'QQQ', 'SMH',
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA'
 );
