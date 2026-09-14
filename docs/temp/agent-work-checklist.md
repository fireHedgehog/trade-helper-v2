# Agent work checklist — independent PMs to portfolio assessment

**Status: ACTIVE — user authorised progressive execution on 2026-09-14,
including tools/apps needed for this project and routine implementation choices.**

Purpose: make small, reviewable advances without rebuilding existing features,
overlapping another agent's edits, or repeatedly reading completed research.
The [research roadmap](strategy-comparison-experiment-design.md) owns the rationale
and proposed trading rules. This file owns task order, current execution state
and concise completion evidence. Update both in place; do not create daily logs
or competing checklists.

## 1. Resume here

| Field | Current value |
| --- | --- |
| Authorised execution scope | Progress through eligible checklist tasks; user said to start and granted full permission. Preserve data, avoid unrelated actions, record evidence and handoffs. |
| Current batch | Research review and next PM integration slice |
| Active task / owner | T25 candidate integration review / Codex coordinator |
| Blocker / decision needed now | None; use roadmap proposals as research defaults, record unresolved provenance without inventing it |
| Next eligible task | T25: prepare a non-voting SMA200 research comparator; retain D default and keep rejected pullback/short candidates in research. T29 historical context is independently eligible. |
| Completed new tasks | 27 of 50: T01-T24, T26-T28 |

The 50 tasks are work slices, not equal effort or a promise of 2% completion per
task. A working increment matters more than a percentage. If an item grows into
several unrelated changes, split it into suffixed IDs before starting and update
its dependants. Do not expand one task into the entire roadmap.

### Agent startup: minimal reading

1. Read this resume table, active claims and the selected task row. Check current
   user instructions and repository instructions; those take precedence.
2. Inspect `git status --short` and relevant changes. Preserve existing edits.
   Read only the roadmap section, source files and completion evidence needed
   for this task and its direct dependencies.
3. Confirm the task is in the authorised batch, prerequisites are complete, and
   its write scope is unclaimed. The coordinator records the claim before a
   worker starts. If a prerequisite is missing, advance a different authorised
   eligible task rather than duplicating or silently skipping it.
4. Implement the smallest complete slice. Run the focused checks in its acceptance
   criteria and required repository checks. Broaden testing only for affected
   integration boundaries, failures or changes since the last validation.
5. Record completion evidence and release the claim. Update the resume table.
   Continue to the next eligible task within the authorised batch without asking
   for permission after every checkbox. Stop at a real unresolved decision,
   exhausted authorised scope, or dependency that cannot be advanced.

Do not reread the entire repository, rerun completed experiments, or restore
archived research merely to regain context. Reopen completed work only when a
changed dependency, relevant code/input difference, regression or user instruction
invalidates its evidence. Record that specific reason. Historical validation
results are evidence from their recorded revision, not fresh tests of later code.
For an interrupted run, retain its job/session ID, input hash, output path and
exact next action in the claim. Check whether it is still running or already
finished before submitting another job. Resume or inspect its outputs where
possible; do not spend another full run merely because the conversation changed.

## 2. Existing work — reuse, do not rebuild

These are implementation observations, not a claim that a fresh full test suite
was run while writing this checklist.

