from __future__ import annotations
#graph_mapper_agent/application/services/navigation_perception_heuristics.py
import unicodedata
from urllib.parse import urlparse
from typing import Any

from graph_mapper_agent.domain.graph import ObservedCandidate
from graph_mapper_agent.application.navigation_perception.models import (
    CandidateObservation,
    NavigationPerceptionRequest,
)


def classify_layout(
    *,
    candidate_count: int,
    non_main_frame_count: int,
    content_present: bool,
) -> str:
    if candidate_count <= 0 and not content_present and non_main_frame_count <= 0:
        return "empty_or_blocked"

    if candidate_count <= 0 and content_present:
        return "document_like"

    if non_main_frame_count > 0 and candidate_count > 0:
        return "framed_navigation"

    if candidate_count >= 12:
        return "dense_index"

    if candidate_count >= 1:
        return "sparse_navigation"

    return "unknown"


def build_summary(
    *,
    layout_kind: str,
    candidate_count: int,
    content_present: bool,
    non_main_frame_count: int,
) -> str:
    return (
        f"layout={layout_kind} | "
        f"candidate_count={candidate_count} | "
        f"content_present={content_present} | "
        f"non_main_frame_count={non_main_frame_count}"
    )


def recommend_next_step(
    *,
    candidate_count: int,
    content_present: bool,
    non_main_frame_count: int,
) -> str | None:
    if candidate_count > 0:
        return "follow_edge"
    if content_present:
        return "validate_current_content"
    if non_main_frame_count > 0:
        return "refine_navigation_perception"
    return "backtrack_or_use_recoverable_choice_points"


def curate_candidate_observations(
    *,
    candidates: list[dict[str, Any]],
    request: NavigationPerceptionRequest,
    limit: int = 5,
) -> tuple[CandidateObservation, ...]:
    selected = select_prompt_candidates(
        candidates=candidates,
        request=request,
        limit=limit,
    )

    observations: list[CandidateObservation] = []
    for candidate in selected:
        url = str(candidate.get("url") or "").strip()
        if not url:
            continue

        metadata = candidate.get("metadata") or {}
        label = (
            str(candidate.get("text") or "").strip()
            or str(metadata.get("semantic_label") or "").strip()
            or url
        )
        rationale = _candidate_rationale(candidate, request)

        observations.append(
            CandidateObservation(
                url=url,
                label=label,
                score=float(candidate.get("score") or 0.0),
                rationale=rationale,
                source_kind=(
                    str(candidate.get("resource_kind") or metadata.get("resource_kind") or "").strip()
                    or None
                ),
                supports_condition_labels=_infer_condition_support(candidate, request),
                target_document_kind_match=_infer_target_document_kind_match(candidate, request),
                temporal_match=_infer_temporal_match(candidate, request),
                progress_likelihood=_infer_progress_likelihood(candidate, request),
                is_intra_page_anchor=(
                    bool(candidate.get("is_intra_page_anchor"))
                    if candidate.get("is_intra_page_anchor") is not None
                    else _is_intra_page_anchor(
                        final_url=str(request.url or "").strip(),
                        candidate_url=url,
                    )
                ),
            )
        )

    return tuple(observations)


def build_observed_candidates(
    inspection: dict[str, Any],
) -> tuple[ObservedCandidate, ...]:
    observed: list[ObservedCandidate] = []
    for candidate in inspection.get("candidates") or []:
        candidate_url = str(candidate.get("url") or "").strip()
        if not candidate_url:
            continue
        metadata = candidate.get("metadata") or {}
        observed.append(
            ObservedCandidate(
                target_url=candidate_url,
                label=(
                    str(candidate.get("text") or "").strip()
                    or str(metadata.get("semantic_label") or "").strip()
                    or candidate_url
                ),
                relation=str(candidate.get("relation") or "unknown"),
                candidate_type=str(candidate.get("candidate_type") or "unknown"),
                resource_kind=(
                    str(candidate.get("resource_kind") or metadata.get("resource_kind") or "").strip()
                    or None
                ),
                delivery_mode=(
                    str(candidate.get("delivery_mode") or metadata.get("delivery_mode") or "").strip()
                    or None
                ),
                semantic_label=str(metadata.get("semantic_label") or "").strip() or None,
                table_heading=str(metadata.get("table_heading") or "").strip() or None,
                adjacent_cell_text=str(metadata.get("adjacent_cell_text") or "").strip() or None,
                same_host=(
                    candidate.get("same_host")
                    if candidate.get("same_host") is not None
                    else metadata.get("same_host")
                ),
                base_score=float(candidate.get("score") or 0.0),
                source_channel="navigation_perception",
                source_frame=(
                    str(candidate.get("source_frame") or "").strip()
                    or str(metadata.get("source_frame") or "").strip()
                    or None
                ),
                metadata=dict(metadata),
            )
        )
    return tuple(observed)


