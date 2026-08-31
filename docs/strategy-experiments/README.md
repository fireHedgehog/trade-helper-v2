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
2. [`xsec-momentum-v1-result.md`](xsec-momentum-v1-result.md) — cross-sectional
   relative-strength momentum. Four stages (selection, exit, direction, sizing)
   + a cost-×2 check. A real edge (long-only, monthly, SMA_100 gate, vol-target
   sizing) but **research only** — not yet wired in; needs a portfolio-level
   runner path.
3. [`oversold-bounce-v1-result.md`](oversold-bounce-v1-result.md) — short-term
   mean reversion. **Negative result**: no tradeable bounce alpha in this
   universe. Nothing built; the Multisectional reversal list stays a UI flag.

## Adding a new one

Research a genuinely different model, freeze the decision, then add
`<name>-<version>-result.md` here and a line to the list above. Never rewrite an
existing result file — a new parameter set or model is a new entry.

The full research dumps (scripts + raw outputs) live only in git history:
Naive Donchian V1 at `c296945`; cross-sectional momentum V1 and oversold
bounce V1 at `0d5e72c`. Each was committed once, then removed in the
following commit.
