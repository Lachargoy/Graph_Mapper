from __future__ import annotations

from typing import Any, Mapping

from graph_mapper_agent.adapters.goal_validation.llm_validation_executor import (
    GoalValidationExecutorSettings,
    LlmBackedGoalValidationPassExecutor,
)
from graph_mapper_agent.adapters.goal_validation.pdf_pymupdf_reader import (
    PyMuPdfGoalValidationPdfEvidenceReader,
)
from graph_mapper_agent.adapters.goal_validation.text_validation_executor import (
    DeterministicGoalValidationPassExecutor,
)
from graph_mapper_agent.application.evidence_extraction.service import (
    EvidenceExtractionService,
)
from graph_mapper_agent.platform.llm.config import (
    LlmRuntimeConfig,
)
from graph_mapper_agent.application.goal_validation import (
    GoalValidationService,
    GoalValidationPolicy,
    ProgressiveGoalValidationUseCase,
)
from graph_mapper_agent.ledger.domain.actor_kind import ActorKind
from graph_mapper_agent.ledger.domain.run_correlation import (
    RunCorrelation,
)
from graph_mapper_agent.ledger.domain.target_ref import TargetRef

from .evidence_extraction import build_evidence_extraction_service


def build_goal_validation_service(
    *,
    llm_runtime_config: LlmRuntimeConfig | None,
    evidence_extraction_visual_runtime: object | None = None,
    evidence_extraction_ocr_runtime: object | None = None,
    evidence_extraction_ocr_runtime_config: LlmRuntimeConfig | None = None,
    execution_metadata: Mapping[str, Any],
    ledger: object | None = None,
    ledger_run: RunCorrelation | None = None,
    ledger_actor: ActorKind | None = None,
    ledger_target: TargetRef | None = None,
    ) -> GoalValidationService:
    mode = str(
        execution_metadata.get("goal_validation_mode")
        or execution_metadata.get("document_validation_mode")
        or "deterministic"
    ).strip().lower()
    pdf_reader = PyMuPdfGoalValidationPdfEvidenceReader()
    evidence_extraction_service: EvidenceExtractionService = build_evidence_extraction_service(
        pdf_reader=pdf_reader,
        vision_runtime=evidence_extraction_visual_runtime,
        ocr_runtime=evidence_extraction_ocr_runtime,
        ocr_runtime_config=evidence_extraction_ocr_runtime_config,
        coverage_runtime=None,
    )

    if mode == "llm" and llm_runtime_config is not None:
        from .llm import build_llm_runtime_bundle

        bundle = build_llm_runtime_bundle(
            llm_runtime_config=llm_runtime_config,
            expected_output_name="goal_validation_output",
            ledger=ledger,
            label_prefix="goal_validation",
        )
        if bundle is None:
            raise ValueError(
                "Could not build the LLM runtime for goal validation."
            )

        executor = LlmBackedGoalValidationPassExecutor(
            pdf_reader=pdf_reader,
            evidence_extraction_service=build_evidence_extraction_service(
                pdf_reader=pdf_reader,
                vision_runtime=evidence_extraction_visual_runtime,
                ocr_runtime=evidence_extraction_ocr_runtime,
                ocr_runtime_config=evidence_extraction_ocr_runtime_config,
                coverage_runtime=bundle.runtime,
            ),
            llm_runtime=bundle.runtime,
            invoke_llm_use_case=bundle.invoke_llm_use_case,
            ledger_run=ledger_run,
            ledger_actor=ledger_actor,
            ledger_target=ledger_target,
            settings=GoalValidationExecutorSettings(
                supports_vision=bool(llm_runtime_config.supports_vision),
            ),
        )
    else:
        executor = DeterministicGoalValidationPassExecutor(
            pdf_reader=pdf_reader,
            evidence_extraction_service=evidence_extraction_service,
        )

    return GoalValidationService(
        use_case=ProgressiveGoalValidationUseCase(
            policy=GoalValidationPolicy(),
            executor=executor,
        )
    )


def build_document_validation_service(
    *,
    llm_runtime_config: LlmRuntimeConfig | None,
    evidence_extraction_visual_runtime: object | None = None,
    evidence_extraction_ocr_runtime: object | None = None,
    evidence_extraction_ocr_runtime_config: LlmRuntimeConfig | None = None,
    execution_metadata: Mapping[str, Any],
    ledger: object | None = None,
    ledger_run: RunCorrelation | None = None,
    ledger_actor: ActorKind | None = None,
    ledger_target: TargetRef | None = None,
) -> GoalValidationService:
    return build_goal_validation_service(
        llm_runtime_config=llm_runtime_config,
        evidence_extraction_visual_runtime=evidence_extraction_visual_runtime,
        evidence_extraction_ocr_runtime=evidence_extraction_ocr_runtime,
        evidence_extraction_ocr_runtime_config=evidence_extraction_ocr_runtime_config,
        execution_metadata=execution_metadata,
        ledger=ledger,
        ledger_run=ledger_run,
        ledger_actor=ledger_actor,
        ledger_target=ledger_target,
    )
