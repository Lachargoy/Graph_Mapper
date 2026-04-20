from __future__ import annotations

from graph_mapper_agent.application.services.decision.normalization import (
    looks_like_bridge,
    looks_like_direct_artifact,
    normalize_text,
    tokenize_text,
)
from graph_mapper_agent.domain.view import NodeView


GENERIC_CONDITION_MARKERS: frozenset[str] = frozenset(
    {
        "document",
        "documento",
        "archivo",
        "artifact",
        "articulo",
        "artículo",
        "pdf",
        "html",
        "pagina",
        "página",
        "page",
        "link",
        "url",
        "recurso",
    }
)

GENERIC_TOKENS_FOR_SPECIFIC_CHECK: frozenset[str] = frozenset(
    {
        "document",
        "documento",
        "archivo",
        "artifact",
        "pagina",
        "page",
        "recurso",
        "sesion",
        "ano",
        "year",
        "kind",
        "target",
        "presence",
        "mandatory",
        "required",
        "document_presence",
        "pdf",
        "html",
        "version",
    }
)


def goal_has_pending_web_page_access(node_view: NodeView) -> bool:
    goal_progress = node_view.goal_progress
    if goal_progress is None:
        return False

    for condition in goal_progress.conditions:
        if condition.status == "satisfied":
            continue
        target_kind = normalize_text(str(getattr(condition, "target_kind", "") or ""))
        kind = normalize_text(str(getattr(condition, "kind", "") or ""))
        if target_kind == "web_page_access" or kind == "navigation_success":
            return True
    return False


def goal_progress_all_satisfied(node_view: NodeView) -> bool:
    goal_progress = node_view.goal_progress
    if goal_progress is None:
        return False
    if not goal_progress.conditions:
        return False
    return all(condition.status == "satisfied" for condition in goal_progress.conditions)


def has_specific_pending_goals(node_view: NodeView) -> bool:
    goal_progress = node_view.goal_progress
    if goal_progress is None:
        return False
    return any(
        condition.status != "satisfied"
        and condition_requires_specific_document_evidence(condition)
        for condition in goal_progress.conditions
    )


def has_promising_bridge_candidates_for_pending_goals(node_view: NodeView) -> bool:
    goal_progress = node_view.goal_progress
    if goal_progress is None:
        return False
    pending = [condition for condition in goal_progress.conditions if condition.status != "satisfied"]
    if not pending:
        return False
    return any(
        looks_like_bridge(candidate)
        and bridge_matches_pending_condition(candidate, condition, node_view)
        for candidate in node_view.candidates
        for condition in pending
    )


def matches_pending_conditions(candidate: object, node_view: NodeView) -> bool:
    goal_progress = node_view.goal_progress
    if goal_progress is None:
        return False
    return any(
        condition.status != "satisfied" and candidate_matches_condition(candidate, condition)
        for condition in goal_progress.conditions
    )


def matches_only_satisfied_conditions(candidate: object, node_view: NodeView) -> bool:
    goal_progress = node_view.goal_progress
    if goal_progress is None:
        return False

    matched_pending = False
    matched_satisfied = False
    pending_exists = False

    for condition in goal_progress.conditions:
        if condition.status != "satisfied":
            pending_exists = True
        if not candidate_matches_condition(candidate, condition):
            continue
        if condition.status == "satisfied":
            matched_satisfied = True
        else:
            matched_pending = True

    return pending_exists and matched_satisfied and not matched_pending


def candidate_matches_condition(candidate: object, condition: object) -> bool:
    text = normalize_text(
        " ".join(
            filter(
                None,
                [
                    str(getattr(candidate, "label", "") or ""),
                    str(getattr(candidate, "target_url", "") or ""),
                    str(getattr(candidate, "reason", "") or ""),
                    str(getattr(candidate, "hint", "") or ""),
                ],
            )
        )
    )

    year = getattr(condition, "year", None)
    if year is not None and str(year) not in text:
        return False

    if condition_requests_generic_pdf(condition):
        return looks_like_direct_artifact(candidate)

    return condition_has_explicit_document_evidence_in_text(condition, text)


def bridge_matches_pending_condition(
    candidate: object,
    condition: object,
    node_view: NodeView,
) -> bool:
    text = normalize_text(
        " ".join(
            filter(
                None,
                [
                    str(getattr(candidate, "label", "") or ""),
                    str(getattr(candidate, "target_url", "") or ""),
                    str(getattr(candidate, "reason", "") or ""),
                    str(getattr(candidate, "hint", "") or ""),
                    str(node_view.url or ""),
                ],
            )
        )
    )

    year = getattr(condition, "year", None)
    if year is not None and str(year) not in text:
        return False

    specific = condition_specific_tokens(condition)
    if not specific:
        return condition_requests_generic_pdf(condition)

    return condition_has_explicit_document_evidence_in_text(condition, text)


def condition_requests_generic_pdf(condition: object) -> bool:
    text = condition_text(condition)
    return "pdf" in text and not condition_requires_specific_document_evidence(condition)


def condition_requires_specific_document_evidence(condition: object) -> bool:
    text = condition_text(condition)
    if not text:
        return False
    tokens = [token for token in tokenize_text(text) if len(token) >= 4]
    specific = [
        token
        for token in tokens
        if token not in GENERIC_CONDITION_MARKERS and not token.isdigit()
    ]
    return bool(specific)


def condition_has_explicit_document_evidence_in_text(
    condition: object,
    candidate_text: str,
) -> bool:
    tokens = condition_specific_tokens(condition)
    if not tokens:
        return False
    matched = [token for token in tokens if token in candidate_text]
    return bool(matched) if len(tokens) == 1 else len(matched) >= 2


def condition_text(condition: object) -> str:
    return normalize_text(
        " ".join(
            filter(
                None,
                [
                    str(getattr(condition, "target_kind", "") or ""),
                    str(getattr(condition, "label", "") or ""),
                ],
            )
        )
    ).strip()


def condition_specific_tokens(condition: object) -> tuple[str, ...]:
    return tuple(
        token
        for token in tokenize_text(condition_text(condition))
        if len(token) >= 4
        and token not in GENERIC_TOKENS_FOR_SPECIFIC_CHECK
        and not token.isdigit()
    )


__all__ = [
    "bridge_matches_pending_condition",
    "candidate_matches_condition",
    "condition_has_explicit_document_evidence_in_text",
    "condition_requests_generic_pdf",
    "condition_requires_specific_document_evidence",
    "condition_specific_tokens",
    "condition_text",
    "goal_has_pending_web_page_access",
    "goal_progress_all_satisfied",
    "has_promising_bridge_candidates_for_pending_goals",
    "has_specific_pending_goals",
    "matches_only_satisfied_conditions",
    "matches_pending_conditions",
]
