from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse


class CandidateProjectionEnricher(Protocol):
    def enrich(
        self,
        *,
        candidate: dict[str, Any],
        hints: tuple[str, ...],
    ) -> dict[str, Any]: ...


class CandidateProjectionTool(Protocol):
    def project(
        self,
        *,
        page_url: str,
        entry_url: str,
        page_title: str | None,
        anchors: object,
        metadata: dict[str, Any],
        goal: str,
        expected_document_kind: str,
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class BaseCandidateProjectionTool:
    enrichers: tuple[CandidateProjectionEnricher, ...] = ()

    def project(
        self,
        *,
        page_url: str,
        entry_url: str,
        page_title: str | None,
        anchors: object,
        metadata: dict[str, Any],
        goal: str,
        expected_document_kind: str,
    ) -> list[dict[str, Any]]:
        if not isinstance(anchors, list):
            return []

        hints = collect_search_hints(metadata, goal, expected_document_kind)
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()

        for item in anchors:
            if not isinstance(item, dict):
                continue
            href = item.get('href')
            if href is None:
                continue
            raw_href = str(href).strip()
            if not raw_href or raw_href.startswith('#') or raw_href.startswith('javascript:'):
                continue
            absolute_url = urljoin(page_url, raw_href)
            if absolute_url in seen:
                continue
            seen.add(absolute_url)

            candidate = {
                'url': absolute_url,
                'text': str(item.get('text') or '').strip(),
                'semantic_label': semantic_label_from_anchor(item),
                'context_text': anchor_context_text(item),
                'table_heading': anchor_optional_text(item, 'table_heading'),
                'section_heading': anchor_optional_text(item, 'section_heading'),
                'adjacent_cell_text': anchor_optional_text(item, 'adjacent_cell_text'),
                'row_text': anchor_optional_text(item, 'row_text'),
                'year_hints': extract_year_hints(item),
                'date_hints': extract_date_hints(item),
                'page_url': page_url or entry_url,
                'frame_url': page_url or entry_url,
                'page_title': page_title,
            }
            for enricher in self.enrichers:
                candidate = enricher.enrich(candidate=candidate, hints=hints)
            candidates.append(candidate)

        candidates.sort(key=lambda item: int(item.get('score') or 0), reverse=True)
        return candidates


@dataclass(frozen=True)
class DocumentCandidateProjectionEnricher:
    def enrich(
        self,
        *,
        candidate: dict[str, Any],
        hints: tuple[str, ...],
    ) -> dict[str, Any]:
        enriched = dict(candidate)
        url = str(enriched.get('url') or '').strip()
        text = str(enriched.get('text') or '').strip()
        semantic_label = str(enriched.get('semantic_label') or '').strip()
        context_text = str(enriched.get('context_text') or '').strip()
        year_hints = tuple(str(v) for v in (enriched.get('year_hints') or ()) if str(v).strip())
        date_hints = tuple(str(v) for v in (enriched.get('date_hints') or ()) if str(v).strip())

        candidate_kind = classify_candidate_kind(
            url,
            text,
            semantic_label=semantic_label,
            context_text=context_text,
        )
        resource_kind = infer_resource_kind(
            url,
            text,
            semantic_label=semantic_label,
            context_text=context_text,
        )
        delivery_mode = infer_delivery_mode(
            url,
            candidate_kind=candidate_kind,
            resource_kind=resource_kind,
        )
        document_kind_hints = infer_document_kind_hints(
            text=text,
            semantic_label=semantic_label,
            context_text=context_text,
            url=url,
        )
        score = score_candidate(
            url,
            text,
            hints,
            semantic_label=semantic_label,
            context_text=context_text,
            year_hints=year_hints,
            date_hints=date_hints,
            candidate_kind=candidate_kind,
        )
        enriched.update(
            {
                'candidate_kind': candidate_kind,
                'resource_kind': resource_kind,
                'delivery_mode': delivery_mode,
                'document_kind_hints': document_kind_hints,
                'score': score,
            }
        )
        return enriched


def collect_search_hints(
    metadata: dict[str, Any],
    goal: str,
    expected_document_kind: str,
) -> tuple[str, ...]:
    hints: list[str] = []
    if goal:
        hints.extend(
            part.strip().lower()
            for part in goal.replace(',', ' ').split()
            if len(part.strip()) > 3
        )
    if expected_document_kind:
        normalized = expected_document_kind.strip().lower()
        hints.append(normalized)
        hints.extend(
            part.strip()
            for part in normalized.replace('-', '_').split('_')
            if len(part.strip()) > 2
        )
    for key in ('search_hints', 'llm_search_hints', 'keywords'):
        value = metadata.get(key)
        if isinstance(value, list):
            hints.extend(str(item).strip().lower() for item in value if str(item).strip())
    return tuple(dict.fromkeys(hints))


def classify_candidate_kind(
    url: str,
    text: str,
    *,
    semantic_label: str | None = None,
    context_text: str | None = None,
) -> str:
    url_lower = url.lower()
    text_lower = text.lower()
    semantic_lower = (semantic_label or '').lower()
    context_lower = (context_text or '').lower()
    combined = ' '.join(part for part in (url_lower, text_lower, semantic_lower, context_lower) if part)

    if url_lower.endswith('.pdf'):
        return 'direct_pdf'
    if url_lower.endswith('.html') and any(token in combined for token in ('pdf', 'anexo', 'volumen', 'descarga', 'facsimilar')):
        return 'bridge_page_to_pdf'
    if any(token in url_lower for token in ('index.html', '/index.', 'indice')) and url_lower.endswith('.html'):
        return 'index_page'
    if any(token in combined for token in ('estenografica', 'gaceta', 'busqueda', 'correo electr', 'informes de gobierno')):
        return 'likely_noise'
    if url_lower.endswith('.html'):
        return 'bridge_page_to_pdf'
    return 'index_page'


def infer_resource_kind(
    url: str,
    text: str,
    *,
    semantic_label: str | None = None,
    context_text: str | None = None,
) -> str:
    url_lower = url.lower()
    combined = ' '.join(
        part.lower()
        for part in (text, semantic_label or '', context_text or '', url)
        if part
    )
    if url_lower.endswith('.pdf'):
        return 'pdf'
    if url_lower.endswith('.xlsx'):
        return 'xlsx'
    if url_lower.endswith('.xls'):
        return 'xls'
    if url_lower.endswith('.csv'):
        return 'csv'
    if url_lower.endswith('.docx'):
        return 'docx'
    if url_lower.endswith('.doc'):
        return 'doc'
    if url_lower.endswith('.zip'):
        return 'zip'
    if url_lower.endswith('.html') or any(token in combined for token in ('html', 'estenograf', 'noticia', 'comunicado', 'boletin')):
        return 'html_document'
    return 'unknown'


def infer_delivery_mode(
    url: str,
    *,
    candidate_kind: str | None,
    resource_kind: str,
) -> str:
    url_lower = url.lower()
    if resource_kind in {'pdf', 'xlsx', 'xls', 'csv', 'doc', 'docx', 'zip'}:
        return 'direct'
    if candidate_kind == 'bridge_page_to_pdf':
        return 'bridge'
    if 'index.' in url_lower or url_lower.endswith('/index.html'):
        return 'index'
    if resource_kind == 'html_document':
        return 'document'
    return 'unknown'


def infer_document_kind_hints(
    *,
    text: str,
    semantic_label: str | None = None,
    context_text: str | None = None,
    url: str | None = None,
) -> tuple[str, ...]:
    combined = ' '.join(part.lower() for part in (text, semantic_label or '', context_text or '', url or '') if part)
    token_map = {
        'diario': 'diario',
        'debate': 'diario',
        'estenograf': 'version_estenografica',
        'gaceta': 'gaceta',
        'acta': 'acta',
        'anexo': 'anexo',
        'volumen': 'volumen',
        'votacion': 'vote_record',
        'voto': 'vote_record',
        'noticia': 'news_article',
        'comunicado': 'press_release',
        'boletin': 'press_release',
    }
    hints: list[str] = []
    for token, label in token_map.items():
        if token in combined and label not in hints:
            hints.append(label)

    has_diario = 'diario de los debates' in combined or ('diario' in combined and 'debate' in combined)
    if has_diario and 'diario' not in hints:
        hints.append('diario')
    if has_diario and any(token in combined for token in ('versiones pdf', '/pdf/', '.pdf', ' pdf ')):
        hints.append('diario_debates_pdf')
    if has_diario and any(token in combined for token in ('versiones html', '/ddebates/', ' html ')):
        hints.append('diario_debates_html')
    return tuple(dict.fromkeys(hints))


def score_candidate(
    url: str,
    text: str,
    hints: tuple[str, ...],
    *,
    semantic_label: str | None = None,
    context_text: str | None = None,
    year_hints: tuple[str, ...] = (),
    date_hints: tuple[str, ...] = (),
    candidate_kind: str | None = None,
) -> int:
    score = 0
    url_lower = url.lower()
    text_lower = text.lower()
    semantic_lower = (semantic_label or '').lower()
    context_lower = (context_text or '').lower()
    combined_text = ' '.join(part for part in (text_lower, semantic_lower, context_lower) if part)

    if candidate_kind == 'direct_pdf':
        score += 12
    elif candidate_kind == 'bridge_page_to_pdf':
        score += 8
    elif candidate_kind == 'index_page':
        score += 2
    elif candidate_kind == 'likely_noise':
        score -= 2

    if url_lower.endswith('.pdf'):
        score += 10
    if any(token in url_lower for token in ('pdf', 'download', 'descarga')):
        score += 4
    if any(token in combined_text for token in ('pdf', 'descargar', 'documento', 'acta', 'diario', 'gaceta', 'anexo', 'volumen')):
        score += 5
    if _looks_like_diario_debates_pdf_hub(url_lower, combined_text):
        score += 18
        if candidate_kind in {'index_page', 'bridge_page_to_pdf'}:
            score += 6
    if year_hints:
        score += min(len(year_hints), 3)
    if date_hints:
        score += 1
    for hint in hints:
        if hint and (hint in url_lower or hint in combined_text):
            score += 3
    parsed = urlparse(url_lower)
    if parsed.scheme in {'http', 'https'}:
        score += 1
    return score


def anchor_optional_text(item: dict[str, Any], key: str) -> str | None:
    value = item.get(key)
    text = str(value or '').strip()
    return text or None


def semantic_label_from_anchor(item: dict[str, Any]) -> str:
    parts = [
        anchor_optional_text(item, 'section_heading') or '',
        anchor_optional_text(item, 'table_heading') or '',
        anchor_optional_text(item, 'row_text') or '',
        str(item.get('text') or '').strip(),
    ]
    return ' | '.join(part for part in parts if part)


def anchor_context_text(item: dict[str, Any]) -> str:
    parts = [
        anchor_optional_text(item, 'section_heading') or '',
        anchor_optional_text(item, 'table_heading') or '',
        anchor_optional_text(item, 'row_text') or '',
        anchor_optional_text(item, 'adjacent_cell_text') or '',
    ]
    return ' | '.join(part for part in parts if part)


def extract_year_hints(item: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for key in ('text', 'row_text', 'adjacent_cell_text', 'table_heading', 'section_heading'):
        raw = str(item.get(key) or '')
        for token in raw.replace(',', ' ').split():
            clean = ''.join(ch for ch in token if ch.isdigit())
            if len(clean) == 4 and clean.startswith(('19', '20')) and clean not in values:
                values.append(clean)
    return tuple(values)


def extract_date_hints(item: dict[str, Any]) -> tuple[str, ...]:
    months = (
        'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
        'julio', 'agosto', 'septiembre', 'setiembre', 'octubre', 'noviembre', 'diciembre',
    )
    values: list[str] = []
    for key in ('text', 'row_text', 'adjacent_cell_text', 'table_heading', 'section_heading'):
        raw = str(item.get(key) or '').lower()
        for month in months:
            if month in raw and month not in values:
                values.append(month)
    return tuple(values)


def _looks_like_diario_debates_pdf_hub(url_lower: str, combined_text: str) -> bool:
    has_diario = 'diario de los debates' in combined_text or ('diario' in combined_text and 'debate' in combined_text)
    has_pdf = any(token in combined_text or token in url_lower for token in ('versiones pdf', '/pdf/', '.pdf', ' pdf '))
    return has_diario and has_pdf
