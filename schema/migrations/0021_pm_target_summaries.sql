BEGIN;
-- Board reads need state/actions, not decompression of every historical chart.
ALTER TABLE pm_targets ADD COLUMN summary_json TEXT;
