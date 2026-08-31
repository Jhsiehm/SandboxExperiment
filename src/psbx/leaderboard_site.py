"""results.json -> static table."""

from __future__ import annotations

from pathlib import Path

from psbx.io import read_json
from psbx.paths import resolve


def build_site(run_id: str) -> Path:
    report = read_json(f"data/runs/{run_id}/results.json")
    dest = resolve("leaderboard/site/index.html")
    dest.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for mid, score in report["brier_by_model"].items():
        idx = report["brier_index_by_model"].get(mid, 0.0)
        beat = "yes" if mid in report["models_beating_base_rate"] else "no"
        rows.append(f"<tr><td>{mid}</td><td>{score:.4f}</td><td>{idx:.1f}</td><td>{beat}</td></tr>")
    base_rows = "".join(
        f"<tr><td>{k}</td><td>{v:.4f}</td></tr>" for k, v in report["baselines"].items()
    )
    dest.write_text(
        f"""<!doctype html>
<html lang="en">
<meta charset="utf-8"/>
<title>Prediction Sandbox — {run_id}</title>
<style>
  body {{ font-family: "IBM Plex Mono", ui-monospace, monospace; background:#EFE7D6; color:#1E2530; margin:32px; }}
  table {{ border-collapse: collapse; }}
  td, th {{ border-bottom:1px solid #C6B896; padding:6px 12px; text-align:left; }}
  h1 {{ font-weight:400; }}
</style>
<h1>Prediction Sandbox</h1>
<p>run {run_id} · n={report["n_predictions"]} · flagged={report["n_flagged"]}</p>
<h2>Models</h2>
<table>
  <tr><th>model</th><th>Brier</th><th>Brier index</th><th>beats base rate</th></tr>
  {''.join(rows)}
</table>
<h2>Baselines</h2>
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
