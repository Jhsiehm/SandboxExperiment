"""Versioned training-only original-versus-prefill diagnosis; no outcome scoring."""
import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARMS = ('base', 'pilot_adapter')
CONDITIONS = ('original', 'assistant_prefill')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def require(ok, message):
    if not ok:
        raise ValueError(message)


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def verify(bindings):
    for path, digest in bindings.items():
        require(sha(path) == digest, 'Binding mismatch: ' + path)


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def strict_probabilities(raw):
    value = json.loads(raw, object_pairs_hook=unique_keys)
    require(isinstance(value, dict) and set(value) == {'probabilities'}, 'Expected probabilities object only')
    p = value['probabilities']
    require(isinstance(p, list) and len(p) == 6, 'Expected six probabilities')
    require(all(type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 1 for x in p), 'Invalid probability')
    require(abs(sum(p) - 1) <= 1e-6, 'Probability sum differs from one')
    return p


def initial_cases(source):
    """Read exactly one admitted TRAIN CSV, selecting initial fields only."""
    source = Path(source).resolve()
    manifest = read(source / 'inputs/manifest.json')
    admitted = read(source / 'preparation-audit.json')['per_group']
    selected = next(g for g in manifest['groups'] if g['partition'] == 'train' and g['group_id'] in admitted)
    inputs = (source / 'inputs').resolve()
    path = (inputs / (selected['group_id'] + '.csv')).resolve()
    require(path.parent == inputs, 'Training path escape')
    require(sha(path) == selected['sha256'], 'Training checksum mismatch')
    initial = []
    with path.open(newline='') as stream:
        for row in csv.DictReader(stream):
            if row['event_type'] == 'Initial Opinion':
                initial.append({key: row[key] for key in ('worker_id', 'sliderValue', 'text')})
    require(len(initial) == 4 and len({r['worker_id'] for r in initial}) == 4, 'Expected four distinct initials')
    cases = []
    for i, row in enumerate(initial):
        number = float(row['sliderValue'])
        require(number.is_integer() and 1 <= number <= 6 and row['text'].strip(), 'Invalid initial state')
        cases.append(dict(group_id=selected['group_id'], profile=dict(
            agent_id=f"{selected['group_id']}-p{i}", topic=selected['topic'], initial_score=int(number),
            initial_text=row['text'], partners={})))
    return cases, path


def offline_environment():
    for name in list(os.environ):
        if name.upper().endswith('API_KEY') or name.upper() in ('HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN'):
            os.environ.pop(name)
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_DATASETS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')


def load_contract(output):
    contract = read(output / 'contract.json')
    require(contract['status'] == 'frozen_training_only_format_diagnostic', 'Not frozen')
    verify(contract['bindings'])
    protocol_path = Path(contract['protocol_path'])
    require(str(protocol_path) in contract['bindings'] and contract['policy'] == read(protocol_path), 'Protocol policy mismatch')
    prior_path = Path(contract['prior_candidate_contract_path'])
    require(str(prior_path) in contract['bindings'], 'Unbound original candidate metadata')
    prior = read(prior_path)
    require(contract['model_path'] == prior['model_path'] and contract['adapter_path'] == prior['adapter_path'], 'Candidate paths differ')
    for key in ('model_path', 'adapter_path'):
        directory = Path(contract[key])
        require(all(str(p) in contract['bindings'] for p in directory.iterdir() if p.is_file() and
                    (key == 'model_path' or p.name in ('adapters.safetensors', 'adapter_config.json'))), 'Unbound candidate file')
    for path in [p for p in Path(contract['model_path']).iterdir() if p.is_file()] + [Path(contract['adapter_path']) / 'adapters.safetensors', Path(contract['adapter_path']) / 'adapter_config.json']:
        require(contract['bindings'].get(str(path)) == prior['bindings'].get(str(path)) and str(path) in prior['bindings'], 'Candidate binding differs')
    return contract


