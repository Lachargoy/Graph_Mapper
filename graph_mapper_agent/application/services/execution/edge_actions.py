from __future__ import annotations
#graph_mapper_agent/application/services/execution/edge_actions.py
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit, urlunsplit

from graph_mapper_agent.application.local_perception.service import (
    LocalPerceptionService,
)
from graph_mapper_agent.application.ports.navigation_actions import (
    DownloadArtifactRequest,
    InspectPageRequest,
    NavigationActionsPort,
    OpenArtifactRequest,
    ProbeContentRequest,
)
from graph_mapper_agent.domain.graph import EdgeState

from .artifact import (
    ArtifactValidationContext,
    maybe_auto_persist_validated_artifact,
    maybe_validate_downloaded_artifact,
    maybe_validate_inspected_content,
    maybe_validate_opened_artifact,
)
from .contracts import ActionExecutionResult
from .normalization import optional_str
from .result_builders import local_perception_payload

if TYPE_CHECKING:
    from graph_mapper_agent.application.contracts.runtime_views import (
        RuntimeExecutionPort,
    )


@dataclass(slots=True, frozen=True)
class ExecutionContext:
    navigation_actions: NavigationActionsPort
    jurisdiction_code: str
    document_key: str
    timeout_seconds: int
    storage_namespace: str = "graph_mapper_agent"
    session_id: str | None = None
    run_id: str | None = None
    capture_screenshot_for_observations: bool = False
    local_perception_service: LocalPerceptionService | None = None
    allow_artifact_download: bool = True
    artifact_persistence_mode: str = "on_validation"

    @property
    def artifact_validation(self) -> ArtifactValidationContext:
        return ArtifactValidationContext(
            local_perception_service=self.local_perception_service
        )


def _normalize_candidate_url(url: str | None) -> str:
    candidate = optional_str(url) or ""
    if not candidate:
        return ""
    if not any(ch.isspace() for ch in candidate):
        return candidate

    parts = urlsplit(candidate)
    normalized_path = quote(parts.path, safe="/%")
    normalized_query = quote(parts.query, safe="=&%")
    normalized_fragment = quote(parts.fragment, safe="%")

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            normalized_path,
            normalized_query,
            normalized_fragment,
        )
    )


def _resolve_target_url(
    *,
    edge: EdgeState,
    override_url: str | None = None,
) -> str:
    raw = optional_str(override_url) or optional_str(edge.target_url) or ""
    return _normalize_candidate_url(raw)


def _urls_match(left: str | None, right: str | None) -> bool:
    left_norm = _normalize_candidate_url(left)
    right_norm = _normalize_candidate_url(right)
    return bool(left_norm and right_norm and left_norm == right_norm)


def inspect_edge(
    *,
    context: ExecutionContext,
    runtime: RuntimeExecutionPort,
    edge: EdgeState,
    override_url: str | None = None,
) -> ActionExecutionResult:
    target_url = _resolve_target_url(edge=edge, override_url=override_url)
    if not target_url:
        return ActionExecutionResult(
            action="follow_edge",
            status="failed",
            edge_id=edge.edge_id,
            reason="missing_target_url",
        )

    print(f"[executor._inspect] target_url={target_url}", flush=True)

    raw = None
    existing_node = runtime.graph.get_node_by_url(target_url)
    if existing_node is None and target_url != edge.target_url:
        existing_node = runtime.graph.get_node_by_url(edge.target_url)

    if existing_node:
        snapshot = runtime.resolve_node_observation_snapshot(existing_node.node_id)
        if snapshot:
            print(
                f"[executor._inspect] using existing snapshot for node_id={existing_node.node_id!r} "
                f"url={target_url!r}",
                flush=True,
            )
            raw = dict(snapshot)

    if raw is None:
        raw = context.navigation_actions.inspect_page(
            InspectPageRequest(
                jurisdiction_code=context.jurisdiction_code,
                document_key=context.document_key,
                entry_url=target_url,
                timeout_seconds=context.timeout_seconds,
                include_screenshot=context.capture_screenshot_for_observations,
                metadata={
                    "include_screenshot": context.capture_screenshot_for_observations,
                },
            )
        )

    print(f"[executor._inspect] raw_type={type(raw).__name__}", flush=True)
    print(
        f"[executor._inspect] final_url={raw.get('final_url')} page_url={raw.get('page_url')}",
        flush=True,
    )
    print(
        f"[executor._inspect] candidates_count={len(list(raw.get('candidates') or []))}",
        flush=True,
    )

    local_perception_result = maybe_validate_inspected_content(
        context=context.artifact_validation,
        runtime=runtime,
        edge=edge,
        inspection_result=raw,
    )
    if local_perception_result is not None:
        raw = dict(raw)
        raw["local_perception"] = local_perception_payload(local_perception_result)

    auto_download_result = maybe_auto_persist_validated_artifact(
        context=context,
        edge=edge,
        inspection_result=raw,
        local_perception_result=local_perception_result,
    )
    if auto_download_result is not None:
        raw = dict(raw)
        metadata = raw.get("metadata")
        metadata_dict = dict(metadata) if isinstance(metadata, dict) else {}
        metadata_dict["validated_auto_download"] = True
        raw["metadata"] = metadata_dict

    return ActionExecutionResult(
        action="follow_edge",
        status="ok",
        edge_id=edge.edge_id,
        inspection_result=raw,
        download_result=auto_download_result,
        local_perception_result=local_perception_result,
        reason="inspected_target_url",
    )


