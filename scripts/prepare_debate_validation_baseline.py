"""Fit fixed Laplace-one transitions using admitted development TRAIN groups only."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from psbx.experiments.social_benchmark import parse_group


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_baseline(source_root, audit_path, output_path, *, expected_groups=29):
    source = Path(source_root).resolve()
    inputs = source / 'inputs'
    audit_path = Path(audit_path)
    manifest_path = inputs / 'manifest.json'
    preparation_path = source / 'preparation-audit.json'
    audit = json.loads(audit_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    admitted = json.loads(preparation_path.read_text())['per_group']
    ids = sorted(admitted)
    ids_hash = hashlib.sha256(json.dumps(ids, separators=(',', ':')).encode()).hexdigest()
    if (audit['manifest_sha256'] != sha(manifest_path)
            or audit.get('admitted_group_ids') != ids
            or audit.get('admitted_group_ids_sha256') != ids_hash):
        raise ValueError('Stale participant audit')
    if any(audit['prepared']['train_vs_validation'][k]
           for k in ('participant_overlap', 'group_overlap', 'topic_overlap')):
        raise ValueError('Train-validation split integrity failed')
    train = [g for g in manifest['groups'] if g['partition'] == 'train' and g['group_id'] in admitted]
    validation = [g for g in manifest['groups'] if g['partition'] == 'validation' and g['group_id'] in admitted]
    if len(train) != expected_groups or len({g['group_id'] for g in train}) != expected_groups:
        raise ValueError('Unexpected training group count')
    if {g['topic'] for g in train} & {g['topic'] for g in validation}:
        raise ValueError('Training topic overlaps validation')
    counts = [[1] * 6 for _ in range(6)]
    provenance, people = [], 0
    for group in train:
        path = (inputs / (group['group_id'] + '.csv')).resolve()
        if path.parent != inputs.resolve() or sha(path) != group['sha256']:
            raise ValueError('Training source checksum or path mismatch')
        with path.open(newline='') as stream:
            cases, targets = parse_group(list(csv.DictReader(stream)), group['topic'], group['group_id'])
        labels = {t['agent_id']: t['final_score'] for t in targets}
        if len(labels) != len(cases):
            raise ValueError('Training case-target mismatch')
        for case in cases:
            initial = case['profile']['initial_score']
            final = labels[case['profile']['agent_id']]
            if not isinstance(initial, int) or not isinstance(final, int) or not 1 <= initial <= 6 or not 1 <= final <= 6:
                raise ValueError('Training score outside six categories')
            counts[initial - 1][final - 1] += 1
            people += 1
        provenance.append({'group_id': group['group_id'], 'topic': group['topic'], 'sha256': group['sha256']})
    result = {'schema_version': 1, 'purpose': 'Fixed training-only statistical comparator for sealed validation predictions',
              'method': 'Laplace-one P(final score | initial score), six categories; no tuning',
              'training_groups': len(train), 'training_people': people, 'pseudocount_per_cell': 1,
              'counts': counts, 'probabilities': [[n / sum(row) for n in row] for row in counts],
              'source_manifest_sha256': sha(manifest_path), 'preparation_audit_sha256': sha(preparation_path),
              'participant_audit_sha256': sha(audit_path), 'admitted_group_ids_sha256': ids_hash,
              'provenance': provenance, 'validation_csvs_loaded': 0, 'validation_targets_loaded': 0,
              'reserve_files_loaded': 0}
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    return {'training_groups': len(train), 'training_people': people, 'output_path': str(output.resolve()), 'sha256': sha(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('experiments/debate-sft-replication'))
    parser.add_argument('--audit', type=Path, default=Path('data/local-mlx-pilot/participant-audit.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_baseline(args.source, args.audit, args.output)))
