# Oregon behavior-event feasibility audit — 2026-10-22

**Decision: official data, documentation, and replication code are now acquired and verified. Oregon is feasible for a sparse-input enrollment benchmark; it is not yet cleared for paid agent calls or rich behavioral/societal claims.** Baseline reproduction is owned by the parallel baseline agent; this report does not claim its completion.

## Access and terms

The first [NBER download](https://www.nber.org/research/data/oregon-health-insurance-experiment-data) redirected to account login. The [Harvard/J-PAL catalog](https://doi.org/10.7910/DVN/SJG1ED), version 1.2, required guestbook registration. After the user supplied and authorized required registration details, the documented official API accepted the guestbook and returned a signed download URL. The archive and terms file were fetched through that route; registration details and temporary signed URLs are not saved in the report artifacts.

Archive size: **9,370,270 bytes**. SHA-256: `0426efe3c226ed39ce746322885cbf9bfabff26b759de282378ba1a0012f9e8a`. Its MD5 `1a12e3c55af8caa7089cfa0a869fc0c7` matches the official catalog. Archive paths were checked before extraction. `.gitignore` excludes the ZIP and extracted source directory from source control.

Both NBER and the downloaded Harvard terms prohibit commercial use, reidentification, and contact with known subjects; require lawful use and citation; and disclaim warranties. The catalog's CC0 description includes additional/modified terms and is not unrestricted commercial permission. This is a noncommercial research audit.

## What the sources establish

The [ICPSR catalog](https://www.icpsr.umich.edu/web/HMCA/studies/34314) describes 74,922 lottery-list individuals, including 29,834 selected, with lottery administration and public-benefit records. Its files distinguish applications, approval, and enrollment conceptually. The initial mail survey was collected June–November 2008; subsequent surveys and interviews occur later. Some variables are restricted. Consequently, an “initial” survey is not automatically a pre-lottery profile, and the acquired codebooks must govern exact field selection.

The [original QJE paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC3535298/) establishes household selection despite individual-name drawing, so household-size controls and household-clustered uncertainty matter. Its administrative first-stage reference uses household-size and lottery-draw indicators. A candidate enrollment definition is any Medicaid coverage from notification through September 30, 2009; endpoint coverage is different. The acquired source code and Table III have now been mapped for reproduction. Reported lottery-list covariates include birth year, sex, language, sign-up characteristics, and area-level characteristics. They provide limited personal context.

## Proposed input and scoring boundary

| Information | Proposed handling | Audit requirement (verified mappings below) |
|---|---|---|
| Lottery-list characteristics measured at registration | Candidate model inputs | Exact released columns, labels, missingness, and coarsening |
| Household listed-member count | Design control and candidate input | Public field and relationship to actual household size |
| Assignment/offer known at prediction time | Input and experimental treatment | Field coding and notification cutoff |
| Household/person identifiers | Split/link only, never predictive features | Availability, uniqueness, join integrity |
| Prior administrative history | Conditional candidate input only | Dates strictly precede prediction; released coverage |
| Application, approval, enrollment after notification | Outcomes or intermediates, not baseline inputs | Distinct fields, timing, structural missingness |
| Initial and later surveys | Excluded from pre-lottery prediction by default | Individual response dates and estimand-specific admissibility |
| Published outcome statistics | Reference/scorer only | Keep out of agent context |
| Neighborhood characteristics | Context, not personal income or beliefs | Geographic aggregation and disclosure limits |

No personal attitudes, risk preferences, comprehension, social networks, or exposure can be invented from demographics. Enrollment reflects eligibility and administration as well as choice; the endpoint is not pure preference. General policy rules may be supplied as an experimental scenario, but must not be represented as information every person actually received.

## Verified local mapping

Documentation: `source/OHIE_Public_Use_Files/OHIE_Documentation/ohie_userguide.pdf` (pages 2–4), descriptive codebook (pages 1–2), and state-program codebook (pages 1–4). Text extractions are alongside this report.

- Link: `person_id`; cluster/split: `household_id`; assignment: `treatment`.
- Design: `numhh_list` is listed household members, not total household size; `draw_lottery` includes matched control draws. `dt_notify_lottery` is actual notification for selected people and a randomly assigned matched date for controls—not a real message to them.
- Primary candidate: `ohp_all_ever_matchn_30sep2009`, any Medicaid between matched notification and September 30, 2009. Alternative endpoint: `ohp_all_end_30sep2009`. Codebook reports both complete for 74,922 individuals.
- Registration inputs: `birthyear_list`, `have_phone_list`, `english_list`, `female_list`, `first_day_list`, `last_day_list`, `pobox_list`, `self_list`, `week_list`, `zip_msa_list`, plus listed-household count. Codebook missing counts: female 1, metropolitan indicator 2. ZIP median income mentioned in the paper is absent from the released descriptive field list and must not be fabricated (replication code creates a zero placeholder).
- Prior program-history candidates: `snap_ever_prenotify07`, `snap_tot_hh_prenotify07`, `tanf_ever_prenotify07`, `tanf_tot_hh_prenotify07`. They run from January 1, 2007 to matched notification; confirm inclusive cutoff convention before profile use.
- Exclude post-assignment `applied_app`, `approved_app`, `dt_app_decision`, `postn_death`, survey answers, and realized enrollment from inputs. Application indicators are observed for 29,799 selected records, not a meaningful all-population zero-filled outcome. `dt_retro_coverage` concerns retrospectively applied coverage and should not become a personal baseline fact.

The QJE `prepare_data.do` maps the primary outcome to `ohp_all_ever_admin`, creates `sample_hdd=1`, `noweight=1`, and household-size/lottery-draw indicators. `tables_firststage.do` performs OLS with household-clustered SEs. The official MIT-hosted paper (`qje-mit-paper.pdf`, PDF page 23 / printed page 1079) Table III full-sample reference is N=74,922: ever Medicaid control mean .141, effect .256, SE .0035; endpoint control mean .106, effect .148, SE .0031. These are published reference values, **not results reproduced by this audit**.

## Next gates

1. Baseline agent reproduces the exact reference with matching controls and clustered uncertainty, allowing printed rounding tolerance; report any public-release discrepancy.
2. Keep full-sample historical reproduction distinct from predictive validation. No claim that reference-inspected outcomes constitute untouched confirmation.
3. Freeze household-grouped predictive development/confirmation split before targeted model diagnosis; exclude IDs from features. Fit feature selection and calibration on development only.
4. Choose sparse-input benchmark admission explicitly. Stronger claims require richer independently measured prior behavior, not invented biographies.
5. Freeze target, cutoff, model identifiers, budget and meaningful improvement threshold before paid calls. Preserve ANES reserve and historical artifacts.

No participant-level outcome rows were inspected by this data-audit agent; source codebooks contain published aggregate statistics. No agent calls were made. `manifest.json` records source checksums and verified/unresolved fields. Initial failed HTTP responses are retained as acquisition history and explicitly labeled; they are superseded by the successful official archive.
