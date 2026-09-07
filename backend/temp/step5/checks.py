"""Meaningful execution and past-only selection checks for the research stage."""
from datetime import date,timedelta
from settings import ResearchParams
import engine5,reference5
from calculations import evaluate

def check():
    origin=date(2019,10,15)
    bars=[{'date':(origin+timedelta(days=i)).isoformat(),'o':100.,'h':101.,'l':90.,'c':100.} for i in range(100)]
    for i in range(72,100):bars[i].update(o=105.,h=106.,l=104.,c=105.)
    bars[84].update(o=105.,h=106.,l=99.,c=100.)
    p=ResearchParams(entry_len=10,exit_len=55,initial_enabled=False,trailing_enabled=False,allow_short=False)
    q=p.model_copy(update={'exit_len':5})
    prep=reference5.prepare(bars)
    schedule={2019:('old',p),2020:('new',q)}
    trades=engine5.run(bars,('old',p),prep,schedule=schedule)
    assert trades[0]['rule']=='old' and trades[0]['exit_date'] is None
    # A fast exit applied retrospectively would have exited the held trade.
    changed=engine5.run(bars,('new',q),prep)
    assert changed[0]['exit_date'] is not None
    for cost in ['normal','double']:
        result=evaluate(bars,trades,prep['atr'])[cost]['account']['curve']
        ref=reference5.run(bars,('old',p),prep,schedule=schedule,bps=5 if cost=='normal' else 10,slip=.05 if cost=='normal' else .1)
        assert max(abs(a/10000-b) for a,b in zip(result,ref))<1e-12
    # The activation close confirms an order; the first fill is the next open.
    assert not engine5.run(bars,('old',p),prep,start=len(bars)-1)
    for cut in [78,88,95]:
        prefix=bars[:cut]
        a=engine5.signature(engine5.run(prefix,('old',p),reference5.prepare(prefix),schedule=schedule))
        b=engine5.signature(trades)
        assert [t for t in a if t[3]]==[t for t in b if t[3] and t[3]<=prefix[-1]['date']]
    print('Passed: entry-rule retention across annual changes, next-open activation, future-prefix invariance and independent cash.',flush=True)

if __name__=='__main__':check()
