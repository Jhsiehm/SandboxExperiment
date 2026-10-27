"""Retain the existing six-category DEBATE reference without fitting a model."""
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def require(ok, message):
    if not ok:
        raise ValueError(message)


def category(value):
    return type(value) is int and 1 <= value <= 6


def quality(cases, targets):
    require(isinstance(cases, list) and isinstance(targets, list), 'Expected case/target lists')
    case_keys = [(x.get('group_id'), x.get('profile', {}).get('agent_id')) for x in cases]
    target_keys = [(x.get('group_id'), x.get('agent_id')) for x in targets]
    require(all(all(isinstance(v, str) and v for v in k) for k in case_keys + target_keys), 'Missing identities')
    require(len(set(case_keys)) == len(case_keys) and len(set(target_keys)) == len(target_keys), 'Duplicate identities')
    require(set(case_keys) == set(target_keys), 'Unmatched cases/targets')
    finals = {k: x.get('final_score') for k, x in zip(target_keys, targets)}
    initial = [x['profile'].get('initial_score') for x in cases]
    final = [finals[k] for k in case_keys]
    require(all(category(x) for x in initial + final), 'Invalid six-category scores')
    topics = [x['profile'].get('topic') for x in cases]
    require(all(isinstance(t, str) and t.strip() for t in topics), 'Missing topics')
    return {
        'schema_version': 1, 'scope': 'Already admitted fitting partition only; descriptive counts, no model ranking.',
        'cases': len(cases), 'targets': len(targets),
        'unique_people': len({k[1] for k in case_keys}), 'unique_groups': len({k[0] for k in case_keys}),
        'unique_topics': len(set(topics)), 'missing_identity_count': 0,
        'duplicate_case_identity_count': 0, 'duplicate_target_identity_count': 0,
        'missing_initial_score_count': 0, 'missing_final_score_count': 0,
        'out_of_range_score_count': 0, 'missing_topic_count': 0,
        'missing_initial_text_count': sum(not isinstance(x['profile'].get('initial_text'), str) or not x['profile']['initial_text'].strip() for x in cases),
        'initial_counts': {str(i): initial.count(i) for i in range(1, 7)},
        'final_counts': {str(i): final.count(i) for i in range(1, 7)},
        'changed_count': sum(a != b for a, b in zip(initial, final)),
        'unchanged_count': sum(a == b for a, b in zip(initial, final)),
        'per_initial_support': {str(i): initial.count(i) for i in range(1, 7)},
    }


def build(root):
    root = Path(root).resolve()
    original = root / 'data/local-mlx-pilot/outcome-classifier-v1-20261023'
    residual = root / 'data/local-mlx-pilot/residual-calibration-v1-20261023'
    data = root / 'data/local-mlx-pilot/outcome-sft-v1-data'
    baseline_path = original / 'baseline.json'
    seal_path = original / 'internal-prediction-seal.json'
    seal = read(seal_path)
    require(seal['bindings'].get(str(baseline_path)) == sha(baseline_path), 'Baseline differs from original prediction seal')
    metadata_path = data / 'manifest.json'
    metadata = read(metadata_path)
    case_path, target_path = data / 'training-cases.json', data / 'training-targets.json'
    require(sha(case_path) == metadata['training_cases_sha256'], 'Case hash mismatch')
    require(sha(target_path) == metadata['training_targets_sha256'], 'Target hash mismatch')
    report = quality(read(case_path), read(target_path))
    require(report['cases'] == metadata['training_examples'] == 92, 'Unexpected fitting sample count')
    require(report['unique_groups'] == metadata['training_groups'] == 23, 'Unexpected fitting group count')
    require(report['unique_people'] == 92, 'Unexpected participant reuse')
    baseline = read(baseline_path)
    require(baseline['train_sha256'] == metadata['train_sha256'], 'Baseline training provenance mismatch')
    counts, probabilities = baseline['counts'], baseline['probabilities']
    require(len(counts) == len(probabilities) == 6, 'Not a six-category reference')
    for count, probability in zip(counts, probabilities):
        require(len(count) == len(probability) == 6 and all(type(n) is int and n >= 1 for n in count), 'Invalid Laplace counts')
        require(all(isinstance(p, (int, float)) and math.isfinite(p) and abs(p - n / sum(count)) < 1e-12 for n, p in zip(count, probability)), 'Probability/count mismatch')
    require(sum(map(sum, counts)) - 36 == 92, 'Unexpected Laplace sample support')
    require(all(sum(row) - 6 == report['initial_counts'][str(i)] for i, row in enumerate(counts, 1)), 'Baseline support differs from prepared fitting cases')
    evaluation_path = original / 'internal-evaluation.json'
    evaluation = read(evaluation_path)
    require(evaluation['prediction_seal_sha256'] == sha(seal_path), 'Evaluation seal mismatch')
    decision_path = residual / 'decision.json'
    decision = read(decision_path)
    require(evaluation['numerical_nonworsening_gate'] is False, 'Classifier gate status changed')
    require(decision['status'] == 'oof_gate_failed' and decision['internal_readout'] is False and decision['outer_validation'] is False, 'Residual decision changed')
    bindings = [baseline_path, seal_path, evaluation_path, residual / 'oof-evaluation.json', decision_path, metadata_path, case_path, target_path, Path(__file__).resolve()]
    manifest = {
        'schema_version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'frozen_statistical_reference_development_only',
        'baseline': {'path': str(baseline_path), 'sha256': sha(baseline_path), 'method': 'Laplace-one initial-to-final transition table', 'categories': 6, 'fit_groups': 23, 'fit_people': 92},
        'scope': 'DEBATE six-category development reference; not deployment validation or a seven-category ANES model.',
        'failed_candidates': {'outcome_classifier_v1': 'internal_nonworsening_gate_failed', 'residual_calibration_v1': 'oof_gate_failed'},
        'new_candidate_created': False, 'weights_retrained': False, 'baseline_refitted': False,
        'bindings': {str(p): sha(p) for p in bindings},
    }
    return manifest, report


def write_exclusive(path, payload):
    with Path(path).open('x') as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write('\n')
    Path(path).chmod(0o444)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest, report = build(args.root)
    args.output.mkdir(parents=True, exist_ok=False)
    report_path = args.output / 'data-quality.json'
    write_exclusive(report_path, report)
    manifest['data_quality'] = {'path': str(report_path.resolve()), 'sha256': sha(report_path)}
    write_exclusive(args.output / 'manifest.json', manifest)
    print(json.dumps({'status': manifest['status'], 'cases': report['cases'], 'groups': report['unique_groups']}))


if __name__ == '__main__':
    main()
