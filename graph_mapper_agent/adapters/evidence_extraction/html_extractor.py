from __future__ import annotations

from html import unescape
from html.parser import HTMLParser

from graph_mapper_agent.application.evidence_extraction.models import (
    EvidenceExtractionRequest,
    EvidenceExtractionResult,
    EvidenceItem,
)
from graph_mapper_agent.application.evidence_extraction.ports import (
    EvidenceExtractorPort,
)


class HtmlEvidenceExtractor(EvidenceExtractorPort):
    def extract(self, request: EvidenceExtractionRequest) -> EvidenceExtractionResult:
        artifact = request.artifact
        carrier = artifact.infer_carrier()
        inline_text = str(artifact.inline_text or "").strip()

        if not inline_text:
            return EvidenceExtractionResult(
                carrier=carrier,
                items=(),
                metadata={"source": "html_inline", "status": "empty_inline_text"},
            )

        extracted_text = inline_text
        if carrier == "html":
            extracted_text = _html_to_text(inline_text)

        extracted_text = _normalize_text(extracted_text)
        if not extracted_text:
            return EvidenceExtractionResult(
                carrier=carrier,
                items=(),
                metadata={"source": "html_inline", "status": "empty_extracted_text"},
            )

        return EvidenceExtractionResult(
            carrier=carrier,
            items=(
                EvidenceItem(
                    evidence_kind="inline_text",
                    carrier=carrier,
                    text=extracted_text,
                    metadata={"normalized_from": carrier},
                ),
            ),
            metadata={"source": "html_inline"},
        )


class _HtmlTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag in {"p", "div", "section", "article", "li", "br", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if data.strip():
            self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


def _html_to_text(raw_html: str) -> str:
    parser = _HtmlTextParser()
    parser.feed(raw_html)
    parser.close()
    return unescape(parser.text())


def _normalize_text(value: str) -> str:
    lines = [part.strip() for part in value.splitlines()]
    compact = "\n".join(part for part in lines if part)
    return compact.strip()
