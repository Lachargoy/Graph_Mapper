from __future__ import annotations

import unicodedata


def normalize_text(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def tokenize_text(text: str) -> tuple[str, ...]:
    text = normalize_text(text)
    tokens: list[str] = []
    current: list[str] = []
    for char in text:
        if char.isalnum() or char in {"_", "/"}:
            current.append(char)
        else:
            if current:
                tokens.append("".join(current))
                current = []
    if current:
        tokens.append("".join(current))
    return tuple(tokens)


def strip_url_fragment(value: str) -> str:
    if not value:
        return ""
    return value.split("#", 1)[0]


def looks_like_direct_artifact(candidate: object) -> bool:
    url = normalize_text(str(getattr(candidate, "target_url", "") or ""))
    candidate_type = normalize_text(str(getattr(candidate, "candidate_type", "") or ""))
    mode = normalize_text(str(getattr(candidate, "delivery_mode", "") or ""))
    reason = normalize_text(str(getattr(candidate, "reason", "") or ""))
    return (
        url.endswith(".pdf")
        or candidate_type in {"artifact", "artifact_pdf", "download"}
        or mode == "direct"
        or reason == "direct_artifact_candidate"
    )


def looks_like_bridge(candidate: object) -> bool:
    url = normalize_text(str(getattr(candidate, "target_url", "") or ""))
    candidate_type = normalize_text(str(getattr(candidate, "candidate_type", "") or ""))
    mode = normalize_text(str(getattr(candidate, "delivery_mode", "") or ""))
    reason = normalize_text(str(getattr(candidate, "reason", "") or ""))
    return (
        url.endswith(".html")
        or candidate_type in {"page", "navigation"}
        or mode == "bridge"
        or reason == "bridge_candidate"
    )


__all__ = [
    "looks_like_bridge",
    "looks_like_direct_artifact",
    "normalize_text",
    "strip_url_fragment",
    "tokenize_text",
]
