# Descriptive assessment v1

Frozen 2026-09-14, checklist T26. This is a read-only consumer of independent PM
results, before funded aggregation, grades or instrument selection.

An assessment identifies one asset, saved run, every PM key/version/input hash,
the saved asset cutoff, assessment date, and this contract version. The expected
PM set is the run's frozen target manifest for that asset. Reads use a consistent
database transaction. A newer failed attempt never falls back to an older success.
Changing the chart dropdown never changes this set.

| Observation | Exact meaning |
| --- | --- |
| Fresh entry | An available PM has an `enter` action confirmed at the common cutoff, pending the next asset open. |
| Active support | An available PM holds its direction and has no pending exit. An old holding is support, not a fresh trigger. |
| Exit | A pending exit belongs to its PM. Show the still-held position, but do not count it as support for a new next-open proposal. |
| Abstention | Available, flat, no pending entry. Flat is neither opposition nor veto. |
| Opposition | Long support is opposition to a short proposal, and conversely, only on the same daily horizon. Show both directions without a net score. |
| Unavailable | Missing/failed/cancelled/queued/invalid/insufficient results; changed stored prices; a different cutoff; outdated engine; unsupported action; or cutoff more than seven calendar days old. Keep the expected member in coverage. |
| Hard veto | Reserved for a future named allocation policy. Missing required evidence will block that policy, but this descriptive read does not invent borrow, risk or allocation decisions. |

Freshness is relative to the latest stored asset input hash and assessment UTC
date. Seven calendar days is an explicit operational threshold inherited from
research stale-price handling, not an official exchange calendar or proof the
provider is up to date. The UI displays the cutoff and reasons. This endpoint
does not claim historical replay: it compares a saved run with currently stored
data. T29 defines point-in-time historical context separately.

Recent agreement uses five completed **asset bars**, including the cutoff.
A pending entry qualifies today. A still-held position qualifies when its entry
decision (the asset bar before its actual fill) is in that window. Exited trades
and pending exits never supply recent agreement. Calendar days do not replace
asset bars; old holdings remain active support without recent agreement.

The descriptive family set contains all non-benchmark target PMs, regardless of
`voting_enabled`; that flag remains an independent activation gate for future
funded policies. Benchmarks are visible in the evidence but excluded from family
counts, even if an erroneous definition enables their voting flag. No definition
is modified or promoted by this assessment.

Each family contributes at most one support count. All member PMs must be
available. Unavailable members make that family's support unavailable, preserving
the denominator. All members supporting the same side count once. All abstaining
or exiting give no directional support. Disagreement, including one supporting
and another flat/exiting, is `mixed` and counts for neither side. A mixed family
never creates two independent confirmations. Recent family agreement requires
every supporting member to have a valid recent entry decision.

Output includes long/short supporting and recent families, mixed families,
expected/available PM and family coverage, and per-PM observations with exclusion
and unavailability reasons. Zero support is distinct from missing evidence.
Assessment status is unavailable if a required non-benchmark member is missing;
observable families can still be displayed with that incomplete coverage label.

No PM record, assignment, trade, stop, position or pending action is changed.
No combined order, position size, grade, leverage, probability or hard-veto rule
is inferred. Future policies must freeze their own selected family set and keep
references to these underlying PM facts.
