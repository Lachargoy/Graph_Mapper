from __future__ import annotations

import unittest

from graph_mapper_agent.application.goal_validation import (
    GoalValidationArtifact,
    GoalValidationPass,
    GoalValidationPolicy,
    GoalValidationRequest,
    GoalValidationResult,
)


def _request(**overrides) -> GoalValidationRequest:
    payload = {
        "artifact": GoalValidationArtifact(inline_text="dummy"),
        "validation_goal": "validate current evidence",
        "max_pages": 5,
        "page_budget": 5,
        "escalation_allowed": True,
        "pattern_hints": (),
        "target_page": None,
    }
    payload.update(overrides)
    return GoalValidationRequest(**payload)


def _result(
    *,
    strategy: str,
    status: str,
    pages_consumed: int = 0,
) -> GoalValidationResult:
    validation_pass = GoalValidationPass(
        level=1,
        strategy=strategy,
        reason="test",
        page_numbers=(1,),
    )
    return GoalValidationResult(
        status=status,
        validation_pass=validation_pass,
        rationale="test-result",
        pages_consumed=pages_consumed,
    )


class GoalValidationPolicyTests(unittest.TestCase):
    def test_initial_pass_defaults_to_first_page(self) -> None:
        policy = GoalValidationPolicy()

        next_pass = policy.next_pass(_request())

        self.assertIsNotNone(next_pass)
        self.assertEqual("first_page", next_pass.strategy)
        self.assertEqual((1,), next_pass.page_numbers)

    def test_escalates_first_page_to_window(self) -> None:
        policy = GoalValidationPolicy()

        next_pass = policy.next_pass(
            _request(max_pages=4, page_budget=4),
            history=(_result(strategy="first_page", status="needs_more_pages"),),
        )

        self.assertIsNotNone(next_pass)
        self.assertEqual("first_pages_window", next_pass.strategy)
        self.assertEqual((1, 2, 3), next_pass.page_numbers)

    def test_escalates_to_pattern_search_when_hints_exist(self) -> None:
        policy = GoalValidationPolicy()

        next_pass = policy.next_pass(
            _request(pattern_hints=("invoice",)),
            history=(_result(strategy="first_pages_window", status="inconclusive"),),
        )

        self.assertIsNotNone(next_pass)
        self.assertEqual("pattern_search", next_pass.strategy)
        self.assertEqual(("invoice",), next_pass.pattern_hints)

    def test_stops_when_budget_is_exhausted(self) -> None:
        policy = GoalValidationPolicy()

        next_pass = policy.next_pass(
            _request(page_budget=1),
            history=(_result(strategy="first_page", status="needs_more_pages", pages_consumed=1),),
        )

        self.assertIsNone(next_pass)
