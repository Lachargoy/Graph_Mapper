
#graph_mapper_agent/bootstrap/builders/runtime.py
from __future__ import annotations

from dataclasses import dataclass

from graph_mapper_agent.navigation.application.orchestrator import (
    NavigationOrchestrator,
)
from graph_mapper_agent.application.services.execution.action_executor import (
    GraphMapperActionExecutor,
)
from graph_mapper_agent.application.local_perception.service import (
    LocalPerceptionService,
)
from graph_mapper_agent.application.navigation_perception.service import (
    NavigationPerceptionService,
)
from graph_mapper_agent.application.services.decision.llm_use_case import (
    GraphMapperDecisionLlmUseCase,
)
from graph_mapper_agent.domain.graph_merge import (
    ObservedCandidateMergePolicy,
)
from graph_mapper_agent.application.services.finding_extractor import (
    FindingExtractor,
)
from graph_mapper_agent.application.services.decision.decider import (
    GraphMapperDecider,
)
from graph_mapper_agent.application.services.candidate_ranker import (
    CandidateRanker,
)
from graph_mapper_agent.application.services.candidate_selector import (
    CandidateSelector,
)
from graph_mapper_agent.application.services.exploration_scope_policy import (
    ExplorationScopePolicy,
)
from graph_mapper_agent.application.services.page_classifier import (
    PageClassifier,
)
from graph_mapper_agent.application.services.graph_updater import (
    GraphUpdater,
)
from graph_mapper_agent.application.services.node_view_builder import (
    NodeViewBuilder,
)

from graph_mapper_agent.application.ports.navigation_actions import (
    NavigationActionsPort,
)
from ..config import GraphMapperConfig
from ..execution_config import GuidedGraphMapperConfig
from .perception import build_navigation_perception_coordinator
from ..timing import timed
from graph_mapper_agent.runtime.nodes import GraphMapperNodes
from graph_mapper_agent.runtime.state import (
    update_document_validation_node_state,
)
from graph_mapper_agent.runtime.transitions import (
    TERMINAL_STATES,
    build_transitions,
)

@dataclass(frozen=True)
class RuntimeBundle:
    orchestrator: NavigationOrchestrator


def build_runtime_bundle(
    *,
    request: GraphMapperConfig,
    execution: GuidedGraphMapperConfig,
    navigation_actions: NavigationActionsPort,
    ledger: object | None,
    llm_use_case: GraphMapperDecisionLlmUseCase | None,
    navigation_perception_service: NavigationPerceptionService | None,
    local_perception_service: LocalPerceptionService | None,
) -> RuntimeBundle:
    page_classifier = PageClassifier()
    candidate_selector = CandidateSelector()
    candidate_ranker = CandidateRanker()
    node_view_builder = NodeViewBuilder()
    exploration_scope_policy = ExplorationScopePolicy()
    candidate_merge_policy = ObservedCandidateMergePolicy()
    finding_extractor = FindingExtractor()

    navigation_perception_coordinator = build_navigation_perception_coordinator(
        navigation_perception_service=navigation_perception_service,
        execution_metadata=dict(execution.execution_metadata or {}),
        candidate_merge_policy=candidate_merge_policy,
        finding_extractor=finding_extractor,
        local_perception_service=local_perception_service,
    )

    graph_updater = GraphUpdater(
        finding_extractor=finding_extractor,
        document_validation_state_updater=update_document_validation_node_state,
    )

    decider = GraphMapperDecider(
        candidate_selector=candidate_selector,
        candidate_ranker=candidate_ranker,
        llm_use_case=llm_use_case,
    )

    action_executor = GraphMapperActionExecutor(
        navigation_actions=navigation_actions,
        jurisdiction_code=execution.jurisdiction_code,
        document_key=execution.document_key,
        timeout_seconds=execution.timeout_seconds,
        ledger=ledger,
        storage_namespace=str(
            execution.execution_metadata.get("storage_namespace")
            or "graph_mapper_agent"
        ),
        session_id=(
            str(execution.execution_metadata.get("session_id")).strip()
            if execution.execution_metadata.get("session_id") is not None
            else None
        ),
        run_id=execution.run_id,
        local_perception_service=local_perception_service,
        allow_artifact_download=request.allow_artifact_download,
        artifact_persistence_mode=str(
            execution.execution_metadata.get("artifact_persistence_mode")
            or "on_validation"
        ),
        capture_screenshot_for_observations=bool(
            execution.execution_metadata.get(
                "navigation_perception_include_screenshot",
                False,
            )
        ),
    )

    nodes = GraphMapperNodes(
        page_classifier=page_classifier,
        node_view_builder=node_view_builder,
        exploration_scope_policy=exploration_scope_policy,
        graph_updater=graph_updater,
        decider=decider,
        action_executor=action_executor,
        candidate_merge_policy=candidate_merge_policy,
        navigation_perception_coordinator=navigation_perception_coordinator,
    )

    transitions = timed(
        "runtime.build_transitions",
        lambda: build_transitions(nodes),
    )

    orchestrator = NavigationOrchestrator(
        transitions=transitions,
        terminal_states=TERMINAL_STATES,
        max_steps=request.max_pages,
    )

    return RuntimeBundle(
        orchestrator=orchestrator,
    )
