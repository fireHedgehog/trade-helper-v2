# docs/design-v2 — the app as built

Accurate, current description of trade-helper-v2. This is a **snapshot**: the
design may be torn up and rewritten wholesale later (hence the `-v2` — expect
a `-v3`). When that happens, this folder gets deleted, not archived.

Read in order:

| # | File | Covers |
| --- | --- | --- |
| 00 | `00-overview.md` | Purpose, stack, the eight pages, cross-cutting principles, status |
| 01 | `01-architecture.md` | Repo layout, feature-module pattern, DB / migrations / connection, the fetch worker + runs + pacing, config |
| 02 | `02-data-model.md` | Every table, grouped by instrument / concern family, with the key invariants |
| 03 | `03-data-and-fetch.md` | Providers, each fetch kind, universe selection, the Data Management page |
| 04 | `04-macro.md` | The naive composite + the AI regime gauge + the Macro page |
| 05 | `05-multisectional.md` | The cross-sectional ranking + leadership overlay + caching + the page |
| 06 | `06-trend-and-timing.md` | The Donchian signal engine, the single-symbol Timing page, the whole-universe Trend board |
| 07 | `07-credentials-and-shell.md` | The provider registry + secret handling, the app shell / routing / theme |
| 08 | `08-strategy-management.md` | The (minimal) strategy registry + per-symbol assignment, the `/preview` route, the Strategies page, the Trend allocation note. The doc also carries the fuller unbuilt design. |
| 09 | `09-position-sizing.md` | The Sizing sandbox — the `sector` field added to the board response, the client-side sizing waterfall (inverse-vol → caps → vol-target → macro), the deployed-by-sleeve crowding model, verdicts, and what it deliberately does not do. |

Everything here is **naive-v1 / descriptive / not statistically validated** by
design (see 00). Keep these docs updated as the app changes; when a section
goes stale, fix it or delete it — don't let stale design docs accumulate.
