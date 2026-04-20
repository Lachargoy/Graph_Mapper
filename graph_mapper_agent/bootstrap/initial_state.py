from __future__ import annotations
#graph_mapper_agent/bootstrap/initial_state.py
from typing import Any

from .dto import RunGraphMapperInput


def build_initial_state(
    *,
    input_data: RunGraphMapperInput,
    execution_metadata: dict[str, Any],
    planned_goal_trace: object | None,
    ledger_run: object,
    ledger_actor: object,
    ledger_target: object,
) -> dict[str, object]:
    return {
        "entry_url": input_data.request.entry_url,
        "goal_id": input_data.execution.document_key,
        "goal_context": input_data.request.goal,
        "goal_trace": planned_goal_trace,
        "max_steps": input_data.request.max_pages,
        "mock_observations": input_data.mock_observations or {},
        "ledger_run": ledger_run,
        "ledger_actor": ledger_actor,
        "ledger_target": ledger_target,
        "allow_artifact_download": input_data.request.allow_artifact_download,
        "allow_artifact_open": input_data.request.allow_artifact_open,
        "execution_metadata": execution_metadata,
    }