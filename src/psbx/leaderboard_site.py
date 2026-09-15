"""results.json -> static table."""

from __future__ import annotations

from pathlib import Path

from psbx.io import read_json
from psbx.paths import resolve, run_dir


def build_site(run_id: str) -> Path:
    report = read_json(run_dir(run_id) / "results.json")
    dest = resolve("leaderboard/site/index.html")
    dest.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for mid, score in report["brier_by_model"].items():
        idx = report["brier_index_by_model"].get(mid)
        beat = "yes" if mid in report["models_beating_base_rate"] else "no"
        coverage = (report.get("coverage_by_model") or {}).get(mid) or {}
        prior = (report.get("baselines_by_model") or {}).get(mid, {}).get("prior_signal")
        matched = (report.get("matched_brier_by_model") or {}).get(mid)
        rows.append(
            "<tr>"
            f"<td>{mid}</td><td>{_number(score, 4)}</td><td>{_number(idx, 1)}</td>"
            f"<td>{coverage.get('answered_questions', 0)}/"
            f"{coverage.get('expected_questions', 0)}</td>"
            f"<td>{_number(prior, 4)}</td><td>{_number(matched, 4)}</td><td>{beat}</td>"
            "</tr>"
        )
    base_rows = "".join(
        f"<tr><td>{k}</td><td>{v:.4f}</td></tr>" for k, v in report["baselines"].items()
    )
    dest.write_text(
        f"""<!doctype html>
<html lang="en">
<meta charset="utf-8"/>
<title>Prediction Sandbox — {run_id}</title>
<style>
  body {{
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    background:#EFE7D6;
    color:#1E2530;
    margin:32px;
  }}
  table {{ border-collapse: collapse; }}
  td, th {{ border-bottom:1px solid #C6B896; padding:6px 12px; text-align:left; }}
  h1 {{ font-weight:400; }}
</style>
<h1>Prediction Sandbox</h1>
<p>run {run_id} · n={report["n_predictions"]} · flagged={report["n_flagged"]}</p>
<h2>Models</h2>
<table>
  <tr><th>model</th><th>own-set Brier</th><th>Brier index</th>
  <th>coverage</th><th>own-set prior</th><th>matched Brier</th>
  <th>beats own-set base rate</th></tr>
  {''.join(rows)}
</table>
<h2>Full-question-set reference baselines</h2>
<table>
  <tr><th>baseline</th><th>Brier</th></tr>
  {base_rows}
</table>
<p>Contamination curves and calibration plots live next to results.json.</p>
</html>
""",
        encoding="utf-8",
    )
    return dest


def _number(value: object, digits: int) -> str:
    return "—" if value is None else f"{float(value):.{digits}f}"
