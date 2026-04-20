from __future__ import annotations
#graph_mapper_agent/ledger/application/invoke_llm_with_ledger_use_case.py
from dataclasses import dataclass, field
from typing import Callable
from uuid import uuid4

from graph_mapper_agent.domain.ports.llm_runtime_port import (
    LlmRuntimePort,
    LlmRuntimeRequest,
    LlmRuntimeResponse,
)
from graph_mapper_agent.ledger.domain.actor_kind import ActorKind
from graph_mapper_agent.ledger.domain.event_payloads import (
    LlmCalledPayload,
    LlmCompletedPayload,
    LlmValidationFailedPayload,
)
from graph_mapper_agent.ledger.domain.llm_call_metadata import (
    LlmCallMetadata,
)
from graph_mapper_agent.ledger.domain.llm_interaction import (
    LlmInteraction,
)
from graph_mapper_agent.ledger.domain.run_correlation import (
    RunCorrelation,
)
from graph_mapper_agent.ledger.domain.target_ref import TargetRef
from graph_mapper_agent.ledger.ports import LedgerWritePort


def _default_event_id_factory() -> str:
    return f"evt-{uuid4().hex}"


def _default_call_id_factory() -> str:
    return f"llm-{uuid4().hex}"


@dataclass(frozen=True)
class InvokeLlmWithLedgerUseCase:
    ledger: LedgerWritePort
    llm_runtime: LlmRuntimePort
    provider_name: str = "llm_runtime"
    event_id_factory: Callable[[], str] = field(default=_default_event_id_factory)
    call_id_factory: Callable[[], str] = field(default=_default_call_id_factory)

    def execute(
        self,
        run: RunCorrelation,
        actor: ActorKind,
        request: LlmRuntimeRequest,
        request_kind: str | None = None,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> LlmRuntimeResponse:
        effective_request_kind = request_kind or self._infer_request_kind(request)
        call_id = self.call_id_factory()
        base_metadata = dict(metadata or {})
        base_metadata.setdefault("call_id", call_id)

        self.ledger.record_llm_called(
            event_id=self.event_id_factory(),
            run=run,
            actor=actor,
            payload=LlmCalledPayload(
                operation_name=request.operation_name,
                request_kind=effective_request_kind,
                expected_output_contract=request.expected_output_name,
            ),
            llm=self._build_called_metadata(
                request=request,
                provider_name=self.provider_name,
            ),
            llm_io=self._build_called_interaction(request),
            target=target,
            metadata=base_metadata,
        )

        response = self.llm_runtime.invoke(request)
        validation = response.interaction.validation
        response_is_valid = bool(validation.get("valid", True))

        self.ledger.record_llm_completed(
            event_id=self.event_id_factory(),
            run=run,
            actor=actor,
            payload=LlmCompletedPayload(
                operation_name=request.operation_name,
                finish_reason=self._extract_finish_reason(response),
                response_format_valid=response_is_valid,
                retryable=False,
            ),
            llm=response.metadata,
            llm_io=self._interaction_with_raw_response(response),
            target=target,
            metadata=base_metadata,
        )

        if not response_is_valid:
            self.ledger.record_llm_validation_failed(
                event_id=self.event_id_factory(),
                run=run,
                actor=actor,
                payload=LlmValidationFailedPayload(
                    operation_name=request.operation_name,
                    validation_stage=self._extract_validation_stage(validation),
                    error_message=self._extract_validation_error_message(validation),
                    retryable=False,
                ),
                llm=response.metadata,
                llm_io=self._interaction_with_raw_response(response),
                target=target,
                metadata=base_metadata,
            )

        return response

    @staticmethod
    def _infer_request_kind(request: LlmRuntimeRequest) -> str:
        if request.expected_output_name:
            return "structured_generation"
        return "chat_completion"

    @staticmethod
    def _build_called_metadata(
        request: LlmRuntimeRequest,
        provider_name: str,
    ) -> LlmCallMetadata:
        return LlmCallMetadata(
            provider=provider_name,
            model=request.model_hint or "pending",
            prompt_version=InvokeLlmWithLedgerUseCase._coerce_optional_str(
                request.metadata.get("prompt_version")
            ),
            prompt_hash=InvokeLlmWithLedgerUseCase._coerce_optional_str(
                request.metadata.get("prompt_hash")
            ),
            structured_output_name=request.expected_output_name,
        )

    @staticmethod
    def _build_called_interaction(request: LlmRuntimeRequest) -> LlmInteraction:
        return LlmInteraction(
            input={
                "messages": [dict(message) for message in request.messages],
                "metadata": dict(request.metadata),
            },
            expected_output={"name": request.expected_output_name},
        )

    @staticmethod
    def _interaction_with_raw_response(response: LlmRuntimeResponse) -> LlmInteraction:
        interaction = response.interaction
        response_payload = dict(interaction.response)
        if response.raw_response is not None and "raw_response" not in response_payload:
            response_payload["raw_response"] = dict(response.raw_response)
        return LlmInteraction(
            input=dict(interaction.input),
            expected_output=dict(interaction.expected_output),
            response=response_payload,
            validation=dict(interaction.validation),
        )

    @staticmethod
    def _extract_finish_reason(response: LlmRuntimeResponse) -> str:
        finish_reason = response.interaction.response.get("finish_reason")
        if finish_reason is None:
            return "unknown"
        text = str(finish_reason).strip()
        return text or "unknown"

    @staticmethod
    def _extract_validation_stage(validation: dict[str, object]) -> str:
        stage = validation.get("stage")
        if stage is None:
            return "response_validation"
        text = str(stage).strip()
        return text or "response_validation"

    @staticmethod
    def _extract_validation_error_message(validation: dict[str, object]) -> str:
        explicit_message = validation.get("error_message")
        if explicit_message is not None:
            text = str(explicit_message).strip()
            if text:
                return text
        errors = validation.get("errors")
        if isinstance(errors, list) and errors:
            return "; ".join(str(item) for item in errors if str(item).strip())
        return "La salida LLM no cumplio el contrato esperado."

    @staticmethod
    def _coerce_optional_str(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
