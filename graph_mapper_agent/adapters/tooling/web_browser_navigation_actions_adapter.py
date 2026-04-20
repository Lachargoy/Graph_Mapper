from __future__ import annotations
#graph_mapper_agent/adapters/tooling/web_browser_navigation_actions_adapter.py
from graph_mapper_agent.adapters.web_browser.tool import (
    WebBrowserTool,
)
from graph_mapper_agent.application.ports.navigation_actions import (
    DownloadArtifactRequest,
    InspectPageRequest,
    NavigationActionsPort,
    OpenArtifactRequest,
    SearchWithTextRequest,
    ProbeContentRequest,
)


class WebBrowserNavigationActionsAdapter(NavigationActionsPort):
    """
    Bridge temporal del agente Graph Mapper sobre WebBrowserTool.

    Expone solo las acciones de navegación que el agente necesita,
    sin depender internamente de ToolRegistry.
    """

    def __init__(self, web_browser_tool: WebBrowserTool) -> None:
        self._web_browser_tool = web_browser_tool

    def inspect_page(self, request: InspectPageRequest) -> dict[str, object]:
        raw = self._web_browser_tool.inspect_page(
            {
                "jurisdiction_code": request.jurisdiction_code,
                "document_key": request.document_key,
                "entry_url": request.entry_url,
                "timeout_seconds": request.timeout_seconds,
                "include_screenshot": request.include_screenshot,
                "metadata": dict(request.metadata),
            }
        )
        if not isinstance(raw, dict):
            raise TypeError("inspect_page(...) debe regresar dict[str, object]")
        return raw

    def search_with_text(self, request: SearchWithTextRequest) -> dict[str, object]:
        raw = self._web_browser_tool.search_with_text(
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
            }
        )
        if not isinstance(raw, dict):
            raise TypeError("search_with_text(...) debe regresar dict[str, object]")
        return raw

    def download_artifact(self, request: DownloadArtifactRequest) -> dict[str, object]:
        raw = self._web_browser_tool.download_candidate(
            {
                "jurisdiction_code": request.jurisdiction_code,
                "document_key": request.document_key,
                "candidate_url": request.candidate_url,
                "timeout_seconds": request.timeout_seconds,
            }
        )
        if not isinstance(raw, dict):
            raise TypeError("download_candidate(...) debe regresar dict[str, object]")
        return raw

    def open_artifact(self, request: OpenArtifactRequest) -> dict[str, object]:
        raw = self._web_browser_tool.open_artifact(
            {
                "candidate_url": request.candidate_url,
                "original_path": request.original_path,
                "storage_ref": request.storage_ref,
            }
        )
        if not isinstance(raw, dict):
            raise TypeError("open_artifact(...) debe regresar dict[str, object]")
        return raw

    def inspect_live(
        self,
        request: LiveInspectionRequest,
    ) -> dict[str, object]:
        raw = self._web_browser_tool.inspect_page(
            {
                "entry_url": request.url,
                "goal": request.question,
                "metadata": dict(request.metadata),
                "include_screenshot": request.include_screenshot,
                "max_candidates": request.max_candidates,
            }
        )
        if not isinstance(raw, dict):
            raise TypeError("inspect_page(...) debe regresar dict[str, object]")
        return raw


    def probe_content(self, request: ProbeContentRequest) -> dict[str, object]:
        raw = self._web_browser_tool.probe_content(
            {
                "jurisdiction_code": request.jurisdiction_code,
                "document_key": request.document_key,
                "url": request.url,
                "timeout_seconds": request.timeout_seconds,
                "metadata": dict(request.metadata),
            }
        )
        if not isinstance(raw, dict):
            raise TypeError("probe_content(...) debe regresar dict[str, object]")
        return raw
