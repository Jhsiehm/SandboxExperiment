"""Plain-language scoreboard for the research dashboard."""

from __future__ import annotations

from typing import Any

from psbx.schemas import ModelConfig

RUN_LABELS = {
    "phase1-e2012-smoke": "Practice run (no live AI)",
    "phase2-e2012-real": "Live Claude + GPT",
    "phase2-e2012-openrouter": "Live OpenRouter probe (GPT-4.1 mini)",
    "phase2-e2012-swarm-probe": "Live swarm (median of 12)",
    "phase1-e2012-society": "Society scaffold",
    "phase1-e2012-docker": "Practice run through Docker search",
}

MODEL_LABELS = {
    "gpt-oss-2012ish": "2012-era local model",
    "frontier-a": "Claude Sonnet 4.5",
    "frontier-b": "GPT-4.1 mini",
    "openrouter-gpt-4.1-mini": "swarm worker · OpenAI mini",
    "openrouter-gpt-4o-mini": "swarm worker · OpenAI mini (4o alternate)",
    "openrouter-haiku": "swarm species · Haiku",
    "swarm-median": "swarm · median of 12",
    "openrouter-gemini-flash-lite": "optional scale-up · Gemini Flash-Lite",
    "local-llama-3.1-8b": "local scale-up · Llama 3.1 8B",
    "local-qwen-2.5-7b": "local scale-up · Qwen2.5 7B",
    "prior_signal": "2012 public prior",
}

BASELINE_LABELS = {
    "prior_signal": "2012 public prior",
    "always_base_rate": "Same guess every time",
    "always_0.5": "Coin flip",
    "status_quo_persistence": "Always say no",
    "phase1_heuristic": "Keyword lookup (not a live model)",
}

BASELINE_NOTES = {
    "prior_signal": "What a careful reader already knew in June 2012 (polls, bill status). Beat this on probability error before calling it skill.",
    "always_base_rate": "Give every question the same probability.",
    "always_0.5": "Guess 50% every time.",
    "status_quo_persistence": "Assume nothing happens.",
    "phase1_heuristic": "A keyword search rule from the practice run, not Claude or GPT.",
}

STORY = [
    {
        "step": "1",
        "title": "Pretend today is 30 June 2012",
        "body": "The agent may only read news and official documents published on or before that date. It cannot browse the modern web.",
    },
    {
        "step": "2",
        "title": "Ask 50 yes-or-no questions about the next year",
        "body": "Unemployment, bills, geopolitics. Each question has a real later answer we already know, but the agent is not supposed to look that answer up.",
    },
    {
        "step": "3",
        "title": "Score two different things",
        "body": "Probability error (Brier): were the percentages honest? Ranking (C-index): did it put the events that happened above the ones that did not?",
    },
]

METRICS = [
    {
        "id": "brier",
        "name": "Probability error",
        "short": "Brier",
        "plain": "How far off the percentages were. 0 is perfect. About 0.25 is a coin flip. Smaller is better.",
        "direction": "lower is better",
        "good": "Closer to 0 than the 2012 public prior means real skill, not just memory.",
    },
    {
        "id": "c_index",
        "name": "Ranking",
        "short": "C-index",
        "plain": "Of every pair (one event that happened, one that did not), how often did the higher probability go to the one that happened? 0.50 is guessing. 1.00 is perfect order. Larger is better.",
        "direction": "higher is better",
        "good": "A 2025 model can rank 2012 events well because it remembers history, even if its percentages are sloppy.",
    },
]


def run_label(run_id: str | None) -> str:
    if not run_id:
        return "No run"
    return RUN_LABELS.get(run_id, run_id)


def model_label(model_id: str, models: dict[str, ModelConfig] | None = None) -> str:
    if model_id in MODEL_LABELS:
        return MODEL_LABELS[model_id]
    if models and model_id in models:
        m = models[model_id]
        if m.label:
            return m.label
        return f"{m.model_name} ({m.provider})"
    return model_id


def explain_scores(payload: dict[str, Any], models: dict[str, ModelConfig] | None = None) -> dict[str, Any]:
    report = payload.get("report") or {}
    bases = dict(payload.get("baselines") or report.get("baselines") or {})
    prior_view = payload.get("prior_signal") or {}
    if "prior_signal" not in bases and prior_view.get("brier") is not None:
        bases["prior_signal"] = prior_view["brier"]

    by_model = dict(report.get("brier_by_model") or {})
    index_by = dict(report.get("brier_index_by_model") or {})
    c_by = dict(report.get("c_index_by_model") or {})
    c_bases = dict(report.get("c_index_baselines") or {})
    if prior_view.get("c_index") is not None and "prior_signal" not in c_bases:
        c_bases["prior_signal"] = prior_view["c_index"]
    prior = bases.get("prior_signal")
    base_rate = bases.get("always_base_rate")

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for mid, score in by_model.items():
        rows.append(
            _row(
                mid,
                "model",
                model_label(mid, models),
                score,
                index_by.get(mid),
                c_by.get(mid),
                prior,
                base_rate,
                note=_model_note(mid, models),
            )
        )
        seen.add(mid)

    for key, score in bases.items():
        if key in seen:
            continue
        rows.append(
            _row(
                key,
                "baseline",
                BASELINE_LABELS.get(key, key.replace("_", " ")),
                score,
                _index(score),
                c_bases.get(key),
                prior,
                base_rate,
                note=BASELINE_NOTES.get(key, ""),
            )
        )

    rows.sort(key=lambda r: (r["brier"] is None, r["brier"] if r["brier"] is not None else 9))
    finite = [r["brier"] for r in rows if r["brier"] is not None]
    ceiling = max(finite) if finite else 1.0
    if ceiling <= 0:
        ceiling = 1.0
    for row in rows:
        row["bar"] = None if row["brier"] is None else round(row["brier"] / ceiling, 4)
        row["c_bar"] = None if row["c_index"] is None else round(max(0.0, min(1.0, row["c_index"])), 4)

    beating_prior = list(report.get("models_beating_prior_signal") or [])
    if not beating_prior and prior is not None:
        beating_prior = [
            r["id"] for r in rows if r["kind"] == "model" and r["brier"] is not None and r["brier"] < prior
        ]

    verdict = _verdict(rows, prior, beating_prior, payload.get("run_id"))
    return {
        "run_id": payload.get("run_id"),
        "run_label": run_label(payload.get("run_id")),
        "source": payload.get("source"),
        "story": STORY,
        "metrics": METRICS,
        "verdict": verdict,
        "scoreboard": rows,
        "how_to_read": METRICS[0]["plain"] + " " + METRICS[1]["plain"],
        "contamination_note": _contamination_note(report, models),
        "n_predictions": report.get("n_predictions") or 0,
        "n_flagged": report.get("n_flagged") or 0,
        "brier_by_category": report.get("brier_by_category") or {},
    }


