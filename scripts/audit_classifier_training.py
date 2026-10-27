"""Read-only artifact audit; no model loading, training, prediction or new labels."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import numpy as np


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024**2),b''):
            h.update(block)
    return h.hexdigest()


def histogram(rows,key):
    return dict(sorted(Counter(str(row[key]) for row in rows).items()))


def audit(root):
    root=Path(root).resolve()
    contract=json.loads((root/'contract.json').read_text())
    fit=json.loads((root/'fit-tokens.json').read_text())
    metrics=[json.loads(line) for line in (root/'training/metrics.jsonl').read_text().splitlines()]
    seed=contract['policy']['seed']
    # Installed trainer sorts stable ascending token length, then permutes batch indices.
    ordered=sorted(range(len(fit)),key=lambda i:len(fit[i]['prompt_tokens'])+1)
    permutation=np.random.RandomState(seed).permutation(len(ordered))
    selected=[ordered[int(i)] for i in permutation[:52]]
    seen=[fit[i] for i in selected]
    unseen=[row for i,row in enumerate(fit) if i not in selected]
    blocks=[]
    for start in range(0,52,4):
        indices=selected[start:start+4]
        blocks.append(dict(optimizer_update=start//4+1,rows=indices,
            classes=[fit[i]['target_class']+1 for i in indices],
            mean_preupdate_example_loss=float(np.mean([r['train_loss'] for r in metrics[start:start+4]]))))
    losses=np.array([row['train_loss'] for row in metrics])
    path=root/'training/adapters/adapters.safetensors'
    with path.open('rb') as stream:
        header_length=struct.unpack('<Q',stream.read(8))[0]
        header=json.loads(stream.read(header_length))
    tensor_report=[]
    for name,info in header.items():
        if name=='__metadata__':
            continue
        if info['dtype']!='F32':
            raise ValueError('Unexpected adapter dtype')
        tensor=np.memmap(path,dtype='<f4',mode='r',offset=8+header_length+info['data_offsets'][0],shape=tuple(info['shape']))
        tensor_report.append(dict(name=name,shape=info['shape'],elements=tensor.size,
            finite=bool(np.isfinite(tensor).all()),nonzero=int(np.count_nonzero(tensor)),
            squared_norm=float(np.sum(np.square(tensor,dtype=np.float64),dtype=np.float64))))
    counts_by_leaf={}
    for leaf in ('lora_a','lora_b'):
        subset=[row for row in tensor_report if row['name'].endswith('.'+leaf)]
        counts_by_leaf[leaf]=dict(tensors=len(subset),elements=sum(r['elements'] for r in subset),
            all_finite=all(r['finite'] for r in subset),nonzero_elements=sum(r['nonzero'] for r in subset),
            l2_norm=sum(r['squared_norm'] for r in subset)**.5)
    adapter_checkpoint=root/'training/adapters/0000052_adapters.safetensors'
    seal=json.loads((root/'candidate-seal.json').read_text())
    integrity={path:sha(path)==expected for path,expected in seal['bindings'].items()}
    return dict(scope='Saved training artifacts only; no model execution or holdout target access',
        contract_sha256=sha(root/'contract.json'),candidate_seal_bindings_verified=all(integrity.values()),
        microsteps=len(metrics),iterations_contiguous=[m['iteration'] for m in metrics]==list(range(1,53)),
        inferred_optimizer_updates=13,optimizer_update_evidence='Public trainer updates iff iteration%4==0; optimizer state was not serialized.',
        cumulative_supervised_examples=metrics[-1]['trained_tokens'],
        sampling=dict(status='Reconstruction conditional on unchanged NumPy RNG state after frozen seed; no sampled IDs were logged',
            seed=seed,sorted_indices=ordered,selected_row_indices=selected,unique_seen=len(set(selected)),
            total_available=len(fit),unseen=len(unseen),coverage_fraction=len(set(selected))/len(fit),
            groups_seen=len({r['group'] for r in seen}),groups_available=len({r['group'] for r in fit}),
            selected_class_counts=histogram(seen,'target_class'),available_class_counts=histogram(fit,'target_class'),
            unseen_class_counts=histogram(unseen,'target_class'),class_count_indexing='0=A ...5=F',
            selected_group_counts=histogram(seen,'group'),optimizer_blocks=blocks),
        loss=dict(mean=float(losses.mean()),median=float(np.median(losses)),minimum=float(losses.min()),maximum=float(losses.max()),
            first13_mean=float(losses[:13].mean()),last13_mean=float(losses[-13:].mean()),
            first26_mean=float(losses[:26].mean()),last26_mean=float(losses[-26:].mean()),
            finite=bool(np.isfinite(losses).all()),learning_rates=sorted(set(r['learning_rate'] for r in metrics)),
            interpretation='Different training cases at each step: these are not repeated fixed-set evaluations or evidence of convergence.'),
        adapter=dict(tensors=len(tensor_report),elements=sum(r['elements'] for r in tensor_report),by_leaf=counts_by_leaf,
            layers=sorted({int(r['name'].split('.')[2]) for r in tensor_report}),
            checkpoint52_equals_final=sha(adapter_checkpoint)==sha(path),sha256=sha(path),
            live_before_save_vs_reloaded_prediction_equivalence='Not measured; no pre-save model outputs were recorded.'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=audit(args.run)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
        stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('sampling','adapter')},indent=2))
    print(json.dumps({k:v for k,v in result['sampling'].items() if k not in ('optimizer_blocks','selected_row_indices','sorted_indices','selected_group_counts')},indent=2))
    print(json.dumps(result['adapter'],indent=2))
