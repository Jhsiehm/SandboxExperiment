"""Fail-closed evaluator for the frozen development comparison; no model imports."""
import argparse
import hashlib
import json
import math
from pathlib import Path

ARMS = ('base', 'pilot_adapter')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def verify_bindings(bindings):
    for path, expected in bindings.items():
        require(sha(path) == expected, 'Binding mismatch: ' + path)


def contract_at(root):
    path = root / 'contract.json'
    contract = read(path)
    require(contract['status'] == 'frozen_development_comparison', 'Contract is not frozen')
    verify_bindings(contract['bindings'])
    return contract, sha(path)


def verify_watchdog(root, stage, arm):
    suffix = 'adapter' if stage == 'nll' and arm == 'pilot_adapter' else arm
    path = root / f'watchdog-{stage}-{suffix}' / 'summary.json'
    report = read(path)
    require(report['exit_code'] == 0 and report['child_returncode'] == 0 and
            report['stop_reason'] is None and report.get('error') is None,
            'Supervisor did not complete successfully')
    return path


def nll_report(root):
    root = Path(root).resolve()
    contract, contract_hash = contract_at(root)
    expected_groups = read(contract['validation_groups_path'])
    require(len(expected_groups) == 133, 'Expected 133 validation rows')
    all_rows, results, bound_sources = {}, {}, [root / 'contract.json', Path(__file__).resolve()]
    for arm in ARMS:
        bound_sources.append(verify_watchdog(root, 'nll', arm))
        path = root / arm / 'scores.jsonl'
        summary = read(path.parent / 'summary.json')
        bound_sources.extend([path, path.parent / 'summary.json'])
        require(summary['status'] == 'completed' and summary['arm'] == arm and
                summary['contract_sha256'] == contract_hash and summary['scores_sha256'] == sha(path),
                'Incomplete or unbound NLL arm')
        data = rows(path)
        require(len(data) == 133 and summary['examples'] == 133, 'Incomplete NLL coverage')
        require([r['index'] for r in data] == list(range(133)), 'NLL indices missing or duplicated')
        require([r['group'] for r in data] == expected_groups, 'NLL group mismatch')
        for r in data:
            require(type(r['supervised_tokens']) is int and r['supervised_tokens'] > 0,
                    'Invalid supervised token count')
            require(math.isfinite(r['completion_nll_sum']) and r['completion_nll_sum'] >= 0,
                    'Invalid completion loss')
            require(math.isclose(r['nll'], r['completion_nll_sum'] / r['supervised_tokens'],
                                 rel_tol=1e-10, abs_tol=1e-10), 'Inconsistent per-message loss')
        groups = {g: sum(r['nll'] for r in data if r['group'] == g) /
                     sum(r['group'] == g for r in data) for g in sorted(set(expected_groups))}
        results[arm] = dict(token_weighted_nll=sum(r['completion_nll_sum'] for r in data) /
                           sum(r['supervised_tokens'] for r in data),
                           equal_group_message_mean_nll=sum(groups.values()) / len(groups),
                           mean_message_nll=sum(r['nll'] for r in data) / len(data), groups=groups)
        all_rows[arm] = data
    require([r['supervised_tokens'] for r in all_rows['base']] ==
            [r['supervised_tokens'] for r in all_rows['pilot_adapter']], 'Paired token counts differ')
    result = dict(status='completed', scope='development message prediction only', examples=133,
                  supervised_tokens=sum(r['supervised_tokens'] for r in all_rows['base']), arms=results,
                  adapter_minus_base={k: results['pilot_adapter'][k] - results['base'][k]
                                     for k in ('token_weighted_nll', 'equal_group_message_mean_nll', 'mean_message_nll')},
                  paired_group_differences={g: results['pilot_adapter']['groups'][g] - results['base']['groups'][g]
                                            for g in results['base']['groups']},
                  limitation='Message loss does not establish belief accuracy or confirmation.',
                  contract_sha256=contract_hash, evaluator_sha256=sha(__file__),
                  source_bindings={str(p): sha(p) for p in bound_sources})
    write_new(root / 'message-evaluation.json', result)
    return result


