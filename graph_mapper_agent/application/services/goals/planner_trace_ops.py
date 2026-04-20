from __future__ import annotations

from dataclasses import replace

from graph_mapper_agent.application.services.goals.models import (
    DynamicGoalCondition,
    GoalIntent,
    GoalProposal,
    GoalTrace,
)
from graph_mapper_agent.application.services.goals.planner_models import (
    GoalPlanningOutput,
    PlannedGoalCondition,
)


def build_goal_trace(parsed: GoalPlanningOutput, *, goal_context: str) -> GoalTrace:
    normalized_goal = sanitize_goal_text(parsed.goal_intent, max_len=280) or goal_context
    proposal_summary = sanitize_goal_text(parsed.proposal_summary, max_len=280) or normalized_goal
    conditions = tuple(coerce_condition(condition) for condition in parsed.conditions)

    proposal = GoalProposal(
        proposal_id="proposal_1",
        version=1,
        summary=proposal_summary,
        status="draft",
        conditions=conditions,
        planning_notes=sanitize_goal_text(parsed.planning_notes, max_len=400),
    )
    intent = GoalIntent(
        intent_id="intent_1",
        source_goal_context=goal_context,
        normalized_goal=normalized_goal,
    )
    return GoalTrace(intent=intent, proposals=(proposal,))


def accept_proposal(
    trace: GoalTrace,
    *,
    proposal_id: str,
    actor: str,
    note: str,
) -> GoalTrace:
    updated_proposals = []
    for proposal in trace.proposals:
        if proposal.proposal_id == proposal_id:
            updated_proposals.append(proposal.with_status("active"))
        elif proposal.status == "active":
            updated_proposals.append(proposal.with_status("superseded"))
        else:
            updated_proposals.append(proposal)

    log_entry = validation_log_entry(
        actor=actor,
        action="accept",
        proposal_id=proposal_id,
        note=note,
    )
    return replace(
        trace,
        proposals=tuple(updated_proposals),
        active_proposal_id=proposal_id,
        validation_log=trace.validation_log + (log_entry,),
    )


def revise_proposal(
    trace: GoalTrace,
    *,
    proposal_id: str,
    actor: str,
    note: str,
    summary: str,
    conditions: tuple[DynamicGoalCondition, ...],
) -> GoalTrace:
    base = trace.get_proposal(proposal_id)
    if base is None:
        raise ValueError(f"Unknown proposal_id: {proposal_id}")

    next_version = max((proposal.version for proposal in trace.proposals), default=0) + 1
    new_proposal_id = f"proposal_{next_version}"
    revised_proposal = GoalProposal(
        proposal_id=new_proposal_id,
        version=next_version,
        summary=sanitize_goal_text(summary, max_len=240) or "revised proposal",
        status="draft",
        conditions=conditions,
        planning_notes=sanitize_goal_text(note, max_len=400),
        parent_proposal_id=base.proposal_id,
    )

    updated_proposals = []
    for proposal in trace.proposals:
        if proposal.proposal_id == proposal_id:
            updated_proposals.append(proposal.with_status("superseded"))
        else:
            updated_proposals.append(proposal)
    updated_proposals.append(revised_proposal)

    log_entry = validation_log_entry(
        actor=actor,
        action="revise",
        proposal_id=proposal_id,
        note=note,
    )
    return replace(
        trace,
        proposals=tuple(updated_proposals),
        validation_log=trace.validation_log + (log_entry,),
    )


def coerce_condition(condition: PlannedGoalCondition) -> DynamicGoalCondition:
    return DynamicGoalCondition(
        condition_id=condition.condition_id.strip(),
        label=sanitize_goal_text(condition.label, max_len=160) or "",
        kind=sanitize_goal_text(condition.kind, max_len=80) or "document_presence",
        target_kind=sanitize_goal_text(condition.target_kind, max_len=120) or "",
        requiredness=sanitize_goal_text(condition.requiredness, max_len=40) or "mandatory",
        filters=dict(condition.filters),
        min_count=max(1, int(condition.min_count)),
    )


def build_replan_user_content(trace: GoalTrace, feedback: str) -> str:
    proposal = trace.active_proposal() or (trace.proposals[-1] if trace.proposals else None)
    lines = [
        "ORIGINAL GOAL CONTEXT:",
        trace.intent.source_goal_context,
        "",
        "NORMALIZED INTENT:",
        trace.intent.normalized_goal,
        "",
        "CURRENT PROPOSAL:",
        "none" if proposal is None else (proposal.summary or proposal.proposal_id),
        "",
        "CURRENT CONDITIONS:",
    ]
    if proposal is None or not proposal.conditions:
        lines.append("- none")
    else:
        for condition in proposal.conditions:
            lines.append(
                f"- {condition.condition_id} | "
                f"{condition.label} | "
                f"{condition.kind} | "
                f"{condition.target_kind} | "
                f"requiredness={condition.requiredness} | "
                f"filters={condition.filters} | "
                f"min_count={condition.min_count}"
            )
    lines.extend(
        [
            "",
            "USER FEEDBACK:",
            feedback,
            "",
            "Generate a complete revised proposal. Do not perform a diff; return the entire new operational proposal.",
        ]
    )
    return "\n".join(lines)


def validation_log_entry(*, actor: str, action: str, proposal_id: str, note: str) -> str:
    safe_actor = sanitize_goal_text(actor, max_len=80) or "unknown"
    safe_note = sanitize_goal_text(note, max_len=280) or ""
    return f"actor={safe_actor} action={action} proposal_id={proposal_id} note={safe_note}".strip()


def sanitize_goal_context(value: object, *, max_len: int = 1200) -> str:
    if value is None:
        return ""

    text = str(value).strip()
    if not text:
        return ""

    cleaned = "".join(ch for ch in text if ch.isprintable() or ch in "\n\t")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n").strip()

    if not cleaned:
        return ""

    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()

    return cleaned


def sanitize_goal_text(value: object, *, max_len: int = 800) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    cleaned = "".join(ch for ch in text if ch.isprintable() or ch in "\n\t")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n").strip()

    if not cleaned:
        return None

    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()

    return cleaned or None


__all__ = [
    "accept_proposal",
    "build_goal_trace",
    "build_replan_user_content",
    "coerce_condition",
    "revise_proposal",
    "sanitize_goal_context",
    "sanitize_goal_text",
    "validation_log_entry",
]
