from __future__ import annotations

from pathlib import Path

from leaderboard.store import build_leaderboard
from psbx.schemas import Citation, Prediction, Question, SwarmVote


def _vote(run_id: str, agent_id: str, model_id: str, agent_index: int, p: float) -> SwarmVote:
    return SwarmVote(
        run_id=run_id,
        question_id="q1",
        agent_index=agent_index,
        agent_id=agent_id,
        model_id=model_id,
        model_slug=model_id,
        temperature=0.2,
        max_tokens=64,
        probability=p,
    )


def test_swarm_champion_uses_run_score_not_global_agent_score(tmp_path: Path, monkeypatch) -> None:
    votes_by_run = {
        "run-one": [
            _vote("run-one", "agent-a", "openrouter-gpt-4.1-mini", 0, 0.9),
            _vote("run-one", "agent-b", "openrouter-gpt-4o-mini", 1, 0.1),
        ],
        "run-two": [
            _vote("run-two", "agent-a", "openrouter-gpt-4.1-mini", 0, 0.0),
            _vote("run-two", "agent-b", "openrouter-gpt-4o-mini", 1, 1.0),
        ],
    }
    for run_id in votes_by_run:
        vote_path = tmp_path / run_id / "swarm_votes.jsonl"
        vote_path.parent.mkdir()
        vote_path.touch()

    monkeypatch.setattr("leaderboard.store.run_dir", lambda run_id: tmp_path / run_id)
    monkeypatch.setattr(
        "leaderboard.store.read_jsonl",
        lambda path, _schema: votes_by_run[path.parent.name],
    )
    monkeypatch.setattr("leaderboard.store.load_predictions", lambda _run_id: [])

    question = Question(
        id="q1",
        epoch_id="e2012",
        category="economic",
        text="Will the test event happen by 2012-12-31?",
        resolution_criteria="Test fixture",
        cutoff_date="2012-06-30",
        resolution_date="2012-12-31",
        ground_truth=True,
        generator="test",
    )
    runs = [
        {"run_id": run_id, "n_votes": 2, "primary_brier": 0.25, "n_questions": 1}
        for run_id in votes_by_run
    ]

    payload = build_leaderboard(runs, [question], {})
    swarms = {row["id"]: row for row in payload["swarms"]}

    assert swarms["run-one"]["champion_agent"] == "VECTOR-01"
    assert swarms["run-two"]["champion_agent"] == "NOVA-02"


def _prediction(run_id: str, question_id: str, model_id: str, p: float) -> Prediction:
    return Prediction(
        run_id=run_id,
        question_id=question_id,
        model_id=model_id,
        probability=p,
        reasoning="fixture",
        citations=[Citation(document_id="d", quoted_span="fixture", supports="context")],
    )


def test_model_leaderboard_ranks_only_on_matched_questions(monkeypatch) -> None:
    questions = [
        Question(
            id=question_id,
            epoch_id="e2012",
            category="economic",
            text=f"Will {question_id} happen by 2012-12-31?",
            resolution_criteria="fixture",
            cutoff_date="2012-06-30",
            resolution_date="2012-12-31",
            ground_truth=truth,
            generator="test",
        )
        for question_id, truth in (("q1", True), ("q2", False), ("q3", True))
    ]
    by_run = {
        "wide": [
            _prediction("wide", "q1", "model-wide", 0.9),
            _prediction("wide", "q2", "model-wide", 0.1),
            _prediction("wide", "q3", "model-wide", 0.1),
        ],
        "partial": [
            _prediction("partial", "q1", "model-partial", 0.9),
            _prediction("partial", "q2", "model-partial", 0.1),
        ],
    }
    monkeypatch.setattr(
        "leaderboard.store.load_predictions", lambda run_id: by_run[run_id]
    )
    monkeypatch.setattr(
        "leaderboard.store.run_dir", lambda run_id: Path("not-present") / run_id
    )
    payload = build_leaderboard(
        [{"run_id": "wide"}, {"run_id": "partial"}], questions, {}
    )
    rows = {row["id"]: row for row in payload["models"]}
    assert rows["model-wide"]["record_brier"] > rows["model-partial"]["record_brier"]
    assert rows["model-wide"]["brier"] == rows["model-partial"]["brier"]
    assert rows["model-wide"]["matched_questions"] == 2
    assert rows["model-wide"]["coverage_fraction"] == 1.0
    assert rows["model-partial"]["coverage_fraction"] == 2 / 3
    assert "intersection" in payload["rules"]["comparison"]


def test_model_leaderboard_reports_ignored_duplicate_and_unknown_rows(monkeypatch) -> None:
    question = Question(
        id="known",
        epoch_id="e2012",
        category="economic",
        text="Will known happen by 2012-12-31?",
        resolution_criteria="fixture",
        cutoff_date="2012-06-30",
        resolution_date="2012-12-31",
        ground_truth=True,
        generator="test",
    )
    known = _prediction("run", "known", "model", 0.9)
    unknown = _prediction("run", "unknown", "model", 0.5)
    monkeypatch.setattr(
        "leaderboard.store.load_predictions", lambda run_id: [known, known, unknown]
    )
    monkeypatch.setattr(
        "leaderboard.store.run_dir", lambda run_id: Path("not-present") / run_id
    )
    payload = build_leaderboard([{"run_id": "run"}], [question], {})
    assert payload["summary"]["duplicate_records_ignored"] == 1
    assert payload["summary"]["unknown_question_records_ignored"] == 1
