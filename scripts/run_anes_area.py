"""Prepare, seal, container-run, then score a state ANES structural experiment."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import date
from pathlib import Path

from psbx.config import load_yaml
from psbx.experiments.anes_society import (
    AnesSocietySpec,
    _sha256_file,
    evaluate_vote_predictions,
    load_anes_frame,
    prepare_anes_split,
    verify_prepared_runtime_profiles,
)
from psbx.paths import validate_run_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-fips', type=int, default=39)
    parser.add_argument('--run-id', default='anes2012-ohio-20261004')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.environ['PSBX_ROOT'] = str(root)
    run_id = validate_run_id(args.run_id)
    output = root / 'data/runs' / run_id
    output.mkdir(parents=True, exist_ok=False)
    source = root / 'data/survey-microdata/anes/2012/source/anes_timeseries_2012.dta'
    frame = load_anes_frame(source)
    # Select only by pre-existing geography, never by the evaluation outcome.
    cohort = frame.loc[frame['sample_stfips'] == args.state_fips].copy()
    if cohort.empty:
        raise ValueError('No respondents for requested state FIPS')
    spec = AnesSocietySpec.model_validate(
        load_yaml(root / 'config/anes2012-strict-pre-election.yaml')
    ).model_copy(update={'run_id': run_id})
    private_source = output / 'private-area-source.csv'
    columns = list(dict.fromkeys([
        spec.case_id_field, spec.weight_field, *spec.profile_fields, *spec.target_fields,
    ]))
    cohort[columns].to_csv(private_source, index=False)
    prepared = prepare_anes_split(
        private_source, spec, output / 'anes-society',
        evaluation_root=root / 'data/evaluation-vault',
    )
    verified = verify_prepared_runtime_profiles(
        prepared.runtime_profiles, cutoff=date(2012, 11, 5),
        required_timing_policy='strict_pre_election',
    )
    container_output = output / 'container-output'
    container_output.mkdir()
    env = dict(os.environ, ANES_PROFILES=prepared.runtime_profiles,
               ANES_OUTPUT=str(container_output))
    compose = ['docker', 'compose', '--env-file', '/dev/null', '-f', str(root / 'compose.yaml')]
    resolved = subprocess.check_output([*compose, 'config'], env=env, text=True)
    (output / 'compose.resolved.yaml').write_text(resolved)
    with (output / 'container.log').open('w') as log:
        subprocess.run([*compose, 'run', '--rm', '--no-deps', 'anes'],
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    # Verify input and target seals again before opening evaluation targets.
    verify_prepared_runtime_profiles(prepared.runtime_profiles, cutoff=date(2012, 11, 5))
    seal = json.loads(Path(prepared.split_seal).read_text())
    if _sha256_file(Path(prepared.evaluation_targets)) != seal['evaluation_targets_sha256']:
        raise ValueError('Evaluation targets changed after preparation')
    report = evaluate_vote_predictions(
        container_output / 'predictions.jsonl', prepared.evaluation_targets,
        output / 'evaluation.json',
    )
    manifest = {
        'run_id': run_id, 'state_fips': args.state_fips,
        'selection': 'all available respondents in state, regardless of outcome',
        'source_sha256': _sha256_file(source), 'runtime_verification': verified,
        'image_id': subprocess.check_output(
            ['docker', 'image', 'inspect', 'psbx-anes-area:local', '--format', '{{.Id}}'],
            text=True,
        ).strip(),
        'compose_sha256': _sha256_file(output / 'compose.resolved.yaml'),
        'evaluation_sha256': _sha256_file(output / 'evaluation.json'),
        'scientific_result': False,
        'interpretation': 'Heuristic structural simulation, not a live LLM replication.',
    }
    (output / 'run-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'manifest': manifest, 'summary': report['summary'],
                      'reference': report['target_population_reference']}, indent=2))


if __name__ == '__main__':
    main()
