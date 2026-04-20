from __future__ import annotations
#graph_mapper_agent/application/services/decision/llm_pipeline.py
from typing import Any

from graph_mapper_agent.application.services.decision.condition_matching import (
    has_promising_bridge_candidates_for_pending_goals,
    has_specific_pending_goals,
    matches_pending_conditions,
    matches_only_satisfied_conditions,
)
from graph_mapper_agent.application.services.decision.constants import (
    ALLOWED_ACTIONS,
    EDGE_REQUIRING_ACTIONS,
)
from graph_mapper_agent.application.services.decision.contracts import (
    GraphMapperDecision,
    parse_scratchpad_update,
    safe_str,
)
from graph_mapper_agent.application.services.decision.fallback_selection import (
    choose_bridge_fallback_candidate,
    choose_safe_fallback_candidate,
)
from graph_mapper_agent.application.services.decision.guardrails import (
    guard_edge_requirements,
    guard_exhausted_bridges,
    guard_fail,
    guard_no_candidates,
    guard_pdf_leaf,
    guard_refine,
    guard_search,
    guard_success,
    guard_validate,
)
from graph_mapper_agent.application.services.decision.heuristic import (
    artifact_arrival_edge_id,
)
from graph_mapper_agent.application.services.decision.llm_context import (
    DecisionLlmContext,
)
from graph_mapper_agent.application.services.decision.llm_use_case import (
    GraphMapperDecisionLlmRequest,
    GraphMapperDecisionLlmUseCase,
)
from graph_mapper_agent.application.services.decision.normalization import (
    looks_like_direct_artifact,
)
from graph_mapper_agent.application.services.decision.prompt_selection import (
    select_prompt_builder,
)
from graph_mapper_agent.application.services.decision.search_helpers import (
    node_view_search_targets,
)
from graph_mapper_agent.domain.view import NodeView
from graph_mapper_agent.ledger.domain.actor_kind import ActorKind
from graph_mapper_agent.ledger.domain.run_correlation import (
    RunCorrelation,
)
from graph_mapper_agent.ledger.domain.target_ref import TargetRef


def decide_llm(
    *,
    llm_use_case: GraphMapperDecisionLlmUseCase,
    node_view: NodeView,
    run: RunCorrelation | None,
    actor: ActorKind | None,
    target: TargetRef | None,
    metadata: dict[str, object],
) -> GraphMapperDecision:
    if run is None:
        raise ValueError("GraphMapperDecider con llm_use_case requiere run")
    if actor is None:
        raise ValueError("GraphMapperDecider con llm_use_case requiere actor")

    ctx = build_llm_context(
        llm_use_case=llm_use_case,
        node_view=node_view,
        run=run,
        actor=actor,
        target=target,
        metadata=metadata,
    )

    return (
        guard_fail(ctx)
        or guard_pdf_leaf(ctx)
        or guard_no_candidates(ctx)
        or guard_success(ctx)
        or guard_refine(ctx)
        or guard_exhausted_bridges(ctx)
        or guard_validate(ctx)
        or guard_search(ctx)
        or guard_edge_requirements(ctx)
        or refine_and_finalize(ctx)
    )


def build_llm_context(
    *,
    llm_use_case: GraphMapperDecisionLlmUseCase,
    node_view: NodeView,
    run: RunCorrelation,
    actor: ActorKind,
    target: TargetRef | None,
    metadata: dict[str, object],
) -> DecisionLlmContext:
    prompt_builder, prompt_version = select_prompt_builder(metadata)
    prompt = prompt_builder(node_view)

    request_metadata = {
        **dict(metadata),
        "prompt_version": prompt_version,
        "graph_mapper_prompt_version": str(
            metadata.get("graph_mapper_prompt_version") or "v1"
        ).strip().lower(),
    }

    payload = llm_use_case.decide(
        GraphMapperDecisionLlmRequest(
            prompt=prompt,
            run=run,
            actor=actor,
            target=target,
            metadata=request_metadata,
        )
    )

    action = str(payload.get("action") or "").strip()
    if action != "fail" and action not in ALLOWED_ACTIONS:
        raise ValueError(f"Acción inválida del LLM: {action!r}")

    raw_edge = payload.get("edge_id")
    edge_id = None if raw_edge in (None, "", "null") else str(raw_edge).strip()

    raw_search_target_id = payload.get("search_target_id")
    search_target_id = (
        None
        if raw_search_target_id in (None, "", "null")
        else str(raw_search_target_id).strip()
    )

    query_text = safe_str(payload.get("query_text"))

    confidence: float | None = None
    if payload.get("confidence") is not None:
        try:
            confidence = float(payload["confidence"])
        except (TypeError, ValueError):
            pass

    rationale = safe_str(payload.get("decision_rationale"))
    scratchpad = parse_scratchpad_update(payload.get("scratchpad_update"))
    arrival_edge_id = artifact_arrival_edge_id(node_view)

    if action == "open_artifact" and not edge_id and arrival_edge_id is not None:
        edge_id = arrival_edge_id

    selected_candidate: Any = None
    if edge_id:
        for candidate in node_view.candidates:
            if candidate.edge_id == edge_id:
                selected_candidate = candidate
                break

    selected_search_target: Any = None
    if search_target_id:
        for item in node_view_search_targets(node_view):
            if safe_str(getattr(item, "search_target_id", None)) == search_target_id:
                selected_search_target = item
                break

    return DecisionLlmContext(
        node_view=node_view,
        action=action,
        edge_id=edge_id,
        search_target_id=search_target_id,
        query_text=query_text,
        confidence=confidence,
        rationale=rationale,
        scratchpad=scratchpad,
        selected_candidate=selected_candidate,
        selected_search_target=selected_search_target,
        arrival_edge_id=arrival_edge_id,
        working_plan=scratchpad.working_plan if scratchpad else None,
        tactical_observations=scratchpad.tactical_observations if scratchpad else None,
    )


