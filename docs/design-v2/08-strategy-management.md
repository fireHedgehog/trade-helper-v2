# Strategy registry, assignment, and per-symbol universe execution

> **Status: a deliberately MINIMAL version is BUILT (migration `0014`). The rest
> of this document is the fuller design that was intentionally not built.**

## AS-BUILT (minimal registry — migration 0014)

What exists now:

- **`signal_strategies`** — `(id, key, name, params_json, is_default, note,
  created_at, updated_at)`. One immutable parameter snapshot per row. Seeded:
  - `naive-donchian-v1` (`is_default = 1`) — the frozen benchmark: `entry_len`
    20, `exit_len` 20, Chandelier 3×ATR, initial 2×ATR stop, `allow_short`
    `false`.
  - `naive-donchian-v1-slow-entry` — identical except `entry_len` 100.
  - "Edit" is not offered: a new parameter set is a new row (V3, V4…).
- **`assets.strategy_id` / `crypto_assets.strategy_id`** — explicit id on every
  active row (default → V1, the `ETF_BONDS` set → V2). Dormant rows stay NULL
  and fall back to the default at resolve time. **`signal_symbol_stats` gains a
  nullable `strategy_id`** stamped by each universe run; its existing
  `params_json` column already holds the exact per-symbol params used.
- **`signal_config` and `GET`/`PUT /api/signals/config` are untouched** — kept
  as a vestigial fallback; nothing reads `signal_config` for the board any more.
- **Resolver**: `run_universe` builds `symbol -> params` once from the registry
  and runs each symbol with its own parameters. **Direction is forced two-sided
  regardless of the strategy** — the board always computes long *and* short so a
  future short-capable strategy needs no re-fetch. `allow_short` in a strategy's
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
  the frozen research (`docs/temp/NAIVE_DONCHIAN_V1_RESEARCH_HANDOFF.md`).

Deliberately NOT built (the rest of this doc): a separate immutable
version table, a dedicated `signal_strategy_assignments` table with priority /
effective-dating / rationale, `signal_run_resolutions` provenance rows, group /
cluster selectors, shadow-default comparison runs, and lifecycle
(research/approved/retired) state. The signal tables are fully wiped and
rewritten every universe run, so there is no historical provenance to protect —
`signal_symbol_stats.params_json` + `strategy_id` is enough.

---

## Fuller design (NOT built)

> Everything below is the original elaborate plan, kept for reference. The
> as-built section above is what actually exists.

## Objective

Add a versioned strategy-management layer above the existing deterministic
signal engine so that:

1. the Trend run always computes the entire current active universe;
2. an operator may explicitly assign approved strategy versions to selected
   symbols;
3. unassigned symbols always resolve to the plain Turtle V1 default;
4. future group or cluster rules can be added without replacing manual symbol
   assignments;
5. every stored signal remains attributable to the exact strategy version and
   assignment rule that produced it; and
6. the full universe remains a permanent control and discovery population even
   when the operator only trades a small watchlist.

The assignment layer changes **which strategy a target runs**, never **whether
the target runs**.

## Non-goals for the first implementation

- Automatic optimisation or automatic promotion of the best historical
  per-symbol parameters.
- A cluster model that changes live assignments without operator approval.
- Portfolio construction, capital allocation, volatility targeting, or order
  execution.
- Borrow availability, borrow fees, crypto funding, futures rolls, tax, or cash
  yield modelling.
- Deleting the existing V1 Trend board or reducing the universe run to the
  watchlist.
- Treating the disposable files under `backend/temp` or `docs/temp` as
  production state.

## As-built baseline at the time of this design

The current application has one active `signal_config` row. A whole-universe
run loads the union of active assets, active crypto assets, and the hard-coded
Trend watchlist, then applies the same Donchian parameter snapshot to every
target. The universe runner forces both long and short directions on.

The disposable multi-horizon experiment independently runs fixed 20/10,
40/20, 55/20, and 100/50 variants plus an equal-horizon ensemble across the
current universe. It is a research harness only. It does not register
strategies, modify `signal_config`, assign strategies to symbols, or change the
Trend board.

## Core invariants

### Full-universe invariant

The target list is resolved before strategy assignments are considered:

```text
targets = active equities/ETFs ∪ active crypto ∪ fixed Trend watchlist
```

Every valid target receives one primary strategy resolution. Assignment lookup
must not filter this list. A successful universe run must report:

