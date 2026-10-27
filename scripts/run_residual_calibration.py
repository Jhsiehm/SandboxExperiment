"""Frozen cross-fitting and conditional internal readout, without model loading."""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
import numpy as np
import scipy
from residual_calibration_solver import fit, predict, rps_by_group

METHODS = ('transition', 'control', 'extension')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def verify(bindings):
    for p, expected in bindings.items():
        require(sha(p) == expected, 'Binding mismatch: ' + p)


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def validate_logits(records, profiles, prompt_records, class_ids):
    require(len(records) == len(profiles) == len(prompt_records), 'Incomplete model coverage')
    ids = [(c['group_id'], c['profile']['agent_id']) for c in profiles]
    require(len(set(ids)) == len(ids), 'Duplicate profile identities')
    for i, (record, case, prompt) in enumerate(zip(records, profiles, prompt_records)):
        require(record['arm'] == 'base', 'Unexpected model arm')
        require(record['row_index'] == i and (record['group_id'], record['agent_id']) == ids[i], 'Model identity/order mismatch')
        require(record['initial_score'] == case['profile']['initial_score'], 'Initial category mismatch')
        require(record['class_token_ids'] == class_ids, 'Class mapping mismatch')
        require(record['prompt_sha256'] == hashlib.sha256(json.dumps(prompt, sort_keys=True).encode()).hexdigest(), 'Prompt hash mismatch')
        z, p = np.asarray(record['logits'], dtype=float), np.asarray(record['probabilities'], dtype=float)
        require(z.shape == p.shape == (6,) and np.all(np.isfinite(z)) and np.all(np.isfinite(p)), 'Invalid class vector')
        q = np.exp(z - z.max()); q /= q.sum()
        require(np.allclose(p, q, atol=1e-6, rtol=0), 'Softmax mismatch')
    return np.asarray([r['logits'] for r in records], dtype=float)


def validate_folds(folds, profiles):
    n = len(profiles)
    identities = folds['row_identities']
    require(len(identities) == n and len(folds['folds']) == 5, 'Unexpected fold coverage')
    for i, (row, case) in enumerate(zip(identities, profiles)):
        require(row['index'] == i and (row['group_id'], row['agent_id']) == (case['group_id'], case['profile']['agent_id']), 'Fold identity mismatch')
    held = []
    for fold in folds['folds']:
        train, valid = fold['training_row_indices'], fold['validation_row_indices']
        require(len(set(train)) == len(train) and len(set(valid)) == len(valid), 'Duplicated split index')
        require(not set(train) & set(valid) and set(train) | set(valid) == set(range(n)), 'Invalid fold partition')
        require(not {identities[i]['component_id'] for i in train} & {identities[i]['component_id'] for i in valid}, 'Component leakage')
        require(not {profiles[i]['profile']['topic'] for i in train} & {profiles[i]['profile']['topic'] for i in valid}, 'Topic leakage')
        require(not {profiles[i]['profile']['agent_id'] for i in train} & {profiles[i]['profile']['agent_id'] for i in valid}, 'Identity leakage')
        require(all(identities[i]['fold'] == fold['fold'] for i in valid), 'Fold assignment mismatch')
        held.extend(valid)
    require(sorted(held) == list(range(n)), 'Out-of-fold coverage missing or repeated')
    return identities


def progression_gate(group_scores, identities, *, minimum_gain=.01, maximum_harm=.05):
    mean = {method: float(np.mean(list(group_scores[method].values()))) for method in METHODS}
    require(all(math.isfinite(x) for x in mean.values()), 'Nonfinite score')
    components = {}
    for row in identities:
        components.setdefault(row['component_id'], set()).add(row['group_id'])
    effects = {component: {other: float(np.mean([group_scores['extension'][g] - group_scores[other][g] for g in groups]))
                           for other in ('transition', 'control')} for component, groups in components.items()}
    gains = {other: mean[other] - mean['extension'] for other in ('transition', 'control')}
    passed = all(gain >= minimum_gain for gain in gains.values()) and all(delta <= maximum_harm for row in effects.values() for delta in row.values())
    return dict(passed=passed, mean_rps=mean, extension_gain=gains, component_differences=effects,
                minimum_required_gain=minimum_gain, maximum_allowed_component_harm=maximum_harm)


