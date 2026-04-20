from __future__ import annotations


def optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def dedupe_tokens(parts: tuple[object, ...]) -> tuple[str, ...]:
    tokens: list[str] = []
    for part in parts:
        raw = str(part or "").strip().lower().replace("_", " ")
        for token in raw.split():
            token = token.strip(" ,.;:()[]{}'\"")
            if len(token) < 3:
                continue
            if token not in tokens:
                tokens.append(token)
    return tuple(tokens[:8])
