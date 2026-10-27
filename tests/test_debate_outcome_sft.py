import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('outcome_sft', REPO / 'scripts/prepare_debate_outcome_sft.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture(tmp_path):
    source = tmp_path / 'source'
    inputs = source / 'inputs'
    inputs.mkdir(parents=True)
    groups = []
    for gid in ('a', 'b', 'c'):
        raw = 'event_type,worker_id,sliderValue,text,event_order\n'
        raw += ''.join(f'Initial Opinion,{gid}{i},1,initial-{gid}-{i},{i}\n' for i in range(4))
        raw += ''.join(f'Post Opinion,{gid}{i},6,FORBIDDEN_POST_TEXT,{i+5}\n' for i in range(4))
        (inputs / f'{gid}.csv').write_text(raw)
        groups.append(dict(group_id=gid, topic=gid, partition='train', sha256=m.sha(inputs / f'{gid}.csv')))
    groups.append(dict(group_id='do-not-open', topic='outer', partition='validation', sha256='missing'))
    (inputs / 'manifest.json').write_text(json.dumps({'groups': groups}))
    admitted = {g['group_id']: 4 for g in groups}
    (source / 'preparation-audit.json').write_text(json.dumps({'per_group': admitted}))
    audit = tmp_path / 'audit.json'
    ids = sorted(admitted)
    audit.write_text(json.dumps({'manifest_sha256': m.sha(inputs / 'manifest.json'), 'admitted_group_ids': ids,
        'admitted_group_ids_sha256': hashlib.sha256(json.dumps(ids, separators=(',', ':')).encode()).hexdigest(),
        'prepared': {'train_vs_validation': dict(participant_overlap=0, group_overlap=0, topic_overlap=0)}}))
    return source, audit


def prepare(source, audit, out):
    return m.prepare(source, audit, out, seed_groups=1, expected_groups=3, expected_training_groups=2,
        expected_holdout_groups=1)


def test_train_only_boundary_and_separate_holdout(tmp_path):
    source, audit = fixture(tmp_path)
    out = tmp_path / 'out'
    summary = prepare(source, audit, out)
    assert summary['training_examples'] == 8 and summary['holdout_people'] == 4
    rows = [json.loads(x) for x in (out / 'train.jsonl').read_text().splitlines()]
    assert all(r['target_score'] == 6 for r in rows)
    assert all('FORBIDDEN_POST_TEXT' not in json.dumps(r['profile']) for r in rows)
    cases = json.loads((out / 'holdout-cases.json').read_text())
    assert 'final_score' not in json.dumps(cases) and 'FORBIDDEN_POST_TEXT' not in json.dumps(cases)
    fit = json.loads((out / 'training-cases.json').read_text())
    assert not {c['group_id'] for c in fit} & {c['group_id'] for c in cases}
    assert len(json.loads((out / 'training-targets.json').read_text())) == 8
    assert (out / 'evaluator/targets.json').stat().st_mode & 0o777 == 0o600
    metadata = json.loads((out / 'manifest.json').read_text())
    assert metadata['validation_csvs_loaded'] == metadata['outer_validation_targets_loaded'] == 0


def test_topic_closure_is_deterministic():
    groups = [dict(group_id=g, topic=g) for g in ('a','b','c','d')]
    seed = min(groups, key=lambda g: hashlib.sha256((m.SPLIT_SALT + g['group_id']).encode()).hexdigest())
    other = next(g for g in groups if g is not seed)
    other['topic'] = seed['topic']
    fit, holdout, seeds = m.topic_closed_split(groups, 1)
    assert len(holdout) == 2 and len(seeds) == 1
    assert not {g['topic'] for g in fit} & {g['topic'] for g in holdout}
    assert m.topic_closed_split(groups, 1) == (fit, holdout, seeds)


def test_stale_admission_rejected(tmp_path):
    source, audit = fixture(tmp_path)
    (source / 'preparation-audit.json').write_text(json.dumps({'per_group': {'a':4}}))
    with pytest.raises(ValueError, match='Stale'):
        prepare(source, audit, tmp_path / 'out')


def test_changed_source_rejected(tmp_path):
    source, audit = fixture(tmp_path)
    (source / 'inputs/a.csv').write_text('changed')
    with pytest.raises(ValueError, match='checksum'):
        prepare(source, audit, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_last_numeric_final_and_no_post_text():
    rows = [dict(event_type='Initial Opinion',worker_id=str(i),sliderValue='1',text='initial',event_order=str(i)) for i in range(4)]
    rows += [dict(event_type='Post Opinion',worker_id=str(i),sliderValue='2',text='secret',event_order=str(i+10)) for i in range(4)]
    rows.append(dict(event_type='Post Opinion',worker_id='0',sliderValue='5',text='secret',event_order='99'))
    result = m.extract(rows, dict(group_id='a',topic='topic'))
    assert result[0][2] == 5 and result[0][3] == 2
    assert all('secret' not in json.dumps(r[1]) for r in result)


def test_final_must_follow_initial():
    rows = [dict(event_type='Initial Opinion', worker_id=str(i), sliderValue='1', text='initial', event_order='50') for i in range(4)]
    rows += [dict(event_type='Post Opinion', worker_id=str(i), sliderValue='2', text='unused', event_order='10') for i in range(4)]
    with pytest.raises(ValueError, match='does not follow'):
        m.extract(rows, dict(group_id='a', topic='topic'))
