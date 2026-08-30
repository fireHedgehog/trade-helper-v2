-- 0007_ai_regime_weights.sql
-- The AI regime run now aggregates the four neutral domain analysts with
-- research-grounded, regime-adjusted weights (inflation weight scales up with
-- distance of core PCE from the 2% target) and blends a deterministic
-- code-computed score with the reconciler's holistic score.
-- Store the weights actually used and both component scores for audit.
-- See docs/draft-design/10-macro-page-and-ai-regime.md §4.1a.

ALTER TABLE ai_regime_runs ADD COLUMN weights_json         TEXT;
ALTER TABLE ai_regime_runs ADD COLUMN code_weighted_score  REAL;
ALTER TABLE ai_regime_runs ADD COLUMN reconciler_score     REAL;
