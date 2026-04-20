from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NavigationAgentState:
    page_stack: list[tuple[str, int]] = field(default_factory=list)
    visited_pages: set[str] = field(default_factory=set)
    inspected_pages: set[str] = field(default_factory=set)
    followed_candidate_urls: set[str] = field(default_factory=set)
    rejected_candidate_urls: set[str] = field(default_factory=set)
    downloaded_candidate_urls: set[str] = field(default_factory=set)
    opened_artifact_urls: set[str] = field(default_factory=set)
    state_counts: dict[tuple[str, str, str, tuple[str, ...], tuple[str, ...]], int] = field(
        default_factory=dict
    )
    llm_decision_count: int = 0
    max_page_hops: int = 3
    max_pages: int = 8
    max_llm_decisions: int = 12
    max_repeated_state: int = 3

    def current_page(self) -> tuple[str, int]:
        if not self.page_stack:
            raise IndexError("page_stack is empty")
        return self.page_stack[-1]

    def reset_to_entry(self, entry_url: str) -> None:
        normalized = _normalize_text(entry_url)
        self.page_stack = [(normalized, 0)] if normalized else []
        if normalized:
            self.visited_pages.add(normalized)

    def push_page(self, url: str, hop_depth: int) -> None:
        normalized = _normalize_text(url)
        if not normalized:
            return
        self.page_stack.append((normalized, hop_depth))
        self.visited_pages.add(normalized)

    def pop_page(self) -> bool:
        if len(self.page_stack) > 1:
            self.page_stack.pop()
            return True
        return False

    def has_visited(self, page_url: str) -> bool:
        normalized = _normalize_text(page_url)
        return normalized in self.visited_pages

    def has_inspected(self, page_url: str) -> bool:
        normalized = _normalize_text(page_url)
        return normalized in self.inspected_pages

    def should_skip_page(self, page_url: str) -> bool:
        normalized = _normalize_text(page_url)
        return normalized in self.inspected_pages and len(self.page_stack) > 1

    def can_visit(self, page_url: str, hop_depth: int) -> bool:
        normalized = _normalize_text(page_url)
        if not normalized:
            return False
        if normalized in self.visited_pages:
            return False
        if hop_depth > self.max_page_hops:
            return False
        if len(self.visited_pages) >= self.max_pages:
            return False
        return True

    def mark_page_inspected(self, page_url: str) -> None:
        normalized = _normalize_text(page_url)
        if normalized:
            self.inspected_pages.add(normalized)

    def register_state(
        self,
        page_url: str,
        candidates: list[dict[str, object]],
        inspection_metadata: dict[str, object] | None = None,
        *,
        state_tag: str = "",
    ) -> int:
        signature = self._state_signature(
            page_url=page_url,
            candidates=candidates,
            inspection_metadata=inspection_metadata,
            state_tag=state_tag,
        )
        count = self.state_counts.get(signature, 0) + 1
        self.state_counts[signature] = count
        return count

    def increment_llm_decisions(self) -> int:
        self.llm_decision_count += 1
        return self.llm_decision_count

    def is_candidate_eligible(self, candidate_url: str | None) -> bool:
        normalized = _normalize_text(candidate_url)
        if not normalized:
            return False
        return (
            normalized not in self.followed_candidate_urls
            and normalized not in self.rejected_candidate_urls
        )

    def mark_candidate_followed(self, candidate_url: str) -> None:
        normalized = _normalize_text(candidate_url)
        if normalized:
            self.followed_candidate_urls.add(normalized)

    def mark_candidate_rejected(self, candidate_url: str) -> None:
        normalized = _normalize_text(candidate_url)
        if normalized:
            self.rejected_candidate_urls.add(normalized)

    def mark_candidate_downloaded(self, candidate_url: str) -> None:
        normalized = _normalize_text(candidate_url)
        if normalized:
            self.downloaded_candidate_urls.add(normalized)

    def mark_artifact_opened(self, artifact_url: str) -> None:
        normalized = _normalize_text(artifact_url)
        if normalized:
            self.opened_artifact_urls.add(normalized)

    def can_download(self, candidate_url: str | None) -> bool:
        normalized = _normalize_text(candidate_url)
        if not normalized:
            return False
        return normalized not in self.downloaded_candidate_urls

    def can_open_artifact(self, artifact_url: str | None) -> bool:
        normalized = _normalize_text(artifact_url)
        if not normalized:
            return False
        return normalized not in self.opened_artifact_urls

    @staticmethod
    def _state_signature(
        page_url: str,
        candidates: list[dict[str, object]],
        inspection_metadata: dict[str, object] | None = None,
        *,
        state_tag: str = "",
    ) -> tuple[str, str, str, tuple[str, ...], tuple[str, ...]]:
        normalized_page_url = _normalize_text(page_url)
        metadata = inspection_metadata or {}

        urls = tuple((_candidate_str(candidate, "url") or "") for candidate in candidates[:10])
        candidate_page_urls = tuple(
            (_candidate_str(candidate, "page_url") or normalized_page_url)
            for candidate in candidates[:10]
        )
        dominant_frame_url = _metadata_str(metadata, "dominant_frame_url") or normalized_page_url

        return (
            normalized_page_url,
            dominant_frame_url,
            state_tag,
            urls,
            candidate_page_urls,
        )


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _candidate_str(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    normalized = _normalize_text(value)
    return normalized or None


def _metadata_str(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    normalized = _normalize_text(value)
    return normalized or None

