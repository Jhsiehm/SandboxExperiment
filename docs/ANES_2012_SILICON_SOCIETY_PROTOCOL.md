# ANES 2012 silicon-sample and society protocol

## The comparison has two baselines, not one

The experiment must keep these designs separate:

1. **Paper replication.** Reproduce Study 2 with the ten published profile variables and
   presidential vote target, and reproduce Study 3's leave-one-question-out interview design.
   This is a silicon-sampling comparison, not a forward forecast.
2. **Election-eve forward prediction.** Freeze public evidence at 2012-11-05, provide only
   permitted pre-election profile answers, and hold post-election answers and certified outcomes
   in the evaluation vault.
3. **Society treatment.** Use the same profiles, questions, evidence, model roster, call budget,
   and seeds as the independent arm, but add bounded peer conversation before a private final
   answer. Conversation is a treatment; it does not replace the independent baseline.

The paper's Study 2 used racial/ethnic identification, gender, age, ideology, party ID, political
interest, church attendance, political discussion, flag-associated patriotism, and state. The
target was `presvote2012_x`. Study 3 used twelve selected 2016 ANES variables and generated one
leave-one-out answer at a time. The new full-question arm is therefore an extension, not an exact
replication.

## Temporal boundary

Election Day was 2012-11-06, so the forward condition uses an information cutoff of 2012-11-05.
Post-election interviews and election results are evaluation-only. The official ANES 2012 file was
released after the election. Pre-election answers extracted from it may be treated as
**contemporaneous private covariates** only when their interview timing is verified; they are not
public election-eve information. The raw ANES file is never mounted in the runtime container.

The existing `sandbox_mode: container` does not put the model process in Docker. It seals the
retrieval sidecar while provider calls and orchestration stay on the host. Accordingly:

- the existing enforceable claim is **cutoff-locked supplied retrieval context**;
- a no-network local/mock runner can be fully container-isolated;
- a hosted modern model cannot be made to forget post-2012 facts in its weights;
- a live hosted-model run needs a narrow provider gateway before it can claim full process egress
  isolation.

Never describe GPT-4.1 mini or another modern hosted model as "knowing only 2012." The accurate
label is "modern model, no tools, supplied context restricted to material dated on or before the
cutoff." Run model-cutoff and evidence ablations separately.

## Full ANES question inventory

The generator inventories every named specification in both official 2012 questionnaires. It
retains phase, section, page, variable, wording, response type, response options, mode, source
hash, and eligibility. The complete inventory includes administrative and routing specifications,
so not every row should be sent to a model. The automated experimental subset excludes:

- restricted or potentially identifying fields;
- interviewer observations, checkpoints, and other administrative items;
- display-only specifications;
- free-text responses;
- unbounded numeric responses with no enumerated answer set;
- rows with no extracted question wording.

This preserves "every question" as an auditable inventory while avoiding silent deletion and
unsafe or statistically incomparable prompts.

## Data zones and allowed flow

```text
Official/replication microdata
            |
            v
      split + hash seal
       /             \
runtime profiles     evaluation vault
(pre fields only)    (post answers/outcomes)
       |                    |
       v                    | opened only after
independent + society       | predictions are sealed
prediction artifacts        |
       \____________________/
                  |
                  v
       aggregate fidelity report
```

Runtime records contain pseudonymous IDs, weights, pre-election fields, collection-timing labels,
and the cutoff. Held-out target names are rejected if they occur as runtime keys. The vault lives
under `data/evaluation-vault/`, which is Git-ignored and prohibited as a container mount.

## Required experiment matrix

At minimum, run matched replications of:

| Arm | Profiles | Frozen evidence | Conversation | Purpose |
|---|---|---|---|---|
| Paper-style independent | actual paper fields | none | no | closest replication |
| Forward independent | pre-election only | matched | no | causal control for society |
| Forward society | same as independent | same pack | bounded rounds | interaction treatment |
| Shuffled profile | shuffled | matched | same as arm | profile dependence |
| Shuffled evidence | same | shuffled eligible pack | same as arm | evidence dependence |
| No evidence | same | none | same as arm | model-prior dependence |

