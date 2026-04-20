from __future__ import annotations
#./application/services/execution/action_executor.py
from dataclasses import dataclass
from typing import TYPE_CHECKING

from graph_mapper_agent.application.local_perception.service import (
    LocalPerceptionService,
)

from graph_mapper_agent.application.ports.navigation_actions import (
    NavigationActionsPort,
)
from graph_mapper_agent.domain.graph import EdgeState

from .contracts import ActionExecutionResult
from .edge_actions import (
    ExecutionContext,
    download_artifact_for_edge,
    inspect_edge,
    open_artifact_for_edge,
    follow_edge_with_probe,
)
from .normalization import optional_str
from .search import SearchExecutionContext, search_with_text
from .validation import ValidationExecutionContext, validate_current_content

if TYPE_CHECKING:
    from graph_mapper_agent.application.contracts.runtime_views import (
        RuntimeExecutionPort,
    )


@dataclass(slots=True)
class GraphMapperActionExecutor:
    navigation_actions: NavigationActionsPort
    jurisdiction_code: str = "default"
    document_key: str = "graph_mapper_run"
    timeout_seconds: int = 60
    ledger: object | None = None
    local_perception_service: LocalPerceptionService | None = None
    capture_screenshot_for_observations: bool = False
    allow_artifact_download: bool = True
    artifact_persistence_mode: str = "on_validation"
    storage_namespace: str = "graph_mapper_agent"
    session_id: str | None = None
    run_id: str | None = None

    def execute(
        self,
        *,
        runtime: RuntimeExecutionPort,
        decision: dict[str, object],
    ) -> ActionExecutionResult:
        action = str(decision.get("action") or "").strip()
        edge_id = optional_str(decision.get("edge_id"))

        print(f"[executor.execute] action={action} edge_id={edge_id}", flush=True)
        print(f"[executor.execute] decision={decision}", flush=True)

        if action == "mark_exhausted":
            print("[executor.execute] mark_exhausted -> ok", flush=True)
            return ActionExecutionResult(
                action=action,
                status="ok",
                edge_id=None,
                reason="node_marked_exhausted",
            )

        if action == "success":
            print("[executor.execute] success -> ok", flush=True)
            return ActionExecutionResult(
                action=action,
                status="ok",
                edge_id=None,
                reason="goal_satisfied",
            )

        if action == "fail":
            print("[executor.execute] fail -> ok", flush=True)
            return ActionExecutionResult(
                action=action,
                status="ok",
                edge_id=None,
                reason="decision_requested_fail",
            )

        if action == "validate_current_content":
            return validate_current_content(
                context=self._validation_context(),
                runtime=runtime,
                decision=decision,
            )

        if action == "search_with_text":
            return search_with_text(
                context=self._search_context(),
                runtime=runtime,
                decision=decision,
            )

        if not edge_id:
            raise ValueError(f"{action} requiere edge_id")

        edge = runtime.graph.get_edge(edge_id)
        if edge is None:
            raise ValueError(f"Edge no encontrado: {edge_id}")

        print(
            f"[executor.execute] edge found label={edge.label!r} target_url={edge.target_url}",
            flush=True,
        )

        if action == "follow_edge":
            return follow_edge_with_probe(
                runtime=runtime,
                edge=edge,
                context=self._execution_context(),
            )

        if action == "download_artifact":
            return download_artifact_for_edge(
                runtime=runtime,
                edge=edge,
                context=self._execution_context(),
            )

        if action == "open_artifact":
            return open_artifact_for_edge(
                runtime=runtime,
                edge=edge,
                context=self._execution_context(),
            )

        raise ValueError(f"Acción no soportada: {action!r}")

    def _execution_context(self) -> ExecutionContext:
        return ExecutionContext(
            navigation_actions=self.navigation_actions,
            jurisdiction_code=self.jurisdiction_code,
            document_key=self.document_key,
            timeout_seconds=self.timeout_seconds,
            storage_namespace=self.storage_namespace,
            session_id=self.session_id,
            run_id=self.run_id,
            capture_screenshot_for_observations=self.capture_screenshot_for_observations,
            local_perception_service=self.local_perception_service,
            allow_artifact_download=self.allow_artifact_download,
            artifact_persistence_mode=self.artifact_persistence_mode,
        )

    def _validation_context(self) -> ValidationExecutionContext:
        return ValidationExecutionContext(
            navigation_actions=self.navigation_actions,
            jurisdiction_code=self.jurisdiction_code,
            document_key=self.document_key,
            timeout_seconds=self.timeout_seconds,
            local_perception_service=self.local_perception_service,
        )

    def _search_context(self) -> SearchExecutionContext:
        return SearchExecutionContext(
            navigation_actions=self.navigation_actions,
            jurisdiction_code=self.jurisdiction_code,
            document_key=self.document_key,
            timeout_seconds=self.timeout_seconds,
            include_screenshot=self.capture_screenshot_for_observations,
        )


def _looks_like_direct_artifact_edge(edge: EdgeState) -> bool:
    target_url = str(edge.target_url or "").strip().lower()
    if target_url.endswith(".pdf"):
        return True
    if "/pdf/" in target_url:
        return True
    if "arxiv.org/pdf/" in target_url:
        return True

    delivery_mode = str(edge.delivery_mode or "").strip().lower()
    resource_kind = str(edge.resource_kind or "").strip().lower()
    label = str(edge.label or "").strip().lower()
    semantic_label = str(edge.semantic_label or "").strip().lower()
    if delivery_mode == "direct":
        return True
    if resource_kind in {"pdf", "artifact", "document", "file", "pdf_document"}:
        return True
    if ".pdf" in label or "/pdf/" in label:
        return True
    if ".pdf" in semantic_label or "/pdf/" in semantic_label:
        return True

    return False
