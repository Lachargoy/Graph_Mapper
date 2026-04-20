from __future__ import annotations
#graph_mapper_agent/application/services/decision/llm_use_case.py
import json
import os
from dataclasses import dataclass, field
from typing import Any

from graph_mapper_agent.domain.ports.llm_runtime_port import (
    LlmRuntimeRequest,
)
from graph_mapper_agent.ledger.application.invoke_llm_with_ledger_use_case import (
    InvokeLlmWithLedgerUseCase,
)
from graph_mapper_agent.ledger.domain.actor_kind import ActorKind
from graph_mapper_agent.ledger.domain.run_correlation import (
    RunCorrelation,
)
from graph_mapper_agent.ledger.domain.target_ref import TargetRef


_VERBOSE = os.getenv("AITHER_GRAPH_MAPPER_VERBOSE", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_ANSI_ENABLED = os.getenv("AITHER_NO_COLOR", "").strip().lower() not in {
    "1",
    "true",
    "yes",
    "on",
}
_ANSI_RESET = "\033[0m"
_ANSI_GRAPH = "\033[38;5;39m"


def _fmt(prefix: str, msg: str) -> str:
    if not _ANSI_ENABLED:
        return f"[{prefix}] {msg}"
    return f"{_ANSI_GRAPH}[{prefix}]{_ANSI_RESET} {msg}"


def _log_block(title: str, lines: list[str], *, verbose_only: bool = False) -> None:
    if verbose_only and not _VERBOSE:
        return
    print(f"[graph_mapper.llm] {title}", flush=True)
    for line in lines:
        print(f"[graph_mapper.llm]   {line}", flush=True)


def _preview(text: str, limit: int = 240) -> str:
    normalized = str(text).replace("\n", "\\n")
    if len(normalized) > limit:
        return normalized[:limit].rstrip() + "..."
    return normalized


@dataclass(frozen=True)
class GraphMapperDecisionLlmRequest:
    prompt: str
    run: RunCorrelation
    actor: ActorKind
    target: TargetRef | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphMapperDecisionLlmUseCase:
    invoke_llm_use_case: InvokeLlmWithLedgerUseCase
    prompt_version: str = "graph_mapper_v3"
    structured_output_name: str = "graph_mapper_navigation_decision"

    def decide(
        self,
        request: GraphMapperDecisionLlmRequest,
    ) -> dict[str, object]:
        system_prompt = _system_prompt()

        _log_block(
            "GRAPH_MAPPER_DECISION REQUEST",
            [
                f"prompt_len={len(request.prompt)}",
                f"prompt_preview={_preview(request.prompt)!r}",
            ],
        )

        llm_request = LlmRuntimeRequest(
            operation_name="graph_mapper_navigation_decision",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.prompt},
            ],
            expected_output_name=self.structured_output_name,
            metadata={
                **dict(request.metadata),
                "prompt_version": self.prompt_version,
                "structured_output_name": self.structured_output_name,
            },
        )

        llm_response = self.invoke_llm_use_case.execute(
            run=request.run,
            actor=request.actor,
            request=llm_request,
            target=request.target,
            metadata={
                **dict(request.metadata),
                "prompt_version": self.prompt_version,
                "structured_output_name": self.structured_output_name,
                "expected_output": _expected_output_contract(),
            },
        )

        return _extract_decision_payload_from_response(llm_response)


def _system_prompt() -> str:
    return (
        "You are a navigation decision-maker for the graph_mapper lane.\n"
        "You must respond ONLY with valid JSON.\n"
        "Allowed actions: "
        '["refine_navigation_perception","validate_current_content","follow_edge","download_artifact","open_artifact","mark_exhausted","success"].\n'
        "If you choose follow_edge, download_artifact, or open_artifact, you must include a valid "
        '"edge_id".\n'
        "validate_current_content does not use edge_id and validates the local evidence already available in the current node.\n"
        "Use refine_navigation_perception when the current node is ambiguous, has too many candidates, or needs better local reading before selecting an edge.\n"
        "Your goal is NOT to explore for the sake of exploring: you must maximize useful progress, avoid loops, and use structural and tactical memory correctly.\n"
        "You must distinguish between:\n"
        '- "decision_rationale": brief justification for the chosen action\n'
        '- "scratchpad_update": optional update to the tactical scratchpad\n'
        "If the current page no longer offers real progress and the remaining content appears repetitive, you must use 'mark_exhausted'.\n"
        'Exact format: {"action":"...","edge_id":"...","decision_rationale":"...","confidence":0.0,"scratchpad_update":{"working_plan":"...","tactical_observations":"..."}}'
    )


def _expected_output_contract() -> dict[str, object]:
    return {
        "type": "json_object",
        "schema_name": "graph_mapper_navigation_decision",
        "required_fields": ["action"],
        "optional_fields": [
            "edge_id",
            "decision_rationale",
            "confidence",
            "scratchpad_update",
        ],
        "allowed_actions": [
            "refine_navigation_perception",
            "validate_current_content",
            "follow_edge",
            "download_artifact",
            "open_artifact",
            "mark_exhausted",
            "success",
        ],
    }


def _extract_decision_payload_from_response(llm_response: Any) -> dict[str, object]:
    interaction = getattr(llm_response, "interaction", None)
    if interaction is None:
        raise TypeError("LlmRuntimeResponse does not contain interaction")

    response_payload = getattr(interaction, "response", None)
    if not isinstance(response_payload, dict):
        raise TypeError("LlmRuntimeResponse.interaction.response must be dict[str, object]")

    candidate_keys = (
        "parsed_response",
        "output",
        "parsed_output",
        "structured_output",
        "json_output",
        "content",
        "text",
        "response_text",
        "completion",
    )

    for key in candidate_keys:
        if key in response_payload:
            try:
                return _extract_decision_payload(response_payload[key])
            except Exception:
                pass

    message = response_payload.get("message")
    if isinstance(message, dict):
        message_content = message.get("content")
        if message_content is not None:
            try:
                return _extract_decision_payload(message_content)
            except Exception:
                pass

    if "action" in response_payload:
        return _extract_decision_payload(response_payload)

    raise TypeError(
        "Could not extract decision payload from LlmRuntimeResponse.interaction.response"
    )


def _extract_decision_payload(output: Any) -> dict[str, object]:
    if isinstance(output, dict):
        return dict(output)

    if isinstance(output, str):
        text = output.strip()
        if not text:
            raise ValueError("LLM output is empty")

        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise TypeError("LLM JSON output must be a JSON object")
        return dict(parsed)

    model_dump = getattr(output, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict):
            return dict(dumped)

    raise TypeError(f"Unsupported structured output type: {type(output)!r}")


__all__ = [
    "GraphMapperDecisionLlmRequest",
    "GraphMapperDecisionLlmUseCase",
]