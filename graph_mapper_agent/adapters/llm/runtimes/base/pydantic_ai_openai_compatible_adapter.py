from __future__ import annotations
#aither/adapters/llm/runtimes/base/pydantic_ai_openai_compatible_adapter.py
import asyncio
import os
import sys
import time
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModelSettings
from pydantic_ai.output import NativeOutput, PromptedOutput, ToolOutput

from graph_mapper_agent.adapters.llm.runtimes.base.callable_llm_runtime_adapter import (
    CallableLlmRuntimeAdapter,
    RawLlmResult,
)
from graph_mapper_agent.adapters.llm.runtimes.base.error_handling import (
    build_failure_details,
    is_retryable,
)
from graph_mapper_agent.adapters.llm.runtimes.base.executor_pool import (
    cleanup_agent_executor,
    get_agent_executor,
)
from graph_mapper_agent.adapters.llm.runtimes.base.message_parsing import (
    parse_messages,
)
from graph_mapper_agent.adapters.llm.runtimes.base.model_building import (
    build_model,
    build_model_settings,
)
from graph_mapper_agent.adapters.llm.runtimes.base.response_building import (
    build_success_result,
    raw_result_from_response,
)
from graph_mapper_agent.adapters.llm.runtimes.base.serialization import (
    coerce_optional_str,
    serialize_value,
)
from graph_mapper_agent.adapters.llm.outputs.structured_output_registry import (
    resolve_output_type,
)
from graph_mapper_agent.domain.ports.llm_runtime_port import (
    LlmRuntimeError,
    LlmRuntimePort,
    LlmRuntimeRequest,
    LlmRuntimeResponse,
)

__all__ = [
    "PydanticAiOpenAiCompatibleSettings",
    "PydanticAiOpenAiCompatibleAdapter",
    "cleanup_agent_executor",
]

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_STRUCTURED_OUTPUT_MODES: dict[str, type] = {
    "native": NativeOutput,
    "prompted": PromptedOutput,
    "tool": ToolOutput,
}

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PydanticAiOpenAiCompatibleSettings:
    """Configuración inmutable para el adaptador PydanticAI OpenAI-compatible."""

    base_url: str | None = None
    default_model: str = "local-model"
    api_key: str | None = None
    timeout_seconds: int = 250

    provider_name: str = "openai_compatible"
    backend_name: str = "pydantic_ai_openai_compatible"

    supports_vision: bool = False

    reasoning_enabled: bool = False
    reasoning_effort: str | None = None
    reasoning_max_tokens: int | None = None
    reasoning_exclude: bool = False

    structured_output_mode: str = "auto"

    provider_require_parameters: bool = False
    provider_allow_fallbacks: bool = True
    provider_order: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Adaptador
# ---------------------------------------------------------------------------

