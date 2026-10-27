# Classifier error analysis

This is a post-hoc decomposition of the already-scored 24-person internal cohort, compared with the available 92 training examples. All six internal groups contain four people, so person-weighted aggregate RPS equals the frozen equal-group endpoint. No outer-validation or reserve data, new model runs, or new fitting were used. Participant statements and person-level records are omitted.

## Main finding

The trained candidate varies very little across profiles and assigns most of its probability to the middle categories. This descriptive pattern explains much of its disadvantage against the initial-state transition baseline. It does not establish whether the cause is insufficient updates, optimization behavior, the restricted class-token representation, or some combination.

Overall RPS (lower is better): transition **0.1247**, persistence **0.1333**, base **0.1846**, candidate **0.2160**. Candidate minus transition is **0.0913**. The transition baseline beats the candidate in five of six groups. The candidate improves over base in three groups and worsens in three; the harmful group effects are larger overall.

## Change versus persistence

Fourteen of 24 people did not change category. On these unchanged people, RPS is candidate **0.2110**, base **0.1754**, transition **0.0722**, persistence **0**. This stratum contributes **0.0810**, or about **88.6%**, of the candidate-minus-transition aggregate gap.

Ten people changed category. Their RPS is candidate **0.2231**, base **0.1975**, transition **0.1982**, persistence **0.3200**. This stratum contributes the remaining **0.0104** of the gap. Thus the baseline advantage is primarily protection against unnecessary movement among stable respondents, rather than dramatically superior prediction of changed respondents.

Average predicted probability of any change is **0.8024** for the candidate, **0.7552** for base and **0.5916** for transition; the observed change fraction is **0.4167**. These are descriptive aggregate discrepancies, not a calibration study. Among the unchanged people alone, candidate mean probability of change remains **0.7693**.

## Category conditioning and distribution differences

The candidate's expected category ranges only from **3.8366 to 3.9188** across all 24 profiles (population SD **0.0209**), versus **4.2344 to 5.3224** for base (SD **0.3092**). Its highest-probability category is 4 in 23 cases and 3 in one case. Base chooses category 5 in 22 cases, category 4 once and category 6 once. Both exhibit class preferences; the candidate's predicted expectation is particularly insensitive to the recorded initial state.

The candidate assigns an average **80.8%** probability mass to categories 3 and 4 combined. Its mean predicted category is **3.8741**, compared with observed final mean **4.4167**. The transition baseline's mean prediction is also low (**3.8357**) yet its RPS is much better. Matching only the marginal mean would therefore miss the important advantage: conditional placement of probability by initial category.

Seven internal people began at category 6 and all seven remained there. Candidate RPS is **0.3219**, versus base **0.0841** and transition **0.0862**; persistence is exactly correct. Candidate expected category in this subgroup is **3.8874**. This subgroup is a substantial contributor to the poor aggregate score.

There is also an observed cohort difference: category 6 is the final answer for **11/24 internal people (45.8%)**, compared with **23/92 fitting people (25.0%)**. The fitting final mean is **3.7500**, versus **4.4167** internally; fitting change rate is **47.8%**, versus **41.7%** internally. These six held-out topics differ from the fitting topics by design. Such small-cohort differences should not be generalized into population shift claims.

Initial-category cell sizes are **1, 3, 7, 2, 4, 7**. The candidate improves over base in the cells beginning at 1–4 and worsens in those beginning at 5–6, consistent with a common downward shift in its output. Several cells are too small for stable conclusions. The machine-readable output preserves counts for every cell and all six group effects rather than promoting a selective subgroup result.

## Training exposure and interpretation

The baseline uses all 92 available fitting outcomes. The classifier completed 52 batch-size-one microsteps and 13 optimizer updates, so equal access to a dataset is not equal realized training exposure. The separate iterator/RNG audit reconstructs **52 unique examples from 21/23 fitting groups**, leaving **40 examples unseen**. Reconstructed selected-category counts are **11, 5, 8, 7, 8, 13**, versus **16, 8, 20, 10, 15, 23** in the full fitting pool. Only 8/20 category-3 examples were selected. Because sampled row IDs were not logged during training, these are conditional reconstructions, not directly observed exposure records; see `reports/classifier-training-audit-20261023.json`. This imbalance in realized data consumption limits a head-to-head method claim, but does not erase the operational failure of the tested budget.

The results support preserving the failed development gate and investigating why predicted distributions weakly depend on the profile. They do not support expanding interaction or treating valid numerical output as demonstrated human fidelity. Any next experiment should be specified independently of these small subgroup outcomes.

## Reproduction and checks

Run `scripts/analyze_classifier_errors.py --run data/local-mlx-pilot/outcome-classifier-v1-20261023 --output <new-directory>` from the repository. The script verifies the completed evaluation's prediction seal, sealed file bindings, target digest and prepared-data digests before analysis. It reproduces all four frozen aggregate RPS values to **1e-12** and checks that change-stratum contributions sum to the total candidate-minus-transition gap.

The final aggregate artifact is `data/local-mlx-pilot/outcome-classifier-v1-20261023/error-analysis-v2/aggregate.json`, SHA-256 `0c9b71202fa0196b01934e721c413807f613b8770dc11bde4cede55ac9cd5dd7`. It includes initial-category, change-status and group decompositions, marginal category counts, predicted distributions, confidence and entropy summaries, and source hashes. The earlier v1 aggregate is retained; v2 adds expected-category range and dispersion.

## Post-hoc control for reconstructed sample exposure

A separate diagnostic fits the same Laplace-one transition rule using only the **52 reconstructed sampled fitting rows**, rather than all 92 available rows. Before fitting, row-by-row group, pseudonymous agent and target-class identity were checked against the frozen `fit-tokens.json`; the sampling audit's contract hash and all original prediction-seal bindings were verified. This is explicitly a **post-hoc inferred-sample control**, not a replacement for the frozen baseline.

Its RPS is **0.1347**, compared with **0.1247** for the original full-92 transition baseline. The candidate remains at **0.2160**, leaving a **0.0813** gap against the exposure-matched statistical control. Reducing baseline exposure increases its error by **0.0100**—about 11% of the original 0.0913 candidate-versus-baseline gap. In this diagnostic, the baseline's access to the extra 40 examples does **not** account for the ranking against the candidate. This does not rule out undertraining of the neural model, because equal observed examples do not imply equal optimization or convergence.

Reproduce with `scripts/analyze_classifier_sample_control.py`, pointing to the run and `reports/classifier-training-audit-20261023.json`. The separate artifact is `data/local-mlx-pilot/outcome-classifier-v1-20261023/error-analysis-sampled-control-v1/aggregate.json`. No original baseline, predictions, or outcomes were altered. Sample IDs remain reconstructed rather than directly logged, and the 24 internal outcomes were already exposed when this control was chosen.