| Done | Capability and boundary | Starting evidence |
| --- | --- | --- |
| [x] | Trend and Timing model dropdowns already exist, currently with Donchian only. Extend them when real PM options exist. | [TrendPage](../../frontend/src/features/trend/TrendPage.tsx), [TimingPage](../../frontend/src/features/timing/TimingPage.tsx) |
| [x] | Assigned long Donchian and fixed short benchmark run independently, including positions and pending actions. Arbitrary multiple PM families are not yet supported. | [engine](../../backend/app/features/signals/engine.py), [service](../../backend/app/features/signals/service.py) |
| [x] | Timing long/short controls filter displayed results. Parameter runs are unsaved previews. | [TimingPage](../../frontend/src/features/timing/TimingPage.tsx), `service.preview` |
| [x] | Trend has a collapsed signal accordion with long entry, long exit, short entry and short exit tables in one row. | [TrendPage](../../frontend/src/features/trend/TrendPage.tsx); commit `abf3c46` |
| [x] | Strategy preset registry and one-long-preset-per-asset assignment exist. Reuse them when designing multiple assignments. | [repository](../../backend/app/features/signals/repository.py), [migration 0014](../../schema/migrations/0014_signal_strategies.sql) |
| [x] | Funded long, short and fixed combined accounts, equal/volatility sizing, costs and trade contributions exist. | [portfolio](../../backend/app/features/sizing/portfolio.py), [sizing design](../design-v2/09-position-sizing.md) |
| [x] | Multisectional context, background worker and one-click refresh exist. Context does not yet aggregate PM decisions. | [ranking](../../backend/app/features/multisectional/ranking.py), [worker](../../backend/app/features/data_management/worker.py), [refresh](../../frontend/src/features/data-management/refresh.ts) |
| [x] | Playwright generated folders/output and logs have ignore rules. | [.gitignore](../../.gitignore); commit `abf3c46` |

Existing tests to extend where relevant: [signal tests](../../backend/tests/test_signals.py),
[sizing tests](../../backend/tests/test_sizing.py),
[frontend trading tests](../../frontend/tests/trading.test.cjs),
[refresh tests](../../frontend/tests/refresh.test.cjs).

## 3. Coordination and completion protocol

Default to **one active writer in this shared checkout**. Multiple agents are
optional; sequential work is the simplest way to avoid conflicts. A Markdown
claim is not an atomic filesystem lock and cannot make concurrent self-claiming
safe. One coordinator assigns tasks and is the only writer of this checklist.
Workers return evidence to the coordinator instead of racing to edit its state.

If parallel workers are useful, the coordinator first assigns disjoint scopes
and isolated worktrees/checkouts. Frontend consumers wait for the backend contract
to be frozen. Schema, shared types, dependency files and common fixtures each
have one owner. Two experiments never write the same output path or share a
writable SQLite database. Give each run an ID and frozen input reference; integrate
through one coordinator and validate the integration once. Never reset, clean,
stash, overwrite or delete another agent's work to obtain a clean checkout.

| Task | Owner/session | Base revision + worktree | Exact write scope | State | Next action / handoff |
| --- | --- | --- | --- | --- | --- |
| T01-T15 | Codex coordinator, 2026-09-14 | `abf3c46`, main shared checkout | PM implementation and research foundation | done | Evidence below; do not rerun completed reference or live PM jobs |
| T26-T28 | Codex coordinator, 2026-09-14 | `abf3c46`, main shared checkout | `backend/app/features/pms/assessment*`, PM read API, `backend/tests/test_assessments.py`, Timing assessment UI | done | T26-T28 complete: contract, read API, Timing panel; five assessment tests and 11 PM tests passed; frontend build passed; live A long/short evidence reviewed |
| T20-T24 | Codex coordinator, 2026-09-15 | `f1bffc4`, main shared checkout | `backend/temp/pm-research/`, `docs/temp/` | done | All controls, long diagnostics and short comparisons finished. Read `research-report.md`; manifests `controls-v1`, `long-diagnostics-v1`, `short-comparison-v1` all succeeded. No research process remains to wait on or restart. |
| T16-T19 | Codex coordinator, 2026-09-14 | `abf3c46`, main shared checkout | `backend/temp/pm-research/`, `docs/temp/` | done | T16 complete. T17 v2 PID 10632 finished successfully; output `results/20260914T032109Z/sma-comparison-v2/run.json`. T19 PID 10848 completed, `pullback-v1/run.json` succeeded. Logs `output/logs/sma-research-v2.*.log` and `pullback-research.*.log`. Check manifests/processes before resubmitting. Source copies frozen per run. |

Permitted states: **proposed, ready, active, blocked, done, deferred**. All unchecked
tasks below start proposed. An authorised task becomes ready when prerequisites
are done; a blocked/deferred task needs a specific reason. Do not call deferred
work complete. Do not take over an active claim just because it is old: the
coordinator must confirm handoff or abandonment first.

