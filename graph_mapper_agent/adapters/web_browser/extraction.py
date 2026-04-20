# aither/adapters/tools/web_browser/extraction.py
"""
Web page content extraction utilities via Playwright.

Contains:
- semantic link extraction
- visible text extraction
- title extraction
- PERMISSIVE detection of search targets
"""
from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import urljoin, urlparse

__all__ = [
    "extract_raw_anchors",
    "extract_page_text",
    "extract_title",
    "extract_search_targets",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_TEXT_MAX_CHARS: int = 1_200
_INNER_TEXT_TIMEOUT_MS: int = 1_500

_SEARCH_TARGET_PLACEHOLDER_MAX_CHARS: int = 180
_SEARCH_TARGET_LABEL_MAX_CHARS: int = 180
_SEARCH_TARGET_NAME_MAX_CHARS: int = 100
_SEARCH_TARGET_FORM_ACTION_MAX_CHARS: int = 240

_DISALLOWED_SEARCH_INPUT_TYPES: frozenset[str] = frozenset({
    "password",
    "hidden",
    "checkbox",
    "radio",
    "file",
    "submit",
    "button",
    "reset",
    "image",
    "color",
    "date",
    "datetime-local",
    "month",
    "range",
    "time",
    "week",
})

# ---------------------------------------------------------------------------
# JS script for semantic link extraction
# ---------------------------------------------------------------------------

EXTRACT_CANDIDATES_JS: str = r"""
elements => {
  const normalize = value => (value || '').replace(/\s+/g, ' ').trim();
  const limit = (value, size=260) => normalize(value).slice(0, size);
  const headingSelector = 'h1, h2, h3, h4, h5, h6, th, caption, legend';
  const containerSelector = 'tr, li, dt, dd, p, article, section, div, td';

  const textOf = node => limit(node ? (node.innerText || node.textContent || '') : '');

  const firstHeadingIn = node => {
    if (!node || !node.querySelector) return '';
    const found = node.querySelector(headingSelector);
    return textOf(found);
  };

  const previousHeading = node => {
    let current = node;
    while (current) {
      let sibling = current.previousElementSibling;
      while (sibling) {
        const siblingHeading = sibling.matches && sibling.matches(headingSelector)
          ? textOf(sibling)
          : firstHeadingIn(sibling);
        if (siblingHeading) return siblingHeading;
        sibling = sibling.previousElementSibling;
      }
      current = current.parentElement;
      if (current && current.matches && current.matches(headingSelector)) {
        const ownHeading = textOf(current);
        if (ownHeading) return ownHeading;
      }
    }
    return '';
  };

  const nearestTableHeading = cell => {
    const table = cell && cell.closest ? cell.closest('table') : null;
    const row = cell && cell.parentElement ? cell.parentElement.closest('tr') : null;
    if (!table || !row) return '';
    let scan = row.previousElementSibling;
    while (scan) {
      const cells = Array.from(scan.querySelectorAll('td, th'));
      const headingCell = cells.find(candidate => {
        const colspan = parseInt(candidate.getAttribute('colspan') || '1', 10);
        const klass = candidate.getAttribute('class') || '';
        return colspan > 1 || /Titulo/i.test(klass);
      });
      if (headingCell) {
        const heading = textOf(headingCell);
        if (heading) return heading;
      }
      scan = scan.previousElementSibling;
    }
    return '';
  };

  const rowContext = cell => {
    if (!cell || !cell.parentElement) return {rowText: '', rowCells: [], adjacentCellText: ''};
    const row = cell.parentElement.closest('tr');
    if (!row) return {rowText: '', rowCells: [], adjacentCellText: ''};

    const cells = Array.from(row.children)
      .filter(node => node && (node.tagName === 'TD' || node.tagName === 'TH'));
    const rowCells = cells.map(textOf).filter(Boolean);

    let adjacentCellText = '';
    let sibling = cell.nextElementSibling;
    while (sibling) {
      if (sibling.tagName === 'TD' || sibling.tagName === 'TH') {
        adjacentCellText = textOf(sibling);
        if (adjacentCellText) break;
      }
      sibling = sibling.nextElementSibling;
    }

    if (!adjacentCellText) {
      const table = cell.closest('table');
      let nextRow = row.nextElementSibling;
      while (nextRow && table && nextRow.closest('table') === table) {
        const nextCells = Array.from(nextRow.querySelectorAll('td, th')).map(textOf).filter(Boolean);
        if (nextCells.length >= 2) {
          adjacentCellText = nextCells[1] || '';
          break;
        }
        nextRow = nextRow.nextElementSibling;
      }
    }

    return {
      rowText: rowCells.join(' | '),
      rowCells,
      adjacentCellText,
    };
  };

  return elements.map(el => {
    const href = el.getAttribute('href');
    const text = limit(el.innerText || el.textContent || '', 180);
    const title = limit(el.getAttribute('title') || '', 180);
    const ariaLabel = limit(el.getAttribute('aria-label') || '', 180);
    const cell = el.closest('td, th');
    const tableHeading = nearestTableHeading(cell);
    const rowInfo = rowContext(cell);
    const container = el.closest(containerSelector);
    const containerText = limit(container ? (container.innerText || container.textContent || '') : '', 320);
    const sectionHeading = previousHeading(container || cell || el);
    const parentText = limit(el.parentElement ? (el.parentElement.innerText || el.parentElement.textContent || '') : '', 240);
    return {
      href,
      text,
      title,
      aria_label: ariaLabel,
      table_heading: tableHeading,
      section_heading: sectionHeading,
      row_text: rowInfo.rowText || containerText,
      row_cells: rowInfo.rowCells,
      adjacent_cell_text: rowInfo.adjacentCellText,
      parent_text: parentText,
    };
  });
}
"""

# ---------------------------------------------------------------------------
# JS script for extracting search targets (PERMISSIVE)
# ---------------------------------------------------------------------------

EXTRACT_SEARCH_TARGETS_JS: str = r"""
elements => {
  const normalize = value => (value || '').replace(/\s+/g, ' ').trim();
  const limit = (value, size=180) => normalize(value).slice(0, size);

  const isVisible = el => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (!style) return false;
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    if (style.opacity === '0') return false;

    const rect = el.getBoundingClientRect();
    if (!rect) return false;
    if (rect.width <= 0 || rect.height <= 0) return false;

    return true;
  };

  const labelTextFor = el => {
    if (!el) return '';

    const ariaLabel = limit(el.getAttribute('aria-label') || '', 180);
    if (ariaLabel) return ariaLabel;

    const idAttr = el.getAttribute('id') || '';
    if (idAttr) {
      try {
        const label = document.querySelector(`label[for="${CSS.escape(idAttr)}"]`);
        const labelText = limit(label ? (label.innerText || label.textContent || '') : '', 180);
        if (labelText) return labelText;
      } catch (_) {}
    }

    const parentLabel = el.closest('label');
    const parentLabelText = limit(parentLabel ? (parentLabel.innerText || parentLabel.textContent || '') : '', 180);
    if (parentLabelText) return parentLabelText;

    return '';
  };

  const sameHost = action => {
    if (!action) return true;
    try {
      const resolved = new URL(action, window.location.href);
      return resolved.host === window.location.host;
    } catch (_) {
      return null;
    }
  };

  const looksSearchLike = el => {
    const type = normalize(el.getAttribute('type') || '').toLowerCase();
    const name = normalize(el.getAttribute('name') || '').toLowerCase();
    const idAttr = normalize(el.getAttribute('id') || '').toLowerCase();
    const placeholder = normalize(el.getAttribute('placeholder') || '').toLowerCase();
    const ariaLabel = normalize(el.getAttribute('aria-label') || '').toLowerCase();
    const cls = normalize(el.getAttribute('class') || '').toLowerCase();
    const role = normalize(el.getAttribute('role') || '').toLowerCase();

    const form = el.closest('form');
    const formRole = normalize(form ? (form.getAttribute('role') || '') : '').toLowerCase();
    const formAction = normalize(form ? (form.getAttribute('action') || '') : '').toLowerCase();
    const formId = normalize(form ? (form.getAttribute('id') || '') : '').toLowerCase();
    const formClass = normalize(form ? (form.getAttribute('class') || '') : '').toLowerCase();

    const haystack = [
      type, name, idAttr, placeholder, ariaLabel, cls, role,
      formRole, formAction, formId, formClass
    ].join(' ');

    if (type === 'search') return true;
    if (name === 'q') return true;

    if (haystack.includes('search')) return true;
    if (haystack.includes('buscar')) return true;
    if (haystack.includes('find')) return true;
    if (haystack.includes('query')) return true;
    if (haystack.includes('consulta')) return true;
    if (haystack.includes('busqueda')) return true;
    if (haystack.includes('búsqueda')) return true;
    if (haystack.includes('duckduckgo')) return true;
    if (haystack.includes('google')) return true;
    if (haystack.includes('bing')) return true;

    return false;
  };

  return elements.map(el => {
    const form = el.closest('form');
    const type = limit(el.getAttribute('type') || 'text', 40).toLowerCase();
    const name = limit(el.getAttribute('name') || '', 100);
    const idAttr = limit(el.getAttribute('id') || '', 100);
    const placeholder = limit(el.getAttribute('placeholder') || '', 180);
    const ariaLabel = limit(el.getAttribute('aria-label') || '', 180);
    const label = labelTextFor(el);
    const formAction = limit(form ? (form.getAttribute('action') || '') : '', 240);
    const formMethod = limit(form ? (form.getAttribute('method') || 'get') : 'get', 20).toLowerCase();
    const role = limit(el.getAttribute('role') || '', 40).toLowerCase();
    const className = limit(el.getAttribute('class') || '', 180);
    const autocomplete = limit(el.getAttribute('autocomplete') || '', 80).toLowerCase();

    return {
      tag: (el.tagName || '').toLowerCase(),
      input_type: type,
      name,
      id_attr: idAttr,
      placeholder,
      aria_label: ariaLabel,
      label,
      role,
      class_name: className,
      autocomplete,
      form_action: formAction,
      form_method: formMethod,
      visible: isVisible(el),
      same_host: sameHost(formAction),
      looks_search_like: looksSearchLike(el),
    };
  });
}
"""

# ---------------------------------------------------------------------------
# Extraction functions
# ---------------------------------------------------------------------------


def extract_raw_anchors(frame_like: Any) -> list[dict[str, Any]]:
    try:
        anchors = frame_like.eval_on_selector_all(
            "a[href]",
            EXTRACT_CANDIDATES_JS,
        )
    except Exception:
        return []

    return anchors if isinstance(anchors, list) else []


def extract_page_text(
    page: Any,
    max_chars: int = _DEFAULT_TEXT_MAX_CHARS,
) -> str | None:
    try:
        raw = page.locator("body").inner_text(timeout=_INNER_TEXT_TIMEOUT_MS)
    except Exception:
        return None

    normalized = " ".join(str(raw).split())
    if not normalized:
        return None

    return normalized[:max_chars]


def extract_title(page: Any) -> str | None:
    try:
        title = str(page.title() or "").strip()
        return title or None
    except Exception:
        return None


def extract_search_targets(frame_like: Any, frame_url: str) -> list[dict[str, Any]]:
    """
    Extracts possible search targets from a frame/page.

    Strategy:
    - broad selector: input, textarea
    - permissive JS
    - gentle but useful Python filter
    - flexible score / confidence
    """
    try:
        raw_targets = frame_like.eval_on_selector_all(
            "input, textarea",
            EXTRACT_SEARCH_TARGETS_JS,
        )
    except Exception:
        return []

    if not isinstance(raw_targets, list):
        return []

    parsed_frame = urlparse(str(frame_url or "").strip())
    frame_host = parsed_frame.netloc.strip().lower()

    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for item in raw_targets:
        if not isinstance(item, dict):
            continue

        visible = bool(item.get("visible"))
        if not visible:
            continue

        tag = _clean_text(item.get("tag"), 40).lower() or "input"
        input_type = _clean_text(item.get("input_type"), 40).lower() or "text"
        name = _clean_text(item.get("name"), _SEARCH_TARGET_NAME_MAX_CHARS)
        id_attr = _clean_text(item.get("id_attr"), _SEARCH_TARGET_NAME_MAX_CHARS)
        placeholder = _clean_text(item.get("placeholder"), _SEARCH_TARGET_PLACEHOLDER_MAX_CHARS)
        aria_label = _clean_text(item.get("aria_label"), _SEARCH_TARGET_LABEL_MAX_CHARS)
        label = _clean_text(item.get("label"), _SEARCH_TARGET_LABEL_MAX_CHARS)
        role = _clean_text(item.get("role"), 40).lower()
        class_name = _clean_text(item.get("class_name"), 180)
        autocomplete = _clean_text(item.get("autocomplete"), 80).lower()
        form_action = _clean_text(item.get("form_action"), _SEARCH_TARGET_FORM_ACTION_MAX_CHARS)
        form_method = _clean_text(item.get("form_method"), 20).lower() or "get"
        same_host = item.get("same_host")
        looks_search_like = bool(item.get("looks_search_like"))

        if input_type in _DISALLOWED_SEARCH_INPUT_TYPES:
            continue

        score = _compute_search_target_score(
            tag=tag,
            input_type=input_type,
            name=name,
            id_attr=id_attr,
            placeholder=placeholder,
            aria_label=aria_label,
            label=label,
            role=role,
            class_name=class_name,
            autocomplete=autocomplete,
            form_action=form_action,
            form_method=form_method,
            same_host=same_host,
            looks_search_like=looks_search_like,
            frame_host=frame_host,
        )

        # Súper permisivo: si huele aunque sea poquito a buscador, pasa.
        if score < 0.35:
            continue

        search_target_id = _build_search_target_id(
            frame_url=frame_url,
            tag=tag,
            input_type=input_type,
            name=name,
            id_attr=id_attr,
            placeholder=placeholder,
            aria_label=aria_label,
            label=label,
            form_action=form_action,
        )
        if search_target_id in seen_ids:
            continue
        seen_ids.add(search_target_id)

        results.append(
            {
                "search_target_id": search_target_id,
                "tag": tag,
                "input_type": input_type,
                "name": name,
                "id_attr": id_attr,
                "placeholder": placeholder,
                "aria_label": aria_label,
                "label": label,
                "role": role,
                "class_name": class_name,
                "autocomplete": autocomplete,
                "form_action": form_action,
                "form_method": form_method,
                "same_host": same_host,
                "confidence": round(min(score, 1.0), 3),
                "source_frame": str(frame_url or "").strip(),
            }
        )

    results.sort(
        key=lambda item: (
            float(item.get("confidence") or 0.0),
            1 if item.get("same_host") is True else 0,
            1 if str(item.get("input_type") or "") == "search" else 0,
            1 if str(item.get("name") or "") == "q" else 0,
        ),
        reverse=True,
    )
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_text(value: object, max_len: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    return text[:max_len]


def _build_search_target_id(
    *,
    frame_url: str,
    tag: str,
    input_type: str,
    name: str,
    id_attr: str,
    placeholder: str,
    aria_label: str,
    label: str,
    form_action: str,
) -> str:
    raw = "|".join(
        [
            str(frame_url or "").strip(),
            tag,
            input_type,
            name,
            id_attr,
            placeholder,
            aria_label,
            label,
            form_action,
        ]
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"search_{digest}"


def _compute_search_target_score(
    *,
    tag: str,
    input_type: str,
    name: str,
    id_attr: str,
    placeholder: str,
    aria_label: str,
    label: str,
    role: str,
    class_name: str,
    autocomplete: str,
    form_action: str,
    form_method: str,
    same_host: object,
    looks_search_like: bool,
    frame_host: str,
) -> float:
    score = 0.0

    haystack = " ".join(
        [
            input_type,
            name.lower(),
            id_attr.lower(),
            placeholder.lower(),
            aria_label.lower(),
            label.lower(),
            role.lower(),
            class_name.lower(),
            autocomplete.lower(),
            form_action.lower(),
            form_method.lower(),
        ]
    )

    if tag in {"input", "textarea"}:
        score += 0.10

    if input_type == "search":
        score += 0.65
    elif input_type in {"text", ""}:
        score += 0.20

    if name.lower() == "q":
        score += 0.55

    if role == "searchbox":
        score += 0.45

    if autocomplete in {"off", "on"}:
        score += 0.02

    keywords = (
        "search",
        "buscar",
        "find",
        "query",
        "consulta",
        "busqueda",
        "búsqueda",
    )
    if any(k in haystack for k in keywords):
        score += 0.40

    engine_keywords = ("duckduckgo", "google", "bing")
    if any(k in haystack for k in engine_keywords):
        score += 0.12

    if looks_search_like:
        score += 0.35

    if same_host is True:
        score += 0.08
    elif same_host is False:
        score -= 0.03

    if form_method == "get":
        score += 0.05

    # Bonus pequeño si el action del form parece de búsqueda
    normalized_form_action = form_action.lower()
    if any(k in normalized_form_action for k in keywords):
        score += 0.12

    # No castigar por no tener form_action: muchos buscadores modernos igual funcionan.
    if not form_action:
        score += 0.03

    # Bonus si el id/name/class tienen pinta clara de caja de búsqueda
    micro_hits = 0
    for text in (name.lower(), id_attr.lower(), class_name.lower()):
        if any(k in text for k in keywords):
            micro_hits += 1
    score += min(micro_hits * 0.08, 0.24)

    return score