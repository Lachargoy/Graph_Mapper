from __future__ import annotations

import unittest

from graph_mapper_agent.adapters.llm.outputs.structured_output_registry import (
    resolve_output_type,
)
from graph_mapper_agent.application.contracts.document_validation import (
    DocumentValidationLlmOutput,
    GoalValidationLlmOutput,
)


class GoalValidationStructuredOutputTests(unittest.TestCase):
    def test_goal_validation_output_resolves(self) -> None:
        self.assertIs(
            GoalValidationLlmOutput,
            resolve_output_type("goal_validation_output"),
        )

    def test_legacy_document_validation_output_still_resolves(self) -> None:
        self.assertIs(
            DocumentValidationLlmOutput,
            resolve_output_type("document_validation_output"),
        )
