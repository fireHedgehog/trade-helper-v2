# Architecture

## Repo layout

```
backend/app/
  main.py                     FastAPI app + lifespan (run_migrations, start_worker)
  core/config.py              pydantic-settings Settings (env / backend/.env)
  db/
    connection.py             get_connection() / db_dependency() — WAL, FK on, busy_timeout 5s
    migrator.py               forward-only NNNN_*.sql runner, records schema_migrations
  secrets/store.py            keyring wrapper (get/set/delete_secret)
  providers/
    base.py                   ProviderSpec / FieldSpec / register()
    {alpaca,fred,openai_provider}.py   provider registrations (fields, verify fn)
    loader.py                 imports every provider module so register() runs
    secret_resolver.py        resolve_provider_secrets(key) -> {field: value}
    clients/{alpaca_client,fred_client,http}.py   paced HTTP + backoff
  pacing.py                   HostLimiter / get_limiter(host, min_interval)
  features/<name>/            one folder per feature (see below)
frontend/src/
  app/{router,AppShell,theme}.tsx
  shared/{api/client.ts, components/}
  features/<name>/            page.tsx + api.ts + types.ts + components/
schema/migrations/            NNNN_*.sql  (0001–0012)
database/                     runtime SQLite file only (git-ignored)
docs/design-v2/               this set (the as-built reference; superseded whole, not archived)
```

## Backend feature module pattern

Each `backend/app/features/<name>/` has, as needed:

- `router.py` — `APIRouter(prefix="/api/<name>")`, thin; delegates to a service.
- `service.py` — orchestration (load → compute → persist → shape response).
- `repository.py` — all SQL for that feature's tables. No business logic.
- `schemas.py` — pydantic request/response models.
- extra pure-compute modules (`composite.py`, `ranking.py`, `engine.py`, …).

Registered in `main.py`: `credentials`, `data_management` (`/api/data`),
`macro` (`/api/macro`), `multisectional` (`/api/multisectional`), `signals`
(`/api/signals`).

## Database

- **Single SQLite file**, `isolation_level=None` (explicit `BEGIN`/`COMMIT`), `check_same_thread=False`, `PRAGMA journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout=5000` (a worker thread writes while HTTP reads).
- **Migrations** (`db/migrator.py`) run in `main.py`'s lifespan before the app serves. Each `NNNN_*.sql` script + its `schema_migrations` insert commit together. Never edit an applied migration — add a new one.
- **Frontend API** (`shared/api/client.ts`): a `fetch` wrapper, `BASE_URL` `/api`, throws `ApiError(status, detail)`.

## Fetch worker, runs, pacing (`features/data_management/`)

- **`worker.py`** — one `asyncio.Queue`, one consumer task, started in the lifespan. `submit(kind, mode, scope, scope_arg) -> (run_id, deduped)`: de-dupes by kind (a second submit while one is queued/running returns the existing `run_id`). On startup `_reconcile_orphaned_runs()` marks any still-`queued`/`running` `fetch_runs` row `failed` ("interrupted by a server restart"). `VALID_KINDS = {asset_catalog, asset_prices, crypto_bars, commodity_prices, macro, memberships, option_snapshots, signal_universe}`.
- **`runs.py`** — `fetch_runs` / `fetch_run_items` bookkeeping + an in-process cancel-flag set. Handlers call `set_planned` → `start_target` / `finish_target` per symbol/series (per-target commit, so a crash or cancel loses at most one target), and `raise_if_cancelled` between targets. `GET /api/data/runs/{id}` polls the counters row for the progress bar.
- **`pacing.py`** — `HostLimiter` serialises requests per host to a minimum interval (Alpaca 0.40 s ≈ 150/min, FRED 0.70 s, issuer sites 2.0 s). `clients/http.py` adds 429/5xx exponential backoff.

## Config (`core/config.py`, all overridable via env / `backend/.env`)

`database_path`, `schema_dir`, `cors_origins`, provider base URLs,
`history_start_date = "2016-01-01"`, `alpaca_price_feed = "sip"`,
`alpaca_sip_end_lag_days = 1`, `alpaca_min_interval_seconds = 0.40`,
`fred_min_interval_seconds = 0.70`, `fred_revision_lookback_days = 90`,
`fetch_timeout_seconds = 30`, `fetch_max_retries = 4`.
