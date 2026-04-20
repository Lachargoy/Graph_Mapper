#graph_mapper_agent/bootstrap/runner.py
from __future__ import annotations

import time
from uuid import uuid4
from typing import Any, Mapping

from graph_mapper_agent.platform.llm.config import (
    LlmRuntimeConfig,
)
from graph_mapper_agent.application.local_perception.service import (
    LocalPerceptionService,
)
from graph_mapper_agent.application.goal_validation import (
    ValidateGoalUseCase,
)
from graph_mapper_agent.application.services.decision.llm_use_case import (
    GraphMapperDecisionLlmUseCase,
)
from graph_mapper_agent.ledger.domain.actor_kind import ActorKind
from graph_mapper_agent.ledger.domain.event_payloads import (
    RunCompletedPayload,
    RunFailedPayload,
    RunStartedPayload,
)
from graph_mapper_agent.ledger.domain.run_correlation import (
    RunCorrelation,
)
from graph_mapper_agent.ledger.domain.target_ref import TargetRef

from .builders.goals import build_goal_trace
from .builders.ledger import build_ledger_writer
from .builders.llm import build_llm_runtime_bundle
from .builders.perception import build_navigation_perception_service
from .builders.runtime import build_runtime_bundle
from .builders.tooling import build_tooling
from .builders.validation import build_goal_validation_service
from .config import GraphMapperConfig
from .dto import RunGraphMapperInput
from .execution_config import GuidedGraphMapperConfig
from .initial_state import build_initial_state
from .metadata import build_execution_metadata
from .result import GraphMapperResult
from .timing import timed, ts
from ..runtime.transitions import START_STATE


