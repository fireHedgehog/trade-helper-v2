# Trade Helper

A local-first, single-operator trading **research** app. Six honest surfaces,
each doing one job, all naive-v1 — real, known, never claimed to be
statistically validated. See [`docs/`](docs/) for the full design package
(read [`docs/00-overview.md`](docs/00-overview.md) first).

## Repository layout

```
docs/        Design package — the specification. Start here.
schema/      Ordered SQL migrations. The single source of truth for the DB.
database/    Runtime home of the SQLite file (git-ignored, disposable).
backend/     FastAPI + SQLite. One folder per feature under app/features/.
frontend/    React + TypeScript + Vite. One folder per feature under src/features/.
```

Frontend and backend are separate apps with their own tooling and their own
per-feature module folders — nothing is dumped in one big file. Schema lives
outside both so a data migration is just a new `schema/migrations/NNNN_*.sql`.

## Status

| Surface | State |
| --- | --- |
| Credentials | **Implemented** — store/rotate FRED + Alpaca keys, per-key Test button |
| Macro, Multisectional, Trend, Timing, Data management | Placeholder pages, feature folders scaffolded |

## Run it

Two terminals.

```bash
# 1. Backend  →  http://localhost:8000
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# 2. Frontend  →  http://localhost:5173  (proxies /api to the backend)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173, go to **Credentials**, paste a key, click
**Test**.

- FRED needs one value (**API Key**).
- Alpaca needs two (**API Key ID** + **API Secret Key**) — Alpaca issues
  credentials as an identify-plus-authenticate pair, like a username and
  password. FRED is a single key. The page says so on each card.

See [`backend/README.md`](backend/README.md) and
[`frontend/README.md`](frontend/README.md) for details.

## Credentials: the one rule that is not simplified away

The raw secret value is **never** stored in the database, never returned by
an API, never logged, never bundled into the frontend. It is written once to
the OS keychain and resolved from there (or a per-field environment variable)
at runtime. The `credentials` table holds only provider configuration and
verification metadata. See [`docs/07-credentials-page.md`](docs/07-credentials-page.md).

## Reset the database

```bash
rm database/trade_helper.sqlite3    # migrations rebuild it on next backend start
```