Group assignment, prompt order, evidence pack, and sampling seed must be paired across independent
and society arms. Final answers are private; public messages are not counted as votes. Report
between-replication variance and cluster uncertainty, not just one swarm median.

## Metrics

For the paper baseline, preserve its binary vote correspondence metrics (tetrachoric correlation,
Cohen's kappa, ICC, and proportion agreement) and subgroup reporting. Add weighted aggregate share
error, Brier score when probabilities are available, completion/missingness, distributional
distance, and question-by-question correspondence for the full-question arm. ANES weights are
required for representative population estimates.

The bundled structural pilot reports Brier, agreement, kappa, and vote-share error only to validate
the split/treatment/seal/evaluation machinery. Its heuristic outputs are not scientific findings.

## Local workflow

Place the official pre/post questionnaire PDFs in the ignored source directory, then run:

```bash
psbx experiment anes-question-bank

psbx experiment anes-pilot \
  --config config/anes2012-society.yaml \
  --input data/survey-microdata/anes/2012/source/full_results_2012_2.csv \
  --paper-baseline-input \
    data/survey-microdata/anes/2012/source/full_results_2012_2.csv

# For the official weighted microdata, keep the paper's generated probabilities
# in their own input file rather than treating them as ANES respondent fields.
psbx experiment anes-pilot \
  --config config/anes2012-society-official.yaml \
  --input data/survey-microdata/anes/2012/source/anes_timeseries_2012.dta \
  --paper-baseline-input \
    data/survey-microdata/anes/2012/source/full_results_2012_2.csv

psbx experiment anes-doctor
```

To build and run the provider-free engine with a fully sealed network boundary:

```bash
docker build -f Dockerfile.anes-society -t psbx-anes-society:local .

psbx experiment anes-container-plan \
  --profiles data/runs/anes2012-society-structural-pilot/anes-society/runtime/profiles.jsonl \
  --output data/runs/anes2012-society-structural-pilot/anes-society/container-output
```

Review the printed command before executing it. It uses `--network none`, a read-only root,
dropped capabilities, `no-new-privileges`, bounded memory/CPU/PIDs, one read-only profile mount,
and one output mount. It never mounts the evaluation vault.

The paid live conversational probe is intentionally separate:

```bash
PSBX_ENABLE_PAID_MODELS=1 \
PSBX_MAX_PAID_REQUESTS=100 \
PSBX_MAX_RUN_USD=1 \
psbx experiment anes-live-vote \
  --profiles data/runs/anes2012-society-structural-pilot/anes-society/runtime/profiles.jsonl \
  --output data/runs/anes2012-live-vote-probe/anes-society \
  --run-id anes2012-live-vote-probe \
  --max-agents 12 \
  --rounds 2
```

This path pairs one independent private answer per profile with two public-message rounds and one
private post-conversation answer. Agents see only their own profile and anonymous peer messages;
they never receive evaluation targets and all calls have tools disabled. The preflight reserves
up to 96 requests because every call is allowed one strict-JSON retry. Add `--world-context` only
with a dated JSON pack whose declared cutoff is 2012-11-05; the loader rejects later documents.

This live command still makes provider calls from the host. Its seal therefore records
`full_process_container_isolation: false` and `model_weight_temporal_isolation: false`. It is useful
for the paper-style no-evidence baseline and for plumbing tests, but it is not the final sealed
remote-provider architecture.

## Scope and claims

Results concern aggregate response fidelity under declared treatments. They do not identify actual
people, infer how a named person voted, justify political persuasion, or establish that a swarm is
a literal society. Synthetic/de-identified profiles must remain research artifacts; protected
attributes must not become deterministic political labels or targeting features.
