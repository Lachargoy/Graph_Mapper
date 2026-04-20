from __future__ import annotations
#graph_mapper_agent/application/services/execution/validation.py
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

from graph_mapper_agent.application.ports.navigation_actions import (
    InspectPageRequest,
    NavigationActionsPort,
)
from graph_mapper_agent.domain.graph import EdgeState

from .artifact import (
    ArtifactValidationContext,
    maybe_validate_downloaded_artifact,
    maybe_validate_opened_artifact,
)
from .contracts import ActionExecutionResult
from .normalization import optional_str
from .result_builders import local_perception_payload
from .validation_support import (
    build_artifact_validation_intent,
    candidate_count_from_inspection,
)

if TYPE_CHECKING:
    from graph_mapper_agent.application.contracts.runtime_views import (
        RuntimeExecutionPort,
    )


@dataclass(slots=True, frozen=True)
class ValidationExecutionContext:
    navigation_actions: NavigationActionsPort
    jurisdiction_code: str
    document_key: str
    timeout_seconds: int
    local_perception_service: LocalPerceptionService | None = None

    @property
    def artifact_validation(self) -> ArtifactValidationContext:
        return ArtifactValidationContext(
            local_perception_service=self.local_perception_service
        )


def validate_current_content(
    *,
    context: ValidationExecutionContext,
    runtime: RuntimeExecutionPort,
    decision: dict[str, object],
) -> ActionExecutionResult:
    if context.local_perception_service is None:
        raise RuntimeError("validate_current_content requiere local_perception_service")

    validation_target = decision.get("validation_target")
    if validation_target is None:
        return ActionExecutionResult(
            action="validate_current_content",
            status="ok",
            reason="missing_validation_target_ref",
        )

    target_node_id = optional_str(getattr(validation_target, "node_id", None))
    source_kind = optional_str(getattr(validation_target, "source_kind", None))

    if not target_node_id or not source_kind:
        return ActionExecutionResult(
            action="validate_current_content",
            status="ok",
            reason="invalid_validation_target_ref",
        )

    node = runtime.graph.get_node(target_node_id)
    if node is None:
        return ActionExecutionResult(
            action="validate_current_content",
            status="ok",
            reason="validation_target_node_missing",
        )

    if source_kind == "inspection":
        inspection_result = runtime.inspection_result_by_node.get(target_node_id)
        if isinstance(inspection_result, dict):
            inspection_result = ensure_validation_observation_with_screenshot(
                context=context,
                runtime=runtime,
                target_node_id=target_node_id,
                node_url=optional_str(getattr(validation_target, "page_url", None))
                or node.canonical_url,
                inspection_result=inspection_result,
            )
            local_perception_result = maybe_validate_current_node_inspection(
                context=context,
                runtime=runtime,
                node=node,
                inspection_result=inspection_result,
            )
            if local_perception_result is not None:
                enriched_inspection = dict(inspection_result)
                enriched_inspection["local_perception"] = local_perception_payload(
                    local_perception_result
                )
                return ActionExecutionResult(
                    action="validate_current_content",
                    status="ok",
                    inspection_result=enriched_inspection,
                    local_perception_result=local_perception_result,
                    reason="validated_frozen_node_inspection",
                )

        return ActionExecutionResult(
            action="validate_current_content",
            status="ok",
            reason="frozen_inspection_target_not_available",
        )

    if source_kind == "artifact":
        artifact_result = runtime.artifact_result_by_node.get(target_node_id)
        download_result = runtime.download_result_by_node.get(target_node_id) or {}

        if isinstance(artifact_result, dict) and bool(artifact_result.get("valid")):
            local_perception_result = maybe_validate_current_artifact_result(
                context=context,
                runtime=runtime,
                node=node,
                artifact_result=artifact_result,
                download_result=download_result if isinstance(download_result, dict) else {},
            )
            if local_perception_result is not None:
                enriched_artifact = dict(artifact_result)
                enriched_artifact["local_perception"] = local_perception_payload(
                    local_perception_result
                )
                return ActionExecutionResult(
                    action="validate_current_content",
                    status="ok",
                    download_result=download_result
                    if isinstance(download_result, dict)
                    else None,
                    artifact_result=enriched_artifact,
                    local_perception_result=local_perception_result,
                    reason="validated_frozen_open_artifact",
                )

        return ActionExecutionResult(
            action="validate_current_content",
            status="ok",
            reason="frozen_artifact_target_not_available",
        )

    if source_kind == "download":
        download_result = runtime.download_result_by_node.get(target_node_id)
        if isinstance(download_result, dict):
            local_perception_result = maybe_validate_current_download(
                context=context,
                runtime=runtime,
                node=node,
                download_result=download_result,
            )
            if local_perception_result is not None:
                enriched_download = dict(download_result)
                enriched_download["local_perception"] = local_perception_payload(
                    local_perception_result
                )
                return ActionExecutionResult(
                    action="validate_current_content",
                    status="ok",
                    download_result=enriched_download,
                    local_perception_result=local_perception_result,
                    reason="validated_frozen_downloaded_artifact",
                )

        return ActionExecutionResult(
            action="validate_current_content",
            status="ok",
            reason="frozen_download_target_not_available",
        )

    return ActionExecutionResult(
        action="validate_current_content",
        status="ok",
        reason=f"unsupported_validation_target_source_kind:{source_kind}",
    )


