from __future__ import annotations

import json
import os
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from graph_mapper_agent.interfaces.chat import (
    ChatTurnRequest,
    process_chat_turn,
)
from graph_mapper_agent.platform.llm.config import (
    LlmRuntimeConfig,
)
from graph_mapper_agent.bootstrap.builders.ledger import (
    build_ledger_writer,
)

# --- Configuration ---
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BASE_CONFIGS_DIR = PROJECT_ROOT / "bootstrap" / "configs"
CONFIGS_DIR = Path(os.getenv("GRAPH_MAPPER_CONFIGS_DIR", str(_BASE_CONFIGS_DIR)))
_BASE_LEDGER_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "ledger"
    / "graph_mapper_agent.sqlite3"
)
DEFAULT_LEDGER_URL = os.getenv(
    "GRAPH_MAPPER_LEDGER_URL",
    f"sqlite:///{_BASE_LEDGER_PATH}",
)

# --- Global State ---
executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="graph-mapper-http")
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = Lock()

def load_profiles() -> list[dict[str, Any]]:
    if not CONFIGS_DIR.exists():
        return [empty_profile()]

    items: list[dict[str, Any]] = []
    for path in sorted(CONFIGS_DIR.glob("*.json")):
        try:
            payload = load_profile_payload(path.name)
        except Exception:
            continue
        request_payload = dict(payload.get("request") or {})
        execution_payload = dict(payload.get("execution") or {})
        execution_metadata = dict(execution_payload.get("execution_metadata") or {})
        llm_runtime = dict(payload.get("llm_runtime") or {})
        visual_runtime = dict(payload.get("evidence_extraction_visual_llm_runtime") or {})
        ocr_runtime = dict(payload.get("evidence_extraction_ocr_llm_runtime") or {})
        validation_runtime = dict(payload.get("goal_validation_llm_runtime") or {})
        items.append(
            {
                "name": path.name,
                "entry_url": str(request_payload.get("entry_url") or "").strip(),
                "goal": str(request_payload.get("goal") or "").strip(),
                "decision_mode": str(request_payload.get("decision_mode") or "llm").strip(),
                "research_mode": str(
                    execution_metadata.get("research_mode") or "collect_artifacts"
                ).strip(),
                "source_namespace": str(
                    execution_metadata.get("source_namespace")
                    or execution_payload.get("jurisdiction_code")
                    or "generic"
                ).strip(),
                "principal_model": str(llm_runtime.get("default_model") or "").strip(),
                "ocr_model": str(
                    ocr_runtime.get("default_model")
                    or visual_runtime.get("default_model")
                    or ""
                ).strip(),
                "ocr_mode": str(payload.get("ocr_mode") or "text").strip(),
                "validation_model": str(
                    validation_runtime.get("default_model") or ""
                ).strip(),
                "artifact_persistence_mode": str(
                    execution_metadata.get("artifact_persistence_mode") or "on_validation"
                ).strip(),
                "allow_artifact_download": bool(request_payload.get("allow_artifact_download", True)),
                "allow_artifact_open": bool(request_payload.get("allow_artifact_open", True)),
            }
        )
    return items or [empty_profile()]

def load_profile_payload(name: str) -> dict[str, Any]:
    path = CONFIGS_DIR / name
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)

def empty_profile() -> dict[str, Any]:
    return {
        "name": "no-config.json",
        "entry_url": "",
        "goal": "",
        "decision_mode": "llm",
        "research_mode": "collect_artifacts",
        "allow_artifact_download": True,
        "allow_artifact_open": True,
    }