def download_artifact_for_edge(
    *,
    context: ExecutionContext,
    runtime: RuntimeExecutionPort,
    edge: EdgeState,
    override_url: str | None = None,
) -> ActionExecutionResult:
    target_url = _resolve_target_url(edge=edge, override_url=override_url)
    if not target_url:
        return ActionExecutionResult(
            action="download_artifact",
            status="failed",
            edge_id=edge.edge_id,
            reason="missing_target_url",
        )

    print(f"[executor._download] target_url={target_url}", flush=True)
    print(
        f"[executor._download] jurisdiction_code={context.jurisdiction_code} "
        f"document_key={context.document_key} timeout_seconds={context.timeout_seconds}",
        flush=True,
    )

    try:
        raw = context.navigation_actions.download_artifact(
            DownloadArtifactRequest(
                jurisdiction_code=context.jurisdiction_code,
                document_key=context.document_key,
                candidate_url=target_url,
                timeout_seconds=context.timeout_seconds,
                storage_namespace=context.storage_namespace,
                session_id=context.session_id,
                run_id=context.run_id,
            )
        )
    except HTTPError as exc:
        return _build_http_failure_result(
            action="download_artifact",
            edge=edge,
            exc=exc,
            target_url=target_url,
        )

    print(f"[executor._download] raw_type={type(raw).__name__}", flush=True)
    print(
        f"[executor._download] download_url={raw.get('download_url')} "
        f"final_url={raw.get('final_url')} filename={raw.get('filename')} "
        f"original_path={raw.get('original_path')}",
        flush=True,
    )

    local_perception_result = maybe_validate_downloaded_artifact(
        context=context.artifact_validation,
        runtime=runtime,
        edge=edge,
        download_result=raw,
    )
    if local_perception_result is not None:
        raw = dict(raw)
        raw["local_perception"] = local_perception_payload(local_perception_result)

    return ActionExecutionResult(
        action="download_artifact",
        status="ok",
        edge_id=edge.edge_id,
        download_result=raw,
        local_perception_result=local_perception_result,
        reason="artifact_downloaded",
    )


def open_artifact_for_edge(
    *,
    context: ExecutionContext,
    runtime: RuntimeExecutionPort,
    edge: EdgeState,
) -> ActionExecutionResult:
    target_url = _resolve_target_url(edge=edge)
    if not target_url:
        return ActionExecutionResult(
            action="open_artifact",
            status="failed",
            edge_id=edge.edge_id,
            reason="missing_target_url",
        )

    print(f"[executor._open] edge.target_url={target_url}", flush=True)

    latest_download = runtime.last_download_result

    print(
        f"[executor._open] has_last_download={bool(latest_download)}",
        flush=True,
    )

    download_matches_edge = False
    if isinstance(latest_download, dict):
        last_url = optional_str(latest_download.get("download_url"))
        last_final_url = optional_str(latest_download.get("final_url"))
        last_path = optional_str(latest_download.get("original_path"))

        print(f"[executor._open] last_download_url={last_url}", flush=True)
        print(f"[executor._open] last_final_url={last_final_url}", flush=True)
        print(f"[executor._open] last_original_path={last_path}", flush=True)

        if last_path and (
            _urls_match(last_url, target_url) or _urls_match(last_final_url, target_url)
        ):
            download_matches_edge = True

    if not download_matches_edge:
        print(
            "[executor._open] last_download_result no coincide con el edge actual. "
            "Se descargará de nuevo.",
            flush=True,
        )
        try:
            latest_download = context.navigation_actions.download_artifact(
                DownloadArtifactRequest(
                    jurisdiction_code=context.jurisdiction_code,
                    document_key=context.document_key,
                    candidate_url=target_url,
                    timeout_seconds=context.timeout_seconds,
                    storage_namespace=context.storage_namespace,
                    session_id=context.session_id,
                    run_id=context.run_id,
                )
            )
        except HTTPError as exc:
            return _build_http_failure_result(
                action="open_artifact",
                edge=edge,
                exc=exc,
                target_url=target_url,
            )

    candidate_url = (
        optional_str(latest_download.get("download_url"))
        or optional_str(latest_download.get("final_url"))
        or target_url
    )
    original_path = optional_str(latest_download.get("original_path"))

    print(f"[executor._open] candidate_url={candidate_url}", flush=True)
    print(f"[executor._open] original_path={original_path}", flush=True)

    artifact_raw = context.navigation_actions.open_artifact(
        OpenArtifactRequest(
            candidate_url=candidate_url,
            original_path=original_path,
            storage_ref=original_path,
        )
    )

    print(f"[executor._open] artifact_raw_type={type(artifact_raw).__name__}", flush=True)

    local_perception_result = maybe_validate_opened_artifact(
        context=context.artifact_validation,
        runtime=runtime,
        edge=edge,
        download_result=latest_download,
        artifact_result=artifact_raw,
    )
    if local_perception_result is not None:
        artifact_raw = dict(artifact_raw)
        artifact_raw["local_perception"] = local_perception_payload(
            local_perception_result
        )

    print(
        f"[executor._open] artifact_valid={artifact_raw.get('valid')} "
        f"artifact_kind={artifact_raw.get('artifact_kind')}",
        flush=True,
    )

    return ActionExecutionResult(
        action="open_artifact",
        status="ok",
        edge_id=edge.edge_id,
        download_result=latest_download,
        artifact_result=artifact_raw,
        local_perception_result=local_perception_result,
        reason="artifact_opened",
    )


