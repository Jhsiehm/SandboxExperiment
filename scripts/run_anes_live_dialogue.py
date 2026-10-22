"""Run and evaluate a reproducible, bounded live ANES state dialogue pilot."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx

from psbx.config import load_models, load_yaml
from psbx.env import load_dotenv
from psbx.experiments.anes_society import (
    _sha256_file,
    evaluate_vote_predictions,
    run_live_llm_vote_society,
)
from psbx.paths import validate_run_id
from psbx.schemas import ModelConfig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='config/anes2012-ohio-live-dialogue.yaml')
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.environ['PSBX_ROOT'] = str(root)
    load_dotenv()
    spec = load_yaml(root / args.config)
    run_id = validate_run_id(args.run_id)
    output = root / 'data/runs' / run_id
    output.mkdir(parents=True, exist_ok=True)
    snapshot = output / 'configuration.json'
    if snapshot.exists() and json.loads(snapshot.read_text()) != spec:
        raise ValueError('Configuration changed; use a fresh run ID')
    snapshot.write_text(json.dumps(spec, indent=2) + '\n')
    readiness = {}
    for endpoint in ['auth/key', 'credits']:
        response = httpx.get(
            'https://openrouter.ai/api/v1/' + endpoint,
            headers={'Authorization': 'Bearer ' + os.environ.get('OPENROUTER_API_KEY', '')},
            timeout=30,
        )
        readiness[endpoint] = {'http_status': response.status_code}
        if response.status_code == 200:
            data = response.json()['data']
            readiness[endpoint].update({key: data[key] for key in [
                'limit_remaining', 'total_credits', 'total_usage',
            ] if key in data})
    (output / 'provider-readiness.json').write_text(json.dumps(readiness, indent=2) + '\n')
    if any(r['http_status'] != 200 for r in readiness.values()):
        raise RuntimeError('Provider authentication/readiness failed; see readiness artifact')
    credits = readiness['credits']
    if credits['total_credits'] - credits['total_usage'] < spec['max_run_usd']:
        raise RuntimeError('Account credit is below the configured run ceiling')
    key_remaining = readiness['auth/key'].get('limit_remaining')
    if key_remaining is not None and key_remaining < spec['max_run_usd']:
        raise RuntimeError('API key remaining limit is below the configured run ceiling')
    workers_path = output / 'workers.json'
    if workers_path.exists():
        workers = [ModelConfig.model_validate(row) for row in json.loads(workers_path.read_text())]
    else:
        response = httpx.get('https://openrouter.ai/api/v1/models', timeout=30)
        response.raise_for_status()
        catalog = {row['id']: row for row in response.json()['data']}
        configured = load_models()
        workers = []
        selected = {}
        for _ in range(spec['copies_per_model']):
            for model_id in spec['models']:
                model = configured[model_id]
                row = catalog[model.model_name]
                if spec.get('json_output') and 'response_format' not in row.get(
                    'supported_parameters', []
                ):
                    raise ValueError(f'{model_id} does not support JSON output mode')
                pricing = row['pricing']
                selected[model.model_name] = {'id': row['id'], 'pricing': pricing}
                workers.append(model.model_copy(update={
                    'max_tokens': 256, 'temperature': 0.8,
                    'json_output': bool(spec.get('json_output', False)),
                    'cost_per_1k_input': float(pricing['prompt']) * 1000,
                    'cost_per_1k_output': float(pricing['completion']) * 1000,
                }))
        workers_path.write_text(json.dumps(
            [worker.model_dump(mode='json') for worker in workers], indent=2,
        ) + '\n')
        (output / 'catalog-selection.json').write_text(json.dumps(selected, indent=2) + '\n')
    profiles = root / spec['profiles']
    rows = [json.loads(line) for line in profiles.read_text().splitlines()]
    if not all(row['profile']['sample_stfips'] == spec['state_fips'] for row in rows):
        raise ValueError('Runtime profiles do not match the configured state')
    os.environ.update(
        PSBX_MOCK_LLM='0', PSBX_ENABLE_PAID_MODELS='1',
        PSBX_MAX_PAID_REQUESTS=str(spec['max_paid_requests']),
        PSBX_MAX_RUN_USD=str(spec['max_run_usd']),
    )
    result = run_live_llm_vote_society(
        profiles, output / 'anes-society', run_id=run_id, _workers=workers,
        **{key: spec[key] for key in [
            'seed', 'replications', 'max_agents', 'group_size', 'rounds',
        ]},
    )
    targets = root / spec['targets']
    split = json.loads((profiles.parent.parent / 'split-seal.json').read_text())
    if _sha256_file(targets) != split['evaluation_targets_sha256']:
        raise ValueError('Evaluation targets no longer match the prepared split')
    report = evaluate_vote_predictions(
        result['predictions'], targets, output / 'evaluation.json',
    )
    print(json.dumps({'run': result, 'summary': report['summary']}, indent=2))


if __name__ == '__main__':
    main()
