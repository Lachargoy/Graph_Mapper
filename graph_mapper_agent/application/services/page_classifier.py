from __future__ import annotations
#graph_mapper_agent/application/services/page_classifier.py
from dataclasses import dataclass, field

from graph_mapper_agent.domain.page_type import PageType


@dataclass(frozen=True)
class PageClassification:
    page_type: PageType
    confidence: float
    diagnostics: dict[str, object] = field(default_factory=dict)


class PageClassifier:
    def classify(
        self,
        *,
        page_url: str,
        candidates: list[dict[str, object]],
        inspection_metadata: dict[str, object] | None,
        frame_summaries: list[dict[str, object]],
    ) -> PageClassification:
        metadata = inspection_metadata or {}
        selected_frame = _metadata_dict(metadata, "selected_frame") or {}

        text_excerpt = _optional_str(selected_frame.get("text_excerpt")) or ""
        page_title = _optional_str(metadata.get("page_title")) or ""
        dominant_frame_url = _optional_str(metadata.get("dominant_frame_url"))
        has_frames = len(frame_summaries) > 1

        candidate_count = len(candidates)
        has_table_context = any(_has_table_context(candidate) for candidate in candidates)

        artifact_candidate_count = sum(
            1 for candidate in candidates if _is_artifact_candidate(candidate)
        )
        page_candidate_count = sum(
            1 for candidate in candidates if _is_page_candidate(candidate)
        )
        bridge_candidate_count = sum(
            1 for candidate in candidates if _is_bridge_candidate(candidate)
        )
        direct_download_count = sum(
            1 for candidate in candidates if _is_direct_download_candidate(candidate)
        )
        viewer_like_count = sum(
            1 for candidate in candidates if _is_viewer_like_candidate(candidate)
        )
        same_host_count = sum(
            1 for candidate in candidates if _is_same_host_candidate(candidate)
        )

        joined_text = " ".join(
            filter(
                None,
                [
                    page_url.lower(),
                    page_title.lower(),
                    text_excerpt.lower(),
                    " ".join(
                        str(candidate.get("semantic_label") or "").lower()
                        for candidate in candidates[:12]
                    ),
                    " ".join(
                        str(candidate.get("table_heading") or "").lower()
                        for candidate in candidates[:8]
                    ),
                    " ".join(
                        str(candidate.get("adjacent_cell_text") or "").lower()
                        for candidate in candidates[:8]
                    ),
                ],
            )
        )

        diagnostics: dict[str, object] = {
            "candidate_count": candidate_count,
            "artifact_candidate_count": artifact_candidate_count,
            "page_candidate_count": page_candidate_count,
            "bridge_candidate_count": bridge_candidate_count,
            "direct_download_count": direct_download_count,
            "viewer_like_count": viewer_like_count,
            "same_host_count": same_host_count,
            "has_frames": has_frames,
            "has_table_context": has_table_context,
            "dominant_frame_url": dominant_frame_url,
        }

        if has_frames and dominant_frame_url and dominant_frame_url != page_url:
            return PageClassification(
                page_type=PageType.FRAMESET_INDEX,
                confidence=0.84,
                diagnostics={**diagnostics, "matched_rule": "frameset_index"},
            )

        if any(
            token in joined_text
            for token in (
                "noticia",
                "boletin",
                "boletín",
                "comunicado",
                "news",
                "press",
                "blog",
                "article",
            )
        ):
            if any(
                token in joined_text
                for token in (
                    "publicado",
                    "autor",
                    "redaccion",
                    "redacción",
                    "published",
                    "by ",
                    "posted",
                )
            ):
                return PageClassification(
                    page_type=PageType.NEWS_ARTICLE_PAGE,
                    confidence=0.77,
                    diagnostics={**diagnostics, "matched_rule": "news_article_page"},
                )
            return PageClassification(
                page_type=PageType.NEWS_LISTING,
                confidence=0.72,
                diagnostics={**diagnostics, "matched_rule": "news_listing"},
            )

        if has_table_context and candidate_count >= 2:
            if any(
                token in joined_text
                for token in (
                    "enero",
                    "febrero",
                    "marzo",
                    "abril",
                    "mayo",
                    "junio",
                    "julio",
                    "agosto",
                    "septiembre",
                    "octubre",
                    "noviembre",
                    "diciembre",
                    "january",
                    "february",
                    "march",
                    "april",
                    "may",
                    "june",
                    "july",
                    "august",
                    "september",
                    "october",
                    "november",
                    "december",
                    "calendar",
                    "calendario",
                    "fecha",
                    "date",
                )
            ):
                return PageClassification(
                    page_type=PageType.CALENDAR_INDEX,
                    confidence=0.83,
                    diagnostics={**diagnostics, "matched_rule": "calendar_index"},
                )
            return PageClassification(
                page_type=PageType.TABLE_INDEX,
                confidence=0.81,
                diagnostics={**diagnostics, "matched_rule": "table_index"},
            )

        if bridge_candidate_count >= 2 and direct_download_count <= 2:
            return PageClassification(
                page_type=PageType.BRIDGE_DOWNLOAD_PAGE,
                confidence=0.74,
                diagnostics={**diagnostics, "matched_rule": "bridge_download_page"},
            )

        if direct_download_count >= 3:
            return PageClassification(
                page_type=PageType.DOCUMENT_DETAIL_PAGE,
                confidence=0.70,
                diagnostics={**diagnostics, "matched_rule": "document_detail_page"},
            )

        if artifact_candidate_count >= 3 and page_candidate_count <= 3:
            return PageClassification(
                page_type=PageType.ARTIFACT_HUB,
                confidence=0.72,
                diagnostics={**diagnostics, "matched_rule": "artifact_hub"},
            )

        if (
            candidate_count >= 5
            and artifact_candidate_count >= 1
            and page_candidate_count >= 2
        ):
            return PageClassification(
                page_type=PageType.MIXED_INDEX,
                confidence=0.65,
                diagnostics={**diagnostics, "matched_rule": "mixed_index"},
            )

        if candidate_count >= 5 or page_candidate_count >= 3 or same_host_count >= 4:
            return PageClassification(
                page_type=PageType.LIST_INDEX,
                confidence=0.61,
                diagnostics={**diagnostics, "matched_rule": "list_index"},
            )

        if viewer_like_count >= 1 and artifact_candidate_count >= 1:
            return PageClassification(
                page_type=PageType.DOCUMENT_DETAIL_PAGE,
                confidence=0.63,
                diagnostics={
                    **diagnostics,
                    "matched_rule": "viewer_like_document_detail",
                },
            )

        if candidate_count == 0:
            return PageClassification(
                page_type=PageType.UNKNOWN,
                confidence=0.35,
                diagnostics={**diagnostics, "matched_rule": "unknown_no_candidates"},
            )

        return PageClassification(
            page_type=PageType.GENERIC_INDEX,
            confidence=0.47,
            diagnostics={**diagnostics, "matched_rule": "generic_index"},
        )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _metadata_dict(metadata: dict[str, object], key: str) -> dict[str, object] | None:
    value = metadata.get(key)
    if isinstance(value, dict):
        return value
    return None


