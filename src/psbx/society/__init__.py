"""AgentSociety 2 scaffold for the frozen-epoch forecast benchmark."""

from psbx.society.as2_config import swarm_agent_specs
from psbx.society.experiment import agent_specs_for_models, run_society, run_society_swarm
from psbx.society.perspectives import assign_personas, load_perspectives
from psbx.society.shim import load_as2

__all__ = [
    "agent_specs_for_models",
    "assign_personas",
    "load_as2",
    "load_perspectives",
    "run_society",
    "run_society_swarm",
    "swarm_agent_specs",
]
