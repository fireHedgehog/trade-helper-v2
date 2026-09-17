"""Expected engine identities by family, shared by evaluation and read surfaces."""
from .registry import STRATEGIES


def current_engine_version(family: str) -> str | None:
    strategy = STRATEGIES.get(family)
    return strategy.engine_version if strategy else None
