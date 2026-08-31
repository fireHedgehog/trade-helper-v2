# Cross-sectional momentum — research handoff (DONE)

> Scratch, kept only in this snapshot commit. Frozen conclusions:
> `docs/strategy-experiments/xsec-momentum-v1-result.md` (hardcoded tables).
> Stages M1–M4 + cost-×2 ran; a real long-only edge, research only (not wired
> in). This handoff is the original plan; the result doc is authoritative.

Same philosophy as the Turtle work (`docs/strategy-experiments/naive-donchian-v1-result.md`):
a simple, explainable, disciplined rule set — **not** the historical optimum.
Prefer one full-universe default rule; allow an asset-class exception only when
the evidence is large and stable. Producing an exception is not the goal;
producing a clean controlled experiment is.

## What already exists (do NOT rebuild)

The Multisectional page (`features/multisectional/ranking.py`, `05-multisectional.md`)
already computes, per symbol, over the whole active universe:

- **Composite score 0–100** = universe-percentile-rank then weighted mean of:
  `rs_3m .25 / rs_6m .25 / rs_12m .15` (own 63/126/252-session return minus
  SPY's), `high_52w_distance .15`, `trend_distance .10` (mean `ln(price/SMA_n)`,
  n ∈ 20/50/100/200), `slope .10` (are the SMAs rising).
- **Leadership persistence** = fraction of the last 13 weekly formations a name
  sat in the top decile (by 63-session RS) of the liquid top-100.

These are the **entry ranking**. The page and its tabs stay untouched. This
research only decides how to turn the ranking into a strategy: how many to
hold, how often to rebalance, **what the exit is**, direction, and sizing.

## Research tree

1. **M1 — Selection & holding rule** (the "entry" analog)
2. **M2 — Exit architecture** (the decorated-exit question)
3. **M3 — Direction** (long only? long/short? — de-bias controlled)
4. **M4 — Portfolio / sizing** (reuse the Turtle P4 ladder + a momentum-crash variant)
5. **M5 — Cost x2 sanity check**
6. **Freeze** as `xsec-momentum-v1`

Each stage: pre-declare a small candidate set (no continuous sweep, no
per-symbol tuning), run all of them full-universe, pick the modal
Sharpe/Calmar winner across the predefined periods, allow an exception only on
large + stable evidence.

### M1 — Selection & holding

Candidates (cross product, then trim):

| Dimension | Candidates |
| --- | --- |
| Signal | composite score · leadership persistence · both (AND) |
| Basket size N | 10 · 20 · 40 |
| Rebalance cadence | weekly · monthly · quarterly |
| Skip-recent | none · skip the most recent 21 sessions (the Jegadeesh-Titman "12-1" gap) — note `rs_*` already blends 3/6/12m, so test whether an explicit skip helps |

Metric per candidate: equal-weight the basket, hold to next rebalance, book
turnover cost. Report CAGR / Sharpe / maxDD / Calmar / turnover / avg holding
period, full universe and the traded subset, per period.

Expected shape: monthly rebalance, N ≈ 20, composite score as the primary
signal, persistence as a quality filter. Confirm, do not assume.

### M2 — Exit architecture

Hold M1 fixed. Candidates (these are the "OR"s to test cleanly):

| Key | Rule |
| --- | --- |
| `E0` rank-only | sell when a name drops out of the top N at the rebalance. Baseline. |
| `E1` hysteresis | enter top N, exit only below top `1.5·N` — a wide "backstop", the momentum analog of `c3_d20`. |
| `E2` trend gate | E1 + must stay above `SMA_100`; drops below → exit immediately, between rebalances. |
| `E3` exhaustion | E1 + exit if the name's own 21-session return turns negative while still ranked (short-term momentum rolled over). |
| `E4` ATR trail | E1 + a Chandelier `k·ATR` trailing stop under each position (borrow the Turtle exit). |

Select one canonical default + at most one asset-class exception. This is the
"is the exit decorated?" question — the hypothesis is that E1/E2 (hysteresis +
trend gate) beat E0, and E3/E4 add little; test it.

### M3 — Direction

Run, at the frozen M1+M2 rules:

- `long` — hold the top-N winners only (this is the natural momentum book).
- `long/short` — also short the bottom-N losers, dollar-neutral.
- `short` standalone — the loser basket alone, for de-bias.

Split the equity universe into buy&hold-drift quintiles (same control as the
Turtle Stage 3). Momentum crashes (2009, 2020) are almost entirely a short-leg
event (Daniel-Moskowitz "Momentum crashes") — expect **long only** as the
default, with the experiment free to flag any sleeve where the short leg is
genuinely Sharpe-neutral and adds CAGR. Rebound / mean-reversion is a separate
strategy (its own handoff), not the momentum short leg.

### M4 — Portfolio / sizing

Reuse the Turtle Stage 4 P4 ladder verbatim (inverse-vol sizing → 12% vol-
target scalar → per-position 10% NAV + gross caps → fixed sleeve budgets →
weekly rebalance; headline `k_max = 1`). One momentum-specific extra variant:

- **P4 + crash de-risk** — an extra scalar that cuts the whole momentum sleeve
  when its own realised vol spikes above its trailing median (Barroso &
  Santa-Clara "constant-volatility momentum"). Keep only if it clearly improves
  the 2009 / 2020 drawdown.

### M5 — Cost x2

`--cost-mult 2` on every stage script. Momentum turnover is higher than the
Turtle's, so this bites harder — if a rule does not survive, it is not real.
Decisions are checked, not re-optimised.

## Freeze contract

1. Record the fixed selection / exit / direction / sizing rules + any exception.
2. Record engine version, universe, dataset cutoff, both cost levels.
3. Name it `xsec-momentum-v1`.
4. No parameter optimisation inside v1.
5. Conclusions (tables, hardcoded) → `docs/strategy-experiments/xsec-momentum-v1-result.md`.

## Engineering notes

- **Walk-forward ranking.** `ranking.py::compute_ranking` only scores "now".
  The backtest needs the score *as of each rebalance date* — re-run the same
  metric maths on each per-symbol series truncated to date `d`, `d` walking on
  the cadence. The metrics are simple (returns over 63/126/252 sessions,
  distance to the 252-day max, mean `ln(price/SMA_n)`, SMA slope); reimplement
  them compactly in `backend/temp/momentum_experiment.py` rather than importing
  the app function. Align all series to SPY session dates.
- **Portfolio-level engine.** Momentum ranks the whole universe each rebalance
  and holds a basket — a different code path from the per-symbol Donchian
  engine, closer to `portfolio_aggregation_experiment.py` (the deleted Stage 4
  script; its structure is in git history at `c296945`). The final frozen
  strategy needs this path added to `signal_strategies` / the runner.
- Full-universe control + traded-subset report, same as the Turtle.
- SQLite read-only; disposable outputs under `docs/temp/`.

## Artifact map (this phase)

- `backend/temp/momentum_experiment.py` — the staged experiment (M1 first).
- `docs/temp/momentum_*` — disposable CSV / JSON / HTML outputs.
