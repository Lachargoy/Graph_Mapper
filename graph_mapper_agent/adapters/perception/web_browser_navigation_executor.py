from __future__ import annotations
#./adapters/perception/web_browser_navigation_executor.py
from dataclasses import dataclass
from typing import Any

from graph_mapper_agent.adapters.web_browser.tool import (
    WebBrowserTool,
)
from graph_mapper_agent.domain.graph import ObservedCandidate
from graph_mapper_agent.application.navigation_perception.models import (
    CandidateObservation,
    NavigationPerceptionRequest,
    NavigationPerceptionResult,
)


@dataclass(frozen=True, slots=True)
class WebBrowserNavigationPerceptionExecutorSettings:
    max_candidates_to_inspect: int = 600


class WebBrowserNavigationPerceptionExecutor:
    def __init__(
        self,
        *,
        web_browser_tool: WebBrowserTool,
        settings: WebBrowserNavigationPerceptionExecutorSettings | None = None,
    ) -> None:
        self._web_browser_tool = web_browser_tool
        self._settings = settings or WebBrowserNavigationPerceptionExecutorSettings()

    def perceive(self, request: NavigationPerceptionRequest) -> NavigationPerceptionResult:
        prefetched = self._resolve_prefetched_inspection(request)

        if prefetched is None and not request.url:
            raise ValueError('navigation perception requires a target URL or prefetched inspection')

        if prefetched is not None:
            inspection = prefetched
            cands_count = len(list(inspection.get('candidates') or []))
            print(
                "[navigation_perception.executor] using prefetched inspection snapshot "
                f"url={inspection.get('page_url') or inspection.get('final_url') or request.url!r} "
                f"title={inspection.get('title')!r} "
                f"candidate_count={cands_count}",
                flush=True,
            )
            if cands_count > 0:
                print(f"[navigation_perception.executor] primer candidato snapshot: {inspection.get('candidates')[0].get('url')!r}", flush=True)
        else:
            print(
                "[navigation_perception.executor] live inspect_page "
                f"url={request.url!r}",
                flush=True,
            )
            inspection = self._web_browser_tool.inspect_page(
                {
                    'entry_url': request.url,
                    'goal': request.question,
                    'metadata': request.metadata,
                    'max_candidates': self._settings.max_candidates_to_inspect,
                }
            )

        metadata = inspection.get('metadata') or {}
        candidates = inspection.get('candidates') or []
        candidate_count = int(metadata.get('candidate_count') or len(candidates))
        frame_count = int(metadata.get('frame_count') or 1)
        non_main_frame_count = int(metadata.get('non_main_frame_count') or max(frame_count - 1, 0))
        content_present = bool(metadata.get('content_present') or inspection.get('text_excerpt') or inspection.get('content'))

        top_candidate_observations = self._curate_candidate_observations(
            candidates=candidates,
            request=request,
        )
        observed_candidates = self._build_observed_candidates(candidates)

        layout_kind = self._classify_layout(
            candidate_count=candidate_count,
            non_main_frame_count=non_main_frame_count,
            content_present=content_present,
        )
        status = 'analyzed' if candidate_count > 0 or content_present or non_main_frame_count > 0 else 'inconclusive'
        recommended_next_step = self._recommend_next_step(
            candidate_count=candidate_count,
            content_present=content_present,
            non_main_frame_count=non_main_frame_count,
        )
        summary = self._build_summary(
            layout_kind=layout_kind,
            candidate_count=candidate_count,
            content_present=content_present,
            non_main_frame_count=non_main_frame_count,
        )

        return NavigationPerceptionResult(
            status=status,
            summary=summary,
            confidence=0.82 if status == 'analyzed' else 0.35,
            recommended_next_step=recommended_next_step,
            layout_kind=layout_kind,
            visible_candidate_count=candidate_count,
            navigation_frame_detected=non_main_frame_count > 0 and candidate_count > 0,
            content_frame_detected=content_present,
            top_candidate_observations=top_candidate_observations,
            observed_candidates=observed_candidates,
            metadata={
                'curated_candidate_count': len(top_candidate_observations),
                'final_url': inspection.get('final_url'),
                'title': inspection.get('title'),
                'frame_count': frame_count,
                'non_main_frame_count': non_main_frame_count,
                'content_present': content_present,
                'used_prefetched_inspection': prefetched is not None,
            },
        )

    @staticmethod
    def _resolve_prefetched_inspection(
        request: NavigationPerceptionRequest,
    ) -> dict[str, object] | None:
        metadata = request.metadata if isinstance(request.metadata, dict) else {}

        for key in (
            'prefetched_observation',
            'prefetched_inspection',
            'frozen_snapshot',
            'inspection_snapshot',
            'search_snapshot',
        ):
            value = metadata.get(key)
            if isinstance(value, dict) and value:
                print(f"[debug.np.adapter] snapshot encontrado con llave {key!r} candidate_count={len(list(value.get('candidates') or []))}", flush=True)
                return dict(value)

        print(f"[debug.np.adapter] no se encontro prefetched snapshot en metadata. Llaves disponibles: {list(metadata.keys())!r}", flush=True)
        return None

    @staticmethod
    def _build_observed_candidates(candidates: list[dict]) -> tuple[ObservedCandidate, ...]:
        observed: list[ObservedCandidate] = []
        for candidate in candidates:
            candidate_url = str(candidate.get('url') or '').strip()
            if not candidate_url:
                continue
            metadata = candidate.get('metadata') or {}
            source_frame = (
                str(candidate.get('source_frame') or '').strip()
                or str(metadata.get('source_frame') or '').strip()
                or None
            )
            observed.append(
                ObservedCandidate(
                    target_url=candidate_url,
                    label=WebBrowserNavigationPerceptionExecutor._candidate_label(candidate, metadata),
                    relation=str(candidate.get('relation') or 'unknown'),
                    candidate_type=str(candidate.get('candidate_type') or 'unknown'),
                    resource_kind=(
                        str(candidate.get('resource_kind') or metadata.get('resource_kind') or '').strip() or None
                    ),
                    delivery_mode=(
                        str(candidate.get('delivery_mode') or metadata.get('delivery_mode') or '').strip() or None
                    ),
                    semantic_label=(
                        str(candidate.get('semantic_label') or metadata.get('semantic_label') or '').strip() or None
                    ),
                    table_heading=(
                        str(candidate.get('table_heading') or metadata.get('table_heading') or '').strip() or None
                    ),
                    adjacent_cell_text=(
                        str(candidate.get('adjacent_cell_text') or metadata.get('adjacent_cell_text') or '').strip() or None
                    ),
                    same_host=(
                        candidate.get('same_host')
                        if candidate.get('same_host') is not None
                        else metadata.get('same_host')
                    ),
                    base_score=float(candidate.get('score') or 0.0),
                    source_channel='navigation_perception',
                    source_frame=source_frame,
                    metadata=dict(metadata),
                )
            )
        return tuple(observed)

    @staticmethod
    def _classify_layout(
        *,
        candidate_count: int,
        non_main_frame_count: int,
        content_present: bool,
    ) -> str:
        if non_main_frame_count > 0 and candidate_count > 0 and content_present:
            return 'split_navigation_content'
        if candidate_count > 0 and content_present:
            return 'candidate_index_with_content'
        if candidate_count > 0:
            return 'candidate_index'
        if content_present:
            return 'content_only'
        return 'unknown'

    @staticmethod
    def _recommend_next_step(
        *,
        candidate_count: int,
        content_present: bool,
        non_main_frame_count: int,
    ) -> str:
        if non_main_frame_count > 0 and candidate_count > 0:
            return 'use_navigation_frame_candidates'
        if candidate_count > 0:
            return 'inspect_candidates'
        if content_present:
            return 'inspect_content'
        return 'retry_or_expand_navigation_probe'

    @staticmethod
    def _build_summary(
        *,
        layout_kind: str,
        candidate_count: int,
        content_present: bool,
        non_main_frame_count: int,
    ) -> str:
        return (
            f'layout={layout_kind}; candidates={candidate_count}; '
            f'content_present={content_present}; non_main_frames={non_main_frame_count}'
        )

    def _curate_candidate_observations(
        self,
        *,
        candidates: list[dict],
        request: NavigationPerceptionRequest,
        limit: int = 5,
    ) -> tuple[CandidateObservation, ...]:
        goal_tokens = self._tokenize_goal(request.question, request.pattern_hints)
        scored: list[tuple[tuple[int, float, str], CandidateObservation]] = []

        for candidate in candidates:
            candidate_url = str(candidate.get('url') or '').strip()
            metadata = candidate.get('metadata') or {}
            label = self._candidate_label(candidate, metadata)
            source_kind = self._candidate_source_kind(candidate, metadata)
            candidate_tokens = self._tokenize_candidate(candidate_url, label, metadata)
            matched_tokens = tuple(sorted(goal_tokens & candidate_tokens))
            match_count = len(matched_tokens)
            base_score = float(candidate.get('score') or 0.0)
            final_score = float(match_count * 10) + base_score
            rationale = (
                f"goal_token_overlap={','.join(matched_tokens)}"
                if matched_tokens
                else 'fallback_visibility_candidate'
            )
            observation = CandidateObservation(
                url=candidate_url,
                label=label,
                score=final_score,
                rationale=rationale,
                source_kind=source_kind,
            )
            scored.append(((match_count, final_score, label.lower()), observation))

        scored.sort(key=lambda item: item[0], reverse=True)
        return tuple(observation for _, observation in scored[:limit])

    @staticmethod
    def _candidate_label(candidate: dict, metadata: dict) -> str:
        return (
            str(candidate.get('text') or '').strip()
            or str(metadata.get('semantic_label') or '').strip()
            or str(metadata.get('aria_label') or '').strip()
            or str(candidate.get('url') or '').strip()
        )

    @staticmethod
    def _candidate_source_kind(candidate: dict, metadata: dict) -> str | None:
        for key in ('resource_kind', 'delivery_mode', 'candidate_type', 'relation'):
            value = str(candidate.get(key) or metadata.get(key) or '').strip()
            if value:
                return value
        return None

    @staticmethod
    def _tokenize_goal(question: str, pattern_hints: tuple[str, ...]) -> set[str]:
        parts = [question, *pattern_hints]
        return WebBrowserNavigationPerceptionExecutor._tokenize_parts(*parts)

    @staticmethod
    def _tokenize_candidate(candidate_url: str, label: str, metadata: dict) -> set[str]:
        parts = [
            candidate_url,
            label,
            str(metadata.get('semantic_label') or ''),
            str(metadata.get('context_text') or ''),
            str(metadata.get('adjacent_cell_text') or ''),
        ]
        return WebBrowserNavigationPerceptionExecutor._tokenize_parts(*parts)

    @staticmethod
    def _tokenize_parts(*parts: str) -> set[str]:
        tokens: set[str] = set()
        for part in parts:
            normalized = ''.join(ch.lower() if ch.isalnum() else ' ' for ch in str(part))
            for token in normalized.split():
                if len(token) >= 3:
                    tokens.add(token)
        return tokens