def run_graph_mapper(input_data: RunGraphMapperInput) -> GraphMapperResult:
    total_start = time.perf_counter()
    print(f"[{ts()}] [graph_mapper] NEW RUNNER LOADED", flush=True)
    print(f"[{ts()}] [graph_mapper] run_graph_mapper started", flush=True)

    input_data.request.validate()
    input_data.execution.validate()

    writer = timed(
        "build_ledger_writer",
        lambda: build_ledger_writer(input_data.execution.ledger_database_url),
    )

    if input_data.request.decision_mode == "llm" and writer is None:
        raise ValueError(
            "GraphMapper in 'llm' mode requires ledger_database_url in "
            "execution.ledger.database_url or AITHER_LEDGER_DATABASE_URL in the environment."
        )

    tooling = timed("build_tooling", build_tooling)
    registry = tooling.registry
    browser_tool = tooling.browser_tool
    navigation_actions = tooling.navigation_actions
    live_inspection = tooling.live_inspection

    llm_runtime_source = input_data.execution.llm_runtime
    navigation_perception_llm_runtime_source = (
        input_data.execution.navigation_perception_llm_runtime
        if input_data.execution.navigation_perception_llm_runtime is not None
        else llm_runtime_source
    )
    goal_validation_llm_runtime_source = (
        input_data.execution.goal_validation_llm_runtime
        if input_data.execution.goal_validation_llm_runtime is not None
        else llm_runtime_source
    )
    evidence_extraction_visual_llm_runtime_source = (
        input_data.execution.evidence_extraction_visual_llm_runtime
        if input_data.execution.evidence_extraction_visual_llm_runtime is not None
        else goal_validation_llm_runtime_source
    )
    evidence_extraction_ocr_llm_runtime_source = (
        input_data.execution.evidence_extraction_ocr_llm_runtime
        if input_data.execution.evidence_extraction_ocr_llm_runtime is not None
        else evidence_extraction_visual_llm_runtime_source
    )

    ledger_run = RunCorrelation(
        run_id=input_data.execution.run_id,
        thread_id=input_data.execution.document_key,
        workflow_name=input_data.execution.workflow_name,
    )
    ledger_actor = ActorKind.AGENT
    ledger_target = TargetRef(
        target_kind=input_data.execution.target_kind,
        target_id=input_data.execution.target_id or input_data.execution.document_key,
        context={"jurisdiction_code": input_data.execution.jurisdiction_code},
    )
    session_id = _resolve_session_id(input_data)

    _record_session_bootstrap(
        writer=writer,
        session_id=session_id,
        input_data=input_data,
    )

    llm_use_case = timed(
        "build_graph_mapper_llm_use_case",
        lambda: (
            _build_graph_mapper_llm_use_case(
                llm_runtime_config=llm_runtime_source,
                ledger=writer,
            )
            if input_data.request.decision_mode == "llm"
            else None
        ),
    )

    planned_goal_result = timed(
        "build_goal_trace",
        lambda: build_goal_trace(
            request=input_data.request,
            execution=input_data.execution,
        ),
    )

    runtime_execution_metadata = dict(input_data.execution.execution_metadata or {})

    navigation_perception_service = timed(
        "build_navigation_perception_service",
        lambda: build_navigation_perception_service(
            browser_tool=browser_tool,
            live_inspection=live_inspection,
            llm_runtime_config=navigation_perception_llm_runtime_source,
            execution_metadata=runtime_execution_metadata,
            ledger=writer,
            ledger_run=ledger_run,
            ledger_actor=ledger_actor,
            ledger_target=ledger_target,
        ),
    )

    goal_validation_service = timed(
        "build_goal_validation_service",
        lambda: build_goal_validation_service(
            llm_runtime_config=goal_validation_llm_runtime_source,
            evidence_extraction_visual_runtime=(
                _build_generic_runtime(
                    llm_runtime_config=evidence_extraction_visual_llm_runtime_source,
                    ledger=writer,
                    label_prefix="evidence_extraction_visual",
                )
            ),
            evidence_extraction_ocr_runtime=(
                _build_generic_runtime(
                    llm_runtime_config=evidence_extraction_ocr_llm_runtime_source,
                    ledger=writer,
                    label_prefix="evidence_extraction_ocr",
                )
            ),
            evidence_extraction_ocr_runtime_config=evidence_extraction_ocr_llm_runtime_source,
            execution_metadata=runtime_execution_metadata,
            ledger=writer,
            ledger_run=ledger_run,
            ledger_actor=ledger_actor,
            ledger_target=ledger_target,
        ),
    )

    local_perception_service = LocalPerceptionService(
        goal_validation_service=goal_validation_service,
        goal_validation_use_case=ValidateGoalUseCase(
            service=goal_validation_service
        ),
        navigation_perception_service=navigation_perception_service,
    )

    runtime_bundle = timed(
            "build_runtime_bundle",
            lambda: build_runtime_bundle(
                request=input_data.request,
                execution=input_data.execution,
                navigation_actions=navigation_actions,
                ledger=writer,
                llm_use_case=llm_use_case,
                navigation_perception_service=navigation_perception_service,
                local_perception_service=local_perception_service,
            ),
        )
    orchestrator = runtime_bundle.orchestrator

    execution_metadata = build_execution_metadata(
        execution=input_data.execution,
        request=input_data.request,
        registry=registry,
        llm_runtime_source=llm_runtime_source,
        navigation_perception_llm_runtime_source=navigation_perception_llm_runtime_source,
        goal_validation_llm_runtime_source=goal_validation_llm_runtime_source,
        evidence_extraction_visual_llm_runtime_source=evidence_extraction_visual_llm_runtime_source,
        evidence_extraction_ocr_llm_runtime_source=evidence_extraction_ocr_llm_runtime_source,
        planned_goal_result=planned_goal_result,
    )

    planned_goal_trace = (
        planned_goal_result.goal_trace if planned_goal_result is not None else None
    )

    initial_state = build_initial_state(
        input_data=input_data,
        execution_metadata=execution_metadata,
        planned_goal_trace=planned_goal_trace,
        ledger_run=ledger_run,
        ledger_actor=ledger_actor,
        ledger_target=ledger_target,
    )

    print(
        f"[{ts()}] [graph_mapper] components ready "
        f"llm_enabled={llm_use_case is not None} "
        f"tools={list(registry.list_tools())} "
        f"goal_trace_loaded={planned_goal_trace is not None}",
        flush=True,
    )

    print(
        f"[{ts()}] [graph_mapper] orchestrator.execute starting "
        f"entry_url={input_data.request.entry_url!r} "
        f"decision_mode={input_data.request.decision_mode!r} "
        f"max_pages={input_data.request.max_pages}",
        flush=True,
    )

    _record_run_started(
        writer=writer,
        run=ledger_run,
        actor=ledger_actor,
        target=ledger_target,
        input_data=input_data,
        session_id=session_id,
    )

    try:
        final_state = timed(
            "orchestrator.execute",
            lambda: orchestrator.execute(
                initial_state=initial_state,
                start_at=START_STATE,
            ),
        )
    except Exception as exc:
        _record_run_failed(
            writer=writer,
            run=ledger_run,
            actor=ledger_actor,
            target=ledger_target,
            error=exc,
            session_id=session_id,
        )
        _record_session_failure_message(
            writer=writer,
            session_id=session_id,
            error=exc,
        )
        _record_run_failure_evaluation(
            writer=writer,
            run=ledger_run,
            session_id=session_id,
            error=exc,
        )
        raise

    result = GraphMapperResult(
        final_state=final_state,
        final_status=_extract_final_status(final_state),
    )

    _record_run_completed(
        writer=writer,
        run=ledger_run,
        actor=ledger_actor,
        target=ledger_target,
        result=result,
        session_id=session_id,
    )
    _record_session_result_message(
        writer=writer,
        session_id=session_id,
        result=result,
    )
    _record_run_completion_evaluation(
        writer=writer,
        run=ledger_run,
        session_id=session_id,
        result=result,
    )

    total_elapsed = time.perf_counter() - total_start
    print(
        f"[{ts()}] [graph_mapper] run_graph_mapper finished "
        f"final_status={result.final_status!r} elapsed={total_elapsed:.3f}s",
        flush=True,
    )

    return result