def crossfit_arrays(initial, targets, logits, groups, folds):
    n = len(initial)
    output = {method: np.full((n, 6), np.nan) for method in METHODS}
    models = []
    for fold in folds['folds']:
        tr, va = np.asarray(fold['training_row_indices']), np.asarray(fold['validation_row_indices'])
        control = fit(initial[tr], targets[tr], logits[tr], groups[tr], extension=False)
        extension = fit(initial[tr], targets[tr], logits[tr], groups[tr], extension=True)
        require(np.allclose(control['table'], extension['table'], atol=0, rtol=0), 'Comparator transition tables differ')
        output['transition'][va] = np.asarray(control['table'])[initial[va] - 1]
        output['control'][va] = predict(control, initial[va], logits[va])
        output['extension'][va] = predict(extension, initial[va], logits[va])
        models.append(dict(fold=fold['fold'], training_indices=tr.tolist(), validation_indices=va.tolist(), control=control, extension=extension))
    for p in output.values():
        require(np.all(np.isfinite(p)) and np.all((p >= 0) & (p <= 1)) and np.allclose(p.sum(axis=1), 1, atol=1e-8), 'Incomplete/invalid OOF predictions')
    return output, models


def run(root):
    root = Path(root).resolve()
    cpath = root / 'contract.json'
    c = read(cpath)
    require(c['status'] == 'frozen_residual_calibration_v1', 'Unfrozen calibration')
    verify(c['bindings'])
    require(str(Path(__file__).resolve()) in c['bindings'], 'Unbound orchestrator')
    require(c['analysis_environment'] == dict(python=sys.version, numpy=np.__version__, scipy=scipy.__version__), 'Analysis runtime differs from frozen environment')
    profiles_path, folds_path = Path(c['profiles_path']), Path(c['folds_path'])
    profiles, folds = read(profiles_path), read(folds_path)
    require(len(profiles) == 92 and sha(profiles_path) == folds['source_training_cases_sha256'], 'Fitting profile mismatch')
    identities = validate_folds(folds, profiles)
    prediction_path, summary_path = root / 'base-fit/predictions.jsonl', root / 'base-fit/summary.json'
    summary = read(summary_path)
    watch_path = root / 'watchdog-base-fit/summary.json'
    watch = read(watch_path)
    require(watch['exit_code'] == watch['child_returncode'] == 0 and watch['stop_reason'] is None and watch.get('error') is None, 'Base-logit supervisor failed')
    require(summary['status'] == 'completed' and summary['completed'] == 92 and summary['contract_sha256'] == sha(cpath) and summary['predictions_sha256'] == sha(prediction_path), 'Incomplete/unbound base-logit run')
    logits = validate_logits(rows(prediction_path), profiles, read(c['prompts_path']), c['class_token_ids'])
    # Fitting labels are authorized here; none enter the model process.
    targets_path = Path(folds['source_training_targets_path'])
    require(sha(targets_path) == folds['source_training_targets_sha256'], 'Fitting targets changed')
    target_rows = read(targets_path)
    mapping = {(row['group_id'], row['agent_id']): row['final_score'] for row in target_rows}
    ids = [(p['group_id'], p['profile']['agent_id']) for p in profiles]
    require(len(mapping) == len(target_rows) == 92 and set(mapping) == set(ids), 'Fitting target coverage mismatch')
    require(all(type(p['profile']['initial_score']) is int and 1 <= p['profile']['initial_score'] <= 6 for p in profiles), 'Invalid initial categories')
    require(all(type(value) is int and 1 <= value <= 6 for value in mapping.values()), 'Invalid fitting categories')
    initial = np.array([p['profile']['initial_score'] for p in profiles], dtype=int)
    targets = np.array([mapping[key] for key in ids], dtype=int)
    require(np.all((1 <= initial) & (initial <= 6)) and np.all((1 <= targets) & (targets <= 6)), 'Invalid category')
    groups = np.array([p['group_id'] for p in profiles])
    output, models = crossfit_arrays(initial, targets, logits, groups, folds)
    scores = {method: rps_by_group(p, targets, groups) for method, p in output.items()}
    gate = progression_gate(scores, identities)
    result = dict(status='completed', scope='Training-only cross-fitting; all earlier results preserved', people=92, groups=23,
                  gate=gate, group_rps=scores, fold_models=models,
                  source_bindings={str(path): sha(path) for path in [cpath, prediction_path, summary_path, watch_path, targets_path]},
                  internal_targets_accessed=False, outer_validation_accessed=False)
    write_new(root / 'oof-predictions.json', {method: value.tolist() for method, value in output.items()})
    write_new(root / 'oof-evaluation.json', result)
    if not gate['passed']:
        write_new(root / 'decision.json', dict(status='oof_gate_failed', internal_readout=False, outer_validation=False, reason='Extension failed fixed improvement/component gates; no refit or further tuning.'))
        return result
    # Only a passed OOF gate admits refits and the previously inspected internal cohort.
    final_models = {name: fit(initial, targets, logits, groups, extension=name == 'extension') for name in ('control', 'extension')}
    write_new(root / 'final-calibrators.json', final_models)
    internal_readout(root, c, final_models)
    return result


