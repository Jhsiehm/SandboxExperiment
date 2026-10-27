import json
import math

import mlx.core as mx
import pytest

from classifier_v1 import build_loss, class_token_ids, probabilities_from_logits, messages, verify, sha


class Tokenizer:
    def encode(self, text, add_special_tokens=False):
        return [ord(text)]
    def decode(self, tokens):
        return chr(tokens[0])


def test_mapping_single_ordered_unique_roundtrip():
    assert class_token_ids(Tokenizer()) == [65,66,67,68,69,70]
    class Multi(Tokenizer):
        def encode(self, *args, **kwargs):
            return [1,2]
    with pytest.raises(ValueError, match='single'):
        class_token_ids(Multi())
    class Duplicate(Tokenizer):
        def encode(self,*args,**kwargs):
            return [1]
    with pytest.raises(ValueError, match='distinct'):
        class_token_ids(Duplicate())


def test_restricted_loss_uniform_and_correct_position():
    ids=[2,3,4,5,6,7]
    # Prompt positions0,1,2. Its lastposition2 predicts class token at position3.
    batch=mx.array([[9,9,9,4,0]])
    lengths=mx.array([[3,4]])
    logits=mx.zeros((1,4,10))
    loss,count=build_loss(ids)(lambda _:logits,batch,lengths)
    assert float(loss.item()) == pytest.approx(math.log(6),rel=1e-6)
    assert int(count.item())==1
    boosted=mx.array([[[0.]*10,[0.]*10,[0.,0.,-100.,-100.,100.,-100.,-100.,-100.,0.,0.],[0.]*10]])
    loss,_=build_loss(ids)(lambda _:boosted,batch,lengths)
    assert float(loss.item())==pytest.approx(0,abs=1e-6)


def test_no_loss_gradient_on_other_positions_or_outside_classes():
    ids=[2,3,4,5,6,7]
    batch=mx.array([[9,9,9,4,0]])
    lengths=mx.array([[3,4]])
    def objective(logits):
        return build_loss(ids)(lambda _:logits,batch,lengths)[0]
    gradient=mx.grad(objective)(mx.zeros((1,4,10))).tolist()[0]
    assert all(value==0 for pos in [0,1,3] for value in gradient[pos])
    assert all(gradient[2][i]==0 for i in [0,1,8,9])
    assert gradient[2][4]<0
    changed=mx.zeros((1,4,10)).at[:,:,0].add(10000)
    assert float(objective(changed).item())==pytest.approx(math.log(6),rel=1e-6)


def test_probabilities_are_restricted_and_mass_separate():
    result=probabilities_from_logits(mx.array([100.,0.,0.,0.,0.,0.,0.]),[1,2,3,4,5,6])
    assert result['probabilities']==pytest.approx([1/6]*6,rel=1e-6)
    assert result['full_vocabulary_class_mass']<1e-30
    with pytest.raises(ValueError,match='Nonfinite'):
        probabilities_from_logits(mx.array([float('nan')]*6),list(range(6)))


def test_prompt_projects_initial_fields_only():
    profile=dict(agent_id='id',topic='topic',initial_score=2,initial_text='initial',partners={'1':'peer'})
    rendered=json.dumps(messages(dict(profile=profile)))
    assert 'peer' not in rendered and 'initial' in rendered
    profile['final_score']=6
    with pytest.raises(ValueError,match='profile'):
        messages(dict(profile=profile))


def test_output_hash_tampering_rejected(tmp_path):
    path=tmp_path/'predictions.jsonl'
    path.write_text('original')
    bound={str(path):sha(path)}
    verify(bound)
    path.write_text('changed')
    with pytest.raises(ValueError,match='Binding'):
        verify(bound)
