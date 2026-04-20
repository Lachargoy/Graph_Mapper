from __future__ import annotations
#graph_mapper_agent/application/services/finding_extractor.py
import unicodedata
from dataclasses import dataclass
from uuid import uuid4

from graph_mapper_agent.domain.findings import (
    FindingEvidence,
    FindingKind,
    FindingRecord,
)
from graph_mapper_agent.application.navigation_perception.models import (
    CurrentNodeGoalMatch,
)


@dataclass(slots=True, frozen=True)
class FindingExtractor:
    def from_open_artifact(
        self,
        *,
        node_id: str,
        source_url: str,
        edge_id: str | None,
        edge_label: str,
        artifact_text: str | None,
        artifact_url: str | None,
        local_perception: dict[str, object] | None = None,
        source_action: str = "open_artifact",
    ) -> FindingRecord | None:
        text = (artifact_text or "").strip()
        resolved_artifact_url = (artifact_url or "").strip()
        local_perception_summary = _optional_str(
            None if local_perception is None else local_perception.get("summary")
        ) or ""
        local_perception_status = _optional_str(
            None if local_perception is None else local_perception.get("status")
        )
        local_perception_confidence = _coerce_optional_float(
            None if local_perception is None else local_perception.get("confidence")
        )
        local_perception_metadata = (
            dict(local_perception.get("metadata") or {})
            if isinstance(local_perception, dict)
            else {}
        )

        if not text and not resolved_artifact_url and not local_perception_summary:
            return None

        snippet_parts = []
        if text:
            snippet_parts.append(text[:220].replace("\n", " ").strip())
        if local_perception_summary:
            snippet_parts.append(local_perception_summary[:180])
        snippet = " | ".join(part for part in snippet_parts if part)[:220]

        label = edge_label.strip() if edge_label else ""
        value = resolved_artifact_url or label or "artifact"

        explicit_year = local_perception_metadata.get("validated_year")
        inferred_year = (
            explicit_year
            if isinstance(explicit_year, int)
            else self._infer_year(
                resolved_artifact_url,
                label,
                text[:500],
                local_perception_summary,
            )
        )

        is_pdf = self._looks_like_pdf(resolved_artifact_url)
        explicit_family = _optional_str(
            local_perception_metadata.get("validated_document_family")
        )
        document_family = explicit_family or self._infer_document_family(
            resolved_artifact_url,
            label,
            text[:500],
            local_perception_summary,
        )

        confidence = 0.70
        if local_perception_confidence is not None:
            confidence = max(confidence, min(0.92, local_perception_confidence))

        return FindingRecord(
            finding_id=f"finding_{uuid4().hex[:12]}",
            kind=FindingKind.DOCUMENT,
            label=label or value,
            value=value,
            confidence=confidence,
            evidence=(
                FindingEvidence(
                    source_node_id=node_id,
                    source_url=source_url,
                    edge_id=edge_id,
                    snippet=snippet,
                ),
            ),
            attributes={
                "artifact_url": resolved_artifact_url or None,
                "has_text": bool(text),
                "text_length": len(text),
                "document_family": document_family,
                "year": inferred_year,
                "is_pdf": is_pdf,
                "source_action": source_action,
                "validation_status": local_perception_metadata.get("validation_status")
                or local_perception_status,
                "matched_condition_ids": tuple(
                    str(item)
                    for item in (local_perception_metadata.get("matched_condition_ids") or ())
                    if str(item).strip()
                ),
                "validated_document_family": explicit_family,
                "validated_year": explicit_year if isinstance(explicit_year, int) else None,
                "local_perception_confidence": local_perception_confidence,
                "local_perception_summary": local_perception_summary or None,
            },
        )

    def from_download_artifact(
        self,
        *,
        node_id: str,
        source_url: str,
        edge_id: str | None,
        edge_label: str,
        artifact_url: str | None,
        download_result: dict[str, object],
    ) -> FindingRecord | None:
        resolved_artifact_url = (artifact_url or "").strip()
        label = edge_label.strip() if edge_label else ""

        filename = (
            _optional_str(download_result.get("filename"))
            or _optional_str(download_result.get("storage_ref"))
            or ""
        ).strip()

        candidate_url = _optional_str(download_result.get("candidate_url")) or ""
        download_url = _optional_str(download_result.get("download_url")) or ""

        if not resolved_artifact_url and not filename and not label:
            return None

        value = resolved_artifact_url or filename or label or "artifact"
        evidence_text = " | ".join(
            part for part in [label, filename, resolved_artifact_url] if part
        ).strip()

        inferred_year = self._infer_year(
            resolved_artifact_url,
            label,
            filename,
            candidate_url,
            download_url,
        )
        is_pdf = self._looks_like_pdf(resolved_artifact_url or filename or download_url)
        document_family = "pdf_document" if is_pdf else None

        return FindingRecord(
            finding_id=f"finding_{uuid4().hex[:12]}",
            kind=FindingKind.DOCUMENT,
            label=label or filename or value,
            value=value,
            confidence=0.62,
            evidence=(
                FindingEvidence(
                    source_node_id=node_id,
                    source_url=source_url,
                    edge_id=edge_id,
                    snippet=evidence_text[:220],
                ),
            ),
            attributes={
                "artifact_url": resolved_artifact_url or None,
                "candidate_url": candidate_url or None,
                "download_url": download_url or None,
                "filename": filename or None,
                "has_text": False,
                "text_length": 0,
                "document_family": document_family,
                "year": inferred_year,
                "is_pdf": is_pdf,
                "source_action": "download_artifact",
                "validation_status": None,
                "matched_condition_ids": (),
            },
        )

    def from_navigation_perception_current_node(
        self,
        *,
        node_id: str,
        source_url: str,
        match: CurrentNodeGoalMatch,
        summary: str | None = None,
    ) -> FindingRecord | None:
        document_family = str(match.document_family or "").strip()
        if not document_family:
            return None

        label = (
            next(
                (value for value in match.supports_condition_labels if str(value).strip()),
                None,
            )
            or document_family
        )
        artifact_url = (match.artifact_url or source_url or "").strip() or None
        snippet = " | ".join(
            part
            for part in (
                match.rationale or "",
                summary or "",
            )
            if part
        )[:220]
        inferred_year = self._infer_year(
            artifact_url,
            label,
            summary or "",
            match.rationale or "",
        )

        confidence = 0.68 if match.confidence is None else float(match.confidence)

        return FindingRecord(
            finding_id=f"finding_{uuid4().hex[:12]}",
            kind=FindingKind.DOCUMENT,
            label=label,
            value=artifact_url or label,
            confidence=confidence,
            evidence=(
                FindingEvidence(
                    source_node_id=node_id,
                    source_url=source_url,
                    edge_id=None,
                    snippet=snippet,
                ),
            ),
            attributes={
                "artifact_url": artifact_url,
                "has_text": False,
                "text_length": 0,
                "document_family": document_family,
                "year": inferred_year,
                "is_pdf": self._looks_like_pdf(artifact_url),
                "source_action": "navigation_perception_current_node",
                "supports_condition_labels": tuple(match.supports_condition_labels),
            },
        )

    def _infer_year(self, *parts: object) -> int | None:
        for year in (2026, 2025, 2024, 2023, 2022, 2021, 2020):
            needle = str(year)
            for part in parts:
                text = str(part or "")
                if needle in text:
                    return year
        return None

    def _looks_like_pdf(self, text: object) -> bool:
        value = str(text or "").strip().lower()
        return value.endswith(".pdf") or ".pdf?" in value or ".pdf#" in value

    def _infer_document_family(self, *parts: object) -> str | None:
        merged = " ".join(_normalize_text(part) for part in parts)
        if ".pdf" in merged:
            return "pdf_document"
        return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_text(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))