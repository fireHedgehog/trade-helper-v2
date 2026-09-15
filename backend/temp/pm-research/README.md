# Historical independent-PM research

The research workflow below is retained for provenance. It is not an active task
queue. Do not run these commands or restart experiments without a new explicit
user request for research. Start with `docs/temp/agent-work-checklist.md` at the
repository root for application delivery and the user's latest scope.
The technical playbook and historical report live alongside that checklist.
Earlier archived experiments must not be retrieved without explicit user instruction.

These source files and small planning documents are retained in Git. SQLite
inputs, source copies in run outputs, ledgers, generated charts, Playwright files
and logs remain local and ignored. The snapshot manifest and each run manifest
record hashes and exact source versions. A fresh data export produces a different
snapshot; it does not recreate an older input hash.

From `backend`, using the application virtual environment:

```powershell
.venv/Scripts/python.exe -m pytest temp/pm-research/tests -q
.venv/Scripts/python.exe temp/pm-research/snapshot.py create
.venv/Scripts/python.exe temp/pm-research/snapshot.py validate <snapshot-directory>
```

Snapshot creation updates `current-snapshot.json`. Do not create another snapshot
while a batch relying on that pointer is queued. Completed exports are immutable.

`references.py` creates the funded Donchian/buy-and-hold reference once per output
directory. `comparisons.py` creates candidate funded accounts and true per-asset
standalone accounts. Use `--candidate`, `--name` and, only for the first matched
standalone comparison, `--include-references`. Existing output directories are
never overwritten. Failed attempts retain their status, source and logs.

`controls.py` is the explicitly frozen six-control batch for this snapshot. It
waits for the documented primary runs, uses at most two independent processes,
and refuses source changes before each launch. It is not a parameter optimiser.
Do not rerun it when its manifest already exists; inspect or resume deliberately.

All experiments are research only. They use local frozen prices, never provider
fetches, live database writes, broker orders or automatic strategy promotion.

`short-specification.md` freezes the separate failed-rally hypothesis;
`short_comparison.py` compares it with fixed short and cash. `long_diagnostics.py`
reuses completed long runs for annual/class/paired analysis, executes the predefined
matched concentration checks, and writes three charts. Optional plotting libraries
are pinned in `requirements-research.txt`.

`write_report.py` rebuilds the single working report from completed outputs without
rerunning experiments. Completed manifests for the September snapshot are recorded
in the checklist. Never infer that missing ignored outputs should be regenerated
automatically; first locate the original snapshot and recorded run artifacts.
