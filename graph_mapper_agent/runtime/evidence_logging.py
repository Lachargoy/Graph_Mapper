from __future__ import annotations
#graph_mapper_agent/runtime/evidence_logging.py
from typing import Any


def record_action_evidence(
    *,
    ledger: object | None,
    run_id: str | None,
    action_result: dict[str, object],
) -> None:
    if ledger is None or not run_id or not str(run_id).strip():
        return

    recorder = getattr(ledger, "record_evidence", None)
    if not callable(recorder):
        return

    action = _optional_str(action_result.get("action")) or ""

    inspection_result = action_result.get("inspection_result")
    if isinstance(inspection_result, dict):
        recorder(
            run_id=run_id,
            evidence_kind="inspection_result",
            source_kind="web_page",
            source_url=_optional_str(inspection_result.get("page_url")),
            mime_type="text/html",
            title=_optional_str(inspection_result.get("title")),
            content={
                "content": _optional_str(inspection_result.get("content")),
                "text_excerpt": _optional_str(inspection_result.get("text_excerpt")),
                "screenshot_base64": _optional_str(
                    inspection_result.get("screenshot_base64")
                ),
                "screenshot_mime_type": _optional_str(
                    inspection_result.get("screenshot_mime_type")
                ),
                "local_perception": _safe_dict(inspection_result.get("local_perception")),
            },
            metadata={
                "action": action,
                "candidate_count": len(list(inspection_result.get("candidates") or ())),
            },
        )

    download_result = action_result.get("download_result")
    if isinstance(download_result, dict):
        recorder(
            run_id=run_id,
            evidence_kind="download_result",
            source_kind="artifact_download",
            source_url=_optional_str(download_result.get("download_url")),
            local_path=_optional_str(download_result.get("original_path")),
            mime_type=_optional_str(download_result.get("content_type")),
            title=_optional_str(download_result.get("filename")),
            content={
                "final_url": _optional_str(download_result.get("final_url")),
                "sha256": _optional_str(download_result.get("sha256")),
                "size_bytes": download_result.get("size_bytes"),
                "local_perception": _safe_dict(download_result.get("local_perception")),
            },
            metadata={"action": action},
        )

    artifact_result = action_result.get("artifact_result")
    if isinstance(artifact_result, dict):
        recorder(
            run_id=run_id,
            evidence_kind="artifact_result",
            source_kind="opened_artifact",
            source_url=_optional_str(download_result.get("download_url"))
            if isinstance(download_result, dict)
            else _optional_str(artifact_result.get("source_url")),
            local_path=(
                _optional_str(download_result.get("original_path"))
                if isinstance(download_result, dict)
                else None
            ),
            mime_type=_optional_str(download_result.get("content_type"))
            if isinstance(download_result, dict)
            else None,
            title=_optional_str(download_result.get("filename"))
            if isinstance(download_result, dict)
            else None,
            content={
                "valid": bool(artifact_result.get("valid")),
                "artifact_kind": _optional_str(artifact_result.get("artifact_kind")),
                "content": _optional_str(artifact_result.get("content")),
                "text_excerpt": _optional_str(artifact_result.get("text_excerpt")),
                "local_perception": _safe_dict(artifact_result.get("local_perception")),
            },
            metadata={"action": action},
        )

    # RECORD GOAL VALIDATION ONLY ONCE, FROM A CANONICAL SOURCE
    canonical = _select_canonical_goal_validation_source(action_result)
    if canonical is not None:
        _record_local_perception_evidence(
            recorder=recorder,
            run_id=run_id,
            local_perception=canonical["local_perception"],
            source_kind=canonical["source_kind"],
            source_url=canonical["source_url"],
            local_path=canonical["local_path"],
            mime_type=canonical["mime_type"],
            title=canonical["title"],
            action=action,
        )


def _select_canonical_goal_validation_source(
    action_result: dict[str, object],
) -> dict[str, object] | None:
    action = _optional_str(action_result.get("action")) or ""

    inspection_result = action_result.get("inspection_result")
    download_result = action_result.get("download_result")
    artifact_result = action_result.get("artifact_result")
    validation_target = action_result.get("validation_target")
    target_source_kind = _optional_str(getattr(validation_target, "source_kind", None))

    sources = _build_validation_sources(
        inspection_result=inspection_result,
        download_result=download_result,
        artifact_result=artifact_result,
    )

    def pick(kind: str) -> dict[str, object] | None:
        candidate = sources.get(kind)
        if candidate is None:
            return None
        if candidate["local_perception"] is None:
            return None
        return candidate

    # validate_current_content must respect the carrier indicated by validation_target
    if action == "validate_current_content":
        if target_source_kind:
            preferred = pick(target_source_kind)
            if preferred is not None:
                return preferred

        for kind in ("artifact", "download", "inspection"):
            preferred = pick(kind)
            if preferred is not None:
                return preferred
        return None

    # open_artifact: if there was validation, the canonical one is from the opened artifact
    if action == "open_artifact":
        return pick("artifact")

    # download_artifact: only record validation if it actually came embedded there
    if action == "download_artifact":
        return pick("download")

    # follow_edge: only from inspection/web_page
    if action == "follow_edge":
        return pick("inspection")

    # defensive fallback
    for kind in ("artifact", "download", "inspection"):
        preferred = pick(kind)
        if preferred is not None:
            return preferred

    return None


