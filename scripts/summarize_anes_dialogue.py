"""Summarize sealed paired ballots and verify that dialogue artifacts are complete."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from psbx.experiments.anes_society import _canonical_json_sha256, _sha256_file
from psbx.paths import resolve, validate_run_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    root = resolve('data/runs') / validate_run_id(args.run_id)
    report = json.loads((root / 'evaluation.json').read_text())
    seal = json.loads((root / 'evaluation.seal.json').read_text())
    assert seal['report_sha256'] == _sha256_file(root / 'evaluation.json')
    assert seal['seal_sha256'] == _canonical_json_sha256(
        {k: v for k, v in seal.items() if k != 'seal_sha256'}
    )
    p = root / 'anes-society'
    prediction_seal = json.loads((p / 'prediction-seal.json').read_text())
    assert _sha256_file(p / 'prediction-seal.json') == seal['prediction_seal_sha256']
    for filename, key in [('predictions.jsonl', 'predictions_sha256'),
                          ('conversation.jsonl', 'conversation_sha256'),
                          ('call-checkpoints.jsonl', 'call_checkpoints_sha256')]:
        assert _sha256_file(p / filename) == prediction_seal[key]
    config = json.loads((root / 'configuration.json').read_text())
    targets_path = resolve(config['targets'])
    assert _sha256_file(targets_path) == seal['targets_sha256']
    predictions = pd.read_json(p / 'predictions.jsonl', lines=True)
    conversations = pd.read_json(p / 'conversation.jsonl', lines=True)
    targets = pd.read_csv(targets_path)
    merged = predictions.merge(targets, on='synthetic_person_id', suffixes=('', '_target'))
    valid = merged[merged.presvote2012_x.isin([1, 2])]
    paired = predictions.pivot(index=['replication', 'synthetic_person_id'],
                               columns='treatment', values='predicted_probability')
    metrics = pd.DataFrame(report['per_replication'])
    comparisons = []
    for replication, rows in metrics.groupby('replication'):
        independent = rows[rows.treatment == 'independent'].iloc[0]
        society = rows[rows.treatment == 'society'].iloc[0]
        comparisons.append({
            'replication': int(replication), 'scorable_profiles': int(independent['n']),
            'brier_change_society_minus_independent': float(society.brier - independent.brier),
            'agreement_change': float(society.agreement - independent.agreement),
            'independent_absolute_share_error': float(abs(
                independent.predicted_republican_share - independent.observed_republican_share)),
            'society_absolute_share_error': float(abs(
                society.predicted_republican_share - society.observed_republican_share)),
        })
    public = conversations[conversations.treatment == 'society']
    counts = public.groupby(['replication', 'round']).size()
    assert len(counts) == config['replications'] * config['rounds']
    assert (counts == config['max_agents']).all()
    ledger = json.loads((root / 'spend_ledger.json').read_text())
    summary = {
        'run_id': args.run_id, 'state': config['state'], 'scientific_result': False,
        'completed_logical_calls': prediction_seal['completed_logical_calls'],
        'private_ballots': len(predictions), 'public_messages': len(public),
        'private_reflections': int((conversations.treatment == 'independent').sum()),
        'profile_replication_pairs': len(paired),
        'unique_sampled_profiles': int(predictions.synthetic_person_id.nunique()),
        'scorable_profile_replication_pairs': int(len(valid) // 2),
        'unique_scorable_profiles': int(valid.synthetic_person_id.nunique()),
        'summary': report['summary'], 'paired_comparisons': comparisons,
        'mean_absolute_probability_change': float(np.mean(abs(
            paired.society - paired.independent))),
        'binary_prediction_flips': int(((paired.society > .5) !=
                                       (paired.independent > .5)).sum()),
        'provider_reported_cost_usd': sum(
            (entry.get('reported_usage') or {}).get('provider_cost_usd', 0) or 0
            for entry in ledger['entries']),
        'request_reservations': ledger['reserved_requests'],
        'unreconciled_requests': sum(entry.get('reported_usage') is None
                                    for entry in ledger['entries']),
        'interpretation': 'Small paired replications; descriptive pilot, not a powered '
                          'effect estimate. Respondents may recur across replications. Eight '
                          'pre-election fields, modern models, and no evidence pack differ '
                          'from the exact published ten-field silicon-sampling study.',
    }
    destination = root / 'comparison.json'
    destination.write_text(json.dumps(summary, indent=2) + '\n')
    analysis_seal = {'comparison_sha256': _sha256_file(destination),
                     'evaluation_seal_sha256': _sha256_file(root / 'evaluation.seal.json'),
                     'analysis_source_sha256': _sha256_file(Path(__file__))}
    analysis_seal['seal_sha256'] = _canonical_json_sha256(analysis_seal)
    (root / 'comparison.seal.json').write_text(json.dumps(analysis_seal, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
