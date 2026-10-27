import json
import math
import pytest
from scripts import evaluate_outcome_classifier as ev


def test_metrics_known_cases():
    assert ev.metrics([0,0,1,0,0,0],3,3) == dict(rps=0,change_brier=0,expected_category_mae=0)
    value=ev.metrics([1,0,0,0,0,0],1,6)
    assert value == dict(rps=1,change_brier=1,expected_category_mae=5)


def dump(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj))


def fixture(root):
    cases=[dict(group_id='g',profile=dict(agent_id='p',initial_score=2))]
    for arm in ev.ARMS:
        row=dict(arm=arm,group_id='g',agent_id='p',probabilities=[1/6]*6,logits=[0]*6,prompt_sha256='same')
        path=root/'internal'/arm/'predictions.jsonl'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(row)+'\n')
        dump(path.parent/'summary.json',dict(status='completed',completed=1,contract_sha256='contract',predictions_sha256=ev.sha(path)))
        dump(root/f'watchdog-internal-{arm}'/'summary.json',dict(exit_code=0,child_returncode=0,stop_reason=None,error=None))
    return cases


def test_admit_matched_predictions(tmp_path):
    cases=fixture(tmp_path)
    rows,_=ev.admit_predictions(tmp_path,'internal',cases,'contract')
    assert len(rows['base'])==1


@pytest.mark.parametrize('change',['partial','prompt','logits','identity','watchdog'])
def test_admission_rejects_incomplete_or_mismatched(tmp_path,change):
    cases=fixture(tmp_path)
    path=tmp_path/'internal/pilot_classifier/predictions.jsonl'
    row=json.loads(path.read_text())
    if change=='partial': row=None
    elif change=='prompt': row['prompt_sha256']='different'
    elif change=='logits': row['logits'][0]=10
    elif change=='identity': row['agent_id']='wrong'
    if change=='watchdog':
        dump(tmp_path/'watchdog-internal-pilot_classifier/summary.json',dict(exit_code=124,child_returncode=0,stop_reason='wall_seconds'))
    else:
        path.write_text('' if row is None else json.dumps(row)+'\n')
        summary=ev.read(path.parent/'summary.json')
        summary['predictions_sha256']=ev.sha(path)
        dump(path.parent/'summary.json',summary)
    with pytest.raises(ValueError):
        ev.admit_predictions(tmp_path,'internal',cases,'contract')


def test_probability_validation():
    for p in ([0]*6,[float('nan')]*6,[True,0,0,0,0,0],[1,0,0,0,0]):
        with pytest.raises(ValueError):ev.probs(p)
