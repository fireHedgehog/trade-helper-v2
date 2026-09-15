"""Production SMA PMs: independent sides, next-open fills, fixed ATR stop."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.features.signals import engine, indicators
from app.features.signals.params import ENGINE_VERSION as EXECUTION_VERSION, SignalParams
from .contracts import PMDefinition

ENGINE_VERSION = f'sma-1/{EXECUTION_VERSION}'


class SMAParams(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    model: Literal['sma'] = 'sma'
    period: int = Field(default=200, ge=2, le=500)
    atr_len: int = Field(default=20, ge=5, le=60)
    atr_stop_mult: float = Field(default=3.0, ge=0.5, le=6.0)
    fill_at: Literal['open_next'] = 'open_next'
    cost_bps: float = Field(default=5.0, ge=0, le=50)
    slippage_atr: float = Field(default=0.05, ge=0, le=1)

    def start_bar(self):
        return max(self.period - 1, self.atr_len)


def definitions(params: SMAParams | None = None):
    params = params or SMAParams()
    return tuple(PMDefinition.create(
        key=f'sma-trend-{side}', name=f'SMA{params.period} {side}', family='sma',
        direction=side, parameters=params.model_dump(), engine_version=ENGINE_VERSION,
        start_bar=params.start_bar(), voting_enabled=True)
        for side in ('long', 'short'))


def run(bars, params: SMAParams, direction: str, *, start: int):
    if direction not in ('long', 'short'):
        raise ValueError('SMA requires one explicit direction')
    closes = [b['c'] for b in bars]
    average = indicators.sma(closes, params.period)
    above = [ma is not None and close > ma for close, ma in zip(closes, average)]
    below = [ma is not None and close < ma for close, ma in zip(closes, average)]
    rules = engine.CloseRules(
        entries=[1 if up else -1 if down else 0 for up, down in zip(above, below)],
        long_exits=below, short_exits=above, ready=[ma is not None for ma in average],
        overlays={'sma': average, 'sma_period': params.period},
        entry_reason='sma_above' if direction == 'long' else 'sma_below',
        exit_reason='sma_exit')
    # Reuse fill ordering, gap-aware stops, costs and fixed-unit accounting.
    execution = SignalParams(
        entry_len=5, exit_len=3, warmup_buffer=0,
        atr_len=params.atr_len, atr_stop_mult=params.atr_stop_mult,
        fill_at=params.fill_at, cost_bps=params.cost_bps, slippage_atr=params.slippage_atr,
        initial_enabled=True, trailing_enabled=False, channel_enabled=True,
        allow_long=direction == 'long', allow_short=direction == 'short')
    return engine.run(bars, execution, start=max(start, params.start_bar()), rules=rules)