def _row(
    rid: str,
    kind: str,
    label: str,
    brier: float | None,
    index: float | None,
    c_index: float | None,
    prior: float | None,
    base_rate: float | None,
    note: str,
) -> dict[str, Any]:
    vs_prior = None if brier is None or prior is None else round(brier - prior, 4)
    return {
        "id": rid,
        "kind": kind,
        "label": label,
        "brier": brier,
        "brier_index": index,
        "c_index": c_index,
        "beats_prior": bool(brier is not None and prior is not None and brier < prior),
        "beats_base": bool(brier is not None and base_rate is not None and brier < base_rate),
        "delta_vs_prior": vs_prior,
        "note": note,
        "reference": rid == "prior_signal",
    }


def _index(brier: float | None) -> float | None:
    if brier is None:
        return None
    return (1.0 - (brier**0.5)) * 100.0


def _model_note(mid: str, models: dict[str, ModelConfig] | None) -> str:
    if not models or mid not in models:
        return ""
    m = models[mid]
    return f"This model’s stated training cutoff is {m.declared_pretraining_cutoff.isoformat()}."


def _verdict(
    rows: list[dict[str, Any]],
    prior: float | None,
    beating_prior: list[str],
    run_id: str | None,
) -> dict[str, str]:
    models = [r for r in rows if r["kind"] == "model"]
    ranked = [r for r in models if r.get("c_index") is not None]
    best_c = max(ranked, key=lambda r: r["c_index"]) if ranked else None
    ranking = ""
    if best_c:
        ranking = (
            f"{best_c['label']} ranked events at {best_c['c_index']:.2f} "
            "(0.50 is guessing which ones happened; 1.00 is perfect order)."
        )
    if not models:
        return {
            "tone": "empty",
            "headline": "Nothing has been scored yet.",
            "detail": "Use Run practice to score a simple keyword lookup, or Run live once API keys are set.",
            "ranking": "Ranking (C-index) will appear after a scored run.",
        }
    labels = {r["id"]: r["label"] for r in rows}
    best = min(models, key=lambda r: r["brier"] if r["brier"] is not None else 9)
    if beating_prior:
        names = ", ".join(labels.get(i, i) for i in beating_prior)
        verdict = {
            "tone": "win",
            "headline": f"{names} beat the 2012 public prior on probability error.",
            "detail": (
                f"Best probability error is {best['brier']:.3f} ({best['label']}). "
                f"The 2012 prior is {prior:.3f}. Smaller is better. "
                f"This is {run_label(run_id)}."
            ),
            "ranking": ranking,
        }
    else:
        prior_txt = f"{prior:.3f}" if prior is not None else "—"
        extra = ""
        if best["delta_vs_prior"] is not None and best["delta_vs_prior"] > 0:
            extra = f" That is {best['delta_vs_prior']:.3f} worse than the prior."
        verdict = {
            "tone": "miss",
            "headline": "No model beat the 2012 public prior on probability error.",
            "detail": (
                f"Best model error is {best['brier']:.3f} ({best['label']}). "
                f"The 2012 public prior is {prior_txt}.{extra} "
                "The agent is not yet more accurate than facts already sitting on the question."
            ),
            "ranking": ranking,
        }
    scores = [r["brier"] for r in models if r["brier"] is not None]
    if len(scores) > 1 and len({round(s, 6) for s in scores}) == 1:
        verdict["detail"] += (
            " Every model row matches because this practice run used one keyword rule "
            "for every label — it is not three independent AIs."
        )
    return verdict


def _contamination_note(report: dict[str, Any], models: dict[str, ModelConfig] | None) -> str:
    curves = report.get("contamination") or []
    if not curves:
        return (
            "We also check whether a model only gets better after its training cutoff. "
            "On this 2012 set, today’s big models were trained years later, so that chart "
            "cannot show a before/after spike. Ranking vs probability error is the useful split."
        )
    post = [c.get("post_cutoff_mean_brier") for c in curves]
    if any(v is None for v in post):
        return (
            "Today’s Claude and GPT were trained long after these 2012–2013 answers. "
            "They may remember what happened (high ranking) even if their percentages "
            "are sloppy (high probability error). That split is the point of this epoch, "
            "not a reason to skip it."
        )
    return (
        "This chart is accuracy versus how far the answer date sits from the model’s "
        "training cutoff. A sudden jump once that gap crosses zero is a leakage signal."
    )
