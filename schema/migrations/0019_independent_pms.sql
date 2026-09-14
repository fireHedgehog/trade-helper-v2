-- Additive PM storage. Existing signal tables/assignments remain unchanged.
BEGIN;

CREATE TABLE pm_definitions (
    pm_key TEXT NOT NULL,
    version TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    PRIMARY KEY (pm_key, version)
);

CREATE TABLE pm_assignments (
    symbol TEXT NOT NULL,
    pm_key TEXT NOT NULL,
    version TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
    PRIMARY KEY(symbol, pm_key),
    FOREIGN KEY(pm_key, version) REFERENCES pm_definitions(pm_key, version)
);

CREATE TABLE pm_runs (
    id INTEGER PRIMARY KEY,
    fetch_run_id INTEGER REFERENCES fetch_runs(id),
    input_hash TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('running','succeeded','partial','failed','cancelled')),
    created_at TEXT NOT NULL,
    finished_at TEXT,
    error TEXT
);

CREATE TABLE pm_targets (
    run_id INTEGER NOT NULL REFERENCES pm_runs(id),
    symbol TEXT NOT NULL,
    pm_key TEXT NOT NULL,
    version TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('queued','ok','insufficient_history','invalid_data','failed','cancelled')),
    error TEXT,
    PRIMARY KEY(run_id,symbol,pm_key,version),
    FOREIGN KEY(pm_key,version) REFERENCES pm_definitions(pm_key,version)
);

CREATE TABLE pm_results (
    run_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    pm_key TEXT NOT NULL,
    version TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY(run_id,symbol,pm_key,version),
    FOREIGN KEY(run_id,symbol,pm_key,version) REFERENCES pm_targets(run_id,symbol,pm_key,version)
);
CREATE INDEX idx_pm_targets_symbol_run ON pm_targets(symbol,run_id DESC);
CREATE INDEX idx_pm_runs_fetch ON pm_runs(fetch_run_id);
