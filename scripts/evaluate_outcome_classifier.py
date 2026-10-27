"""Separate target-gated evaluator for a six-choice development classifier."""
import argparse
import hashlib
import json
import math
from pathlib import Path

ARMS = ('base', 'pilot_classifier')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024**2), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(bindings):
    for path, digest in bindings.items():
        require(sha(path) == digest, 'Binding mismatch: ' + path)


def write_new(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')


def probs(p):
    require(isinstance(p, list) and len(p) == 6, 'Expected six probabilities')
    require(all(type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 1 for x in p), 'Invalid probabilities')
    require(abs(sum(p) - 1) <= 1e-6, 'Invalid probability sum')
    return p


def metrics(p, initial, final):
    cumulative = 0.0
    loss = 0.0
    for k in range(1, 6):
        cumulative += p[k - 1]
        loss += (cumulative - int(final <= k)) ** 2
    return dict(rps=loss / 5,
                change_brier=(1 - p[initial - 1] - int(initial != final)) ** 2,
                expected_category_mae=abs(sum((k + 1) * x for k, x in enumerate(p)) - final))


def fit_baseline(train_path, output):
    rows = [json.loads(line) for line in Path(train_path).read_text().splitlines()]
    require(len(rows) == 92 and len({r['group_id'] for r in rows}) == 23, 'Unexpected fitting cohort')
    counts = [[1] * 6 for _ in range(6)]
    for row in rows:
        initial, final = row['profile']['initial_score'], row['target_score']
        require(type(initial) is int and type(final) is int and 1 <= initial <= 6 and 1 <= final <= 6, 'Invalid fit category')
        counts[initial - 1][final - 1] += 1
    result = dict(method='Laplace-one transition fitted on same23groups92people as classifier',
                  counts=counts, probabilities=[[x / sum(row) for x in row] for row in counts],
                  train_sha256=sha(train_path), evaluator_sha256=sha(__file__))
    write_new(output, result)
    return result


def admit_predictions(root, stage, cases, contract_hash):
    expected = [(c['group_id'], c['profile']['agent_id']) for c in cases]
    require(len(expected) == len(set(expected)), 'Duplicate case identity')
    data, sources = {}, []
    for arm in ARMS:
        directory = root / stage / arm
        summary_path, predictions_path = directory / 'summary.json', directory / 'predictions.jsonl'
        watch_path = root / ('watchdog-' + stage + '-' + arm) / 'summary.json'
        watch = read(watch_path)
        require(watch['exit_code'] == watch['child_returncode'] == 0 and watch['stop_reason'] is None and watch.get('error') is None, 'Supervisor did not succeed')
        summary = read(summary_path)
        require(summary['status'] == 'completed' and summary['completed'] == len(cases), 'Incomplete prediction coverage')
        require(summary['contract_sha256'] == contract_hash and summary['predictions_sha256'] == sha(predictions_path), 'Unbound predictions')
        rows = [json.loads(line) for line in predictions_path.read_text().splitlines()]
        require([(r['group_id'], r['agent_id']) for r in rows] == expected, 'Prediction identity/order mismatch')
        for row in rows:
            require(row['arm'] == arm, 'Wrong arm')
            p = probs(row['probabilities'])
            logits = row['logits']
            require(len(logits) == 6 and all(type(x) in (float, int) and math.isfinite(x) for x in logits), 'Invalid logits')
            weights = [math.exp(x - max(logits)) for x in logits]
            require(all(abs(x - w / sum(weights)) < 1e-6 for x, w in zip(p, weights)), 'Probability/logit mismatch')
        data[arm] = rows
        sources.extend((watch_path, summary_path, predictions_path))
    require([r['prompt_sha256'] for r in data['base']] == [r['prompt_sha256'] for r in data['pilot_classifier']], 'Paired prompts differ')
    return data, sources


def evaluate(root, stage, cases_path, metadata_path, target_path):
    require(stage == 'internal', 'This version evaluates the internal stage only')
    root = Path(root).resolve()
    contract_path = root / 'contract.json'
    contract = read(contract_path)
    for key in ('common_bindings', 'train_bindings', 'prediction_bindings'):
        verify(contract[key])
    candidate_path = root / 'candidate-seal.json'
    candidate = read(candidate_path)
    require(candidate['contract_sha256'] == sha(contract_path), 'Candidate contract mismatch')
    verify(candidate['bindings'])
    training_watch_path = root / 'watchdog-train/summary.json'
    training_watch = read(training_watch_path)
    require(training_watch['exit_code'] == training_watch['child_returncode'] == 0 and training_watch['stop_reason'] is None, 'Training supervisor failed')
    cases_path, metadata_path = Path(cases_path).resolve(), Path(metadata_path).resolve()
    metadata = read(metadata_path)
    expected_case_hash = metadata['holdout_cases_sha256'] if stage == 'internal' else metadata['cases_sha256']
    require(sha(cases_path) == expected_case_hash, 'Case hash mismatch')
    require(str(cases_path) in contract['prediction_bindings'] and str(metadata_path) in contract['common_bindings'], 'Unbound case metadata')
    require(str(Path(__file__).resolve()) in contract['common_bindings'], 'Unbound evaluator source')
    cases = read(cases_path)
    require(len(cases) == (24 if stage == 'internal' else 16), 'Unexpected case coverage')
    predictions, paths = admit_predictions(root, stage, cases, sha(contract_path))
    baseline_path = root / 'baseline.json'
    require(str(baseline_path) in contract['common_bindings'], 'Unbound baseline')
    baseline = read(baseline_path)
    require(baseline['train_sha256'] == metadata['train_sha256'] and baseline['evaluator_sha256'] == sha(__file__), 'Baseline fit provenance mismatch')
    for arm in ARMS:
        require(read(root / stage / arm / 'summary.json')['candidate_seal_sha256'] == sha(candidate_path), 'Candidate prediction mismatch')
    matrix = baseline['probabilities']
    require(len(matrix) == 6, 'Invalid baseline shape')
    for p in matrix:
        probs(p)
    # Dataset metadata and candidate seals are added to bindings by the coordinator
    # before execution. No target contents may be opened by this admission step.
    seal_path = root / (stage + '-prediction-seal.json')
    seal = dict(stage=stage, target_path=str(Path(target_path).resolve()), targets_sha256=metadata['targets_sha256'],
                bindings={str(p): sha(p) for p in [contract_path, Path(__file__).resolve(), cases_path,
                    metadata_path, baseline_path, candidate_path, training_watch_path, *paths]})
    write_new(seal_path, seal)
    verify(seal['bindings'])
    # First target access is deliberately after full paired coverage and sealing.
    require(sha(target_path) == seal['targets_sha256'], 'Target hash mismatch')
    targets = read(target_path)
    truth = {(t['group_id'], t['agent_id']): t['final_score'] for t in targets}
    ids = [(c['group_id'], c['profile']['agent_id']) for c in cases]
    require(len(targets) == len(truth) == len(cases) and set(truth) == set(ids), 'Target identity mismatch')
    require(all(type(t) is int and 1 <= t <= 6 for t in truth.values()), 'Invalid target category')
    report = {}
    for arm in (*ARMS, 'persistence', 'transition'):
        rows = []
        for i, case in enumerate(cases):
            initial = case['profile']['initial_score']
            require(type(initial) is int and 1 <= initial <= 6, 'Invalid initial category')
            p = ([float(k == initial) for k in range(1, 7)] if arm == 'persistence' else
                 matrix[initial - 1] if arm == 'transition' else predictions[arm][i]['probabilities'])
            rows.append(dict(group=case['group_id'], **metrics(p, initial, truth[ids[i]])))
        groups = {g: {m: sum(r[m] for r in rows if r['group'] == g) / sum(r['group'] == g for r in rows)
                      for m in ('rps', 'change_brier', 'expected_category_mae')} for g in sorted({r['group'] for r in rows})}
        report[arm] = dict(groups=groups, **{m: sum(v[m] for v in groups.values()) / len(groups)
                                          for m in ('rps', 'change_brier', 'expected_category_mae')})
    delta = report['pilot_classifier']['rps'] - report['base']['rps']
    result = dict(status='completed', stage=stage, people=len(cases), scope='Development six-choice prediction; not calibrated latent beliefs',
                  arms=report, adapter_minus_base_rps=delta,
                  paired_group_differences={g: report['pilot_classifier']['groups'][g]['rps'] - report['base']['groups'][g]['rps'] for g in report['base']['groups']},
                  numerical_nonworsening_gate=delta <= .02, group_review_required=True,
                  limitation='Small development cohort; probabilities are conditional on six declared label tokens. No population/causal/confirmation claim.',
                  prediction_seal_sha256=sha(seal_path))
    write_new(root / (stage + '-evaluation.json'), result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['fit', 'internal'])
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    args = parser.parse_args()
    if args.phase == 'fit':
        result = fit_baseline(args.data / 'train.jsonl', args.run_dir / 'baseline.json')
    else:
        result = evaluate(args.run_dir, args.phase,
            args.data / ('holdout-cases.json' if args.phase == 'internal' else 'cases.json'),
            args.data / 'manifest.json', args.data / 'evaluator/targets.json')
    print(json.dumps(result, indent=2))
