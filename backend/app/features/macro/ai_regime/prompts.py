"""Loader for prompts.toml — the AI risk-on/off prompts.

Read at run time (not import time) so edits to prompts.toml take effect on the
next fetch without a restart. `version` is stored on every ai_regime_run.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPTS_PATH = Path(__file__).with_name("prompts.toml")


@dataclass(frozen=True)
class Persona:
    key: str
    name: str
    instruction: str  # contains "{snapshot}"


DOMAIN_KEYS = ("inflation", "credit_vol", "growth_labor", "rates_curve")


@dataclass(frozen=True)
class Weights:
    base: dict[str, float]      # inflation / credit_vol / growth_labor / rates_curve
    infl_target: float
    infl_gap_full: float
    infl_max_boost: float
    code_blend: float

    def adjusted(self, core_pce_yoy: float | None) -> dict[str, float]:
        """Regime-adjusted weights: inflation scales up with distance of core
        PCE YoY from target; the other three renormalise to keep the sum = 1."""
        w = dict(self.base)
        if core_pce_yoy is not None and self.infl_gap_full > 0:
            gap = abs(core_pce_yoy - self.infl_target)
            boost = max(0.0, min(gap / self.infl_gap_full, 1.0))
            new_infl = self.base["inflation"] + self.infl_max_boost * boost
            others = [k for k in DOMAIN_KEYS if k != "inflation"]
            other_sum = sum(self.base[k] for k in others)
            scale = (1.0 - new_infl) / other_sum if other_sum else 0.0
            w = {"inflation": new_infl, **{k: self.base[k] * scale for k in others}}
        return {k: round(v, 4) for k, v in w.items()}


@dataclass(frozen=True)
class PromptSet:
    version: int
    system: str
    personas: list[Persona]
    rebuttal: str  # contains "{snapshot}", "{own_answer}", "{opposing_answer}"
    reconciler: str  # contains "{snapshot}", "{persona_answers}", "{weights}"
    weights: Weights
    persona_max_tokens: int
    reconciler_max_tokens: int
    temperature: float

    ADVOCATES = ("risk_on", "risk_off")


def _load() -> PromptSet:
    data = tomllib.loads(PROMPTS_PATH.read_text(encoding="utf-8"))

    personas = [
        Persona(key=p["key"], name=p["name"], instruction=p["instruction"].strip())
        for p in data.get("persona", [])
    ]
    if not personas:
        raise ValueError("prompts.toml has no [[persona]] blocks")

    system = data["system"]["text"].strip()
    reconciler = data["reconciler"]["instruction"].strip()
    rebuttal = data.get("rebuttal", {}).get("instruction", "").strip()
    for name, text in [("system", system), ("reconciler", reconciler), ("rebuttal", rebuttal)]:
        if not text:
            raise ValueError(f"prompts.toml: [{name}] is empty")
    for p in personas:
        if "{snapshot}" not in p.instruction:
            raise ValueError(f"persona '{p.key}' instruction is missing {{snapshot}}")
    for token in ("{snapshot}", "{persona_answers}", "{weights}"):
        if token not in reconciler:
            raise ValueError(f"reconciler prompt must contain {token}")
    for token in ("{snapshot}", "{own_answer}", "{opposing_answer}"):
        if token not in rebuttal:
            raise ValueError(f"rebuttal prompt must contain {token}")

    w = data.get("weights", {})
    base = {k: float(w.get(k, d)) for k, d in
            (("inflation", 0.20), ("credit_vol", 0.30), ("growth_labor", 0.30), ("rates_curve", 0.20))}
    weights = Weights(
        base=base,
        infl_target=float(w.get("infl_target", 2.0)),
        infl_gap_full=float(w.get("infl_gap_full", 2.0)),
        infl_max_boost=float(w.get("infl_max_boost", 0.20)),
        code_blend=float(w.get("code_blend", 0.5)),
    )

    meta = data.get("meta", {})
    return PromptSet(
        version=int(data.get("version", 1)),
        system=system,
        personas=personas,
        rebuttal=rebuttal,
        reconciler=reconciler,
        weights=weights,
        persona_max_tokens=int(meta.get("persona_max_tokens", 260)),
        reconciler_max_tokens=int(meta.get("reconciler_max_tokens", 420)),
        temperature=float(meta.get("temperature", 0.4)),
    )


@lru_cache(maxsize=1)
def _cached() -> PromptSet:
    return _load()


def get_prompts(*, reload: bool = False) -> PromptSet:
    if reload:
        _cached.cache_clear()
    return _cached()
