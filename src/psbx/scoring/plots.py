"""Seaborn performance plots for swarm / mix / practice runs.

Dark HUD palette. These answer: where did each agent land, how sharp were
the percentages, and did the median beat the species?
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from psbx.io import read_jsonl
from psbx.paths import resolve, run_dir
from psbx.schemas import Prediction, Question, SwarmVote

_LOCK = threading.Lock()
INK = "#f3eee4"
MUTED = "#c4b8a8"
PANEL = "#120c1c"
AX = "#1a1228"
LINE = "#6b4aa0"
ACCENT = "#7dde9a"
WARN = "#f08070"
PURPLE = "#c4b5fd"
BRASS = "#e6c07b"
GRID = "#3a2a52"

SPECIES_SHORT = {
    "openrouter-gpt-4.1-mini": "GPT-4.1 mini",
    "openrouter-gpt-4o-mini": "GPT-4o mini",
    "openrouter-haiku": "Haiku",
    "openrouter-gemini-flash-lite": "Flash-Lite",
    "openrouter-llama-3.1-8b": "Llama 8B",
    "openrouter-qwen-2.5-7b": "Qwen 7B",
    "swarm-median": "Median of 12",
    "prior_signal": "2012 prior",
    "always_0.5": "Coin flip",
    "gpt-oss-2012ish": "Keyword / 2012-era",
    "frontier-a": "Claude Sonnet",
    "frontier-b": "GPT-4.1 mini",
}

SPECIES_ORDER = [
    "GPT-4.1 mini",
    "GPT-4o mini",
    "Haiku",
    "Flash-Lite",
    "Llama 8B",
    "Qwen 7B",
    "Median of 12",
]

PALETTE = {
    "GPT-4.1 mini": "#c4b5fd",
    "GPT-4o mini": "#a78bfa",
    "Haiku": "#7dde9a",
    "Flash-Lite": "#f08070",
    "Llama 8B": "#fbbf24",
    "Qwen 7B": "#67e8f9",
    "Median of 12": INK,
    "2012 prior": BRASS,
    "Coin flip": MUTED,
}


def short_name(model_id: str) -> str:
    if model_id in SPECIES_SHORT:
        return SPECIES_SHORT[model_id]
    if model_id.startswith("openrouter-"):
        return model_id.replace("openrouter-", "").replace("-", " ")
    return model_id


def _apply_theme() -> None:
    sns.set_theme(
        style="darkgrid",
        rc={
            "figure.facecolor": PANEL,
            "axes.facecolor": AX,
            "axes.edgecolor": LINE,
            "axes.labelcolor": INK,
            "axes.titlecolor": INK,
            "text.color": INK,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "legend.facecolor": AX,
            "legend.edgecolor": LINE,
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
        },
    )


def _finish(fig: plt.Figure, path: Path) -> None:
    fig.patch.set_facecolor(PANEL)
    fig.tight_layout()
    fig.savefig(path, dpi=140, facecolor=PANEL, edgecolor="none")
    plt.close(fig)


def _scored_questions(
    questions: list[Question], ids: set[str]
) -> dict[str, Question]:
    return {
        q.id: q
        for q in questions
        if q.id in ids and q.ground_truth is not None
    }


def _item_brier(p: float, yes: bool) -> float:
    y = 1.0 if yes else 0.0
    return (p - y) ** 2


def _prior_p(question: Question) -> float:
    if question.prior_signal is None:
        return 0.5
    return float(question.prior_signal.probability)


def _vote_frame(
    votes: list[SwarmVote], scored: dict[str, Question]
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for vote in votes:
        q = scored.get(vote.question_id)
        if q is None:
            continue
        yes = bool(q.ground_truth)
        rows.append(
            {
                "question_id": vote.question_id,
                "agent_id": vote.agent_id,
                "species": short_name(vote.model_id),
                "model_id": vote.model_id,
                "p": float(vote.probability),
                "truth": 1.0 if yes else 0.0,
                "yes": yes,
                "brier": _item_brier(vote.probability, yes),
                "prior": _prior_p(q),
            }
        )
    return pd.DataFrame(rows)


def _pred_frame(
    preds: list[Prediction], scored: dict[str, Question]
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for pred in preds:
        q = scored.get(pred.question_id)
        if q is None:
            continue
        yes = bool(q.ground_truth)
        rows.append(
            {
                "question_id": pred.question_id,
                "agent_id": pred.model_id,
                "species": short_name(pred.model_id),
                "model_id": pred.model_id,
                "p": float(pred.probability),
                "truth": 1.0 if yes else 0.0,
                "yes": yes,
                "brier": _item_brier(pred.probability, yes),
                "prior": _prior_p(q),
            }
        )
    return pd.DataFrame(rows)


def _mean_brier(frame: pd.DataFrame, group: str) -> pd.DataFrame:
    out = frame.groupby(group, as_index=False)["brier"].mean()
    return out.sort_values("brier")


def _plot_vote_swarm(votes: pd.DataFrame, dest: Path) -> dict[str, str] | None:
    if votes.empty:
        return None
    qids = list(votes["question_id"].unique())
    fig_h = 4.2 if len(qids) == 1 else min(2.4 * len(qids), 10)
    fig, axes = plt.subplots(
        nrows=len(qids),
        figsize=(8.6, fig_h),
        squeeze=False,
        sharex=True,
    )
    species = set(votes["species"])
    order = [s for s in SPECIES_ORDER if s in species]
    order.extend(sorted(species - set(order)))
    palette = {k: PALETTE.get(k, PURPLE) for k in order}
    for ax, qid in zip(axes[:, 0], qids):
        chunk = votes[votes["question_id"] == qid]
        truth = float(chunk["truth"].iloc[0])
        prior = float(chunk["prior"].iloc[0])
        sns.swarmplot(
            data=chunk,
            x="p",
            y="species",
            hue="species",
            order=order,
            palette=palette,
            size=9,
            linewidth=0.4,
            edgecolor=PANEL,
            ax=ax,
            legend=False,
        )
        median_p = float(chunk["p"].median())
        ax.axvline(truth, color=ACCENT, linewidth=1.8, linestyle="--", zorder=0)
        ax.axvline(prior, color=BRASS, linewidth=1.3, linestyle=":", zorder=0)
        ax.axvline(median_p, color=INK, linewidth=1.5, zorder=0)
        ax.set_xlim(-0.03, 1.03)
        ax.set_xlabel("Probability the event happens (YES)")
        ax.set_ylabel("")
        happened = "happened" if truth >= 0.5 else "did not happen"
        ax.set_title(
            f"{qid}  ·  later: {happened}  ·  "
            f"median {median_p:.2f}  ·  prior {prior:.2f}"
        )
        ax.annotate(
            "truth",
            xy=(truth, -0.62),
            color=ACCENT,
            fontsize=8,
            ha="center",
            annotation_clip=False,
        )
        ax.annotate(
            "median",
            xy=(median_p, -0.62),
            color=INK,
            fontsize=8,
            ha="center",
            annotation_clip=False,
        )
        ax.annotate(
            "2012 prior",
            xy=(prior, len(order) - 0.32),
            color=BRASS,
            fontsize=8,
            ha="center",
            annotation_clip=False,
        )
    caption = (
        "Each dot is one agent vote. Dashed green is what later happened. "
        "Solid white is the swarm median. Dotted brass is the 2012 public prior. "
        "A tight cluster on the truth side is a good swarm; a spread that the "
        "median still sits near truth is the crowd doing its job."
    )
    _finish(fig, dest)
    return {
        "id": "vote_swarm",
        "title": "Where each agent landed",
        "question": "Did the agents agree, and did their middle answer land near reality?",
        "caption": caption,
        "good_result": (
            "Dots cluster near the dashed truth line, or the white median improves on "
            "the brass historical prior."
        ),
        "file": dest.name,
    }


def _plot_brier_bars(
    agents: pd.DataFrame,
    dest: Path,
    *,
    extra_rows: list[dict[str, Any]] | None = None,
) -> dict[str, str] | None:
    means = _mean_brier(agents, "species")
    extras = pd.DataFrame(extra_rows or [])
    frame = pd.concat([means, extras], ignore_index=True) if not extras.empty else means
    if frame.empty:
        return None
    frame = frame.sort_values("brier", ascending=True).reset_index(drop=True)
    prior_val = next(
        (float(r["brier"]) for r in (extra_rows or []) if r["species"] == "2012 prior"),
        0.25,
    )
    colors: list[str] = []
    for row in frame.itertuples():
        if str(row.species).startswith("Median of "):
            colors.append(ACCENT)
        elif row.species == "2012 prior":
            colors.append(BRASS)
        elif row.species == "Coin flip":
            colors.append(MUTED)
        elif row.brier < prior_val:
            colors.append(ACCENT)
        else:
            colors.append(WARN)
    fig, ax = plt.subplots(figsize=(8.6, max(2.8, 0.42 * len(frame) + 1.2)))
    sns.barplot(
        data=frame,
        x="brier",
        y="species",
        hue="species",
        palette=dict(zip(frame["species"], colors)),
        dodge=False,
        ax=ax,
        legend=False,
    )
    ax.set_xlabel("Probability error (Brier) · smaller is better")
    ax.set_ylabel("")
    ax.set_title("How sharp were the percentages?")
    for i, row in enumerate(frame.itertuples()):
        ax.text(
            row.brier + 0.008,
            i,
            f"{row.brier:.3f}",
            va="center",
            color=INK,
            fontsize=9,
        )
    _finish(fig, dest)
    return {
        "id": "brier_bars",
        "title": "Probability error by agent",
        "question": "Whose percentages were closest to what actually happened?",
        "caption": (
            "Brier is (forecast − outcome)². 0 is perfect. About 0.25 is a coin flip. "
            "Beat the 2012 prior on the same questions before calling it skill. "
            "Green is the swarm median; brass is the prior."
        ),
        "good_result": "Shorter bars are better; zero would mean perfect probabilities.",
        "file": dest.name,
    }


def _plot_signed_error(agents: pd.DataFrame, dest: Path) -> dict[str, str] | None:
    if agents.empty:
        return None
    frame = agents.copy()
    frame["signed"] = frame["p"] - frame["truth"]
    if frame["question_id"].nunique() > 1:
        frame = (
            frame.groupby(["species", "agent_id"], as_index=False)["signed"]
            .mean()
        )
    if "agent_id" in frame.columns and frame["agent_id"].astype(str).str.startswith("swarm:").any():
        tail = frame["agent_id"].astype(str).str[-2:]
        frame["who"] = frame["species"] + "  " + tail
    else:
        frame["who"] = frame["species"]
    frame = frame.sort_values("signed").reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(8.6, max(3.2, 0.38 * len(frame) + 1.4)))
    ys = list(range(len(frame)))
    ax.axvline(0, color=ACCENT, linewidth=1.4, linestyle="--", zorder=0)
    for y, row in zip(ys, frame.itertuples()):
        color = PALETTE.get(row.species, PURPLE)
        ax.plot([0, row.signed], [y, y], color=color, linewidth=1.6, alpha=0.9)
        ax.scatter([row.signed], [y], color=color, s=48, zorder=3, edgecolors=PANEL, linewidths=0.4)
    ax.set_yticks(ys)
    ax.set_yticklabels(list(frame["who"]))
    ax.set_xlabel("Forecast − outcome  ·  0 is a perfect percentage")
    ax.set_ylabel("")
    ax.set_title("Too skeptical, or too sure?")
    _finish(fig, dest)
    return {
        "id": "signed_error",
        "title": "Overconfidence vs underconfidence",
        "question": "Does each agent systematically predict events too strongly or too weakly?",
        "caption": (
            "Zero is a perfect percentage. Left of zero: too skeptical the event would "
            "happen. Right of zero: too sure it would. Brier hides the direction; this "
            "is how you see whether a species is loud or shy."
        ),
        "good_result": "Marks close to the center line show less directional bias.",
        "file": dest.name,
    }


def _plot_item_violin(preds: pd.DataFrame, dest: Path) -> dict[str, str] | None:
    n_q = preds["question_id"].nunique()
    if preds.empty or n_q < 8:
        return None
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    order = list(_mean_brier(preds, "species")["species"])
    sns.violinplot(
        data=preds,
        x="brier",
        y="species",
        hue="species",
        order=order,
        palette={s: PALETTE.get(s, PURPLE) for s in order},
        inner="quartile",
        cut=0,
        ax=ax,
        legend=False,
    )
    ax.set_xlabel("Per-question Brier")
    ax.set_ylabel("")
    ax.set_title("Consistency across questions")
    _finish(fig, dest)
    return {
        "id": "item_brier_violin",
        "title": "Error spread across questions",
        "question": "Was a run consistently useful, or did a few large mistakes dominate it?",
        "caption": (
            "Each blob is the distribution of per-question probability error. "
            "A tight violin near zero is reliable. A long right tail is a few "
            "badly miscalibrated answers."
        ),
        "good_result": "A narrow shape concentrated near zero means consistent accuracy.",
        "file": dest.name,
    }


def render_performance_plots(
    *,
    run_id: str,
    questions: list[Question],
    predictions: list[Prediction],
    votes: list[SwarmVote],
    dest: str | Path,
) -> list[dict[str, str]]:
    dest_dir = resolve(dest)
    dest_dir.mkdir(parents=True, exist_ok=True)
    ids = {p.question_id for p in predictions} | {v.question_id for v in votes}
    scored = _scored_questions(questions, ids)
    if not scored:
        return []
    vote_df = _vote_frame(votes, scored)
    pred_df = _pred_frame(predictions, scored)
    agents = vote_df if not vote_df.empty else pred_df[pred_df["model_id"] != "prior_signal"]
    if agents.empty:
        return []
    scored_list = list(scored.values())
    prior = sum(_item_brier(_prior_p(q), bool(q.ground_truth)) for q in scored_list) / len(
        scored_list
    )
    extras = [
        {"species": "2012 prior", "brier": prior},
        {"species": "Coin flip", "brier": 0.25},
    ]
    median_df = pred_df[pred_df["model_id"] == "swarm-median"]
    if not vote_df.empty and not median_df.empty:
        per_question = vote_df.groupby("question_id")["agent_id"].nunique()
        agent_count = int(per_question.max()) if not per_question.empty else len(votes)
        median_df = median_df.copy()
        median_df["species"] = f"Median of {agent_count}"
    specs: list[dict[str, str]] = []
    with _LOCK:
        _apply_theme()
        if not vote_df.empty:
            spec = _plot_vote_swarm(vote_df, dest_dir / "vote_swarm.png")
            if spec:
                specs.append(spec)
        elif not pred_df.empty and pred_df["question_id"].nunique() <= 6:
            spec = _plot_vote_swarm(pred_df, dest_dir / "vote_swarm.png")
            if spec:
                specs.append(spec)
        bar_src = agents
        if not vote_df.empty and not median_df.empty:
            bar_src = pd.concat([vote_df, median_df], ignore_index=True)
        spec = _plot_brier_bars(bar_src, dest_dir / "brier_bars.png", extra_rows=extras)
        if spec:
            specs.append(spec)
        err_src = vote_df if not vote_df.empty else agents
        spec = _plot_signed_error(err_src, dest_dir / "signed_error.png")
        if spec:
            specs.append(spec)
        spec = _plot_item_violin(
            pred_df if not pred_df.empty else agents,
            dest_dir / "item_brier_violin.png",
        )
        if spec:
            specs.append(spec)
    for spec in specs:
        spec["run_id"] = run_id
        spec["url"] = f"/api/runs/{run_id}/plots/{spec['file']}"
    return specs


def _source_mtime(folder: Path) -> float:
    stamps = [0.0]
    for name in ("predictions.jsonl", "swarm_votes.jsonl", "results.json", "scores.json"):
        path = folder / name
        if path.exists():
            stamps.append(path.stat().st_mtime)
    return max(stamps)


def write_performance_plots(
    run_id: str,
    questions: list[Question],
    *,
    force: bool = False,
) -> list[dict[str, str]]:
    folder = run_dir(run_id)
    if not folder.is_dir():
        return []
    dest = folder / "plots"
    preds: list[Prediction] = []
    votes: list[SwarmVote] = []
    pred_path = folder / "predictions.jsonl"
    vote_path = folder / "swarm_votes.jsonl"
    if pred_path.exists() and pred_path.stat().st_size > 0:
        preds = read_jsonl(pred_path, Prediction)
    if vote_path.exists() and vote_path.stat().st_size > 0:
        votes = read_jsonl(vote_path, SwarmVote)
    if not preds and not votes:
        return []
    stamp_path = dest / ".stamp"
    meta_path = dest / "plots.json"
    source_m = _source_mtime(folder)
    if (
        not force
        and stamp_path.exists()
        and meta_path.exists()
        and dest.exists()
        and list(dest.glob("*.png"))
        and stamp_path.stat().st_mtime >= source_m
    ):
        try:
            cached = json.loads(meta_path.read_text(encoding="utf-8"))
            if (
                isinstance(cached, list)
                and cached
                and all(
                    isinstance(spec, dict)
                    and spec.get("question")
                    and spec.get("good_result")
                    for spec in cached
                )
            ):
                return cached
        except (OSError, json.JSONDecodeError):
            pass
    specs = render_performance_plots(
        run_id=run_id,
        questions=questions,
        predictions=preds,
        votes=votes,
        dest=dest,
    )
    meta_path.write_text(json.dumps(specs, indent=2), encoding="utf-8")
    stamp_path.write_text(str(source_m), encoding="utf-8")
    return specs
