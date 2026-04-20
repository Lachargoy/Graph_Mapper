from __future__ import annotations

import unittest

from graph_mapper_agent.application.document_validation.service import (
    DocumentValidationService,
)
from graph_mapper_agent.application.document_validation.use_cases.progressive_validate_artifact import (
    ProgressiveValidateArtifactResult,
    ProgressiveValidateArtifactUseCase,
)
from graph_mapper_agent.application.document_validation.validation_models import (
    ValidationGoalCondition,
    ValidationPass,
    ValidationRequest,
    ValidationResult,
)
from graph_mapper_agent.application.goal_validation import (
    GoalCondition,
    GoalValidationPass,
    GoalValidationRequest,
    GoalValidationResult,
    GoalValidationService,
)


class GoalValidationLegacyCompatTests(unittest.TestCase):
    def test_legacy_validation_types_alias_goal_validation_types(self) -> None:
        self.assertIs(ValidationRequest, GoalValidationRequest)
        self.assertIs(ValidationPass, GoalValidationPass)
        self.assertIs(ValidationResult, GoalValidationResult)
        self.assertIs(ValidationGoalCondition, GoalCondition)

    def test_legacy_service_aliases_goal_validation_service(self) -> None:
        self.assertIs(DocumentValidationService, GoalValidationService)
        self.assertIs(ProgressiveValidateArtifactUseCase, ProgressiveValidateArtifactUseCase)
        self.assertIs(ProgressiveValidateArtifactResult, ProgressiveValidateArtifactResult)
