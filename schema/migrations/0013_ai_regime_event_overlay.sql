-- Store the bounded, fast-decaying macro catalyst adjustment separately from
-- the structural weighted-vote and reconciler scores.

ALTER TABLE ai_regime_runs ADD COLUMN event_overlay REAL NOT NULL DEFAULT 0;
