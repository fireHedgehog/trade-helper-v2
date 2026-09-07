"""Fixed Step 6 choices, declared before inspecting portfolio results."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'backend/temp/step5'))
from settings import BY_ID, ResearchParams

OUT = ROOT/'docs/temp/step6'
CAPITAL = 100_000.
RULES = ['e20-x55-s0', 'e20-x55-s3', 'baseline-short']
PARAMS = {key: ResearchParams(**BY_ID[key]['params']) for key in RULES}
BOOKS = {
    'long-channel': {'long': RULES[0]},
    'long-initial': {'long': RULES[1]},
    'short-reference': {'short': RULES[2]},
    'combined-channel': {'long': RULES[0], 'short': RULES[2]},
    'combined-initial': {'long': RULES[1], 'short': RULES[2]},
}
LABELS = {'long-channel': 'Long · 20/55 channel only',
          'long-initial': 'Long · 20/55 + initial 3 ATR',
          'short-reference': 'Short · fixed 20/20 benchmark',
          'combined-channel': '50/50 · channel long + benchmark short',
          'combined-initial': '50/50 · initial-stop long + benchmark short',
          'buy-hold': 'Equal-capital buy & hold reference'}
METHODS = {'equal': 'Equal capital', 'inverse-vol': 'Inverse volatility',
           'capped-vol': 'Inverse volatility + entry caps'}
COSTS = {'normal': {'bps': 5., 'atr': .05, 'borrow': .02},
         'double': {'bps': 10., 'atr': .10, 'borrow': .04}}
GROUP_CAPS = {'Equities and other ETFs': .70, 'Bonds': .40, 'Crypto': .10}
SYMBOL_CAP = .10
VOL_BARS = 60
VOL_FLOOR = .01
COMMON_WARMUP = 65
MAX_STALE_DAYS = 7
WINDOWS = {'full': '2016-01-04', 'recent': '2020-01-01'}

ASSUMPTIONS = {
    'capital': CAPITAL,
    'universe': 'Frozen current database: all 678 assets; priority subset 60. Not historical index membership.',
    'windows': 'Full available calendar and a fresh flat start in 2020; previously inspected history, not an unseen holdout.',
    'eligibility': '65 completed asset bars and latest observation no older than 7 calendar days; no future availability filter.',
    'signals': 'Unchanged Step 5 signal engine and fixed rules, with a common 65-bar activation and a flat start for each window; next-open entries. No retries of unfunded entries until a new native entry.',
    'volatility': 'Trailing 60 close-to-close simple returns, sample standard deviation; annualise by sqrt(252), crypto sqrt(365); 1% annual floor. Inputs strictly before entry date.',
    'weights': 'Equal or inverse-vol weights across ALL eligible cohort assets, including flat assets. Size only at entry; no periodic rebalance or cash sweep.',
    'cash': 'Zero cash interest. Fractional units. Fixed units until native exit. Entry costs fit inside the assigned budget.',
    'combined': '50% initial capital per independent long/short sleeve; no transfers or rebalancing between sleeves. Sleeve equity shares subsequently drift.',
    'funding': 'New entries funded from prior marks after accrued borrow; same-day exit proceeds become available next day. Batch requests scaled proportionally, never alphabetically prioritised.',
    'short': 'Synthetic fully collateralised short exposure: reserve twice current short liability from cash (sale proceeds plus own collateral). Assumed borrow 2% annual normal / 4% doubled on previous marked notional, calendar-day accrual. No verified locate, margin, futures funding or venue implementation.',
    'caps': 'Only capped-vol: aggregate long+short gross per symbol <=10%, equities/other ETFs <=70%, bonds <=40%, crypto <=10% of prior-mark portfolio equity at admission. Unused amounts stay cash, no redistribution. Caps do not force exits; market moves can breach them afterwards.',
    'gross_limit': 'All methods admit positions only within each sleeve equity after costs, reserving 100% own collateral for shorts. Subsequent gaps or short losses can cause a funding deficit; recorded, no invented margin liquidation.',
    'costs': COSTS,
    'prices': 'Frozen adjusted OHLC for equities/ETFs and Coinbase raw OHLC for crypto; units are research units in those series. Borrow is additional to signed adjusted-price P&L.',
    'missing_data': 'Hold last known marks, expose stale holdings separately; do not fabricate exits or remove assets with ended histories.',
    'buy_hold': 'One fixed initial-capital/N budget reserved for each cohort member, deployed at its first eligible open in the window; buy once, hold, costs included. Unavailable shares of capital stay cash.',
    'interpretation': 'Portfolio CAGR comes from one shared account, not median asset CAGR. Short and combined cases provide functional comparisons, not short optimisation or an execution recommendation.',
}
