from __future__ import annotations

from typing import Protocol

from graph_mapper_agent.application.goal_validation.artifact_models import (
    GoalValidationArtifact,
    RenderedPageEvidence,
    TextPageEvidence,
)


class GoalValidationPdfEvidenceReaderPort(Protocol):
    def page_count(self, artifact: GoalValidationArtifact) -> int: ...

    def read_text_pages(
        self,
        artifact: GoalValidationArtifact,
        *,
        page_numbers: tuple[int, ...] | None = None,
        max_pages: int | None = None,
    ) -> tuple[TextPageEvidence, ...]: ...

    def render_page_image(
        self,
        artifact: GoalValidationArtifact,
        *,
        page_number: int,
        dpi: int = 100,
    ) -> RenderedPageEvidence: ...
