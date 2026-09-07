# Trade Helper

A local-first trading research app with market data, macro context, momentum
rankings, trend signals and portfolio sizing. It does not place broker orders.
Start with the [current application design](docs/design-v2/README.md).

The permanent strategy research reference is
[Naive Donchian V2](docs/strategy-experiments/naive-donchian-v2-result.md).
Its archive commit preserves the full experiments; the temp folders are absent
from the current checkout. Agents must not retrieve or restore those archived
files unless the user explicitly requests it. Multi-strategy development is parked.

## Repository layout

```
docs/        Current design in design-v2/; concise results in strategy-experiments/.
schema/      Ordered SQL migrations. The single source of truth for the DB.
database/    Local SQLite file (git-ignored).
backend/     FastAPI + SQLite. One folder per feature under app/features/.
frontend/    React + TypeScript + Vite. One folder per feature under src/features/.
```

Frontend and backend are separate apps with their own tooling and their own
per-feature module folders — nothing is dumped in one big file. Schema lives
outside both so a data migration is just a new `schema/migrations/NNNN_*.sql`.

## Status

| Surface | State |
| --- | --- |
| Credentials / Data management | Provider keys, paced fetching, adjustment repair and one-click data + computation workflow |
| Macro / Multisectional | Weighted macro baseline, manual optional AI and cross-sectional momentum context |
| Trend / Timing / Strategies | Assigned long preset plus independent fixed short benchmark; saved signals and scratch previews |
| Sizing | Current allocations and historical long, short or combined portfolios, with per-asset contributions |

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
verification metadata. See [credentials and shell](docs/design-v2/07-credentials-and-shell.md).

## Local data

Schema migrations apply on backend startup. Market history can be fetched again;
back up the SQLite database to retain assignments, saved results and accumulated
option snapshots. Macro AI is a separate manual action and is never triggered by
the one-click data refresh or portfolio simulation.
