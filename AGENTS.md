# Project instructions

## Git control belongs to the user

- Never run git commit or git push. The user explicitly prohibited both.
- Leave changes uncommitted for the user to review, revert, commit and push.
- Earlier commit/push authorisation is revoked. Broad implementation permission
  never authorises committing, pushing or rewriting Git history.

The user reset the workflow on 2026-09-15: **build application features for a
discretionary technical trader; implementation first, parameter tuning later.**

- Start at `docs/temp/agent-work-checklist.md`, then read only the relevant part
  of `docs/temp/strategy-comparison-experiment-design.md` (the technical playbook).
- Trend/Timing and PM computations must always replay the full available stored
  history, for individual assets and all-target runs. Never make them incremental,
  append-only, shortened-window or skip-unchanged computations. Fetching new market
  data is a separate operation; its incremental mode must not change strategy runs.
- Use established technical disciplines and clear editable defaults. Combine
  structure, location, trigger, invalidation and targets with relevant evidence.
- Preserve uptrend, downtrend, confirmed range and unclear-state distinctions.
  Define high/low using visible structural anchors. Weekly context, daily setups
  and genuine 4-hour data have separate roles; unavailable data is not a vote.
- Keep the user's SMA production request in scope, including its short side;
  historical research conclusions are not a production admission gate.
- Every directional family includes long AND short behaviour. Neutral/range and
  options volatility exposure must be explicit. Never substitute the fixed short
  benchmark for implementing a new family's short side.
- Do not run quantitative research, comparative backtests, profitability gates,
  parameter sweeps or statistical/forward validation unless the user explicitly
  requests that work again. Do not resume the superseded T01-T50 research plan.
- Small functional tests, correct arithmetic, bar timing, persistence isolation
  and browser checks are required as appropriate; profitability proof is not.
- Deliver visible functionality using existing PM storage, worker, dropdowns,
  chart overlays and assessment. Preserve PM independence and trader overrides.
- Keep one concise completion record per feature. Do not count research or
  documentation tasks as product-completion percentages or reread completed work.
- Preserve existing data and research records. Do not retrieve archived
  experiments without explicit user instruction. Do not launch broker orders.
- Existing project authorisation covers routine implementation; do not ask for
  permission at every checklist item. Current user instructions take precedence.
