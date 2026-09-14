import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from comparisons import event_index, standalone_data, portfolio
from test_accounting import fixture


def test_asset_slice_rebases_exit_and_preserves_independent_accounting():
    data = fixture(95.)
    data['infos']['X'].update(decision_date='2020-01-01',execution_date='2020-01-02',last='2020-01-03')
    # Earlier warmup calendar must not dilute the standalone reporting period.
    data['dates'].insert(0,'2019-12-31')
    for values in data['market']['X'].values(): values.insert(0,values[0])
    tape = data['tapes']['full']['e20-x55-s3']
    tape.insert(0,[]); tape[2][0]['exit_t']=3
    single=standalone_data(data,'full','X',event_index(data,'full'))
    assert single['dates']==['2020-01-01','2020-01-02','2020-01-03']
    assert single['tapes']['full']['e20-x55-s3'][1][0]['exit_t']==2
    result=portfolio.simulate(single,'single','full','long-initial','equal','normal',1000.)
    assert result['stats']['ending']==pytest.approx((1000/100.15)*(95-.0475-.15))
    assert result['trades'][0]['exit_date']=='2020-01-03'
    assert result['audit']['max_identity_error']<1e-6
    # No next open is unavailable, not a zero-return account.
    data['infos']['X']['execution_date']=None
    assert standalone_data(data,'full','X',event_index(data,'full')) is None
