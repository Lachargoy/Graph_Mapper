
#bootstrap/builders/tooling.py
from __future__ import annotations

from dataclasses import dataclass

from graph_mapper_agent.adapters.tools.ingest_storage import (
    IngestStorage,
)
from graph_mapper_agent.adapters.tools.tool_registry import (
    ToolRegistry,
)
from graph_mapper_agent.adapters.web_browser.tool import (
    WebBrowserTool,
    WebBrowserToolSettings,
)
from graph_mapper_agent.adapters.tooling.web_browser_navigation_actions_adapter import (
    WebBrowserNavigationActionsAdapter,
)
from graph_mapper_agent.adapters.tooling.web_browser_live_inspection_adapter import (
    WebBrowserLiveInspectionAdapter,
)
from graph_mapper_agent.application.ports.navigation_actions import (
    NavigationActionsPort,
)
from graph_mapper_agent.application.ports.live_inspection import (
    LiveInspectionPort,
)


@dataclass(frozen=True)
class ToolingBundle:
    registry: ToolRegistry
    browser_tool: WebBrowserTool
    navigation_actions: NavigationActionsPort
    live_inspection: LiveInspectionPort


def build_tooling() -> ToolingBundle:
    registry = ToolRegistry()
    browser_tool = WebBrowserTool(
        storage=IngestStorage(),
        settings=WebBrowserToolSettings(),
    )
    navigation_actions = WebBrowserNavigationActionsAdapter(browser_tool)
    live_inspection = WebBrowserLiveInspectionAdapter(browser_tool)

    registry.register("search_with_text", browser_tool.search_with_text)
    registry.register("inspect_page", browser_tool.inspect_page)
    registry.register("download_candidate", browser_tool.download_candidate)
    registry.register("open_artifact", browser_tool.open_artifact)

    return ToolingBundle(
        registry=registry,
        browser_tool=browser_tool,
        navigation_actions=navigation_actions,
        live_inspection=live_inspection,
    )
