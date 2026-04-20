from __future__ import annotations
# ./platform/llm/config.py

import os
from dataclasses import dataclass, replace
from typing import Any, Literal, Mapping, cast


LlmBackendName = Literal[
    "ollama",
    "chatopenai_direct",
    "pydantic_ai_adapter",
    "pydantic_ai_openrouter",
    "openrouter_chatopenai",
]

_SUPPORTED_BACKENDS = {
    "ollama",
    "chatopenai_direct",
    "pydantic_ai_adapter",
    "pydantic_ai_openrouter",
    "openrouter_chatopenai",
}

_LM_STUDIO_BACKENDS = {
    "chatopenai_direct",
    "pydantic_ai_adapter",
}

_OLLAMA_BACKENDS = {
    "ollama",
}

_OPENROUTER_BACKENDS = {
    "pydantic_ai_openrouter",
    "openrouter_chatopenai",
}


@dataclass(frozen=True)
class LlmRuntimeConfigPatch:
    """
    Override parcial.
    Usa None para significar: 'no tocar este campo'.
    """
    backend: LlmBackendName | None = None
    base_url: str | None = None
    default_model: str | None = None
    api_key: str | None = None
    timeout_seconds: int | None = None
    enable_reasoning: bool | None = None
    reasoning_effort: str | None = None
    reasoning_max_tokens: int | None = None
    reasoning_exclude: bool | None = None
    structured_output_mode: str | None = None
    provider_require_parameters: bool | None = None
    provider_allow_fallbacks: bool | None = None
    provider_order: tuple[str, ...] | None = None
    supports_vision: bool | None = None

    @classmethod
    def from_json_dict(cls, data: Mapping[str, Any]) -> "LlmRuntimeConfigPatch":
        return cls(
            backend=_coerce_optional_backend(data.get("backend")),
            base_url=_coerce_str(data.get("base_url")),
            default_model=_coerce_str(data.get("default_model") or data.get("model")),
            api_key=_coerce_str(data.get("api_key")),
            timeout_seconds=_coerce_optional_int(data.get("timeout_seconds")),
            enable_reasoning=_coerce_optional_bool(data.get("enable_reasoning")),
            reasoning_effort=_coerce_str(data.get("reasoning_effort")),
            reasoning_max_tokens=_coerce_optional_int(data.get("reasoning_max_tokens")),
            reasoning_exclude=_coerce_optional_bool(data.get("reasoning_exclude")),
            structured_output_mode=_coerce_str(data.get("structured_output_mode")),
            provider_require_parameters=_coerce_optional_bool(
                data.get("provider_require_parameters", data.get("require_parameters"))
            ),
            provider_allow_fallbacks=_coerce_optional_bool(
                data.get("provider_allow_fallbacks", data.get("allow_fallbacks"))
            ),
            provider_order=_coerce_optional_csv_tuple(data.get("provider_order")),
            supports_vision=_coerce_optional_bool(data.get("supports_vision")),
        )


