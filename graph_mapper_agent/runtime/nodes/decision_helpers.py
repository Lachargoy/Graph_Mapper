from __future__ import annotations
#graph_mapper_agent/runtime/nodes/decision_helpers.py
from graph_mapper_agent.application.services.goals.models import (
    GoalTrace,
)


def decision_metadata_from_state(state: dict[str, object]) -> dict[str, object]:
    execution_metadata = state.get("execution_metadata")
    if not isinstance(execution_metadata, dict):
        return {}

    decision_metadata: dict[str, object] = {}
    prompt_version = execution_metadata.get("graph_mapper_prompt_version")
    if prompt_version not in (None, ""):
        decision_metadata["graph_mapper_prompt_version"] = str(prompt_version)

    return decision_metadata


def build_goal_trace_from_state(state: dict[str, object]) -> GoalTrace | None:
    raw_goal_trace = state.get("goal_trace")
    if isinstance(raw_goal_trace, GoalTrace):
        return raw_goal_trace
    return None


def sanitize_llm_text(value: object, *, max_len: int = 4000) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    cleaned = "".join(ch for ch in text if ch.isprintable() or ch in "\n\t")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n").strip()

    if not cleaned:
        return None

    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()

    return cleaned or None


__all__ = [
    "build_goal_trace_from_state",
    "decision_metadata_from_state",
    "sanitize_llm_text",
]
