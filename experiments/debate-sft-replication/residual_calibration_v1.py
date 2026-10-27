"""Ninety-two frozen-base forwards; label-free model process for calibration."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def require(ok,message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024**2),b''):
            h.update(block)
    return h.hexdigest()


def write_new(path,value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,indent=2,allow_nan=False)
        stream.write('\n')


def offline():
    for name in list(os.environ):
        if name.upper().endswith('API_KEY') or name.upper() in ('HF_TOKEN','HUGGING_FACE_HUB_TOKEN'):
            os.environ.pop(name)
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_DATASETS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')


def load_prompt_module(path):
    spec=importlib.util.spec_from_file_location('frozen_classifier_prompt',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_profiles(cases,identities):
    require(len(cases)==len(identities)==92,'Expected92profile rows')
    for i,(case,identity) in enumerate(zip(cases,identities)):
        require(set(case)=={'group_id','profile'},'Unexpected casefield; labels forbidden')
        require(set(case['profile'])=={'agent_id','topic','initial_score','initial_text','partners'},'Unexpected profilefield')
        require(identity['index']==i and identity['group_id']==case['group_id'] and identity['agent_id']==case['profile']['agent_id'],'Fold/profile identity mismatch')


def load_contract(output):
    c=read(output/'contract.json')
    require(c['status']=='frozen_residual_calibration_v1','Not frozen')
    for path,expected in c['bindings'].items():
        require(sha(path)==expected,'Binding mismatch: '+path)
    require(c['policy']==read(c['protocol_path']) and c['protocol_path'] in c['bindings'],'Policy mismatch')
    prior=read(c['prior_classifier_contract_path'])
    require(c['prior_classifier_contract_path'] in c['bindings'] and c['model_path']==prior['model_path'],'Base metadata mismatch')
    for path in Path(c['model_path']).iterdir():
        if path.is_file():
            require(str(path) in c['bindings'] and c['bindings'][str(path)]==prior['common_bindings'].get(str(path)),'Basefile mismatch')
    require(c['class_token_ids']==prior['class_token_ids'],'Class order mismatch')
    return c


def prepare(output,folds_path,analysis_python):
    offline()
    from transformers import AutoTokenizer
    output,folds_path=Path(output).resolve(),Path(folds_path).resolve()
    output.mkdir(mode=0o700,exist_ok=False)
    folds=read(folds_path)  # Do not recursively verify source_bindings: includes fittinglabels.
    profiles_path=Path(folds['source_training_cases_path'])
    require(sha(profiles_path)==folds['source_training_cases_sha256'],'Training profile checksum mismatch')
    cases=read(profiles_path)
    validate_profiles(cases,folds['row_identities'])
    require(len(folds['folds'])==5,'Expected five folds')
    require(sorted(i for f in folds['folds'] for i in f['validation_row_indices'])==list(range(92)),'Incomplete OOFcoverage')
    policy_path=HERE/'residual-calibration-v1.protocol.json'
    policy=read(policy_path)
    prior_path=ROOT/'data/local-mlx-pilot/outcome-classifier-v1-20261023/contract.json'
    prior=read(prior_path)  # Onlymetadata, neveroldfitlabels orinternaloutcomes.
    prompt_source=HERE/'classifier_v1.py'
    require(sha(prompt_source)==prior['common_bindings'][str(prompt_source)],'Original classifier promptsource changed')
    prompt_module=load_prompt_module(prompt_source)
    model=Path(prior['model_path'])
    model_files=[p for p in sorted(model.iterdir()) if p.is_file()]
    for path in model_files:
        require(sha(path)==prior['common_bindings'].get(str(path)),'Original modelbytes changed')
    tokenizer=AutoTokenizer.from_pretrained(str(model),local_files_only=True)
    ids=prompt_module.class_token_ids(tokenizer)
    require(ids==prior['class_token_ids'],'Class mapping changed')
    prompts=[]
    for i,case in enumerate(cases):
        messages=prompt_module.messages(case)
        tokens=tokenizer.apply_chat_template(messages,add_generation_prompt=True,return_dict=False)
        require(0<len(tokens)<=policy['runtime']['max_context_tokens'],'Contextlimit; no truncation')
        prompts.append(dict(row_index=i,group_id=case['group_id'],agent_id=case['profile']['agent_id'],
            initial_score=case['profile']['initial_score'],messages=messages,prompt_tokens=tokens))
    write_new(output/'prompts.json',prompts)
    command=[str(analysis_python),'-c','import json,sys,numpy,scipy; print(json.dumps(dict(python=sys.version,numpy=numpy.__version__,scipy=scipy.__version__)))']
    analysis_env=json.loads(subprocess.check_output(command,text=True))
    write_new(output/'analysis-environment.json',analysis_env)
    bound=[Path(__file__).resolve(),policy_path,prompt_source,HERE/'local_watchdog.py',
        ROOT/'scripts/residual_calibration_solver.py',ROOT/'scripts/run_residual_calibration.py',
        ROOT/'data/local-mlx-pilot/requirements.lock',prior_path,profiles_path,folds_path,
        output/'prompts.json',output/'analysis-environment.json',profiles_path.parent/'manifest.json',
        prior_path.parent/'internal-prediction-seal.json',*model_files]
    contract=dict(status='frozen_residual_calibration_v1',policy=policy,protocol_path=str(policy_path),
        bindings={str(p):sha(p) for p in bound},model_path=str(model),class_token_ids=ids,
        internal_prior_run=str(prior_path.parent),prepared_data_path=str(profiles_path.parent),
        prior_classifier_contract_path=str(prior_path),prompt_source_path=str(prompt_source),
        profiles_path=str(profiles_path),folds_path=str(folds_path),prompts_path=str(output/'prompts.json'),
        analysis_environment=analysis_env,
        analysis_label_metadata=dict(training_targets_path=folds['source_training_targets_path'],
                                    training_targets_sha256=folds['source_training_targets_sha256']),
        internal_existing_source_metadata=dict(prediction_seal_path=str(prior_path.parent/'internal-prediction-seal.json'),
                                              prediction_seal_sha256=sha(prior_path.parent/'internal-prediction-seal.json')),
        fit_labels_loaded_by_prepare=False,internal_outcomes_loaded=False,outer_validation_loaded=False)
    write_new(output/'contract.json',contract)
    print(json.dumps(dict(status='frozen',run=str(output),forward_calls=92,contract_sha256=sha(output/'contract.json'))))


def swap_mib():
    raw=subprocess.check_output(['sysctl','-n','vm.swapusage'],text=True)
    match=re.search(r'used\s*=\s*([\d.]+)([KMG])',raw)
    require(match is not None,'Unparseable system swap')
    return float(match[1])*{'K':1/1024,'M':1,'G':1024}[match[2]]


def run(output):
    offline()
    import mlx.core as mx
    from mlx_lm import load
    output=Path(output).resolve()
    c=load_contract(output)
    p=c['policy']['runtime']
    module=load_prompt_module(c['prompt_source_path'])
    prompts=read(c['prompts_path'])
    require(len(prompts)==92 and [r['row_index'] for r in prompts]==list(range(92)),'Malformed sealed prompts')
    directory=output/'base-fit'
    directory.mkdir(mode=0o700,exist_ok=False)
    mx.set_cache_limit(256*1024**2)
    mx.reset_peak_memory()
    mx.random.seed(p['seed'])
    baseline_swap,started=swap_mib(),time.monotonic()
    model,tokenizer=load(c['model_path'])  # No adapter.
    model.eval()
    require(module.class_token_ids(tokenizer)==c['class_token_ids'],'Class mapping mismatch')
    records=[]
    failure=None
    try:
        for item in prompts:
            require(time.monotonic()-started<p['wall_seconds'],'Walltime cap')
            values=module.probabilities_from_logits(model(mx.array(item['prompt_tokens'])[None])[0,-1,:],c['class_token_ids'])
            record=dict(arm='base',row_index=item['row_index'],group_id=item['group_id'],agent_id=item['agent_id'],
                initial_score=item['initial_score'],**values,class_token_ids=c['class_token_ids'],
                prompt_sha256=hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest(),
                prompt_tokens=len(item['prompt_tokens']),peak_allocated_bytes=mx.get_peak_memory())
            records.append(record)
            with (directory/'predictions.jsonl').open('a') as stream:
                stream.write(json.dumps(record,allow_nan=False)+'\n')
            require(mx.get_peak_memory()<=p['mlx_peak_gib']*1024**3,'MLX memory cap')
            require(swap_mib()-baseline_swap<=p['swap_growth_mib'],'System swapgrowth cap')
            mx.clear_cache()
            if len(records)%20==0:
                print(f'Frozen base {len(records)}/92 completed',flush=True)
    except Exception as exc:
        failure=f'{type(exc).__name__}: {exc}'
    result=dict(status='completed' if failure is None and len(records)==92 else 'failed',failure=failure,
        completed=len(records),contract_sha256=sha(output/'contract.json'),
        predictions_sha256=sha(directory/'predictions.jsonl') if records else None,
        elapsed_seconds=time.monotonic()-started,peak_allocated_bytes=mx.get_peak_memory(),
        baseline_swap_mib=baseline_swap,final_swap_mib=swap_mib(),fit_labels_loaded=False,internal_outcomes_loaded=False)
    write_new(directory/'summary.json',result)
    print(json.dumps(result),flush=True)
    if failure:
        raise SystemExit(2)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('prepare','run'))
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--folds',type=Path,default=ROOT/'data/local-mlx-pilot/residual-calibration-v1-data/folds-v3.json')
    parser.add_argument('--analysis-python',type=Path,default=Path('/Users/joshua/Documents/ChatGPT/Policy Sim/.venv/bin/python'))
    args=parser.parse_args()
    if args.phase=='prepare':
        prepare(args.run_dir,args.folds,args.analysis_python)
    else:
        run(args.run_dir)