def _build_validation_sources(
    *,
    inspection_result: object,
    download_result: object,
    artifact_result: object,
) -> dict[str, dict[str, object]]:
    inspection_lp = _safe_dict(
        inspection_result.get("local_perception")
        if isinstance(inspection_result, dict)
        else None
    )
    download_lp = _safe_dict(
        download_result.get("local_perception")
        if isinstance(download_result, dict)
        else None
    )
    artifact_lp = _safe_dict(
        artifact_result.get("local_perception")
        if isinstance(artifact_result, dict)
        else None
    )

    return {
        "inspection": {
            "local_perception": inspection_lp,
            "source_kind": "web_page",
            "source_url": _optional_str(inspection_result.get("page_url"))
            if isinstance(inspection_result, dict)
            else None,
            "local_path": None,
            "mime_type": "text/html" if isinstance(inspection_result, dict) else None,
            "title": _optional_str(inspection_result.get("title"))
            if isinstance(inspection_result, dict)
            else None,
        },
        "download": {
            "local_perception": download_lp,
            "source_kind": "artifact_download",
            "source_url": _optional_str(download_result.get("download_url"))
            if isinstance(download_result, dict)
            else None,
            "local_path": _optional_str(download_result.get("original_path"))
            if isinstance(download_result, dict)
            else None,
            "mime_type": _optional_str(download_result.get("content_type"))
            if isinstance(download_result, dict)
            else None,
            "title": _optional_str(download_result.get("filename"))
            if isinstance(download_result, dict)
            else None,
        },
        "artifact": {
            "local_perception": artifact_lp,
            "source_kind": "opened_artifact",
            "source_url": (
                _optional_str(download_result.get("download_url"))
                if isinstance(download_result, dict)
                else _optional_str(artifact_result.get("source_url"))
                if isinstance(artifact_result, dict)
                else None
            ),
            "local_path": (
                _optional_str(download_result.get("original_path"))
                if isinstance(download_result, dict)
                else None
            ),
            "mime_type": (
                _optional_str(download_result.get("content_type"))
                if isinstance(download_result, dict)
                else None
            ),
            "title": (
                _optional_str(download_result.get("filename"))
                if isinstance(download_result, dict)
                else None
            ),
        },
    }


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_dict(value: object) -> dict[str, object] | None:
    return dict(value) if isinstance(value, dict) else None


def _record_local_perception_evidence(
    *,
    recorder: object,
    run_id: str,
    local_perception: dict[str, object] | None,
    source_kind: str,
    source_url: str | None,
    local_path: str | None,
    mime_type: str | None,
    title: str | None,
    action: object,
) -> None:
    if local_perception is None:
        return

    metadata = _safe_dict(local_perception.get("metadata")) or {}
    recorder(
        run_id=run_id,
        evidence_kind="goal_validation_result",
        source_kind=source_kind,
        source_url=source_url,
        local_path=local_path,
        mime_type=mime_type,
        title=title,
        content={
            "target_kind": _optional_str(local_perception.get("target_kind")),
            "status": _optional_str(local_perception.get("status")),
            "confidence": local_perception.get("confidence"),
            "summary": _optional_str(local_perception.get("summary")),
            "recommended_next_step": _optional_str(
                local_perception.get("recommended_next_step")
            ),
            "matched_condition_ids": list(metadata.get("matched_condition_ids") or ()),
            "validated_document_family": metadata.get("validated_document_family"),
            "validated_year": metadata.get("validated_year"),
            "validation_scope_assessment": metadata.get(
                "validation_scope_assessment"
            ),
            "validation_status": metadata.get("validation_status"),
            "validation_strategy": metadata.get("validation_strategy"),
            "passes_executed": metadata.get("passes_executed"),
        },
        metadata={
            "action": action,
            "source_action": metadata.get("source_action"),
        },
    )