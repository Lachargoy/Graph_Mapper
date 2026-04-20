from __future__ import annotations


def safe_append_navigation_event(
    *,
    ledger: object | None,
    run_id: str | None,
    event_type: str,
    payload: dict[str, object],
) -> None:
    if ledger is None:
        return

    if not run_id or not str(run_id).strip():
        return

    append_event = getattr(ledger, "append_event", None)
    if append_event is None:
        return

    try:
        append_event(
            run_id=str(run_id),
            event_type=event_type,
            payload=dict(payload),
        )
    except Exception:
        return
