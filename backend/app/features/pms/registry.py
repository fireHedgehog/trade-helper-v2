"""Register a strategy once; execution and the shared Trend UI discover it here."""
from dataclasses import dataclass
from typing import Callable

from app.features.signals import engine
from app.features.signals.params import ENGINE_VERSION, SignalParams
from . import adapters, sma


def _donchian(bars, definition):
    params = SignalParams(**definition.parameters)
    if params.allow_long != (definition.direction == 'long') or params.allow_short != (definition.direction == 'short'):
        raise ValueError('PM direction does not match its engine parameters')
    start = max(definition.start_bar, params.warmup())
    return engine.run(bars, params, start=start), start


def _sma(bars, definition):
    params = sma.SMAParams(**definition.parameters)
    start = max(definition.start_bar, params.start_bar())
    return sma.run(bars, params, definition.direction, start=start), start


def _legacy_donchian_board(conn, charts):
    from app.features.signals.service import get_board
    return get_board(conn, charts)


@dataclass(frozen=True)
class Strategy:
    key: str
    name: str
    engine_version: str
    definitions: Callable
    execute: Callable
    legacy_board: Callable | None = None


STRATEGIES = {
    'donchian': Strategy('donchian', 'Donchian', ENGINE_VERSION, adapters.definitions, _donchian, _legacy_donchian_board),
    'sma': Strategy('sma', 'SMA', sma.ENGINE_VERSION, lambda assigned: sma.definitions(), _sma),
}


def get(family):
    try: return STRATEGIES[family]
    except KeyError: raise ValueError(f'Unknown registered strategy: {family}') from None


def catalog():
    return [{'key':s.key, 'name':s.name} for s in STRATEGIES.values()]
