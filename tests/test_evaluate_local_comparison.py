import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('local_evaluator', Path(__file__).parents[1] / 'scripts/evaluate_local_comparison.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def jsonl(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r) + '\n' for r in value))


def make_run(tmp_path, nll_done=False):
    cases = [dict(group_id=f'g{i//4}', profile=dict(agent_id=f'p{i}', initial_score=1)) for i in range(16)]
    dump(tmp_path / 'cases/cases.json', cases)
    targets = [dict(group_id=c['group_id'], agent_id=c['profile']['agent_id'], final_score=1) for c in cases]
    target = tmp_path / 'cases/evaluator/targets.json'
    dump(target, targets)
    dump(tmp_path / 'cases/manifest.json', {'targets_sha256': m.sha(target)})
    groups = [f'g{i%4}' for i in range(133)]
    dump(tmp_path / 'groups.json', groups)
    contract = dict(status='frozen_development_comparison', cases_path=str(tmp_path / 'cases/cases.json'),
                    validation_groups_path=str(tmp_path / 'groups.json'), bindings={str(p): m.sha(p) for p in
                    [tmp_path / 'cases/cases.json', tmp_path / 'cases/manifest.json', tmp_path / 'groups.json']})
    dump(tmp_path / 'contract.json', contract)
    ch = m.sha(tmp_path / 'contract.json')
    for arm in m.ARMS:
        for stage in ('nll', 'direct'):
            suffix = 'adapter' if stage == 'nll' and arm == 'pilot_adapter' else arm
            dump(tmp_path / f'watchdog-{stage}-{suffix}/summary.json',
                 dict(exit_code=0, child_returncode=0, stop_reason=None, error=None))
        scores = [dict(index=i, group=g, supervised_tokens=2, completion_nll_sum=2., nll=1.) for i, g in enumerate(groups)]
        path = tmp_path / arm / 'scores.jsonl'
        jsonl(path, scores)
        dump(path.parent / 'summary.json', dict(status='completed', arm=arm, examples=133, contract_sha256=ch, scores_sha256=m.sha(path)))
        predictions = [dict(agent=c['profile']['agent_id'], group=c['group_id'], arm=arm, status='valid',
                       prompt={'system':'fixed','user':'fixed'}, prompt_tokens=12,
                       probabilities=[1,0,0,0,0,0], raw='{"probabilities":[1,0,0,0,0,0]}') for c in cases]
        path = tmp_path / ('direct-' + arm) / 'predictions.jsonl'
        jsonl(path, predictions)
        dump(path.parent / 'summary.json', dict(status='completed', completed=16, valid=16, contract_sha256=ch, predictions_sha256=m.sha(path)))
    baseline = tmp_path / 'baseline.json'
    dump(baseline, dict(probabilities=[[1,0,0,0,0,0] for _ in range(6)]))
    dump(tmp_path / 'baseline-provenance-seal.json', dict(frozen_contract_sha256=ch, bindings={str(baseline): m.sha(baseline)}))
    if nll_done:
        m.nll_report(tmp_path)
    return target


def test_nll_complete_paired_report(tmp_path):
    make_run(tmp_path)
    result = m.nll_report(tmp_path)
    assert result['supervised_tokens'] == 266
    assert result['adapter_minus_base']['token_weighted_nll'] == 0
    assert not (tmp_path / 'belief-evaluation.json').exists()


@pytest.mark.parametrize('change', ['tokens', 'index', 'group', 'short'])
def test_nll_rejects_unpaired_coverage(tmp_path, change):
    make_run(tmp_path)
    path = tmp_path / 'pilot_adapter/scores.jsonl'
    data = m.rows(path)
    if change == 'tokens':
        data[0].update(supervised_tokens=4, completion_nll_sum=4.)
    elif change == 'index':
        data[0]['index'] = 1
    elif change == 'group':
        data[0]['group'] = 'other'
    else:
        data.pop()
    jsonl(path, data)
    summary = m.read(path.parent / 'summary.json')
    summary['scores_sha256'] = m.sha(path)
    dump(path.parent / 'summary.json', summary)
    with pytest.raises(ValueError):
        m.nll_report(tmp_path)
    assert not (tmp_path / 'message-evaluation.json').exists()


def test_belief_seals_before_first_target_access(tmp_path, monkeypatch):
    target = make_run(tmp_path, nll_done=True)
    original_sha = m.sha
    def guarded_sha(path):
        if Path(path) == target:
            assert (tmp_path / 'belief-prediction-seal.json').exists()
        return original_sha(path)
    monkeypatch.setattr(m, 'sha', guarded_sha)
    result = m.belief_report(tmp_path)
    assert result['arms']['base']['rps'] == 0
    assert result['arms']['base']['change_brier'] == 0
    assert result['engineering_gates']['B2_numerical_entry_guard'] is True


def test_incomplete_direct_refuses_before_target_read(tmp_path, monkeypatch):
    target = make_run(tmp_path)
    summary = tmp_path / 'direct-base/summary.json'
    value = m.read(summary)
    value.update(status='stopped', valid=0, completed=1)
    dump(summary, value)
    original_read, original_sha = m.read, m.sha
    def no_target_read(path):
        assert Path(path) != target, 'Target read before gate'
        return original_read(path)
    def no_target_hash(path):
        assert Path(path) != target, 'Target hashed before gate'
        return original_sha(path)
    monkeypatch.setattr(m, 'read', no_target_read)
    monkeypatch.setattr(m, 'sha', no_target_hash)
    with pytest.raises(ValueError, match='incomplete'):
        m.belief_report(tmp_path)
    assert not (tmp_path / 'belief-prediction-seal.json').exists()


def test_baseline_tamper_refuses_before_target_access(tmp_path, monkeypatch):
    target = make_run(tmp_path, nll_done=True)
    (tmp_path / 'baseline.json').write_text('{}')
    original_sha = m.sha
    def no_target_hash(path):
        assert Path(path) != target
        return original_sha(path)
    monkeypatch.setattr(m, 'sha', no_target_hash)
    with pytest.raises(ValueError, match='Binding'):
        m.belief_report(tmp_path)


def test_rps_normalization_and_change_event():
    result = m.individual_metrics([1,0,0,0,0,0], 1, 6)
    assert result == dict(rps=1, change_brier=1, expected_category_mae=5)


@pytest.mark.parametrize('stage', ['nll', 'direct'])
def test_late_watchdog_failure_blocks_report(tmp_path, stage):
    make_run(tmp_path)
    dump(tmp_path / f'watchdog-{stage}-base/summary.json',
         dict(exit_code=124, child_returncode=0, stop_reason='rss_gib'))
    with pytest.raises(ValueError, match='Supervisor'):
        (m.nll_report if stage == 'nll' else m.belief_report)(tmp_path)
    assert not (tmp_path / 'belief-prediction-seal.json').exists()


@pytest.mark.parametrize('change', ['prompt', 'invalid_record'])
def test_invalid_pair_refuses_before_target_read(tmp_path, monkeypatch, change):
    target = make_run(tmp_path)
    path = tmp_path / 'direct-pilot_adapter/predictions.jsonl'
    data = m.rows(path)
    if change == 'prompt':
        data[0]['prompt']['user'] = 'changed'
    else:
        data[0]['status'] = 'invalid_format'
    jsonl(path, data)
    summary = m.read(path.parent / 'summary.json')
    summary['predictions_sha256'] = m.sha(path)
    dump(path.parent / 'summary.json', summary)
    original_sha = m.sha
    def no_target_hash(path):
        assert Path(path) != target
        return original_sha(path)
    monkeypatch.setattr(m, 'sha', no_target_hash)
    with pytest.raises(ValueError):
        m.belief_report(tmp_path)
    assert not (tmp_path / 'belief-prediction-seal.json').exists()
