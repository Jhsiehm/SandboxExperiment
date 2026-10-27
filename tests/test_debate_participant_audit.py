import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('participant_audit', Path(__file__).parents[1] / 'scripts/audit_debate_participants.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(tmp_path, partition='validation'):
    groups = []
    for gid, part, ids in [('a', 'train', ['person1', 'person2']), ('b', partition, ['person2', 'person3'])]:
        content = 'worker_id,event_type,text\n' + ''.join(f'{p},Initial Opinion,unused\n' for p in ids)
        content += f'{ids[0]},Message,not a new participant\n'
        (tmp_path / f'{gid}.csv').write_text(content)
        groups.append(dict(group_id=gid, partition=part, topic=gid, sha256=hashlib.sha256(content.encode()).hexdigest()))
    (tmp_path / 'manifest.json').write_text(json.dumps({'groups': groups}))
    return tmp_path


def test_overlap_counts_memberships_and_redacts_ids(tmp_path):
    result = module.audit(fixture(tmp_path), {'a': 2, 'b': 2}, ['a'])
    assert result['prepared']['train_vs_validation']['participant_overlap'] == 1
    assert result['prepared']['all']['participant_memberships'] == 4
    assert result['prepared']['all']['participants_in_multiple_groups'] == 1
    assert result['prepared']['train_vs_validation']['topic_overlap'] == 0
    assert 'person2' not in json.dumps(result)
    assert result['selected_development_vs_sft_train']['group_overlap'] == 1


def test_rejected_group_excluded_from_prepared(tmp_path):
    result = module.audit(fixture(tmp_path), {'a': 2})
    assert result['downloaded']['train_vs_validation']['participant_overlap'] == 1
    assert result['prepared']['train_vs_validation']['participant_overlap'] == 0


def test_rejects_non_development_partition(tmp_path):
    with pytest.raises(ValueError, match='Only development'):
        module.audit(fixture(tmp_path, 'evaluation'), {'a': 2})


def test_rejects_changed_input(tmp_path):
    fixture(tmp_path)
    (tmp_path / 'a.csv').write_text('changed')
    with pytest.raises(ValueError, match='checksum'):
        module.audit(tmp_path, {'a': 2})


def test_admission_binding_changes_with_set(tmp_path):
    fixture(tmp_path)
    first = module.audit(tmp_path, {'a': 2})
    second = module.audit(tmp_path, {'a': 2, 'b': 2})
    assert first['admitted_group_ids'] == ['a']
    assert second['admitted_group_ids'] == ['a', 'b']
    assert first['admitted_group_ids_sha256'] != second['admitted_group_ids_sha256']
