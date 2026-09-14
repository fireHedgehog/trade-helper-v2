# Independent PM contract, version 1

A PM is an independently named strategy, not a display filter. Each result is
identified by run + asset + PM key + preset version. Several same-direction or
opposing PMs may hold an asset independently. An exit belongs only to its PM.

`contracts.py` defines the saved payload. A definition records family, side,
daily horizon, exact parameters, engine version, immutable preset hash, benchmark
role and voting eligibility. The parameters/engine/identity hash is checked when
loading as well as writing. Changes create a new version, not rewritten history.

A result records a per-asset input hash and actual latest completed bar, execution
status, position, pending action, trades, daily returns, overlays and metrics.
`ok` and `insufficient_history` are distinct: missing results never mean flat.
Failure reasons belong to failed run targets. Freshness is evaluated when reading,
separately from the original result's status. Every coherent run also records its
whole-input hash and frozen assignment manifest; all PMs for one asset use the
same bar snapshot. Never assemble a consensus from silently mixed run versions.

The existing long preset and fixed short are adapters over the existing engine.
Their shared 65-bar/minimum-parameter warmup stays unchanged. The research
comparison's 250-bar warmup is a separate research convention, not a production
engine change. Timing parameter previews are not automatically persisted.

Saved results are immutable. A retry creates a new run. A read must specify its
run and PM identity; "latest successful" may be offered explicitly alongside the
latest attempt's status, but failure cannot be presented as a new successful run.
Old tables remain available during migration. No automatic backfill/recalculation
is implied by creating the schema, and no aggregate grade or order is produced.

Storage uses separate immutable preset definitions, enabled assignments, runs,
targets and compressed result payloads. Each target is unique within a run and
links to one frozen preset version. Save only against that planned target and
matching input. One PM failure is labelled without overwriting other results;
the parent run remains partial/failed rather than silently claiming completion.

Validation: two same-direction PMs and an opposing PM must survive independent
saves and reloads; changed parameters produce a new version; changed inputs cannot
be inserted under the old run; switching chart selection must never mutate data.

Trend's Run all enabled PMs submits the existing background worker. Timing and
Trend extend their existing model dropdowns with saved PMs; selection does not
compute or change assignments. Frozen input bars preserve historical charts even
if live prices change. Migrations 0019-0021 add storage without replacing legacy
signal tables. Changing a PM definition requires a new version and run.

[Descriptive assessment](assessment-contract.md) reads all targets for the asset
in the selected run. Timing displays family-level support and expandable evidence.
Benchmarks stay visible but do not contribute to support counts; missing inputs
remain in required coverage. Funded aggregation, grades, new strategy-family
activation and instrument leverage remain separate roadmap tasks.
