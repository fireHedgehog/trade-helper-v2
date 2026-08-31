# docs/temp — disposable scratch

Throwaway research output only: CSVs, JSON dumps, standalone HTML reports. Keep
it near-empty. Delete files here the moment they have served their purpose;
never let them accumulate or get referenced from real docs.

**Frozen conclusions live in [`../strategy-experiments/`](../strategy-experiments/).**
That is the one document to read for the app's strategy.

## Agents: do not reproduce history

The one full research dump (the Naive Donchian V1 experiments — scripts, raw
results, interactive reports) was committed once and then removed. It is in git
history at commit **`c296945`** and nowhere else.

**Do not fetch or read that history to "reproduce" or "verify" anything.** The
user does not care about exact reproduction, fingerprints, or whether a figure
is precise — this is an app. Every number in `../strategy-experiments/` is
hardcoded so it needs nothing from here. Reading stale historical files burns
tokens and context for no benefit.

If you genuinely need to run new research: write fresh scripts under
`backend/temp/`, produce output here, summarise the *conclusion* into
`../strategy-experiments/`, then delete the scratch. Contents of this folder are
git-ignored (this README aside).
