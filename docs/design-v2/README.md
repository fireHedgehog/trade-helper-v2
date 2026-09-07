# docs/design-v2 — the app as built

Current behavior, data contracts and operating assumptions for trade-helper-v2.

Read in order:

| # | File | Covers |
| --- | --- | --- |
| 00 | `00-overview.md` | Purpose, stack, the eight pages and operating workflow |
| 01 | `01-architecture.md` | Repo layout, feature-module pattern, DB / migrations / connection, the fetch worker + runs + pacing, config |
| 02 | `02-data-model.md` | Every table, grouped by instrument / concern family, with the key invariants |
| 03 | `03-data-and-fetch.md` | Providers, each fetch kind, universe selection, the Data Management page |
| 04 | `04-macro.md` | The naive composite + the AI regime gauge + the Macro page |
| 05 | `05-multisectional.md` | The cross-sectional ranking + leadership overlay + caching + the page |
| 06 | `06-trend-and-timing.md` | The Donchian signal engine, the single-symbol Timing page, the whole-universe Trend board |
| 07 | `07-credentials-and-shell.md` | The provider registry + secret handling, the app shell / routing / theme |
| 08 | `08-strategy-management.md` | Strategy registry, symbol assignment, preview, and the Strategies page |
| 09 | `09-position-sizing.md` | Fresh allocations, historical funded portfolios, costs and direction contributions |
| 10 | `10-paper-trading.md` | Current boundary between research simulation and broker execution |

The [multiple-strategy discussion](11-strategy-design-draft.md) is **parked** and
describes proposed behaviour only. Files 00–10 describe current application state.
The permanent research reference is
[Naive Donchian V2](../strategy-experiments/naive-donchian-v2-result.md), including
the archive commit. Experiment folders are removed from the current checkout.
Do not retrieve archived files unless the user explicitly requests it.
Update design documents in place; new research uses temporary folders until review.
