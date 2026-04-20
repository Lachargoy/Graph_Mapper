from __future__ import annotations

from dataclasses import dataclass

from graph_mapper_agent.domain.view import NodeViewCandidate


@dataclass(slots=True, frozen=True)
class RankedCandidate:
    candidate: NodeViewCandidate
    effective_score: float


@dataclass(slots=True, frozen=True)
class CandidateRanker:
    repetition_penalty: float = 0.25
    same_host_bonus: float = 0.05
    bridge_bonus: float = 0.10
    direct_artifact_bonus: float = 0.12
    table_context_bonus: float = 0.08

    def rank(
        self,
        candidates: tuple[NodeViewCandidate, ...],
    ) -> tuple[RankedCandidate, ...]:
        ranked: list[RankedCandidate] = []

        for candidate in candidates:
            score = float(candidate.base_score or 0.0)

            score -= candidate.attempt_count * self.repetition_penalty

            if candidate.hint == "same_host_candidate":
                score += self.same_host_bonus

            if candidate.reason == "bridge_candidate":
                score += self.bridge_bonus

            if candidate.reason == "direct_artifact_candidate":
                score += self.direct_artifact_bonus

            if candidate.hint == "table_context_candidate":
                score += self.table_context_bonus

            ranked.append(
                RankedCandidate(
                    candidate=candidate,
                    effective_score=score,
                )
            )

        ranked.sort(
            key=lambda item: (
                -item.effective_score,
                item.candidate.attempt_count,
                item.candidate.label.lower(),
            )
        )
        return tuple(ranked)