Completion requires all of the following:

- The row's acceptance condition is met, including relevant failure behaviour.
- Existing behaviour is preserved or its change is explicit and in scope.
- Focused validation passed; integration checks cover changed boundaries.
- The result is reviewable and reproducible from recorded files/settings.
- The checkbox, evidence row and resume state agree; no pending required work
  is concealed under a checked box.

Use this compact evidence format, one row per completed task. A commit is
optional: uncommitted work can be complete if exact files and validation are
recorded. When available record the commit; for research record the run ID,
input hash, configuration and result path. A bare "done" is insufficient.

| Task | Result / files | Revision or run + inputs | Validation and date | Remaining limitation |
| --- | --- | --- | --- | --- |
| — | No new tasks completed | — | — | — |

Keep unresolved decisions here, only when they become relevant. The coordinator
first checks existing authorisation and frozen rules rather than asking again.

| Decision | Blocks | Concrete proposal and alternatives | Resolution |
| --- | --- | --- | --- |
| — | — | No new decision required to review this checklist | — |

### Latest integration evidence

- T10: Frozen per-asset chart inputs and PM results persist independently; changing current prices leaves the saved chart intact. Existing signal endpoints still work.
- T11: Existing worker supports PM runs, deduplicates submissions, reports per-target progress and partial failures, and preserves completed PMs on cancellation. Targeted worker tests passed.
- T12: Explicit run/PM/version read APIs and a summary board exist. A missing PM produces an explicit unavailable response, never another PM's result.
- Validation: all backend regression tests passed on 2026-09-14 (including 10 PM tests); all 20 frontend tests passed; production frontend build passed. Existing bundle-size and testclient deprecation warnings remain.
- Live review: job 115 was started through Trend's Run all enabled PMs button. It uses current production prices, independently of research snapshot `20260914T032109Z`. Check `/api/data/runs/115` before starting another.

### Saved-PM UI milestone (T13-T15)

- T13: Timing extends the existing dropdown with saved PM/run/version selection. Frozen charts, stops, positions and ledgers switch without POST requests; URL selection survives refresh. Unsaved parameter preview remains separate.
- T14: Trend extends the existing dropdown with All saved PMs and per-PM views, plus Run all enabled PMs. Four independent signal tables remain collapsed by default and side-by-side when expanded.
- T15: 11 PM tests pass, including the exact held-A / entering-B / B-exits-A-remains / opposing-short lifecycle through save and reload. Browser checked real A long and short holdings independently; screenshots `output/playwright/pm-trend.png` and `pm-timing-short.png`.
- Live completion: worker job 115 / PM run 1, 1,356 targets across 678 assets, zero failed targets, 41,268 trade rows. Completed 2026-09-14T07:57:58Z. No network data requests or broker orders. Existing legacy board/results remain available.
- Regression evidence: backend full suite passed before the final lifecycle test; focused PM suite passed after it. Frontend build passed; existing 20 frontend tests passed. Browser's transient HTTP 500 during dev-server reload resolved after reload; only the pre-existing missing favicon remains.

## 4. Task sequence

Dependencies below are task IDs; "—" means no unfinished task prerequisite, not
permission to start outside the authorised batch. The area is a starting scope,
not an exclusive lock: claims must name actual files before concurrent work.

### Foundation — establish comparable inputs

Roadmap reference: Part I A/F and Part II 2–4. These tasks produce reusable
inputs and explicit rules before any strategy ranking.

