# Agent checklist: ship discretionary trading features

Updated: 2026-09-15. This replaces the old T01–T50 research programme.
Technical definitions and editable defaults: [technical playbook](strategy-comparison-experiment-design.md).

## 1. Resume here

| Field | Current state |
| --- | --- |
| Latest user scope | User resumed implementation: “ok continue then”, starting with the proposed SMA production delivery. |
| Current deliverable | APP01 complete: production SMA long and short run and display in the local app. |
| Implementation state | APP01 complete; continue application delivery, no new research. |
| Next implementation task | APP02: direction, range structure, volatility condition and location. Then directional, two-way range and explicit volatility setup definitions; opportunity grades and leveraged instruments follow. Do not redo SMA. |
| Research state | Historical work retained. No experiment, sweep or performance-admission task is active. |
| Existing checkpoint | PM implementation: f1bffc4. Historical research checkpoint: efdd0ac. |
| Handoff | Read this section and the claimed task only, then its relevant playbook section and local contracts. |

## 2. Rules for every task

- Never commit or push. The user revoked all earlier commit/push authorisation.
  Leave changes uncommitted; the user controls Git history and publication.
- Build visible application capability from established techniques; tune parameters later.
- Every directional strategy must cover long entry/exit AND short entry/exit explicitly.
- No up/down trend still needs a defined state and useful setup choices. Separate range
  width from volatility and its expansion/contraction. Include range long/short, buying
  volatility (such as a long straddle) and selling volatility as distinct named setups.
  Define their conditions before grades and leverage; do not equate sideways with sell-vol.
- Combine structure, location, trigger, invalidation and targets. Include weekly/daily/4-hour
  evidence when available; do not turn the product into a lone SMA or indicator contest.
- No quantitative research, comparative backtests, profitability gates or parameter sweeps
  unless the user explicitly requests them again. Old research conclusions do not veto SMA delivery.
- Check functional correctness, data timing, persistence and affected browser workflows.
  Do not call this permission to run performance experiments.
- Reuse PM isolation, worker, dropdowns, overlays, assessment, sizing and existing data.
- Missing evidence is unavailable, not flat or confirming. A range requires positive evidence.
- Keep trader choices visible and saved. Do not overwrite automatic evidence or other PM states.
- Advance through an authorised implementation batch without asking after every checkbox.
  Respect a later stop or narrower task.

## 3. Completed capability: reuse it

These are recorded implementation checkpoints, not fresh full-suite results from this documentation task.

| Capability | Evidence and boundary |
| --- | --- |
| Independent PM definitions/results/assignments and run-all worker | [PM contract](../../backend/app/features/pms/README.md), checkpoint f1bffc4. Several PMs may hold the same asset in either direction. |
| Saved PM selection in Trend and Timing | Existing dropdowns and charts; changing the displayed PM does not mutate its state. |
| Descriptive assessment | [Assessment contract](../../backend/app/features/pms/assessment-contract.md). Family support/coverage exists; allocation, hard-veto policy, grades and leverage do not. |
| Four signal tables behind a collapsed accordion | [Trend page](../../frontend/src/features/trend/TrendPage.tsx), checkpoint abf3c46. Preserve long entry/exit and short entry/exit. |
| Donchian long and existing fixed short | Existing signal engine/adapters. Fixed short does not substitute for another family's short implementation. |
| Funded sizing, costs and direction contributions | [Sizing design](../design-v2/09-position-sizing.md). Reuse the arithmetic, then extend explicitly for instruments. |
| Macro, multisectional and refresh workflow | Existing context/data features; not yet a combined discretionary opportunity policy. |
| Playwright artifacts and logs ignored | [.gitignore](../../.gitignore), checkpoint abf3c46. Do not recommit generated outputs. |
| Prior experiments | [Historical report](research-report.md), checkpoint efdd0ac. Completed records; do not restart them or treat them as the active plan. |

