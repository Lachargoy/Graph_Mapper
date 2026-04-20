from __future__ import annotations

from graph_mapper_agent.application.local_perception.goal_validation_service_port import (
    GoalValidationServicePort,
)


# Legacy alias kept during the transition from document_validation to
# goal_validation. New code should depend on GoalValidationServicePort.
DocumentValidationServicePort = GoalValidationServicePort
