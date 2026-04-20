from __future__ import annotations
# graph_mapper_agent/bootstrap/execution_config.py

from dataclasses import dataclass, field
from typing import Any, Mapping
from uuid import uuid4

from graph_mapper_agent.platform.llm.config import (
    LlmRuntimeConfig,
)


@dataclass(frozen=True)
class GuidedGraphMapperConfig:
    jurisdiction_code: str
    document_key: str
    timeout_seconds: int = 200

    target_kind: str = "artifact"
    target_id: str | None = None

    workflow_name: str = "graph_mapper"
    run_id: str = field(default_factory=lambda: f"graph-mapper-{uuid4().hex[:12]}")

    execution_metadata: dict[str, Any] = field(default_factory=dict)

    llm_runtime: LlmRuntimeConfig | None = None
    navigation_perception_llm_runtime: LlmRuntimeConfig | None = None
    goal_validation_llm_runtime: LlmRuntimeConfig | None = None
    evidence_extraction_visual_llm_runtime: LlmRuntimeConfig | None = None
    evidence_extraction_ocr_llm_runtime: LlmRuntimeConfig | None = None
    ledger_database_url: str | None = None

    def validate(self) -> None:
        if not self.jurisdiction_code.strip():
            raise ValueError(
                "GuidedGraphMapperConfig.jurisdiction_code no puede ir vacío."
            )
        if not self.document_key.strip():
            raise ValueError(
                "GuidedGraphMapperConfig.document_key no puede ir vacío."
            )
        if self.timeout_seconds <= 0:
            raise ValueError(
                "GuidedGraphMapperConfig.timeout_seconds debe ser > 0."
            )

        for runtime in (
            self.llm_runtime,
            self.navigation_perception_llm_runtime,
            self.goal_validation_llm_runtime,
            self.evidence_extraction_visual_llm_runtime,
            self.evidence_extraction_ocr_llm_runtime,
        ):
            if runtime is not None:
                runtime.validate()

    @classmethod
    def from_json_dict(cls, data: Mapping[str, Any]) -> "GuidedGraphMapperConfig":
        ledger_payload = data.get("ledger") or {}
        ledger_database_url = None
        if isinstance(ledger_payload, Mapping):
            ledger_database_url = (
                str(ledger_payload.get("database_url") or "").strip() or None
            )

        return cls(
            jurisdiction_code=str(data.get("jurisdiction_code") or "").strip(),
            document_key=str(data.get("document_key") or "").strip(),
            timeout_seconds=_coerce_positive_int(data.get("timeout_seconds"), 120),
            target_kind=str(data.get("target_kind") or "artifact").strip(),
            target_id=(
                str(data.get("target_id")).strip()
                if data.get("target_id") is not None
                else None
            ),
            workflow_name=str(data.get("workflow_name") or "graph_mapper").strip(),
            run_id=str(
                data.get("run_id") or f"graph-mapper-{uuid4().hex[:12]}"
            ).strip(),
            execution_metadata=dict(data.get("execution_metadata") or {}),
            llm_runtime=_parse_runtime_config(data.get("llm_runtime")),
            navigation_perception_llm_runtime=_parse_runtime_config(
                data.get("navigation_perception_llm_runtime")
            ),
            goal_validation_llm_runtime=_parse_runtime_config(
                data.get("goal_validation_llm_runtime")
                or data.get("document_validation_llm_runtime")
            ),
            evidence_extraction_visual_llm_runtime=_parse_runtime_config(
                data.get("evidence_extraction_visual_llm_runtime")
            ),
            evidence_extraction_ocr_llm_runtime=_parse_runtime_config(
                data.get("evidence_extraction_ocr_llm_runtime")
            ),
            ledger_database_url=ledger_database_url,
        )

    @property
    def document_validation_llm_runtime(self) -> LlmRuntimeConfig | None:
        return self.goal_validation_llm_runtime


def _parse_runtime_config(value: object) -> LlmRuntimeConfig | None:
    if not isinstance(value, Mapping):
        return None
    return LlmRuntimeConfig.from_json_dict(value)


def _coerce_positive_int(value: object, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default