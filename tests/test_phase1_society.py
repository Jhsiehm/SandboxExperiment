from datetime import date, datetime, timezone

import numpy as np
import pytest
from typer.testing import CliRunner

from psbx.cli import app
from psbx.config import load_epochs, load_swarm
from psbx.corpus.aggregate_sources import gallup_mip_documents, ingest_aggregate_sources
from psbx.corpus.build_index import collect_documents
from psbx.corpus.index import HybridIndex
from psbx.epochs import documents_allowed_for_advance, propose_year_step
from psbx.eval.baseline import evaluate_human_baseline, mae_vs_prior_signal, vote_spread
from psbx.eval.stimulus import items_from_questions
from psbx.io import read_jsonl
from psbx.schemas import (
    CONDITIONER_SOURCE_TYPES,
    Citation,
    Document,
    Prediction,
    Question,
    SwarmVote,
)
from psbx.society.as2_config import swarm_agent_specs
from psbx.society.perspectives import assign_personas, load_perspectives


def test_perspective_roster_expands_without_inference():
    catalog = load_perspectives()
    assert catalog.simulation_only is True
    assert catalog.not_inferred is True
    roster = load_swarm()
    assigned = assign_personas(roster, catalog)
    assert len(assigned) == 12
    assert len(catalog.catalog_only()) >= 1
    ids = [p.id for p in assigned]
    assert len(set(ids)) == 12
    extras = {p.id for p in catalog.catalog_only()}
    assert extras.isdisjoint(set(ids))
    for persona in assigned:
        assert persona.region
        assert persona.urbanicity in {"urban", "suburban", "rural"}
        assert persona.party_id in {"democrat", "republican", "independent"}
        block = persona.prompt_block()
        assert "not inferred" in block.lower() or "Simulation persona" in block


def test_swarm_specs_carry_explicit_personas():
    specs = swarm_agent_specs()
    assert len(specs) == 12
    assert all(s["profile"].get("simulation_persona") is True for s in specs)
    assert {s["profile"]["perspective_id"] for s in specs}


def test_conditioner_fixtures_respect_cutoff():
    epoch = load_epochs()["e2012"]
    docs = ingest_aggregate_sources(epoch)
    kinds = {d.source_type for d in docs}
    assert kinds >= CONDITIONER_SOURCE_TYPES
    for doc in docs:
        assert doc.published_at.date() <= epoch.cutoff_date
        assert doc.provenance
    mip = gallup_mip_documents(epoch.cutoff_date)
    assert mip
    assert all(d.published_at.date() <= epoch.cutoff_date for d in mip)
    assert all(d.published_at.strftime("%Y-%m") <= "2012-06" for d in mip)


def test_future_survey_rejected_from_index():
    epoch = load_epochs()["e2012"]
    future = Document(
        id="future-survey",
        url="https://example.com/poll-july",
        outlet="Gallup",
        published_at=datetime(2012, 7, 15, tzinfo=timezone.utc),
        title="post-cutoff poll",
        text="This survey was published after the e2012 cutoff and must not index.",
        source_type="survey",
        prominence=0.2,
        provenance="test",
    )
    with pytest.raises(AssertionError):
        HybridIndex([future], np.zeros((1, 8), dtype=np.float32), epoch.cutoff_date)


def test_collect_documents_keeps_conditioners_inside_cutoff():
    epoch = load_epochs()["e2012"]
    docs = collect_documents(epoch)
    kinds = {d.source_type for d in docs}
    assert "survey" in kinds
    assert "ad" in kinds
    assert "academic" in kinds
    for doc in docs:
        assert doc.published_at.date() <= epoch.cutoff_date


def test_media_stimulus_items_reuse_e2012_questions():
    qs = read_jsonl("data/questions/e2012.jsonl", Question)[:5]
    items = items_from_questions(qs)
    assert len(items) == 5
    assert all(item.stimulus_kind == "contemporaneous_media" for item in items)
    assert all(item.score_field == "ground_truth" for item in items)
    assert {item.question_id for item in items} == {q.id for q in qs}


def test_human_baseline_eval_two_tracks():
    qs = read_jsonl("data/questions/e2012.jsonl", Question)[:3]
    preds = [
        Prediction(
            run_id="t-eval",
            question_id=q.id,
            model_id="swarm-median",
            probability=0.4,
            reasoning="test",
            citations=[
                Citation(document_id="d", quoted_span="span of evidence", supports="context")
            ],
        )
        for q in qs
    ]
    votes = [
        SwarmVote(
            run_id="t-eval",
            question_id=qs[0].id,
            agent_index=i,
            agent_id=f"swarm:x:{i:02d}",
            model_id="openrouter-gpt-4.1-mini",
            model_slug="openai/gpt-4.1-mini",
            temperature=0.8,
            max_tokens=256,
            probability=0.3 + 0.02 * i,
            perspective_id=f"persona-{i}",
        )
        for i in range(12)
    ]
    report = evaluate_human_baseline(
        "t-eval", predictions=preds, questions=qs, votes=votes
    )
    assert "A_media_stimulus" in report.tracks
    assert "B_demographic_swarm" in report.tracks
    assert report.tracks["A_media_stimulus"].brier_vs_later_outcomes is not None
    assert report.tracks["A_media_stimulus"].mae_vs_prior_signal is not None
    assert report.tracks["B_demographic_swarm"].vote_spread is not None
    assert mae_vs_prior_signal(preds, qs) is not None
    assert vote_spread(votes) > 0


def test_year_step_hook_does_not_ingest_future():
    epoch = load_epochs()["e2012"]
    payload = propose_year_step(epoch, years=1)
    assert payload["ingests_documents"] is False
    assert payload["policy_sim"] is False
    assert payload["to_cutoff"] == "2013-06-30"
    old = Document(
        id="old",
        url="https://example.com/old",
        outlet="Reuters",
        published_at=datetime(2012, 1, 1, tzinfo=timezone.utc),
        title="old",
        text="already in e2012",
        source_type="wire",
    )
    nxt = Document(
        id="next-year",
        url="https://example.com/2013",
        outlet="Reuters",
        published_at=datetime(2013, 1, 15, tzinfo=timezone.utc),
        title="next year",
        text="would be allowed only after an enabled year-step ingest",
        source_type="wire",
    )
    leak = Document(
        id="leak",
        url="https://example.com/2014",
        outlet="Reuters",
        published_at=datetime(2014, 1, 1, tzinfo=timezone.utc),
        title="too far",
        text="beyond the proposed cutoff",
        source_type="wire",
    )
    kept = documents_allowed_for_advance(
        [old, nxt, leak],
        epoch.cutoff_date,
        date.fromisoformat(payload["to_cutoff"]),
    )
    assert [d.id for d in kept] == ["next-year"]


def test_mock_society_swarm_config_allows_heuristic():
    from psbx.config import load_run

    mock = load_run("config/run-society-swarm-mock.yaml")
    assert mock.allow_mock is True
    assert mock.use_swarm is True
    assert mock.perspectives == "config/perspectives.yaml"
    live = load_run("config/run-society-swarm.yaml")
    assert live.allow_mock is False


def test_eval_and_epoch_cli(monkeypatch):
    monkeypatch.setenv("PSBX_MOCK_LLM", "1")
    runner = CliRunner()
    result = runner.invoke(app, ["epoch", "propose", "--from", "e2012", "--years", "1"])
    assert result.exit_code == 0, result.output
    assert "ingests_documents" in result.output
    result = runner.invoke(app, ["eval", "baseline", "--run", "missing-run"])
    assert result.exit_code == 0, result.output
    assert "A_media_stimulus" in result.output
