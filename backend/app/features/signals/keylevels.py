"""Auto-drawn horizontal reference lines for the Timing chart.

Descriptive context only — prior 52-week high/low, all-time high, and the last
confirmed swing high/low, each labelled by whether price is currently above or
below it ("was resistance -> now support"). Not signals.
"""

from __future__ import annotations

from app.features.signals import indicators as ind

_YEAR = 252


def key_levels(bars: list[dict]) -> list[dict]:
    if len(bars) < 40:
        return []
    h = [b["h"] for b in bars]
    lo = [b["l"] for b in bars]
    last = bars[-1]["c"]
    out: list[dict] = []

    if len(bars) > _YEAR + 1:
        prior_hi = max(h[-_YEAR - 1:-1])
        prior_lo = min(lo[-_YEAR - 1:-1])
        out.append({"price": prior_hi, "label": "52-week high",
                    "kind": "resistance" if last < prior_hi else "reclaimed"})
        out.append({"price": prior_lo, "label": "52-week low",
                    "kind": "support" if last > prior_lo else "broken"})

    ath = max(h[:-1])
    out.append({"price": ath, "label": "all-time high",
                "kind": "resistance" if last < ath else "at highs"})

    piv_hi, piv_lo = ind.confirmed_pivots(h, lo, 3)
    if piv_hi:
        i = piv_hi[-1]
        out.append({"price": h[i], "label": f"{bars[i]['date'][:7]} swing high",
                    "kind": "resistance" if last < h[i] else "was resistance / now support"})
    if piv_lo:
        i = piv_lo[-1]
        out.append({"price": lo[i], "label": f"{bars[i]['date'][:7]} swing low",
                    "kind": "support" if last > lo[i] else "was support / now resistance"})

    # drop lines within 0.5% of an already-listed one
    dedup: list[dict] = []
    for lvl in sorted(out, key=lambda x: x["price"]):
        if not any(abs(lvl["price"] - d["price"]) / lvl["price"] < 0.005 for d in dedup):
            dedup.append(lvl)
    return dedup
