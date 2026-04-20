from __future__ import annotations

from dataclasses import dataclass

from graph_mapper_agent.application.goal_validation.validation_models import (
    GoalValidationPass,
    GoalValidationRequest,
    GoalValidationResult,
)


@dataclass(frozen=True, slots=True)
class GoalValidationPolicy:
    default_window_pages: int = 3

    def next_pass(
        self,
        request: GoalValidationRequest,
        *,
        history: tuple[GoalValidationResult, ...] = (),
    ) -> GoalValidationPass | None:
        if not history:
            return self._initial_pass(request)

        last = history[-1]
        if not last.requests_more_evidence():
            return None
        if not request.escalation_allowed:
            return None

        consumed_pages = sum(result.pages_consumed for result in history)
        remaining_budget = max(0, request.page_budget - consumed_pages)
        if remaining_budget <= 0:
            return None

        if last.validation_pass.strategy == "first_page":
            page_limit = min(request.max_pages, self.default_window_pages, remaining_budget)
            if page_limit <= 1:
                return self._pattern_or_visual_pass(request, level=2)
            return GoalValidationPass(
                level=2,
                strategy="first_pages_window",
                reason="first_page_inconclusive_expand_window",
                page_numbers=tuple(range(1, page_limit + 1)),
            )

        if last.validation_pass.strategy == "first_pages_window":
            return self._pattern_or_visual_pass(request, level=3)

        if last.validation_pass.strategy == "pattern_search":
            if request.target_page is not None:
                return GoalValidationPass(
                    level=4,
                    strategy="visual_page",
                    reason="pattern_search_inconclusive_visual_confirmation",
                    page_numbers=(request.target_page,),
                )
            return GoalValidationPass(
                level=4,
                strategy="visual_page",
                reason="pattern_search_inconclusive_visual_confirmation",
                page_numbers=(1,),
            )

        return None

    def _initial_pass(self, request: GoalValidationRequest) -> GoalValidationPass:
        if request.preferred_strategy == "visual_page":
            target = request.target_page or 1
            return GoalValidationPass(
                level=1,
                strategy="visual_page",
                reason="requested_visual_validation",
                page_numbers=(target,),
            )
        return GoalValidationPass(
            level=1,
            strategy="first_page",
            reason="cheap_initial_validation",
            page_numbers=(1,),
        )

    def _pattern_or_visual_pass(
        self,
        request: GoalValidationRequest,
        *,
        level: int,
    ) -> GoalValidationPass | None:
        if request.pattern_hints:
            return GoalValidationPass(
                level=level,
                strategy="pattern_search",
                reason="text_window_inconclusive_use_pattern_search",
                pattern_hints=request.pattern_hints,
            )
        target = request.target_page or 1
        return GoalValidationPass(
            level=level,
            strategy="visual_page",
            reason="text_validation_inconclusive_visual_confirmation",
            page_numbers=(target,),
        )


__all__ = ["GoalValidationPolicy"]