```text
resolved_primary_targets == valid_universe_targets
```

An explicit assignment may be absent, disabled, or archived. In every such
case, the target resolves to the approved default V1 strategy rather than being
skipped.

### One primary resolution per target

For a given universe run and symbol, exactly one strategy version is primary.
Research shadows may add comparison computations, but they cannot replace or
ambiguate the primary board state.

### Immutable historical provenance

Every result must retain:

- strategy identity;
- immutable strategy-version identity;
- exact parameter JSON;
- engine version;
- assignment source (`manual_symbol`, future `group`, or `default`);
- source assignment identifier when applicable; and
- primary versus shadow role.

Editing a strategy creates a new version. It never changes the meaning of an
already stored run.

### Manual intent wins

The initial resolver precedence is:

```text
manual symbol assignment > group assignment (future) > default Turtle V1
```

There may be at most one active assignment at the winning precedence for a
symbol. An ambiguity is a configuration error; it must not be resolved by row
order.

## Domain model

### Strategy identity

A strategy is the stable operator-facing concept, for example:

- `turtle-v1`
- `turtle-medium`
- `turtle-classic-slow`
- `turtle-slow`
- `turtle-horizon-ensemble`

The identity owns a name and description. It does not own mutable live
parameters.

### Strategy version

A version is an immutable executable specification:

- model family;
- entry and exit horizons;
- stop and trail architecture;
- allowed directions or direction-combination rule;
- fill and cost assumptions;
- ensemble component versions and weights, if any;
- compatible signal-engine version;
- lifecycle state (`research`, `approved`, `retired`); and
- creation timestamp and operator note.

Only an `approved` version may be the default or receive a production
assignment. Research versions remain runnable in the research harness.

The initial candidate registry may contain the current V1 as the only approved
version. Multi-horizon candidates stay in `research` until evidence is reviewed
and the operator explicitly approves them.

### Assignment

An assignment connects one target selector to one approved strategy version.
The first implementation needs only `manual_symbol`. The schema should reserve
the selector type so a later `group` or `cluster` rule does not require a
redesign.

Assignment fields include:

- selector type;
- selector key (`QQQ`, `BTC/USD`, or a future group key);
- strategy-version ID;
- active flag;
- priority within its selector type;
- operator rationale;
- created and updated timestamps; and
- optional effective start/end timestamps for future scheduling.

Removing or deactivating an assignment immediately restores default resolution
on the next run. Historical runs retain the old provenance.

### Default

There is exactly one approved default strategy version. The first migration
must point it to the as-built Donchian 20/10 V1 parameter snapshot.

The system must reject:

- zero defaults;
- multiple defaults;
- a research or retired default; and
- deletion of a version referenced by a default, assignment, or historical
  result.

Archiving replaces destructive deletion.

## Proposed persistence model

Names are provisional until implementation review.

### `signal_strategies`

| Column | Purpose |
| --- | --- |
| `id` | Stable strategy identity. |
| `key` | Unique machine key. |
| `name` | Operator-facing name. |
| `description` | Plain-language intent. |
| `archived` | Hides future use without deleting history. |
| timestamps | Audit metadata. |

### `signal_strategy_versions`

| Column | Purpose |
| --- | --- |
| `id` | Immutable executable version. |
| `strategy_id` | Parent identity. |
| `version` | Monotonic integer unique within a strategy. |
| `model` | Engine model family. |
| `params_json` | Validated exact parameter snapshot. |
| `components_json` | Ensemble component IDs/weights; NULL for one engine model. |
| `engine_version` | Compatibility and provenance. |
| `status` | `research`, `approved`, or `retired`. |
| `is_default` | Exactly one approved row across the table. |
| `note` | Operator rationale for the version. |
| `created_at` | Immutable creation time. |

The database should enforce version uniqueness. Default uniqueness may require
a partial unique index plus application validation in SQLite.

### `signal_strategy_assignments`

| Column | Purpose |
| --- | --- |
| `id` | Assignment identity. |
| `selector_type` | Initially `manual_symbol`; reserves `group`/`cluster`. |
| `selector_key` | Normalised symbol or future group key. |
| `strategy_version_id` | Approved version to run. |
| `priority` | Explicit ordering within a selector type. |
| `active` | Participates in resolution. |
| `rationale` | Required human explanation for manual overrides. |
| timestamps | Audit metadata. |

An active uniqueness constraint should prevent two active manual assignments
for the same normalised symbol.