def prepare(output):
    offline_environment()
    from transformers import AutoTokenizer
    output = Path(output).resolve()
    output.mkdir(mode=0o700, exist_ok=False)
    protocol_path = HERE / 'format-smoke-v1.protocol.json'
    protocol = read(protocol_path)
    data = ROOT / 'data/local-mlx-pilot'
    model = Path((data / 'model-path.txt').read_text().strip())
    adapter = data / 'pilot-20261023-030458/adapters'
    # Require exact original candidate and source revision; no model discovery/search.
    require(read(data / 'model-source.json')['revision'] == '241a666dad6cb93c8ff213d39a7f34a36bf26db4', 'Unexpected model revision')
    require(sha(adapter / 'adapters.safetensors') == '0ff604a8aa8b9edba4edd3e6030bab3d2e6379bd5cfe69f787ce248102283740', 'Unexpected adapter')
    require(model.name == '241a666dad6cb93c8ff213d39a7f34a36bf26db4', 'Unexpected model snapshot')
    prior_contract_path = data / 'matched-comparison-20261023/contract.json'
    prior = read(prior_contract_path)  # Metadata only; never verify old validation payload bindings.
    require(prior['model_path'] == str(model) and prior['adapter_path'] == str(adapter), 'Candidate path mismatch')
    candidate_files = [p for p in sorted(model.iterdir()) if p.is_file()] + [adapter / 'adapters.safetensors', adapter / 'adapter_config.json']
    for path in candidate_files:
        require(prior['bindings'].get(str(path)) == sha(path), 'Original candidate bytes changed')
    cases, training_path = initial_cases(HERE)
    worker_path = ROOT / 'src/psbx/experiments/social_worker.py'
    spec = importlib.util.spec_from_file_location('format_prompt', worker_path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    tokenizer = AutoTokenizer.from_pretrained(str(model), local_files_only=True)
    prompts = []
    for case in cases:
        prompt = worker.build_prompt(dict(profile=case['profile'], arm='private', stage='final', round=3, history=[]))
        messages = [dict(role='system', content=prompt['system']), dict(role='user', content=prompt['user'])]
        base_tokens = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_dict=False)
        for condition in CONDITIONS:
            prefix = '' if condition == 'original' else protocol['assistant_prefix']
            tokens = list(base_tokens) + tokenizer.encode(prefix, add_special_tokens=False)
            require(len(tokens) + protocol['max_new_tokens'] <= protocol['max_total_tokens'], 'Context cap exceeded')
            prompts.append(dict(agent=case['profile']['agent_id'], group=case['group_id'], condition=condition,
                                messages=messages, assistant_prefix=prefix, prompt_tokens=tokens))
    write_new(output / 'cases.json', cases)
    write_new(output / 'prompts.json', prompts)
    bound = [Path(__file__).resolve(), protocol_path, worker_path, HERE / 'local_watchdog.py',
             HERE / 'inputs/manifest.json', HERE / 'preparation-audit.json', training_path,
             data / 'requirements.lock', data / 'model-source.json', prior_contract_path, output / 'cases.json', output / 'prompts.json',
             adapter / 'adapters.safetensors', adapter / 'adapter_config.json']
    bound += [p for p in sorted(model.iterdir()) if p.is_file()]
    contract = dict(status='frozen_training_only_format_diagnostic', version=protocol['version'],
                    policy=protocol, protocol_path=str(protocol_path), prior_candidate_contract_path=str(prior_contract_path), model_path=str(model), adapter_path=str(adapter),
                    selected_training_group=cases[0]['group_id'], prompt_count_per_arm=len(prompts),
                    bindings={str(p): sha(p) for p in bound}, validation_cases_loaded=0,
                    validation_targets_loaded=0, reserve_files_loaded=0, paid_calls=0)
    write_new(output / 'contract.json', contract)
    print(json.dumps(dict(status='frozen', run=str(output), generations=16, contract_sha256=sha(output / 'contract.json'))))


def repetition_fraction(tokens):
    grams = [tuple(tokens[i:i + 4]) for i in range(max(0, len(tokens) - 3))]
    return 0.0 if not grams else (len(grams) - len(set(grams))) / len(grams)


