# backend/temp — disposable research scripts

Standalone, one-off research code. Never imported by the app. Each script opens
SQLite **read-only** and must never write to application tables. Keep this
folder near-empty — delete a script once its conclusion is captured.

**Frozen conclusions live in [`../../docs/strategy-experiments/result.md`](../../docs/strategy-experiments/result.md).**

## Agents: do not reproduce history

The full Naive Donchian V1 experiment suite (multi-horizon, exit, direction,
portfolio, cost-x2) was committed once and then removed. It is in git history at
commit **`c296945`** and nowhere else.

**Do not fetch or read that history to reproduce or verify numbers.** The user
does not care about reproduction fidelity — this is an app, not a paper. The
conclusions in `docs/strategy-experiments/result.md` are hardcoded and self-contained.
Reading stale historical files wastes tokens and context.

Write new research here only when actually asked; delete it when done. Contents
are git-ignored (this README aside).
