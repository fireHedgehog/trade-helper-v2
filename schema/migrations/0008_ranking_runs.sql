-- 0008_ranking_runs.sql
-- Cache the cross-sectional ranking. It is a ~2 s in-memory computation over
-- every active symbol's price history — recomputing on every page visit is
-- wasteful. Instead: "Recompute" stores a snapshot here; the page reads the
-- latest snapshot and shows how stale it is vs the newest price data.

CREATE TABLE IF NOT EXISTS ranking_runs (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    computed_at                 TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    latest_price_date           TEXT,   -- the price date the ranking was computed against
    member_count                INTEGER,
    eligible_count              INTEGER,
    leadership_formation_count  INTEGER,
    payload_json                TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ranking_runs_computed ON ranking_runs(computed_at DESC);
