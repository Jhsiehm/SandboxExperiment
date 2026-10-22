"""Static scientific plot from the sealed individual comparison."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from psbx.experiments.anes_society import _sha256_file
from psbx.experiments.decision_profiles import check_seal
from psbx.experiments.individual_validation import RUN_ID, read
from psbx.paths import resolve

root = resolve("data/runs") / RUN_ID
report = read(root / "evaluation.json")
s = read(root / "evaluation-seal.json")
check_seal(s)
assert s["report_sha256"] == _sha256_file(root / "evaluation.json")
arms = [
    "training_prevalence",
    "party_smoothed",
    "sparse_direct",
    "rich_direct",
    "focused_direct",
    "focused_review",
]
labels = [
    "Training prevalence",
    "Party baseline",
    "Sparse · direct",
    "Rich · direct",
    "Focused · direct",
    "Focused · private review",
]
colors = ["#8a929b", "#4f8572", "#6089a7", "#355d80", "#be7541", "#825c8b"]
fig, axes = plt.subplots(1, 3, figsize=(12, 5.4), sharey=True)
fig.subplots_adjust(left=0.23, right=0.97, bottom=0.22, top=0.73, wspace=0.18)
maximum = max(m["brier"] for m in report["metrics"]) * 1.22
for ax, task, title in zip(
    axes, ["vote", "health_law", "gun_policy"], ["Vote", "Health-care law", "Gun policy"]
):
    rows = [next(m for m in report["metrics"] if m["arm"] == a and m["task"] == task) for a in arms]
    ax.barh(range(6), [r["brier"] for r in rows], color=colors, height=0.6)
    ax.set_xlim(0, maximum)
    ax.set_yticks(range(6), labels)
    ax.set_title(f"{title}\n{rows[0]['n']} scorable people", fontsize=11, pad=10)
    for i, r in enumerate(rows):
        ax.text(r["brier"] + 0.005, i, f"{r['brier']:.3f}", va="center", fontsize=9)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", alpha=0.15)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel("Weighted half-Brier ↓", fontsize=10, labelpad=10)
axes[0].invert_yaxis()
fig.suptitle(
    "Individual-agent development comparison",
    x=0.035,
    ha="left",
    y=0.98,
    fontsize=18,
    weight="bold",
)
fig.text(
    0.035,
    0.86,
    "24 previously inspected Ohio respondents · 2 repeats · 1 model · no conversation",
    fontsize=11,
)
fig.text(
    0.035,
    0.055,
    "Lower scores are better. Baselines trained on 96 separate development respondents.\n"
    "The 50-person reserve was not used. These are development results, not fresh validation.",
    fontsize=10,
    color="#555555",
)
for ext in ["png", "svg"]:
    p = root / f"results.{ext}"
    fig.savefig(p, dpi=180, facecolor="white")
    p.chmod(0o600)
print(root / "results.png")