def run(output, arm):
    offline_environment()
    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler
    import re
    import subprocess
    def swap():
        raw = subprocess.check_output(['sysctl', '-n', 'vm.swapusage'], text=True)
        match = re.search(r'used\s*=\s*([\d.]+)([KMG])', raw)
        require(match is not None, 'Unparseable swap usage')
        return float(match[1]) * {'K': 1 / 1024, 'M': 1, 'G': 1024}[match[2]]
    output = Path(output).resolve()
    contract = load_contract(output)
    policy = contract['policy']
    directory = output / arm
    directory.mkdir(mode=0o700, exist_ok=False)
    prompts = read(output / 'prompts.json')
    require(len(prompts) == 8, 'Expected eight sealed prompts per arm')
    mx.set_cache_limit(256 * 1024**2)
    mx.reset_peak_memory()
    mx.random.seed(policy['seed'])
    start, baseline_swap = time.monotonic(), swap()
    model, tokenizer = load(contract['model_path'], adapter_path=contract['adapter_path'] if arm == 'pilot_adapter' else None)
    model.eval()
    records, failure = [], None
    try:
        for item in prompts:
            require(time.monotonic() - start < policy['total_wall_seconds'], 'Local wall cap exceeded')
            text_parts, generated_tokens, finish_reason, generation_count = [], [], None, None
            for response in stream_generate(model, tokenizer, prompt=item['prompt_tokens'],
                    max_tokens=policy['max_new_tokens'], sampler=make_sampler(temp=policy['temperature'])):
                text_parts.append(response.text)
                generated_tokens.append(int(response.token))
                finish_reason = response.finish_reason
                generation_count = response.generation_tokens
            require(generation_count == len(generated_tokens), 'Stream token count mismatch')
            continuation = ''.join(text_parts)
            raw = item['assistant_prefix'] + continuation
            record = dict(agent=item['agent'], group=item['group'], condition=item['condition'], arm=arm,
                          assistant_prefix=item['assistant_prefix'], continuation=continuation, assembled_response=raw,
                          generated_tokens=generated_tokens, generated_token_count=generation_count,
                          token_count_source='MLX GenerationResponse.generation_tokens; includes terminal EOS when emitted',
                          token_cap_hit=finish_reason == 'length', finish_reason=finish_reason,
                          repetition_fourgram_fraction=repetition_fraction(generated_tokens),
                          peak_allocated_bytes=mx.get_peak_memory(), elapsed_seconds=time.monotonic() - start,
                          prompt_sha256=hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest())
            try:
                record.update(status='valid', probabilities=strict_probabilities(raw))
            except (ValueError, TypeError) as exc:
                record.update(status='invalid_format', error=str(exc))
            records.append(record)
            with (directory / 'predictions.jsonl').open('a') as stream:
                stream.write(json.dumps(record, allow_nan=False) + '\n')
            print(f"{arm} {len(records)}/8 {item['condition']} {record['status']}", flush=True)
            require(mx.get_peak_memory() <= policy['mlx_peak_gib'] * 1024**3, 'MLX memory cap exceeded')
            require(swap() - baseline_swap <= policy['swap_growth_mib'], 'System swap growth cap exceeded')
            mx.clear_cache()
    except Exception as exc:
        failure = f'{type(exc).__name__}: {exc}'
    summary = dict(status='completed' if failure is None and len(records) == 8 else 'failed',
                   failure=failure, completed=len(records), valid=sum(r['status'] == 'valid' for r in records),
                   contract_sha256=sha(output / 'contract.json'), elapsed_seconds=time.monotonic() - start,
                   peak_allocated_bytes=mx.get_peak_memory(), baseline_swap_mib=baseline_swap, final_swap_mib=swap(),
                   predictions_sha256=sha(directory / 'predictions.jsonl') if records else None,
                   validation_cases_loaded=0, validation_targets_loaded=0, paid_calls=0)
    write_new(directory / 'summary.json', summary)
    print(json.dumps(summary), flush=True)
    if failure is not None:
        raise SystemExit(2)


