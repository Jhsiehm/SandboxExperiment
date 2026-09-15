# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary users are the project owner and research collaborators evaluating how individual LLMs and bounded representative-agent swarms behave under controlled historical information conditions. Public-facing deployment is undecided.

## Product Purpose

Prediction Sandbox makes model and swarm behavior inspectable. Users select an epoch, evidence condition, model composition, and validated population profile; run a bounded experiment; then inspect provenance, agent interactions, aggregate forecasts, demographic representation, and later evaluation without silently crossing the historical cutoff.

## Positioning

The product joins a cutoff-controlled forecasting benchmark to explicit, population-weighted synthetic personas. It shows the chain from frozen evidence through independent agents to aggregation, while keeping data coverage, behavior validation, and simulation cost as separate claims.

## Operating Context

The current application is a local, loopback-only FastAPI research workbench with a dependency-light HTML/CSS/JavaScript dashboard. Epoch `e2012` is the working historical environment. Runs are append-only and can be practice/mock, live model mixes, or configurable swarms.

## Capabilities and Constraints

- The current geographic world is the United States: the nation, all 50 states, the District of Columbia, and available historical sub-state boundaries.
- A clean checkout contains no generated state, D.C., or national population profiles. It can build one deterministic fictional fixture profile for practice. Any locally generated real-geography profile is runnable only when its own validation manifest is present.
- Census and election comparison layers are evaluation/display inputs with `runtime_access: false`; they are never inserted into prompts or retrieval.
- Paid model traffic is off unless deliberately enabled. Conservative request and run ceilings are enforced before network I/O.
- The application may later support a globe and non-U.S. demographic worlds, but no international coverage or equivalence is currently claimed.
- Synthetic populations are statistically constructed representations, not actual residents. Demographic fidelity does not establish political-behavior fidelity.

## Brand Commitments

The product name remains Prediction Sandbox. The interface is an original tactical intelligence workbench whose data-generated world uses restrained block-world references. It must not copy proprietary Palantir Gotham or Minecraft assets, logos, terminology, or exact interface trade dress.

## Evidence on Hand

- Product behavior and current commands: `README.md`.
- Research boundaries and inappropriate-use constraints: `docs/USE_CASES_AND_BOUNDARIES.md`.
- Population dashboard claims and warning language: `docs/DASHBOARD_SPEC.md`.
- Historical state, congressional, legislative, county, and voting-district geometry is derived from U.S. Census Bureau TIGER/Line files, with source URLs and checksums recorded in `leaderboard/static/geography/e2012/manifest.json`.
- Generated Census, corpus, population, run, and evaluation-vault artifacts are intentionally ignored. Claims must hold on a clean checkout or explicitly identify the local build prerequisite.
- There are no checked-in validated real-geography population profiles or 2026 general-election results; future work must not fabricate them.

## Product Principles

1. Show the evidence chain, not only the final score.
2. Make missing, source-only, synthetic, and validated states visually distinct.
3. Represent large populations with bounded weighted panels, never one paid agent per person.
4. Keep future information and comparison datasets outside model context.
5. Let visual ambition reveal system state without overstating data coverage.

## Accessibility & Inclusion

Every map action must have a keyboard- and list-based equivalent. Status cannot rely on color alone, reduced-motion preferences must be respected, and demographic categories must follow the source schema without inferring political identity or behavior.
