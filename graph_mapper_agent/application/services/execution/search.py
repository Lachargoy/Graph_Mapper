from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
#graph_mapper_agent/application/services/execution/search.py
from graph_mapper_agent.application.ports.navigation_actions import (
    NavigationActionsPort,
    SearchWithTextRequest,
)

from .contracts import ActionExecutionResult
from .normalization import optional_str

if TYPE_CHECKING:
    from graph_mapper_agent.application.contracts.runtime_views import (
        RuntimeExecutionPort,
    )


@dataclass(slots=True, frozen=True)
class SearchExecutionContext:
    navigation_actions: NavigationActionsPort
    jurisdiction_code: str
    document_key: str
    timeout_seconds: int
    include_screenshot: bool = False


def search_with_text(
    *,
    context: SearchExecutionContext,
    runtime: RuntimeExecutionPort,
    decision: dict[str, object],
) -> ActionExecutionResult:
    search_target_id = optional_str(decision.get("search_target_id"))
    query_text = optional_str(decision.get("query_text"))

    if not search_target_id:
        raise ValueError("search_with_text requiere search_target_id")
    if not query_text:
        raise ValueError("search_with_text requiere query_text")
    if not runtime.current_node_id:
        raise ValueError("search_with_text requiere current_node_id")

    node = runtime.graph.get_node(runtime.current_node_id)
    if node is None:
        raise ValueError(f"Nodo actual no encontrado: {runtime.current_node_id}")

    print(
        "[debug.executor.search.enter] "
        f"node_id={node.node_id!r} "
        f"url={node.canonical_url!r} "
        f"search_target_id={search_target_id!r} "
        f"query_text={query_text!r}",
        flush=True,
    )

    raw = context.navigation_actions.search_with_text(
        SearchWithTextRequest(
            jurisdiction_code=context.jurisdiction_code,
            document_key=context.document_key,
            entry_url=node.canonical_url,
            search_target_id=search_target_id,
            query_text=query_text,
            timeout_seconds=context.timeout_seconds,
            include_screenshot=context.include_screenshot,
        )
    )

    print(
        f"[debug.executor.search.raw] raw_type={type(raw).__name__}",
        flush=True,
    )

    candidates = list(raw.get("candidates") or [])
    search_metadata = raw.get("search_metadata")
    metadata = raw.get("metadata")

    print(
        "[debug.executor.search.result] "
        f"final_url={raw.get('final_url')!r} "
        f"page_url={raw.get('page_url')!r} "
        f"title={raw.get('title')!r} "
        f"candidate_count={len(candidates)} "
        f"search_target_count={len(list(raw.get('search_targets') or []))} "
        f"search_metadata={search_metadata!r}",
        flush=True,
    )

    if isinstance(metadata, dict):
        print(
            "[debug.executor.search.metadata] "
            f"candidate_count={metadata.get('candidate_count')!r} "
            f"search_target_count={metadata.get('search_target_count')!r} "
            f"content_present={metadata.get('content_present')!r}",
            flush=True,
        )

    for idx, candidate in enumerate(candidates[:10], start=1):
        if not isinstance(candidate, dict):
            print(
                f"[debug.executor.search.candidate.{idx}] non_dict={candidate!r}",
                flush=True,
            )
            continue

        print(
            "[debug.executor.search.candidate] "
            f"idx={idx} "
            f"url={candidate.get('url')!r} "
            f"text={candidate.get('text')!r} "
            f"resource_kind={candidate.get('resource_kind')!r} "
            f"delivery_mode={candidate.get('delivery_mode')!r} "
            f"score={candidate.get('score')!r}",
            flush=True,
        )

    status, reason = _resolve_search_outcome(
        current_url=node.canonical_url,
        raw=raw,
    )

    print(
        "[debug.executor.search.outcome] "
        f"status={status!r} reason={reason!r}",
        flush=True,
    )

    return ActionExecutionResult(
        action="search_with_text",
        status=status,
        inspection_result=raw,
        search_target_id=search_target_id,
        query_text=query_text,
        reason=reason,
    )


def _resolve_search_outcome(
    *,
    current_url: str,
    raw: dict[str, object],
) -> tuple[str, str]:
    """
    Decide si el search produjo progreso real o fue no-op/fallo silencioso.

    Criterios de no-op / failed:
    - search_metadata.status = target_not_found / failed / no_target
    - results_detected = False y state_delta_kind in {None, "none", "no_change"}
    - la URL final sigue siendo la misma y no hay delta explícito
    """
    search_metadata = raw.get("search_metadata")

    # Si no es dict, intentamos convertirlo si parece un objeto con campos
    if search_metadata is not None and not isinstance(search_metadata, dict):
        try:
            # Soporte básico para objetos con __dict__ o pydantic models
            if hasattr(search_metadata, "model_dump"):
                search_metadata = getattr(search_metadata, "model_dump")()
            elif hasattr(search_metadata, "__dict__"):
                search_metadata = search_metadata.__dict__
        except Exception:
            pass

    status = None
    state_delta_kind = None
    results_detected = None

    if isinstance(search_metadata, dict):
        status = optional_str(search_metadata.get("status"))
        state_delta_kind = optional_str(search_metadata.get("state_delta_kind"))
        results_detected = search_metadata.get("results_detected")

    if status in {"target_not_found", "failed", "no_target", "target_missing"}:
        return "failed", f"search_{status}"

    if results_detected is False and state_delta_kind in {None, "none", "no_change"}:
        return "failed", "search_no_state_delta"

    final_url = (
        optional_str(raw.get("page_url"))
        or optional_str(raw.get("final_url"))
        or current_url
    )

    # Si no hay search_metadata y la URL es la misma, sospechamos que no hubo cambio
    if search_metadata is None and current_url and final_url and current_url == final_url:
        # Pero si hay nuevos candidatos, quizá sí hubo cambio (p.ej. AJAX que no muta URL)
        candidates = raw.get("candidates")
        if not candidates or (isinstance(candidates, (list, tuple)) and len(candidates) == 0):
            return "failed", "search_missing_metadata_no_url_change_no_candidates"

    if (
        current_url
        and final_url
        and current_url == final_url
        and state_delta_kind in {None, "none", "no_change"}
        and results_detected is not True
    ):
        return "failed", "search_same_page_no_delta"

    return "ok", "search_executed"