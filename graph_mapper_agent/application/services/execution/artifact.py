from __future__ import annotations
#graph_mapper_agent/application/services/execution/artifact.py
from dataclasses import dataclass
from typing import TYPE_CHECKING

from graph_mapper_agent.application.goal_validation.artifact_models import (
    GoalValidationArtifact,
)
from graph_mapper_agent.application.local_perception.models import (
    LocalPerceptionRequest,
    LocalPerceptionResult,
    LocalPerceptionTargetRef,
)
from graph_mapper_agent.application.local_perception.service import (
    LocalPerceptionService,
)
from graph_mapper_agent.domain.graph import EdgeState
from graph_mapper_agent.application.ports.navigation_actions import (
    DownloadArtifactRequest,
)

from .validation_support import (
    build_artifact_validation_intent,
    candidate_count_from_inspection,
    inspection_looks_like_terminal_document,
)
from .normalization import optional_str

if TYPE_CHECKING:
    from graph_mapper_agent.application.contracts.runtime_views import (
        RuntimeExecutionPort,
    )


@dataclass(slots=True, frozen=True)
class ArtifactValidationContext:
    local_perception_service: LocalPerceptionService | None


def maybe_auto_persist_validated_artifact(
    *,
    context: object,
    edge: EdgeState,
    inspection_result: dict[str, object],
    local_perception_result: LocalPerceptionResult | None,
) -> dict[str, object] | None:
    if not getattr(context, "allow_artifact_download", True):
        return None
    if str(getattr(context, "artifact_persistence_mode", "on_validation") or "").strip().lower() != "on_validation":
        return None
    if not _is_positive_goal_validation(local_perception_result):
        return None
    if not _looks_like_direct_artifact(edge=edge, inspection_result=inspection_result):
        return None

    navigation_actions = getattr(context, "navigation_actions", None)
    jurisdiction_code = getattr(context, "jurisdiction_code", None)
    document_key = getattr(context, "document_key", None)
    timeout_seconds = getattr(context, "timeout_seconds", None)
    if navigation_actions is None or jurisdiction_code is None or document_key is None or timeout_seconds is None:
        return None

    return navigation_actions.download_artifact(
        DownloadArtifactRequest(
            jurisdiction_code=str(jurisdiction_code),
            document_key=str(document_key),
            candidate_url=edge.target_url,
            timeout_seconds=int(timeout_seconds),
        )
    )


def maybe_validate_opened_artifact(
    *,
    context: ArtifactValidationContext,
    runtime: RuntimeExecutionPort,
    edge: EdgeState,
    download_result: dict[str, object],
    artifact_result: dict[str, object],
) -> LocalPerceptionResult | None:
    if context.local_perception_service is None:
        return None
    local_path = optional_str(download_result.get("original_path"))
    if not bool(artifact_result.get("valid")):
        return None
    inline_text = optional_str(artifact_result.get("content"))
    artifact_kind = optional_str(artifact_result.get("artifact_kind")) or ""
    if not local_path and not inline_text:
        return None
    if artifact_kind == "non_pdf_file" and not inline_text:
        return None

    artifact = GoalValidationArtifact(
        local_path=local_path,
        source_url=optional_str(download_result.get("download_url")) or edge.target_url,
        media_type=optional_str(download_result.get("content_type")),
        filename=optional_str(download_result.get("filename")),
        inline_text=inline_text,
    )
    question, pattern_hints, goal_conditions = build_artifact_validation_intent(
        runtime, edge
    )
    return context.local_perception_service.perceive(
        LocalPerceptionRequest(
            target_kind="artifact_document",
            question=question,
            target_ref=LocalPerceptionTargetRef(artifact=artifact),
            goal_conditions=goal_conditions,
            pattern_hints=pattern_hints,
            max_pages=3,
            page_budget=3,
            escalation_allowed=True,
            metadata={
                "source_action": "open_artifact",
                "edge_id": edge.edge_id,
                "edge_label": edge.label,
                "candidate_url": edge.target_url,
                "validation_entry_kind": "opened_artifact",
            },
        )
    )


