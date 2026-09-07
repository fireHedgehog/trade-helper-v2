"""Small hand-checks of the new switches and independent dollar accounting."""
from datetime import date, timedelta
from configs import ResearchParams
from research_engine import run
from cash import account
from app.features.signals.indicators import wilder_atr


def check():
    bars = [{"date": (date(2020,1,1)+timedelta(days=i)).isoformat(),
             "o": 100., "h": 101., "l": 99., "c": 100., "v": 1000} for i in range(35)]
    for op,hi,lo,cl in [(100,104,100,103),(103,104,90,103),(103,104,102,103)]:
        bars.append({"date": (date.fromisoformat(bars[-1]["date"])+timedelta(days=1)).isoformat(),
                     "o": op,"h":hi,"l":lo,"c":cl,"v":1000})
    for short in [False, True]:
        prices = [{**b,"o":200-b["o"],"h":200-b["l"],"l":200-b["h"],"c":200-b["c"]} for b in bars] if short else bars
        p = ResearchParams(cost_bps=0,slippage_atr=0,trailing_enabled=False)
        stopped = run(prices,p).trades
        free = run(prices,p.model_copy(update={"initial_enabled":False})).trades
        assert stopped[0]["exit_reason"] == "stop_initial"
        assert free[0]["exit_date"] is None
        atr = wilder_atr([b["h"] for b in prices],[b["l"] for b in prices],[b["c"] for b in prices],20)
        dollars = account(prices, stopped, atr, 0, 0)
        assert abs(dollars["ending"]/10000-1-stopped[0]["return_pct"]) < 1e-10
        assert dollars["identity_error"] < 1e-8
    # A channel breach on the final close schedules tomorrow's exit.
    prices = bars[:-2] + [dict(bars[-2],l=95,c=96), dict(bars[-1],o=96,h=98,l=95,c=97)]
    p = ResearchParams(initial_enabled=False,trailing_enabled=False,atr_stop_mult=6)
    assert run(prices,p).trades[0]["exit_reason"] == "channel_reversal"
    assert run(prices,p.model_copy(update={"channel_enabled":False})).trades[0]["exit_date"] is None
    # $10,000 buys/shorts 100 units at $100, exits at $110. The previous
    # close ($90) and price after exit ($130) must never enter the trade P&L.
    prices=[{'date':'2020-01-01','c':90.}, {'date':'2020-01-02','c':105.},
            {'date':'2020-01-03','c':130.}]
    for side,expected in [('long',10889.5),('short',8889.5)]:
        trades=[{'direction':side,'entry_date':'2020-01-02','entry_price':100.,
                 'exit_date':'2020-01-03','exit_price':110.,'exit_reason':'channel_reversal'}]
        dollars=account(prices,trades,[10.,10.,10.],5,.05)
        assert abs(dollars['ending']-expected)<1e-8
        assert dollars['fees']==10.5 and dollars['slippage']==100.
        free=account(prices,trades,[10.,10.,10.],0,0)
        assert abs(free['ending']-(11000 if side=='long' else 9000))<1e-8
    print('Hand checks passed: stop switches, both directions, next-open exits and exact dollar P&L/costs',flush=True)


if __name__ == '__main__':
    check()
