from __future__ import annotations
#graph_mapper_agent/application/services/execution/validation_support.py
from typing import TYPE_CHECKING

from graph_mapper_agent.application.goal_validation.validation_models import (
    GoalCondition,
)
from graph_mapper_agent.application.local_perception.models import (
    LocalPerceptionResult,
)
from graph_mapper_agent.domain.graph import EdgeState

from .normalization import dedupe_tokens, optional_str
from .result_builders import local_perception_payload

if TYPE_CHECKING:
    from graph_mapper_agent.application.contracts.runtime_views import (
        RuntimeGoalTracePort,
    )


def candidate_count_from_inspection(inspection_result: dict[str, object]) -> int:
    metadata = inspection_result.get("metadata")
    metadata_dict = metadata if isinstance(metadata, dict) else {}
    inspection_metadata = inspection_result.get("inspection_metadata")
    inspection_metadata_dict = (
        inspection_metadata if isinstance(inspection_metadata, dict) else {}
    )
    raw_value = (
        metadata_dict.get("candidate_count")
        or inspection_metadata_dict.get("candidate_count")
        or len(list(inspection_result.get("candidates") or ()))
    )
    try:
        return int(raw_value or 0)
    except (TypeError, ValueError):
        return 0


def inspection_looks_like_terminal_document(
    inspection_result: dict[str, object],
) -> bool:
    candidates = list(inspection_result.get("candidates") or ())
    if not candidates:
        return True
    candidate_count = candidate_count_from_inspection(inspection_result)
    if candidate_count <= 2:
        return True
    non_anchor_candidates = 0
    for candidate in candidates:
        if not isinstance(candidate, dict):
            non_anchor_candidates += 1
            continue
        if candidate.get("is_intra_page_anchor") is True:
            continue
        non_anchor_candidates += 1
    return non_anchor_candidates == 0


def build_artifact_validation_intent(
    runtime: RuntimeGoalTracePort,
    edge: EdgeState,
) -> tuple[str, tuple[str, ...], tuple[GoalCondition, ...]]:
    evaluated = runtime.evaluated_goal_trace()
    active = None if evaluated is None else evaluated.active_proposal()

    if active is None:
        return (
            f"Validar el tipo documental del artifact asociado a '{edge.label}'.",
            dedupe_tokens((edge.label, edge.target_url)),
            (),
        )

    pending = [condition for condition in active.conditions if condition.status != "satisfied"]
    if not pending:
        return (
            f"Validar el tipo documental del artifact asociado a '{edge.label}'.",
            dedupe_tokens((edge.label, edge.target_url)),
            (),
        )

    condition_lines: list[str] = []
    token_sources: list[object] = [edge.label, edge.target_url]
    goal_conditions: list[GoalCondition] = []

    for condition in pending:
        year = condition.year_filter
        document_family = condition.document_family
        preferred_carrier = condition.preferred_carrier
        accepted_carriers = condition.accepted_carriers
        strict_carrier_required = condition.strict_carrier_required

        condition_lines.append(
            f"{condition.label} "
            f"(target_kind={condition.target_kind}, "
            f"document_family={document_family}, "
            f"year={year}, "
            f"preferred_carrier={preferred_carrier}, "
            f"accepted_carriers={list(accepted_carriers)}, "
            f"strict_carrier_required={strict_carrier_required})"
        )

        token_sources.extend(
            (
                condition.label,
                condition.target_kind,
                document_family,
                preferred_carrier,
                *accepted_carriers,
                year,
            )
        )

        goal_conditions.append(
            GoalCondition(
                condition_id=condition.condition_id,
                label=condition.label,
                target_kind=condition.target_kind,
                year=year,
                requiredness=condition.requiredness,
                min_count=condition.min_count,
                document_family=document_family,
                preferred_carrier=preferred_carrier,
                accepted_carriers=accepted_carriers,
                strict_carrier_required=strict_carrier_required,
            )
        )

    question = (
        "Determina si este artifact satisface alguna de las condiciones pendientes. "
        "Evalua solo el documento actual. "
        "Valida principalmente por familia documental, año y alcance visible. "
        "El carrier importa solo cuando la condición lo requiera explícitamente. "
        f"Condiciones pendientes: {'; '.join(condition_lines)}."
    )

    return question, dedupe_tokens(tuple(token_sources)), tuple(goal_conditions)


def infer_validation_document_family(condition: object) -> str:
    explicit = optional_str(getattr(condition, "target_kind", None))
    label = optional_str(getattr(condition, "label", None)) or ""
    label_l = label.lower()

    if explicit and explicit not in {"pdf_document", "document", "artifact"}:
        return explicit

    if (
        "estenograf" in label_l
        or "stenographic" in label_l
        or "versión estenográfica" in label_l
    ):
        return "stenographic_version"

    if "anexo" in label_l or "annex" in label_l:
        return "annex_document"

    if "acta" in label_l:
        return "minutes_document"

    if "iniciativa" in label_l:
        return "initiative_document"

    if "dictamen" in label_l:
        return "dictamen_document"

    return explicit or "document"


__all__ = [
    "build_artifact_validation_intent",
    "candidate_count_from_inspection",
    "infer_validation_document_family",
    "inspection_looks_like_terminal_document",
    "local_perception_payload",
]
