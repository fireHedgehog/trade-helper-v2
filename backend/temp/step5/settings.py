"""Step 5: a fixed long-only neighbourhood and annual historical evaluation."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'backend/temp/step3'))
from configs import ResearchParams
OUT = ROOT/'docs/temp/step5'
YEARS = list(range(2020, 2027))
LENGTHS = [5, 10, 15, 20, 25, 30, 40, 55, 70]
AUDIT = {'BTC/USD','ETH/USD','SPY','QQQ','TLT','NVDA','ECHO'}
RULES = []
for entry in [5,10,15,20,25,30]:
    for exit_len in [40,55,70]:
        for stop in [None,2.,3.]:
            key = f'e{entry}-x{exit_len}-s{stop:g}' if stop else f'e{entry}-x{exit_len}-s0'
            p = ResearchParams(entry_len=entry,exit_len=exit_len,initial_enabled=stop is not None,
                               atr_stop_mult=stop or 2.,trailing_enabled=False,allow_short=False)
            RULES.append({'id':key,'entry':entry,'exit':exit_len,'stop':stop,'tuned':True,
                          'label':f'{entry}/{exit_len} · '+(f'{stop:g}× ATR initial' if stop else 'channel only'),
                          'params':p.model_dump()})
for side in ['long','short']:
    p=ResearchParams(entry_len=20,exit_len=20,allow_long=side=='long',allow_short=side=='short')
    RULES.append({'id':f'baseline-{side}','entry':20,'exit':20,'stop':2.,'tuned':False,
                  'label':f'Fixed breakout {side} · 20/20 + initial 2 + trail 3','params':p.model_dump()})
BY_ID={r['id']:r for r in RULES}
ANCHORS=['e10-x55-s2','e20-x55-s3','e20-x55-s0']
POLICIES=[*ANCHORS,'adaptive-common','adaptive-class','baseline-long','baseline-short']
LABELS={**{r['id']:r['label'] for r in RULES},'adaptive-common':'Annual selection · one common rule',
        'adaptive-class':'Annual selection · asset-class rules'}
COSTS={'normal':(5.,.05),'double':(10.,.10),'gross':(0.,0.)}
LEDGER=['direction','entry_date','entry_price','exit_date','mark_price','reason','signed_units',
        'starting_equity','price_pnl','fees','slippage','ending_equity','mark_date']


def asset_class(info):
    return 'Crypto' if '/' in info['symbol'] else 'Bonds' if info['group']=='Bonds' else 'Equities and other ETFs'
