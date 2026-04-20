from __future__ import annotations
#graph_mapper_agent/runtime/state/validation_target.py
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .validation import document_validation_context_signature

if TYPE_CHECKING:
    from .models import GraphMapperState


@dataclass(slots=True, frozen=True)
class ValidationTargetRef:
    node_id: str
    source_kind: str
    page_url: str | None = None
    artifact_url: str | None = None
    local_path: str | None = None
    title: str | None = None
    content_signature: str | None = None


def optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_validation_target_for_node(
    *,
    runtime: GraphMapperState,
    node_id: str,
) -> ValidationTargetRef | None:
    artifact_result = runtime.artifact_result_by_node.get(node_id)
    download_result = runtime.download_result_by_node.get(node_id)
    inspection_result = runtime.inspection_result_by_node.get(node_id)

    if isinstance(artifact_result, dict):
        inline_text = optional_str(artifact_result.get("content"))
        artifact_url = None
        local_path = None
        title = None

        if isinstance(download_result, dict):
            artifact_url = optional_str(download_result.get("download_url")) or optional_str(
                download_result.get("candidate_url")
            )
            local_path = optional_str(download_result.get("original_path"))
            title = optional_str(download_result.get("filename"))

        artifact_kind = optional_str(artifact_result.get("artifact_kind"))
        if inline_text or local_path or artifact_kind:
            content_signature = "|".join(
                (
                    "artifact",
                    artifact_url or "",
                    local_path or "",
                    title or "",
                    artifact_kind or "",
                    str(len(inline_text or "")),
                )
            )
            return ValidationTargetRef(
                node_id=node_id,
                source_kind="artifact",
                artifact_url=artifact_url,
                local_path=local_path,
                title=title,
                content_signature=content_signature,
            )

    if isinstance(download_result, dict):
        local_path = optional_str(download_result.get("original_path"))
        artifact_url = optional_str(download_result.get("download_url")) or optional_str(
            download_result.get("candidate_url")
        )
        title = optional_str(download_result.get("filename"))
        if local_path:
            content_signature = "|".join(
                (
                    "download",
                    artifact_url or "",
                    local_path or "",
                    title or "",
                )
            )
            return ValidationTargetRef(
                node_id=node_id,
                source_kind="download",
                artifact_url=artifact_url,
                local_path=local_path,
                title=title,
                content_signature=content_signature,
            )

    if isinstance(inspection_result, dict):
        content = optional_str(inspection_result.get("content")) or optional_str(
            inspection_result.get("text_excerpt")
        )
        screenshot_base64 = optional_str(inspection_result.get("screenshot_base64"))
        page_url = optional_str(inspection_result.get("page_url")) or optional_str(
            inspection_result.get("url")
        )
        title = optional_str(inspection_result.get("title"))

        if content or screenshot_base64:
            content_signature = document_validation_context_signature(
                inspection_result=inspection_result,
                payload=None,
            )
            return ValidationTargetRef(
                node_id=node_id,
                source_kind="inspection",
                page_url=page_url,
                title=title,
                content_signature=content_signature,
            )

    return None


__all__ = [
    "ValidationTargetRef",
    "build_validation_target_for_node",
    "optional_str",
]