def maybe_validate_downloaded_artifact(
    *,
    context: ArtifactValidationContext,
    runtime: RuntimeExecutionPort,
    edge: EdgeState,
    download_result: dict[str, object],
) -> LocalPerceptionResult | None:
    if context.local_perception_service is None:
        return None
    local_path = optional_str(download_result.get("original_path"))
    if not local_path:
        return None

    artifact = GoalValidationArtifact(
        local_path=local_path,
        source_url=optional_str(download_result.get("download_url")) or edge.target_url,
        media_type=optional_str(download_result.get("content_type")),
        filename=optional_str(download_result.get("filename")),
        inline_text=None,
    )
    question, pattern_hints, goal_conditions = build_artifact_validation_intent(
        runtime, edge
    )
    return context.local_perception_service.perceive(
        LocalPerceptionRequest(
            target_kind="artifact_document",
            question=question,
            target_ref=LocalPerceptionTargetRef(artifact=artifact),
            goal_conditions=goal_conditions,
            pattern_hints=pattern_hints,
            max_pages=2,
            page_budget=2,
            escalation_allowed=True,
            metadata={
                "source_action": "download_artifact",
                "edge_id": edge.edge_id,
                "edge_label": edge.label,
                "candidate_url": edge.target_url,
                "validation_entry_kind": "downloaded_artifact",
            },
        )
    )


def maybe_validate_inspected_content(
    *,
    context: ArtifactValidationContext,
    runtime: RuntimeExecutionPort,
    edge: EdgeState,
    inspection_result: dict[str, object],
) -> LocalPerceptionResult | None:
    if context.local_perception_service is None:
        return None
    content = optional_str(inspection_result.get("content")) or optional_str(
        inspection_result.get("text_excerpt")
    )
    screenshot_base64 = optional_str(inspection_result.get("screenshot_base64"))
    screenshot_mime_type = optional_str(inspection_result.get("screenshot_mime_type"))
    if not content and not screenshot_base64:
        return None
    if not inspection_looks_like_terminal_document(inspection_result):
        return None
    metadata = inspection_result.get("metadata")
    metadata_dict = metadata if isinstance(metadata, dict) else {}
    candidate_count = candidate_count_from_inspection(inspection_result)

    artifact = GoalValidationArtifact(
        local_path=None,
        source_url=optional_str(inspection_result.get("page_url")) or edge.target_url,
        filename=optional_str(inspection_result.get("title")) or edge.label or None,
        inline_text=content,
        screenshot_base64=screenshot_base64,
        screenshot_mime_type=screenshot_mime_type,
    )
    question, pattern_hints, goal_conditions = build_artifact_validation_intent(
        runtime, edge
    )
    return context.local_perception_service.perceive(
        LocalPerceptionRequest(
            target_kind="inline_document_content",
            question=question,
            target_ref=LocalPerceptionTargetRef(artifact=artifact),
            goal_conditions=goal_conditions,
            pattern_hints=pattern_hints,
            max_pages=1,
            page_budget=1,
            escalation_allowed=False,
            metadata={
                "source_action": "follow_edge",
                "edge_id": edge.edge_id,
                "edge_label": edge.label,
                "candidate_url": edge.target_url,
                "current_page_url": optional_str(inspection_result.get("page_url"))
                or edge.target_url,
                "current_page_title": optional_str(inspection_result.get("title"))
                or edge.label,
                "candidate_count": candidate_count,
                "navigation_frame_detected": metadata_dict.get(
                    "navigation_frame_detected"
                ),
                "content_frame_detected": metadata_dict.get("content_frame_detected"),
                "validation_loose_gate": True,
            },
        )
    )


def _is_positive_goal_validation(
    local_perception_result: LocalPerceptionResult | None,
) -> bool:
    if local_perception_result is None:
        return False
    payload = local_perception_result.payload
    final_result = getattr(payload, "final_result", None)
    status = getattr(final_result, "status", None)
    return str(status or "").strip() == "validated"


def _looks_like_direct_artifact(
    *,
    edge: EdgeState,
    inspection_result: dict[str, object],
) -> bool:
    target_url = str(edge.target_url or "").strip().lower()
    final_url = optional_str(inspection_result.get("final_url")) or optional_str(
        inspection_result.get("page_url")
    )
    final_url = str(final_url or "").strip().lower()
    if target_url.endswith(".pdf") or final_url.endswith(".pdf"):
        return True

    delivery_mode = str(edge.delivery_mode or "").strip().lower()
    resource_kind = str(edge.resource_kind or "").strip().lower()
    if delivery_mode == "direct":
        return True
    if resource_kind in {"pdf", "artifact", "document", "file"}:
        return True

    metadata = inspection_result.get("metadata")
    metadata_dict = metadata if isinstance(metadata, dict) else {}
    return bool(metadata_dict.get("is_download_intercepted"))
