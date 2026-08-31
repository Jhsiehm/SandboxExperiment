"""Plain-language scoreboard for the research dashboard."""

from __future__ import annotations

from typing import Any

from psbx.schemas import ModelConfig

RUN_LABELS = {
    "phase1-e2012-smoke": "Mock heuristic",
    "phase2-e2012-real": "Live frontier models",
    "phase1-e2012-society": "Society scaffold",
}

MODEL_LABELS = {
    "gpt-oss-2012ish": "2012-era local (gpt2)",
    "frontier-a": "Claude Sonnet 4.5",
    "frontier-b": "GPT-4.1 mini",
    "prior_signal": "Contemporaneous prior",
}

BASELINE_LABELS = {
    "prior_signal": "Contemporaneous prior",
    "always_base_rate": "Always the average yes-rate",
    "always_0.5": "Always 50%",
    "status_quo_persistence": "Always no",
    "phase1_heuristic": "Phase 1 retrieval heuristic",
}

BASELINE_NOTES = {
    "prior_signal": "Public 2012 signal already in the question (polls, bill status). This is the bar to beat.",
    "always_base_rate": "Predict the same probability on every question.",
    "always_0.5": "Uninformative coin flip.",
    "status_quo_persistence": "Assume the event does not happen.",
    "phase1_heuristic": "Keyword retrieval heuristic from the mock run, not a live model.",
}

HOW_TO_READ = (
    "Brier score is (forecast − outcome)², averaged. 0 is perfect, 0.25 is a coin flip "
    "on a balanced set. Lower is better. A model is only useful here if it beats the "
    "contemporaneous prior — information that was already public at the cutoff."
)


def run_label(run_id: str | None) -> str:
    if not run_id:
        return "No run"
    return RUN_LABELS.get(run_id, run_id)


def model_label(model_id: str, models: dict[str, ModelConfig] | None = None) -> str:
    if model_id in MODEL_LABELS:
        return MODEL_LABELS[model_id]
    if models and model_id in models:
        m = models[model_id]
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

    beating_prior = list(report.get("models_beating_prior_signal") or [])
    if not beating_prior and prior is not None:
        beating_prior = [r["id"] for r in rows if r["kind"] == "model" and r["brier"] is not None and r["brier"] < prior]

    verdict = _verdict(rows, prior, beating_prior, payload.get("run_id"))
    return {
        "run_id": payload.get("run_id"),
        "run_label": run_label(payload.get("run_id")),
        "source": payload.get("source"),
        "verdict": verdict,
        "scoreboard": rows,
        "how_to_read": HOW_TO_READ,
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
    return f"Declared training cutoff {m.declared_pretraining_cutoff.isoformat()} · {m.provider}"


def _verdict(
    rows: list[dict[str, Any]],
    prior: float | None,
    beating_prior: list[str],
    run_id: str | None,
) -> dict[str, str]:
    models = [r for r in rows if r["kind"] == "model"]
    if not models:
        return {
            "tone": "empty",
            "headline": "No scored model run yet.",
            "detail": "Run mock to score the retrieval heuristic, or run live once Anthropic and OpenAI keys are set. The contemporaneous prior is already computed from the question set.",
        }
    labels = {r["id"]: r["label"] for r in rows}
    best = min(models, key=lambda r: r["brier"] if r["brier"] is not None else 9)
    if beating_prior:
        names = ", ".join(labels.get(i, i) for i in beating_prior)
        verdict = {
            "tone": "win",
            "headline": f"{names} beat the contemporaneous prior.",
            "detail": (
                f"Best Brier is {best['brier']:.3f} ({best['label']}). "
                f"Prior is {prior:.3f}. Lower is better. Run {run_label(run_id)}."
            ),
        }
    else:
        prior_txt = f"{prior:.3f}" if prior is not None else "—"
        extra = ""
        if best["delta_vs_prior"] is not None and best["delta_vs_prior"] > 0:
            extra = f" That is {best['delta_vs_prior']:.3f} worse than the prior."
        verdict = {
            "tone": "miss",
            "headline": "No model beat the contemporaneous prior.",
            "detail": (
                f"Best model Brier is {best['brier']:.3f} ({best['label']}). "
                f"The 2012 public prior is {prior_txt}.{extra} "
                "The agent is not yet extracting more than what was already in the question metadata."
            ),
        }
    scores = [r["brier"] for r in models if r["brier"] is not None]
    if len(scores) > 1 and len({round(s, 6) for s in scores}) == 1:
        verdict["detail"] += (
            " All model rows share this score because the mock run used one retrieval heuristic "
            "for every config — it is not three independent live models."
        )
    return verdict


def _contamination_note(report: dict[str, Any], models: dict[str, ModelConfig] | None) -> str:
    curves = report.get("contamination") or []
    if not curves:
        return (
            "The contamination chart needs scored predictions. On e2012, questions resolve in "
            "2012–2013 while frontier cutoffs are 2024–2025, so a leakage spike at gap=0 cannot appear."
        )
    post = [c.get("post_cutoff_mean_brier") for c in curves]
    if any(v is None for v in post):
        return (
            "Most registered models have training cutoffs after these questions resolve, "
            "so they have no post-cutoff slice. A leakage spike at gap=0 cannot appear for them. "
            "Use the scoreboard (model vs prior) as the headline comparison on e2012."
        )
    return (
        "Accuracy vs gap (resolution date minus declared training cutoff). "
        "A sharp improvement once the gap crosses zero is a leakage signal."
    )
