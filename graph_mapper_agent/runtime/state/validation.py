from __future__ import annotations
#graph_mapper_agent/runtime/state/validation.py
from typing import TYPE_CHECKING

from graph_mapper_agent.application.contracts.validation_state import (
    DocumentValidationNodeState,
)

if TYPE_CHECKING:
    from .models import GraphMapperState


def document_validation_context_signature(
    *,
    inspection_result: dict[str, object] | None,
    payload: dict[str, object] | None = None,
) -> str:
    inspection_dict = inspection_result if isinstance(inspection_result, dict) else {}
    payload_dict = payload if isinstance(payload, dict) else {}
    metadata = payload_dict.get("metadata")
    metadata_dict = dict(metadata) if isinstance(metadata, dict) else {}

    page_url = (
        _optional_str(inspection_dict.get("page_url"))
        or _optional_str(inspection_dict.get("final_url"))
        or _optional_str(inspection_dict.get("url"))
        or ""
    )
    title = _optional_str(inspection_dict.get("title")) or ""
    content = (
        _optional_str(inspection_dict.get("content"))
        or _optional_str(inspection_dict.get("text_excerpt"))
        or ""
    )
    source_action = (
        _optional_str(metadata_dict.get("source_action"))
        or _optional_str(payload_dict.get("source_action"))
        or ""
    )
    return "|".join((page_url, title, str(len(content)), source_action))


def _pending_signature_from_runtime(runtime: GraphMapperState) -> str:
    evaluated = runtime.evaluated_goal_trace()
    active = None if evaluated is None else evaluated.active_proposal()
    if active is None:
        return ""

    pending_ids = sorted(
        condition.condition_id
        for condition in active.conditions
        if condition.status != "satisfied"
    )
    return "|".join(pending_ids)


def _evidence_signature(
    *,
    inspection_result: dict[str, object] | None,
    payload: dict[str, object] | None,
    evidence_ref: str | None = None,
) -> str:
    inspection_dict = inspection_result if isinstance(inspection_result, dict) else {}
    payload_dict = payload if isinstance(payload, dict) else {}
    metadata = payload_dict.get("metadata")
    metadata_dict = dict(metadata) if isinstance(metadata, dict) else {}

    ref = (
        (evidence_ref or "").strip()
        or _optional_str(metadata_dict.get("evidence_ref"))
        or _optional_str(inspection_dict.get("page_url"))
        or _optional_str(inspection_dict.get("final_url"))
        or _optional_str(inspection_dict.get("url"))
        or ""
    )
    source_action = (
        _optional_str(metadata_dict.get("source_action"))
        or _optional_str(payload_dict.get("source_action"))
        or ""
    )
    return f"{ref}|{source_action}"


def update_document_validation_node_state(
    *,
    runtime: GraphMapperState,
    node_id: str,
    payload: dict[str, object] | None,
    inspection_result: dict[str, object] | None = None,
    evidence_ref: str | None = None,
) -> DocumentValidationNodeState:
    node_state = runtime.goal_validation_state_by_node.get(node_id)
    if node_state is None:
        node_state = DocumentValidationNodeState(node_id=node_id)
        runtime.goal_validation_state_by_node[node_id] = node_state

    current_context_signature = document_validation_context_signature(
        inspection_result=inspection_result,
        payload=payload,
    )
    pending_signature = _pending_signature_from_runtime(runtime)
    evidence_signature = _evidence_signature(
        inspection_result=inspection_result,
        payload=payload,
        evidence_ref=evidence_ref,
    )

    validation_key = (
        f"{evidence_signature}||{pending_signature}"
        if evidence_signature or pending_signature
        else current_context_signature
    )

    if current_context_signature != node_state.last_context_signature:
        node_state.validation_attempts = 0
    else:
        node_state.validation_attempts += 1

    payload_dict = payload if isinstance(payload, dict) else {}
    metadata = payload_dict.get("metadata")
    metadata_dict = dict(metadata) if isinstance(metadata, dict) else {}

    validation_status = _optional_str(
        metadata_dict.get("validation_status")
    ) or _optional_str(payload_dict.get("status"))

    matched_condition_ids = tuple(
        str(item).strip()
        for item in (metadata_dict.get("matched_condition_ids") or ())
        if str(item).strip()
    )

    source_action = _optional_str(metadata_dict.get("source_action")) or _optional_str(
        payload_dict.get("source_action")
    )

    node_state.last_context_signature = current_context_signature
    node_state.last_evidence_signature = evidence_signature or None
    node_state.last_pending_signature = pending_signature or None
    node_state.last_validation_status = validation_status
    node_state.last_matched_condition_ids = matched_condition_ids
    node_state.last_source_action = source_action

    # 1) If this evidence was already validated before, do not validate again.
    if evidence_signature and evidence_signature in node_state.validated_evidence_signatures:
        node_state.can_revalidate = False
        node_state.reason = "same_evidence_already_validated_try_sibling_edges"
        return node_state

    # 2) If we already tried exactly this combination of evidence + pending,
    #    we don't repeat it either.
    if validation_key in node_state.seen_validation_keys:
        node_state.can_revalidate = False
        node_state.reason = "same_validation_context_already_attempted"
        return node_state

    # 3) We register this combination as already attempted.
    node_state.seen_validation_keys.add(validation_key)

    # 4) Main policy:
    #    - validated => this evidence is consumed; go for siblings
    #    - invalid/inconclusive/needs_more_pages => do not repeat same context
    #    - any other case => yes available
    if validation_status == "validated":
        if evidence_signature:
            node_state.validated_evidence_signatures.add(evidence_signature)
        node_state.can_revalidate = False
        node_state.reason = "current_evidence_consumed_try_sibling_edges"
    elif validation_status in ("invalid", "inconclusive", "needs_more_pages"):
        node_state.can_revalidate = False
        node_state.reason = (
            f"same_context_blocked_after_{validation_status}"
        )
    else:
        node_state.can_revalidate = True
        node_state.reason = "document_validation_available"

    return node_state


