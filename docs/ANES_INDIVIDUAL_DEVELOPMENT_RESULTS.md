# Individual-agent development results — 2026-10-20

Run: `anes2012-ohio-individual-development-20261020`.

**Decision: retain focused direct prediction as a development candidate; do not promote it as a validated improvement. Private evidence review has not earned its extra step. The simple party baseline remains the strongest aggregate comparator in this sample.**

## Completed comparison

24 previously inspected Ohio development respondents, two repeats, one GPT-4.1-mini model. Four agent conditions: sparse direct, existing rich direct, focused direct, focused with a brief private evidence review. No conversation or historical pack. Statistical baselines fit on the other 96 development respondents, excluding all 24 evaluated people. The 50-person reserve is excluded from both sets.

The focused profile has 15 observed fields: eight original fields; personal-finance change, insurance and retrospective economic perception; and measured health, gun ownership, political attention and social trust. All four additional fields are observed for all 24 people. This changes both field selection and available evidence, so it does not isolate a causal contribution from any individual field.

## Scores

Weighted half-multiclass Brier; lower is better. Macro averages the three task scores equally. Repeated forecast losses are averaged within person. These are development estimates, not fresh-holdout results.

| Condition | Vote | Health law | Gun policy | Macro |
|---|---:|---:|---:|---:|
| Training prevalence | .27717 | .31095 | .30123 | .29645 |
| Party-smoothed baseline | .23429 | .22863 | .28735 | **.25009** |
| Sparse direct | .23720 | **.20982** | .35505 | .26736 |
| Rich direct | **.23023** | .21068 | .37407 | .27166 |
| Focused direct | .23547 | .21145 | .33296 | **.25996** |
| Focused with private review | .23454 | .23412 | .32937 | .26601 |

The primary focused-minus-rich contrast was **−.01170**, approximately 4.3% lower aggregate error. Its paired respondent-bootstrap 95% interval was **[−.04104,+.01600]**, crossing zero. The predefined development signal gate failed. Improvement magnitude and per-task regression thresholds passed, but uncertainty did not exclude no improvement.

Focused review minus focused direct was **+.00605**, interval [−.02596,+.03189]. Review scored worse overall, especially for health law, but the interval does not establish general harm. Focused direct minus party baseline was +.00987, interval [−.03380,+.05426]; no agent superiority over that baseline is established.

Twenty people had scorable vote outcomes;24 had each policy outcome. Survey-weighted effective sample sizes were only 12.18 and 14.62 respectively. The bootstrap is conditional on this small development subset and does not model the full ANES survey design. One model and two stochastic repeats provide limited robustness evidence.

## What the failures show

**The focused profile's gain is mainly gun-policy prediction.** Relative to rich direct, gun Brier improved by .04111, whereas vote worsened by .00524 and health law by .00077. Adding relevant observations is a plausible explanation, but reducing unrelated inputs is another; this comparison cannot distinguish them.

**Gun-policy response distributions remain badly mismatched.** Nineteen of 24 people selected keeping rules the same, four selected more difficult, and one selected easier. Weighted shares were 88.45%,10.43%,1.13%, respectively. Focused direct assigned only 41.97% average probability to keeping rules the same, while rich direct assigned 36.48%. Focused direct still assigned 46.64% to more difficult. These are properties of this selected sample, not estimates of all Ohio residents.

The gun target's code meanings and all 24 people's three target values were independently checked against the original Stata source after predictions sealed. The mismatch is not explained by a reversed answer order or a target-vault mapping error.

**Gun predictions are too confident relative to their accuracy here.** Focused direct's average top-category probability was 62.95%, versus 43.20% weighted modal accuracy. This aggregate confidence gap is a diagnostic, not a full reliability-curve estimate. Its gun predictions were also less repeat-stable than rich direct:67.94% versus 90.34% modal agreement. Better scoring and greater repeat consistency do not necessarily move together.

**Review can stabilize an incorrect prediction.** Health-law repeat agreement rose from 92.19% under focused direct to 100% with review, while Brier worsened from .21145 to .23412. This illustrates why internal consistency is not our success criterion.

**Small score differences depend on weighting.** Exploratory unweighted macro Brier was .25499 sparse, .25799 rich, .25476 focused, and .25420 reviewed. The reviewed arm is narrowly best among agents on this alternate descriptive metric, unlike the predefined weighted primary. This does not change the primary decision; it further cautions against declaring a winner from 24 people.

## Next development step

Keep direct prediction as the reference implementation and test focused-profile ablations: original evidence plus each new covariate group, versus the same reduced existing fields without additions. Use development data to diagnose the gun-policy category imbalance and test a simple calibrated statistical/agent combination under cross-fitting. Do not calibrate on the same outcomes used to claim validation. A stronger individual model must earn its advantage over the party baseline on unseen people before social interaction is added.

The evidence does not yet justify more reflective steps, a larger swarm, or using the 50-person reserve for repeated prompt selection. It also does not show that personal evidence or reflection can never help.

## Execution and audit

- 240 live logical calls, all valid on the first format attempt;192 final three-task forecasts and 48 private reviews.
- 296 offline tests passed, with two existing dependency warnings. Focused lint and diff checks passed.
- Recorded provider cost **USD .0929464**, zero unresolved usage records. No recorded provider failure.
- Independent audit reconstructed person/condition inputs and review pairing, validated all checkpoints/seals, and recomputed every agent and baseline Brier score.
- No overlap among evaluation 24, baseline-training 96, and reserved 50.
- Each prompt worker ran in a fresh no-network, no-mount, non-root, read-only Docker container with dropped capabilities, no-new-privileges and resource limits. Runtime probes and separate container inspection passed.
- The exact Linux/arm 64 worker image was exported; its OCI index and 13 content-addressed blobs were verified. Remote inference and the trusted host broker remain outside this image.
- Six of 48 reviews exceeded the prompted 80-word preference, with a maximum 86 words. They were retained; the parser's hard bound was 4,000 characters. Do not describe this as strictly length-matched cognition.
- Predictions were sealed before this run opened targets. These people were previously inspected, so this is execution isolation rather than newly blinded scientific validation.

Protocol: `docs/ANES_INDIVIDUAL_DEVELOPMENT_PROTOCOL.md`. Results, figure, audit, source snapshots, logs, image export and completion seal: `data/runs/anes2012-ohio-individual-development-20261020/`. Clean-checkout portability and removal of pretrained historical knowledge are not established.