| Done | ID | Depends on | Area | Small deliverable and acceptance condition |
| --- | --- | --- | --- | --- |
| [x] | T01 | — | Research specification | Freeze one conventions record: 250-bar warmup, first decision/fill, cash timing, buy-and-hold budget exception and meaning of each stress test. Distinguish the recalled 2× position run from production doubled costs; unresolved provenance is labelled, not invented. |
| [x] | T02 | T01 | `backend/temp` | Create a reproducible read-only research snapshot/export with symbol membership, calendars, cutoff, source and content hash. Reopening it yields the same data despite later live-database changes. |
| [x] | T03 | T02 | Research validation | Produce a complete coverage/data-quality table, including missing/short histories and the documented SPY low. Every frozen asset has a row and each flag has a reason. |
| [x] | T04 | T03 | Research inputs | Resolve flagged material inputs using retained source evidence, or mark affected comparisons provisional. Corrections produce a new snapshot/hash; no silent clipping or live-database overwrite. |
| [x] | T05 | T01 | Research accounting | Hand-reconcile representative entry, adverse gap-stop, scheduled exit, same-day funding and open-mark examples. Expected cash, units, costs and equity are explicit and independently checked. |
| [x] | T06 | T04, T05 | Research reference | Run Donchian long and buy-and-hold on the common snapshot/conventions. Ledgers reconcile to funded equity and coverage. Provisional data can support exploratory results but cannot establish a winner. |

### PM foundation — extend existing behaviour incrementally

Roadmap reference: Part I B. This preparatory infrastructure can follow T01
without waiting for all strategy experiments. Initially adapt existing Donchian
behaviour; adding experimental PMs to production remains a separate decision.

| Done | ID | Depends on | Area | Small deliverable and acceptance condition |
| --- | --- | --- | --- | --- |
| [x] | T07 | T01 | Signal contract | Define a versioned PM result/assignment contract: asset, family, preset/version, run, direction, horizon, status, cutoff, position, actions, stops and ledger references. Distinguish unsaved previews from persisted runs. Freeze it before dependent implementation. |
| [x] | T08 | T07 | Signal adapters | Wrap existing long Donchian and fixed short as two PM identities without changing their financial behaviour. Focused fixtures reproduce current trades, stops and pending actions. |
| [x] | T09 | T07 | Schema/storage | Add non-destructive versioned storage for multiple assignments and asset/PM/run results. Prove on a temporary database that PM B cannot overwrite PM A, including two PMs on the same side; test migration from the existing schema. |
| [x] | T10 | T08, T09 | Persistence | Persist/retrieve both existing PMs through the new contract, with a compatibility path for current pages. Old results remain accessible; a failed new run cannot masquerade as fresh success. |
| [x] | T11 | T10 | Backend orchestration | Extend the existing worker to run all enabled, deduplicated assignments against one input version. Test cancellation, partial failure, progress and coherent run completion; no automatic data fetch or macro AI call. |
| [x] | T12 | T10 | PM read API | Expose saved PM choices and results for an asset/run, with missing/stale/failed states. Fetching a PM is read-only and identifies the exact saved result; no silent fallback to another PM. |
| [x] | T13 | T12 | Timing UI | Extend the existing model selection to inspect saved PM charts, stops, trades and equity. Switching views triggers no simulation, deletes no results and keeps unsaved parameter previews clearly separate. |
| [x] | T14 | T11, T12 | Trend UI | Extend existing model controls and the four-table accordion for PM-labelled signals and selectable views. All enabled PMs still compute regardless of display selection; incomplete coverage is visible. |
| [x] | T15 | T13, T14 | Focused integration | Demonstrate PM A holding while PM B enters, for both same-direction and opposing-direction cases; then exit B and show A unchanged. Verify through save/reload and view switching using deterministic fixtures; validate real existing PMs as well. |

### Strategy breadth — add one independently testable family at a time

Roadmap reference: Part II and Part I F. Research strategies live under
`backend/temp` until deliberately enabled through the PM integration task.