def build_chat_request(payload: dict[str, Any]) -> tuple[ChatTurnRequest, dict[str, Any]]:
    profiles = load_profiles()
    selected_name = str(payload.get("profile_name") or "").strip()
    selected_profile = next(
        (item for item in profiles if item["name"] == selected_name),
        profiles[0] if profiles else empty_profile(),
    )
    profile_payload = load_profile_payload(selected_profile["name"])

    request_payload = dict(profile_payload.get("request") or {})
    execution_payload = dict(profile_payload.get("execution") or {})
    execution_metadata = dict(execution_payload.get("execution_metadata") or {})
    metadata = dict(request_payload.get("metadata") or {})

    run_id = optional_str(payload.get("run_id")) or f"chat-run-{uuid4().hex[:12]}"
    session_id = optional_str(payload.get("session_id"))

    chat_request = ChatTurnRequest(
        user_message=str(payload.get("user_message") or request_payload.get("goal") or "").strip(),
        entry_url=str(payload.get("entry_url") or request_payload.get("entry_url") or "").strip(),
        session_id=session_id,
        run_id=run_id,
        research_mode=str(payload.get("research_mode") or "collect_artifacts").strip(),
        decision_mode=str(payload.get("decision_mode") or request_payload.get("decision_mode") or "llm").strip(),
        max_hops=int(payload.get("max_hops") or request_payload.get("max_hops") or 250),
        max_pages=int(payload.get("max_pages") or request_payload.get("max_pages") or 500),
        timeout_seconds=int(payload.get("timeout_seconds") or execution_payload.get("timeout_seconds") or 200),
        allow_artifact_download=bool(
            payload.get("allow_artifact_download", request_payload.get("allow_artifact_download", True))
        ),
        allow_artifact_open=bool(
            payload.get("allow_artifact_open", request_payload.get("allow_artifact_open", True))
        ),
        source_namespace=str(
            payload.get("source_namespace")
            or execution_metadata.get("source_namespace")
            or execution_payload.get("jurisdiction_code")
            or "generic"
        ).strip(),
        resource_key=optional_str(
            payload.get("resource_key")
            or execution_metadata.get("resource_key")
            or execution_payload.get("document_key")
        ),
        metadata={
            **metadata,
            **dict(payload.get("metadata") or {}),
            "config_profile": selected_profile["name"],
            "ocr_mode": str(
                payload.get("ocr_mode")
                or metadata.get("ocr_mode")
                or selected_profile.get("ocr_mode")
                or "text"
            ).strip(),
        },
        execution_metadata={
            **execution_metadata,
            **dict(payload.get("execution_metadata") or {}),
            "source_namespace": str(
                payload.get("source_namespace")
                or execution_metadata.get("source_namespace")
                or execution_payload.get("jurisdiction_code")
                or "generic"
            ).strip(),
            "resource_key": optional_str(
                payload.get("resource_key")
                or execution_metadata.get("resource_key")
                or execution_payload.get("document_key")
            ),
            "storage_namespace": str(
                payload.get("storage_namespace")
                or execution_metadata.get("storage_namespace")
                or "graph_mapper_agent"
            ).strip(),
        },
        llm_runtime=runtime_from_profile(profile_payload, "llm_runtime"),
        navigation_perception_llm_runtime=runtime_from_profile(
            profile_payload, "navigation_perception_llm_runtime"
        ),
        goal_validation_llm_runtime=runtime_from_profile(
            profile_payload, "goal_validation_llm_runtime", "document_validation_llm_runtime"
        ),
        evidence_extraction_visual_llm_runtime=runtime_from_profile(
            profile_payload, "evidence_extraction_visual_llm_runtime"
        ),
        evidence_extraction_ocr_llm_runtime=runtime_from_profile(
            profile_payload, "evidence_extraction_ocr_llm_runtime"
        ),
        ledger_database_url=optional_str(
            payload.get("ledger_database_url")
            or (execution_payload.get("ledger") or {}).get("database_url")
            or DEFAULT_LEDGER_URL
        ),
    )
    return chat_request, selected_profile

def runtime_from_profile(profile_payload: dict[str, Any], *keys: str) -> LlmRuntimeConfig | None:
    for key in keys:
        value = profile_payload.get(key)
        if isinstance(value, dict):
            return LlmRuntimeConfig.from_json_dict(value).resolve_defaults()
    return None

