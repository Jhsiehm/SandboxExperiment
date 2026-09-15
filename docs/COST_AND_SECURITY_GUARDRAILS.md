# Cost and security guardrails

## Default hard limits

Paid traffic is disabled unless `PSBX_ENABLE_PAID_MODELS=1` is set in addition to the required
provider credential. Defaults fail closed at:

- `$1.00` reserved cost per run;
- `$0.10` estimated cost per request;
- `100` paid requests per run;
- `16,000` conservative input tokens per request;
- the model's configured output cap (`256` for OpenRouter swarm workers and `2,048` for the
  native comparison models).

Every paid request reserves its conservative cost before network I/O. The reservation includes
the full output allowance and is never released merely because a request fails. A malformed or
oversized spend ledger blocks the run rather than resetting its totals.

## Read-only projections

`GET /api/swarm/options` publishes `run_type_estimates` and
`representative_swarm_projections`. Values below use the checked-in prices, 8,000 preflight input
tokens per attempt, and the full output allowance. They are conservative planning estimates, not
provider bills. The runtime can still block earlier if the actual serialized input exceeds the
16,000-token per-request ceiling.

| Run shape | Questions | Max paid attempts | Preflight input | Max output | Estimate | Default result |
|---|---:|---:|---:|---:|---:|---|
| Practice | 50 | 0 | 0 | 0 | `$0.000000` | Free |
| Live mix, six species | 1 | 48 | 384,000 | 12,288 | `$0.112384` | Paid mode off |
| Weighted swarm, 12 agents | 1 | 24 | 192,000 | 6,144 | `$0.056192` | Paid mode off |
| Weighted swarm, 25 agents | 1 | 50 | 400,000 | 12,800 | `$0.119603` | Paid mode off |
| Weighted swarm, 50 agents | 1 | 100 | 800,000 | 25,600 | `$0.234694` | Paid mode off |
| Weighted swarm, 100 agents | 1 | 200 | 1,600,000 | 51,200 | `$0.476115` | Blocked by request cap |
| Native Claude + GPT full config | 50 | 1,200 | 9,600,000 | 2,457,600 | `$36.718080` | Blocked by request and run caps |

The swarm reserves two possible paid attempts per agent/question: the initial request and one
retry. Under the default 100-request cap, the paid ceiling for one question is therefore 50
agents. For `q` questions it is `floor(100 / (2 × q))`. A 100-agent population-weighted swarm is
available as a sizing/roster preview, but the current paid dashboard will not start it under the
default cap. A future mock/local execution path must use a separate, explicit configuration rather
than silently bypassing the paid-run guard.

## Network and credential boundaries

- Paid provider origins are pinned to their official HTTPS origins unless an explicit custom-
  proxy override is enabled.
- Local vLLM endpoints must resolve to loopback. They cannot silently become remote egress.
- Dashboard jobs receive an allowlisted child-process environment, not arbitrary cloud tokens
  from the parent process.
- The unauthenticated viewer binds to loopback only, checks the socket peer and Host header, and
  requires a non-simple same-origin mutation header.
- OpenRouter routing rejects data-collection routes and supplies a provider price ceiling.
- Census requests use a fixed official HTTPS host, refuse redirects, limit response size, and
  never persist `CENSUS_API_KEY` in cache metadata.
- FEC downloads require an official FEC HTTPS host, opt-in execution, file-count and byte limits,
  matching PDF/XLS/XLSX signatures, and SHA-256 manifests.
- Election/Census result layers are stored as display/evaluation provenance with
  `runtime_access: false`; they are never placed into forecast prompts or retrieval.

## Residual risks and operator controls

Checked-in provider prices can become stale. Configure an independent hard provider-key budget,
disable automatic top-ups, review the preflight estimate, and use a new low-privilege key for
experiments. Local caps limit this process; they do not replace provider-side billing controls.

The viewer has no account system. Keep it on loopback, or place authentication and TLS at a
separate reverse proxy before any shared deployment. Official-source pinning reduces supply-chain
risk but does not prove that an upstream agency file is semantically correct; normalization still
requires coverage, duplicate, total, vintage, and certification checks.