| Done | ID | Depends on | Area | Small deliverable and acceptance condition |
| --- | --- | --- | --- | --- |
| [x] | T16 | T01 | Research signals | Implement fixed SMA200 long trend from Part II. Verify equality behaviour, completed-bar inputs, common start and next-open execution on small fixtures. |
| [x] | T17 | T16, T06 | Research results | Run the SMA candidate on the frozen snapshot at normal/doubled costs; save matched-date standalone and funded comparisons against the references, with complete coverage. |
| [x] | T18 | T01 | Research signals | Implement the specified SMA200/RSI2 pullback. Verify Wilder edge cases, SMA5/regime/time exits, entry-day stop and tenth-held-bar confirmation. |
| [x] | T19 | T18, T06 | Research results | Run pullback at both cost levels on the same snapshot; reconcile its ledgers and report its cash time, turnover and losses against the references. |
| [x] | T20 | T17, T19 | Research controls | Run all predefined M3/P0 stop controls and four neighbouring settings. Save every trial, including failures; do not add a parameter search based on attractive results. |
| [x] | T21 | T20 | Research report | Complete paired/annual/concentration diagnostics and the four tables/three charts specified in Part II. State retain/replace/complement/inconclusive with limitations; no automatic production promotion. |
| [x] | T22 | T01 | Short specification | Freeze one failed-rally short's exact regime, entry, exit, stop, horizon, borrow assumptions and matching-date fixed-short/cash comparisons. Resolve thresholds before execution; a prose strategy name alone is not done. |
| [x] | T23 | T22, T05 | Research signals | Implement that short candidate independently; reconcile rising-price losses, gap-through stops, exits and costs on deterministic fixtures. Never infer a short entry from another PM's long exit. |
| [x] | T24 | T23, T04 | Research results | Compare the short candidate with the fixed short and cash, with borrow stress, coverage and feasibility limitations. Retain the possibility that no short allocation is justified. |
| [ ] | T25 | T15, T21, T24 | PM integration | Record the reviewed candidate selection, then adapt only the deliberately enabled candidates into the PM contract. Match research results on the frozen sample; benchmarks and rejected candidates are not silently promoted or allowed to vote. |

### Assessment — a new function reading independent PM results

Roadmap reference: Part I C. Displaying disagreement is useful before any
aggregation policy starts changing simulated allocations.

| Done | ID | Depends on | Area | Small deliverable and acceptance condition |
| --- | --- | --- | --- | --- |
| [x] | T26 | T15 | Assessment contract | Define fresh entry, active support, opposition, abstention, missing, exit and hard veto; freeze families, horizons, freshness and coverage semantics. Assessment output references PM inputs and never edits them. |
| [x] | T27 | T26 | Assessment engine | Implement descriptive family-level long/short support and recent agreement. Mixed family presets are labelled; flat is not denial; missing required inputs remain unavailable. No combined orders yet. |
| [x] | T28 | T27 | Assessment UI | Show per-asset support, opposition, coverage and reasons beside expandable PM details. Existing chart selection and PM positions remain independent; user can trace every count to a PM. |
| [ ] | T29 | T26, T02 | Historical context | Produce/replay Multisectional context available at each historical decision time, with universe and timestamps. Test against future-data leakage; missing context is explicit. |
| [ ] | T30 | T25, T26 | Policy specification | Freeze a small named policy set: funded split, union, intersection and explicit veto. Define origin PM, simultaneous-entry ties, conflicts, exits and common capital. Resolve choices before changing trades. |
| [ ] | T31 | T30, T05 | Funded assessment | Implement one shared-account ledger for accepted proposals, with cash batching, duplicate exposure, origin-owned exits and independent PM attribution. Opposite hypothetical PM books do not create free capital. |
| [ ] | T32 | T31, T27, T29 | Research comparison | Compare the frozen policies at constant size against component PMs/funded splits under both cost levels. Preserve every result and report whether combining signals actually adds value. |

### Grades — size accepted opportunities without leverage first

Roadmap reference: Part I D. Grade changes, vote filters and leverage must have
separate comparisons so a result can be attributed to the right change.

