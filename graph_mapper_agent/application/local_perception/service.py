from __future__ import annotations

from graph_mapper_agent.application.goal_validation import (
    GoalValidationRequest,
)
from graph_mapper_agent.application.local_perception.goal_validation_service_port import (
    GoalValidationServicePort,
)
from graph_mapper_agent.application.local_perception.goal_validation_use_case_port import (
    GoalValidationUseCasePort,
)
from graph_mapper_agent.application.local_perception.models import (
    LocalPerceptionRequest,
    LocalPerceptionResult,
)
from graph_mapper_agent.application.local_perception.navigation_perception_service_port import (
    NavigationPerceptionServicePort,
)
from graph_mapper_agent.application.navigation_perception.models import (
    NavigationPerceptionRequest,
)


class LocalPerceptionService:
    def __init__(
        self,
        *,
        goal_validation_service: GoalValidationServicePort | None = None,
        goal_validation_use_case: GoalValidationUseCasePort | None = None,
        document_validation_service: GoalValidationServicePort | None = None,
        navigation_perception_service: NavigationPerceptionServicePort | None = None,
    ) -> None:
        self._goal_validation_service = (
            goal_validation_service or document_validation_service
        )
        self._goal_validation_use_case = goal_validation_use_case
        self._navigation_perception_service = navigation_perception_service

    def perceive(self, request: LocalPerceptionRequest) -> LocalPerceptionResult:
        if request.target_kind == 'artifact_document':
            return self._perceive_artifact_document(request)
        if request.target_kind == 'inline_document_content':
            return self._perceive_artifact_document(request)
        if request.target_kind == 'navigation_state':
            return self._perceive_navigation_state(request)
        return LocalPerceptionResult(
            target_kind=request.target_kind,
            status='unsupported',
            confidence=0.0,
            summary=f'Unsupported local perception target kind: {request.target_kind}',
            recommended_next_step='defer_or_add_specialized_service',
        )

    def _perceive_artifact_document(self, request: LocalPerceptionRequest) -> LocalPerceptionResult:
        if self._goal_validation_use_case is None and self._goal_validation_service is None:
            raise RuntimeError('Goal validation service is not configured')
        artifact = request.target_ref.artifact
        if artifact is None:
            raise ValueError('artifact_document requests require target_ref.artifact')

        goal_validation_request = GoalValidationRequest(
            artifact=artifact,
            validation_goal=request.question,
            goal_conditions=request.goal_conditions,
            max_pages=request.max_pages,
            page_budget=request.page_budget,
            escalation_allowed=request.escalation_allowed,
            pattern_hints=request.pattern_hints,
            metadata=dict(request.metadata),
        )
        if self._goal_validation_use_case is not None:
            validation_result = self._goal_validation_use_case.execute(
                goal_validation_request
            )
        else:
            validation_result = self._goal_validation_service.validate(
                goal_validation_request
            )
        final_result = validation_result.final_result
        return LocalPerceptionResult(
            target_kind=request.target_kind,
            status='completed',
            confidence=1.0,
            summary=final_result.rationale,
            recommended_next_step=final_result.recommended_next_strategy,
            payload=validation_result,
            metadata={
                'validation_status': final_result.status,
                'validation_strategy': final_result.validation_pass.strategy,
                'passes_executed': len(validation_result.history),
                'matched_condition_ids': tuple(
                    str(item)
                    for item in (final_result.metadata.get('matched_condition_ids') or ())
                    if str(item).strip()
                ),
                'validated_document_family': final_result.metadata.get('validated_document_family'),
                'validated_year': final_result.metadata.get('validated_year'),
                'validation_scope_assessment': final_result.metadata.get('validation_scope_assessment'),
                'source_action': request.metadata.get('source_action'),
            },
        )

    def _perceive_navigation_state(self, request: LocalPerceptionRequest) -> LocalPerceptionResult:
        if self._navigation_perception_service is None:
            raise RuntimeError('Navigation perception service is not configured')
        navigation_request = NavigationPerceptionRequest(
            question=request.question,
            node_id=request.target_ref.node_id,
            url=request.target_ref.url,
            pattern_hints=request.pattern_hints,
            metadata=request.metadata,
        )
        navigation_result = self._navigation_perception_service.perceive(navigation_request)
        return LocalPerceptionResult(
            target_kind='navigation_state',
            status='completed',
            confidence=navigation_result.confidence,
            summary=navigation_result.summary,
            recommended_next_step=navigation_result.recommended_next_step,
            payload=navigation_result,
            metadata={
                'navigation_status': navigation_result.status,
                'layout_kind': navigation_result.layout_kind,
                'visible_candidate_count': navigation_result.visible_candidate_count,
            },
        )
