# Strategy experiments

Frozen results of the strategy research — one file per model that has been
locked in. Conclusions only, not process. Each file's numbers are **hardcoded
literals**; they depend on nothing else. Do not fetch git history to reproduce
or verify — it wastes tokens and the user does not care about reproduction
fidelity.

Naming: `<model-name>-<version>-result.md`.

## Results

1. [`naive-donchian-v1-result.md`](naive-donchian-v1-result.md) — the first
   frozen trend benchmark. Five stages (entry horizon, exit architecture,
   direction, portfolio) + a cost-×2 sanity check. Wired into the app via the
   `signal_strategies` registry (migration `0014`).

## Adding a new one

Research a genuinely different model, freeze the decision, then add
`<name>-<version>-result.md` here and a line to the list above. Never rewrite an
existing result file — a new parameter set or model is a new entry.

The one full research dump (scripts + raw outputs) is in git history at commit
`c296945` and nowhere else.
