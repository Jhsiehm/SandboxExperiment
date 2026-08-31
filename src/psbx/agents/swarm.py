"""Phase 3 stub. Perception-filtered multi-agent comparison.

The AgentSociety 2 scaffold (`custom/`, `psbx society run`) is the intended
home for a later swarm vs single-agent comparison. This module stays a stub
until min_prominence perception runs are in scope.
"""

from __future__ import annotations

from psbx.schemas import Epoch, ModelConfig, Prediction, Question


def run_swarm(
    question: Question,
    model: ModelConfig,
    epoch: Epoch,
    run_id: str,
) -> Prediction:
    raise NotImplementedError(
        "swarm.py is a Phase 3 stub: raise min_prominence and compare single-agent vs swarm"
    )
