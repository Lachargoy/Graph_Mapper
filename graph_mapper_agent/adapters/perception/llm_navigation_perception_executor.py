# aither/adapters/navigation_perception/llm_navigation_perception_executor.py
from __future__ import annotations

import base64
import json
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from graph_mapper_agent.application.ports.inspection_source import (
    InspectionSourcePort,
    InspectionSourceRequest,
)
from graph_mapper_agent.application.services.navigation_perception_heuristics import (
    build_observed_candidates,
    build_summary,
    classify_layout,
    curate_candidate_observations,
    recommend_next_step,
    select_prompt_candidates,
)
from graph_mapper_agent.domain.graph import ObservedCandidate
from graph_mapper_agent.application.navigation_perception.models import (
    CandidateObservation,
    CurrentNodeGoalMatch,
    NavigationPerceptionRequest,
    NavigationPerceptionResult,
    VisualRecoveryHint,
)
from graph_mapper_agent.domain.ports.llm_runtime_port import (
    LlmRuntimeError,
    LlmRuntimePort,
    LlmRuntimeRequest,
)
from graph_mapper_agent.ledger.application.invoke_llm_with_ledger_use_case import (
    InvokeLlmWithLedgerUseCase,
)
from graph_mapper_agent.ledger.domain.actor_kind import ActorKind
from graph_mapper_agent.ledger.domain.run_correlation import (
    RunCorrelation,
)
from graph_mapper_agent.ledger.domain.target_ref import TargetRef


@dataclass(frozen=True, slots=True)
class LlmNavigationPerceptionExecutorSettings:
    prompt_version: str = "navigation_perception_v3_en"
    max_candidates_to_inspect: int = 600
    max_candidates_to_prompt: int = 40
    text_excerpt_max_chars: int = 2000
    image_detail: str = "auto"
    enable_visual_recovery_pass: bool = True
    max_visual_recovery_hints: int = 6
    debug_payload_io: bool = False
    debug_payload_dump_dir: str | None = None