def internal_readout(root, contract, models):
    prior_root = Path(contract['internal_prior_run'])
    source_root = Path(contract['prepared_data_path'])
    prior_seal_path = prior_root / 'internal-prediction-seal.json'
    prior_seal = read(prior_seal_path)
    verify(prior_seal['bindings'])  # Prior seal contains no target file binding.
    metadata_path = source_root / 'manifest.json'
    metadata = read(metadata_path)
    cases_path, base_path = source_root / 'holdout-cases.json', prior_root / 'internal/base/predictions.jsonl'
    require(sha(cases_path) == metadata['holdout_cases_sha256'], 'Internal profiles changed')
    cases, base = read(cases_path), rows(base_path)
    require(len(cases) == len(base) == 24, 'Incomplete internal cases')
    keys = [(p['group_id'], p['profile']['agent_id']) for p in cases]
    require([(r['group_id'], r['agent_id']) for r in base] == keys, 'Internal order changed')
    require(all(r['class_token_ids'] == contract['class_token_ids'] for r in base), 'Internal class mapping mismatch')
    logits = np.asarray([r['logits'] for r in base], dtype=float)
    initial = np.asarray([c['profile']['initial_score'] for c in cases], dtype=int)
    groups = np.asarray([c['group_id'] for c in cases])
    predictions = dict(transition=np.asarray(models['control']['table'])[initial - 1],
                       **{name: predict(model, initial, logits) for name, model in models.items()})
    output_path = root / 'internal-calibrated-predictions.json'
    write_new(output_path, dict(identities=keys, probabilities={k:v.tolist() for k,v in predictions.items()}))
    target_path = source_root / 'evaluator/targets.json'
    paths = [root/'contract.json', root/'final-calibrators.json', root/'oof-evaluation.json', output_path,
             prior_seal_path, metadata_path, cases_path, base_path]
    seal = dict(bindings={str(p):sha(p) for p in paths}, targets_sha256=metadata['targets_sha256'])
    seal_path = root/'internal-calibration-seal.json'
    write_new(seal_path, seal)
    verify(seal['bindings'])
    # First internal outcome access in this protocol.
    require(sha(target_path) == seal['targets_sha256'], 'Internal targets changed')
    target_rows = read(target_path)
    truth = {(r['group_id'], r['agent_id']):r['final_score'] for r in target_rows}
    require(len(target_rows) == len(truth) == 24 and set(truth) == set(keys), 'Internal target coverage mismatch')
    require(all(type(value) is int and 1 <= value <= 6 for value in truth.values()), 'Invalid internal categories')
    y = np.asarray([truth[k] for k in keys], dtype=int)
    scores = {name:rps_by_group(p, y, groups) for name,p in predictions.items()}
    means = {name:float(np.mean(list(value.values()))) for name,value in scores.items()}
    retained = all(means['extension'] < means[name] for name in ('transition','control'))
    write_new(root/'internal-calibration-evaluation.json', dict(status='completed',scope='Already-exposed development cohort',people=24,
        group_rps=scores,mean_rps=means,direction_retained=retained,seal_sha256=sha(seal_path)))
    write_new(root/'decision.json', dict(status='gates_passed' if retained else 'internal_direction_failed',internal_readout=True,
        outer_validation=False,reason='Consider separate outer validation only after review.' if retained else 'No progression; do not tune on exposed internal outcomes.'))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    args=parser.parse_args()
    try:
        result=run(args.run_dir)
        print(json.dumps(dict(status=result['status'],gate=result['gate']),indent=2))
    except Exception as exc:
        failure=args.run_dir/'calibration-failure.json'
        if not failure.exists():
            write_new(failure,dict(status='failed',error=f'{type(exc).__name__}: {exc}',retry_permitted=False))
        raise
