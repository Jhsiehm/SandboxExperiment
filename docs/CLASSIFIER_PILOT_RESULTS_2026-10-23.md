# Six-category classifier pilot — 2026-10-23

The fresh, task-aligned candidate produced complete finite probability vectors but failed the internal predictive-quality gate. It was not promoted to outer validation or social simulation. This is a negative development result, not proof that larger task-aligned models cannot work.

## What changed

The earlier message-only adapter could not produce valid belief distributions; a separate prefix diagnostic also failed. Before freezing this new experiment, the team considered one-hot JSON imitation and chose the reviewer's stronger categorical objective. A fresh adapter starts from the pinned 4-bit Llama 3.1-8B base. It learns cross-entropy over six fixed single-token labels A-F, mapped to recorded categories 1–6. The training target is one observed final category. Prediction uses float32 softmax over the same six logits at the first assistant position. Validity is mathematical, not a claim that formatting or calibrated human beliefs were learned.

## Training and isolation

A deterministic five-group hash selection, expanded to include shared topics, left 23 fitting groups / 92 labeled records and 6 internal groups / 24 people. Supplied participant IDs, groups and topics have zero internal overlap. All records remain development data; prior investigators and diagnostics have seen some of this material. Original outer-validation CSVs and outcome files were not used.

The fixed new adapter received 52 microsteps / 13 optimizer updates, batch 1 and accumulation 4, rank 8 across 16 layers, learning rate 0.00005 and seed 20261023. There was no held-out monitoring, checkpoint choice, resume from the failed adapter, extra candidate, or retry. The final checkpoint alone was evaluated. It took 43.78 seconds with peak MLX allocation 5,475,067,092 bytes (about 5.10 GiB). System swap did not increase across training. Native MLX allocations and sampled process RSS are not whole-machine memory or sandbox guarantees.

Training and inference verify distinct bindings. Neither reads internal outcomes. Preparation verifies raw TRAIN sources and extracts the last numeric post-opinion category only when its event order is after that person's initial event. The evaluator accessed internal targets only after both 24-case prediction files, candidate weights, source, baseline and watchdog artifacts passed admission and prediction sealing. The statistical transition baseline used the same 23 fitting groups / 92 people.

## Internal results

Equal-group normalized ranked probability score (lower better):

- Base: 0.184574.
- New candidate: 0.216049.
- Point-mass persistence: 0.133333.
- Training-only Laplace-one transition: 0.124716.

Candidate minus base is +0.031475, exceeding the predeclared maximum worsening of +0.02. Three groups improved and three worsened; individual group differences are all retained in internal-evaluation.json. Change-event Brier improved slightly, from 0.397598 to 0.379312, but the primary RPS gate failed. Expected-category MAE worsened from 1.332604 to 1.511860. Neither secondary result replaces the frozen decision rule.

All 48 inference records were complete and finite. The mean full-vocabulary probability mass on the six label tokens was 0.984780 for base and 0.654332 for candidate. Restricted-class loss does not constrain that outside-class mass, so these normalized vectors must be described as conditional six-choice predictions, not unrestricted next-token confidence or proven calibration.

## Verification and decision

Three agents prepared and audited data, implemented training/prediction, and reviewed the protocol. The coordinator implemented/integrated the separate evaluator and executed the local runs. Independent reviews passed. Six MLX classifier tests, six preparation tests, eight evaluator tests and nine viewer tests passed (29 total); JS syntax and diff checks passed. No paid API calls, downloads, reserve access or new outer-validation predictions occurred.

Keep this candidate and failure frozen. Do not expand to social simulation, silently fall back to base predictions, or tune another candidate against these internal outcomes. A further attempt should begin with a new declared design, using the strong statistical baseline as the reference; more steps alone are not justified by this result. Neither this small pilot nor earlier message-loss improvements establish human simulation fidelity.

Artifacts: data/local-mlx-pilot/outcome-classifier-v1-20261023/{contract.json,candidate-seal.json,internal-prediction-seal.json,internal-evaluation.json,decision.json}, frozen-source/, training/, internal/ and watchdog summaries. Contract SHA256: d337a209357e71e07a0aa4b7460ce23f57b82685a08cae65c69e8362e1dffbbc.
