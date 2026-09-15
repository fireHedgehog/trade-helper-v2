"""Expected engine identities by family, shared by evaluation and read surfaces."""
from app.features.signals.params import ENGINE_VERSION as DONCHIAN_VERSION
from .sma import ENGINE_VERSION as SMA_VERSION


def current_engine_version(family: str) -> str | None:
    return {'donchian': DONCHIAN_VERSION, 'sma': SMA_VERSION}.get(family)