| Done | ID | Depends on | Area | Small deliverable and acceptance condition |
| --- | --- | --- | --- | --- |
| [ ] | T33 | T32 | Grade specification | Freeze Skip/C/B/A conditions, the direction-specific Multisectional threshold, required inputs, 5% free-cash base proposal and 0/0.5/1/2 multipliers. Record reviewed choices; do not treat grades as probabilities. |
| [ ] | T34 | T33 | Sizing engine | Implement cash-based grade requests using one pre-batch free-cash snapshot, reserving costs/collateral and scaling competing requests proportionally. Verify the $20,000 cash example and order independence. |
| [ ] | T35 | T34 | Portfolio limits | Apply frozen per-position planned-loss and gross symbol/sector/underlying/account limits. Record requested versus permitted size and reasons. A stop loss estimate is not a guaranteed loss cap. |
| [ ] | T36 | T35, T31 | Research comparison | Compare grade sizing against constant-base sizing on the exact same accepted signals and against the production reference. Report by-entry-grade counts, contribution, losses and cash use without changing labels after seeing results. |
| [ ] | T37 | T36, T28 | Sizing UI | Show grade reasons, base cash, requested/permitted allocation, units and constraints. Keep lot multiplier separate from account/position leverage; later grade changes do not automatically resize existing positions. |

### Instruments — one realistic leverage route at a time

Roadmap reference: Part I E. Feasibility/specification may begin earlier, but
leveraged funded results wait for a defined policy and appropriate instrument data.

| Done | ID | Depends on | Area | Small deliverable and acceptance condition |
| --- | --- | --- | --- | --- |
| [ ] | T38 | T01 | Instrument specification | Select one product/venue route for research and freeze signal-to-instrument mapping, stop reference, calendar, financing terms, execution assumptions and data needs. Verify current terms from primary sources; keep unavailable details unresolved. |
| [ ] | T39 | T38 | Instrument data | Acquire/version actual product or contract data and required financing/margin history, with provenance and valid coverage. No invented pre-inception prices or unsupported liquidity claims. |
| [ ] | T40 | T39, T05 | Instrument accounting | Reconcile cash, units/contracts, product or underlying exposure, financing and margin on small examples. Handle the selected route's reset/roll/funding features and avoid double-counting embedded costs. |
| [ ] | T41 | T40 | Stress accounting | Implement the selected route's adverse gaps, unavailable execution, margin changes and applicable forced exits. Specify scenario ordering or conservative bounds where daily bars cannot resolve it. |
| [ ] | T42 | T36, T41 | Exposure experiment | Freeze what 1×/1.5×/2× means, reset rules and failure limits; run matched-history and separately labelled shocks. Report collateral/equity minima, drawdowns, forced exits, costs and gap losses; survival alone is not approval. |
| [ ] | T43 | T42 | Instrument UI | Present requested exposure, instrument, financing assumptions, account gross/net and estimated underlying exposure. Unsupported products receive no executable sizing proposal; grade does not implicitly select leverage. |

### Forward observation and handoff

Roadmap reference: Part I F. Recording frozen signals can start early; evaluation
must not credit a later policy with observations collected before it existed.

| Done | ID | Depends on | Area | Small deliverable and acceptance condition |
| --- | --- | --- | --- | --- |
| [ ] | T44 | T11, T12 | Observation storage | Append dated decisions for explicitly frozen PM versions/input cutoffs. Reruns/revisions do not overwrite what was knowable at the original decision time; no broker orders. |
| [ ] | T45 | T37, T44 | Paper ledger | Connect a reviewed unlevered assessment/grade policy to paper positions and costs; preserve original proposals versus simulated fills and attribution. Attach a leveraged route only after T42/T43 and explicit selection. |
| [ ] | T46 | T45 | Monitoring | Freeze review horizon/coverage requirements and paper loss/exposure limits; show stale inputs, missing observations, rule changes and assumption breaches. Version changes begin a distinct evaluation record. |
| [ ] | T47 | T46 | Forward report | After the predefined observation requirement is actually met, compare grades/policies with baselines and reconcile paper outcomes. Elapsed waiting is not completion; insufficient observations stay pending. |
| [ ] | T48 | T47 | Review decision | Present a concrete keep/revise/retire decision with evidence and material limitations. Record the user's decision; no automatic production activation or forced removal of useful research PMs. |
| [ ] | T49 | T48 | Product integration | Apply only the reviewed selection, document actual versus still-planned capabilities, and verify persistence, view selection, assessment and sizing together. Include a tested way to disable new policies while keeping stored history. |
| [ ] | T50 | T49 | Documentation/handoff | Write the concise permanent result/design updates and remaining-gaps summary. Leave research intact unless archive/deletion is explicitly authorised; commit/push only within current authorisation. |

