import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('calibration_folds', Path(__file__).parents[1] / 'scripts/prepare_residual_calibration_folds.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def records(n=8):
    return [{'group_id': f'g{i}', 'profile': {'agent_id': f'p{i}', 'topic': f't{i}', 'initial_score': i % 6 + 1}, 'target_score': (i+1) % 6 + 1} for i in range(n)]


def test_topics_and_person_components_preserved():
    rows = records()
    rows[1]['profile']['topic'] = rows[0]['profile']['topic']
    rows[2]['profile']['agent_id'] = rows[1]['profile']['agent_id']
    result = m.make_folds(rows, 3)
    component = next(c for c in result['components'] if 'g0' in c['group_ids'])
    assert component['group_ids'] == ['g0', 'g1', 'g2']
    assert sorted(i for f in result['folds'] for i in f['validation_row_indices']) == list(range(8))


def test_labels_and_ratings_do_not_affect_assignment():
    rows = records(12)
    first = m.make_folds(rows)
    for row in rows:
        row['target_score'] = 6
        row['profile']['initial_score'] = 1
    assert m.make_folds(rows) == first


def test_balanced_deterministic_metadata_only_folds():
    result = m.make_folds(records(23))
    assert sorted(f['validation_people'] for f in result['folds']) == [4,4,5,5,5]
    assert result == m.make_folds(records(23))
    assert all(set(f['training_row_indices']).isdisjoint(f['validation_row_indices']) for f in result['folds'])


def test_insufficient_components_fails():
    rows = records(8)
    for row in rows:
        row['profile']['topic'] = 'same'
    with pytest.raises(ValueError, match='Too few'):
        m.make_folds(rows)


def test_duplicate_group_person_fails():
    rows = records()
    rows.append(rows[0])
    with pytest.raises(ValueError, match='Duplicate'):
        m.make_folds(rows)
