from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from graph_mapper_agent.adapters.llm.runtimes.base.message_parsing import (
    parse_json_object_from_text,
)


@dataclass(frozen=True)
class StructuredOutputPreparation:
    parsed_payload: dict[str, Any]
    prepared_payload: dict[str, Any]
    repair_applied: bool = False
    repair_notes: tuple[str, ...] = ()


def parse_structured_output_text(text: str) -> dict[str, Any]:
    return parse_json_object_from_text(text)


def prepare_structured_output_payload(
    *,
    expected_output_name: str | None,
    parsed_payload: dict[str, Any],
) -> StructuredOutputPreparation:
    repaired_payload = dict(parsed_payload)
    repair_notes: list[str] = []

    if expected_output_name == "navigation_perception_output":
        _apply_navigation_perception_repairs(
            repaired_payload,
            repair_notes,
        )

    return StructuredOutputPreparation(
        parsed_payload=dict(parsed_payload),
        prepared_payload=repaired_payload,
        repair_applied=bool(repair_notes),
        repair_notes=tuple(repair_notes),
    )


def validate_prepared_output(
    *,
    output_type: type[BaseModel],
    prepared_payload: dict[str, Any],
) -> BaseModel:
    return output_type.model_validate(prepared_payload)


def _apply_navigation_perception_repairs(
    payload: dict[str, Any],
    repair_notes: list[str],
) -> None:
    if "confidence" not in payload:
        payload["confidence"] = 0.5
        repair_notes.append("navigation_perception_default_confidence")

    for key in (
        "best_immediate_condition_labels",
        "visual_recovery_hints",
        "curated_candidates",
    ):
        if key not in payload:
            payload[key] = []
            repair_notes.append(f"navigation_perception_default_{key}")