class LlmNavigationPerceptionExecutor:
    def __init__(
        self,
        *,
        inspection_source: InspectionSourcePort,
        llm_runtime: LlmRuntimePort,
        invoke_llm_use_case: InvokeLlmWithLedgerUseCase | None = None,
        ledger_run: RunCorrelation | None = None,
        ledger_actor: ActorKind | None = None,
        ledger_target: TargetRef | None = None,
        settings: LlmNavigationPerceptionExecutorSettings | None = None,
    ) -> None:
        self._inspection_source = inspection_source
        self._llm_runtime = llm_runtime
        self._invoke_llm_use_case = invoke_llm_use_case
        self._ledger_run = ledger_run
        self._ledger_actor = ledger_actor
        self._ledger_target = ledger_target
        self._settings = settings or LlmNavigationPerceptionExecutorSettings()

    def perceive(self, request: NavigationPerceptionRequest) -> NavigationPerceptionResult:
        inspection = self._inspection_source.resolve_for_perception(
            InspectionSourceRequest(
                url=request.url,
                question=request.question,
                metadata=request.metadata if isinstance(request.metadata, dict) else {},
                include_screenshot=request.include_screenshot,
                max_candidates=self._settings.max_candidates_to_inspect,
            )
        )

        inspection_metadata = inspection.get("metadata") or {}
        inspection_metadata = (
            inspection_metadata if isinstance(inspection_metadata, dict) else {}
        )
        used_prefetched = bool(inspection_metadata.get("used_prefetched_inspection"))
        inspection_source_kind = str(
            inspection_metadata.get("inspection_source_kind") or ""
        ).strip() or "unknown"

        print(
            "[debug.np.llm.prefetched] "
            f"node_id={request.node_id!r} "
            f"used_prefetched={used_prefetched} "
            f"inspection_source_kind={inspection_source_kind!r} "
            f"candidate_count={len(list(inspection.get('candidates') or []))} "
            f"search_target_count={len(list(inspection.get('search_targets') or []))} "
            f"final_url={inspection.get('final_url')!r} "
            f"page_url={inspection.get('page_url')!r}",
            flush=True,
        )

        fallback_without_screenshot_used = False
        llm_error_fallback_used = False
        llm_error_fallback_reason: str | None = None
        llm_error_details: dict[str, object] | None = None

        try:
            payload, llm_request_debug = self._invoke_llm(
                request=request,
                inspection=inspection,
                prompt_candidates=None,
                recovery_hints=(),
                pass_label="initial",
            )
        except LlmRuntimeError as exc:
            if not self._should_retry_without_screenshot(
                request=request,
                inspection=inspection,
                error=exc,
            ):
                if self._should_fallback_to_heuristic(error=exc):
                    heuristic_result = self._fallback_result_from_inspection(
                        request=request,
                        inspection=inspection,
                        reason=(
                            "llm_navigation_perception_invalid_or_unavailable_response; "
                            "using_browser_heuristic_fallback"
                        ),
                        error=exc,
                    )
                    return heuristic_result
                raise

            fallback_without_screenshot_used = True
            print(
                "[navigation_perception] multimodal request rejected; retrying without screenshot",
                file=sys.stderr,
                flush=True,
            )
            inspection = dict(inspection)
            inspection["screenshot_base64"] = ""
            inspection["screenshot_mime_type"] = None

            try:
                payload, llm_request_debug = self._invoke_llm(
                    request=request,
                    inspection=inspection,
                    prompt_candidates=None,
                    recovery_hints=(),
                    pass_label="initial_fallback_no_screenshot",
                )
            except LlmRuntimeError as exc:
                if self._should_fallback_to_heuristic(error=exc):
                    heuristic_result = self._fallback_result_from_inspection(
                        request=request,
                        inspection=inspection,
                        reason=(
                            "llm_navigation_perception_failed_after_multimodal_retry; "
                            "using_browser_heuristic_fallback"
                        ),
                        error=exc,
                    )
                    return heuristic_result
                raise

        visual_recovery_hints = self._parse_visual_recovery_hints(
            payload.get("visual_recovery_hints")
        )
        recovery_candidates = self._recover_candidates_from_visual_hints(
            inspection=inspection,
            visual_hints=visual_recovery_hints,
        )

        recovery_pass_used = False
        recovery_request_debug = None
        if self._settings.enable_visual_recovery_pass and recovery_candidates:
            try:
                payload, recovery_request_debug = self._invoke_llm(
                    request=request,
                    inspection=inspection,
                    prompt_candidates=self._build_final_prompt_candidates(
                        inspection=inspection,
                        recovered_candidates=recovery_candidates,
                    ),
                    recovery_hints=visual_recovery_hints,
                    pass_label="recovery_final",
                )
                recovery_pass_used = True
                visual_recovery_hints = self._parse_visual_recovery_hints(
                    payload.get("visual_recovery_hints")
                )
            except LlmRuntimeError as exc:
                if self._should_fallback_to_heuristic(error=exc):
                    llm_error_fallback_used = True
                    llm_error_fallback_reason = (
                        "llm_navigation_perception_recovery_pass_failed; "
                        "kept_initial_llm_payload"
                    )
                    llm_error_details = {
                        "error_class": exc.error_class,
                        "message": exc.message,
                        "retryable": exc.retryable,
                    }
                else:
                    raise

        self._emit_debug_io(
            request=request,
            inspection=inspection,
            llm_request_debug=llm_request_debug,
            llm_response_payload=payload,
        )

        metadata = inspection.get("metadata") or {}
        metadata = metadata if isinstance(metadata, dict) else {}

        request_metadata = request.metadata if isinstance(request.metadata, dict) else {}
        current_node_can_revalidate = request_metadata.get("current_node_can_revalidate")
        current_node_validation_status = str(
            request_metadata.get("current_node_validation_status") or ""
        ).strip() or None
        current_node_validation_reason = str(
            request_metadata.get("current_node_validation_reason") or ""
        ).strip() or None

        raw_candidates = list(inspection.get("candidates") or [])
        raw_search_targets = list(inspection.get("search_targets") or [])

        candidate_count = int(
            metadata.get("candidate_count") or len(raw_candidates)
        )
        search_target_count = int(
            metadata.get("search_target_count") or len(raw_search_targets)
        )
        search_capability_available = search_target_count > 0

        observed_candidates = self._build_observed_candidates(inspection)
        curated_candidates = tuple(
            CandidateObservation(
                url=str(item.get("url") or "").strip(),
                label=str(item.get("label") or "").strip(),
                score=float(item.get("score") or 0.0),
                rationale=str(item.get("rationale") or "").strip(),
                source_kind=(str(item.get("source_kind") or "").strip() or None),
                supports_condition_labels=tuple(
                    str(value).strip()
                    for value in (item.get("supports_condition_labels") or [])
                    if str(value).strip()
                ),
                target_document_kind_match=(
                    str(item.get("target_document_kind_match") or "").strip() or None
                ),
                temporal_match=tuple(
                    str(value).strip()
                    for value in (item.get("temporal_match") or [])
                    if str(value).strip()
                ),
                progress_likelihood=(
                    str(item.get("progress_likelihood") or "").strip() or None
                ),
                is_intra_page_anchor=(
                    bool(item.get("is_intra_page_anchor"))
                    if item.get("is_intra_page_anchor") is not None
                    else None
                ),
            )
            for item in payload.get("curated_candidates") or []
            if str(item.get("url") or "").strip()
        )

        recommended_next_step = payload.get("recommended_next_step")
        goal_slice_exhausted = payload.get("goal_slice_exhausted")
        goal_slice_exhaustion_reason = (
            str(payload.get("goal_slice_exhaustion_reason") or "").strip() or None
        )

        # If search targets exist, they count as local progress only when they are actually usable.
        # The LLM prompt is expected to discriminate between strategic search entrypoints and
        # irrelevant same-host search boxes on irrelevant hosts.
        if search_capability_available:
            if not recommended_next_step:
                recommended_next_step = "search_with_text"
            elif recommended_next_step == "backtrack_or_use_recoverable_choice_points":
                recommended_next_step = "search_with_text"

            if goal_slice_exhausted is True:
                goal_slice_exhausted = False
                goal_slice_exhaustion_reason = (
                    "search_targets_available_prevent_local_exhaustion"
                )

        # Clamp: if local state already says current evidence should not be revalidated,
        # do not allow perception to keep pushing validate_current_content.
        if (
            current_node_can_revalidate is False
            and recommended_next_step == "validate_current_content"
        ):
            if search_capability_available:
                recommended_next_step = "search_with_text"
            elif curated_candidates:
                recommended_next_step = None
            else:
                recommended_next_step = "backtrack_or_use_recoverable_choice_points"

        return NavigationPerceptionResult(
            status=payload["status"],
            summary=str(payload["summary"]),
            confidence=float(payload["confidence"]),
            recommended_next_step=recommended_next_step,
            layout_kind=payload.get("layout_kind"),
            visible_candidate_count=candidate_count,
            navigation_frame_detected=payload.get("navigation_frame_detected"),
            content_frame_detected=payload.get("content_frame_detected"),
            produced_meaningful_delta=payload.get("produced_meaningful_delta"),
            goal_slice_exhausted=goal_slice_exhausted,
            goal_slice_exhaustion_reason=goal_slice_exhaustion_reason,
            immediate_condition_gain=(
                int(payload.get("immediate_condition_gain"))
                if payload.get("immediate_condition_gain") is not None
                else None
            ),
            best_immediate_condition_labels=tuple(
                str(value).strip()
                for value in (payload.get("best_immediate_condition_labels") or [])
                if str(value).strip()
            ),
            strategic_return_suggested=payload.get("strategic_return_suggested"),
            strategic_return_reason=(
                str(payload.get("strategic_return_reason") or "").strip() or None
            ),
            strategic_return_priority=(
                float(payload.get("strategic_return_priority"))
                if payload.get("strategic_return_priority") is not None
                else None
            ),
            current_node_goal_match=self._parse_current_node_goal_match(
                payload.get("current_node_goal_match")
            ),
            visual_recovery_hints=visual_recovery_hints,
            top_candidate_observations=curated_candidates,
            observed_candidates=observed_candidates,
            metadata={
                "final_url": inspection.get("final_url"),
                "title": inspection.get("title"),
                "candidate_count": candidate_count,
                "search_target_count": search_target_count,
                "search_capability_available": search_capability_available,
                "used_prefetched_inspection": used_prefetched,
                "inspection_source_kind": inspection_source_kind,
                "screenshot_included": bool(inspection.get("screenshot_base64")),
                "llm_multimodal_fallback_used": fallback_without_screenshot_used,
                "llm_error_fallback_used": llm_error_fallback_used,
                "llm_error_fallback_reason": llm_error_fallback_reason,
                "llm_error_fallback_details": llm_error_details,
                "llm_visual_recovery_pass_used": recovery_pass_used,
                "llm_visual_recovery_hint_count": len(visual_recovery_hints),
                "llm_visual_recovery_candidate_count": len(recovery_candidates),
                "current_node_can_revalidate": current_node_can_revalidate,
                "current_node_validation_status": current_node_validation_status,
                "current_node_validation_reason": current_node_validation_reason,
                "llm_navigation_perception": payload,
                "llm_navigation_perception_request": (
                    llm_request_debug if self._settings.debug_payload_io else None
                ),
                "llm_navigation_perception_recovery_request": (
                    recovery_request_debug if self._settings.debug_payload_io else None
                ),
            },
        )

    @staticmethod
    def _should_fallback_to_heuristic(*, error: LlmRuntimeError) -> bool:
        if error.error_class in {"UnexpectedModelBehavior", "APITimeoutError", "APIConnectionError"}:
            return True
        lowered = str(error.message or "").lower()
        return (
            "invalid response from openai chat completions endpoint" in lowered
            or "validation errors for chatcompletion" in lowered
            or "provider returned error" in lowered
        )

    def _fallback_result_from_inspection(
        self,
        *,
        request: NavigationPerceptionRequest,
        inspection: dict[str, Any],
        reason: str,
        error: LlmRuntimeError,
    ) -> NavigationPerceptionResult:
        metadata = inspection.get("metadata") or {}
        metadata = metadata if isinstance(metadata, dict) else {}

        candidates = inspection.get("candidates") or []
        search_targets = inspection.get("search_targets") or []

        candidate_count = int(metadata.get("candidate_count") or len(candidates))
        search_target_count = int(metadata.get("search_target_count") or len(search_targets))
        search_capability_available = search_target_count > 0

        frame_count = int(metadata.get("frame_count") or 1)
        non_main_frame_count = int(
            metadata.get("non_main_frame_count") or max(frame_count - 1, 0)
        )
        content_present = bool(
            metadata.get("content_present") or inspection.get("text_excerpt") or inspection.get("content")
        )

        used_prefetched = bool(metadata.get("used_prefetched_inspection"))
        inspection_source_kind = str(
            metadata.get("inspection_source_kind") or ""
        ).strip() or "unknown"

        top_candidate_observations = self._heuristic_curate_candidate_observations(
            candidates=candidates,
            request=request,
        )
        observed_candidates = self._build_observed_candidates(inspection)

        layout_kind = classify_layout(
            candidate_count=candidate_count,
            non_main_frame_count=non_main_frame_count,
            content_present=content_present,
        )
        status = (
            "analyzed"
            if candidate_count > 0 or content_present or non_main_frame_count > 0 or search_capability_available
            else "inconclusive"
        )

        recommended_next_step = self._recommend_next_step_from_local_state(
            candidate_count=candidate_count,
            search_target_count=search_target_count,
            content_present=content_present,
            non_main_frame_count=non_main_frame_count,
        )

        summary = (
            "fallback=browser_heuristic; "
            + build_summary(
                layout_kind=layout_kind,
                candidate_count=candidate_count,
                content_present=content_present,
                non_main_frame_count=non_main_frame_count,
            )
        )
        if search_capability_available:
            summary += f" | search_targets_detected={search_target_count}"

        goal_slice_exhausted = False if search_capability_available else None
        goal_slice_exhaustion_reason = None if search_capability_available else None

        return NavigationPerceptionResult(
            status=status,
            summary=summary,
            confidence=0.7 if status == "analyzed" else 0.3,
            recommended_next_step=recommended_next_step,
            layout_kind=layout_kind,
            visible_candidate_count=candidate_count,
            navigation_frame_detected=non_main_frame_count > 0 and candidate_count > 0,
            content_frame_detected=content_present,
            produced_meaningful_delta=None,
            goal_slice_exhausted=goal_slice_exhausted,
            goal_slice_exhaustion_reason=goal_slice_exhaustion_reason,
            immediate_condition_gain=None,
            best_immediate_condition_labels=(),
            strategic_return_suggested=None,
            strategic_return_reason=None,
            strategic_return_priority=None,
            current_node_goal_match=None,
            visual_recovery_hints=(),
            top_candidate_observations=top_candidate_observations,
            observed_candidates=observed_candidates,
            metadata={
                "curated_candidate_count": len(top_candidate_observations),
                "final_url": inspection.get("final_url"),
                "title": inspection.get("title"),
                "frame_count": frame_count,
                "non_main_frame_count": non_main_frame_count,
                "content_present": content_present,
                "candidate_count": candidate_count,
                "search_target_count": search_target_count,
                "search_capability_available": search_capability_available,
                "used_prefetched_inspection": used_prefetched,
                "inspection_source_kind": inspection_source_kind,
                "llm_error_fallback_used": True,
                "llm_error_fallback_reason": reason,
                "llm_error_fallback_details": {
                    "error_class": error.error_class,
                    "message": error.message,
                    "retryable": error.retryable,
                },
            },
        )

    def _heuristic_curate_candidate_observations(
        self,
        *,
        candidates: list[dict[str, Any]],
        request: NavigationPerceptionRequest,
        limit: int = 5,
    ) -> tuple[CandidateObservation, ...]:
        return curate_candidate_observations(
            candidates=candidates,
            request=request,
            limit=limit,
        )

    @staticmethod
    def _recommend_next_step_from_local_state(
        *,
        candidate_count: int,
        search_target_count: int,
        content_present: bool,
        non_main_frame_count: int,
    ) -> str | None:
        if candidate_count <= 0 and search_target_count > 0:
            return "search_with_text"

        return recommend_next_step(
            candidate_count=candidate_count,
            content_present=content_present,
            non_main_frame_count=non_main_frame_count,
        )

    @staticmethod
    def _should_retry_without_screenshot(
        *,
        request: NavigationPerceptionRequest,
        inspection: dict[str, Any],
        error: LlmRuntimeError,
    ) -> bool:
        if not request.include_screenshot:
            return False
        if not inspection.get("screenshot_base64"):
            return False
        if error.error_class == "VisionNotSupported":
            return True
        if error.error_class not in {"ModelHTTPError", "BadRequestError", "APIStatusError"}:
            return False
        message = str(error.message or "")
        lowered = message.lower()
        return (
            "status_code: 400" in lowered
            or "input validation error" in lowered
            or "provider returned error" in lowered
        )

    @staticmethod
    def _build_observed_candidates(
        inspection: dict[str, Any],
    ) -> tuple[ObservedCandidate, ...]:
        return build_observed_candidates(inspection)

    @staticmethod
    def _parse_current_node_goal_match(value: object) -> CurrentNodeGoalMatch | None:
        if not isinstance(value, dict):
            return None
        document_family = str(value.get("document_family") or "").strip()
        if not document_family:
            return None
        return CurrentNodeGoalMatch(
            document_family=document_family,
            supports_condition_labels=tuple(
                str(item).strip()
                for item in (value.get("supports_condition_labels") or [])
                if str(item).strip()
            ),
            rationale=(str(value.get("rationale") or "").strip() or None),
            confidence=(
                float(value.get("confidence"))
                if value.get("confidence") is not None
                else None
            ),
            artifact_url=(str(value.get("artifact_url") or "").strip() or None),
        )

    def _parse_visual_recovery_hints(self, value: object) -> tuple[VisualRecoveryHint, ...]:
        if not isinstance(value, list):
            return ()
        hints: list[VisualRecoveryHint] = []
        for item in value[: self._settings.max_visual_recovery_hints]:
            if not isinstance(item, dict):
                continue
            visible_label = str(item.get("visible_label") or "").strip()
            rationale = str(item.get("rationale") or "").strip()
            if not visible_label or not rationale:
                continue
            hints.append(
                VisualRecoveryHint(
                    visible_label=visible_label,
                    rationale=rationale,
                    confidence=(
                        float(item.get("confidence"))
                        if item.get("confidence") is not None
                        else None
                    ),
                    suspected_document_family=(
                        str(item.get("suspected_document_family") or "").strip() or None
                    ),
                    matches_condition_labels=tuple(
                        str(value).strip()
                        for value in (item.get("matches_condition_labels") or [])
                        if str(value).strip()
                    ),
                )
            )
        return tuple(hints)

    def _recover_candidates_from_visual_hints(
        self,
        *,
        inspection: dict[str, Any],
        visual_hints: tuple[VisualRecoveryHint, ...],
    ) -> tuple[dict[str, Any], ...]:
        if not visual_hints:
            return ()
        candidates = list(inspection.get("candidates") or [])
        if not candidates:
            return ()

        initial_prompt_candidates = candidates[: self._settings.max_candidates_to_prompt]
        initial_urls = {
            str(candidate.get("url") or "").strip()
            for candidate in initial_prompt_candidates
            if str(candidate.get("url") or "").strip()
        }

        scored: list[tuple[tuple[int, float, str], dict[str, Any]]] = []
        for candidate in candidates:
            candidate_url = str(candidate.get("url") or "").strip()
            if not candidate_url or candidate_url in initial_urls:
                continue
            haystack = self._candidate_recovery_text(candidate)
            best_score = 0
            best_confidence = 0.0
            for hint in visual_hints:
                hint_tokens = self._tokenize_recovery_hint(hint)
                if not hint_tokens:
                    continue
                matched = sum(1 for token in hint_tokens if token in haystack)
                if matched <= 0:
                    continue
                family_bonus = 0
                suspected_family = self._normalize_recovery_text(
                    hint.suspected_document_family or ""
                )
                if suspected_family:
                    family_tokens = [
                        token
                        for token in suspected_family.replace("_", " ").split()
                        if len(token) >= 3
                    ]
                    family_bonus = sum(1 for token in family_tokens if token in haystack)
                matched += family_bonus
                if matched > best_score:
                    best_score = matched
                    best_confidence = float(hint.confidence or 0.0)
            if best_score <= 0:
                continue
            scored.append(((best_score, best_confidence, candidate_url), candidate))

        scored.sort(key=lambda item: item[0], reverse=True)
        recovered = [
            candidate
            for _, candidate in scored[: self._settings.max_candidates_to_prompt]
        ]
        return tuple(recovered)

    @staticmethod
    def _candidate_recovery_text(candidate: dict[str, Any]) -> str:
        metadata = candidate.get("metadata") or {}
        return " ".join(
            part
            for part in (
                LlmNavigationPerceptionExecutor._normalize_recovery_text(candidate.get("url") or ""),
                LlmNavigationPerceptionExecutor._normalize_recovery_text(candidate.get("text") or ""),
                LlmNavigationPerceptionExecutor._normalize_recovery_text(candidate.get("title") or ""),
                LlmNavigationPerceptionExecutor._normalize_recovery_text(metadata.get("semantic_label") or ""),
                LlmNavigationPerceptionExecutor._normalize_recovery_text(metadata.get("context_text") or ""),
                LlmNavigationPerceptionExecutor._normalize_recovery_text(metadata.get("adjacent_cell_text") or ""),
                LlmNavigationPerceptionExecutor._normalize_recovery_text(metadata.get("table_heading") or ""),
                LlmNavigationPerceptionExecutor._normalize_recovery_text(candidate.get("resource_kind") or ""),
                LlmNavigationPerceptionExecutor._normalize_recovery_text(candidate.get("delivery_mode") or ""),
                LlmNavigationPerceptionExecutor._normalize_recovery_text(metadata.get("resource_kind") or ""),
                LlmNavigationPerceptionExecutor._normalize_recovery_text(metadata.get("delivery_mode") or ""),
            )
            if part
        )

    @staticmethod
    def _tokenize_recovery_hint(hint: VisualRecoveryHint) -> tuple[str, ...]:
        tokens: list[str] = []
        for part in (
            hint.visible_label,
            hint.suspected_document_family or "",
            " ".join(hint.matches_condition_labels),
            hint.rationale,
        ):
            normalized = LlmNavigationPerceptionExecutor._normalize_recovery_text(part)
            for token in normalized.replace("_", " ").split():
                if len(token) >= 3 and token not in tokens:
                    tokens.append(token)
        return tuple(tokens)

    @staticmethod
    def _normalize_recovery_text(value: object) -> str:
        raw = str(value or "").strip().lower()
        decomposed = unicodedata.normalize("NFKD", raw)
        return "".join(
            ch if ch.isalnum() or ch in {"_", " "} else " "
            for ch in decomposed
            if not unicodedata.combining(ch)
        )

    def _build_final_prompt_candidates(
        self,
        *,
        inspection: dict[str, Any],
        recovered_candidates: tuple[dict[str, Any], ...],
    ) -> tuple[dict[str, Any], ...]:
        base_candidates = list(inspection.get("candidates") or [])
        prompt_candidates: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for candidate in recovered_candidates:
            candidate_url = str(candidate.get("url") or "").strip()
            if not candidate_url or candidate_url in seen_urls:
                continue
            prompt_candidates.append(candidate)
            seen_urls.add(candidate_url)

        for candidate in base_candidates:
            candidate_url = str(candidate.get("url") or "").strip()
            if not candidate_url or candidate_url in seen_urls:
                continue
            prompt_candidates.append(candidate)
            seen_urls.add(candidate_url)

        return tuple(prompt_candidates[: self._settings.max_candidates_to_prompt])

    def _invoke_llm(
        self,
        *,
        request: NavigationPerceptionRequest,
        inspection: dict[str, Any],
        prompt_candidates: tuple[dict[str, Any], ...] | None,
        recovery_hints: tuple[VisualRecoveryHint, ...],
        pass_label: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        system_prompt = self._system_prompt()
        user_content = self._user_content(
            request=request,
            inspection=inspection,
            prompt_candidates=prompt_candidates,
            recovery_hints=recovery_hints,
            pass_label=pass_label,
        )
        llm_request = LlmRuntimeRequest(
            operation_name="navigation_perception",
            messages=(
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ),
            expected_output_name="navigation_perception_output",
            metadata={
                "prompt_version": self._settings.prompt_version,
                "structured_output_name": "navigation_perception_output",
                "navigation_perception_pass_label": pass_label,
            },
        )
        if (
            self._invoke_llm_use_case is not None
            and self._ledger_run is not None
            and self._ledger_actor is not None
        ):
            response = self._invoke_llm_use_case.execute(
                run=self._ledger_run,
                actor=self._ledger_actor,
                request=llm_request,
                target=self._ledger_target,
                metadata={
                    "prompt_version": self._settings.prompt_version,
                    "structured_output_name": "navigation_perception_output",
                    "navigation_perception_pass_label": pass_label,
                    "navigation_perception_debug_payload_io": self._settings.debug_payload_io,
                },
            )
        else:
            response = self._llm_runtime.invoke(llm_request)

        interaction = getattr(response, "interaction", None)
        if interaction is None:
            raise TypeError("LlmRuntimeResponse does not contain interaction")

        validation = getattr(interaction, "validation", None)
        if not isinstance(validation, dict):
            raise TypeError("LlmRuntimeResponse.interaction.validation must be dict[str, object]")

        payload = validation.get("parsed_response")
        if not isinstance(payload, dict):
            raise TypeError(
                "LlmRuntimeResponse.interaction.validation.parsed_response must be dict[str, object]"
            )

        return payload, self._build_request_debug_payload(
            request=request,
            inspection=inspection,
            system_prompt=system_prompt,
            user_content=user_content,
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are a local web-navigation curator. "
            "You do not decide the agent's global action. "
            "You analyze the local state of a page, its candidates, and its structure, "
            "and you return a structured shortlist of locally plausible candidates for the current goal. "

            "Evaluate all pending conditions at the same time. "
            "Do not bias toward the first condition mentioned in question or goal_summary. "
            "Prioritize pending conditions that can be advanced locally in the fewest steps, not the first one mentioned. "

            "If the current node already offers a plausible local path to satisfy a pending condition, "
            "report it as immediate progress even if another condition appears first in the goal text. "
            "If the current node better satisfies a different condition than the first one, report that as well in "
            "curated_candidates, best_immediate_condition_labels, and immediate_condition_gain. "

            "If the current node itself already fulfills a pending condition, even if it is not a PDF and not downloadable, "
            "return current_node_goal_match with document_family, supports_condition_labels, rationale, and confidence. "
            "If the current node already looks like the final deliverable and the visible local evidence seems sufficient for formal validation, "
            "use recommended_next_step=validate_current_content. "
            "Do not treat current_node_goal_match as a formal goal closure; it only signals that the runtime should hand off to document_validation. "

            "Return immediate_condition_gain as the number of pending conditions that seem resolvable from this node without backtracking, "
            "and best_immediate_condition_labels as the conditions that can best be advanced here. "
            "Prioritize explicit alignment with pending conditions, document type, and temporal constraints. "

            "Do not invent candidates. "
            "If a link is only an intra-page anchor and does not appear to open real progress, mark it as such and lower its priority. "

            "If the screenshot suggests important visible candidates that do not appear in the textual candidate list, "
            "return visual_recovery_hints with visible labels, suspected document family, matched condition labels, and brief rationales "
            "so the runtime can try to recover them from the DOM. "
            "In the final pass, if recovery_hints_applied is provided, combine original and recovered candidates and return a coherent final shortlist. "

            "If this node is a strategic hub worth returning to later for other branches, set strategic_return_suggested=true "
            "with a short reason and numeric priority. "

            "Search-target policy: the existence of search_targets does not automatically mean they are useful. "
            "A local search box only counts as useful progress if it is semantically aligned with the current goal. "
            "Do not recommend search_with_text merely because a same-host search box exists. "
            "If the current host or page is clearly irrelevant to the goal, and the visible search box is only an internal same-host search field "
            "(for example videos, site-local posts, account search, or other irrelevant local discovery), do not treat it as strategic search progress. "
            "In that case prefer candidates if they are useful; otherwise prefer backtrack_or_use_recoverable_choice_points. "

            "If the node is a true search entrypoint relevant to the goal and search_targets are available, "
            "that counts as local progress even if no useful candidates are visible yet. "
            "Do not mark goal_slice_exhausted solely because links are missing if the node is such a search entrypoint. "
            "If search_target_count > 0 and there are no useful visible candidates, you may use recommended_next_step=search_with_text "
            "only when the available search target is actually usable for the goal. "

            "Use backtrack_or_use_recoverable_choice_points only when there are no useful links, no usable search targets, "
            "and additional local refinement would not help. "

            "If request.metadata indicates current_node_can_revalidate=false, do not recommend validate_current_content for the current evidence. "
            "In that case, if local progress is still possible, prioritize candidates, search_with_text, or "
            "backtrack_or_use_recoverable_choice_points depending on the actual local state. "
            "A current_node_goal_match may still be informative, but it must not become validate_current_content if the current evidence has already been consumed."
        )

    def _user_content(
        self,
        *,
        request: NavigationPerceptionRequest,
        inspection: dict[str, Any],
        prompt_candidates: tuple[dict[str, Any], ...] | None,
        recovery_hints: tuple[VisualRecoveryHint, ...],
        pass_label: str,
    ) -> Any:
        metadata = inspection.get("metadata") or {}
        metadata = metadata if isinstance(metadata, dict) else {}

        request_metadata = request.metadata if isinstance(request.metadata, dict) else {}
        current_node_can_revalidate = request_metadata.get("current_node_can_revalidate")
        current_node_validation_status = request_metadata.get("current_node_validation_status")
        current_node_validation_reason = request_metadata.get("current_node_validation_reason")
        current_node_last_matched_condition_ids = tuple(
            str(item).strip()
            for item in (request_metadata.get("current_node_last_matched_condition_ids") or ())
            if str(item).strip()
        )
        current_node_last_evidence_signature = request_metadata.get("current_node_last_evidence_signature")

        candidates = (
            list(prompt_candidates)
            if prompt_candidates is not None
            else list(inspection.get("candidates") or [])
        )
        search_targets = list(inspection.get("search_targets") or [])

        text_excerpt = str(inspection.get("text_excerpt") or inspection.get("content") or "")
        text_excerpt = text_excerpt[: self._settings.text_excerpt_max_chars]
        final_url = str(
            inspection.get("page_url")
            or inspection.get("final_url")
            or request.url
            or ""
        )

        if prompt_candidates is not None:
            deduped: list[dict[str, Any]] = []
            seen_urls: set[str] = set()
            for candidate in candidates:
                url = str(candidate.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                deduped.append(candidate)
                seen_urls.add(url)
            prompt_candidates = deduped[: self._settings.max_candidates_to_prompt]
        else:
            prompt_candidates = select_prompt_candidates(
                candidates=candidates,
                request=request,
                limit=self._settings.max_candidates_to_prompt,
            )

        candidate_lines: list[str] = []
        for index, candidate in enumerate(prompt_candidates, start=1):
            candidate_metadata = candidate.get("metadata") or {}
            candidate_url = str(candidate.get("url") or "").strip()
            label = str(candidate.get("text") or "").strip()
            semantic_label = str(candidate_metadata.get("semantic_label") or "").strip()
            context_text = str(candidate_metadata.get("context_text") or "").strip()
            table_heading = str(candidate_metadata.get("table_heading") or "").strip()
            adjacent_cell_text = str(candidate_metadata.get("adjacent_cell_text") or "").strip()
            resource_kind = str(
                candidate.get("resource_kind") or candidate_metadata.get("resource_kind") or ""
            ).strip()
            delivery_mode = str(
                candidate.get("delivery_mode") or candidate_metadata.get("delivery_mode") or ""
            ).strip()
            candidate_type = str(candidate.get("candidate_type") or "").strip()
            relation = str(candidate.get("relation") or "").strip()
            base_score = candidate.get("score")
            is_intra_page_anchor = self._is_intra_page_anchor(
                final_url=final_url,
                candidate_url=candidate_url,
            )

            candidate_lines.append(
                f"- idx={index} | url={candidate_url} | "
                f"label={label!r} | semantic_label={semantic_label!r} | "
                f"context_text={context_text!r} | table_heading={table_heading!r} | "
                f"adjacent_cell_text={adjacent_cell_text!r} | resource_kind={resource_kind!r} | "
                f"delivery_mode={delivery_mode!r} | candidate_type={candidate_type!r} | "
                f"relation={relation!r} | base_score={base_score!r} | "
                f"is_intra_page_anchor={is_intra_page_anchor}"
            )

        candidate_block = "\n".join(candidate_lines)

        search_target_lines: list[str] = []
        for index, target in enumerate(search_targets, start=1):
            search_target_lines.append(
                f"- idx={index} | "
                f"search_target_id={str(target.get('search_target_id') or '').strip()} | "
                f"tag={str(target.get('tag') or '').strip()!r} | "
                f"input_type={str(target.get('input_type') or '').strip()!r} | "
                f"name={str(target.get('name') or '').strip()!r} | "
                f"id_attr={str(target.get('id_attr') or '').strip()!r} | "
                f"placeholder={str(target.get('placeholder') or '').strip()!r} | "
                f"aria_label={str(target.get('aria_label') or '').strip()!r} | "
                f"label={str(target.get('label') or '').strip()!r} | "
                f"form_action={str(target.get('form_action') or '').strip()!r} | "
                f"same_host={target.get('same_host')!r} | "
                f"confidence={target.get('confidence')!r}"
            )

        search_target_block = "\n".join(search_target_lines)

        text_content = (
            f"pass_label: {pass_label}\n"
            f"goal_summary: {request.goal_summary or request.question}\n"
            f"pending_goal_conditions: {list(request.pending_goal_conditions)}\n"
            f"target_document_kinds: {list(request.target_document_kinds)}\n"
            f"temporal_constraints: {list(request.temporal_constraints)}\n"
            f"question: {request.question}\n"
            f"pattern_hints: {list(request.pattern_hints)}\n"
            f"recovery_hints_applied: {[hint.visible_label for hint in recovery_hints]}\n"
            f"current_node_can_revalidate: {current_node_can_revalidate}\n"
            f"current_node_validation_status: {current_node_validation_status}\n"
            f"current_node_validation_reason: {current_node_validation_reason}\n"
            f"current_node_last_matched_condition_ids: {list(current_node_last_matched_condition_ids)}\n"
            f"current_node_last_evidence_signature: {current_node_last_evidence_signature}\n"
            f"page_url: {final_url}\n"
            f"title: {inspection.get('title') or inspection.get('page_title') or ''}\n"
            f"frame_count: {metadata.get('frame_count')}\n"
            f"non_main_frame_count: {metadata.get('non_main_frame_count')}\n"
            f"content_present: {metadata.get('content_present')}\n"
            f"candidate_count: {metadata.get('candidate_count') or len(candidates)}\n"
            f"search_target_count: {metadata.get('search_target_count') or len(search_targets)}\n"
            f"search_capability_available: {bool(search_targets)}\n"
            f"prompt_candidate_count: {len(prompt_candidates)}\n"
            f"screenshot_included: {bool(inspection.get('screenshot_base64'))}\n"
            f"text_excerpt:\n{text_excerpt}\n"
            f"search_targets:\n{search_target_block}\n"
            f"candidates:\n{candidate_block}"
        )

        screenshot_base64 = str(inspection.get("screenshot_base64") or "").strip()
        screenshot_mime_type = (
            str(inspection.get("screenshot_mime_type") or "image/png").strip() or "image/png"
        )

        if not screenshot_base64:
            return text_content

        return [
            {
                "type": "text",
                "text": text_content,
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{screenshot_mime_type};base64,{screenshot_base64}",
                    "detail": self._settings.image_detail,
                },
            },
        ]

    @staticmethod
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

    def _build_request_debug_payload(
        self,
        *,
        request: NavigationPerceptionRequest,
        inspection: dict[str, Any],
        system_prompt: str,
        user_content: Any,
    ) -> dict[str, Any]:
        screenshot_base64 = str(inspection.get("screenshot_base64") or "").strip()
        screenshot_mime_type = (
            str(inspection.get("screenshot_mime_type") or "image/png").strip() or "image/png"
        )
        screenshot_data_url = None
        if screenshot_base64:
            screenshot_data_url = f"data:{screenshot_mime_type};base64,{screenshot_base64}"

        inspection_metadata = inspection.get("metadata") or {}
        inspection_metadata = (
            inspection_metadata if isinstance(inspection_metadata, dict) else {}
        )

        return {
            "request": asdict(request),
            "system_prompt": system_prompt,
            "user_content": user_content,
            "inspection_summary": {
                "final_url": inspection.get("final_url") or inspection.get("page_url"),
                "title": inspection.get("title") or inspection.get("page_title"),
                "candidate_count": len(inspection.get("candidates") or []),
                "search_target_count": len(inspection.get("search_targets") or []),
                "frame_count": inspection_metadata.get("frame_count"),
                "non_main_frame_count": inspection_metadata.get("non_main_frame_count"),
                "content_present": inspection_metadata.get("content_present"),
                "screenshot_included": bool(screenshot_base64),
                "screenshot_mime_type": screenshot_mime_type if screenshot_base64 else None,
                "used_prefetched_inspection": bool(
                    inspection_metadata.get("used_prefetched_inspection")
                ),
                "inspection_source_kind": (
                    str(inspection_metadata.get("inspection_source_kind") or "").strip()
                    or "unknown"
                ),
                "screenshot_data_url_preview": (
                    None if screenshot_data_url is None else screenshot_data_url[:160] + "..."
                ),
            },
        }

    def _emit_debug_io(
        self,
        *,
        request: NavigationPerceptionRequest,
        inspection: dict[str, Any],
        llm_request_debug: dict[str, Any],
        llm_response_payload: dict[str, Any],
    ) -> None:
        if not self._settings.debug_payload_io:
            return

        print(
            "[navigation_perception.debug] outgoing request:",
            json.dumps(llm_request_debug, ensure_ascii=False, indent=2, default=str),
            file=sys.stderr,
            flush=True,
        )
        print(
            "[navigation_perception.debug] incoming response:",
            json.dumps(llm_response_payload, ensure_ascii=False, indent=2, default=str),
            file=sys.stderr,
            flush=True,
        )

        dump_dir = self._settings.debug_payload_dump_dir
        if not dump_dir:
            return

        screenshot_path = self._dump_debug_payloads(
            dump_dir=dump_dir,
            request=request,
            inspection=inspection,
            llm_request_debug=llm_request_debug,
            llm_response_payload=llm_response_payload,
        )
        if screenshot_path is not None:
            llm_request_debug["inspection_summary"]["screenshot_path"] = str(screenshot_path)
            llm_request_debug["user_content"] = self._redact_user_content_image_data(
                llm_request_debug.get("user_content"),
                screenshot_path=str(screenshot_path),
            )
            request_path = Path(dump_dir) / f"{self._safe_debug_stem(request)}_request.json"
            request_path.write_text(
                json.dumps(llm_request_debug, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

    def _dump_debug_payloads(
        self,
        *,
        dump_dir: str,
        request: NavigationPerceptionRequest,
        inspection: dict[str, Any],
        llm_request_debug: dict[str, Any],
        llm_response_payload: dict[str, Any],
    ) -> Path | None:
        base_dir = Path(dump_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        stem = self._safe_debug_stem(request)
        request_path = base_dir / f"{stem}_request.json"
        response_path = base_dir / f"{stem}_response.json"

        request_path.write_text(
            json.dumps(llm_request_debug, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        response_path.write_text(
            json.dumps(llm_response_payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        screenshot_base64 = str(inspection.get("screenshot_base64") or "").strip()
        if screenshot_base64:
            screenshot_mime_type = (
                str(inspection.get("screenshot_mime_type") or "image/png").strip() or "image/png"
            )
            extension = self._mime_extension(screenshot_mime_type)
            screenshot_path = base_dir / f"{stem}_screenshot.{extension}"
            screenshot_path.write_bytes(base64.b64decode(screenshot_base64))
            return screenshot_path

        return None

    @staticmethod
    def _safe_debug_stem(request: NavigationPerceptionRequest) -> str:
        raw = str(request.node_id or request.url or "navigation_perception").strip()
        cleaned = "".join(ch if ch.isalnum() else "_" for ch in raw)
        cleaned = cleaned.strip("_") or "navigation_perception"
        return cleaned[:80]

    @staticmethod
    def _mime_extension(mime_type: str) -> str:
        lowered = mime_type.lower()
        if lowered == "image/jpeg":
            return "jpg"
        if lowered == "image/webp":
            return "webp"
        return "png"

    @staticmethod
    def _redact_user_content_image_data(user_content: Any, *, screenshot_path: str) -> Any:
        if not isinstance(user_content, list):
            return user_content
        redacted: list[dict[str, Any]] = []
        for item in user_content:
            if not isinstance(item, dict):
                redacted.append(item)
                continue
            if item.get("type") != "image_url":
                redacted.append(item)
                continue
            image_url = item.get("image_url")
            if not isinstance(image_url, dict):
                redacted.append(item)
                continue
            redacted.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"<redacted; see screenshot_path={screenshot_path}>",
                        "detail": image_url.get("detail"),
                    },
                }
            )
        return redacted