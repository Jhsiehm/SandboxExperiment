"""Audit downloaded development identities only; never reads reserve data or outcomes.

Repeated event rows for a person are expected. Repetition here means membership in
multiple groups, or duplicated Initial Opinion rows. Reports contain hashes only.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def summarize(groups):
    membership = Counter(p for g in groups for p in g['participants'])
    return {'groups': len(groups), 'unique_participants': len(membership),
            'participant_memberships': sum(membership.values()),
            'participants_in_multiple_groups': sum(n > 1 for n in membership.values()),
            'maximum_groups_per_participant': max(membership.values(), default=0)}


def compare(left, right):
    lp = set().union(*(g['participants'] for g in left))
    rp = set().union(*(g['participants'] for g in right))
    shared = lp & rp
    return {'participant_overlap': len(shared),
            'participant_hashes': sorted(digest(p) for p in shared),
            'group_overlap': len({g['group_id'] for g in left} & {g['group_id'] for g in right}),
            'topic_overlap': len({g['topic'] for g in left} & {g['topic'] for g in right})}


def audit(inputs, admitted, fit_groups=None):
    inputs = Path(inputs).resolve()
    manifest = json.loads((inputs / 'manifest.json').read_text())
    records = []
    seen = set()
    for item in manifest['groups']:
        gid = item['group_id']
        if item['partition'] not in ('train', 'validation'):
            raise ValueError('Only development train/validation partitions allowed')
        if gid in seen:
            raise ValueError('Duplicate manifest group')
        seen.add(gid)
        path = (inputs / (gid + '.csv')).resolve()
        if path.parent != inputs:
            raise ValueError('Group path escapes development inputs')
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Development input checksum mismatch')
        # Ignore text, opinions and other response fields entirely.
        with path.open(newline='') as stream:
            initial = [row['worker_id'].strip() for row in csv.DictReader(stream)
                       if row['event_type'] == 'Initial Opinion']
        if not initial or any(not p for p in initial):
            raise ValueError('Missing initial participant identity')
        records.append(dict(item, participants=set(initial),
                            duplicate_initial_rows=len(initial)-len(set(initial))))
    if set(admitted) - seen:
        raise ValueError('Admitted groups absent from development manifest')
    prepared = [g for g in records if g['group_id'] in admitted]
    report = {'schema_version': 1, 'scope': 'Downloaded development CSV initial-record identities only',
              'reserve_files_loaded': 0, 'raw_participant_ids_reported': False,
              'manifest_sha256': digest((inputs / 'manifest.json').read_text()),
              'admitted_group_ids': sorted(admitted),
              'admitted_group_ids_sha256': digest(json.dumps(sorted(admitted), separators=(',', ':')))}
    for name, groups in [('downloaded', records), ('prepared', prepared)]:
        train = [g for g in groups if g['partition'] == 'train']
        valid = [g for g in groups if g['partition'] == 'validation']
        report[name] = {'all': summarize(groups), 'train': summarize(train),
                        'validation': summarize(valid), 'train_vs_validation': compare(train, valid),
                        'duplicate_initial_rows': sum(g['duplicate_initial_rows'] for g in groups)}
    train = [g for g in prepared if g['partition'] == 'train']
    if fit_groups is not None:
        if not train or set(fit_groups) - {g['group_id'] for g in train}:
            raise ValueError('Baseline fit groups outside prepared training groups')
        selected = train[:1]  # Same frozen metadata ordering as development runner.
        fit = [g for g in train if g['group_id'] in fit_groups]
        report['historical_development_baseline'] = dict(compare(fit, selected),
            selected_group=selected[0]['group_id'], fit_groups=len(fit))
        report['selected_development_vs_sft_train'] = compare(train, selected)
    report['limitations'] = ['Identity equality is an audit of supplied worker IDs, not proof of real-person uniqueness.',
                            'Previously inspected development data are not a fresh confirmatory holdout.']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('experiments/debate-sft-replication'))
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepared = json.loads((args.source / 'preparation-audit.json').read_text())
    fitted = json.loads(args.baseline.read_text())['fit_groups'] if args.baseline else None
    result = audit(args.source / 'inputs', prepared['per_group'], fitted)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({name: result[name]['train_vs_validation']['participant_overlap']
                      for name in ('downloaded', 'prepared')}))


if __name__ == '__main__':
    main()