def run_graph_mapper_from_json_dict(payload: Mapping[str, Any]) -> GraphMapperResult:
    request_payload = payload.get("request") or {}
    execution_payload = dict(payload.get("execution") or {})
    llm_runtime_payload = payload.get("llm_runtime")
    navigation_perception_llm_runtime_payload = payload.get(
        "navigation_perception_llm_runtime"
    )
    goal_validation_llm_runtime_payload = payload.get(
        "goal_validation_llm_runtime"
    ) or payload.get("document_validation_llm_runtime")
    evidence_extraction_visual_llm_runtime_payload = payload.get(
        "evidence_extraction_visual_llm_runtime"
    )
    evidence_extraction_ocr_llm_runtime_payload = payload.get(
        "evidence_extraction_ocr_llm_runtime"
    )

    if isinstance(llm_runtime_payload, Mapping):
        execution_payload["llm_runtime"] = dict(llm_runtime_payload)
    if isinstance(navigation_perception_llm_runtime_payload, Mapping):
        execution_payload["navigation_perception_llm_runtime"] = dict(
            navigation_perception_llm_runtime_payload
        )
    if isinstance(goal_validation_llm_runtime_payload, Mapping):
        execution_payload["goal_validation_llm_runtime"] = dict(
            goal_validation_llm_runtime_payload
        )
    if isinstance(evidence_extraction_visual_llm_runtime_payload, Mapping):
        execution_payload["evidence_extraction_visual_llm_runtime"] = dict(
            evidence_extraction_visual_llm_runtime_payload
        )
    if isinstance(evidence_extraction_ocr_llm_runtime_payload, Mapping):
        execution_payload["evidence_extraction_ocr_llm_runtime"] = dict(
            evidence_extraction_ocr_llm_runtime_payload
        )

    request = GraphMapperConfig.from_json_dict(request_payload)
    execution = GuidedGraphMapperConfig.from_json_dict(execution_payload)

    mock_observations = payload.get("mock_observations")
    if mock_observations is not None and not isinstance(mock_observations, dict):
        raise TypeError("mock_observations must be dict[str, dict[str, object]]")

    return run_graph_mapper(
        RunGraphMapperInput(
            request=request,
            execution=execution,
            mock_observations=mock_observations,
        )
    )