def probabilities(p):
    require(isinstance(p, list) and len(p) == 6, 'Expected six probabilities')
    require(all(type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 1 for x in p),
            'Invalid probability')
    require(abs(sum(p) - 1) <= 1e-6, 'Invalid probability sum')
    return p


def direct_inputs(root, contract, contract_hash):
    cases = read(contract['cases_path'])
    identities = [(c['group_id'], c['profile']['agent_id']) for c in cases]
    require(len(cases) == len(set(identities)) == 16, 'Expected 16 unique cases')
    require(len({g for g, _ in identities}) == 4, 'Expected four groups')
    predictions, paths = {}, []
    for arm in ARMS:
        watchdog_path = verify_watchdog(root, 'direct', arm)
        path = root / ('direct-' + arm) / 'predictions.jsonl'
        summary_path = path.parent / 'summary.json'
        summary = read(summary_path)
        require(summary['status'] == 'completed' and summary['completed'] == summary['valid'] == 16,
                'Direct stage incomplete; targets must remain unread')
        require(summary['contract_sha256'] == contract_hash and
                summary['predictions_sha256'] == sha(path), 'Unbound direct predictions')
        data = rows(path)
        require(len(data) == 16 and [(r['group'], r['agent']) for r in data] == identities,
                'Direct identity or coverage mismatch')
        for row in data:
            require(row['status'] == 'valid' and row['arm'] == arm, 'Invalid direct record')
            p = probabilities(row['probabilities'])
            raw = json.loads(row['raw'])
            require(isinstance(raw, dict) and set(raw) == {'probabilities'} and
                    probabilities(raw['probabilities']) == p, 'Raw prediction mismatch')
        predictions[arm] = data
        paths.extend([path, summary_path, watchdog_path])
    for base, adapted in zip(predictions['base'], predictions['pilot_adapter']):
        require(base['prompt'] == adapted['prompt'] and
                type(base['prompt_tokens']) is int and base['prompt_tokens'] > 0 and
                base['prompt_tokens'] == adapted['prompt_tokens'], 'Paired prompts differ')
    return cases, predictions, paths


def individual_metrics(p, initial, final):
    cumulative = 0.0
    squared = []
    for k in range(1, 6):
        cumulative += p[k - 1]
        squared.append((cumulative - int(final <= k)) ** 2)
    expectation = sum((i + 1) * x for i, x in enumerate(p))
    return dict(rps=sum(squared) / 5,
                change_brier=(1 - p[initial - 1] - int(final != initial)) ** 2,
                expected_category_mae=abs(expectation - final))