The earlier statement that arbitrary PM independence was absent is obsolete after f1bffc4.
The earlier statement that aggregation was wholly absent also needs precision: descriptive
assessment exists; the action/size decision policy remains unfinished.

## 4. Small deliverables in implementation order

All unchecked rows are proposed, not claims that a feature is already implemented.
An authorised coordinator may subdivide a row into smaller visible slices; preserve its
acceptance conditions and both directions. Do not count documents as product completion.

| ID | Status | Deliverable | Prerequisites | Done means |
| --- | --- | --- | --- | --- |
| APP01 | [x] done | Production SMA long and short | Existing PM contract | Versioned SMA200 long/short PMs run and save independently, use next-open entries/exits, a fixed 3 ATR20 stop and existing cost accounting, and appear in Trend/Timing with overlays and reasons. Donchian remains available. Completion evidence below. |
| APP02 | [ ] proposed | Structure, volatility condition and location on charts | Existing bars/charts; playbook §§3, 8 | Confirmed HH/HL/LH/LL and protected levels; UP/DOWN/RANGE/TRANSITION/UNKNOWN; anchored zones/channels and high/middle/low labels; narrow/wide range and volatility expansion/contraction described separately; reasons and unavailable cases visible. |
| APP03 | [ ] proposed | Trend pullback long AND trend rally short | APP02 | Both daily recipes from §4 run/save as independent PMs; entry, stop, first obstacle/target, cost and invalidation visible. |
| APP04 | [ ] proposed | Range long AND range short | APP02 | Both range-edge recipes run/save; broken ranges suspend entries; middle-of-range and unclear structure do not become automatic signals. |
| APP04V | [ ] proposed | Explicit non-directional setup rules and cards | APP02, alongside APP04 | Define conditions for two-way range trading, buying volatility (including a named long-straddle candidate) and selling volatility with a named defined-risk structure. Show trigger, invalidation, required inputs and why each setup applies or waits. Do not infer an options opportunity from range width alone; distinguish long/short straddles explicitly. Pricing and leg construction belong to APP13. Complete these definitions before grades/leverage. |
| APP05 | [ ] proposed | Editable structure and trade-plan review | APP02–APP04 | Trader can adjust anchors/levels and accept/reject a plan with a reason; original automatic output and version history survive. |
| APP06 | [ ] proposed | Weekly context | APP02 | Completed weekly bars and structure beside daily plans; major obstacles/conflicts visible; forming bars labelled separately. |
| APP07 | [ ] proposed | Genuine 4-hour data path | Data contract from playbook §5 | Timestamped bars, provider/session/calendar metadata, coverage/freshness and persistence; missing data explicit; daily history never expanded into invented intraday bars. |
| APP08 | [ ] proposed | Multi-timeframe entry evidence | APP03–APP04, APP06–APP07 | Weekly context + daily location + optional 4-hour trigger, with as-of cutoffs and supporting/opposing/unavailable reasons; no fake probability or three-vote shortcut. |
| APP09 | [ ] proposed | Opportunity card and net reward/risk | APP03–APP04 | Complete directional plan from §6; expected fill, structural stop, nearest obstacle, costs and missing instrument assumptions; manual override recorded. Reuse fields introduced earlier. |
| APP10 | [ ] proposed | Decision policy across all PMs | APP09 and existing descriptive assessment | Explicit versioned agreement/opposition/veto policy; holdings differ from fresh entries; macro/multisectional context; reasons and coverage; no PM state overwritten. |
| APP11 | [ ] proposed | Discretionary C/B/A sizing | APP10, APP04V | Editable base lot and grade multipliers, cash basis, stop-risk/exposure limits, trader override and clear arithmetic. Keep opportunity grade distinct from instrument leverage. No calibration exercise required. |
| APP12 | [ ] proposed | One concrete leveraged instrument route | APP11 | Select a supported instrument; model multiplier, financing/margin, costs and constraints. Separate instrument mechanics from underlying direction and from a simple 2x quantity stress. |
| APP13 | [ ] proposed | Price and construct volatility instrument plans | APP04V and actual options data/instrument support | Turn the named volatility setups into explicit legs, quotes, expiry, payoff, cost and management rules. Support buying volatility and defined-risk selling volatility separately; identify long versus short straddle. Report missing inputs rather than invent prices. Implement within the instrument stage; APP04V definitions do not wait for it. |
| APP14 | [ ] deferred | More named composite techniques | First four setup templates shipped | Pick one useful technique from §7, specify both directions and integrate it. No catalogue-wide research prerequisite. |

