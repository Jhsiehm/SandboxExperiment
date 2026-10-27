"""Metadata-only balanced five-fold partitions of the already admitted92fit rows.

Targets and initial ratings never influence connected components or fold choice.
The previously bound participant audit establishes supplied-ID uniqueness across
source groups; row agent IDs additionally preserve any explicitly shared identity.
"""
import argparse
import hashlib
import json
from pathlib import Path

SALT = 'residual-calibration-folds-v1:'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def make_folds(rows, fold_count=5):
    require(fold_count >= 2, 'At least two folds required')
    groups = sorted({r['group_id'] for r in rows})
    parent = {g: g for g in groups}
    def root(g):
        while parent[g] != g:
            parent[g] = parent[parent[g]]
            g = parent[g]
        return g
    def join(a, b):
        parent[root(b)] = root(a)
    owners = {}
    identities = []
    for i, row in enumerate(rows):
        group, profile = row['group_id'], row['profile']
        require(isinstance(group, str) and group and profile['agent_id'] and profile['topic'], 'Missing split metadata')
        identities.append({'index': i, 'group_id': group, 'agent_id': profile['agent_id']})
        for key in [('topic', profile['topic']), ('person', profile['agent_id'])]:
            if key in owners:
                join(group, owners[key])
            else:
                owners[key] = group
    require(len({(r['group_id'], r['agent_id']) for r in identities}) == len(rows), 'Duplicate group-person row')
    components = {}
    for group in groups:
        components.setdefault(root(group), []).append(group)
    component_rows = []
    for member_groups in components.values():
        indices = [r['index'] for r in identities if r['group_id'] in member_groups]
        key = hashlib.sha256((SALT + json.dumps(sorted(member_groups), separators=(',', ':'))).encode()).hexdigest()
        component_rows.append({'group_ids': sorted(member_groups), 'row_indices': indices, 'people': len(indices), 'tie_break_sha256': key})
    require(len(component_rows) >= fold_count, 'Too few independent components')
    component_rows.sort(key=lambda c: (-c['people'], c['tie_break_sha256']))
    folds = [{'fold': i, 'validation_group_ids': [], 'validation_row_indices': []} for i in range(fold_count)]
    for component_id, component in enumerate(component_rows):
        component['component_id'] = component_id
        chosen = min(folds, key=lambda f: (len(f['validation_row_indices']), len(f['validation_group_ids']), f['fold']))
        chosen['validation_group_ids'].extend(component['group_ids'])
        chosen['validation_row_indices'].extend(component['row_indices'])
        component['fold'] = chosen['fold']
        for index in component['row_indices']:
            identities[index].update(component_id=component_id, fold=chosen['fold'])
    all_indices = set(range(len(rows)))
    for fold in folds:
        fold['validation_group_ids'].sort()
        fold['validation_row_indices'].sort()
        fold['training_row_indices'] = sorted(all_indices - set(fold['validation_row_indices']))
        fold['validation_people'] = len(fold['validation_row_indices'])
        fold['training_people'] = len(fold['training_row_indices'])
        for key in ('agent_id', 'topic'):
            train = {rows[i]['profile'][key] for i in fold['training_row_indices']}
            valid = {rows[i]['profile'][key] for i in fold['validation_row_indices']}
            require(not train & valid, 'Fold identity/topic overlap')
    require(sorted(i for f in folds for i in f['validation_row_indices']) == list(range(len(rows))), 'Incomplete fold coverage')
    return {'fold_count': fold_count, 'people': len(rows), 'groups': len(groups), 'components': component_rows,
            'row_identities': identities, 'folds': folds,
            'split_rule': 'Union groups sharing exact topic or supplied agent identity; sort components by descending row count then salted SHA256 of sorted group IDs; greedily assign minimum(row count, group count, fold index). No outcomes or ratings used.'}


def prepare(data_root, prior_contract_path, participant_audit_path, output):
    data = Path(data_root).resolve()
    contract_path, audit_path = Path(prior_contract_path).resolve(), Path(participant_audit_path).resolve()
    manifest_path, train_path = data / 'manifest.json', data / 'train.jsonl'
    manifest = json.loads(manifest_path.read_text())
    contract = json.loads(contract_path.read_text())
    audit = json.loads(audit_path.read_text())
    require(contract['train_bindings'].get(str(train_path)) == sha(train_path) == manifest['train_sha256'], 'Training data binding mismatch')
    require(contract['common_bindings'].get(str(manifest_path)) == sha(manifest_path), 'Preparation metadata binding mismatch')
    require(manifest['source_bindings'].get(str(audit_path)) == sha(audit_path), 'Participant audit binding mismatch')
    require(audit['prepared']['all']['participants_in_multiple_groups'] == 0 and audit['prepared']['duplicate_initial_rows'] == 0, 'Supplied IDs are not globally unique; direct identity components required')
    rows = [json.loads(line) for line in train_path.read_text().splitlines()]
    require(len(rows) == 92 and len({r['group_id'] for r in rows}) == 23, 'Unexpected fitting pool')
    expected_groups = {g['group_id'] for g in manifest['provenance'] if g['split'] == 'train'}
    require({r['group_id'] for r in rows} == expected_groups, 'Fitting group provenance mismatch')
    cases_path = data / 'training-cases.json'
    require(sha(cases_path) == manifest['training_cases_sha256'], 'Training profile binding mismatch')
    cases = json.loads(cases_path.read_text())
    require([(r['group_id'], r['profile']['agent_id']) for r in rows] == [(r['group_id'], r['profile']['agent_id']) for r in cases], 'Training profile order mismatch')
    require(all(set(r) == {'group_id', 'profile'} for r in cases), 'Unexpected training profile field')
    result = make_folds(rows)
    result.update(schema_version=1, scope='Five-fold development calibration on92fit rows only',
        source_training_cases_path=str(cases_path), source_training_cases_sha256=manifest['training_cases_sha256'],
        source_training_targets_path=str(data / 'training-targets.json'), source_training_targets_sha256=manifest['training_targets_sha256'],
        split_salt=SALT, target_fields_used=False, initial_rating_used=False,
        internal_holdout_cases_loaded=0, internal_holdout_targets_loaded=0, outer_validation_files_loaded=0, reserve_files_loaded=0,
        supplied_person_separation='Previously bound source participant audit verifies zero repeated supplied worker IDs across all admitted groups; prepared agent IDs are group pseudonyms.',
        source_bindings={str(p): sha(p) for p in [Path(__file__).resolve(), train_path, cases_path, manifest_path, audit_path, contract_path]})
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    output.chmod(0o444)
    return {'folds_path': str(output), 'sha256': sha(output), 'people': len(rows), 'groups': result['groups'],
            'components': len(result['components']), 'fold_validation_people': [f['validation_people'] for f in result['folds']]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--prior-contract', type=Path, required=True)
    parser.add_argument('--participant-audit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.data, args.prior_contract, args.participant_audit, args.output)))
