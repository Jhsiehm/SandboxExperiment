"""Static results table. Delegates to psbx.leaderboard_site when results.json exists."""

from __future__ import annotations

import json
from pathlib import Path

from leaderboard.store import compute_scores, list_runs
from psbx.paths import resolve


def build_site(src: str | Path | None = None, dest: str | Path | None = None) -> Path:
    dest_path = resolve(dest or "leaderboard/site/index.html")
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    if src is None:
        found = _find_results()
        if found:
            run_id = found.parent.name
            try:
                from psbx.leaderboard_site import build_site as core_build

                return core_build(run_id)
            except Exception:
                src = found

    if src:
        payload = json.loads(resolve(src).read_text(encoding="utf-8"))
        source = str(src)
    else:
        from leaderboard.store import bootstrap

        state = bootstrap()
        payload = compute_scores(state.questions, list(state.models.values()), state.run.run_id)
        source = payload.get("source", "computed")

    dest_path.write_text(_render(payload, source, list_runs()), encoding="utf-8")
    return dest_path


def _find_results() -> Path | None:
    root = resolve("data/runs")
    if not root.exists():
        return None
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        for name in ("results.json", "scores.json", "score_report.json"):
            path = child / name
            if path.exists() and path.stat().st_size > 0:
                return path
    return None


def _render(payload: dict, source: str, runs: list[dict]) -> str:
    report = payload.get("report") if isinstance(payload, dict) else None
    if report is None and isinstance(payload, dict) and "brier_by_model" in payload:
        report = payload
    baselines = {}
    if isinstance(payload, dict):
        baselines = (report or {}).get("baselines") or payload.get("baselines") or {}
    brier = (report or {}).get("brier_by_model") or {}
    coverage = (report or {}).get("coverage_by_model") or {}
    model_baselines = (report or {}).get("baselines_by_model") or {}
    matched = (report or {}).get("matched_brier_by_model") or {}
    rows = "".join(
        (
            f"<tr><th>{_esc(model_id)}</th>"
            f"<td>{'—' if score is None else f'{float(score):.4f}'}</td>"
            f"<td>{_coverage_text(coverage.get(model_id))}</td>"
            f"<td>{_number((model_baselines.get(model_id) or {}).get('prior_signal'))}</td>"
            f"<td>{_number(matched.get(model_id))}</td></tr>"
        )
        for model_id, score in sorted(brier.items())
    ) or "<tr><td colspan='5'>No model scores on disk.</td></tr>"
    base_rows = "".join(
        f"<tr><th>{_esc(k)}</th><td>{float(v):.4f}</td></tr>" for k, v in baselines.items()
    ) or "<tr><td colspan='2'>No baselines.</td></tr>"
    run_rows = "".join(
        f"<tr><td>{_esc(r['run_id'])}</td><td>{r['n_predictions']}</td>"
        f"<td>{'yes' if r['has_scores'] else 'no'}</td></tr>"
        for r in runs
    ) or "<tr><td colspan='3'>No runs in data/runs/.</td></tr>"
    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>PSBX leaderboard</title>
<style>
  :root {{ --paper:#EFE7D6; --ink:#1E2530; --line:#C6B896; --stamp:#A3392C; }}
  body {{ margin:32px; background:var(--paper); color:var(--ink);
         font:16px/1.45 Spectral, "Source Serif 4", serif; }}
  h1 {{ font:500 13px/1 "IBM Plex Mono", monospace; letter-spacing:.12em;
        text-transform:uppercase; border-bottom:1px solid var(--line); padding-bottom:8px; }}
  table {{ border-collapse:collapse; width:100%; margin:24px 0; }}
  th, td {{ border-top:1px solid var(--line); text-align:left; padding:8px 10px;
            font:13px/1.4 "IBM Plex Mono", monospace; }}
  .src {{ color:#565B66; font:12px/1.4 "IBM Plex Mono", monospace; }}
</style>
<body>
<h1>Prediction Sandbox · static results</h1>
<p class="src">source { _esc(source) }</p>
<h2>Model scores and coverage</h2>
<table>
<tr><th>model</th><th>own-set Brier</th><th>coverage</th>
<th>own-set prior</th><th>matched Brier</th></tr>
{rows}
</table>
<h2>Full-question-set reference baselines</h2>
<table>{base_rows}</table>
<h2>Runs</h2>
<table><tr><th>run</th><th>n predictions</th><th>scores</th></tr>{run_rows}</table>
</body>
</html>
"""


def _esc(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _number(value: object) -> str:
    return "—" if value is None else f"{float(value):.4f}"


def _coverage_text(value: object) -> str:
    row = value if isinstance(value, dict) else {}
    answered = int(row.get("answered_questions") or 0)
    expected = int(row.get("expected_questions") or 0)
    return f"{answered}/{expected}"


if __name__ == "__main__":
    print(build_site())
