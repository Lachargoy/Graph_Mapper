from __future__ import annotations
#graph_mapper_agent/application/services/decision/decider.py
from dataclasses import dataclass

from graph_mapper_agent.application.services.candidate_ranker import (
    CandidateRanker,
)
from graph_mapper_agent.application.services.candidate_selector import (
    CandidateSelector,
)
from graph_mapper_agent.application.services.decision.contracts import (
    GraphMapperDecision,
)
from graph_mapper_agent.application.services.decision.heuristic import (
    HeuristicDecisionEngine,
)
from graph_mapper_agent.application.services.decision.llm_use_case import (
    GraphMapperDecisionLlmUseCase,
)
from graph_mapper_agent.application.services.decision.llm_pipeline import (
    decide_llm,
)
from graph_mapper_agent.domain.view import NodeView
from graph_mapper_agent.ledger.domain.actor_kind import ActorKind
from graph_mapper_agent.ledger.domain.run_correlation import (
    RunCorrelation,
)
from graph_mapper_agent.ledger.domain.target_ref import TargetRef


@dataclass(slots=True)
class GraphMapperDecider:
    candidate_selector: CandidateSelector
    candidate_ranker: CandidateRanker
    llm_use_case: GraphMapperDecisionLlmUseCase | None = None

    def decide(
        self,
        node_view: NodeView,
        *,
        run: RunCorrelation | None = None,
        actor: ActorKind | None = None,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> GraphMapperDecision:
        if self.llm_use_case is None:
            return HeuristicDecisionEngine(
                candidate_selector=self.candidate_selector,
                candidate_ranker=self.candidate_ranker,
            ).decide(node_view)

        return decide_llm(
            llm_use_case=self.llm_use_case,
            node_view=node_view,
            run=run,
            actor=actor,
            target=target,
            metadata=metadata or {},
        )


__all__ = ["GraphMapperDecider"]