def select_prompt_candidates(
    *,
    candidates: list[dict[str, Any]],
    request: NavigationPerceptionRequest,
    limit: int,
) -> list[dict[str, Any]]:
    if not candidates:
        return []

    def haystack(candidate: dict[str, Any]) -> str:
        metadata = candidate.get("metadata") or {}
        parts = [
            str(candidate.get("url") or ""),
            str(candidate.get("text") or ""),
            str(candidate.get("title") or ""),
            str(candidate.get("relation") or ""),
            str(candidate.get("candidate_type") or ""),
            str(candidate.get("resource_kind") or ""),
            str(candidate.get("delivery_mode") or ""),
            str(metadata.get("semantic_label") or ""),
            str(metadata.get("context_text") or ""),
            str(metadata.get("adjacent_cell_text") or ""),
            str(metadata.get("table_heading") or ""),
            str(metadata.get("resource_kind") or ""),
            str(metadata.get("delivery_mode") or ""),
        ]
        return normalize_recovery_text(" ".join(parts))

    keywords_by_kind = {
        "annex_document": ["anexo", "annex", "anx"],
        "appendix_document": ["apendice", "apéndice", "appendix"],
        "textual_version": [
            "estenograf",
            "estenográfica",
            "estenografica",
            "stenographic",
            "version estenografica",
            "versión estenográfica",
        ],
        "discussion_journal": ["diario", "debate", "journal", "discusion", "discusión"],
        "pdf": [".pdf", "pdf"],
        "session_record": ["sesion", "sesión", "acta", "registro"],
    }

    buckets: dict[str, list[dict[str, Any]]] = {}
    for kind in request.target_document_kinds:
        buckets[f"kind:{kind}"] = []
    for cond in request.pending_goal_conditions:
        buckets[f"cond:{cond}"] = []
    for temp in request.temporal_constraints:
        buckets[f"time:{temp}"] = []
    buckets["general"] = []

    for candidate in candidates:
        text = haystack(candidate)
        assigned = False

        for kind in request.target_document_kinds:
            keys = keywords_by_kind.get(
                kind,
                [normalize_recovery_text(kind.replace("_", " "))],
            )
            if any(k in text for k in keys):
                buckets[f"kind:{kind}"].append(candidate)
                assigned = True

        for cond in request.pending_goal_conditions:
            cond_norm = normalize_recovery_text(cond.replace("_", " "))
            cond_tokens = [tok for tok in cond_norm.split() if len(tok) >= 3]
            if cond_tokens and any(tok in text for tok in cond_tokens):
                buckets[f"cond:{cond}"].append(candidate)
                assigned = True

        for temp in request.temporal_constraints:
            temp_str = normalize_recovery_text(str(temp))
            if temp_str and temp_str in text:
                buckets[f"time:{temp}"].append(candidate)
                assigned = True

        if not assigned:
            buckets["general"].append(candidate)

    for bucket in buckets.values():
        bucket.sort(key=lambda c: float(c.get("score") or 0.0), reverse=True)

    ordered_bucket_keys = [
        *[f"kind:{k}" for k in request.target_document_kinds],
        *[f"cond:{c}" for c in request.pending_goal_conditions],
        *[f"time:{t}" for t in request.temporal_constraints],
        "general",
    ]

    result: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    active = True
    while len(result) < limit and active:
        active = False
        for bucket_key in ordered_bucket_keys:
            bucket = buckets.get(bucket_key, [])
            while bucket:
                candidate = bucket.pop(0)
                url = str(candidate.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                result.append(candidate)
                seen_urls.add(url)
                active = True
                break
            if len(result) >= limit:
                break

    return result[:limit]


def normalize_recovery_text(value: object) -> str:
    raw = str(value or "").strip().lower()
    decomposed = unicodedata.normalize("NFKD", raw)
    return "".join(
        ch if ch.isalnum() or ch in {"_", " "} else " "
        for ch in decomposed
        if not unicodedata.combining(ch)
    )


def _candidate_rationale(
    candidate: dict[str, Any],
    request: NavigationPerceptionRequest,
) -> str:
    metadata = candidate.get("metadata") or {}
    parts: list[str] = []

    resource_kind = str(candidate.get("resource_kind") or metadata.get("resource_kind") or "").strip()
    delivery_mode = str(candidate.get("delivery_mode") or metadata.get("delivery_mode") or "").strip()
    semantic_label = str(metadata.get("semantic_label") or "").strip()
    table_heading = str(metadata.get("table_heading") or "").strip()
    context_text = str(metadata.get("context_text") or "").strip()

    if resource_kind:
        parts.append(f"resource_kind={resource_kind}")
    if delivery_mode:
        parts.append(f"delivery_mode={delivery_mode}")
    if semantic_label:
        parts.append(f"semantic_label={semantic_label}")
    if table_heading:
        parts.append(f"table_heading={table_heading}")
    if context_text:
        parts.append(f"context≈{context_text[:80]}")

    matched_conditions = _infer_condition_support(candidate, request)
    if matched_conditions:
        parts.append(f"matches={list(matched_conditions)}")

    temporal_match = _infer_temporal_match(candidate, request)
    if temporal_match:
        parts.append(f"time={list(temporal_match)}")

    return " | ".join(parts) if parts else "candidate_visible_in_local_context"


def _infer_condition_support(
    candidate: dict[str, Any],
    request: NavigationPerceptionRequest,
) -> tuple[str, ...]:
    text = _candidate_text(candidate)
    matched: list[str] = []
    for cond in request.pending_goal_conditions:
        cond_norm = normalize_recovery_text(cond.replace("_", " "))
        cond_tokens = [tok for tok in cond_norm.split() if len(tok) >= 3]
        if cond_tokens and any(tok in text for tok in cond_tokens):
            matched.append(cond)
    return tuple(matched)


def _infer_target_document_kind_match(
    candidate: dict[str, Any],
    request: NavigationPerceptionRequest,
) -> str | None:
    text = _candidate_text(candidate)
    for kind in request.target_document_kinds:
        kind_norm = normalize_recovery_text(kind.replace("_", " "))
        kind_tokens = [tok for tok in kind_norm.split() if len(tok) >= 3]
        if kind_tokens and any(tok in text for tok in kind_tokens):
            return kind
    return None


def _infer_temporal_match(
    candidate: dict[str, Any],
    request: NavigationPerceptionRequest,
) -> tuple[str, ...]:
    text = _candidate_text(candidate)
    matched: list[str] = []
    for temp in request.temporal_constraints:
        temp_str = normalize_recovery_text(str(temp))
        if temp_str and temp_str in text:
            matched.append(str(temp))
    return tuple(matched)


def _infer_progress_likelihood(
    candidate: dict[str, Any],
    request: NavigationPerceptionRequest,
) -> str | None:
    condition_hits = len(_infer_condition_support(candidate, request))
    kind_hit = _infer_target_document_kind_match(candidate, request) is not None
    resource_kind = str(candidate.get("resource_kind") or "").strip().lower()
    delivery_mode = str(candidate.get("delivery_mode") or "").strip().lower()

    if delivery_mode in {"direct", "download"} or resource_kind in {"pdf", "document"}:
        if condition_hits > 0 or kind_hit:
            return "high"
        return "medium"

    if condition_hits > 0 or kind_hit:
        return "medium"

    return "low"


def _candidate_text(candidate: dict[str, Any]) -> str:
    metadata = candidate.get("metadata") or {}
    return " ".join(
        part
        for part in (
            normalize_recovery_text(candidate.get("url") or ""),
            normalize_recovery_text(candidate.get("text") or ""),
            normalize_recovery_text(candidate.get("title") or ""),
            normalize_recovery_text(metadata.get("semantic_label") or ""),
            normalize_recovery_text(metadata.get("context_text") or ""),
            normalize_recovery_text(metadata.get("adjacent_cell_text") or ""),
            normalize_recovery_text(metadata.get("table_heading") or ""),
            normalize_recovery_text(candidate.get("resource_kind") or ""),
            normalize_recovery_text(candidate.get("delivery_mode") or ""),
        )
        if part
    )


def _is_intra_page_anchor(*, final_url: str, candidate_url: str) -> bool:
    if not final_url or not candidate_url:
        return False
    final_parts = urlparse(final_url)
    candidate_parts = urlparse(candidate_url)
    if not candidate_parts.fragment:
        return False
    return (
        final_parts.scheme,
        final_parts.netloc,
        final_parts.path,
        final_parts.query,
    ) == (
        candidate_parts.scheme,
        candidate_parts.netloc,
        candidate_parts.path,
        candidate_parts.query,
    )
