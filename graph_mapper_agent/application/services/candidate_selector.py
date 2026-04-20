from __future__ import annotations

from dataclasses import dataclass

from graph_mapper_agent.domain.view import NodeViewCandidate


@dataclass(slots=True, frozen=True)
class CandidateSelector:
    max_attempts_per_edge: int = 2
    allow_terminal_failures: bool = False

    def select(
        self,
        candidates: tuple[NodeViewCandidate, ...],
    ) -> tuple[NodeViewCandidate, ...]:
        selected: list[NodeViewCandidate] = []

        for candidate in candidates:
            if not self.allow_terminal_failures and candidate.status in {
                "failed",
                "blocked",
                "rejected",
            }:
                continue

            if candidate.attempt_count >= self.max_attempts_per_edge:
                continue

            selected.append(candidate)

        return tuple(selected)
