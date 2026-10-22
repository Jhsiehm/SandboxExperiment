"""Plot the sealed exploratory pilot, preserving the predeclared primary contrast."""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from psbx.experiments.anes_society import _sha256_file
from psbx.experiments.decision_profiles import check_seal
from psbx.experiments.social_benchmark import RUN_ID
from psbx.paths import resolve

root = resolve("data/runs") / RUN_ID
report = json.loads((root / "evaluation.json").read_text())
seal = json.loads((root / "evaluation-seal.json").read_text())
check_seal(seal)
assert _sha256_file(root / "evaluation.json") == seal["report_sha256"]
labels = {
    "persistence": "Keep initial view",
    "private": "Private reflection",
    "swarm": "Generated conversation",
    "replay": "Real incoming messages",
}
colors = ["#667085", "#3471a1", "#b3663b", "#5c8570"]
fig, (left, right) = plt.subplots(1, 2, figsize=(12, 5.7), gridspec_kw={"width_ratios": [1.2, 1]})
fig.subplots_adjust(left=0.21, right=0.96, top=0.78, bottom=0.23, wspace=0.65)
rows = report["metrics"]
left.barh(range(4), [r["rps"] for r in rows], color=colors, height=0.58)
left.set_yticks(range(4), [labels[r["arm"]] for r in rows])
left.invert_yaxis()
maximum = max(r["rps"] for r in rows)
left.set_xlim(0, maximum * 1.3)
for i, row in enumerate(rows):
    left.text(row["rps"] + maximum * 0.035, i, f"{row['rps']:.4f}", va="center", fontsize=10)
left.set_xlabel("Ranked probability score · lower is better", labelpad=13)
left.set_title("Final human-opinion prediction", loc="left", fontsize=12, pad=14)

groups = sorted({r["group"] for r in report["group_results"]})
lookup = {(r["group"], r["arm"]): r["rps"] for r in report["group_results"]}
deltas = [lookup[g, "swarm"] - lookup[g, "private"] for g in groups]
right.axvline(0, color="#89919b", linewidth=1)
right.scatter(deltas, range(8), color="#b3663b", s=35, zorder=3)
contrast = report["contrasts"][0]
lo, hi = contrast["group_bootstrap_95_interval"]
mean = contrast["group_mean_rps_change"]
right.errorbar(mean, 9, xerr=[[mean - lo], [hi - mean]], fmt="D", color="#202d3d", capsize=4)
right.set_yticks(
    list(range(8)) + [9], [f"Group {i + 1}" for i in range(8)] + ["Mean / 95% interval"]
)
right.invert_yaxis()
right.set_xlabel(
    "Swarm − private RPS\nNegative: better   |   Positive: worse", labelpad=13, fontsize=9
)
right.set_title("Does conversation help?", loc="left", fontsize=12, pad=14)
for axis in [left, right]:
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.tick_params(axis="y", length=0)
    axis.grid(axis="x", alpha=0.15)
    axis.set_axisbelow(True)
fig.suptitle("Human social-emulation pilot", x=0.04, ha="left", fontsize=19, weight="bold", y=0.97)
fig.text(0.04, 0.88, "32 people · 8 selected groups · 4 topics · 1 model / repetition", fontsize=11)
fig.text(
    0.04,
    0.06,
    "Exploratory group bootstrap; shortened conversation protocol.\n"
    "These results do not establish population accuracy or a causal human discussion effect.",
    fontsize=10,
    color="#555555",
)
for suffix in ["png", "svg"]:
    destination = root / f"results.{suffix}"
    fig.savefig(destination, dpi=180, facecolor="white")
    destination.chmod(0o600)
print(root / "results.png")
