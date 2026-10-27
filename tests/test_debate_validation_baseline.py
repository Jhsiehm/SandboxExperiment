import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('validation_baseline', Path(__file__).parents[1] / 'scripts/prepare_debate_validation_baseline.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def setup(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    inputs = source / 'inputs'
    inputs.mkdir(parents=True)
    csv_text = 'event_type,worker_id\nInitial Opinion,opaque\n'
    (inputs / 't.csv').write_text(csv_text)
    groups = [dict(group_id='t', partition='train', topic='train', sha256=module.sha(inputs / 't.csv')),
              dict(group_id='v', partition='validation', topic='validation', sha256='not-opened')]
    (inputs / 'manifest.json').write_text(json.dumps({'groups': groups}))
    (source / 'preparation-audit.json').write_text(json.dumps({'per_group': {'t': 1, 'v': 1}}))
    audit = tmp_path / 'audit.json'
    ids = ['t', 'v']
    audit.write_text(json.dumps({'manifest_sha256': module.sha(inputs / 'manifest.json'), 'admitted_group_ids': ids,
        'admitted_group_ids_sha256': hashlib.sha256(json.dumps(ids, separators=(',', ':')).encode()).hexdigest(),
        'prepared': {'train_vs_validation': dict(participant_overlap=0, group_overlap=0, topic_overlap=0)}}))
    monkeypatch.setattr(module, 'parse_group', lambda rows, topic, gid: ([{'profile': {'agent_id': 'a', 'initial_score': 1}}], [{'agent_id': 'a', 'final_score': 2}]))
    return source, audit


def test_training_only_laplace_fit(tmp_path, monkeypatch):
    source, audit = setup(tmp_path, monkeypatch)
    out = tmp_path / 'baseline.json'
    summary = module.prepare_baseline(source, audit, out, expected_groups=1)
    result = json.loads(out.read_text())
    assert summary['training_people'] == 1
    assert result['counts'][0] == [1, 2, 1, 1, 1, 1]
    assert result['probabilities'][0][1] == 2 / 7
    assert result['probabilities'][1] == [1 / 6] * 6
    assert result['validation_targets_loaded'] == result['validation_csvs_loaded'] == 0


def test_overlap_rejected(tmp_path, monkeypatch):
    source, audit = setup(tmp_path, monkeypatch)
    report = json.loads(audit.read_text())
    report['prepared']['train_vs_validation']['participant_overlap'] = 1
    audit.write_text(json.dumps(report))
    with pytest.raises(ValueError, match='integrity'):
        module.prepare_baseline(source, audit, tmp_path / 'out.json', expected_groups=1)


def test_changed_training_source_rejected(tmp_path, monkeypatch):
    source, audit = setup(tmp_path, monkeypatch)
    (source / 'inputs/t.csv').write_text('changed')
    with pytest.raises(ValueError, match='checksum'):
        module.prepare_baseline(source, audit, tmp_path / 'out.json', expected_groups=1)