def report(output):
    output = Path(output).resolve()
    contract = load_contract(output)
    prompts = read(output / 'prompts.json')
    expected = [(x['agent'], x['condition']) for x in prompts]
    supervisor_elapsed = 0.0
    results, paired_statuses, source_bindings = {}, {}, {str(output / 'contract.json'): sha(output / 'contract.json')}
    for arm in ARMS:
        watchdog_path = output / ('watchdog-format-' + arm) / 'summary.json'
        watch = read(watchdog_path)
        require(watch['exit_code'] == watch['child_returncode'] == 0 and watch['stop_reason'] is None and watch.get('error') is None, 'Supervisor failure')
        supervisor_elapsed += watch['elapsed_seconds']
        summary_path, predictions_path = output / arm / 'summary.json', output / arm / 'predictions.jsonl'
        summary = read(summary_path)
        require(summary['status'] == 'completed' and summary['completed'] == 8 and
                summary['contract_sha256'] == sha(output / 'contract.json') and
                summary['predictions_sha256'] == sha(predictions_path), 'Incomplete/unbound arm')
        records = [json.loads(line) for line in predictions_path.read_text().splitlines()]
        require([(r['agent'], r['condition']) for r in records] == expected, 'Mismatched records')
        require(summary['valid'] == sum(r['status'] == 'valid' for r in records), 'Summary validity mismatch')
        for r, prompt in zip(records, prompts):
            require(r['arm'] == arm and r['group'] == prompt['group'], 'Record model/group mismatch')
            require(r['assistant_prefix'] == prompt['assistant_prefix'], 'Recorded prefix mismatch')
            require(r['generated_token_count'] == len(r['generated_tokens']), 'Recorded token count mismatch')
            require(r['token_cap_hit'] == (r['finish_reason'] == 'length'), 'Recorded cap mismatch')
            require(r['prompt_sha256'] == hashlib.sha256(json.dumps(prompt, sort_keys=True).encode()).hexdigest(), 'Mismatched paired prompt')
            require(r['assembled_response'] == prompt['assistant_prefix'] + r['continuation'], 'Prefix assembly mismatch')
            try:
                p = strict_probabilities(r['assembled_response'])
            except (ValueError, TypeError):
                require(r['status'] == 'invalid_format', 'Incorrect invalid record')
            else:
                require(r['status'] == 'valid' and r['probabilities'] == p, 'Incorrect validity record')
        paired_statuses[arm] = [{'agent':r['agent'], 'condition':r['condition'], 'status':r['status'],
                                 'finish_reason':r['finish_reason'], 'generated_token_count':r['generated_token_count']} for r in records]
        results[arm] = {condition: dict(valid=sum(r['status'] == 'valid' for r in records if r['condition'] == condition),
            attempted=4, token_cap_hits=sum(r['token_cap_hit'] for r in records if r['condition'] == condition),
            mean_repetition_fourgram_fraction=sum(r['repetition_fourgram_fraction'] for r in records if r['condition'] == condition)/4)
            for condition in CONDITIONS}
        for path in (watchdog_path, summary_path, predictions_path):
            source_bindings[str(path)] = sha(path)
    require(supervisor_elapsed <= contract['policy']['total_wall_seconds'], 'Combined supervisor wall budget exceeded')
    result = dict(status='completed', supervisor_elapsed_seconds=supervisor_elapsed, scope='training-only format diagnosis', results=results, paired_statuses=paired_statuses,
                  prefill_all_models_all_cases_valid=all(results[a]['assistant_prefill']['valid'] == 4 for a in ARMS),
                  next_step='Consider a separately frozen validation protocol only if prefill gate passes; no automatic rerun.',
                  belief_accuracy_evaluated=False, validation_targets_loaded=0, source_bindings=source_bindings)
    write_new(output / 'format-evaluation.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'run', 'report'))
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--arm', choices=ARMS)
    args = parser.parse_args()
    if args.phase == 'run':
        if args.arm is None:
            parser.error('--arm is required for run')
        run(args.run_dir, args.arm)
    else:
        (prepare if args.phase == 'prepare' else report)(args.run_dir)
