import copy
import pytest
from residual_calibration_v1 import validate_profiles


def fixtures():
    cases=[dict(group_id=f'g{i//4}',profile=dict(agent_id=f'a{i}',topic='topic',initial_score=1,initial_text='initial',partners={})) for i in range(92)]
    ids=[dict(index=i,group_id=c['group_id'],agent_id=c['profile']['agent_id']) for i,c in enumerate(cases)]
    return cases,ids


def test_initial_only_profiles_accepted():
    validate_profiles(*fixtures())


@pytest.mark.parametrize('location',['case','profile'])
def test_target_fields_rejected(location):
    cases,ids=fixtures()
    (cases[0] if location=='case' else cases[0]['profile'])['target_score']=6
    with pytest.raises(ValueError):
        validate_profiles(cases,ids)


def test_row_order_cannot_change():
    cases,ids=fixtures()
    cases[0],cases[1]=cases[1],cases[0]
    with pytest.raises(ValueError,match='identity'):
        validate_profiles(cases,ids)