### `signal_run_resolutions`

One immutable row per computed `(run_id, symbol, role)`:

| Column | Purpose |
| --- | --- |
| `run_id`, `symbol`, `role` | Composite key; role is `primary` or `shadow_default`. |
| `strategy_version_id` | Resolved immutable version. |
| `assignment_source` | `manual_symbol`, future `group`, or `default`. |
| `assignment_id` | NULL for default; source assignment otherwise. |
| `params_json` | Defensive execution snapshot. |
| `engine_version` | Exact engine used. |

`signal_events`, `signal_symbol_stats`, and any chart payload must be
unambiguously connected to the resolution row. The implementation must decide
whether to add `role`/version foreign keys directly or introduce result-set
IDs. It must not rely on whatever assignment is active when a historical row is
read.

## Resolution algorithm

For every target in a universe-run snapshot:

1. normalise the symbol using the existing signal data rules;
2. look up one active manual symbol assignment;
3. if absent, evaluate future group rules in deterministic priority order;
4. if absent, select the one approved default version;
5. validate model/engine compatibility;
6. persist the resolution snapshot before or atomically with its results; and
7. compute the symbol even when the resolution source is `default`.

Resolution should be a pure function over a preloaded registry and assignment
snapshot. The universe loop must not execute one database query per symbol.

## Universe-run execution

The runner remains a full-universe job:

```text
load target snapshot
  -> load registry/assignment snapshot
  -> resolve one primary version for every valid target
  -> group targets by executable version
  -> compute and persist primary results
  -> optionally compute approved shadow comparisons
  -> publish one complete board snapshot
```

Grouping targets by version avoids repeated parameter parsing and makes progress
reporting clear. Progress remains target-based so the existing fetch panel can
continue to show `completed / planned` symbols.

The final run summary should include counts such as:

```json
{
  "targets": 678,
  "primary_resolved": 678,
  "assignment_counts": {
    "manual_symbol": 27,
    "group": 0,
    "default": 651
  },
  "strategy_counts": {
    "turtle-v1@1": 651,
    "turtle-horizon-ensemble@1": 27
  }
}
```

The values above illustrate the contract; they are not current production
assignments.

## Primary and shadow results

The board displays one primary result per symbol. An assigned symbol may also
run the default V1 as a `shadow_default` comparison so an operator can measure
whether the manual override improved on leaving that same symbol at V1.

Shadow rules for the first implementation:

- disabled by default for the full universe;
- optionally enabled for manually assigned symbols only;
- never used to set the board state;
- stored separately from primary results;
- excluded from the universe target count; and
- visible only in strategy comparison/detail views.

The large unassigned default population remains the cross-sectional control.
Same-symbol shadows provide the counterfactual control for assigned targets.

## Strategy Manager page

Add a dedicated route, provisionally `/strategies`.

### Strategy registry table

Columns:

- strategy name and version;
- lifecycle status;
- model and concise horizon/exit summary;
- direction policy;
- default indicator;
- assigned-symbol count;
- last research run date; and
- actions appropriate to status.

An approved or referenced version is immutable. “Edit” creates the next
research version with copied parameters.

### Strategy detail

Show:

- plain-language rule description;
- exact parameters;
- version history;
- research evidence and its date/universe;
- assigned symbols;
- operator rationale;
- promotion/retirement controls; and
- default-V1 comparison where available.

The page must label descriptive or in-sample evidence as such. It must not call
the highest historical result “recommended”.

### Assignment editor

The operator can:

- search the asset catalog;
- select multiple symbols;
- assign one approved version;
- add a required rationale;
- review conflicts before saving;
- deactivate an assignment; and
- see that removal falls back to V1.

The initial UI should favour an explicit table over drag-and-drop or an
automatic optimiser.

## Trend and Timing page integration

### Trend board

The board remains full-universe and keeps the watchlist plus long/short/flat
sections. Add:

- resolved strategy name/version;
- assignment source (`Manual`, future `Group`, or `Default`);
- filters for strategy and assignment source; and
- run-summary counts by strategy/source.

An ensemble may expose fractional net position, for example `+0.50`, in
addition to the high-level long/short/flat state. The UI must distinguish
fractional ensemble conviction from a position-sizing recommendation.

Unassigned rows still show V1 breakouts, preserving placeholders, discovery,
and the control population.

### Timing page

