from __future__ import annotations

import json
from datetime import date

from psbx.agents.runner import ToolCall, Turn
from psbx.io import write_jsonl
from psbx.sandbox.harness import run_set
from psbx.schemas import Citation, Epoch, ModelConfig, Prediction, Question, RunConfig


class RecordingBackend:
    def __init__(self) -> None:
        self.n_calls = 0
        self._queries: list[str] = []

    @property
    def queries(self) -> list[str]:
        return list(self._queries)

    def search(self, query, k=10, min_prominence=0.0, source_types=None):
        del k, min_prominence, source_types
        self.n_calls += 1
        self._queries.append(query)
        return []

    def fetch(self, document_id):
        self.n_calls += 1
        return {
            "id": document_id,
            "title": "Fixture",
            "published_at": "2012-01-01T00:00:00",
            "text": "fixture quotation",
        }


def _question(question_id: str) -> Question:
    return Question(
        id=question_id,
        epoch_id="e2012",
        category="economic",
        text=f"Will fixture outcome {question_id} occur by 2012-12-31?",
        resolution_criteria="deterministic fixture",
        cutoff_date=date(2012, 6, 30),
        resolution_date=date(2012, 12, 31),
        ground_truth=True,
        generator="test",
    )


def _model(model_id: str, provider: str) -> ModelConfig:
    return ModelConfig(
        id=model_id,
        provider=provider,
        model_name=f"fixture/{model_id}",
        declared_pretraining_cutoff=date(2011, 1, 1),
        is_instruction_tuned=True,
    )


def test_live_run_isolates_retrieval_per_forecast_and_refuses_batch_overshoot(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("PSBX_MOCK_LLM", raising=False)
    monkeypatch.setenv("PSBX_ENABLE_PAID_MODELS", "0")
    backend = RecordingBackend()
    questions = [_question("q1"), _question("q2")]
    models = [_model("openai-fixture", "openai"), _model("anthropic-fixture", "anthropic")]
    epoch = Epoch(
        id="e2012",
        cutoff_date=date(2012, 6, 30),
        resolution_window_end=date(2013, 6, 30),
        corpus_index_path="unused",
    )
    run = RunConfig(
        run_id="retrieval-budget-live-fixture",
        epoch="e2012",
        models=[model.id for model in models],
        question_set="unused.jsonl",
        max_tool_calls=2,
        n_questions=2,
        allow_mock=False,
    )
    output = tmp_path / "runs" / run.run_id
    existing = Prediction(
        run_id=run.run_id,
        question_id="q1",
        model_id="openai-fixture",
        probability=0.5,
        reasoning="resumed",
        citations=[
            Citation(
                document_id="fixture-doc",
                quoted_span="fixture quotation",
                supports="context",
            )
        ],
    )
    write_jsonl(output / "predictions.jsonl", [existing])

    monkeypatch.setattr("psbx.sandbox.harness.load_index", lambda *args, **kwargs: object())
    monkeypatch.setattr("psbx.sandbox.harness.search_client_for", lambda *args: backend)
    monkeypatch.setattr("psbx.sandbox.harness.prepare_spend_guard", lambda *args: None)
    monkeypatch.setattr("psbx.sandbox.harness.ensure_run_provenance", lambda *args: None)
    monkeypatch.setattr("psbx.sandbox.harness.skip_reason", lambda model: None)
    monkeypatch.setattr("psbx.sandbox.harness.run_dir", lambda run_id: tmp_path / "runs" / run_id)
    monkeypatch.setattr("psbx.sandbox.harness.validate_citations", lambda pred, index: pred)

    turns: dict[tuple[str, str], int] = {}
    refused_results = []

    def fake_complete(model, messages, *, system, tools=True):
        del system
        question_id = "q1" if "Question id: q1" in json.dumps(messages) else "q2"
        key = (model.id, question_id)
        attempt = turns.get(key, 0)
        turns[key] = attempt + 1
        if attempt == 0:
            assert tools is True
            calls = [
                ToolCall(
                    id=f"{model.id}-{question_id}-{index}",
                    name="search",
                    arguments={"query": f"{model.id}-{question_id}-{index}"},
                )
                for index in range(3)
            ]
            if model.provider == "anthropic":
                return Turn(
                    text="",
                    tool_calls=calls,
                    anthropic_content=[
                        {
                            "type": "tool_use",
                            "id": call.id,
                            "name": call.name,
                            "input": call.arguments,
                        }
                        for call in calls
                    ],
                )
            return Turn(
                text="",
                tool_calls=calls,
                openai_message={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments),
                            },
                        }
                        for call in calls
                    ],
                },
            )

        assert tools is False
        if model.provider == "anthropic":
            results = messages[-1]["content"]
            assert {row["tool_use_id"] for row in results} == {
                f"{model.id}-{question_id}-{index}" for index in range(3)
            }
            refused_results.extend(row["content"] for row in results)
        else:
            results = messages[-3:]
            assert {row["tool_call_id"] for row in results} == {
                f"{model.id}-{question_id}-{index}" for index in range(3)
            }
            refused_results.extend(row["content"] for row in results)
        return Turn(
            text=(
                '{"probability":0.4,"reasoning":"fixture","citations":'
                '[{"document_id":"fixture-doc","quoted_span":"fixture quotation",'
                '"supports":"context"}]}'
            )
        )

    monkeypatch.setattr("psbx.agents.single_agent.complete_turn", fake_complete)
    predictions = run_set(questions, models, epoch, run)

    fresh = [prediction for prediction in predictions if prediction.reasoning != "resumed"]
    assert len(fresh) == 3
    assert backend.n_calls == 3 * run.max_tool_calls
    assert all(prediction.n_tool_calls == run.max_tool_calls for prediction in fresh)
    assert all(len(prediction.search_queries) == run.max_tool_calls for prediction in fresh)
    assert sum("allowance exhausted" in result for result in refused_results) == 3
