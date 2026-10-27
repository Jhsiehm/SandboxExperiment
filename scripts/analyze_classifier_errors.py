"""Reproduce aggregate diagnostics for already-scored internal classifier outcomes.

No text or person-level records are emitted. No new model or fitting operations.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

ARMS = ('base', 'pilot_classifier', 'persistence', 'transition')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def jsonl(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines()]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def rps(p, target):
    return sum((sum(p[:k]) - int(target <= k)) ** 2 for k in range(1, 6)) / 5


def histogram(values):
    return [sum(v == k for v in values) for k in range(1, 7)]


def cohort(rows):
    n = len(rows)
    return {'people': n, 'groups': len({r['group'] for r in rows}),
            'initial_counts': histogram([r['initial'] for r in rows]),
            'final_counts': histogram([r['final'] for r in rows]),
            'changed': sum(r['initial'] != r['final'] for r in rows),
            'change_rate': sum(r['initial'] != r['final'] for r in rows) / n,
            'initial_mean': sum(r['initial'] for r in rows) / n,
            'final_mean': sum(r['final'] for r in rows) / n,
            'mean_absolute_change': sum(abs(r['final'] - r['initial']) for r in rows) / n}


def summarize(rows):
    if not rows:
        return {'people': 0, 'arms': {}}
    n = len(rows)
    result = cohort(rows)
    result['arms'] = {}
    for arm in ARMS:
        probabilities = [r['probabilities'][arm] for r in rows]
        expected = [sum((k + 1) * p[k] for k in range(6)) for p in probabilities]
        losses = [rps(p, r['final']) for p, r in zip(probabilities, rows)]
        result['arms'][arm] = {'rps': sum(losses) / n,
            'change_brier': sum((1 - p[r['initial'] - 1] - int(r['initial'] != r['final'])) ** 2 for p, r in zip(probabilities, rows)) / n,
            'predicted_change_rate': sum(1 - p[r['initial'] - 1] for p, r in zip(probabilities, rows)) / n,
            'mean_predicted_category': sum(expected) / n,
            'predicted_category_min': min(expected), 'predicted_category_max': max(expected),
            'predicted_category_std': math.sqrt(sum((e - sum(expected) / n) ** 2 for e in expected) / n),
            'signed_expected_category_error': sum(e - r['final'] for e, r in zip(expected, rows)) / n,
            'expected_category_mae': sum(abs(e - r['final']) for e, r in zip(expected, rows)) / n,
            'mean_category_probabilities': [sum(p[k] for p in probabilities) / n for k in range(6)],
            'argmax_category_counts': histogram([max(range(6), key=lambda k: p[k]) + 1 for p in probabilities]),
            'mean_max_probability': sum(max(p) for p in probabilities) / n,
            'mean_entropy_nats': sum(-sum(x * math.log(x) for x in p if x > 0) for p in probabilities) / n}
    result['candidate_minus_transition_rps'] = result['arms']['pilot_classifier']['rps'] - result['arms']['transition']['rps']
    result['candidate_minus_base_rps'] = result['arms']['pilot_classifier']['rps'] - result['arms']['base']['rps']
    return result


def analyze(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    evaluated = read(root / 'internal-evaluation.json')
    require(evaluated['status'] == 'completed', 'Internal outcomes not previously scored')
    seal_path = root / 'internal-prediction-seal.json'
    require(evaluated['prediction_seal_sha256'] == sha(seal_path), 'Evaluation seal mismatch')
    seal = read(seal_path)
    for path, expected in seal['bindings'].items():
        require(sha(path) == expected, 'Prediction binding mismatch')
    target_path = Path(seal['target_path'])
    require(sha(target_path) == seal['targets_sha256'], 'Target hash mismatch')
    targets = read(target_path)
    data = target_path.parent.parent
    manifest = read(data / 'manifest.json')
    train_path, cases_path = data / 'train.jsonl', data / 'holdout-cases.json'
    require(sha(train_path) == manifest['train_sha256'] and sha(cases_path) == manifest['holdout_cases_sha256'], 'Data mismatch')
    cases = read(cases_path)
    truth = {(r['group_id'], r['agent_id']): r['final_score'] for r in targets}
    preds = {a: jsonl(root / 'internal' / a / 'predictions.jsonl') for a in ARMS[:2]}
    expected = [(c['group_id'], c['profile']['agent_id']) for c in cases]
    require(len(expected) == len(truth) == 24 and set(expected) == set(truth), 'Internal coverage mismatch')
    for a in preds:
        require([(r['group_id'], r['agent_id']) for r in preds[a]] == expected, 'Prediction identity mismatch')
    matrix = read(root / 'baseline.json')['probabilities']
    scored = []
    for i, case in enumerate(cases):
        initial, final = case['profile']['initial_score'], truth[expected[i]]
        scored.append({'group': case['group_id'], 'initial': initial, 'final': final,
            'probabilities': {**{a: preds[a][i]['probabilities'] for a in preds},
                'persistence': [int(k == initial) for k in range(1, 7)], 'transition': matrix[initial - 1]}})
    fit = [{'group': r['group_id'], 'initial': r['profile']['initial_score'], 'final': r['target_score']} for r in jsonl(train_path)]
    overall = summarize(scored)
    require(all(abs(overall['arms'][a]['rps'] - evaluated['arms'][a]['rps']) < 1e-12 for a in ARMS), 'RPS does not reproduce sealed evaluation')
    by_change = {state: summarize([r for r in scored if (r['initial'] != r['final']) == changed]) for state, changed in [('changed', True), ('unchanged', False)]}
    for summary in by_change.values():
        summary['weighted_contribution_candidate_minus_transition_rps'] = summary['people'] / len(scored) * summary['candidate_minus_transition_rps']
    require(abs(sum(s['weighted_contribution_candidate_minus_transition_rps'] for s in by_change.values()) - overall['candidate_minus_transition_rps']) < 1e-12, 'Change decomposition mismatch')
    result = {'schema_version': 1, 'scope': 'Post-hoc descriptive decomposition of already-scored internal24 and fit92 only',
        'overall': overall, 'fit_cohort': cohort(fit), 'by_change': by_change,
        'by_initial_category': {str(k): summarize([r for r in scored if r['initial'] == k]) for k in range(1, 7)},
        'fit_by_initial_category': {str(k): cohort([r for r in fit if r['initial'] == k]) if any(r['initial'] == k for r in fit) else {'people': 0} for k in range(1, 7)},
        'by_group': {g: summarize([r for r in scored if r['group'] == g]) for g in sorted({r['group'] for r in scored})},
        'limitations': ['Small cells and six groups; no inferential or causal interpretation.', 'Fit92 is available supervision; actual52-step exposure must be audited separately.', 'Restricted-class probabilities are not validated private-belief distributions.', 'No outer-validation or reserve outcomes used.'],
        'source_bindings': {str(p): sha(p) for p in [Path(__file__).resolve(), root / 'internal-evaluation.json', seal_path, train_path, cases_path, data / 'manifest.json', root / 'baseline.json']}}
    output.mkdir(parents=True, exist_ok=False)
    (output / 'aggregate.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return {'people': 24, 'fit_people': len(fit), 'output_path': str(output / 'aggregate.json'), 'sha256': sha(output / 'aggregate.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(analyze(args.run, args.output)))