def _candidate_text(candidate: dict[str, object]) -> str:
    return " ".join(
        filter(
            None,
            [
                _optional_str(candidate.get("semantic_label")) or "",
                _optional_str(candidate.get("url")) or "",
                _optional_str(candidate.get("resource_kind")) or "",
                _optional_str(candidate.get("delivery_mode")) or "",
                _optional_str(candidate.get("table_heading")) or "",
                _optional_str(candidate.get("adjacent_cell_text")) or "",
            ],
        )
    ).lower()


def _is_artifact_candidate(candidate: dict[str, object]) -> bool:
    resource_kind = str(candidate.get("resource_kind") or "").strip().lower()
    delivery_mode = str(candidate.get("delivery_mode") or "").strip().lower()
    url = str(candidate.get("url") or "").strip().lower()
    text = _candidate_text(candidate)

    if resource_kind in {
        "pdf_document",
        "word_document",
        "spreadsheet",
        "artifact",
        "downloadable_document",
    }:
        return True
    if delivery_mode == "direct":
        return True
    if url.endswith(".pdf") or ".pdf?" in url:
        return True
    if any(
        token in text
        for token in ("pdf", "descargar", "descarga", "download", "documento", "document")
    ):
        return True
    return False


def _is_page_candidate(candidate: dict[str, object]) -> bool:
    resource_kind = str(candidate.get("resource_kind") or "").strip().lower()
    delivery_mode = str(candidate.get("delivery_mode") or "").strip().lower()
    url = str(candidate.get("url") or "").strip().lower()

    if resource_kind in {"html_document", "html_page", "page"}:
        return True
    if delivery_mode == "bridge":
        return True
    if url.startswith("http") and not (url.endswith(".pdf") or ".pdf?" in url):
        return True
    return False


def _is_bridge_candidate(candidate: dict[str, object]) -> bool:
    delivery_mode = str(candidate.get("delivery_mode") or "").strip().lower()
    if delivery_mode == "bridge":
        return True

    text = _candidate_text(candidate)
    return any(
        token in text
        for token in (
            "ver documento",
            "consultar",
            "abrir",
            "detalle",
            "ver más",
            "ver mas",
            "view",
            "open",
            "details",
            "read more",
        )
    )


def _is_direct_download_candidate(candidate: dict[str, object]) -> bool:
    delivery_mode = str(candidate.get("delivery_mode") or "").strip().lower()
    url = str(candidate.get("url") or "").strip().lower()
    if delivery_mode == "direct":
        return True
    if url.endswith(".pdf") or ".pdf?" in url:
        return True
    return False


def _is_viewer_like_candidate(candidate: dict[str, object]) -> bool:
    text = _candidate_text(candidate)
    url = str(candidate.get("url") or "").strip().lower()

    return any(
        token in text or token in url
        for token in (
            "viewer",
            "visor",
            "embed",
            "documentviewer",
            "pdfjs",
            "preview",
        )
    )


def _is_same_host_candidate(candidate: dict[str, object]) -> bool:
    value = candidate.get("same_host")
    if isinstance(value, bool):
        return value

    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes"}


def _has_table_context(candidate: dict[str, object]) -> bool:
    return bool(
        _optional_str(candidate.get("table_heading"))
        or _optional_str(candidate.get("adjacent_cell_text"))
    )
