import json
import pytest
from scripts.freeze_statistical_reference import quality, write_exclusive, build
from pathlib import Path


def rows():
    return ([{'group_id': 'private-group', 'profile': {'agent_id': 'private-agent', 'topic': 'private-topic', 'initial_score': 2, 'initial_text': 'private-text'}}], [{'group_id': 'private-group', 'agent_id': 'private-agent', 'final_score': 3}])


def test_aggregate_only():
    result = quality(*rows())
    assert result['changed_count'] == 1
    assert result['per_initial_support']['2'] == 1
    assert 'private-' not in json.dumps(result)


@pytest.mark.parametrize('change', ['duplicate', 'unmatched', 'range', 'boolean', 'missing'])
def test_reject_invalid(change):
    cases, targets = rows()
    if change == 'duplicate': cases.append(cases[0])
    if change == 'unmatched': targets[0]['agent_id'] = 'different'
    if change == 'range': targets[0]['final_score'] = 7
    if change == 'boolean': targets[0]['final_score'] = True
    if change == 'missing': cases[0]['profile'].pop('initial_score')
    with pytest.raises(ValueError): quality(cases, targets)


def test_exclusive(tmp_path):
    path = tmp_path / 'report.json'
    write_exclusive(path, {'ok': True})
    with pytest.raises(FileExistsError): write_exclusive(path, {'ok': False})
    assert json.loads(path.read_text()) == {'ok': True}


def test_existing_reference_selective_access(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    original = Path.read_bytes
    original_text = Path.read_text
    def allowed(path):
        assert path.name not in ('targets.json', 'train.jsonl')
        assert path.suffix != '.csv'
    def guarded_bytes(path, *args, **kwargs):
        allowed(path)
        return original(path, *args, **kwargs)
    def guarded_text(path, *args, **kwargs):
        allowed(path)
        return original_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_bytes', guarded_bytes)
    monkeypatch.setattr(Path, 'read_text', guarded_text)
    manifest, report = build(root)
    assert manifest['baseline']['fit_people'] == report['cases'] == 92
    assert manifest['baseline_refitted'] is False