def resolve_local_artifact_path(raw_path: str) -> Path | None:
    path = Path(raw_path)
    candidate = path if path.is_absolute() else (PROJECT_ROOT / path)
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError:
        return None
    if not resolved.is_file():
        return None
    return resolved

def is_allowed_artifact_path(path: Path) -> bool:
    allowed_roots = [PROJECT_ROOT.resolve()]
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        return False
    return any(resolved == root or root in resolved.parents for root in allowed_roots)

def job_snapshot(job_id: str) -> dict[str, Any] | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        snapshot = {key: value for key, value in job.items() if key != "future"}
        future = job.get("future")
    if isinstance(future, Future) and future.done() and snapshot["status"] == "running":
        update_job(
            job_id,
            status="failed",
            error={"message": "Job aborted unexpectedly"},
            finished_at=utc_now(),
        )
        return job_snapshot(job_id)
    return snapshot

def update_job(job_id: str, **updates: Any) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.update(updates)

def create_chat_job(chat_request: ChatTurnRequest, profile: dict[str, Any]) -> str:
    job_id = f"job-{uuid4().hex[:12]}"
    job = {
        "job_id": job_id,
        "status": "queued",
        "created_at": utc_now(),
        "started_at": None,
        "finished_at": None,
        "profile_name": profile["name"],
        "session_id": chat_request.resolved_session_id(),
        "run_id": chat_request.run_id,
        "research_mode": chat_request.research_mode,
        "entry_url": chat_request.entry_url,
        "user_message": chat_request.user_message,
        "error": None,
        "result": None,
        "future": None,
    }
    with _jobs_lock:
        _jobs[job_id] = job

    future = executor.submit(run_chat_job, job_id, chat_request)
    with _jobs_lock:
        _jobs[job_id]["future"] = future
    return job_id

def run_chat_job(job_id: str, chat_request: ChatTurnRequest) -> None:
    update_job(job_id, status="running", started_at=utc_now())
    try:
        response = process_chat_turn(chat_request)
    except Exception as exc:
        update_job(
            job_id,
            status="failed",
            finished_at=utc_now(),
            error={
                "error_class": type(exc).__name__,
                "message": str(exc) or repr(exc),
            },
        )
        return

    update_job(
        job_id,
        status="completed",
        finished_at=utc_now(),
        result={
            "session_id": response.session_id,
            "run_id": response.research_response.run_id,
            "final_status": response.research_response.final_status,
            "answer": response.research_response.answer,
            "summary": response.research_response.summary,
        },
    )

def optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def record_plan_state(*, session_id: str, state_payload: dict[str, Any], ledger_database_url: str) -> None:
    writer = build_ledger_writer(ledger_database_url)
    record_session = getattr(writer, "record_session", None)
    if callable(record_session):
        record_session(
            session_id=session_id,
            session_kind="chat_planning",
            context={"research_plan": state_payload.get("plan") or {}},
            metadata={"planning_state": "active"},
        )
    record_message = getattr(writer, "record_message", None)
    if callable(record_message):
        record_message(
            session_id=session_id,
            role="system",
            content={"research_plan": state_payload.get("plan") or {}},
            metadata={"kind": "research_plan_update"},
        )

def record_plan_turn_messages(*, session_id: str, state_payload: dict[str, Any], ledger_database_url: str) -> None:
    messages = state_payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return
    writer = build_ledger_writer(ledger_database_url)
    record_message = getattr(writer, "record_message", None)
    if not callable(record_message):
        return
    for item in messages[-2:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        text = str(item.get("text") or "").strip()
        if role not in {"user", "agent"} or not text:
            continue
        record_message(
            session_id=session_id,
            role="assistant" if role == "agent" else role,
            content={"text": text},
            metadata={
                "kind": "planning_assistant_turn" if role == "agent" else "planning_user_turn",
                "with_launch": bool(item.get("with_launch")),
            },
        )
