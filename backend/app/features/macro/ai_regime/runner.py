"""Orchestrates one AI regime run: snapshot → persona votes → (rebuttal) →
reconciler → deterministic calibration → persist."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, datetime, timezone

from app.features.macro import composite as naive
from app.features.macro.ai_regime import calibration, repository as repo
from app.features.macro.ai_regime import model_catalog as mc
from app.features.macro.ai_regime.openai_client import OpenAIError, chat, extract_json, web_chat
from app.features.macro.ai_regime.prompts import get_prompts
from app.features.macro.ai_regime.snapshot import build_snapshot

logger = logging.getLogger(__name__)

_VALID_VOTES = {"ON", "OFF", "NEUTRAL"}


class RegimeRunError(RuntimeError):
    pass


_PERIOD_DAYS = {"Daily": 1, "Weekly": 7, "Monthly": 30, "Quarterly": 91}
_STALE_GRACE = 12  # extra slack beyond one period + the series' own release lag


def _stale_series(conn: sqlite3.Connection) -> list[str]:
    """A series is 'stale' only if its last observation is older than one full
    period *plus its typical release lag* plus a grace window — i.e. a release
    we should already have seen has not landed. Normal reporting lag (July CPI
    in August) is NOT stale."""
    rows = conn.execute(
        """
        SELECT c.series_id, c.frequency, c.typical_lag_days, s.last_date
          FROM macro_series_catalog c
          LEFT JOIN macro_obs_stats s ON s.series_id = c.series_id
         WHERE c.tracked = 1
        """
    ).fetchall()
    today = date.today()
    out: list[str] = []
    for r in rows:
        if not r["last_date"]:
            out.append(r["series_id"])
            continue
        period = _PERIOD_DAYS.get((r["frequency"] or "").strip(), 30)
        # normal cadence: the latest obs sits ~(period + release-lag) behind
        # today. Only flag when it is a *further* full period past that — i.e.
        # a release we should already have has not landed.
        limit = 2 * period + (r["typical_lag_days"] or 14) + _STALE_GRACE
        try:
            if (today - date.fromisoformat(r["last_date"])).days > limit:
                out.append(r["series_id"])
        except ValueError:
            pass
    return out


def _naive_score(conn: sqlite3.Connection) -> float | None:
    obs_rows = conn.execute(
        "SELECT series_id, date, value FROM macro_observations WHERE value IS NOT NULL "
        "ORDER BY series_id, date"
    ).fetchall()
    by: dict[str, list[tuple[str, float]]] = {}
    for r in obs_rows:
        by.setdefault(r["series_id"], []).append((r["date"], r["value"]))
    return naive.compute(by, None).score


def _cost(model_id: str, pt: int, ct: int) -> float | None:
    for m in mc.load_models():
        if m.id == model_id and (m.input_usd_per_1m or m.output_usd_per_1m):
            return round(m.est_cost_usd(pt, ct), 6)
    return None


async def run(
    conn: sqlite3.Connection,
    *,
    model: str | None,
    budget_key: str,
    force: bool,
) -> dict:
    trading_date = datetime.now(timezone.utc).date().isoformat()
    cached = repo.get_by_date(conn, trading_date)
    if cached and not force and cached["status"] == "ok":
        return repo.full(conn, cached)

    model_id = model or mc.default_model_id()
    budgets = {b.key: b for b in mc.load_budgets()}
    budget = budgets.get(budget_key)
    if budget is None:
        raise RegimeRunError(f"unknown budget '{budget_key}'")
    prompts = get_prompts(reload=True)

    snap, snap_json = build_snapshot(
        conn, detail=budget.snapshot_detail, rate_series_points=budget.rate_series_points
    )
    if not snap.get("macro"):
        raise RegimeRunError("no macro observations — run Fetch macro data first")

    core_pce_yoy = (snap.get("macro", {}).get("PCEPILFE", {}) or {}).get("d12m_pct")
    weights = prompts.weights.adjusted(core_pce_yoy)
    weights_note = (
        f"{json.dumps(weights)}  (inflation weight elevated: core PCE YoY "
        f"{core_pce_yoy}% vs {prompts.weights.infl_target}% target)"
        if core_pce_yoy is not None
        else json.dumps(weights)
    )

    personas = [p for p in prompts.personas if p.key in budget.personas]
    answers: dict[str, dict] = {}
    msgs: list[dict] = []
    seq = 0
    total_pt = total_ct = 0

    async def _call(system: str, user: str, max_tokens: int) -> tuple[str, dict, int, int]:
        text, pt, ct = await chat(
            model_id, system, user, max_tokens=max_tokens, temperature=prompts.temperature
        )
        parsed = _safe_json(text)
        # Reasoning models can spend the whole budget thinking and return an
        # empty / non-JSON body — retry once with a much larger cap.
        if not parsed and (not text.strip() or "{" not in text):
            text2, pt2, ct2 = await chat(
                model_id, system, user, max_tokens=max_tokens * 4,
                temperature=prompts.temperature,
            )
            pt += pt2
            ct += ct2
            p2 = _safe_json(text2)
            if p2 or text2.strip():
                text, parsed = text2, p2
        return text, parsed, pt, ct

    try:
        # ---- round 1: independent persona votes ----
        for p in personas:
            user = (
                p.instruction.replace("{snapshot}", snap_json)
                .replace("{current_date}", trading_date)
            )
            if p.key == "macro_catalyst":
                try:
                    text, pt, ct = await web_chat(
                        model_id, prompts.system, user, max_tokens=budget.persona_max_tokens
                    )
                    parsed = _safe_json(text)
                except OpenAIError as exc:
                    logger.warning("Macro catalyst web search unavailable: %s", exc)
                    parsed = {
                        "vote": "NEUTRAL",
                        "conviction": 0,
                        "impact": 0,
                        "pricing_status": "unclear",
                        "event": "Web search unavailable",
                        "event_date": None,
                        "incremental_reason": "No sourced catalyst assessment was available.",
                        "sources": [],
                    }
                    text, pt, ct = json.dumps(parsed), 0, 0
            else:
                text, parsed, pt, ct = await _call(
                    prompts.system, user, budget.persona_max_tokens
                )
            total_pt += pt
            total_ct += ct
            vote = str(parsed.get("vote", "")).upper()
            answers[p.key] = parsed
            msgs.append(dict(
                seq=seq, role="persona", persona=p.key, round=1, prompt=user, completion=text,
                parsed_json=json.dumps(parsed), vote=vote if vote in _VALID_VOTES else None,
                conviction=_num(parsed.get("conviction")), prompt_tokens=pt, completion_tokens=ct,
            ))
            seq += 1

        # ---- round 2: advocate rebuttals (large budget only) ----
        if budget.rebuttal_round and "risk_on" in answers and "risk_off" in answers:
            for own, opp in (("risk_on", "risk_off"), ("risk_off", "risk_on")):
                user = (
                    prompts.rebuttal.replace("{snapshot}", snap_json)
                    .replace("{own_answer}", json.dumps(answers[own]))
                    .replace("{opposing_answer}", json.dumps(answers[opp]))
                )
                text, parsed, pt, ct = await _call(prompts.system, user, budget.persona_max_tokens)
                total_pt += pt
                total_ct += ct
                vote = str(parsed.get("vote", "")).upper()
                if parsed:
                    answers[own] = {**answers[own], **parsed}
                msgs.append(dict(
                    seq=seq, role="rebuttal", persona=own, round=2, prompt=user, completion=text,
                    parsed_json=json.dumps(parsed), vote=vote if vote in _VALID_VOTES else None,
                    conviction=_num(parsed.get("conviction")), prompt_tokens=pt, completion_tokens=ct,
                ))
                seq += 1

        # ---- round 3: reconciler ----
        user = (
            prompts.reconciler.replace("{snapshot}", snap_json)
            .replace("{persona_answers}", json.dumps(answers, indent=1))
            .replace("{weights}", weights_note)
        )
        text, rec, pt, ct = await _call(prompts.system, user, budget.reconciler_max_tokens)
        total_pt += pt
        total_ct += ct
        msgs.append(dict(
            seq=seq, role="reconciler", persona=None, round=3, prompt=user, completion=text,
            parsed_json=json.dumps(rec), vote=None, conviction=None,
            prompt_tokens=pt, completion_tokens=ct,
        ))
        seq += 1
    except OpenAIError as exc:
        raise RegimeRunError(str(exc)) from exc

    # ---- tally + weighted code score + calibrate ----
    structural_answers = {k: v for k, v in answers.items() if k != "macro_catalyst"}
    final_votes = [str(a.get("vote", "")).upper() for a in structural_answers.values()]
    on = final_votes.count("ON")
    off = final_votes.count("OFF")
    neutral = final_votes.count("NEUTRAL")

    code_score = _weighted_code_score(answers, weights)
    reconciler_score = _num(rec.get("score"))
    blend = prompts.weights.code_blend
    if code_score is not None and reconciler_score is not None:
        structural_score_raw = blend * code_score + (1 - blend) * reconciler_score
    else:
        structural_score_raw = (
            reconciler_score if reconciler_score is not None else (code_score or 50.0)
        )
    event_overlay = _catalyst_overlay(answers.get("macro_catalyst"), trading_date)
    score_raw = max(0.0, min(100.0, structural_score_raw + event_overlay))

    conf_raw = _num(rec.get("confidence")) or 50.0
    naive_score = _naive_score(conn)
    adv_conv = [
        _num(answers.get(k, {}).get("conviction")) or 0.0 for k in ("risk_on", "risk_off")
        if k in answers
    ]
    score, confidence, notes = calibration.calibrate(
        score_raw=score_raw, confidence_raw=conf_raw,
        on_votes=on, off_votes=off, neutral_votes=neutral,
        advocate_convictions=adv_conv, stale_series=_stale_series(conn), naive_score=naive_score,
    )
    if "macro_catalyst" in answers:
        notes.append(_catalyst_note(answers["macro_catalyst"], event_overlay))

    run_row = {
        "trading_date": trading_date,
        "model": model_id,
        "budget": budget_key,
        "prompt_version": prompts.version,
        "score_raw": round(score_raw, 1),
        "score": score,
        "confidence_raw": round(conf_raw, 1),
        "confidence": confidence,
        "calibration_notes": "; ".join(notes) if notes else None,
        "on_votes": on, "off_votes": off, "neutral_votes": neutral,
        "summary": (rec.get("summary") or "").strip() or None,
        "naive_score": naive_score,
        "weights_json": json.dumps(weights),
        "code_weighted_score": (round(code_score, 1) if code_score is not None else None),
        "reconciler_score": (round(reconciler_score, 1) if reconciler_score is not None else None),
        "event_overlay": round(event_overlay, 1),
        "input_snapshot_json": snap_json,
        "prompt_tokens": total_pt, "completion_tokens": total_ct,
        "cost_estimate_usd": _cost(model_id, total_pt, total_ct),
        "status": "ok", "error": None,
    }
    run_id = repo.upsert_run(conn, run_row)
    repo.insert_messages(conn, run_id, msgs)
    return repo.full(conn, repo.get_by_date(conn, trading_date))


_VOTE_VAL = {"ON": 1.0, "NEUTRAL": 0.0, "OFF": -1.0}

_PRICING_FACTOR = {
    "unpriced": 1.0,
    "partly_priced": 0.5,
    "mostly_priced": 0.0,
    "unclear": 0.25,
}


def _catalyst_overlay(answer: dict | None, trading_date: str) -> float:
    """Bounded, fast-decaying event adjustment; structural weights stay intact."""
    if not answer:
        return 0.0
    vote = str(answer.get("vote", "")).upper()
    sign = 1.0 if vote == "ON" else -1.0 if vote == "OFF" else 0.0
    if sign == 0.0 or not answer.get("sources"):
        return 0.0
    impact = max(0.0, min(5.0, _num(answer.get("impact")) or 0.0))
    conviction = max(0.0, min(100.0, _num(answer.get("conviction")) or 0.0)) / 100.0
    pricing = _PRICING_FACTOR.get(str(answer.get("pricing_status", "unclear")), 0.25)
    try:
        event_date = date.fromisoformat(str(answer.get("event_date")))
        age_days = max(0, (date.fromisoformat(trading_date) - event_date).days)
    except ValueError:
        age_days = 3
    recency = 0.5 ** (age_days / 3.0)
    return round(sign * impact * conviction * pricing * recency, 2)


def _catalyst_note(answer: dict, overlay: float) -> str:
    event = str(answer.get("event") or "no qualifying fresh catalyst").strip()[:100]
    pricing = str(answer.get("pricing_status") or "unclear").replace("_", " ")
    return f"macro catalyst overlay {overlay:+.1f} ({event}; {pricing}; 3-day half-life)"


def _weighted_code_score(answers: dict[str, dict], weights: dict[str, float]) -> float | None:
    """Deterministic 0-100 from the neutral domain analysts:
    Σ(weight · conviction · signed_vote) / Σ(weight over those that voted), then
    map [-1,+1] → [0,100]. Advocates (risk_on/risk_off) are excluded."""
    num = den = 0.0
    for key, w in weights.items():
        a = answers.get(key) or {}
        v = _VOTE_VAL.get(str(a.get("vote", "")).upper())
        if v is None:
            continue
        conv = (_num(a.get("conviction")) or 60.0) / 100.0
        num += w * conv * v
        den += w
    if den == 0:
        return None
    return max(0.0, min(100.0, 50.0 + 50.0 * (num / den)))


def _num(v: object) -> float | None:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _safe_json(text: str) -> dict:
    try:
        return extract_json(text)
    except (OpenAIError, ValueError):
        return {}
