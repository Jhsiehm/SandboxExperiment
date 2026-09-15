from __future__ import annotations

from pathlib import Path

from leaderboard.store import build_leaderboard
from psbx.schemas import Question, SwarmVote


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