class PydanticAiOpenAiCompatibleAdapter(CallableLlmRuntimeAdapter):
    """
    Adaptador LLM que usa PydanticAI con proveedores OpenAI-compatible.

    Soporta structured outputs (native / prompted / tool), visión,
    reasoning tokens, fallback a otro runtime y logging estructurado.
    """

    def __init__(
        self,
        settings: PydanticAiOpenAiCompatibleSettings,
        fallback_runtime: LlmRuntimePort | None = None,
    ) -> None:
        self._settings = settings
        self._fallback_runtime = fallback_runtime
        self._client_cache: dict[str, AsyncOpenAI] = {}

        super().__init__(
            provider_name=settings.provider_name,
            invoke_callable=self._invoke_with_pydantic_ai,
        )

        self._verbose_logging = (
            os.getenv("AITHER_PYDANTICAI_VERBOSE", "").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self._ansi_enabled = (
            os.getenv("AITHER_NO_COLOR", "").strip().lower()
            not in {"1", "true", "yes", "on"}
        )

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} "
            f"provider={self._settings.provider_name!r} "
            f"backend={self._settings.backend_name!r} "
            f"model={self._settings.default_model!r}>"
        )

    # =========================================================================
    # Logging
    # =========================================================================

    _TITLE_COLORS: dict[str, str] = {
        "navigation_perception": "\033[38;5;42m",
        "document_validation": "\033[38;5;220m",
        "candidate_validation": "\033[38;5;220m",
        "graph_mapper": "\033[38;5;39m",
    }

    def _color_for_title(self, title: str, lines: list[str]) -> str:
        joined = " ".join(lines)
        for keyword, color in self._TITLE_COLORS.items():
            if keyword in joined:
                return color
        return "\033[38;5;245m"

    def _log_block(
        self,
        title: str,
        lines: list[str],
        *,
        verbose_only: bool = False,
    ) -> None:
        if verbose_only and not self._verbose_logging:
            return

        if self._ansi_enabled:
            color = self._color_for_title(title, lines)
            prefix = f"{color}[PydanticAI]\033[0m"
        else:
            prefix = "[PydanticAI]"

        print(f"{prefix} {title}", file=sys.stderr, flush=True)
        for line in lines:
            print(f"{prefix}   {line}", file=sys.stderr, flush=True)

    def _debug_dump_model_settings(
        self,
        model_settings: OpenAIChatModelSettings | None,
    ) -> None:
        """Loggea el contenido real de model_settings para depuración fina."""
        self._log_block(
            "LLM SETTINGS PRE-AGENT",
            [f"model_settings_raw={model_settings!r}"],
            verbose_only=False,
        )

        if model_settings is None:
            self._log_block(
                "LLM SETTINGS DUMP",
                ["model_settings_dump=None"],
                verbose_only=False,
            )
            return

        try:
            dumped = model_settings.model_dump(exclude_none=True)
        except Exception:
            dumped = str(model_settings)

        self._log_block(
            "LLM SETTINGS DUMP",
            [f"model_settings_dump={dumped!r}"],
            verbose_only=False,
        )

    # =========================================================================
    # Invocación principal
    # =========================================================================

    def _invoke_with_pydantic_ai(
        self,
        request: LlmRuntimeRequest,
    ) -> RawLlmResult:
        output_type = resolve_output_type(request.expected_output_name)

        if output_type is None:
            return self._handle_missing_output_type(request)

        configured_output = self._configured_output_type(output_type)
        model_name = request.model_hint or self._settings.default_model

        system_prompt_text, user_prompt, image_count = parse_messages(
            request.messages,
            supports_vision=self._settings.supports_vision,
        )
        model_settings = self._build_model_settings(request)

        self._log_block(
            "LLM OUTPUT CONFIG",
            [
                f"resolved_output_type={getattr(output_type, '__name__', str(output_type))!r}",
                f"configured_output={configured_output!r}",
                f"structured_output_mode={self._settings.structured_output_mode!r}",
            ],
            verbose_only=False,
        )

        self._debug_dump_model_settings(model_settings)

        self._log_call_start(
            request=request,
            model_name=model_name,
            system_prompt_text=system_prompt_text,
            user_prompt=user_prompt,
            image_count=image_count,
        )

        agent = Agent(
            model=self._build_model(model_name),
            output_type=configured_output,
            system_prompt=system_prompt_text,
            model_settings=model_settings,
        )

        started_at = time.perf_counter()

        self._log_block(
            "LLM DISPATCH",
            [
                f"operation={request.operation_name!r}",
                f"model={model_name!r}",
                f"supports_vision={self._settings.supports_vision!r} image_count={image_count}",
            ],
        )

        try:
            result = self._run_agent(agent=agent, user_prompt=user_prompt)
        except LlmRuntimeError:
            raise
        except Exception as exc:
            self._raise_agent_failure(exc, request, started_at)

        return self._build_success_result(
            result=result,
            request=request,
            model_name=model_name,
            output_type=output_type,
            image_count=image_count,
            started_at=started_at,
        )

    # =========================================================================
    # Flujos auxiliares de invocación
    # =========================================================================

    def _handle_missing_output_type(
        self,
        request: LlmRuntimeRequest,
    ) -> RawLlmResult:
        if self._fallback_runtime is not None:
            return self._raw_result_from_response(
                self._fallback_runtime.invoke(request),
            )

        raise LlmRuntimeError(
            error_class="MissingOutputType",
            message=(
                f"PydanticAI requiere un output_type registrado para "
                f"{request.expected_output_name!r} o un fallback_runtime configurado."
            ),
            retryable=False,
        )

    def _raise_agent_failure(
        self,
        exc: Exception,
        request: LlmRuntimeRequest,
        started_at: float,
    ) -> None:
        """Registra el fallo y relanza como ``LlmRuntimeError``."""
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        failure = self._failure_details(exc)

        self._log_block(
            "LLM FAILURE",
            [
                f"operation={request.operation_name!r}",
                f"origin={failure['origin']!r} type={type(exc).__name__!r}",
                f"elapsed_ms={elapsed_ms:.2f}",
                f"message={failure['message']!r}",
                f"cause_type={failure['cause_type']!r} cause_message={failure['cause_message']!r}",
                f"provider_name={failure['provider_name']!r} provider_message={failure['provider_message']!r}",
                f"provider_code={failure['provider_code']!r} status_code={failure['status_code']!r}",
                f"exception_payload={failure['exception_payload']!r}",
            ],
        )

        raise LlmRuntimeError(
            error_class=type(exc).__name__,
            message=str(exc) or "PydanticAI no pudo completar la llamada.",
            retryable=is_retryable(failure),
        ) from exc

    def _build_success_result(
        self,
        result: Any,
        request: LlmRuntimeRequest,
        model_name: str,
        output_type: type,
        image_count: int,
        started_at: float,
    ) -> RawLlmResult:
        result_payload = build_success_result(
            result=result,
            request=request,
            model_name=model_name,
            output_type=output_type,
            image_count=image_count,
            started_at=started_at,
            settings=self._settings,
        )
        self._log_block(
            "LLM RESULT",
            [
                f"operation={request.operation_name!r}",
                f"model={model_name!r} finish_reason={result_payload.response.get('finish_reason')!r}",
                f"tokens_in={result_payload.input_tokens} "
                f"tokens_out={result_payload.output_tokens} "
                f"total={result_payload.total_tokens}",
            ],
        )
        return result_payload

    # =========================================================================
    # Logging de llamadas
    # =========================================================================

    def _log_call_start(
        self,
        request: LlmRuntimeRequest,
        model_name: str,
        system_prompt_text: str | None,
        user_prompt: str | list[Any],
        image_count: int,
    ) -> None:
        system_len = len(system_prompt_text) if system_prompt_text else 0
        user_len = len(user_prompt) if isinstance(user_prompt, (str, list)) else 0

        self._log_block(
            "LLM CALL",
            [
                f"operation={request.operation_name!r}",
                f"provider={self._settings.provider_name!r} "
                f"backend={self._settings.backend_name!r}",
                f"model={model_name!r} "
                f"expected_output={request.expected_output_name!r}",
                f"messages={len(request.messages)} images={image_count}",
                f"system_len={system_len} user_len={user_len}",
            ],
        )

        if not self._verbose_logging:
            return

        if system_prompt_text:
            self._log_block(
                "LLM SYSTEM PREVIEW",
                [f"preview={system_prompt_text[:400]!r}"],
                verbose_only=True,
            )

        if isinstance(user_prompt, str):
            self._log_block(
                "LLM USER PREVIEW",
                [f"preview={user_prompt[:600]!r}"],
                verbose_only=True,
            )
        else:
            preview = self._serialize_value(user_prompt[:3])
            self._log_block(
                "LLM USER PREVIEW",
                [f"parts_preview={preview!r}"],
                verbose_only=True,
            )

    # =========================================================================
    # Configuración del modelo
    # =========================================================================

    def _configured_output_type(self, output_type: type) -> Any:
        mode = (self._settings.structured_output_mode or "auto").strip().lower()
        wrapper = _STRUCTURED_OUTPUT_MODES.get(mode)
        if wrapper is not None:
            return wrapper(output_type)
        return output_type

    def _build_model_settings(
        self,
        request: LlmRuntimeRequest,
    ) -> OpenAIChatModelSettings | None:
        model_settings, dumped, reasoning, provider = build_model_settings(
            request=request,
            settings=self._settings,
        )

        self._log_block(
            "LLM SETTINGS COMPONENTS",
            [
                f"temperature={request.temperature!r}",
                f"reasoning={reasoning!r}",
                f"provider={provider!r}",
            ],
            verbose_only=False,
        )

        if model_settings is None:
            self._log_block(
                "LLM SETTINGS COMPONENTS",
                ["final_settings=None"],
                verbose_only=False,
            )
            return None

        self._log_block(
            "LLM SETTINGS COMPONENTS",
            [f"final_settings={dumped!r}"],
            verbose_only=False,
        )

        return model_settings

    def _build_reasoning_body(self) -> dict[str, Any] | None:
        from graph_mapper_agent.adapters.llm.runtimes.base.model_building import build_reasoning_body
        return build_reasoning_body(self._settings)

    def _build_provider_body(self) -> dict[str, Any] | None:
        from graph_mapper_agent.adapters.llm.runtimes.base.model_building import build_provider_body
        return build_provider_body(self._settings)

    def _build_model(self, model_name: str):
        return build_model(
            model_name=model_name,
            settings=self._settings,
            client_cache=self._client_cache,
        )

    def _get_or_create_client(self) -> AsyncOpenAI:
        from graph_mapper_agent.adapters.llm.runtimes.base.model_building import get_or_create_client
        return get_or_create_client(
            settings=self._settings,
            client_cache=self._client_cache,
        )

    def _normalized_base_url(self) -> str:
        from graph_mapper_agent.adapters.llm.runtimes.base.model_building import normalized_base_url
        return normalized_base_url(self._settings)

    # =========================================================================
    # Ejecución del agente
    # =========================================================================

    def _run_agent(self, agent: Agent, user_prompt: str | list[Any]) -> Any:
        """Ejecuta el agente síncrono, delegando a un hilo si ya hay loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return agent.run_sync(user_prompt)

        return self._run_agent_in_thread(agent, user_prompt)

    def _run_agent_in_thread(
        self,
        agent: Agent,
        user_prompt: str | list[Any],
    ) -> Any:
        executor = get_agent_executor()

        future = executor.submit(asyncio.run, agent.run(user_prompt))

        try:
            return future.result(timeout=self._settings.timeout_seconds)
        except FuturesTimeoutError as exc:
            future.cancel()
            raise LlmRuntimeError(
                error_class="AgentTimeout",
                message=(
                    f"El agente PydanticAI excedió el timeout de "
                    f"{self._settings.timeout_seconds}s."
                ),
                retryable=True,
            ) from exc

    # =========================================================================
    # Conversión fallback
    # =========================================================================

    def _raw_result_from_response(
        self,
        response: LlmRuntimeResponse,
    ) -> RawLlmResult:
        return raw_result_from_response(response)

    # =========================================================================
    # Manejo de errores
    # =========================================================================

    def _failure_details(self, exc: Exception) -> dict[str, Any]:
        return build_failure_details(
            exc,
            serialize_value=serialize_value,
        )

    @staticmethod
    def _coerce_optional_str(value: object) -> str | None:
        return coerce_optional_str(value)

    @staticmethod
    def _serialize_value(value: object, _depth: int = 0) -> Any:
        return serialize_value(value, _depth)
