import hashlib
import json

import pytest

from format_smoke_v1 import initial_cases, strict_probabilities, repetition_fraction


@pytest.mark.parametrize('text', [
    '{"probabilities":[1,0,0,0,0,0],"probabilities":[0,1,0,0,0,0]}',
    '{"probabilities":[true,0,0,0,0,0]}',
    '{"probabilities":[NaN,0,0,0,0,1]}',
    '{"probabilities":[0,0,0,0,0,0]}',
    '```json\n{"probabilities":[1,0,0,0,0,0]}\n```',
    '{"probabilities":[1,0,0,0,0,0],"explanation":"extra"}',
])
def test_strict_no_repairs(text):
    with pytest.raises(ValueError):
        strict_probabilities(text)


def test_declared_prefix_plus_exact_continuation():
    assert strict_probabilities('{"probabilities":[' + '0.1,0.2,0.3,0.4,0,0]}') == [.1,.2,.3,.4,0,0]
    with pytest.raises(ValueError):
        strict_probabilities('{"probabilities":[' + 'I think that is true.')


def source_fixture(tmp_path):
    inputs = tmp_path / 'inputs'
    inputs.mkdir()
    raw = 'event_type,worker_id,sliderValue,text\n' + ''.join(
        f'Initial Opinion,w{i},{i+1},initial{i}\n' for i in range(4))
    raw += 'Post Opinion,w0,6,SECRET_LATER\nmessage_sent,w0,4,SECRET_HISTORY\n'
    (inputs / 'train.csv').write_text(raw)
    manifest = {'groups':[
        dict(group_id='validation-never-open', partition='validation', topic='excluded', sha256='none'),
        dict(group_id='rejected-train-never-open', partition='train', topic='excluded', sha256='none'),
        dict(group_id='train', partition='train', topic='selected', sha256=hashlib.sha256(raw.encode()).hexdigest()),
        dict(group_id='later-train-never-open', partition='train', topic='excluded', sha256='none')]}
    (inputs / 'manifest.json').write_text(json.dumps(manifest))
    (tmp_path / 'preparation-audit.json').write_text(json.dumps({'per_group':{'train':4,'later-train-never-open':4}}))
    return tmp_path


def test_exact_first_admitted_train_initial_only(tmp_path):
    cases, path = initial_cases(source_fixture(tmp_path))
    assert len(cases) == 4 and path.name == 'train.csv'
    assert all(c['group_id'] == 'train' and c['profile']['partners'] == {} for c in cases)
    assert 'SECRET' not in json.dumps(cases)
    assert 'worker_id' not in json.dumps(cases)
    assert [c['profile']['initial_score'] for c in cases] == [1,2,3,4]


def test_training_checksum_enforced(tmp_path):
    source_fixture(tmp_path)
    (tmp_path / 'inputs/train.csv').write_text('changed')
    with pytest.raises(ValueError, match='checksum'):
        initial_cases(tmp_path)


def test_repetition_diagnostic_counts_repeated_token_grams():
    assert repetition_fraction([1,2,3]) == 0
    assert repetition_fraction([1,2,3,4,5]) == 0
    assert repetition_fraction([1] * 8) == .8


def test_contract_rejects_policy_divergence(tmp_path):
    import format_smoke_v1 as m
    protocol = tmp_path / 'protocol.json'
    protocol.write_text('{"max_new_tokens":256}')
    contract = dict(status='frozen_training_only_format_diagnostic', protocol_path=str(protocol),
                    bindings={str(protocol):m.sha(protocol)}, policy={'max_new_tokens':512})
    (tmp_path / 'contract.json').write_text(json.dumps(contract))
    with pytest.raises(ValueError, match='policy'):
        m.load_contract(tmp_path)


def report_fixture(tmp_path, monkeypatch):
    import format_smoke_v1 as m
    def dump(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
    dump(tmp_path / 'contract.json', {})
    prompts = [dict(agent=f'p{i}', group='g', condition=c, assistant_prefix='' if c=='original' else '{"probabilities":[')
               for i in range(4) for c in m.CONDITIONS]
    dump(tmp_path / 'prompts.json', prompts)
    monkeypatch.setattr(m, 'load_contract', lambda path: {'policy':{'total_wall_seconds':900}})
    for arm in m.ARMS:
        records = []
        for p in prompts:
            full = '{"probabilities":[1,0,0,0,0,0]}'
            records.append(dict(**p, arm=arm, status='valid', probabilities=[1,0,0,0,0,0],
                assembled_response=full, continuation=full[len(p['assistant_prefix']):],
                generated_tokens=[1,2], generated_token_count=2, finish_reason='stop', token_cap_hit=False,
                repetition_fourgram_fraction=0, prompt_sha256=hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()))
        path = tmp_path / arm / 'predictions.jsonl'
        path.parent.mkdir()
        path.write_text(''.join(json.dumps(r)+'\n' for r in records))
        dump(path.parent / 'summary.json', dict(status='completed',completed=8,valid=8,
            contract_sha256=m.sha(tmp_path/'contract.json'),predictions_sha256=m.sha(path)))
        dump(tmp_path / f'watchdog-format-{arm}/summary.json', dict(exit_code=0,child_returncode=0,
            stop_reason=None,error=None,elapsed_seconds=1))
    return m


@pytest.mark.parametrize('tamper', ['validity','prompt_hash','prefix','arm','group'])
def test_report_rejects_forged_records(tmp_path, monkeypatch, tamper):
    m = report_fixture(tmp_path,monkeypatch)
    path = tmp_path/'base/predictions.jsonl'
    records = [json.loads(line) for line in path.read_text().splitlines()]
    if tamper=='validity':
        records[0]['status']='invalid_format'
    elif tamper=='prompt_hash':
        records[0]['prompt_sha256']='changed'
    elif tamper=='prefix':
        records[0]['assistant_prefix']='changed'
    else:
        records[0][tamper]='changed'
    path.write_text(''.join(json.dumps(r)+'\n' for r in records))
    summary=m.read(path.parent/'summary.json')
    summary.update(predictions_sha256=m.sha(path),valid=sum(r['status']=='valid' for r in records))
    (path.parent/'summary.json').write_text(json.dumps(summary))
    with pytest.raises(ValueError):
        m.report(tmp_path)
    assert not (tmp_path/'format-evaluation.json').exists()


def test_report_preserves_both_conditions(tmp_path,monkeypatch):
    m=report_fixture(tmp_path,monkeypatch)
    m.report(tmp_path)
    value=m.read(tmp_path/'format-evaluation.json')
    assert value['prefill_all_models_all_cases_valid'] is True
    assert value['results']['base']['original']['valid']==4
    assert value['results']['pilot_adapter']['assistant_prefill']['valid']==4
    assert value['belief_accuracy_evaluated'] is False