def refine_and_finalize(ctx: DecisionLlmContext) -> GraphMapperDecision:
    if ctx.action == "download_artifact" and ctx.selected_candidate is not None:
        early = refine_download(ctx)
        if early is not None:
            return early

    if (
        ctx.action in EDGE_REQUIRING_ACTIONS
        and ctx.selected_candidate is not None
        and looks_like_direct_artifact(ctx.selected_candidate)
        and has_specific_pending_goals(ctx.node_view)
        and not matches_pending_conditions(ctx.selected_candidate, ctx.node_view)
        and has_promising_bridge_candidates_for_pending_goals(ctx.node_view)
    ):
        bridge = choose_bridge_fallback_candidate(
            ctx.node_view,
            exclude_edge_id=ctx.selected_candidate.edge_id,
        )
        if bridge is not None:
            return GraphMapperDecision(
                action="follow_edge",
                edge_id=bridge.edge_id,
                decision_rationale=ctx.suffixed(
                    "redirected_to_bridge_candidate_for_specific_pending_goal",
                    "direct_artifact_without_specific_goal_match",
                ),
                confidence=ctx.or_confidence(0.60),
                scratchpad_update=ctx.scratchpad,
            )

    if ctx.action == "open_artifact" and ctx.selected_candidate is not None:
        if not looks_like_direct_artifact(ctx.selected_candidate):
            ctx.action = "follow_edge"
            ctx.rationale = ctx.suffixed(
                "degraded_to_follow_edge_for_bridge_validation",
                "llm_requested_open_on_non_direct",
            )

    return GraphMapperDecision(
        action=ctx.action,
        edge_id=ctx.edge_id,
        search_target_id=ctx.search_target_id,
        query_text=ctx.query_text,
        decision_rationale=ctx.rationale,
        confidence=ctx.confidence,
        scratchpad_update=ctx.scratchpad,
    )


def refine_download(ctx: DecisionLlmContext) -> GraphMapperDecision | None:
    candidate = ctx.selected_candidate

    if not looks_like_direct_artifact(candidate):
        ctx.action = "follow_edge"
        ctx.rationale = ctx.suffixed(
            "degraded_to_follow_edge_for_bridge_or_non_direct",
            "llm_requested_download_on_non_direct",
        )
        return None

    if not matches_only_satisfied_conditions(candidate, ctx.node_view):
        return None

    fallback = choose_safe_fallback_candidate(
        ctx.node_view,
        exclude_edge_id=candidate.edge_id,
    )

    if fallback is None:
        return GraphMapperDecision(
            action="mark_exhausted",
            edge_id=None,
            decision_rationale=ctx.suffixed(
                "converted_to_mark_exhausted_to_avoid_redundant_satisfied_artifact",
                "download_matches_only_satisfied_conditions",
            ),
            confidence=ctx.or_confidence(0.55),
            scratchpad_update=ctx.scratchpad,
        )

    fallback_action = (
        "download_artifact" if looks_like_direct_artifact(fallback) else "follow_edge"
    )
    return GraphMapperDecision(
        action=fallback_action,
        edge_id=fallback.edge_id,
        decision_rationale=ctx.suffixed(
            "redirected_to_non_redundant_candidate",
            "download_matches_only_satisfied_conditions",
        ),
        confidence=ctx.or_confidence(0.55),
        scratchpad_update=ctx.scratchpad,
    )


__all__ = [
    "build_llm_context",
    "decide_llm",
    "refine_and_finalize",
]
