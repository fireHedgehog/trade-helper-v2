-- 0002_add_openai_credential.sql
-- Add the OpenAI provider row. Used by the Macro page's AI risk-on/off
-- estimate. Same rule as the other providers: the raw key is never stored
-- here, only configuration + verification metadata.

INSERT OR IGNORE INTO credentials (provider_key, credential_name, environment_variable)
VALUES ('openai', 'trade-helper/openai', 'OPENAI_API_KEY');
