-- Keep original chart inputs with the run, never read today's revised prices as yesterday's saved chart.
BEGIN;
CREATE TABLE pm_inputs (
    run_id INTEGER NOT NULL REFERENCES pm_runs(id),
    symbol TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    bars BLOB NOT NULL,
    PRIMARY KEY(run_id,symbol)
);
