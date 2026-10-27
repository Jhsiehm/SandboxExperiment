import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('local_cases', Path(__file__).parents[1] / 'scripts/debate_local_cases.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def setup_source(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    inputs = source / 'inputs'
    inputs.mkdir(parents=True)
    raw = 'event_type,worker_id\nInitial Opinion,opaque\n'
    (inputs / 'v.csv').write_text(raw)
    manifest = {'groups': [{'group_id': 'v', 'topic': 'topic', 'partition': 'validation', 'sha256': hashlib.sha256(raw.encode()).hexdigest()},
                           {'group_id': 'never-open', 'topic': 'reserve', 'partition': 'evaluation', 'sha256': 'unavailable'}]}
    (inputs / 'manifest.json').write_text(json.dumps(manifest))
    (source / 'preparation-audit.json').write_text(json.dumps({'per_group': {'v': 2}}))
    audit = tmp_path / 'audit.json'
    audit.write_text(json.dumps({'manifest_sha256': module.sha(inputs / 'manifest.json'), 'admitted_group_ids': ['v'], 'admitted_group_ids_sha256': hashlib.sha256(b'["v"]').hexdigest(), 'prepared': {'train_vs_validation': dict(participant_overlap=0, group_overlap=0, topic_overlap=0)}}))
    def parse(rows, topic, group_id):
        return ([{'group_id': group_id, 'profile': dict(agent_id='vp0', topic=topic, initial_score=1, initial_text='initial', partners={}),
                  'real_incoming': ['PRIVATE_FUTURE']}], [{'group_id': group_id, 'agent_id': 'vp0', 'final_score': 6}])
    monkeypatch.setattr(module, 'parse_group', parse)
    return source, audit


def test_only_allowed_context_and_separate_targets(tmp_path, monkeypatch):
    source, audit = setup_source(tmp_path, monkeypatch)
    result = module.prepare_validation_cases(source, tmp_path / 'out', participant_audit_path=audit, expected_groups=1, expected_people=1)
    cases = Path(result['cases_path']).read_text()
    assert 'PRIVATE_FUTURE' not in cases and 'final_score' not in cases and 'real_incoming' not in cases
    assert 'final_score' not in json.dumps(result)
    assert json.loads(Path(result['targets_path']).read_text())[0]['final_score'] == 6
    assert Path(result['targets_path']).stat().st_mode & 0o777 == 0o600
    assert result['groups'] == result['people'] == 1


def test_checksum_fails_before_parsing(tmp_path, monkeypatch):
    source, audit = setup_source(tmp_path, monkeypatch)
    (source / 'inputs/v.csv').write_text('changed')
    with pytest.raises(ValueError, match='checksum'):
        module.prepare_validation_cases(source, tmp_path / 'out', participant_audit_path=audit, expected_groups=1, expected_people=1)


def test_split_overlap_blocks(tmp_path, monkeypatch):
    source, audit = setup_source(tmp_path, monkeypatch)
    report = json.loads(audit.read_text())
    report['prepared']['train_vs_validation']['participant_overlap'] = 1
    audit.write_text(json.dumps(report))
    with pytest.raises(ValueError, match='integrity'):
        module.prepare_validation_cases(source, tmp_path / 'out', participant_audit_path=audit, expected_groups=1, expected_people=1)


def test_default_count_guard(tmp_path, monkeypatch):
    source, audit = setup_source(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='group count'):
        module.prepare_validation_cases(source, tmp_path / 'out', participant_audit_path=audit)


def test_stale_admitted_set_blocks(tmp_path, monkeypatch):
    source, audit = setup_source(tmp_path, monkeypatch)
    (source / 'preparation-audit.json').write_text(json.dumps({'per_group': {'v': 2, 'newly-admitted': 3}}))
    with pytest.raises(ValueError, match='admitted group set'):
        module.prepare_validation_cases(source, tmp_path / 'out', participant_audit_path=audit, expected_groups=1, expected_people=1)
    assert not (tmp_path / 'out/cases.json').exists()
