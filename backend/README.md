# Backend

FastAPI + SQLite. Numeric work (ATR, Donchian, z-scores, FRED series) lives
here. Local-first, single operator, no ops.

## Layout

```
app/
  main.py                 app wiring: CORS, migrations on startup, routers
  core/config.py          settings (env / backend/.env), path resolution
  db/
    connection.py         sqlite3 connection + transaction helpers
    migrator.py           forward-only runner for ../schema/migrations/*.sql
  secrets/store.py        OS-keychain read/write + env-var read fallback
  providers/
    base.py               ProviderSpec / FieldSpec registry
    fred.py, alpaca.py    per-provider fields + verify() call
    loader.py             imports provider modules so they self-register
  pacing.py               per-host request pacing (1 in-flight, min interval)
  providers/clients/      paced HTTP clients: alpaca_client, fred_client, http
  features/
    credentials/          one feature = router + service + repository + schemas
    data_management/      fetch worker + runs + per-family handlers + browse
      worker.py           single asyncio queue/consumer (started in lifespan)
      runs.py             fetch_runs / fetch_run_items + cancellation flags
      catalog|prices|crypto|macro|commodities.py   per-family fetch handlers
      repository.py       server-paginated browse queries
      router.py           /api/data/* endpoints
tests/
```

Each feature is its own folder (`features/<name>/`) with its own router,
service, repository, and schemas — nothing is dumped in one module. New
pages (macro, multisectional, trend, timing, data-management) get a sibling
folder here.

## Run

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt          # or: pip install -e ".[dev]"
uvicorn app.main:app --reload            # http://localhost:8000
```

Migrations in `../schema/migrations/` run automatically on startup. The
SQLite file is created at `../database/trade_helper.sqlite3` (override with
`DATABASE_PATH`).

## Test

```bash
cd backend
source .venv/bin/activate
pytest
```

Tests use a throwaway database and an in-memory stand-in for the OS keychain;
no real network calls, no real secrets.

## Credentials API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/credentials` | List each provider's config + verification status (never a secret). |
| `GET` | `/api/credentials/{provider_key}` | One provider's status. |
| `PUT` | `/api/credentials/{provider_key}` | Set/rotate secret field(s). Write-only: body `{ "values": { "<field>": "<secret>" } }`, returns metadata only. |
| `DELETE` | `/api/credentials/{provider_key}` | Remove stored secret(s), mark not configured. |
| `POST` | `/api/credentials/{provider_key}/verify` | One minimal real call to the provider; records `healthy` / `invalid`. |

`provider_key` is `fred`, `alpaca`, or `openai`. FRED and OpenAI each need one
field (`api_key`); Alpaca needs two (`api_key_id`, `api_secret_key`) because
Alpaca issues credentials as an identify-plus-authenticate pair. OpenAI is
used by the Macro page's AI regime estimate; its verify call lists models
(read-only, no generation).

## Data Management API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/data/runs` | start a fetch — body `{kind, mode?, scope?, scope_arg?}`; `kind` ∈ `asset_catalog` \| `asset_prices` \| `crypto_bars` \| `commodity_prices` \| `macro` |
| `GET` | `/api/data/runs/{id}` | one run's counters — poll this for the progress bar |
| `GET` | `/api/data/runs?limit=` | recent runs (history) |
| `GET` | `/api/data/runs/{id}/items` | per-target results |
| `POST` | `/api/data/runs/{id}/cancel` | request cancellation (checked between targets) |
| `GET` | `/api/data/assets`, `/assets/{s}`, `/assets/{s}/bars` | paginated browse |
| `GET` | `/api/data/macro`, `/macro/{id}/observations` | macro catalog + observations |
| `GET` | `/api/data/crypto`, `/crypto/bars?symbol=`, `/commodities`, `/commodities/{i}/prices` | |

One background asyncio worker runs jobs one at a time. Requests are paced
(`app/pacing.py`): ≥400 ms between Alpaca calls, ≥700 ms between FRED calls,
`Retry-After` / exponential backoff on 429/5xx, commit after every target.
Incremental is the default; `mode=full` re-pulls from `history_start_date`.

## Secret handling (not negotiable — see docs/07-credentials-page.md)

The raw secret is never written to SQLite, never returned by an API, never
logged. `PUT` accepts it once, writes it to the OS keychain, and forgets it.
Reads resolve keychain first, then a per-field environment variable
(`FRED_API_KEY`, `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`,
`OPENAI_API_KEY`).
