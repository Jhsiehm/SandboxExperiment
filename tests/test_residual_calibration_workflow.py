import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_residual_calibration as workflow


def test_changed_runtime_stops_before_data_access(monkeypatch, tmp_path):
    contract = dict(status='frozen_residual_calibration_v1',
        bindings={str(Path(workflow.__file__).resolve()): 'bound'},
        analysis_environment=dict(python='different', numpy=np.__version__, scipy=workflow.scipy.__version__))
    reads = []
    def read_contract(path):
        reads.append(Path(path).name)
        return contract
    monkeypatch.setattr(workflow, 'read', read_contract)
    monkeypatch.setattr(workflow, 'verify', lambda bindings: None)
    with pytest.raises(ValueError, match='Analysis runtime'):
        workflow.run(tmp_path)
    assert reads == ['contract.json']


def test_gate_requires_both_comparators_and_component_guard():
    identities=[dict(group_id='a',component_id='x'),dict(group_id='b',component_id='y')]
    scores={'transition':{'a':.2,'b':.2},'control':{'a':.18,'b':.18},'extension':{'a':.15,'b':.16}}
    assert workflow.progression_gate(scores,identities)['passed']
    scores['extension']={'a':.175,'b':.175}
    assert not workflow.progression_gate(scores,identities)['passed']
    scores['extension']={'a':.24,'b':.01}
    result=workflow.progression_gate(scores,identities)
    assert result['extension_gain']['control']>.01 and not result['passed']


def fold_fixture():
    profiles=[dict(group_id=f'g{i}',profile=dict(agent_id=f'p{i}',topic=f't{i}')) for i in range(5)]
    identities=[dict(index=i,group_id=f'g{i}',agent_id=f'p{i}',component_id=f'c{i}',fold=i) for i in range(5)]
    folds={'row_identities':identities,'folds':[dict(fold=i,training_row_indices=[j for j in range(5) if i!=j],validation_row_indices=[i]) for i in range(5)]}
    return profiles,folds


def test_fold_partition_and_actual_topic_guard():
    profiles,folds=fold_fixture()
    workflow.validate_folds(folds,profiles)
    profiles[1]['profile']['topic']='t0'
    with pytest.raises(ValueError,match='Topic leakage'):
        workflow.validate_folds(folds,profiles)


def test_crossfit_never_fits_validation_rows(monkeypatch):
    _,folds=fold_fixture()
    seen=[]
    def fit(initial,targets,logits,groups,*,extension):
        seen.append((tuple(groups),extension))
        return dict(table=np.full((6,6),1/6).tolist(),bias=[0]*6,alpha=0)
    monkeypatch.setattr(workflow,'fit',fit)
    monkeypatch.setattr(workflow,'predict',lambda model,initial,logits: np.full((len(initial),6),1/6))
    output,models=workflow.crossfit_arrays(np.array([1,2,3,4,5]),np.array([6,5,4,3,2]),np.zeros((5,6)),np.array([f'g{i}' for i in range(5)]),folds)
    assert len(seen)==10 and len(models)==5
    for fold_index in range(5):
        assert all(f'g{fold_index}' not in x[0] for x in seen[fold_index*2:fold_index*2+2])
    assert all(np.allclose(value,1/6) for value in output.values())


def test_logit_admission_rejects_adapter_or_target_prompt():
    profiles=[dict(group_id='g',profile=dict(agent_id='p',initial_score=2))]
    prompts=[dict(prompt_tokens=[1,2,3])]
    row=dict(arm='base',row_index=0,group_id='g',agent_id='p',initial_score=2,
             class_token_ids=list(range(6)),logits=[0]*6,probabilities=[1/6]*6,
             prompt_sha256=hashlib.sha256(json.dumps(prompts[0],sort_keys=True).encode()).hexdigest())
    workflow.validate_logits([row],profiles,prompts,list(range(6)))
    row['arm']='adapter'
    with pytest.raises(ValueError,match='arm'):
        workflow.validate_logits([row],profiles,prompts,list(range(6)))
