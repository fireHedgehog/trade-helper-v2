-- 0001_init.sql
-- Initial schema. For now this is only the credentials table: provider
-- configuration and verification metadata. The raw secret value is NEVER
-- stored here (see docs/07-credentials-page.md) — it lives in the OS keychain
-- or an injected environment variable and is resolved at runtime.

CREATE TABLE IF NOT EXISTS credentials (
    provider_key             TEXT PRIMARY KEY,
    -- Base lookup name used against the OS keychain. Individual fields are
    -- stored under "<credential_name>/<field_name>".
    credential_name          TEXT NOT NULL,
    -- Human-readable reference to the environment-variable fallback family
    -- (e.g. "FRED_API_KEY", "ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY").
    -- The provider registry in code is the authority on exact names.
    environment_variable     TEXT NOT NULL,
    -- 1 once every required field has been submitted at least once.
    configured               INTEGER NOT NULL DEFAULT 0 CHECK (configured IN (0, 1)),
    verification_status       TEXT NOT NULL DEFAULT 'unverified'
                                 CHECK (verification_status IN ('unverified', 'healthy', 'invalid')),
    last_verified_at         TEXT,
    -- Short status line from the last verify attempt (e.g. "HTTP 200",
    -- "HTTP 401"). Never the response body.
    last_verification_detail TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Seed the two providers this app needs. INSERT OR IGNORE keeps this safe to
-- re-run and safe alongside a database that already has these rows.
INSERT OR IGNORE INTO credentials (provider_key, credential_name, environment_variable)
VALUES
    ('fred',   'trade-helper/fred',   'FRED_API_KEY'),
    ('alpaca', 'trade-helper/alpaca', 'ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY');
