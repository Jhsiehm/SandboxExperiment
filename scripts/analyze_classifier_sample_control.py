"""Post-hoc inferred-sample Laplace control; never replaces the frozen baseline."""
import argparse
import json
from pathlib import Path

from analyze_classifier_errors import jsonl, read, require, rps, sha


def analyze(root, audit_path, output):
    root, audit_path, output = Path(root).resolve(), Path(audit_path).resolve(), Path(output).resolve()
    seal_path = root / 'internal-prediction-seal.json'
    evaluation = read(root / 'internal-evaluation.json')
    require(evaluation['status'] == 'completed' and evaluation['prediction_seal_sha256'] == sha(seal_path), 'Internal evaluation mismatch')
    seal = read(seal_path)
    for path, expected in seal['bindings'].items():
        require(sha(path) == expected, 'Sealed source mismatch')
    target_path = Path(seal['target_path'])
    require(sha(target_path) == seal['targets_sha256'], 'Internal targets mismatch')
    data = target_path.parent.parent
    manifest = read(data / 'manifest.json')
    train_path, cases_path, token_path = data / 'train.jsonl', data / 'holdout-cases.json', root / 'fit-tokens.json'
    require(sha(train_path) == manifest['train_sha256'] and sha(cases_path) == manifest['holdout_cases_sha256'], 'Prepared data mismatch')
    contract = read(root / 'contract.json')
    require(contract['train_bindings'][str(token_path)] == sha(token_path), 'Fit token binding mismatch')
    audit = read(audit_path)
    require(audit['contract_sha256'] == sha(root / 'contract.json'), 'Sampling audit contract mismatch')
    selected = audit['sampling']['selected_row_indices']
    fit, tokens = jsonl(train_path), read(token_path)
    require(len(fit) == len(tokens) == 92 and len(selected) == len(set(selected)) == 52, 'Unexpected sampling coverage')
    for row, encoded in zip(fit, tokens):
        require((row['group_id'], row['profile']['agent_id'], row['target_score'] - 1) ==
                (encoded['group'], encoded['agent'], encoded['target_class']), 'Fit row ordering mismatch')
    counts = [[1] * 6 for _ in range(6)]
    for index in selected:
        require(type(index) is int and 0 <= index < len(fit), 'Invalid sampled index')
        row = fit[index]
        counts[row['profile']['initial_score'] - 1][row['target_score'] - 1] += 1
    matrix = [[n / sum(row) for n in row] for row in counts]
    full = read(root / 'baseline.json')['probabilities']
    cases = read(cases_path)
    truth = {(r['group_id'], r['agent_id']): r['final_score'] for r in read(target_path)}
    require(len(cases) == len(truth) == 24, 'Unexpected internal coverage')
    rows = []
    for case in cases:
        initial = case['profile']['initial_score']
        final = truth[case['group_id'], case['profile']['agent_id']]
        rows.append({'group': case['group_id'], 'sampled_rps': rps(matrix[initial - 1], final), 'full_rps': rps(full[initial - 1], final)})
    group_scores = {g: {name: sum(r[name] for r in rows if r['group'] == g) / sum(r['group'] == g for r in rows)
                       for name in ('sampled_rps', 'full_rps')} for g in sorted({r['group'] for r in rows})}
    sampled_rps = sum(v['sampled_rps'] for v in group_scores.values()) / len(group_scores)
    full_rps = sum(v['full_rps'] for v in group_scores.values()) / len(group_scores)
    require(abs(full_rps - evaluation['arms']['transition']['rps']) < 1e-12, 'Full baseline reproduction failed')
    result = {'scope': 'POSTHOC inferred-sample control; not a frozen baseline or new confirmation',
        'sample_status': audit['sampling']['status'], 'sampled_fit_people': 52, 'full_fit_people': 92, 'internal_people': 24,
        'method': 'Same fixed Laplace-one P(final|initial) using reconstructed52 unique consumed rows',
        'sampled_counts_with_pseudocount': counts, 'sampled_probabilities': matrix,
        'sampled_transition_rps': sampled_rps, 'full_transition_rps': full_rps, 'sampled_minus_full_rps': sampled_rps - full_rps,
        'base_rps': evaluation['arms']['base']['rps'], 'candidate_rps': evaluation['arms']['pilot_classifier']['rps'],
        'candidate_minus_sampled_transition_rps': evaluation['arms']['pilot_classifier']['rps'] - sampled_rps,
        'per_group': group_scores,
        'limitations': ['Sampling reconstructed from seed and pinned iterator, not logged row IDs.', 'This control is chosen after observing internal outcomes.', 'Equal sample access does not equal optimizer convergence or model capacity.', 'Small six-group cohort; no outer-validation or reserve data used.'],
        'source_bindings': {str(p): sha(p) for p in [Path(__file__).resolve(), Path(__file__).with_name('analyze_classifier_errors.py'), audit_path, seal_path, train_path, token_path, root / 'internal-evaluation.json']}}
    output.mkdir(parents=True, exist_ok=False)
    (output / 'aggregate.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return {k: result[k] for k in ('sampled_transition_rps', 'full_transition_rps', 'sampled_minus_full_rps', 'candidate_minus_sampled_transition_rps')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--sampling-audit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(analyze(args.run, args.sampling_audit, args.output)))
