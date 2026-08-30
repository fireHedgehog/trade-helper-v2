-- 0005_ai_regime.sql
-- Finalise the AI risk-on/off regime tables. `ai_regime_runs` was created by
-- 0003 with a first-draft column set; this migration adds the calibration +
-- budget columns, makes trading_date unique (one cached run per date),
-- replaces the draft `ai_regime_votes` with the fuller `ai_regime_messages`
-- audit trail. See docs/draft-design/10-macro-page-and-ai-regime.md §4, §6.

ALTER TABLE ai_regime_runs ADD COLUMN budget            TEXT NOT NULL DEFAULT 'medium';
ALTER TABLE ai_regime_runs ADD COLUMN score_raw         REAL;
ALTER TABLE ai_regime_runs ADD COLUMN confidence_raw    REAL;
ALTER TABLE ai_regime_runs ADD COLUMN calibration_notes TEXT;

-- table is empty at this point, so a unique index is safe to add.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_regime_trading_date ON ai_regime_runs(trading_date);

DROP TABLE IF EXISTS ai_regime_votes;

CREATE TABLE IF NOT EXISTS ai_regime_messages (
    run_id            INTEGER NOT NULL,
    seq               INTEGER NOT NULL,
    role              TEXT NOT NULL,        -- persona / rebuttal / reconciler
    persona           TEXT,                 -- risk_on / … / NULL for reconciler
    round             INTEGER NOT NULL,     -- 1 / 2 / 3
    prompt            TEXT NOT NULL,
    completion        TEXT NOT NULL,
    parsed_json       TEXT,
    vote              TEXT,                 -- ON / OFF / NEUTRAL for persona rows
    conviction        REAL,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    PRIMARY KEY (run_id, seq)
);
