"""Shared sizing assumptions for current allocations and historical portfolios."""
from typing import Literal
from pydantic import BaseModel, Field
from app.features.data_management.universe import ETF_BONDS
from app.features.signals.watchlist import TREND_WATCHLIST

MAJOR_COMPANIES = {'AAPL','AMZN','AVGO','BRK.B','COST','GOOG','GOOGL','HD','JNJ','JPM','LLY',
                   'MA','META','MSFT','NVDA','ORCL','PG','TSLA','UNH','V','WMT','XOM'}
PRIORITY = set(TREND_WATCHLIST) | set(ETF_BONDS) | MAJOR_COMPANIES | {'ETH/USD'}
RULES = ['e20-x55-s0', 'e20-x55-s3', 'baseline-short']
BOOKS = {'long-channel': {'long': RULES[0]}, 'long-initial': {'long': RULES[1]},
         'short-reference': {'short': RULES[2]},
         'combined-channel': {'long': RULES[0], 'short': RULES[2]},
         'combined-initial': {'long': RULES[1], 'short': RULES[2]}}
COSTS = {'normal': {'bps': 5., 'atr': .05, 'borrow': .02},
         'double': {'bps': 10., 'atr': .10, 'borrow': .04}}
GROUP_CAPS = {'Equities and other ETFs': .70, 'Bonds': .40, 'Crypto': .10}
SYMBOL_CAP = .10
VOL_BARS = 60
VOL_FLOOR = .01
COMMON_WARMUP = 65
MAX_STALE_DAYS = 7
WINDOWS = {'full': '1900-01-01', 'recent': '2020-01-01'}

class SizingRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    scope: Literal['priority','universe'] = 'priority'
    window: Literal['full','recent'] = 'recent'
    book: Literal['long-initial','short-reference','combined-initial'] = 'long-initial'
    method: Literal['equal','inverse-vol','capped-vol'] = 'equal'
    cost: Literal['normal','double'] = 'normal'
    capital: float = Field(100000., ge=100, le=1e10, allow_inf_nan=False)

def asset_class(symbol: str) -> str:
    return 'Crypto' if '/' in symbol else 'Bonds' if symbol in ETF_BONDS else 'Equities and other ETFs'
