from __future__ import annotations

from typing import Any, Mapping

from graph_mapper_agent.application.services.goals.models import (
    DynamicGoalCondition,
    GoalTrace,
)
from graph_mapper_agent.application.services.goals.planner import (
    GoalPlannerRequest,
    GoalPlannerResult,
    GoalPlannerUseCase,
)

from ..config import GraphMapperConfig
from ..execution_config import GuidedGraphMapperConfig
from ..timing import ts


def build_goal_trace(
    *,
    request: GraphMapperConfig,
    execution: GuidedGraphMapperConfig,
) -> GoalPlannerResult | None:
    result = _maybe_plan_goals(
        request=request,
        execution=execution,
    )
    result = _apply_goal_trace_feedback(
        result,
        execution_metadata=dict(execution.execution_metadata or {}),
    )
    result = _ensure_active_goal_trace(result)
    return result


def _maybe_plan_goals(
    *,
    request: GraphMapperConfig,
    execution: GuidedGraphMapperConfig,
) -> GoalPlannerResult | None:
    execution_metadata = dict(execution.execution_metadata or {})
    precomputed_goal_trace = execution_metadata.get("precomputed_goal_trace")
    if isinstance(precomputed_goal_trace, GoalTrace):
        print(
            f"[{ts()}] [graph_mapper.goal_planner] using precomputed goal_trace",
            flush=True,
        )
        return GoalPlannerResult(
            planning_notes=str(
                execution_metadata.get("goal_planning_notes") or ""
            ).strip()
            or None,
            goal_trace=precomputed_goal_trace,
        )

    goal_context = (request.goal or "").strip()
    if not goal_context:
        print(
            f"[{ts()}] [graph_mapper.goal_planner] skipped: empty goal_context",
            flush=True,
        )
        return None

    llm_runtime_config = execution.llm_runtime
    if llm_runtime_config is None:
        print(
            f"[{ts()}] [graph_mapper.goal_planner] skipped: no llm_runtime available",
            flush=True,
        )
        return None

    planner = GoalPlannerUseCase(llm_runtime_config=llm_runtime_config)
    result = planner.plan(GoalPlannerRequest(goal_context=goal_context))

    if result.goal_trace is None:
        print(
            f"[{ts()}] [graph_mapper.goal_planner] planner returned no goal_trace",
            flush=True,
        )
        return None

    print(
        f"[{ts()}] [graph_mapper.goal_planner] goal_trace={result.goal_trace is not None} "
        f"planning_notes={result.planning_notes!r}",
        flush=True,
    )
    return result


def _apply_goal_trace_feedback(
    result: GoalPlannerResult | None,
    *,
    execution_metadata: Mapping[str, Any],
) -> GoalPlannerResult | None:
    if result is None or result.goal_trace is None:
        return result

    feedback = execution_metadata.get("goal_trace_feedback")
    if not isinstance(feedback, Mapping):
        return result

    action = str(feedback.get("action") or "").strip().lower()
    proposal_id = str(feedback.get("proposal_id") or "").strip()
    actor = str(feedback.get("actor") or "user").strip() or "user"
    note = str(feedback.get("note") or "").strip()

    if not proposal_id:
        proposal = result.goal_trace.active_proposal() or (
            result.goal_trace.proposals[-1] if result.goal_trace.proposals else None
        )
        proposal_id = proposal.proposal_id if proposal is not None else ""

    if not proposal_id:
        return result

    updated_trace = result.goal_trace
    if action == "accept":
        updated_trace = GoalPlannerUseCase.accept_proposal(
            updated_trace,
            proposal_id=proposal_id,
            actor=actor,
            note=note or "accepted from execution metadata",
        )
    elif action == "revise":
        updated_trace = GoalPlannerUseCase.revise_proposal(
            updated_trace,
            proposal_id=proposal_id,
            actor=actor,
            note=note or "revised from execution metadata",
            summary=str(feedback.get("summary") or "revised proposal").strip(),
            conditions=_coerce_feedback_conditions(feedback.get("conditions")),
        )
    else:
        return result

    return GoalPlannerResult(
        planning_notes=result.planning_notes,
        goal_trace=updated_trace,
    )


def _ensure_active_goal_trace(
    result: GoalPlannerResult | None,
) -> GoalPlannerResult | None:
    if result is None or result.goal_trace is None:
        return result

    if result.goal_trace.active_proposal() is not None:
        return result

    if not result.goal_trace.proposals:
        return result

    latest_proposal = result.goal_trace.proposals[-1]
    activated_trace = GoalPlannerUseCase.accept_proposal(
        result.goal_trace,
        proposal_id=latest_proposal.proposal_id,
        actor="system",
        note="default_activation_for_run_start",
    )
    return GoalPlannerResult(
        planning_notes=result.planning_notes,
        goal_trace=activated_trace,
    )


def _coerce_feedback_conditions(raw_conditions: object) -> tuple[object, ...]:
    if not isinstance(raw_conditions, list):
        return ()

    conditions = []
    for raw_condition in raw_conditions:
        if not isinstance(raw_condition, Mapping):
            continue

        label = str(raw_condition.get("label") or "").strip()
        if not label:
            continue

        filters = raw_condition.get("filters")
        conditions.append(
            DynamicGoalCondition(
                condition_id=str(
                    raw_condition.get("condition_id") or f"c{len(conditions) + 1}"
                ).strip(),
                label=label,
                kind=str(
                    raw_condition.get("kind") or "document_presence"
                ).strip(),
                target_kind=str(raw_condition.get("target_kind") or "").strip(),
                requiredness=str(
                    raw_condition.get("requiredness") or "mandatory"
                ).strip(),
                filters=dict(filters) if isinstance(filters, Mapping) else {},
                min_count=max(1, int(raw_condition.get("min_count") or 1)),
            )
        )
    return tuple(conditions)
