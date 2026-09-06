# Strategy registry, assignment, and per-symbol universe execution

## Registry and resolution

- **`signal_strategies`** — `(id, key, name, params_json, is_default, note,
  created_at, updated_at)`. One immutable parameter snapshot per row. Seeded:
  - `naive-donchian-v1` (`is_default = 1`) — the frozen benchmark: `entry_len`
    20, `exit_len` 20, Chandelier 3×ATR, initial 2×ATR stop, `allow_short`
    `false`.
  - `naive-donchian-v1-slow-entry` — identical except `entry_len` 100.
  - "Edit" is not offered: a new parameter set is a new row (V3, V4…).
- **`assets.strategy_id` / `crypto_assets.strategy_id`** — explicit id on every
  active row (default → V1, the `ETF_BONDS` set → V2). Dormant rows stay NULL
  and fall back to the default at resolve time. **`signal_symbol_stats` has a
  nullable `strategy_id`** stamped by each universe run; its existing
  `params_json` column already holds the exact per-symbol params used.
- **`signal_config` and `GET`/`PUT /api/signals/config`** provide a standalone
  fallback preset. The board resolves parameters from the strategy registry.
- **Resolver**: `run_universe` builds `symbol -> params` once from the registry
  and runs each symbol with its own parameters. **Direction is forced two-sided
  regardless of the strategy** — the board computes long *and* short for research coverage. `allow_short` in a strategy's
  `params_json` is documentation, not a filter.
- **API** (all under `/api/signals`): `GET /strategies`,
  `GET /strategies/{id}` (with assigned symbols), `POST /strategies/{id}/assign`
  `{symbols:[…]}`, `GET /strategies/resolve/{symbol}`, and
  `POST /preview {symbol, params}` — a stateless single-symbol run that persists
  **nothing**.
- **Timing page**: no "Save parameters". The form pre-fills from the symbol's
  resolved strategy; **Run** calls `/preview` and only updates what is on screen.
  The Trend board still shows the symbol's last *stored* (universe-run) signals
  until the next Trend run.
- **Strategies page** (`/strategies`): lists each strategy, its param table
  (rows differing from the default highlighted), its `note`, its assigned-symbol
  list, and an "Apply to…" symbol multi-select that writes `strategy_id`.
- **Trend page**: the Watchlist header expands a static **advisory allocation
  note** (inverse-vol sizing, ~12% vol target, ~10% position cap, sleeve
  budgets 50/20/15/5/10, long-only default with bonds + BTC as the short
  exceptions, weekly re-check). No portfolio engine — reference text only, from
  the frozen research (`docs/strategy-experiments/naive-donchian-v1-result.md`).

There are no separate version, assignment-priority, shadow-run or approval-lifecycle tables.
Each saved symbol result contains the strategy id and exact parameter snapshot.
