"""AgentSociety 2 InitConfig / StepsConfig export from this repo's swarm roster.

The sibling clone is ``../AgentSociety`` (or ``PSBX_AGENTSOCIETY_ROOT``).
We emit the real CLI contract (``module_type`` / ``agent_type`` / questionnaire
JSON votes). We do not vendor their urban simulator.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from psbx.agents.swarm import expand_bodies, load_roster, worker_models
from psbx.config import load_epochs, load_models
from psbx.io import write_json
from psbx.paths import agentsociety_root, repo_root, resolve
from psbx.schemas import Question, RunConfig, SwarmRoster
from psbx.society.perspectives import assign_personas, load_perspectives

AGENT_CLASS = "ForecasterAgent"
ENV_CLASS = "FrozenEpochEnv"
CUTOFF_ISO = "2012-06-30T00:00:00"

# Keys AgentSociety 2 CLI lifts out of agent kwargs into the static config record.
AS2_AGENT_CONFIG_KEYS = frozenset(
    {
        "max_react_turns",
        "enable_memory",
        "enable_todo_list",
        "disabled_skill_ids",
        "default_activated_skill_ids",
        "extra_skill_paths",
    }
)


def portable_agentsociety_root() -> str | None:
    """Relative sibling path for committed configs. Never bake a machine-local path."""
    sibling = agentsociety_root()
    if sibling is None:
        return None
    expected = repo_root().parent / "AgentSociety"
    if sibling.resolve() == expected.resolve():
        return "../AgentSociety"
    return str(sibling)


def swarm_agent_specs(roster: SwarmRoster | None = None) -> list[dict[str, Any]]:
    """12 ForecasterAgent specs: ``{id, profile, config}`` (AS2 record layout)."""
    roster = roster or load_roster()
    models = load_models()
    try:
        personas = assign_personas(roster, load_perspectives())
    except (FileNotFoundError, ValueError):
        personas = []
    specs: list[dict[str, Any]] = []
    index = 0
    for species in expand_bodies(roster):
        cfg = models[species.model_id]
        if cfg.needs_endpoint:
            continue
        agent_id = index + 1
        persona = personas[index] if index < len(personas) else None
        name = f"forecaster-{species.model_id}-{index:02d}"
        if persona is not None:
            name = f"{persona.id}-{species.model_id}"
        profile: dict[str, Any] = {
            "id": agent_id,
            "name": name,
            "role": "historical forecaster",
            "bio": (
                (persona.prompt_block() if persona is not None else None)
                or species.notes
                or "Uses only FrozenEpochEnv search/fetch as of the cutoff date."
            ),
            "model_id": species.model_id,
            "model_slug": cfg.model_name,
        }
        if persona is not None:
            profile.update(
                {
                    "perspective_id": persona.id,
                    "region": persona.region,
                    "urbanicity": persona.urbanicity,
                    "party_id": persona.party_id,
                    "age_band": persona.age_band,
                    "education": persona.education,
                    "media_diet": list(persona.media_diet),
                    "simulation_persona": True,
                }
            )
        specs.append(
            {
                "id": agent_id,
                "profile": profile,
                "config": {
                    "model_id": species.model_id,
                    "model_slug": cfg.model_name,
                    "agent_class": AGENT_CLASS,
                    "temperature": species.temperature,
                    "max_tokens": species.max_tokens,
                    "max_react_turns": 2,
                    "enable_memory": False,
                    "enable_todo_list": False,
                    "perspective_id": persona.id if persona is not None else "",
                },
            }
        )
        index += 1
    if len(specs) != len(worker_models(roster)):
        raise RuntimeError("swarm agent specs drifted from OpenRouter workers")
    return specs


def init_config_payload(
    *,
    epoch_id: str = "e2012",
    min_prominence: float = 0.0,
    roster: SwarmRoster | None = None,
    question_set: str = "data/questions/e2012.jsonl",
    run_config: str = "config/run-society-swarm.yaml",
) -> dict[str, Any]:
    """Pydantic ``InitConfig`` shape used by ``agentsociety`` CLI."""
    specs = swarm_agent_specs(roster)
    agents = []
    for spec in specs:
        kwargs: dict[str, Any] = dict(spec["profile"])
        kwargs["id"] = spec["id"]
        for key, value in spec["config"].items():
            if key in AS2_AGENT_CONFIG_KEYS:
                kwargs[key] = value
        agents.append(
            {
                "agent_id": spec["id"],
                "agent_type": AGENT_CLASS,
                "kwargs": kwargs,
            }
        )
    sibling = portable_agentsociety_root()
    return {
        "env_modules": [
            {
                "module_type": ENV_CLASS,
                "kwargs": {
                    "epoch_id": epoch_id,
                    "min_prominence": min_prominence,
                },
            }
        ],
        "agents": agents,
        "codegen_router": {"final_summary_enabled": False},
        "psbx": {
            "question_set": question_set,
            "run_config": run_config,
            "agentsociety_root": sibling,
            "note": (
                "Votes stay on psbx OpenRouter (serialized). Install agentsociety2 "
                "from the sibling clone to run this file with the real CLI."
            ),
        },
    }


def questionnaire_prompt(question: Question, cutoff: date) -> str:
    return (
        f"Frozen clock is {cutoff.isoformat()}. That date is now.\n"
        "Call FrozenEpochEnv.epoch_clock, FrozenEpochEnv.persona_card, "
        "FrozenEpochEnv.evidence_pack, FrozenEpochEnv.list_source_types, "
        "FrozenEpochEnv.search, and FrozenEpochEnv.fetch only. "
        "Do not browse the live web.\n"
        "Track A: contemporaneous headlines are the stimulus. "
        "Track B: surveys, ads, and academic studies condition your persona's reaction. "
        "Forecast later public/political response as this simulation persona would.\n\n"
        f"Question id: {question.id}\n"
        f"Resolution date: {question.resolution_date.isoformat()}\n"
        f"Resolution criteria: {question.resolution_criteria}\n\n"
        f"{question.text}\n\n"
        "Reply with JSON only: "
        '{"p": <0-1>, "rationale": "<at most forty words, no chain of thought>"}.'
    )


def steps_payload(questions: list[Question], cutoff: date) -> dict[str, Any]:
    """Pydantic ``StepsConfig`` shape: one questionnaire step per forecast item."""
    start = datetime.combine(cutoff, datetime.min.time()).isoformat()
    steps = []
    for question in questions:
        steps.append(
            {
                "type": "questionnaire",
                "questionnaire_id": f"e2012-{question.id}",
                "title": f"Frozen-epoch forecast {question.id}",
                "description": (
                    "Each ForecasterAgent is a simulation persona. "
                    "Headlines are the stimulus; surveys/ads/studies condition. "
                    "psbx scores the median p as swarm-median vs later outcomes."
                ),
                "questions": [
                    {
                        "id": question.id,
                        "prompt": questionnaire_prompt(question, cutoff),
                        "response_type": "json",
                    }
                ],
            }
        )
    if not steps:
        steps.append(
            {
                "type": "ask",
                "question": (
                    f"Read FrozenEpochEnv.epoch_clock. Today is {cutoff.isoformat()}. "
                    "Search, fetch, then forecast."
                ),
            }
        )
    return {"start_t": start, "steps": steps}


def export_society_bundle(
    run: RunConfig,
    questions: list[Question],
    dest: str | Path,
    *,
    roster: SwarmRoster | None = None,
) -> dict[str, Path]:
    """Write InitConfig, steps.yaml, agent_specs, and a SOCIETY.json checkpoint."""
    dest_dir = resolve(dest)
    dest_dir.mkdir(parents=True, exist_ok=True)
    epoch = load_epochs()[run.epoch]
    roster = roster or load_roster(run.swarm_roster or "config/swarm.yaml")
    specs = swarm_agent_specs(roster)
    init_path = write_json(
        dest_dir / "init_config.json",
        init_config_payload(
            epoch_id=run.epoch,
            min_prominence=run.min_prominence,
            roster=roster,
            question_set=run.question_set,
            run_config="config/run-society-swarm.yaml",
        ),
    )
    steps = steps_payload(questions, epoch.cutoff_date)
    steps_path = dest_dir / "steps.yaml"
    steps_path.write_text(
        yaml.safe_dump(steps, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    specs_path = write_json(
        dest_dir / "agent_specs.json",
        {
            "agent_specs": specs,
            "agent_class_name": AGENT_CLASS,
            "backend": "shim",
            "n_agents": len(specs),
            "workspace_root": ".",
            "agentsociety_root": portable_agentsociety_root(),
        },
    )
    society_path = write_json(
        dest_dir / "SOCIETY.json",
        {
            "schema_version": 1,
            "agent_class_name": AGENT_CLASS,
            "agent_specs": specs,
            "env_module_types": [ENV_CLASS],
            "env_kwargs": {
                ENV_CLASS: {
                    "epoch_id": run.epoch,
                    "min_prominence": run.min_prominence,
                }
            },
            "batch_size": 12,
            "steps_hash": None,
        },
    )
    from psbx.society.workspaces import write_agent_workspaces

    agents_root = write_agent_workspaces(dest_dir / "agents", specs)
    return {
        "init_config": init_path,
        "steps": steps_path,
        "agent_specs": specs_path,
        "society": society_path,
        "agents": agents_root,
    }