def _build_graph_mapper_llm_use_case(
    *,
    llm_runtime_config: LlmRuntimeConfig | None,
    ledger: object | None,
) -> GraphMapperDecisionLlmUseCase | None:
    bundle = build_llm_runtime_bundle(
        llm_runtime_config=llm_runtime_config,
        expected_output_name="graph_mapper_navigation_decision",
        ledger=ledger,
        label_prefix="graph_mapper_decision",
    )
    if bundle is None or bundle.invoke_llm_use_case is None:
        return None

    return GraphMapperDecisionLlmUseCase(
        invoke_llm_use_case=bundle.invoke_llm_use_case,
    )


def _build_generic_runtime(
    *,
    llm_runtime_config: LlmRuntimeConfig | None,
    ledger: object | None,
    label_prefix: str,
) -> object | None:
    if llm_runtime_config is not None and str(llm_runtime_config.backend).strip().lower() == "ollama":
        return None
    bundle = build_llm_runtime_bundle(
        llm_runtime_config=llm_runtime_config,
        expected_output_name=None,
        ledger=ledger,
        label_prefix=label_prefix,
    )
    if bundle is None:
        return None
    return bundle.runtime


def _extract_final_status(state: dict[str, object]) -> str | None:
    status = state.get("final_status")
    if isinstance(status, str) and status.strip():
        return status
    return None


def _record_run_started(
    *,
    writer: object | None,
    run: RunCorrelation,
    actor: ActorKind,
    target: TargetRef | None,
    input_data: RunGraphMapperInput,
    session_id: str | None,
) -> None:
    if writer is None:
        return
    record = getattr(writer, "record_run_started", None)
    if not callable(record):
        return
    record(
        event_id=_new_event_id(),
        run=run,
        actor=actor,
        payload=RunStartedPayload(
            trigger="graph_mapper_runner",
            initial_phase="queued",
            input_channels=("entry_url", "goal"),
        ),
        target=target,
        metadata={
            "session_id": session_id,
            "entry_url": input_data.request.entry_url,
            "goal": input_data.request.goal,
            "decision_mode": input_data.request.decision_mode,
            "allow_artifact_download": input_data.request.allow_artifact_download,
            "allow_artifact_open": input_data.request.allow_artifact_open,
            "execution_metadata": dict(input_data.execution.execution_metadata or {}),
        },
    )


def _record_run_completed(
    *,
    writer: object | None,
    run: RunCorrelation,
    actor: ActorKind,
    target: TargetRef | None,
    result: GraphMapperResult,
    session_id: str | None,
) -> None:
    if writer is None:
        return
    record = getattr(writer, "record_run_completed", None)
    if not callable(record):
        return
    final_phase = result.final_status or "completed"
    record(
        event_id=_new_event_id(),
        run=run,
        actor=actor,
        payload=RunCompletedPayload(
            final_phase=final_phase,
            summary=f"GraphMapper run completed with status={final_phase}",
            suggestions_count=0,
            review_items_count=0,
        ),
        target=target,
        metadata={
            "session_id": session_id,
            "final_status": result.final_status,
            "final_state": result.final_state,
        },
    )


def _record_run_failed(
    *,
    writer: object | None,
    run: RunCorrelation,
    actor: ActorKind,
    target: TargetRef | None,
    error: Exception,
    session_id: str | None,
) -> None:
    if writer is None:
        return
    record = getattr(writer, "record_run_failed", None)
    if not callable(record):
        return
    record(
        event_id=_new_event_id(),
        run=run,
        actor=actor,
        payload=RunFailedPayload(
            error_class=type(error).__name__,
            error_message=str(error) or repr(error),
            failed_phase="runtime_execution",
            retriable=False,
        ),
        target=target,
        metadata={
            "session_id": session_id,
            "error_repr": repr(error),
        },
    )


