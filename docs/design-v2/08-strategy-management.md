# Strategy presets and assignment

The application assigns one long preset per asset. A separate fixed short
benchmark always runs alongside it. Multiple strategy families and multiple
assignments per asset are [parked](11-strategy-design-draft.md).

## Registry

`signal_strategies` stores named parameter snapshots: `id`, `key`, `name`,
`params_json`, `is_default`, `note` and timestamps. The default is
`trend-long-v2`: 20-bar entry, 55-bar exit, ATR20, initial 3×ATR stop, no
Chandelier, next-open fills, 5 bps and 0.05×ATR per-side costs.

Legacy 20/20 and 100/20 presets remain available for deliberate long comparison.
They are not the default or automatic bond exceptions. Presets are immutable
through the UI; the page offers assignment, not parameter editing.

`assets.strategy_id` and `crypto_assets.strategy_id` select the long preset.
A NULL or absent assignment resolves to the current registry default, including
newly fetched catalog names. Catalog refreshes preserve existing assignments.
Resolution includes stored inactive assets when their price history is evaluated.
`signal_config` is a standalone fallback API; normal board runs use the registry.

The fixed short benchmark uses entry20, exit20, ATR20, initial2×ATR and
Chandelier3×ATR. Its parameters and execution are independent of the long
assignment. A long parameter change cannot rewrite short fills.

## Page and API

The Strategies page lists presets, highlights parameter differences, shows
assigned symbols and offers an Apply-to symbol selection. Assignment changes
take effect on the next Trend or portfolio run; they do not alter already saved
history. Each saved symbol result records the exact parameters and strategy id.

API routes under `/api/signals`:

- `GET /strategies` and `GET /strategies/{id}` list presets and assignments.
- `POST /strategies/{id}/assign` accepts `{symbols:[…]}`.
- `GET /strategies/resolve/{symbol}` resolves the long preset.
- `POST /preview {symbol, params}` runs a stateless Timing preview.

Timing edits only its current long preview. It has no Save-parameters action.
Both directions still run and remain separately inspectable. Sizing uses assigned
long presets from the database, not unsaved Timing edits.
