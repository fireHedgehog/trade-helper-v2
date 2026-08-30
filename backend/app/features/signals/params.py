"""Signal-engine parameters (docs/draft-design/04-trend-page.md §R6/§R10).

v1 exposes the `donchian` knobs only. `SignalParams` is the validation
boundary — the stored `signal_config.params_json` and the `PUT /config` body
both go through it, and the engine only ever reads a validated instance.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Bump when the engine's output could change for the same params — it is part
# of the determinism contract and is stored on every run.
ENGINE_VERSION = "donchian-1"


class SignalParams(BaseModel):
    model_config = {"extra": "forbid"}

    model: Literal["donchian"] = "donchian"

    # Donchian channel breakout (Turtle system).
    entry_len: int = Field(20, ge=5, le=200)
    exit_len: int = Field(10, ge=3, le=100)

    # Shared stop stack.
    atr_len: int = Field(20, ge=5, le=60)
    atr_stop_mult: float = Field(2.0, ge=0.5, le=6.0)
    trail_mode: Literal["chandelier", "exit_channel", "atr_trail"] = "chandelier"
    chandelier_k: float = Field(3.0, ge=1.0, le=6.0)
    atr_trail_k: float = Field(3.0, ge=1.0, le=6.0)

    # Execution / accounting.
    fill_at: Literal["close", "open_next"] = "open_next"
    cost_bps: float = Field(5.0, ge=0.0, le=50.0)
    slippage_atr: float = Field(0.05, ge=0.0, le=1.0)

    # Optional regime gate.
    use_ma_regime: bool = False
    ma_regime: int = Field(200, ge=20, le=400)

    stop_and_reverse: bool = False
    warmup_buffer: int = Field(10, ge=0, le=100)

    # Directions the engine may open. A long-only preset sets allow_short=False;
    # the Timing-page Run overrides both from its Long / Short checkboxes.
    allow_long: bool = True
    allow_short: bool = True

    def max_lookback(self) -> int:
        lbs = [self.entry_len, self.exit_len, self.atr_len]
        if self.use_ma_regime:
            lbs.append(self.ma_regime)
        return max(lbs)

    def warmup(self) -> int:
        return self.max_lookback() + self.warmup_buffer


DEFAULT_PARAMS = SignalParams()