def _new_event_id() -> str:
    return f"evt-{uuid4().hex}"


def _resolve_session_id(input_data: RunGraphMapperInput) -> str:
    metadata = dict(input_data.execution.execution_metadata or {})
    explicit = metadata.get("session_id")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    return f"session-{input_data.execution.run_id}"


def _record_session_bootstrap(
    *,
    writer: object | None,
    session_id: str,
    input_data: RunGraphMapperInput,
) -> None:
    if writer is None:
        return

    record_session = getattr(writer, "record_session", None)
    if callable(record_session):
        record_session(
            session_id=session_id,
            session_kind="runtime",
            context={
                "entry_url": input_data.request.entry_url,
                "goal": input_data.request.goal,
            },
            metadata={
                "run_id": input_data.execution.run_id,
                "workflow_name": input_data.execution.workflow_name,
            },
        )

    record_message = getattr(writer, "record_message", None)
    if callable(record_message):
        record_message(
            session_id=session_id,
            role="user",
            content={
                "goal": input_data.request.goal,
                "entry_url": input_data.request.entry_url,
            },
            metadata={
                "kind": "runtime_bootstrap_input",
                "decision_mode": input_data.request.decision_mode,
            },
        )


def _record_session_result_message(
    *,
    writer: object | None,
    session_id: str,
    result: GraphMapperResult,
) -> None:
    if writer is None:
        return
    record_message = getattr(writer, "record_message", None)
    if not callable(record_message):
        return
    record_message(
        session_id=session_id,
        role="assistant",
        content={
            "final_status": result.final_status,
            "final_state": result.final_state,
        },
        metadata={
            "kind": "runtime_result",
        },
    )


def _record_session_failure_message(
    *,
    writer: object | None,
    session_id: str,
    error: Exception,
) -> None:
    if writer is None:
        return
    record_message = getattr(writer, "record_message", None)
    if not callable(record_message):
        return
    record_message(
        session_id=session_id,
        role="assistant",
        content={
            "error_class": type(error).__name__,
            "error_message": str(error) or repr(error),
        },
        metadata={
            "kind": "runtime_failure",
        },
    )


def _record_run_completion_evaluation(
    *,
    writer: object | None,
    run: RunCorrelation,
    session_id: str,
    result: GraphMapperResult,
) -> None:
    if writer is None:
        return
    record_evaluation = getattr(writer, "record_evaluation", None)
    if not callable(record_evaluation):
        return

    final_status = (result.final_status or "").strip().lower()
    success_like = final_status in {"success", "completed", "done"}
    exhausted_like = final_status in {"exhausted", "mark_exhausted"}

    score = 1.0 if success_like else 0.6 if exhausted_like else 0.75
    label = "good" if success_like else "partial" if exhausted_like else "unknown"

    record_evaluation(
        target_kind="run",
        evaluator_kind="heuristic_runtime",
        run_id=run.run_id,
        session_id=session_id,
        score=score,
        label=label,
        usable_for_training=success_like,
        feedback={
            "final_status": result.final_status,
            "has_final_state": bool(result.final_state),
        },
    )


def _record_run_failure_evaluation(
    *,
    writer: object | None,
    run: RunCorrelation,
    session_id: str,
    error: Exception,
) -> None:
    if writer is None:
        return
    record_evaluation = getattr(writer, "record_evaluation", None)
    if not callable(record_evaluation):
        return

    record_evaluation(
        target_kind="run",
        evaluator_kind="heuristic_runtime",
        run_id=run.run_id,
        session_id=session_id,
        score=0.0,
        label="failed",
        usable_for_training=False,
        feedback={
            "error_class": type(error).__name__,
            "error_message": str(error) or repr(error),
        },
    )
