# Human emulation: research direction and evidence

## Open implementations and Aaru-inspired development — 2026-10-20

Decision: retain our isolated individual-prediction harness for the next comparison. Evaluate AgentSociety as a later interaction backend, not as a presumed accuracy improvement. This is a design update; no new model experiment or framework installation is represented by it.

[AgentSociety](https://github.com/tsinghua-fib-lab/agentsociety) now recommends version 2, with modular environments, Ray execution, tracing and replay. The repository states Apache-2.0 except its legacy commercial folder. The [original research](https://arxiv.org/abs/2502.08691) reports large-scale simulation and selected real-world comparisons, which do not establish ANES individual prediction accuracy or an advantage over our baseline. Distributed workspaces are not equivalent to our per-call container isolation. Before integration, pin a revision, inspect dependencies and retain our broker, private payload boundaries and independent evaluator.

[Generative Agents](https://github.com/joonspk-research/generative_agents) supplies an Apache-2.0 town simulation with memory and interaction; its demonstrated believability is a different endpoint from held-out respondent fidelity. [Centaur's released adapter](https://huggingface.co/marcelbinz/Llama-3.1-Centaur-70B-adapter) is a behavioral model under the Llama 3.1 license, not an unrestricted open-source Aaru clone; its documented setup requires 80 GB GPU memory and task-specific choice formatting. Treat it as a future behavioral-model comparator, not a drop-in survey respondent.

[Aaru's public description](https://aaru.com/simulation) combines public, licensed and customer evidence and models joint traits. Its [September evaluation](https://aaru.com/publications/population-simulation-at-the-replication-floor-research) describes independent agent answers and evaluates univariate answer shares. The proprietary model, complete training recipe and data are not supplied by these sources. Our adaptation is inspired by these disclosed principles, not a reproduction of Aaru or its reported scores.

Concrete next comparison:

1. Retain actual ANES respondent rows and weights. They preserve observed within-person trait combinations; independently sampling demographic columns would discard that information. Do not describe the selected Ohio cohort as representative of all Ohio without a sampling assessment.
2. Separate the reduced-existing-evidence arm from the same evidence plus measured additional covariates. Preserve dates, source labels, missingness and the distinction between measured personal exposure and general historical availability. Keep context and interaction disabled in this first comparison.
3. Generate independent probability vectors using the same model, settings and paired people as comparators. Use prevalence and party baselines. Test a calibrated statistical-agent mixture using development-only nested cross-validation: tune mixing strength inside training folds, score outer held-out people, and leave the 50-person reserve unopened.
4. Retain individual weighted Brier as the primary objective. Add weighted answer-share MAE and total variation distance, subgroup diagnostics, and cross-question association checks where sample sizes permit. Aggregate accuracy cannot substitute for individual accuracy; a product of marginal probabilities does not identify a person's joint response distribution.
5. Freeze candidate, acceptance thresholds, folds, budget and source hashes before new calls. Use the existing independent-development thresholds as development screening only; a final validation protocol must address sample size and uncertainty before consuming the reserve. No automatic promotion from the previously inspected 24 cases.
6. Only after individual validation, compare an AgentSociety-backed interaction condition against the identical independent agent on held-out human discussion groups. Pin topology, exposure, time/turn budget and model; report persistence, false movement, disagreement and probability error. Keep all framework-generated explanations separate from observed human evidence.

No new licensed behavioral data or synthetic personas are needed for steps 1–4. Further data acquisition should target measured prior attitudes, exposure and longitudinal outcomes that resolve specific validation failures.

### Execution stages agreed on 2026-10-20

The live development comparison is `anes2012-ohio-profile-ablation-development-v1`: all 120 previously inspected development respondents, four profile definitions, two independent repeats, five outer respondent folds and four inner folds. The current calibration is a tuned mixture of agent probabilities and a party-conditioned statistical predictor, not an independently trained universal behavioral model. All repeats of one person remain in the same fold. Direct scores use the mean probability vector across repeats; compare arms within this run rather than equating this estimator with earlier mean-repeat-loss scores.

Subsequent stages are conditional research tasks, not already executed experiments:

- **External validation:** freeze one candidate and its statistical comparator before opening the 50-person reserve once. Size a larger external cohort from development paired-loss variance and the predefined practically useful improvement; account for survey weighting and subgroup coverage. Use disjoint respondents in another geography first, then a harmonized survey wave for temporal transport. Check item wording, response scales, measurement timing and preprocessing equivalence before pooling years. A new state does not remove pretrained historical knowledge or establish policy intervention validity.
- **Historical context:** compare no context with a balanced topic-specific pack restricted to material available by the respondent's interview completion date. Personal exposure remains unknown unless measured. Any assumed exposure is a separately labeled experimental condition. Freeze retrieval, source balance, length and outcomes before comparison; do not retrieve by held-out target answers.
- **Targeted data:** prioritize recorded earlier issue positions, longitudinal changes and measured exposure. Admit each new field through a target-alias and timing review, then a separate feature-block comparison. Do not fill missing biographies using generated explanations.
- **Interaction:** after the individual candidate is fixed, compare independent, private reflection, actual-human-message replay and generated conversation on separate human discussion groups. Partition by group and topic, match budgets where possible, and evaluate both change and persistence. AgentSociety is a potential execution backend; its use must retain our per-agent container and message-access checks. Framework adoption does not itself pass the fidelity criterion.

The platform cleanup, implementation audit and frozen-artifact preservation checks are recorded in [the implementation audit](IMPLEMENTATION_AUDIT_20261020.md). No later-stage result should be inferred from preparation or successful software tests.

Reviewed 2026-10-14. This is a research assessment, not a claim that this project can reconstruct a person's full psychology.

## The north star

Predict held-out human responses and changes, with calibrated uncertainty, using only information that would have been available at the prediction time. Evaluate individuals, distributions, and responses to interventions separately. Agent interaction is a candidate mechanism whose incremental value must be demonstrated.

Three objectives must not be conflated:

1. **Individual reconstruction:** Given observed prior answers and circumstances, predict a person's unseen answers. ANES is useful here.
2. **Social dynamics:** Given prior beliefs and a network/exposure process, predict who changes, who remains unchanged, and how disagreement evolves. Requires actual longitudinal interaction records.
3. **Policy reception:** Predict responses under specified policies or information exposures. Strong validation requires held-out randomized policy-vignette or other intervention data; cross-sectional correlations do not establish counterfactual effects.

High vote accuracy alone does not establish any comprehensive reconstruction. Stable party allegiance can make vote prediction easier than other behaviors. A model may match a population mean while misrepresenting individuals, variance, covariance, minority views, or treatment effects.

Short conversations test immediate updating, not lifelong socialization. Family, institutions, repeated exposure, material incentives, identity, and relationships operate over different timescales. An initial recorded belief already reflects some of that history, but the history cannot be uniquely recovered from the belief. Different decision processes can produce the same survey answer. Treat a reconstructed respondent as a probabilistic model constrained by observations, not a recovered mind or a uniquely identified causal explanation.

Self-reported policy preferences also differ from behavior under real costs or constraints. A future benchmark should distinguish expressed support, knowledge, attention, participation, and actual choices instead of treating them as interchangeable measures of human fidelity.

## Primary literature

| Work | Evidence | Implication for this project |
|---|---|---|
| Argyle et al., *Out of One, Many*, Political Analysis (2023), [paper](https://doi.org/10.1017/PAN.2023.2) | Survey-conditioned language models can reproduce some response patterns and subgroup variation. | Observed conditioning is promising; this does not validate an invented social network or universal individual fidelity. |
| Park et al., *Generative Agents*, UIST (2023), [paper](https://arxiv.org/abs/2304.03442) | Memory, reflection, planning, and interaction produced believable behavior in a small simulated town. | Useful architecture. Believability and emergent coordination are different endpoints from predictive accuracy against actual people. |
| Park et al., *LLM Agents Grounded in Self-Reports Enable General-Purpose Simulation of Individuals*, revised preprint (2026), [v3](https://arxiv.org/abs/2411.10109v3) | Interview/survey grounding improved individual simulation relative to demographics alone, evaluated against a human repeat-response benchmark. | Invest in observed personal evidence. Relative-to-test-retest performance is not raw universal accuracy, and this is not a swarm advantage test. |
| Chuang et al., *Simulating Opinion Dynamics with Networks of LLM-based Agents*, Findings NAACL (2024), [paper](https://aclanthology.org/2024.findings-naacl.211/) | Default dynamics favored convergence; prompted confirmation bias changed the resulting dynamics. | A convincing polarization or consensus pattern can be induced by prompt design. It still needs human validation. |
| *Is this the real life? Is this just fantasy? The Misleading Success of Simulating Social Interactions With LLMs*, EMNLP (2024), [paper](https://aclanthology.org/2024.emnlp-main.1208/) | Performance depended strongly on information access; realistic information asymmetry was harder than omniscient settings. | Enforce private state and actual exposure boundaries. Do not give every agent everyone's biography or opinions. |
| *AgentSociety: A Parallelized Framework for Simulating Large-Scale LLM Agents with Realistic Environments and Interactions*, ACL Industry (2025), [paper](https://aclanthology.org/2025.acl-industry.94/) | Large-scale environment and interaction infrastructure is feasible. | Engineering scale is not evidence that simulated people or policy responses are accurate. Distinguish this peer-reviewed framework from broader related preprints. |
| Chuang et al., *DEBATE*, revised preprint v6 (2026), [paper](https://arxiv.org/abs/2510.25110v6) | Human initial/final opinions and actual group conversations provide an empirical test of opinion dynamics; zero-shot agents can overconverge. | This supplies missing interaction ground truth. Our small pilot uses this dataset, but is not a full replication of the authors' benchmark. |
| Bisbee et al., *Synthetic Replacements for Human Survey Data?*, Political Analysis (2024), [paper](https://www.cambridge.org/core/journals/political-analysis/article/synthetic-replacements-for-human-survey-data-the-perils-of-large-language-models/B92267DC26195C7F36E63EA04A47D2FE) | Aggregate agreement can coexist with deficient variability and relationships; output also changes with prompts and model versions. | Evaluate joint patterns, repeatability, and model drift. Aggregate fit is insufficient. |
| Ashokkumar, Hewitt, Ghezae & Willer, *Large language models can predict the results of social science experiments*, Nature (2026), [published article](https://www.nature.com/articles/s41586-026-10742-x) | Published archive: 70 survey experiments, 469 effects, 119,330 participants; predictions tracked effects but systematically overestimated magnitude. A second archive of 15 megastudies/606 effects was harder. | Promising route toward intervention forecasts, with calibration and external human validation. Does not establish a benefit from swarms. Published counts differ from the older author webpage/preprint. |
| Binz et al., *A foundation model to predict and capture human cognition*, Nature (2025), [paper](https://www.nature.com/articles/s41586-025-09215-4) | Fine-tuning on trial-level human choices improved prediction across held-out participants and several novel tasks. | Behavioral training data can improve the individual model. This is distinct from generic chat instruction-following and does not establish political or social-network validity. |

## What our ANES results currently justify

The larger reserved-validation run used 120 previously unprompted Ohio respondents, two repeats, and sparse versus rich observed profiles. Rich profiles slightly improved vote Brier but worsened health-law and gun-policy scores. Average Brier changed from .234631 to .238807; the paired change interval crossed zero. The predeclared improvement gate failed.

This is useful negative evidence against assuming that adding profile fields automatically improves emulation. It does not show that personal evidence is useless. Added fields can be weak, poorly represented, redundant, or cause the model to overweight a feature. Data quantity, representation, inference, and evaluation are distinct possible failure sources. No one of them has been isolated as the cause.

The tested rich profile adds education, personal finances, insurance, economic perceptions, and media-use fields. It is not a comprehensive reconstruction of issue-specific decision processes. Existing variable-label audits identify possible next candidates: political attention, gun ownership, gun-issue importance, self-reported health, government/social trust, and political knowledge. These still need routing, missingness, item-order, and target-leakage audits before use. Health-law support-strength/summary fields reveal the target and remain excluded. Post-election discussion and most-important-problem items cannot be silently treated as pre-election inputs.

The policy targets in the current ANES test are withheld contemporaneous pre-election opinions, whereas vote is a later reported outcome. Performance on the former should be described as response reconstruction, not prospective policy-change prediction. A PRE variable label alone does not establish that an item preceded every target within an interview.

Earlier historical-pack and dialogue pilots also did not establish broad benefit. Giving a person information that existed historically is not the same as showing they encountered it, remembered it, believed it, or considered it relevant. A modern model additionally has pretrained knowledge that Docker cannot erase.

The additional 50 ANES reserve IDs remain untouched. The DEBATE pilot uses a separate dataset, not this reserve.

## New interaction evidence from this session

The completed 32-person DEBATE pilot improved RPS from .15808 under private reflection to .12166 under generated conversation (23.0% relative reduction). Its eight-group bootstrap interval for the paired difference was [-.07418, -.00178]. Real incoming messages scored .11116. This is a positive exploratory signal for further interaction research. However, swarm superiority over persistence was uncertain, persistence had lower expected-rating absolute error, and group-dispersion and conversational-style diagnostics remain problematic. The [complete pilot results](DEBATE_ISOLATED_PILOT_RESULTS.md) preserve these tradeoffs. The new evidence supports confirmation on unseen groups; it does not establish that swarms generally improve human fidelity.

## What a grounded individual profile should represent

Use a schema that preserves provenance, timing, and uncertainty rather than a polished fictional biography:

- Observed prior beliefs: exact item, scale, answer, date, and source.
- Material circumstances: only recorded facts, with missingness retained.
- Topic salience, trust, knowledge, and exposure: distinguish measured values from hypotheses.
- Constraints and opportunities: what choices and information were actually available.
- Memory: information personally received; not everything the researcher knows.
- Uncertainty: separate unknown attributes, uncertain answers, and genuinely ambivalent preferences.

Do not infer that a demographic category dictates a belief. Do not turn every inconsistent answer into a coherent ideology. Human inconsistency, weak preferences, selective attention, misunderstanding, fatigue, and nonresponse may be part of the target behavior. Hypothesized mechanisms must be tested rather than inserted because they sound psychological.

For historical context, maintain four separate concepts: information existed; this person was exposed; they trusted/understood it; it affected a decision. A general historical evidence pack supports the first at most unless there is respondent-specific evidence for the others.

## Bounded self-improvement

Self-improvement means a reproducible model-selection process against external human observations, not agents rewarding one another for persuasive or believable explanations.

1. Partition by person/group and, where possible, topic/time. Keep development, validation, and a final untouched test distinct. An inspected test becomes development evidence for subsequent iterations.
2. Specify one falsifiable hypothesis per change. Examples: evidence-linked profiles reduce unsupported certainty; measured exposure improves updating; bounded attention reduces excessive convergence.
3. Freeze candidate code, prompts, model settings, allowed information, primary metric, secondary guardrails, budget, and acceptance rule before running.
4. Compare identical people across conditions: persistence/statistical baseline; independent agent; matched private reflection; interaction; actual-message replay as a diagnostic. Match compute where the contrast requires it and report remaining differences.
5. Score with proper probabilistic metrics and cluster uncertainty at the social group. Report individual error, calibration, change magnitude/direction, false movement, disagreement, subgroup errors, and cost. Do not treat repeated model samples as additional human participants.
6. Promote only after a predefined meaningful improvement survives held-out groups/topics and repeat runs without unacceptable calibration or heterogeneity losses. Calibrate a practical effect-size threshold from development data and research needs; do not select it after seeing the test.
7. Record failures and stop on exhausted budget, integrity failures, or missing information. An automated loop must not silently search prompts until the reserve looks good.

Repeated seeds measure model stochasticity, not representativeness of the human sample. Larger samples of simulated agents do not shrink model bias. Human repeat-response reliability gives context for attainable fidelity, but is not permission to claim that simulated people are interchangeable with respondents.

Useful next controls, specified before interpreting this pilot, include an initial-profile-only LLM with no repeated reflection; an empirical ordinal transition baseline fitted on development groups; and length-matched shuffled-message exposure. The transition baseline can model both persistence and ordinary response noise, making it stronger than assigning probability one to the initial score. Shuffle only within a predefined development design, and preserve topic/length rules so it answers a clear information-content question. These controls are proposed, not executed in the present pilot.

## Add data selectively

Adding interaction records is justified now because ANES cross-sections cannot answer whether invented conversation predicts real social updating. That is a change in the kind of evidence, not merely its volume.

For personal reconstruction, first diagnose rich-profile failures on existing development data. Then add fields with a defensible pathway to the specific outcome: prior issue attitudes, salience, trust, actual exposure, or longitudinal answers. Ablate feature groups. Avoid broad unstructured historical dumps and invented personal narratives.

For eventual policy reception, add licensed intervention datasets with known treatment assignment, timing, stimuli, outcomes, and population. Hold out entire experiments. Predict aggregate response distributions and treatment contrasts, assess magnitude calibration and transport to new populations, and validate prospectively against people. A cross-sectional vote benchmark is an initial component, not the final test.

## Isolation and reproducibility

Each pilot turn is prepared in a fresh non-root Docker container with no network, read-only root, no mounts or credentials, dropped capabilities, no-new-privileges, and resource limits. The only input is that agent's permitted state. The host broker sends the resulting prompt to remote inference. This enforces an input boundary; it does not containerize the remote LLM, remove pretrained knowledge, or protect against a malicious trusted host.

Frozen source/image/input hashes and prediction seals support local auditing. Clean-checkout portability remains a separate task: dependency locking, portable paths, reviewed source commits, and distributable images need independent verification. Dataset research-only licensing also limits downstream reuse.
