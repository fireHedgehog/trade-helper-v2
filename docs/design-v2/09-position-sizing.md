# 09 — Position sizing (the Sizing sandbox)

`/sizing`. A **real-time parameter sandbox**, not a decision engine. It takes
the Trend board's on-signal names and answers two questions under a risk-ladder
you drag: *how big should each position be*, and *what is holding each one
back*. It places no order, persists nothing, adds no `params.model` branch, no
`signal_runs`, no migration. Same character as the Vol 60d / Mom. columns — a
derived view over data the app already has.

Why a sandbox and not a live optimiser: sizing is **stateful** (needs NAV,
current holdings, remaining cash, book-level vol) but the board is stateless.
Rather than build a paper-trading ledger, the page lets you *feed* the state as
parameters and watch the sizing surface move.

## Data it consumes

- `GET /api/signals/board` — the existing board response, now with a per-row
  **`sector`** field (`signals/service.py::_sector_map` → `assets.sector`,
  joined in `get_board` alongside the momentum map). Advisory grouping only.
- `GET /api/macro/ai-regime/latest`, falling back to `GET /api/macro/overview` —
  one regime **zone** (risk-on / neutral / risk-off) for the macro overlay. The
  score is shown for context; only the zone drives the maths.

Everything else is client-side arithmetic in `features/sizing/engine.ts`.

## The per-name waterfall (`computeSizing`)

Every step only ever **shrinks** a weight, so the table reads left to right:

1. **Inverse-vol raw** — `w_i ∝ 1 / vol_60d_i`, scaled so the raw book sums to
   `k_max × NAV`. Board rows written before migration 0015 carry no
   `vol_60d`; they are sized off a placeholder **25%** σ and flagged (re-run the
   Trend backtest for the real figure).
2. **Per-name cap** — `min(w_i, per-name cap %)` (P3). Not redistributed.
3. **Per-sector cap + sleeve budget** — each sleeve's allowance is
   `per-sector cap % × target gross`, minus what the *deployed-by-sleeve* table
   already holds; the sleeve's new weights are scaled to fit the headroom (S4).
   The optional coarse sleeve budget (Equities / Bonds / Crypto / Other) caps
   each group the same way.
4. **Whole-book vol target** — estimated book vol from the name vols with a flat
   assumed pairwise correlation of 0.5 (or a manual override); scale the whole
   book by `min(1, vol target / est book vol)`.
5. **Macro overlay** — if enabled, multiply gross by a zone scalar
   (risk-on ×1, neutral ×`neutralScale` default 0.65, risk-off ×`riskOffScale`
   default 0.35). Risk-off additionally zeroes names with weak / missing peer
   rank ("keep only the strongest").

Then `target $ = target % × NAV`, `shares = floor(target $ / last_close)`.

## Sleeves

11 GICS sectors + **Bonds** + **Crypto** + **Other**. `assets.sector` drives the
GICS bucket; `constants.ts::BOND_ETFS` / `CRYPTO_SYMBOLS` (and a `/USD` suffix)
override it for cross-asset names with no sector. Commodity ETFs fall to Other.

## Deployed-by-sleeve — the crowding model

A small editable table of held **% NAV per sleeve** (preset buttons: Flat,
Balanced, Tech-heavy, All-in energy). It is the per-sector cap's "already held"
term, so pushing Tech to its cap visibly blocks new semis breakouts. **Coarse
by design**: it assumes your existing book was itself sized by these rules — the
UI says so. Paste-your-holdings precision is a deferred add-on.

## Verdicts

Per row, in precedence order. They are **narrow and per-name**: whole-book
scaling (vol-target, a neutral / risk-off macro overlay) shrinks every target
uniformly — that is normal operation, shown in the hero, and does **not** turn
rows into WAIT.

- **WAIT** — risk-off dropped this name outright (weak / missing peer rank), or
  its target is too small to ticket for some other reason.
- **HOLD** — the per-sector cap squeezed this name to ~nothing: its sleeve is at
  its cap from your deployed-by-sleeve table, no room here.
- **LIGHT** — a cap (per-name or per-sector) trimmed this name below its
  inverse-vol weight, but it still has a real target.
- **ADD** — clean; there is head-room and only the uniform book scaling applied.

The table has a verdict filter (four checkboxes, all on) with live counts, so
"how many WAIT / HOLD and why" is one glance.

## Outputs

- **Hero** — one line + one number: head-room `$` across N names (green) /
  whole-book throttle scalar (amber) / deployed ≈ target (grey).
- **Gross bar** — deployed ┃ can-add ┃ room-to-k_max ┃ macro-blocked, with a
  target tick; plus a one-line *binding constraint*.
- **Sleeve load** — deployed + proposed vs the sector cap, per sleeve.
- **k_max sensitivity** — resulting target gross at k_max ∈ {0.5, 1, 1.5, 2}.
- **Per-name table** — a tight 6 columns (symbol · sleeve · L/S · mom, Vol,
  Target %, Target $, Shares, Verdict). The full step-by-step waterfall and the
  per-row notes live in the verdict chip's hover, not as columns.

## What it deliberately is not

No order tickets, no "buy/sell X shares vs your actual position" (there is no
per-name current holding — only the coarse per-sleeve deployed table), no
persisted paper equity curve. Those would be a separate paper-trading feature.