Timing should default to the symbol's resolved primary strategy and show why it
was selected. A comparison mode may load the default V1 shadow. Editing a
global parameter form must not silently mutate an approved version or change
unrelated assignments.

The existing single active `signal_config` editor must be replaced or narrowed
during migration so it cannot bypass registry/version invariants.

## Proposed API surface

Names are provisional:

```text
GET    /api/signals/strategies
POST   /api/signals/strategies
POST   /api/signals/strategies/{strategy_id}/versions
POST   /api/signals/strategy-versions/{version_id}/approve
POST   /api/signals/strategy-versions/{version_id}/retire
PUT    /api/signals/default-strategy

GET    /api/signals/assignments
POST   /api/signals/assignments
PATCH  /api/signals/assignments/{assignment_id}
DELETE /api/signals/assignments/{assignment_id}

GET    /api/signals/resolution/{symbol}
GET    /api/signals/runs/{run_id}/resolutions
```

Writes validate version status, symbol normalisation, uniqueness, and default
fallback in one transaction.

## Research-to-production lifecycle

1. Declare a small economically meaningful variant before running it.
2. Run the disposable or future persisted research experiment across the full
   control universe and the intended watchlist.
3. Inspect multiple time windows, direction ablations, costs, and stability.
4. Keep the variant in `research` while evidence is incomplete.
5. Require an explicit operator action and rationale to promote a version.
6. Assign the approved version to selected symbols.
7. Keep default V1 shadows for assigned symbols when comparison is useful.
8. Review live and new-period evidence without rewriting historical versions.

No automatic “best variant” promotion is permitted.

## Migration and rollout plan

### Phase 1 — registry foundation

- Add strategy/version/default tables.
- Backfill current `signal_config` as approved `turtle-v1@1` and the sole
  default.
- Add read APIs and resolver unit tests.
- Preserve identical universe results when no assignments exist.

### Phase 2 — manual assignments

- Add the assignment table and transactional write APIs.
- Resolve manual symbol assignments with default fallback.
- Persist per-run resolution provenance.
- Add strategy/source columns and filters to the board.

### Phase 3 — Strategy Manager UI

- Add registry, version, detail, and assignment views.
- Require rationale and conflict review.
- Display explicit `UNASSIGNED -> DEFAULT V1` behaviour.

### Phase 4 — shadows and comparison

- Compute optional V1 shadows for assigned symbols.
- Add same-symbol primary-versus-default comparisons.
- Keep shadows outside the primary board state.

### Phase 5 — group rules and clustering (future)

- Add deterministic group selectors only after manual assignment is stable.
- Keep manual symbol assignments at higher precedence.
- Require operator approval before a cluster result changes an assignment.

## Acceptance criteria

- With zero manual assignments, a universe run produces the same primary
  results as the current V1 runner within deterministic equality.
- With assignments, the number of primary resolved targets still equals the
  valid full-universe target count.
- Every unassigned symbol resolves to the one default V1 version.
- A manual assignment affects only its selected symbols.
- Deactivating an assignment restores V1 on the next run.
- Historical runs remain explainable after new versions and assignments are
  created.
- The board identifies strategy version and assignment source for every row.
- Ambiguous assignments, invalid defaults, and incompatible engine versions
  fail before partial board publication.
- Research and shadow results cannot silently become primary.
- All user-facing and repository content added by the implementation remains in
  English.

## Required test coverage

- Resolver precedence and symbol normalisation.
- Exactly-one-default enforcement.
- Assignment uniqueness and transactional conflict handling.
- Full-universe target-count invariant.
- Identical V1 fallback output before and after registry introduction.
- Strategy-version immutability and historical provenance.
- Primary versus shadow isolation.
- Board filtering without dropping default rows.
- API status/error cases and frontend assignment flows.
- Migration from the existing active `signal_config`.

## Open decisions before implementation

1. Whether the first persisted ensemble is executed inside the signal engine or
   by an orchestration layer over component engine results.
2. Whether result tables receive direct strategy-version/role columns or a
   separate result-set identity.
3. Whether approved versions may be retired while assigned, or assignments must
   be moved first.
4. Whether V1 shadow computation is always on for manual assignments or is a
   per-assignment option.
5. How current per-symbol wipe semantics are replaced by immutable run-owned
   snapshots without making Timing reads expensive.
6. Which research evidence is required before a version can be approved.
7. How fractional ensemble state is represented on the existing board without
   implying portfolio sizing.

These decisions must be resolved before migrations or formal implementation
begin.
