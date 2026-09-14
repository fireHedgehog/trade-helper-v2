import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from long_diagnostics import block_means,reduced_scope,period_stats
from test_accounting import fixture


def test_paired_blocks_preserve_shared_shocks_and_constant_difference():
    shock=np.sin(np.arange(101))*.01
    xs=np.column_stack([shock,shock+.001,shock])
    samples=block_means(xs,28,repeats=100)
    assert samples[:,1]-samples[:,0]==pytest.approx(np.full(100,.001))
    assert samples[:,2]==pytest.approx(samples[:,0])
    assert samples==pytest.approx(block_means(xs,28,repeats=100))


def test_removed_members_no_longer_dilute_funding_and_subperiods_need_full_dates():
    data=fixture(None)
    data['market']['Y']={'inverse':[0.,1.,0.]}
    data['sums']['priority']['members'].append('Y')
    reduced_scope(data,'reduced',['X'])
    assert data['sums']['reduced']['members']==['Y']
    assert list(data['sums']['reduced']['count'])==[0,1,0]
    # Hand-built full curve values: prior equity 100, then 90, then 110.
    curve=[[d,e,0,0,0,0,0,0,0,0,0,0,0,0,0] for d,e in [('2020-12-31',100.),('2021-01-01',90.),('2021-01-02',110.)]]
    stats=period_stats(curve,'2021-01-01','2021-01-02')
    assert stats['net']==pytest.approx(.1) and stats['drawdown']==pytest.approx(-.1)
    assert period_stats(curve,'2021-01-01','2021-12-31') is None
