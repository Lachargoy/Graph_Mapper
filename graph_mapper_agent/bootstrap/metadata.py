from __future__ import annotations
#graph_mapper_agent/bootstrap/metadata.py
from typing import Any

from graph_mapper_agent.adapters.tools.tool_registry import (
    ToolRegistry,
)
from graph_mapper_agent.application.services.goals.planner import (
    GoalPlannerResult,
)
from graph_mapper_agent.platform.llm.config import (
    LlmRuntimeConfig,
)
from .config import GraphMapperConfig
from .execution_config import GuidedGraphMapperConfig


def build_execution_metadata(
    *,
    execution: GuidedGraphMapperConfig,
    request: GraphMapperConfig,
    registry: ToolRegistry,
    llm_runtime_source: LlmRuntimeConfig | None,
    navigation_perception_llm_runtime_source: LlmRuntimeConfig | None,
    goal_validation_llm_runtime_source: LlmRuntimeConfig | None,
    evidence_extraction_visual_llm_runtime_source: LlmRuntimeConfig | None,
    evidence_extraction_ocr_llm_runtime_source: LlmRuntimeConfig | None,
    planned_goal_result: GoalPlannerResult | None,
) -> dict[str, Any]:
    execution_metadata = dict(execution.execution_metadata or {})
    execution_metadata["jurisdiction_id"] = execution.jurisdiction_code
    execution_metadata["registered_tools"] = list(registry.list_tools())
    execution_metadata["decision_mode"] = request.decision_mode

    if llm_runtime_source is not None:
        execution_metadata["llm_runtime_source"] = {
            "backend": llm_runtime_source.backend,
            "default_model": llm_runtime_source.default_model,
            "base_url": llm_runtime_source.base_url,
            "supports_vision": llm_runtime_source.supports_vision,
            "structured_output_mode": llm_runtime_source.structured_output_mode,
        }

    if navigation_perception_llm_runtime_source is not None:
        execution_metadata["navigation_perception_llm_runtime_source"] = {
            "backend": navigation_perception_llm_runtime_source.backend,
            "default_model": navigation_perception_llm_runtime_source.default_model,
            "base_url": navigation_perception_llm_runtime_source.base_url,
            "supports_vision": navigation_perception_llm_runtime_source.supports_vision,
            "structured_output_mode": navigation_perception_llm_runtime_source.structured_output_mode,
            "separate_from_graph_mapper": (
                navigation_perception_llm_runtime_source is not llm_runtime_source
            ),
        }

    if goal_validation_llm_runtime_source is not None:
        execution_metadata["goal_validation_llm_runtime_source"] = {
            "backend": goal_validation_llm_runtime_source.backend,
            "default_model": goal_validation_llm_runtime_source.default_model,
            "base_url": goal_validation_llm_runtime_source.base_url,
            "supports_vision": goal_validation_llm_runtime_source.supports_vision,
            "structured_output_mode": goal_validation_llm_runtime_source.structured_output_mode,
            "separate_from_graph_mapper": (
                goal_validation_llm_runtime_source is not llm_runtime_source
            ),
        }

    if evidence_extraction_visual_llm_runtime_source is not None:
        execution_metadata["evidence_extraction_visual_llm_runtime_source"] = {
            "backend": evidence_extraction_visual_llm_runtime_source.backend,
            "default_model": evidence_extraction_visual_llm_runtime_source.default_model,
            "base_url": evidence_extraction_visual_llm_runtime_source.base_url,
            "supports_vision": evidence_extraction_visual_llm_runtime_source.supports_vision,
            "structured_output_mode": evidence_extraction_visual_llm_runtime_source.structured_output_mode,
            "separate_from_graph_mapper": (
                evidence_extraction_visual_llm_runtime_source is not llm_runtime_source
            ),
        }

    if evidence_extraction_ocr_llm_runtime_source is not None:
        execution_metadata["evidence_extraction_ocr_llm_runtime_source"] = {
            "backend": evidence_extraction_ocr_llm_runtime_source.backend,
            "default_model": evidence_extraction_ocr_llm_runtime_source.default_model,
            "base_url": evidence_extraction_ocr_llm_runtime_source.base_url,
            "supports_vision": evidence_extraction_ocr_llm_runtime_source.supports_vision,
            "structured_output_mode": evidence_extraction_ocr_llm_runtime_source.structured_output_mode,
            "separate_from_graph_mapper": (
                evidence_extraction_ocr_llm_runtime_source is not llm_runtime_source
            ),
        }

    planned_goal_trace = (
        planned_goal_result.goal_trace if planned_goal_result is not None else None
    )
    if planned_goal_trace is not None:
        active_proposal = planned_goal_trace.active_proposal()
        execution_metadata["planned_goal_trace"] = {
            "intent": planned_goal_trace.intent.normalized_goal,
            "active_proposal_id": planned_goal_trace.active_proposal_id,
            "proposal_count": len(planned_goal_trace.proposals),
            "active_conditions": (
                0 if active_proposal is None else len(active_proposal.conditions)
            ),
        }

    return execution_metadata