## 5. Scope boundaries every agent must preserve

- PM independence is an invariant: another PM may enter the same asset, on the
  same or opposite side, while the first holds. Its entry/exit must not overwrite
  the first PM. Each PM's own position rules still apply.
- Assessment is a new consumer of PM results. It may reject a funded proposal;
  that does not erase the originating PM's signal or rewrite its performance.
- Existing dropdowns and long/short filters are reusable UI. Arbitrary PM
  persistence and run-all behaviour need backend work; adding a dropdown option
  alone is not completion.
- Keep production defaults and stored user data intact during research. Test
  migrations on disposable databases first; obtain a recoverable database backup
  before an authorised migration touches the real database.
- Use existing worker, data and accounting infrastructure where appropriate.
  Do not add a new optimiser, data family, AI service, broker order flow or
  unrelated refactor merely because an agent finds it convenient.
- Do not retrieve archived experiment files without explicit user instruction.
  The [V2 result](../strategy-experiments/naive-donchian-v2-result.md) is the retained
  reference. Fresh experiments record their own inputs and evidence.
- Current authorisation governs commits, pushing, force-adding ignored research
  and deletion. A completed task does not itself authorise those actions. Once
  a batch/action is explicitly authorised, do not ask repeatedly for the same
  permission.

## 6. Continue within the existing authorisation

The user authorised progressive execution and routine project decisions. Continue
with the resume table's next eligible task, checking existing process/run manifests
first. No per-checkbox approval is needed. Record a review decision only where the
actual task requires the user's judgment; never claim forward observation is done
before the prescribed time and coverage exist.


### SMA research progress

- T16 complete: completed-close/equality/next-open/common-warmup fixtures pass. Asset-only account slicing separately reconciles a hand-calculated cost-bearing trade. Three focused tests passed.
- T17 first attempt `sma-comparison-v1` failed before writing its first standalone row: duplicate result metadata keyword. Failed manifest/source retained. Fixed and restarted as PID 10632, `sma-comparison-v2`: 8 new SMA funded scenarios, reused 16 funded references, and new matched-date standalone D/B/M accounts. The previously completed funded reference experiments are not rerun.

- T18 complete: independently seeded Wilder RSI2, flat/gain/loss edges; next-open entry; SMA5, regime and tenth-held-close exits; entry-day stop, adverse gap and scheduled-exit precedence. All 14 research tests passed after adding pullback and candidate-run support. T19 running as PID 10848, `pullback-v1`, frozen source retained. Future runs use faster lossless gzip compression; numeric output is unchanged.

### Descriptive assessment contract

- T26 complete: `backend/app/features/pms/assessment-contract.md` freezes required run membership, daily horizon, five asset-bar recency, seven-day/current-input freshness, family disagreement/coverage, benchmark exclusion, and future vote activation. Read-only observation never rewrites PM positions or creates allocations. T27 implementation is independent of the running strategy experiments.

- T19 complete: 8 funded scenarios and 2,712 standalone coverage rows, 672 executable assets plus six insufficient histories, two windows and two costs. Ledgers independently rechecked against contribution sums; no identity error exceeds $0.00001. Primary recent priority pullback CAGR 0.79% normal / -2.91% doubled costs; provisional inputs, high cash exposure, no promotion. See `research-report.md`.
- T27-T28 complete: read-only `/api/pms/assessment/{symbol}` and collapsed Timing assessment panel with family support, recent agreement, coverage and linked per-PM evidence. Five assessment + 11 PM tests passed, frontend build passed, browser reviewed A showing long support while separately preserving its short benchmark position. Screenshot `output/playwright/pm-assessment.png`. Transient new-route 404 during dev reload resolved; final browser assessment loads successfully.

- T17 complete: 8 funded SMA scenarios, 8,136 matched D/B/M standalone coverage rows, unchanged funded references reused. Pair dates/statuses match across all four primary candidates. Primary recent priority SMA CAGR 11.09% normal / 9.81% doubled, drawdown -15.22% / -15.61%; lower return and shallower drawdown than D, provisional. Contribution/equity reconciliation rechecked.
- T20 now running: coordinator PID 21820, six predefined controls only, two at a time, source hashes frozen. All 16 research fixtures passed before control launch.

