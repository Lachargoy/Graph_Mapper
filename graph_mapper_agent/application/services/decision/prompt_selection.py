from __future__ import annotations

from graph_mapper_agent.application.services.decision.prompts import (
    build_decision_prompt,
    build_decision_prompt_v2,
)


def select_prompt_builder(metadata: dict[str, object]):
    variant = str(metadata.get("graph_mapper_prompt_version") or "v1").strip().lower()
    if variant == "v2":
        return build_decision_prompt_v2, "graph_mapper_v4_compact"
    return build_decision_prompt, "graph_mapper_v3"


__all__ = ["select_prompt_builder"]