def ensure_document_validation_node_state(
    *,
    runtime: GraphMapperState,
    node_id: str,
) -> DocumentValidationNodeState:
    payload = runtime.goal_validation_payload_by_node.get(node_id)
    inspection_result = runtime.inspection_result_by_node.get(node_id)

    node_state = runtime.goal_validation_state_by_node.get(node_id)
    if node_state is None:
        node_state = DocumentValidationNodeState(node_id=node_id)
        runtime.goal_validation_state_by_node[node_id] = node_state

    current_context_signature = document_validation_context_signature(
        inspection_result=inspection_result if isinstance(inspection_result, dict) else None,
        payload=payload if isinstance(payload, dict) else None,
    )
    pending_signature = _pending_signature_from_runtime(runtime)
    evidence_signature = _evidence_signature(
        inspection_result=inspection_result if isinstance(inspection_result, dict) else None,
        payload=payload if isinstance(payload, dict) else None,
    )

    node_state.last_context_signature = current_context_signature
    node_state.last_evidence_signature = evidence_signature or None
    node_state.last_pending_signature = pending_signature or None

    # If there is no payload yet, it doesn't mean "infinite permission";
    # it only means that the first validation might be available.
    if not isinstance(payload, dict):
        if evidence_signature and evidence_signature in node_state.validated_evidence_signatures:
            node_state.can_revalidate = False
            node_state.reason = "same_evidence_already_validated_try_sibling_edges"
        else:
            node_state.can_revalidate = True
            node_state.reason = "document_validation_available"
        return node_state

    return update_document_validation_node_state(
        runtime=runtime,
        node_id=node_id,
        payload=payload,
        inspection_result=inspection_result if isinstance(inspection_result, dict) else None,
        evidence_ref=_optional_str(
            dict((payload.get("metadata") or {})).get("evidence_ref")
        ) if isinstance(payload, dict) else None,
    )


def current_node_validation_capability(
    *,
    runtime: GraphMapperState,
    node_id: str,
    document_validation_state: DocumentValidationNodeState | None,
    can_validate: bool,
    build_validation_target_for_node,
) -> tuple[bool, str | None]:
    if not can_validate:
        return False, "document_validation_not_available"

    validation_target = build_validation_target_for_node(
        runtime=runtime,
        node_id=node_id,
    )
    if validation_target is None:
        return False, "insufficient_local_evidence_for_document_validation"

    # If there is no state, we allow the first validation.
    if document_validation_state is None:
        return True, f"validate_current_content_available:{validation_target.source_kind}"

    if not document_validation_state.can_revalidate:
        return False, document_validation_state.reason or "revalidation_blocked"

    return True, (
        f"validate_current_content_available:{validation_target.source_kind}"
        f" | last_status={document_validation_state.last_validation_status or 'none'}"
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "DocumentValidationNodeState",
    "current_node_validation_capability",
    "document_validation_context_signature",
    "ensure_document_validation_node_state",
    "update_document_validation_node_state",
]