from __future__ import annotations

from graph_mapper_agent.application.services.goals.models import (
    GoalTrace,
)


def pending_years_from_goal_trace(goal_trace: GoalTrace | None) -> frozenset[str]:
    if goal_trace is None:
        return frozenset()

    pending: set[str] = set()

    for proposal in goal_trace.proposals:
        if proposal.status != "active":
            continue
        for condition in proposal.conditions:
            if condition.status == "satisfied":
                continue
            year = condition.filters.get("year")
            if isinstance(year, int):
                pending.add(str(year))

    return frozenset(pending)


def year_alignment_score(
    target_url: str,
    label: str,
    pending_years: frozenset[str],
) -> int:
    if not pending_years:
        return 0
    text = f"{target_url} {label}".lower()
    return sum(1 for year in pending_years if year in text)


def goal_aligned_priority(
    base_score: float,
    target_url: str,
    label: str,
    pending_years: frozenset[str],
    *,
    alignment_bonus: float = 100.0,
) -> float:
    score = year_alignment_score(target_url, label, pending_years)
    return score * alignment_bonus + base_score


__all__ = [
    "goal_aligned_priority",
    "pending_years_from_goal_trace",
    "year_alignment_score",
]