APP01 implementation starts by inspecting the existing SMA source/contract, not its historical
profit report. Retain the existing intended long rule; specify the corresponding short trigger,
exit, initial stop, holding state and execution timing before coding. Changes to those semantics
create a named version. Shipping SMA does not complete APP02–APP04.

## 5. Agent coordination: no conflicting writers or repeated work

Default: one active writer in this checkout. One coordinator owns this checklist.
A Markdown claim is a handoff record, not an atomic lock.

| Task | Owner | Base / worktree | Write scope | State | Next action |
| --- | --- | --- | --- | --- | --- |
| DOC01 | Codex, 2026-09-15 | efdd0ac / main | Playbook, checklist, workflow instructions and historical-reference notices | done | User authorised implementation |
| APP01 | Codex, 2026-09-15 | efdd0ac / main | PM SMA runner/registry, shared execution rules, Trend/Timing UI, focused tests and documentation | done | Released. APP02 is next; existing SMA results require no rerun for handoff. |

Before a resumed implementation task:

1. Read the resume section, chosen row and existing completion evidence.
2. Check Git status and relevant instructions. Preserve unrelated/uncommitted work.
3. Claim one task with owner, base revision/worktree, exact files and next action.
4. If parallel workers are useful, the coordinator assigns disjoint scopes and isolated
   worktrees. Schema, shared contracts and dependency files each have one owner.
5. Complete a visible slice, run checks appropriate to its changed boundaries, then record
   files, revision if committed, result and remaining limitations.
6. Release the claim and advance to the next eligible task within the authorised batch.

Never reset, clean, overwrite or delete another agent's work to obtain a clean checkout.
Never share a writable app database between isolated workers. A worker returns its handoff
to the coordinator rather than racing to edit this checklist.

Do not rerun completed checks without a changed dependency, regression, failure or user request.
When interrupted, save exact next action and any live process/session ID. On resume, check
whether that process finished before launching another. Do not repeat repository-wide reading
or reopen old experiment outputs to recover context.

## 6. Completion record

| Task | Result | Verification | Remaining work |
| --- | --- | --- | --- |
| DOC01 | Sourced playbook replaces quant-first roadmap; checklist preserves SMA production, all directions, structure/location and multiple timeframes. | Primary references reviewed; local Markdown links and Git whitespace checked. | App tasks above remain unimplemented by this documentation change. |
| APP01 | [SMA runner](../../backend/app/features/pms/sma.py), [family versions](../../backend/app/features/pms/versions.py), shared execution, PM service/assessment, Trend/Timing overlays and direction-specific labels. | 63 focused backend checks across signals/PMs/SMA/assessment/sizing and 20 frontend checks passed; frontend production build passed. Browser verified both SMA selections, rule text, chart lines/stops and trade history, plus Trend's collapsed four-table accordion. Normal app job 116 / PM run 2 finished 2026-09-15: 2,712 targets, no failures; each SMA side has 673 usable results and 5 insufficient-history records. | Parameters are displayed read-only in this slice; no new settings editor. Short borrow/financing excluded as labelled. APP02–APP14 remain open. |

For future rows record a concrete capability and evidence, not “research complete” or a
percentage. A task with a missing short side, unsaved output or placeholder UI is not done.
