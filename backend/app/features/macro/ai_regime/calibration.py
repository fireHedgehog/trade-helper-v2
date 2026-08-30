"""Deterministic calibration of the reconciler's raw score/confidence.

Counters known LLM over-confidence. Every rule is explicit and its firing is
recorded in `calibration_notes`. See docs/draft-design/10-…-10.md §4.4.
"""

from __future__ import annotations


def _agreement_ceiling(on: int, off: int, neutral: int) -> tuple[float, str]:
    counts = sorted([on, off, neutral], reverse=True)
    total = sum(counts)
    if total == 0:
        return 40.0, "no votes"
    top, second = counts[0], counts[1]
    if top == total:
        return 90.0, "unanimous"
    if top >= total - 1:
        return 72.0, "one dissent"
    if top - second >= 2:
        return 62.0, "clear majority, some dissent"
    return 50.0, "near-even split"


def calibrate(
    *,
    score_raw: float,
    confidence_raw: float,
    on_votes: int,
    off_votes: int,
    neutral_votes: int,
    advocate_convictions: list[float],
    stale_series: list[str],
    naive_score: float | None,
) -> tuple[float, float, list[str]]:
    notes: list[str] = []
    score = max(0.0, min(100.0, score_raw))
    conf = max(0.0, min(100.0, confidence_raw))

    # 1. agreement ceiling
    ceiling, why = _agreement_ceiling(on_votes, off_votes, neutral_votes)
    if conf > ceiling:
        notes.append(f"confidence capped at {ceiling:.0f} ({why})")
        conf = ceiling

    # 2. both advocates confident → genuinely two-sided
    if len(advocate_convictions) >= 2 and all(c >= 70 for c in advocate_convictions):
        conf -= 12
        notes.append("both advocates ≥70 conviction → −12 (situation is two-sided)")

    # 3. stale inputs
    if stale_series:
        drop = min(8 * len(stale_series), conf - 15) if conf > 15 else 0
        if drop > 0:
            conf -= drop
            notes.append(
                f"{len(stale_series)} stale series ({', '.join(stale_series[:5])}) → −{drop:.0f}"
            )

    # 4. divergence from the naive composite
    if naive_score is not None and abs(score_raw - naive_score) > 25:
        conf -= 10
        notes.append(
            f"AI score {score_raw:.0f} vs naive {naive_score:.0f} (>25 apart) → −10"
        )

    # 5. score sanity vs the vote tally
    net = on_votes - off_votes
    if net > 0 and score < 45:
        score = (score + 50) / 2
        notes.append("votes lean ON but score was risk-off → pulled toward 50")
    elif net < 0 and score > 55:
        score = (score + 50) / 2
        notes.append("votes lean OFF but score was risk-on → pulled toward 50")

    return round(max(0.0, min(100.0, score)), 1), round(max(0.0, min(100.0, conf)), 1), notes
