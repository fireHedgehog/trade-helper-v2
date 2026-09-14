"""Adapters preserve production engine behaviour; no DB, fetches or aggregation."""
from __future__ import annotations

from app.features.signals import engine, metrics
from app.features.signals.params import ENGINE_VERSION, SHORT_PARAMS, SignalParams
from app.features.signals.service import _board_state
from .contracts import PMDefinition, PMResult, Position, content_hash


def definitions(long_params: SignalParams) -> tuple[PMDefinition, PMDefinition]:
    long = long_params.model_copy(update={'allow_long':True,'allow_short':False})
    start = max(65,long_params.warmup(),SHORT_PARAMS.warmup())
    return (
        PMDefinition.create(key='donchian-long', name='Donchian long', family='donchian',
            direction='long',parameters=long.model_dump(),engine_version=ENGINE_VERSION,start_bar=start),
        PMDefinition.create(key='donchian-short-benchmark',name='Donchian short benchmark',family='donchian',
            direction='short',parameters=SHORT_PARAMS.model_dump(),engine_version=ENGINE_VERSION,benchmark=True,start_bar=start),
    )


def adapt(symbol: str, bars: list[dict], definition: PMDefinition, result: engine.EngineResult,
          start: int) -> PMResult:
    common = dict(symbol=symbol, pm=definition, input_hash=content_hash(bars),
                  as_of=bars[-1]['date'] if bars else None)
    if len(bars) <= start:
        return PMResult(**common,status='insufficient_history',status_reason=f'Needs more than {start} bars',
                        position=Position(state=None,last_date=common['as_of']))
    state = _board_state(bars,result.trades,result.overlays,result.pending_action)
    return PMResult(**common,status='ok', position=Position.model_validate(state),
                    pending_action=result.pending_action,trades=result.trades,daily=result.daily,
                    overlays=result.overlays,metrics=metrics.summarise(result.trades,result.daily,bars))


def existing_pair(symbol: str, bars: list[dict], long_params: SignalParams) -> list[PMResult]:
    pair = engine.run_pair(bars,long_params)
    start = max(65,long_params.warmup(),SHORT_PARAMS.warmup())
    return [adapt(symbol,bars,definition,pair.directions[definition.direction],start)
            for definition in definitions(long_params)]
