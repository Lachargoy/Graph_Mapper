from __future__ import annotations
#graph_mapper_agent/bootstrap/builders/perception.py
from typing import Any, Mapping

from graph_mapper_agent.adapters.perception.llm_navigation_perception_executor import (
    LlmNavigationPerceptionExecutor,
    LlmNavigationPerceptionExecutorSettings,
)
from graph_mapper_agent.adapters.perception.web_browser_navigation_executor import (
    WebBrowserNavigationPerceptionExecutor,
    WebBrowserNavigationPerceptionExecutorSettings,
)
from graph_mapper_agent.adapters.web_browser.tool import (
    WebBrowserTool,
)
from graph_mapper_agent.platform.llm.config import (
    LlmRuntimeConfig,
)
from graph_mapper_agent.application.services.navigation_perception import (
    NavigationPerceptionCoordinator,
    NavigationPerceptionIntentBuilder,
    NavigationPerceptionTriggerPolicy,
)
from graph_mapper_agent.runtime.state import (
    update_document_validation_node_state,
)
from graph_mapper_agent.application.local_perception.service import (
    LocalPerceptionService,
)
from graph_mapper_agent.application.services.finding_extractor import (
    FindingExtractor,
)
from graph_mapper_agent.application.navigation_perception.service import (
    NavigationPerceptionService,
)
from graph_mapper_agent.domain.graph_merge import (
    ObservedCandidateMergePolicy,
)
from graph_mapper_agent.ledger.domain.actor_kind import ActorKind
from graph_mapper_agent.ledger.config import resolve_graph_mapper_path
from graph_mapper_agent.ledger.domain.run_correlation import (
    RunCorrelation,
)
from graph_mapper_agent.ledger.domain.target_ref import TargetRef

from .llm import build_llm_runtime_bundle
from graph_mapper_agent.adapters.perception.snapshot_aware_inspection_adapter import (
    SnapshotAwareInspectionAdapter,
)
from graph_mapper_agent.application.ports.live_inspection import (
    LiveInspectionPort,
)


def build_navigation_perception_service(
    *,
    browser_tool: WebBrowserTool,
    live_inspection: LiveInspectionPort,
    llm_runtime_config: LlmRuntimeConfig | None,
    execution_metadata: Mapping[str, Any],
    ledger: object | None = None,
    ledger_run: RunCorrelation | None = None,
    ledger_actor: ActorKind | None = None,
    ledger_target: TargetRef | None = None,
) -> NavigationPerceptionService:

    """
    Bridge builder for navigation perception.

    Assembles:
    - LLM executor already migrated to the agent package
    - Legacy heuristic browser executor
    - Legacy navigation perception service

    Does not yet represent the final publishable wiring.
    """
    mode = str(
        execution_metadata.get("navigation_perception_mode") or "heuristic"
    ).strip().lower()
    inspection_source = SnapshotAwareInspectionAdapter(live_inspection)

    if mode == "llm" and llm_runtime_config is not None:
        bundle = build_llm_runtime_bundle(
            llm_runtime_config=llm_runtime_config,
            expected_output_name="navigation_perception_output",
            ledger=ledger,
            label_prefix="navigation_perception",
        )
        if bundle is None:
            raise ValueError(
                "Could not build the LLM runtime for navigation perception."
            )

        executor = LlmNavigationPerceptionExecutor(
                    inspection_source=inspection_source,
                    llm_runtime=bundle.runtime,
                    invoke_llm_use_case=bundle.invoke_llm_use_case,
                    ledger_run=ledger_run,
                    ledger_actor=ledger_actor,
                    ledger_target=ledger_target,
                    settings=LlmNavigationPerceptionExecutorSettings(
                        max_candidates_to_inspect=int(
                            execution_metadata.get(
                                "navigation_perception_max_candidates_to_inspect"
                            )
                            or 600
                        ),
                        max_candidates_to_prompt=int(
                            execution_metadata.get(
                                "navigation_perception_max_candidates_to_prompt"
                            )
                            or 40
                        ),
                        text_excerpt_max_chars=int(
                            execution_metadata.get(
                                "navigation_perception_text_excerpt_max_chars"
                            )
                            or 2000
                        ),
                        enable_visual_recovery_pass=bool(
                            execution_metadata.get(
                                "navigation_perception_enable_visual_recovery_pass", True
                            )
                        ),
                        max_visual_recovery_hints=int(
                            execution_metadata.get(
                                "navigation_perception_max_visual_recovery_hints"
                            )
                            or 6
                        ),
                        debug_payload_io=bool(
                            execution_metadata.get("navigation_perception_debug_payload_io")
                        ),
                        debug_payload_dump_dir=(
                            str(
                                resolve_graph_mapper_path(
                                    str(
                                        execution_metadata.get(
                                            "navigation_perception_debug_payload_dump_dir"
                                        )
                                        or ""
                                    ).strip()
                                )
                            )
                            if str(
                                execution_metadata.get(
                                    "navigation_perception_debug_payload_dump_dir"
                                )
                                or ""
                            ).strip()
                            else None
                        ),
                    ),
                )
    else:
        executor = WebBrowserNavigationPerceptionExecutor(
            web_browser_tool=browser_tool,
            settings=WebBrowserNavigationPerceptionExecutorSettings(
                max_candidates_to_inspect=int(
                    execution_metadata.get(
                        "navigation_perception_max_candidates_to_inspect"
                    )
                    or 600
                ),
            ),
        )

    return NavigationPerceptionService(executor=executor)


def build_navigation_perception_coordinator(
    *,
    navigation_perception_service: NavigationPerceptionService | None,
    execution_metadata: Mapping[str, Any],
    candidate_merge_policy: ObservedCandidateMergePolicy,
    finding_extractor: FindingExtractor,
    local_perception_service: LocalPerceptionService | None = None,
) -> NavigationPerceptionCoordinator | None:
    coordinator = (
        None
        if navigation_perception_service is None
        else NavigationPerceptionCoordinator(
            service=navigation_perception_service,
            trigger_policy=NavigationPerceptionTriggerPolicy(),
            intent_builder=NavigationPerceptionIntentBuilder(
                include_screenshot=bool(
                    execution_metadata.get(
                        "navigation_perception_include_screenshot"
                    )
                )
            ),
            candidate_merge_policy=candidate_merge_policy,
            finding_extractor=finding_extractor,
            document_validation_state_updater=update_document_validation_node_state,
        )
    )

    if coordinator is not None and local_perception_service is not None:
        coordinator.local_perception_service = local_perception_service

    return coordinator