def _build_http_failure_result(
    *,
    action: str,
    edge: EdgeState,
    exc: HTTPError,
    target_url: str,
) -> ActionExecutionResult:
    return ActionExecutionResult(
        action=action,
        status="failed",
        edge_id=edge.edge_id,
        download_result={
            "download_url": target_url,
            "final_url": getattr(exc, "url", None) or target_url,
            "http_status": exc.code,
            "error": str(exc),
        },
        reason=f"http_error_{exc.code}",
    )


def follow_edge_with_probe(
    *,
    context: ExecutionContext,
    runtime: RuntimeExecutionPort,
    edge: EdgeState,
) -> ActionExecutionResult:
    target_url = _resolve_target_url(edge=edge)
    if not target_url:
        return ActionExecutionResult(
            action="follow_edge",
            status="failed",
            edge_id=edge.edge_id,
            reason="missing_target_url",
        )

    print(f"[executor._follow_probe] target_url={target_url}", flush=True)

    probe = context.navigation_actions.probe_content(
        ProbeContentRequest(
            jurisdiction_code=context.jurisdiction_code,
            document_key=context.document_key,
            url=target_url,
            timeout_seconds=context.timeout_seconds,
            metadata={
                "edge_id": edge.edge_id,
            },
        )
    )

    resource_kind = str(probe.get("resource_kind") or "").strip().lower()
    content_type = str(probe.get("content_type") or "").strip().lower()
    final_url = _normalize_candidate_url(str(probe.get("final_url") or "").strip())

    print(
        "[executor._follow_probe] "
        f"resource_kind={resource_kind!r} "
        f"content_type={content_type!r} "
        f"final_url={final_url!r}",
        flush=True,
    )

    if resource_kind == "pdf":
        if not context.allow_artifact_download:
            return ActionExecutionResult(
                action="follow_edge",
                status="blocked",
                edge_id=edge.edge_id,
                reason="pdf_detected_but_download_disabled",
            )

        result = download_artifact_for_edge(
            context=context,
            runtime=runtime,
            edge=edge,
            override_url=final_url or target_url,
        )
        return replace(
            result,
            action="follow_edge",
            reason="follow_edge_resolved_to_pdf_download",
        )

    if resource_kind == "html":
        result = inspect_edge(
            context=context,
            runtime=runtime,
            edge=edge,
            override_url=final_url or target_url,
        )
        return replace(
            result,
            action="follow_edge",
            reason="follow_edge_resolved_to_html_inspection",
        )

    return ActionExecutionResult(
        action="follow_edge",
        status="uncertain",
        edge_id=edge.edge_id,
        reason="content_probe_ambiguous",
        inspection_result={
            "entry_url": target_url,
            "final_url": final_url or target_url,
            "title": "Ambiguous resource",
            "content": "",
            "text_excerpt": "",
            "candidates": [],
            "search_targets": [],
            "metadata": {
                "content_probe": probe,
            },
            "page_title": "Ambiguous resource",
            "page_url": final_url or target_url,
        },
    )