def ensure_validation_observation_with_screenshot(
    *,
    context: ValidationExecutionContext,
    runtime: RuntimeExecutionPort,
    target_node_id: str,
    node_url: str,
    inspection_result: dict[str, object],
) -> dict[str, object]:
    if runtime.has_frozen_dom_snapshot(target_node_id):
        print(
            f"[executor._ensure_validation_observation_with_screenshot] "
            f"skip live inspect_page for frozen snapshot node {target_node_id!r}",
            flush=True,
        )
        return inspection_result

    if inspection_result.get("screenshot_base64"):
        return inspection_result

    raw = context.navigation_actions.inspect_page(
        InspectPageRequest(
            jurisdiction_code=context.jurisdiction_code,
            document_key=context.document_key,
            entry_url=node_url,
            timeout_seconds=context.timeout_seconds,
            include_screenshot=True,
            metadata={"include_screenshot": True},
        )
    )

    merged = dict(inspection_result)
    for key in (
        "content",
        "text_excerpt",
        "title",
        "page_url",
        "final_url",
        "screenshot_base64",
        "screenshot_mime_type",
        "metadata",
        "inspection_metadata",
        "candidates",
    ):
        if raw.get(key) is not None:
            merged[key] = raw.get(key)
    return merged


def maybe_validate_current_node_inspection(
    *,
    context: ValidationExecutionContext,
    runtime: RuntimeExecutionPort,
    node: object,
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
    candidate_count = candidate_count_from_inspection(inspection_result)
    metadata = inspection_result.get("metadata")
    metadata_dict = metadata if isinstance(metadata, dict) else {}
    artifact = GoalValidationArtifact(
        local_path=None,
        source_url=optional_str(inspection_result.get("page_url"))
        or getattr(node, "canonical_url", ""),
        filename=optional_str(inspection_result.get("title"))
        or getattr(node, "title", None)
        or "current_node",
        inline_text=content,
        screenshot_base64=screenshot_base64,
        screenshot_mime_type=screenshot_mime_type,
    )
    synthetic_edge = EdgeState(
        edge_id=f"validate_current_{getattr(node, 'node_id', 'node')}",
        from_node_id=getattr(node, "node_id", "node"),
        target_url=optional_str(inspection_result.get("page_url"))
        or getattr(node, "canonical_url", ""),
        label=optional_str(inspection_result.get("title"))
        or getattr(node, "title", None)
        or "current_node",
    )
    question, pattern_hints, goal_conditions = build_artifact_validation_intent(
        runtime, synthetic_edge
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
                "source_action": "validate_current_content",
                "validation_entry_kind": "current_node_inspection",
                "current_page_url": optional_str(inspection_result.get("page_url"))
                or getattr(node, "canonical_url", ""),
                "current_page_title": optional_str(inspection_result.get("title"))
                or getattr(node, "title", None),
                "current_page_type": getattr(
                    getattr(node, "page_type", None),
                    "value",
                    getattr(node, "page_type", None),
                ),
                "candidate_count": candidate_count,
                "navigation_frame_detected": metadata_dict.get(
                    "navigation_frame_detected"
                ),
                "content_frame_detected": metadata_dict.get("content_frame_detected"),
                "validation_loose_gate": True,
            },
        )
    )


def maybe_validate_current_artifact_result(
    *,
    context: ValidationExecutionContext,
    runtime: RuntimeExecutionPort,
    node: object,
    artifact_result: dict[str, object],
    download_result: dict[str, object],
) -> LocalPerceptionResult | None:
    synthetic_edge = EdgeState(
        edge_id=f"validate_current_{getattr(node, 'node_id', 'node')}",
        from_node_id=getattr(node, "node_id", "node"),
        target_url=optional_str(download_result.get("download_url"))
        or getattr(node, "canonical_url", ""),
        label=optional_str(download_result.get("filename"))
        or getattr(node, "title", None)
        or "current_artifact",
    )
    return maybe_validate_opened_artifact(
        context=context.artifact_validation,
        runtime=runtime,
        edge=synthetic_edge,
        download_result=download_result,
        artifact_result=artifact_result,
    )


def maybe_validate_current_download(
    *,
    context: ValidationExecutionContext,
    runtime: RuntimeExecutionPort,
    node: object,
    download_result: dict[str, object],
) -> LocalPerceptionResult | None:
    synthetic_edge = EdgeState(
        edge_id=f"validate_current_{getattr(node, 'node_id', 'node')}",
        from_node_id=getattr(node, "node_id", "node"),
        target_url=optional_str(download_result.get("download_url"))
        or getattr(node, "canonical_url", ""),
        label=optional_str(download_result.get("filename"))
        or getattr(node, "title", None)
        or "current_download",
    )
    return maybe_validate_downloaded_artifact(
        context=context.artifact_validation,
        runtime=runtime,
        edge=synthetic_edge,
        download_result=download_result,
    )
