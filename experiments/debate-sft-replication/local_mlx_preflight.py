"""Development-only MLX preparation and token/masking audit; never reads reserve data."""

import hashlib
import json
from pathlib import Path

from prepare import prepare
from transformers import AutoTokenizer
from mlx_lm.tuner.datasets import ChatDataset


def main():
    root = Path(__file__).resolve().parent
    output = root.parents[1] / "data/local-mlx-pilot"
    model = (output / "model-path.txt").read_text().strip()
    tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True)
    prepared = prepare(root)
    seal = json.loads((root / "preparation-seal.json").read_text())
    report = {"preparation": prepared["audit"], "splits": {}}
    for name, key in (("train", "train"), ("valid", "validation")):
        records = [{"messages": r["messages"]} for r in prepared[key]]
        dataset = ChatDataset(records, tokenizer, mask_prompt=True)
        lengths, targets = [], []
        for record in records:
            tokens, offset = dataset.process(record)
            prefix = tokenizer.apply_chat_template(
                record["messages"][:-1], add_generation_prompt=True, return_dict=False
            )
            assert tokens[:offset] == prefix, "Prompt mask does not match token prefix"
            assert 0 < offset < len(tokens), "Empty prompt or supervised completion"
            lengths.append(len(tokens))
            targets.append(len(tokens) - offset)
        path = output / f"{name}.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
        sealed_name = "train.jsonl" if name == "train" else "validation.jsonl"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == seal["bindings"][sealed_name]
        ordered = sorted(lengths)
        report["splits"][name] = {
            "examples": len(records), "max_tokens": max(lengths),
            "median_tokens": ordered[len(ordered) // 2],
            "p95_tokens": ordered[int((len(ordered) - 1) * .95)],
            "total_tokens": sum(lengths), "supervised_tokens": sum(targets),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "all_prompt_prefix_masks_verified": True,
        }
    report["model"] = json.loads((output / "model-source.json").read_text())
    (output / "preflight.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report["splits"], indent=2))


if __name__ == "__main__":
    main()
