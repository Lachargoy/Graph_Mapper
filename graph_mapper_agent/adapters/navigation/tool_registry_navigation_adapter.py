#graph_mapper_agent/adapters/navigation/tool_registry_navigation_adapter.py
from __future__ import annotations

from graph_mapper_agent.adapters.tools.tool_registry import (
    ToolRegistry,
)
from graph_mapper_agent.application.ports.navigation_actions import (
    DownloadArtifactRequest,
    InspectPageRequest,
    NavigationActionsPort,
    OpenArtifactRequest,
    SearchWithTextRequest,
)


class ToolRegistryNavigationAdapter(NavigationActionsPort):
    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tool_registry = tool_registry

    def inspect_page(self, request: InspectPageRequest) -> dict[str, object]:
        raw = self._tool_registry.invoke(
            "inspect_page",
            {
                "jurisdiction_code": request.jurisdiction_code,
                "document_key": request.document_key,
                "entry_url": request.entry_url,
                "timeout_seconds": request.timeout_seconds,
                "include_screenshot": request.include_screenshot,
                "metadata": dict(request.metadata),
            },
        )
        if not isinstance(raw, dict):
            raise TypeError("inspect_page(...) debe regresar dict[str, object]")
        return raw

    def search_with_text(self, request: SearchWithTextRequest) -> dict[str, object]:
        raw = self._tool_registry.invoke(
                "search_with_text",
                {
                    "jurisdiction_code": request.jurisdiction_code,
                    "document_key": request.document_key,
                    "entry_url": request.entry_url,
                    "search_target_id": request.search_target_id,
                    "query_text": request.query_text,
                    "timeout_seconds": request.timeout_seconds,
                    "include_screenshot": request.include_screenshot,
                    "metadata": {
                        "include_screenshot": request.include_screenshot,
                    },
                },
            )
        if not isinstance(raw, dict):
            raise TypeError("search_with_text(...) debe regresar dict[str, object]")
        return raw

    def download_artifact(self, request: DownloadArtifactRequest) -> dict[str, object]:
        raw = self._tool_registry.invoke(
            "download_candidate",
            {
                "jurisdiction_code": request.jurisdiction_code,
                "document_key": request.document_key,
                "candidate_url": request.candidate_url,
                "timeout_seconds": request.timeout_seconds,
            },
        )
        if not isinstance(raw, dict):
            raise TypeError("download_candidate(...) debe regresar dict[str, object]")
        return raw

    def open_artifact(self, request: OpenArtifactRequest) -> dict[str, object]:
        raw = self._tool_registry.invoke(
            "open_artifact",
            {
                "candidate_url": request.candidate_url,
                "original_path": request.original_path,
                "storage_ref": request.storage_ref,
            },
        )
        if not isinstance(raw, dict):
            raise TypeError("open_artifact(...) debe regresar dict[str, object]")
        return raw
