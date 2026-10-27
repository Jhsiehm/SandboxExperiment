"""Prepare TRAIN-only six-category classification with a topic-disjoint holdout.

Integer labels encode one observed final category, not known human probabilities.
Never reads outer validation CSVs. Runtime owns the frozen A-F class prompt.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

SPLIT_SALT = 'format-sft-v1:'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def category(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if math.isfinite(number) and number.is_integer() and 1 <= number <= 6 else None


def topic_closed_split(groups, seed_groups=5):
    require(0 < seed_groups < len(groups), 'Invalid holdout seed count')
    ranked = sorted(groups, key=lambda g: hashlib.sha256((SPLIT_SALT + g['group_id']).encode()).hexdigest())
    seeds = [g['group_id'] for g in ranked[:seed_groups]]
    topics = {g['topic'] for g in ranked[:seed_groups]}
    heldout = [g for g in groups if g['topic'] in topics]
    training = [g for g in groups if g['topic'] not in topics]
    require(training and heldout, 'Topic closure leaves empty partition')
    return training, heldout, seeds


def extract(rows, group):
    initial = [r for r in rows if r['event_type'] == 'Initial Opinion']
    require(len(initial) == 4 and len({r['worker_id'] for r in initial}) == 4, 'Expected four initial identities')
    output = []
    for i, row in enumerate(initial):
        require(row['worker_id'].strip() and category(row['sliderValue']) is not None and row['text'].strip(), 'Invalid initial state')
        posts = [r for r in rows if r['event_type'] == 'Post Opinion' and r['worker_id'] == row['worker_id'] and category(r['sliderValue']) is not None]
        require(posts, 'Missing numeric final state')
        orders = [float(r['event_order']) for r in posts]
        require(all(math.isfinite(x) for x in orders) and len(set(orders)) == len(orders), 'Ambiguous final event order')
        initial_order = float(row['event_order'])
        require(math.isfinite(initial_order) and max(orders) > initial_order, 'Final event does not follow initial state')
        final = category(max(posts, key=lambda r: float(r['event_order']))['sliderValue'])
        case = {'group_id': group['group_id'], 'profile': {
            'agent_id': f"{group['group_id']}p{i}", 'topic': group['topic'],
            'initial_score': category(row['sliderValue']), 'initial_text': row['text'], 'partners': {}}}
        output.append((row['worker_id'], case, final, len(posts)))
    return output


def prepare(source_root, audit_path, output_root, *, seed_groups=5, expected_groups=29,
            expected_training_groups=23, expected_holdout_groups=6):
    source = Path(source_root).resolve()
    audit_path = Path(audit_path).resolve()
    inputs = source / 'inputs'
    manifest_path, prep_path = inputs / 'manifest.json', source / 'preparation-audit.json'
    manifest = json.loads(manifest_path.read_text())
    admitted = json.loads(prep_path.read_text())['per_group']
    audit = json.loads(audit_path.read_text())
    admitted_ids = sorted(admitted)
    require(audit['manifest_sha256'] == sha(manifest_path) and audit['admitted_group_ids'] == admitted_ids
            and audit['admitted_group_ids_sha256'] == hashlib.sha256(json.dumps(admitted_ids, separators=(',', ':')).encode()).hexdigest(), 'Stale participant audit')
    require(all(audit['prepared']['train_vs_validation'][k] == 0 for k in ('participant_overlap', 'group_overlap', 'topic_overlap')), 'Outer split integrity failure')
    groups = [g for g in manifest['groups'] if g['partition'] == 'train' and g['group_id'] in admitted]
    require(len(groups) == len({g['group_id'] for g in groups}) == expected_groups, 'Unexpected admitted training groups')
    training, holdout, seeds = topic_closed_split(groups, seed_groups)
    require(len(training) == expected_training_groups and len(holdout) == expected_holdout_groups, 'Unexpected frozen split counts')
    train_ids, holdout_ids = {g['group_id'] for g in training}, {g['group_id'] for g in holdout}
    bindings = {str(p): sha(p) for p in [Path(__file__).resolve(), manifest_path, prep_path, audit_path]}
    examples, holdout_cases, targets, train_cases, training_targets, memberships = [], [], [], [], [], {'train': set(), 'holdout': set()}
    provenance = []
    for group in groups:
        path = (inputs / (group['group_id'] + '.csv')).resolve()
        require(path.parent == inputs.resolve() and sha(path) == group['sha256'], 'Source checksum or path mismatch')
        bindings[str(path)] = sha(path)
        with path.open(newline='') as stream:
            records = extract(list(csv.DictReader(stream)), group)
        split = 'train' if group['group_id'] in train_ids else 'holdout'
        for raw_id, case, final, numeric_posts in records:
            memberships[split].add(raw_id)
            if split == 'train':
                examples.append(dict(case, target_score=final))
                train_cases.append(case)
                training_targets.append({'group_id': case['group_id'], 'agent_id': case['profile']['agent_id'], 'final_score': final, 'numeric_post_records': numeric_posts})
            else:
                holdout_cases.append(case)
                targets.append({'group_id': case['group_id'], 'agent_id': case['profile']['agent_id'], 'final_score': final, 'numeric_post_records': numeric_posts})
        provenance.append({'group_id': group['group_id'], 'topic': group['topic'], 'split': split, 'sha256': group['sha256']})
    require(not memberships['train'] & memberships['holdout'], 'Internal participant overlap')
    require(not train_ids & holdout_ids, 'Internal group overlap')
    require(not {g['topic'] for g in training} & {g['topic'] for g in holdout}, 'Internal topic overlap')
    output = Path(output_root).resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    evaluator = output / 'evaluator'
    evaluator.mkdir(mode=0o700)
    (output / 'train.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in examples))
    for path, data in [(output / 'training-cases.json', train_cases), (output / 'training-targets.json', training_targets), (output / 'holdout-cases.json', holdout_cases), (evaluator / 'targets.json', targets)]:
        path.write_text(json.dumps(data, indent=2) + '\n')
    (evaluator / 'targets.json').chmod(0o600)
    metadata = {'schema_version': 1, 'purpose': 'Restricted-six-class observed-final-category classification; no known personal probability distribution',
        'training_schema': {'group_id': 'string', 'profile': 'initial-only profile', 'target_score': 'observed final integer1..6'},
        'class_mapping': {'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6},
        'target_selection_rule': 'Last numeric Post Opinion by finite event_order for that participant, strictly after their finite initial event_order; duplicate numeric-post orders rejected',
        'start_checkpoint_requirement': 'Fresh frozen BASE only; existing pilot adapter exposed all outer training groups',
        'split_rule': 'First five SHA256(format-sft-v1: + group_id) seed groups, then include every admitted TRAIN group sharing their topics; manifest order retained within partitions',
        'split_salt': SPLIT_SALT, 'seed_group_ids': seeds, 'training_groups': len(training), 'holdout_groups': len(holdout),
        'training_examples': len(examples), 'holdout_people': len(holdout_cases), 'training_cases_path': 'training-cases.json', 'training_targets_path': 'training-targets.json',
        'participant_overlap': 0, 'group_overlap': 0, 'topic_overlap': 0, 'source_bindings': bindings, 'provenance': provenance,
        'train_sha256': sha(output / 'train.jsonl'), 'holdout_cases_sha256': sha(output / 'holdout-cases.json'),
        'targets_sha256': sha(evaluator / 'targets.json'), 'training_cases_sha256': sha(output / 'training-cases.json'), 'training_targets_sha256': sha(output / 'training-targets.json'),
        'validation_csvs_loaded': 0, 'outer_validation_targets_loaded': 0, 'reserve_files_loaded': 0,
        'limitations': ['All examples derive from previously inspected development data.', 'One observed final category is not a known participant probability distribution.', 'No holdout outcome or completion may be supplied to trainer or model prompts.', 'Supplied worker ID separation does not prove unique real-world people.']}
    (output / 'manifest.json').write_text(json.dumps(metadata, indent=2) + '\n')
    return {'training_groups': len(training), 'holdout_groups': len(holdout), 'training_examples': len(examples), 'holdout_people': len(holdout_cases), 'output_path': str(output), 'manifest_sha256': sha(output / 'manifest.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('experiments/debate-sft-replication'))
    parser.add_argument('--audit', type=Path, default=Path('data/local-mlx-pilot/participant-audit.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.audit, args.output)))
