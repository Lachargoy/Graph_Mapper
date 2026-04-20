from __future__ import annotations
#graph_mapper_agent/adapters/tooling/web_browser_live_inspection_adapter.py
from graph_mapper_agent.adapters.web_browser.tool import (
    WebBrowserTool,
)
from graph_mapper_agent.application.ports.live_inspection import (
    LiveInspectionPort,
    LiveInspectionRequest,
)


class WebBrowserLiveInspectionAdapter(LiveInspectionPort):
    """
    Bridge temporal del agente Graph Mapper sobre WebBrowserTool.inspect_page(...).
    """

    def __init__(self, web_browser_tool: WebBrowserTool) -> None:
        self._web_browser_tool = web_browser_tool

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