@dataclass(frozen=True)
class LlmRuntimeConfig:
    """
    Config completa/base para un runtime LLM.
    Los defaults aquí son defaults de configuración, no necesariamente los
    defaults efectivos finales del provider. Esos se terminan de resolver en
    resolve_runtime_plan().
    """
    backend: LlmBackendName = "pydantic_ai_adapter"
    base_url: str | None = None
    default_model: str | None = None
    api_key: str | None = None
    timeout_seconds: int | None = None
    enable_reasoning: bool = False
    reasoning_effort: str | None = None
    reasoning_max_tokens: int | None = None
    reasoning_exclude: bool = False
    structured_output_mode: str | None = None
    provider_require_parameters: bool = False
    provider_allow_fallbacks: bool = True
    provider_order: tuple[str, ...] = ()
    supports_vision: bool = False

    @property
    def model(self) -> str | None:
        return self.default_model

    @property
    def require_parameters(self) -> bool:
        return self.provider_require_parameters

    @property
    def allow_fallbacks(self) -> bool:
        return self.provider_allow_fallbacks

    @classmethod
    def from_env(cls) -> "LlmRuntimeConfig":
        backend = _coerce_backend(
            _env("AITHER_LLM_BACKEND", "pydantic_ai_adapter"),
            "pydantic_ai_adapter",
        )
        supports_vision = _env_bool("AITHER_LLM_SUPPORTS_VISION", False)

        if backend in _OPENROUTER_BACKENDS:
            return cls(
                backend=backend,
                base_url=_optional_env("AITHER_OPENROUTER_BASE_URL"),
                default_model=_optional_env("AITHER_OPENROUTER_MODEL"),
                api_key=_optional_env("AITHER_OPENROUTER_API_KEY"),
                timeout_seconds=_optional_env_int("AITHER_OPENROUTER_TIMEOUT_SECONDS"),
                enable_reasoning=_env_bool("AITHER_OPENROUTER_ENABLE_REASONING", False),
                reasoning_effort=_optional_env("AITHER_OPENROUTER_REASONING_EFFORT"),
                reasoning_max_tokens=_optional_env_int(
                    "AITHER_OPENROUTER_REASONING_MAX_TOKENS"
                ),
                reasoning_exclude=_env_bool(
                    "AITHER_OPENROUTER_REASONING_EXCLUDE", False
                ),
                structured_output_mode=_optional_env(
                    "AITHER_OPENROUTER_STRUCTURED_OUTPUT_MODE"
                ),
                provider_require_parameters=_env_bool(
                    "AITHER_OPENROUTER_REQUIRE_PARAMETERS", False
                ),
                provider_allow_fallbacks=_env_bool(
                    "AITHER_OPENROUTER_ALLOW_FALLBACKS", True
                ),
                provider_order=_env_csv("AITHER_OPENROUTER_PROVIDER_ORDER"),
                supports_vision=supports_vision,
            )

        if backend in _OLLAMA_BACKENDS:
            return cls(
                backend=backend,
                base_url=_optional_env("AITHER_OLLAMA_BASE_URL"),
                default_model=_optional_env("AITHER_OLLAMA_MODEL"),
                api_key=_optional_env("AITHER_OLLAMA_API_KEY"),
                timeout_seconds=_optional_env_int("AITHER_OLLAMA_TIMEOUT_SECONDS"),
                supports_vision=supports_vision,
            )

        return cls(
            backend=backend,
            base_url=_optional_env("AITHER_LM_STUDIO_URL"),
            default_model=_optional_env("AITHER_LM_STUDIO_MODEL"),
            api_key=_optional_env("AITHER_LM_STUDIO_API_KEY"),
            timeout_seconds=_optional_env_int("AITHER_LM_STUDIO_TIMEOUT_SECONDS"),
            supports_vision=supports_vision,
        )

    @classmethod
    def from_json_dict(cls, data: Mapping[str, Any]) -> "LlmRuntimeConfig":
        return cls(
            backend=_coerce_backend(
                data.get("backend"),
                "pydantic_ai_adapter",
            ),
            base_url=_coerce_str(data.get("base_url")),
            default_model=_coerce_str(data.get("default_model") or data.get("model")),
            api_key=_coerce_str(data.get("api_key")),
            timeout_seconds=_coerce_optional_int(data.get("timeout_seconds")),
            enable_reasoning=_coerce_bool(data.get("enable_reasoning"), False),
            reasoning_effort=_coerce_str(data.get("reasoning_effort")),
            reasoning_max_tokens=_coerce_optional_int(data.get("reasoning_max_tokens")),
            reasoning_exclude=_coerce_bool(data.get("reasoning_exclude"), False),
            structured_output_mode=_coerce_str(data.get("structured_output_mode")),
            provider_require_parameters=_coerce_bool(
                data.get("provider_require_parameters", data.get("require_parameters")),
                False,
            ),
            provider_allow_fallbacks=_coerce_bool(
                data.get("provider_allow_fallbacks", data.get("allow_fallbacks")),
                True,
            ),
            provider_order=_coerce_csv_tuple(data.get("provider_order")),
            supports_vision=_coerce_bool(data.get("supports_vision"), False),
        )

    def merge(self, override: LlmRuntimeConfigPatch) -> "LlmRuntimeConfig":
        """
        Mezcla segura con override parcial.
        Si necesitas overrides parciales, usa LlmRuntimeConfigPatch.
        """
        return LlmRuntimeConfig(
            backend=override.backend if override.backend is not None else self.backend,
            base_url=override.base_url if override.base_url is not None else self.base_url,
            default_model=(
                override.default_model
                if override.default_model is not None
                else self.default_model
            ),
            api_key=override.api_key if override.api_key is not None else self.api_key,
            timeout_seconds=(
                override.timeout_seconds
                if override.timeout_seconds is not None
                else self.timeout_seconds
            ),
            enable_reasoning=(
                override.enable_reasoning
                if override.enable_reasoning is not None
                else self.enable_reasoning
            ),
            reasoning_effort=(
                override.reasoning_effort
                if override.reasoning_effort is not None
                else self.reasoning_effort
            ),
            reasoning_max_tokens=(
                override.reasoning_max_tokens
                if override.reasoning_max_tokens is not None
                else self.reasoning_max_tokens
            ),
            reasoning_exclude=(
                override.reasoning_exclude
                if override.reasoning_exclude is not None
                else self.reasoning_exclude
            ),
            structured_output_mode=(
                override.structured_output_mode
                if override.structured_output_mode is not None
                else self.structured_output_mode
            ),
            provider_require_parameters=(
                override.provider_require_parameters
                if override.provider_require_parameters is not None
                else self.provider_require_parameters
            ),
            provider_allow_fallbacks=(
                override.provider_allow_fallbacks
                if override.provider_allow_fallbacks is not None
                else self.provider_allow_fallbacks
            ),
            provider_order=(
                override.provider_order
                if override.provider_order is not None
                else self.provider_order
            ),
            supports_vision=(
                override.supports_vision
                if override.supports_vision is not None
                else self.supports_vision
            ),
        )

    def with_api_key(self, api_key: str | None) -> "LlmRuntimeConfig":
        return replace(self, api_key=api_key)

    def resolve_defaults(self) -> "LlmRuntimeConfig":
        resolved = self

        if resolved.backend in _OLLAMA_BACKENDS:
            return replace(
                resolved,
                base_url=resolved.base_url or "http://127.0.0.1:11434",
                default_model=resolved.default_model or "llava",
                timeout_seconds=_positive_or_default(resolved.timeout_seconds, 180),
                structured_output_mode=None,
                provider_order=(),
                provider_require_parameters=False,
                provider_allow_fallbacks=True,
                enable_reasoning=False,
                reasoning_effort=None,
                reasoning_max_tokens=None,
                reasoning_exclude=False,
            )

        if resolved.backend in _LM_STUDIO_BACKENDS:
            return replace(
                resolved,
                base_url=resolved.base_url or "http://192.168.1.222:1234",
                default_model=resolved.default_model or "local-model",
                timeout_seconds=_positive_or_default(resolved.timeout_seconds, 180),
                structured_output_mode=None,
                provider_order=(),
                provider_require_parameters=False,
                provider_allow_fallbacks=True,
                enable_reasoning=False,
                reasoning_effort=None,
                reasoning_max_tokens=None,
                reasoning_exclude=False,
            )

        current_key = resolved.api_key or os.getenv("AITHER_OPENROUTER_API_KEY")
        return replace(
            resolved,
            base_url=resolved.base_url or "https://openrouter.ai/api/v1",
            default_model=resolved.default_model or "qwen/qwen3.5-27b",
            api_key=current_key,
            timeout_seconds=_positive_or_default(resolved.timeout_seconds, 180),
            structured_output_mode=(
                (resolved.structured_output_mode or "auto").strip().lower()
            ),
        )

    def validate(self) -> None:
        """
        Validación ligera para config cruda.
        No obliga base_url/model todavía, porque esos pueden resolverse después
        en resolve_runtime_plan() o resolve_defaults().
        """
        if self.backend not in _SUPPORTED_BACKENDS:
            raise ValueError(f"Backend LLM no soportado: {self.backend}")

        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("LlmRuntimeConfig.timeout_seconds debe ser > 0 si se proporciona.")

        if self.reasoning_max_tokens is not None and self.reasoning_max_tokens <= 0:
            raise ValueError(
                "LlmRuntimeConfig.reasoning_max_tokens debe ser > 0 si se proporciona."
            )

        if self.reasoning_effort is not None and not self.reasoning_effort.strip():
            raise ValueError(
                "LlmRuntimeConfig.reasoning_effort no puede ser cadena vacía."
            )

        if (
            self.structured_output_mode is not None
            and not self.structured_output_mode.strip()
        ):
            raise ValueError(
                "LlmRuntimeConfig.structured_output_mode no puede ser cadena vacía."
            )

    def validate_resolved(self) -> None:
        """
        Validación estricta para una config ya resuelta/normalizada.
        """
        self.validate()

        if not (self.base_url or "").strip():
            raise ValueError("LlmRuntimeConfig requiere `base_url` no vacío.")

        if not (self.default_model or "").strip():
            raise ValueError("LlmRuntimeConfig requiere `default_model` no vacío.")

        if self.timeout_seconds is None or self.timeout_seconds <= 0:
            raise ValueError("LlmRuntimeConfig requiere `timeout_seconds` > 0.")

        if self.backend in _OPENROUTER_BACKENDS:
            if not (self.structured_output_mode or "").strip():
                raise ValueError(
                    "LlmRuntimeConfig requiere `structured_output_mode` no vacío para OpenRouter."
                )


def _env(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _optional_env(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _optional_env_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_csv(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _coerce_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on"}


def _coerce_optional_bool(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return None
    return text in {"1", "true", "yes", "on"}


def _coerce_csv_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _coerce_optional_csv_tuple(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        parts = tuple(part.strip() for part in value.split(",") if part.strip())
        return parts
    if isinstance(value, (list, tuple)):
        parts = tuple(str(item).strip() for item in value if str(item).strip())
        return parts
    return None


def _coerce_backend(
    value: object,
    default: LlmBackendName = "pydantic_ai_adapter",
) -> LlmBackendName:
    text = _coerce_str(value)
    if text in _SUPPORTED_BACKENDS:
        return cast(LlmBackendName, text)
    return default


def _coerce_optional_backend(value: object) -> LlmBackendName | None:
    text = _coerce_str(value)
    if text is None:
        return None
    if text in _SUPPORTED_BACKENDS:
        return cast(LlmBackendName, text)
    return None


def _positive_or_default(value: int | None, default: int) -> int:
    if value is None or value <= 0:
        return default
    return value