def belief_report(root):
    root = Path(root).resolve()
    contract, contract_hash = contract_at(root)
    # Admission must finish before opening or hashing any evaluator target file.
    cases, predictions, prediction_paths = direct_inputs(root, contract, contract_hash)
    message_report_path = root / 'message-evaluation.json'
    message_report = read(message_report_path)
    require(message_report['status'] == 'completed' and message_report['examples'] == 133 and
            message_report['contract_sha256'] == contract_hash, 'Stage A must complete first')
    verify_bindings(message_report['source_bindings'])
    prediction_paths.append(message_report_path)
    manifest_path = Path(contract['cases_path']).parent / 'manifest.json'
    require(str(manifest_path) in contract['bindings'], 'Case manifest must be frozen')
    metadata = read(manifest_path)
    baseline_path = root / 'baseline.json'
    baseline_seal_path = root / 'baseline-provenance-seal.json'
    baseline_seal = read(baseline_seal_path)
    require(baseline_seal['frozen_contract_sha256'] == contract_hash, 'Baseline contract mismatch')
    require(str(baseline_path) in baseline_seal['bindings'], 'Baseline not sealed')
    verify_bindings(baseline_seal['bindings'])
    baseline = read(baseline_path)
    matrix = baseline['probabilities']
    require(len(matrix) == 6, 'Invalid baseline shape')
    for p in matrix:
        probabilities(p)
    target_path = manifest_path.parent / 'evaluator/targets.json'
    seal_path = root / 'belief-prediction-seal.json'
    seal = dict(scope='Complete B1 predictions before development outcome scoring',
                bindings={str(p): sha(p) for p in [root / 'contract.json', Path(__file__).resolve(),
                    Path(contract['cases_path']), manifest_path, baseline_path, baseline_seal_path, *prediction_paths]},
                targets_path=str(target_path), targets_sha256=metadata['targets_sha256'])
    if seal_path.exists():
        require(read(seal_path) == seal, 'Existing prediction seal differs')
    else:
        write_new(seal_path, seal)
    verify_bindings(seal['bindings'])
    # First target access, only after complete predictions/baseline/evaluator are sealed.
    require(sha(target_path) == seal['targets_sha256'], 'Target hash mismatch')
    targets = read(target_path)
    truth = {(r['group_id'], r['agent_id']): r['final_score'] for r in targets}
    identities = [(c['group_id'], c['profile']['agent_id']) for c in cases]
    require(len(targets) == len(truth) == 16 and set(truth) == set(identities), 'Target identity mismatch')
    require(all(type(x) is int and 1 <= x <= 6 for x in truth.values()), 'Invalid targets')
    reports = {}
    for arm in (*ARMS, 'persistence', 'transition'):
        scored = []
        for i, case in enumerate(cases):
            initial = case['profile']['initial_score']
            require(type(initial) is int and 1 <= initial <= 6, 'Invalid initial state')
            p = ([float(k == initial) for k in range(1, 7)] if arm == 'persistence' else
                 matrix[initial - 1] if arm == 'transition' else predictions[arm][i]['probabilities'])
            scored.append(dict(group=case['group_id'], expected_category=sum((k + 1) * v for k, v in enumerate(p)),
                               **individual_metrics(p, initial, truth[identities[i]])))
        group_scores = {g: {metric: sum(r[metric] for r in scored if r['group'] == g) /
                                    sum(r['group'] == g for r in scored)
                            for metric in ('rps', 'change_brier', 'expected_category_mae')}
                        for g in sorted({r['group'] for r in scored})}
        pairwise = {}
        for g in group_scores:
            expected = [r['expected_category'] for r in scored if r['group'] == g]
            differences = [abs(x - y) for i, x in enumerate(expected) for y in expected[i + 1:]]
            pairwise[g] = sum(differences) / len(differences)
        reports[arm] = dict(groups=group_scores, group_mean_pairwise_expected_category_distance=pairwise,
                            pairwise_warning='Distances between expectations are not observed response variance.', **{metric: sum(v[metric] for v in group_scores.values()) / len(group_scores)
                            for metric in ('rps', 'change_brier', 'expected_category_mae')})
    delta = reports['pilot_adapter']['rps'] - reports['base']['rps']
    group_deltas = {g: reports['pilot_adapter']['groups'][g]['rps'] - reports['base']['groups'][g]['rps']
                    for g in reports['base']['groups']}
    result = dict(status='completed', scope='four-group development diagnostic; no powered confirmation',
                  people=16, arms=reports, adapter_minus_base_rps=delta, paired_group_differences=group_deltas,
                  engineering_gates=dict(B2_numerical_entry_guard=delta <= .02,
                    B2_requires_review='Review all group outcomes without tuning before deciding to proceed.',
                    individual_signal=delta <= -.02 and reports['pilot_adapter']['rps'] <=
                                      min(reports[a]['rps'] for a in ('persistence', 'transition')) and
                                      max(group_deltas.values()) <= .05 and
                                      reports['pilot_adapter']['change_brier'] - reports['base']['change_brier'] <= .02),
                  prediction_seal_sha256=sha(seal_path), targets_sha256=sha(target_path))
    write_new(root / 'belief-evaluation.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('nll', 'beliefs'))
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps((nll_report if args.phase == 'nll' else belief_report)(args.run), indent=2))