### Checkpoint validation

- Full backend regression suite passed after adding descriptive assessment. All 20 frontend tests passed, production build passed, and all 16 dedicated research fixtures passed.
- Git index audit found no tracked Playwright output, logs or SQLite databases. Small research source/conventions and this checklist/report are retained deliberately; frozen data, ledgers and generated outputs stay local and ignored.
- Frontend http://localhost:5173 and backend http://localhost:8000 remain running. Research controls have their own hidden coordinator process and do not need the browser open.

### Strategy breadth continuation

- T20 complete: all six controls succeeded, 48 funded scenarios and 16,272 standalone rows. Each run retained source/parameter/input hashes; ledgers rechecked against ending equity. No control process needs restarting.
- T22-T23 complete: `backend/temp/pm-research/short-specification.md` freezes one failed-rally short in a falling SMA200 regime, next-open entry, fixed 3 ATR stop, SMA20/regime/20-held-close exits, synthetic 2%/4% borrow and fixed-short/cash comparisons. `short_candidate.py` passes three fixtures for independent trigger/time exit, entry-day/gap/scheduled exits, and rising-price/borrow losses with collateral shortfall. This is a research hypothesis, not production selection.
- Current write scope: `backend/temp/pm-research/` diagnostic/short-comparison scripts and tests; `docs/temp/` report/checklist/results. Sources of completed runs stay preserved in their output directories.

- T21 running as hidden process 11736: `results/20260914T032109Z/long-diagnostics-v1/run.json`, logs `output/logs/long-diagnostics.*.log`. It reuses all 80 completed funded results, creates paired/annual/class/subgroup diagnostics, then runs the eight predefined matched concentration comparisons and three charts. Two new accounting/bootstrap fixtures passed. Optional research-only NumPy/Matplotlib versions are frozen in `requirements-research.txt`.
- T24 running as hidden process 2064: `results/20260914T032109Z/short-comparison-v1/run.json`, logs `output/logs/short-research.*.log`. Fixed short / failed rally / cash, matched windows and costs, complete per-asset coverage. All 19 earlier research fixtures passed before launch. Do not rerun either process without checking manifests.

### Completed research review and next handoff

- T21 complete: all 80 long funded trials, 27,120 standalone coverage rows, complete/partial annual results, fixed subperiods, class/subgroup contributions, paired 2,000-resample 28/84-day intervals, eight matched top-five-removal funded reruns, and three visually checked charts. Four long-study tables and all artifact links are in the single rewritten `research-report.md`.
- T24 complete: 24 funded short/cash scenarios and 8,136 standalone coverage rows. Dates/statuses match long-study windows; all funded ledgers reconcile. Recent priority failed-rally CAGR -2.31% normal / -3.92% double versus fixed short -5.81% / -7.38% and cash 0%. No short allocation selected.
- Instrument-gap evidence: two doubled-cost ECHO fixed-short standalone scenarios end below zero after a gap exit (27.13 entry to 54.11 exit), on explicitly flagged unresolved inputs. 5,348 standalone cases have synthetic collateral-reserve deficit days. These are model outputs, not verified broker failures. No margin-call/forced-liquidation model exists yet.
- All 21 research fixtures pass. The report generator reuses completed artifacts; optional NumPy/Matplotlib versions are pinned separately. Completed run sources remain preserved.
- Research selection review: retain Donchian as the app default. SMA200 is a lower-return/lower-drawdown comparison candidate; prepare only a clearly named, non-voting research observer for T25. Pullback and failed-rally remain research outputs. T25 is NOT complete: its adapter, frozen-input parity and app integration still need implementation.
- No active research subprocesses remain. Do not rerun completed controls, primary comparisons, diagnostics or the short study on resume. Start with T25 contract/adapter work and its relevant evidence; T29 is another independently eligible task.
