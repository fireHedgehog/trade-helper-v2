"""Fixed Step 4 grid. Shared Step 3 accounting and frozen prices are reused."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STEP3_CODE = ROOT / 'backend/temp/step3'
sys.path.insert(0, str(STEP3_CODE))
from configs import ResearchParams, configurations

OUTPUT = ROOT / 'docs/temp/step4'
AUDIT_SYMBOLS = {'BTC/USD', 'ETH/USD', 'SPY', 'QQQ', 'TLT', 'NVDA', 'ECHO'}


def rules():
    available = {c['id']: c for c in configurations()}
    profiles = [
        ('channel', 55, 3, 'Channel 55'),
        ('channel_initial', 10, 3, 'Initial + channel 10'),
        ('channel_initial', 55, 3, 'Initial + channel 55'),
        ('all', 10, 3, 'Channel 10 + trail 3'),
        ('all', 55, 3, 'Channel 55 + trail 3'),
        ('all', 55, 4, 'Channel 55 + trail 4'),
    ]
    result = []
    for entry in [10, 20, 55, 200]:
        for architecture, exit_len, trailing, label in profiles:
            key = f'{architecture}-e{entry}-x{exit_len}-i2-t{trailing}'
            result.append({**available[key], 'name': f'E{entry} · {label}'})
    key = 'all-e20-x20-i2-t3'
    result.append({**available[key], 'name': 'E20 · channel 20 + trail 3 (reference)'})
    for i, rule in enumerate(result):
        rule['key'] = f'r{i:02d}'
    assert len(result) == 25 and len({r['id'] for r in result}) == 25
    return result


RULES = rules()
SCENARIOS = [(f'{l["key"]}_{s["key"]}', l['key'], s['key'], 'both') for l in RULES for s in RULES]
SCENARIOS += [(f'{r["key"]}_{side}', r['key'] if side == 'long' else None,
               r['key'] if side == 'short' else None, side) for r in RULES for side in ('long', 'short')]
assert len(SCENARIOS) == 675

FIELDS = ['scenario', 'net', 'cagr', 'drawdown', 'gross', 'fee_only', 'trades',
          'common_net', 'common_cagr', 'common_drawdown', 'common_trades', 'common_days',
          'exhausted', 'gross_exhausted', 'price_pnl', 'fees', 'slippage', 'ending',
          'long_pnl', 'short_pnl', 'long_trades', 'short_trades', 'channel_exits',
          'initial_exits', 'trailing_exits', 'unfunded_signals']
LEDGER_FIELDS = ['direction', 'entry_date', 'entry_price', 'exit_date', 'mark_price', 'reason',
                 'signed_units', 'starting_equity', 'price_pnl', 'fees', 'slippage', 'ending_equity', 'mark_date']
