"""Versioned identities and payloads for independent, persisted strategy views."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Direction = Literal['long', 'short']


def content_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


class PMDefinition(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    family: str
    direction: Direction
    horizon: Literal['daily'] = 'daily'
    start_bar: int = Field(default=65, ge=0)
    parameters: dict[str, Any]
    engine_version: str
    benchmark: bool = False
    voting_enabled: bool = False
    version: str

    @model_validator(mode='after')
    def valid_hash(self):
        if self.version != content_hash(self.model_dump(exclude={'version'})):
            raise ValueError('PM version does not match its frozen definition')
        return self

    @classmethod
    def create(cls, **values):
        values = {'horizon':'daily', 'start_bar':65, 'benchmark':False, 'voting_enabled':False, **values}
        return cls(**values, version=content_hash(values))


class PendingAction(BaseModel):
    action: Literal['enter', 'exit', 'reverse']
    direction: Direction
    signal_date: str
    fill_at: Literal['open_next']
    reason: str | None = None


class Position(BaseModel):
    state: Literal['long', 'short', 'flat'] | None
    state_since: str | None = None
    entry_price: float | None = None
    last_close: float | None = None
    last_date: str | None = None
    current_stop: float | None = None
    unrealized_pct: float | None = None
    atr_20: float | None = None


class PMResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    contract_version: Literal[1] = 1
    symbol: str
    pm: PMDefinition
    input_hash: str
    as_of: str | None
    status: Literal['ok','insufficient_history','invalid_data','failed']
    status_reason: str | None = None
    position: Position
    pending_action: PendingAction | None = None
    trades: list[dict[str, Any]] = Field(default_factory=list)
    daily: list[dict[str, Any]] = Field(default_factory=list)
    overlays: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def independent_side(self):
        if self.position.state not in (None, 'flat', self.pm.direction):
            raise ValueError('Position direction belongs to another PM')
        if any(t.get('direction') != self.pm.direction for t in self.trades):
            raise ValueError('Trade direction belongs to another PM')
        if self.pending_action and self.pending_action.direction != self.pm.direction:
            raise ValueError('Pending action direction belongs to another PM')
        if self.status != 'ok' and (self.position.state is not None or self.trades or self.pending_action):
            raise ValueError('Unavailable PM results cannot masquerade as a position')
        return self
