# Longitudinal panel feasibility: documentation-only inventory

Prepared 2026-10-23. Status: **design candidate; not an executable evaluation contract**.

Scope: research-plan sections 4 and 7. No respondent microdata downloaded, no participant outcomes inspected, and no paid API calls made. This inventory separates verified documentation from design proposals and unresolved harmonization. Official documentation was consulted through web search/open; some direct source downloads returned timeouts or HTTP 403. Source bytes and checksums have therefore not been frozen.

## ANES: verified structure

The May 19, 2026 merged release has nine survey occasions: 2016 pre/post, 2019 maintenance, 2020 pre/post, 2022 maintenance, 2024 maintenance, and 2024 pre/post. These are not nine annual observations. The merged file links using `V160001_orig`. Its universe already requires completion of 2016 pre/post and at least 2020 pre; reported counts are 2,839 at 2020 pre, 2,670 at 2020 post, 2,171 at 2024 pre, and 2,070 at 2024 post. Maintenance surveys were paper questionnaires primarily intended to maintain contact; election-wave mode also varies. The official page advertises a repeated-variable CSV, but its contents were not successfully retrieved in this pass. Consequently no maintenance-wave outcome crosswalk is certified here. [ANES merged study, May 19, 2026](https://electionstudies.org/data-center/2016-2020-2024-panel-merged-study/)

The 2024 variable list confirms IDs `V240001`, `V200001`, and `V160001_orig`. For the 2016–2024 panel, `V240106a` and `V240106b` are the pre/post raked weights, with `V240106c` PSU and `V240106d` stratum. These are distinct from fresh-sample or combined-sample weights. Candidate target fields present in 2024 include party identification `V241227x`, ideological self-placement `V241177`, spending/services `V241239`, government/private medical insurance `V241245`, and party thermometers `V241166`/`V241167`. Presence in 2024 alone does not certify identical questions at earlier waves. [ANES variable list, 20260519, pp. 1, 5–6](https://electionstudies.org/wp-content/uploads/2026/05/anes_timeseries_2024_varlist_20260519.pdf)

The official cumulative-file codebook provides a concrete party-identification starting crosswalk: 2016 `V161158x`, 2020 `V201231x`, and 2024 `V241226`/`V241227x` feed its harmonized party-ID measure. Its construction notes distinguish follow-up responses and missingness. Treat this as metadata guidance for the linked panel, not permission to substitute a stacked cross-section for linked people. The paper-mode branch and final release coding still require checking against the merged sample. [ANES cumulative codebook, February 5, 2026, party-ID section](https://electionstudies.org/wp-content/uploads/2026/02/anes_timeseries_cdf_codebook_var_20260205.pdf)

## CES: verified structure and current limits

The official CES download hub links a distinct 2010–2014 panel deposit; it separately lists the 2010–2012 panel and cumulative common-content files. Use the linked panel, not a join on similarly named IDs in independent annual cross-sections. [CES official download hub](https://tischcollege.tufts.edu/research-faculty/research-centers/cooperative-election-study/data-downloads)

The official Harvard deposit identifies a panel of 9,500 American adults surveyed during the 2010, 2012, and 2014 election cycles. The indexed deposit is version 11.0, DOI `10.7910/DVN/TOE8I1`, under CC0. Listed artifacts are the panel guide `CCES_PanelGuide_Full_2010-2014.pdf` (published February 22, 2017) and `CCES_Panel_Full3waves_VV_V4.dta` (published July 19, 2019). This is a nominal study count, not a verified complete-case count for any proposed endpoint. [Official CES deposit, V11](https://doi.org/10.7910/DVN/TOE8I1)

The guide could not be read successfully in this pass. Therefore exact respondent ID, longitudinal weights, validation flags, variable names, retained-case definitions, and repeated policy-item wording remain **unverified**. Party identification, ideology, turnout and congressional vote are candidate families for the next documentation pass, not confirmed harmonized endpoints. Presidential vote cannot be presumed to be a common contemporaneous outcome in all three election cycles. Do not implement a guessed CES schema.

## Proposed first experiment

Prefer ANES party-ID transitions as the smallest documented starting point. Freeze one target family before inspecting its transition frequencies. Use persistence, a regularized statistical transition model, and profile-only versus earlier-history predictions. Score ordinal probability error plus a separate change-event Brier score; preserve missing/nonresponse categories in the audit instead of mapping them to ideological midpoint.

A defensible initial temporal design is development on 2016→2020 and a frozen 2020→2024 confirmation. Within development, keep all records for one person in one partition. Reusing people across temporal boundaries tests future prediction for known people; it does not establish transfer to unseen people. If unseen-person transfer is also desired, reserve people before any fitting and report that contrast separately.

On the same eligible confirmation people distinguish:

- One-step: condition on observed 2020 state and predict 2024.
- Autonomous: initialize in 2016, carry the predicted 2020 distribution forward, then predict 2024 without ingesting observed 2020 targets.
- Assimilated: explicitly replace/update the state with observed 2020 measurements before predicting 2024; record exactly which measurements are allowed.

These protocols have different information. Report each separately; do not pool their scores. Maintenance checkpoints may be added only after a question-by-wave crosswalk proves that the selected construct and response scale recur. No synthetic annual observations become validation labels.

CES offers a contingency design of 2010→2012 development and 2012→2014 confirmation after its guide is obtained. Election type changes between midterm and presidential years must remain explicit. Choose comparable attitude targets before turnout or candidate-specific vote targets.

## Execution gates

1. Retrieve and checksum the repeated-variable CSV, questionnaires, applicable codebooks, and errata. Freeze release identifiers and document any disagreement between the merged release and older cumulative-codebook mappings.
2. Produce a metadata crosswalk recording source field, question text, response codes/order, survey phase, routing, universe, mode, and missing-value rules. Select one endpoint with verified overlap; otherwise stop this track.
3. Predeclare people partitions, temporal boundaries, eligibility, prediction schema, primary contrast, meaningful improvement threshold, and confirmation access rules before opening target values.
4. Authorize a separate ingestion step that exposes only development records to fitting. A trusted evaluator should retain confirmation outcomes. Record which later observations become permissible assimilation inputs.
5. Audit linkage uniqueness and actual eligible sample sizes. Report attrition by wave and development-observed characteristics. A nominal panel size does not establish effective sample size or power.
6. Choose weights for the stated population and survey phase; do not use a final-wave weight indiscriminately for every transition. Account for survey design and repeated-person dependence in uncertainty. Report weighted population results separately from unweighted person-level diagnostics. Weighting does not itself prove attrition is ignorable.

The current deliverable completes a bounded metadata feasibility pass. It does **not** authorize claims of a ready longitudinal dataset, verified nine-wave target coverage, sufficient power, or a prospective historical forecast. Modern-checkpoint backtests must remain labeled retrospective reconstruction/temporal transfer.
