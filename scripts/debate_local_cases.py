"""Prepare initial-only validation prompts and separate evaluator labels offline."""
import csv
import hashlib
import json
from pathlib import Path

from psbx.experiments.social_benchmark import parse_group


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_validation_cases(source_root, output_root, *, participant_audit_path=None,
                             expected_groups=4, expected_people=16):
    """Write cases.json, evaluator/targets.json and manifest.json; return paths/counts.

    source_root is experiments/debate-sft-replication. Default audit dependency is
    the repository's data/local-mlx-pilot/participant-audit.json. Labels are never
    returned. The caller must pass only cases.json to model workers; file separation
    is an interface boundary, not an OS sandbox.
    """
    source = Path(source_root).resolve()
    output = Path(output_root).resolve()
    inputs = source / 'inputs'
    audit_path = Path(participant_audit_path) if participant_audit_path else source.parents[1] / 'data/local-mlx-pilot/participant-audit.json'
    identity_audit = json.loads(audit_path.read_text())
    manifest_path = inputs / 'manifest.json'
    if identity_audit['manifest_sha256'] != sha(manifest_path):
        raise ValueError('Participant audit does not match input manifest')
    overlap = identity_audit['prepared']['train_vs_validation']
    if any(overlap[k] for k in ('participant_overlap', 'group_overlap', 'topic_overlap')):
        raise ValueError('Participant audit split integrity failed')
    manifest = json.loads(manifest_path.read_text())
    preparation_path = source / 'preparation-audit.json'
    admitted = json.loads(preparation_path.read_text())['per_group']
    admitted_ids = sorted(admitted)
    admitted_hash = hashlib.sha256(json.dumps(admitted_ids, separators=(',', ':')).encode()).hexdigest()
    if (identity_audit.get('admitted_group_ids') != admitted_ids
            or identity_audit.get('admitted_group_ids_sha256') != admitted_hash):
        raise ValueError('Participant audit does not match admitted group set')
    selected = [g for g in manifest['groups'] if g['partition'] == 'validation' and g['group_id'] in admitted]
    if len(selected) != expected_groups or len({g['group_id'] for g in selected}) != expected_groups:
        raise ValueError('Unexpected validation group count')
    cases, targets, provenance = [], [], []
    for group in selected:
        path = (inputs / (group['group_id'] + '.csv')).resolve()
        if path.parent != inputs.resolve():
            raise ValueError('Group path escapes development inputs')
        checksum = sha(path)
        if checksum != group['sha256']:
            raise ValueError('Development input checksum mismatch')
        with path.open(newline='') as stream:
            group_cases, group_targets = parse_group(list(csv.DictReader(stream)), group['topic'], group['group_id'])
        # Explicit whitelist: no observed incoming messages or post-opinion labels.
        for case in group_cases:
            profile = case['profile']
            cases.append({'group_id': case['group_id'], 'profile': {
                key: profile[key] for key in ('agent_id', 'topic', 'initial_score', 'initial_text', 'partners')}})
        targets.extend(group_targets)
        provenance.append({'group_id': group['group_id'], 'topic': group['topic'],
                           'partition': 'validation', 'source_path': str(path), 'sha256': checksum,
                           'agent_ids': [c['profile']['agent_id'] for c in group_cases]})
    if len(cases) != expected_people or len({c['profile']['agent_id'] for c in cases}) != expected_people:
        raise ValueError('Unexpected validation participant count')
    if {(c['group_id'], c['profile']['agent_id']) for c in cases} != {(t['group_id'], t['agent_id']) for t in targets}:
        raise ValueError('Case and evaluator identity mismatch')
    output.mkdir(parents=True, exist_ok=True)
    evaluator = output / 'evaluator'
    evaluator.mkdir(mode=0o700, exist_ok=True)
    evaluator.chmod(0o700)
    paths = {'cases_path': output / 'cases.json', 'targets_path': evaluator / 'targets.json',
             'manifest_path': output / 'manifest.json'}
    metadata = {'schema_version': 1, 'scope': 'Previously downloaded admitted development validation groups only',
                'groups': len(selected), 'people': len(cases), 'reserve_files_loaded': 0,
                'source_manifest_sha256': sha(manifest_path), 'preparation_audit_sha256': sha(preparation_path),
                'participant_audit_path': str(audit_path.resolve()), 'participant_audit_sha256': sha(audit_path),
                'provenance': provenance, 'model_input_fields': ['group_id', 'profile'],
                'warning': 'Validation cohort is exploratory and has been used for training validation; evaluator labels must not enter model context.'}
    paths['cases_path'].write_text(json.dumps(cases, indent=2) + '\n')
    paths['targets_path'].write_text(json.dumps(targets, indent=2) + '\n')
    paths['targets_path'].chmod(0o600)
    metadata['cases_sha256'] = sha(paths['cases_path'])
    metadata['targets_sha256'] = sha(paths['targets_path'])
    paths['manifest_path'].write_text(json.dumps(metadata, indent=2) + '\n')
    return {'groups': len(selected), 'people': len(cases), **{k: str(v) for k, v in paths.items()}}
