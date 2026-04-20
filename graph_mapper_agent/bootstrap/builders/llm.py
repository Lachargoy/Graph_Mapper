#graph_mapper_agent/bootstrap/builders/llm.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from graph_mapper_agent.adapters.llm.composition.runtime_factory import (
    build_llm_runtime,
)
from graph_mapper_agent.platform.llm.config import (
    LlmRuntimeConfig,
)
from graph_mapper_agent.platform.llm.resolve_runtime_plan import (
    resolve_runtime_plan,
)
from graph_mapper_agent.ledger.application.invoke_llm_with_ledger_use_case import (
    InvokeLlmWithLedgerUseCase,
)

from ..timing import timed


@dataclass(frozen=True)
class LlmRuntimeBundle:
    runtime: Any
    provider_name: str
    invoke_llm_use_case: InvokeLlmWithLedgerUseCase | None


def build_llm_runtime_bundle(
    *,
    llm_runtime_config: LlmRuntimeConfig | None,
    expected_output_name: str | None,
    ledger: object | None = None,
    label_prefix: str = "llm",
) -> LlmRuntimeBundle | None:
    if llm_runtime_config is None:
        return None

    plan = timed(
        f"{label_prefix}.resolve_runtime_plan",
        lambda: resolve_runtime_plan(
            llm_runtime_config,
            expected_output_name=expected_output_name,
            tools_requested=False,
        ),
    )

    factory_result = timed(
        f"{label_prefix}.build_llm_runtime",
        lambda: build_llm_runtime(plan),
    )

    invoke_llm_use_case = None
    if ledger is not None:
        invoke_llm_use_case = InvokeLlmWithLedgerUseCase(
            ledger=ledger,
            llm_runtime=factory_result.runtime,
            provider_name=factory_result.provider_name,
        )

    return LlmRuntimeBundle(
        runtime=factory_result.runtime,
        provider_name=factory_result.provider_name,
        invoke_llm_use_case=invoke_llm_use_case,
    )
