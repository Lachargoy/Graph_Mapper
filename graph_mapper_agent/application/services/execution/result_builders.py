from __future__ import annotations

from graph_mapper_agent.application.document_validation.use_cases.progressive_validate_artifact import (
    ProgressiveValidateArtifactResult,
)
from graph_mapper_agent.application.local_perception.models import (
    LocalPerceptionResult,
)


def local_perception_payload(
    local_perception_result: LocalPerceptionResult,
) -> dict[str, object]:
    payload = {
        "target_kind": local_perception_result.target_kind,
        "status": local_perception_result.status,
        "confidence": local_perception_result.confidence,
        "summary": local_perception_result.summary,
        "recommended_next_step": local_perception_result.recommended_next_step,
        "metadata": dict(local_perception_result.metadata),
    }
    validation_payload = _goal_validation_payload(local_perception_result.payload)
    if validation_payload is not None:
        payload["goal_validation"] = validation_payload
    return payload


def _goal_validation_payload(payload: object) -> dict[str, object] | None:
    if not isinstance(payload, ProgressiveValidateArtifactResult):
        return None

    final_result = payload.final_result
    history_items = []
    for item in payload.history:
        history_items.append(
            {
                "status": item.status,
                "rationale": item.rationale,
                "evidence_summary": item.evidence_summary,
                "pages_consumed": item.pages_consumed,
                "recommended_next_strategy": item.recommended_next_strategy,
                "validation_pass": {
                    "level": item.validation_pass.level,
                    "strategy": item.validation_pass.strategy,
                    "reason": item.validation_pass.reason,
                    "page_numbers": list(item.validation_pass.page_numbers),
                    "pattern_hints": list(item.validation_pass.pattern_hints),
                },
                "metadata": dict(item.metadata),
            }
        )

    return {
        "final_result": {
            "status": final_result.status,
            "rationale": final_result.rationale,
            "evidence_summary": final_result.evidence_summary,
            "pages_consumed": final_result.pages_consumed,
            "recommended_next_strategy": final_result.recommended_next_strategy,
            "validation_pass": {
                "level": final_result.validation_pass.level,
                "strategy": final_result.validation_pass.strategy,
                "reason": final_result.validation_pass.reason,
                "page_numbers": list(final_result.validation_pass.page_numbers),
                "pattern_hints": list(final_result.validation_pass.pattern_hints),
            },
            "metadata": dict(final_result.metadata),
        },
        "history": history_items,
    }
