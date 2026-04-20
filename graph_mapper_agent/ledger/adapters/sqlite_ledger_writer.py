from __future__ import annotations
#graph_mapper_agent/ledger/adapters/sqlite_ledger_writer.py
import json
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from graph_mapper_agent.ledger.domain.actor_kind import ActorKind
from graph_mapper_agent.ledger.domain.event_payloads import (
    LlmCalledPayload,
    LlmCompletedPayload,
    LlmValidationFailedPayload,
    NodeExecutedPayload,
    OverrideAppliedPayload,
    RetryScheduledPayload,
    RunCompletedPayload,
    RunFailedPayload,
    RunStartedPayload,
    ToolFailedPayload,
)
from graph_mapper_agent.ledger.domain.event_type import EventType
from graph_mapper_agent.ledger.domain.ledger_event import LedgerEvent
from graph_mapper_agent.ledger.domain.llm_call_metadata import (
    LlmCallMetadata,
)
from graph_mapper_agent.ledger.domain.llm_interaction import (
    LlmInteraction,
)
from graph_mapper_agent.ledger.domain.run_correlation import (
    RunCorrelation,
)
from graph_mapper_agent.ledger.domain.target_ref import TargetRef


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class SqliteLedgerWriter:
    def __init__(self, database_path: str) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._database_path)
        self._connection.row_factory = sqlite3.Row
        self._ensure_schema()

    @classmethod
    def connect(cls, database_path: str) -> "SqliteLedgerWriter":
        return cls(database_path=database_path)

    def append_event(self, event: LedgerEvent | None = None, **kwargs: object) -> object:
        if event is not None:
            self._insert_event(event)
            return None

        run_id = str(kwargs.get("run_id") or "").strip()
        event_type = str(kwargs.get("event_type") or "").strip()
        payload = kwargs.get("payload")
        if not run_id or not event_type or not isinstance(payload, dict):
            raise ValueError("append_event requiere run_id, event_type y payload")

        self._connection.execute(
            """
            INSERT INTO navigation_events (
                run_id,
                event_type,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                run_id,
                event_type,
                json.dumps(payload, ensure_ascii=False, default=self._json_default),
                self._utcnow(),
            ),
        )
        self._connection.commit()
        return None

    def record_run_started(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: RunStartedPayload,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._record_typed_event(
            event_id, EventType.RUN_STARTED, run, actor, payload, target, metadata
        )

    def record_run_completed(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: RunCompletedPayload,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._record_typed_event(
            event_id, EventType.RUN_COMPLETED, run, actor, payload, target, metadata
        )

    def record_run_failed(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: RunFailedPayload,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._record_typed_event(
            event_id, EventType.RUN_FAILED, run, actor, payload, target, metadata
        )

    def record_node_executed(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: NodeExecutedPayload,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._record_typed_event(
            event_id, EventType.NODE_EXECUTED, run, actor, payload, target, metadata
        )

    def record_llm_called(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: LlmCalledPayload,
        llm: LlmCallMetadata,
        llm_io: LlmInteraction | None = None,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._record_typed_event(
            event_id, EventType.LLM_CALLED, run, actor, payload, target, metadata, llm, llm_io
        )

    def record_llm_completed(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: LlmCompletedPayload,
        llm: LlmCallMetadata,
        llm_io: LlmInteraction | None = None,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._record_typed_event(
            event_id, EventType.LLM_COMPLETED, run, actor, payload, target, metadata, llm, llm_io
        )

    def record_llm_validation_failed(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: LlmValidationFailedPayload,
        llm: LlmCallMetadata,
        llm_io: LlmInteraction | None = None,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._record_typed_event(
            event_id,
            EventType.LLM_VALIDATION_FAILED,
            run,
            actor,
            payload,
            target,
            metadata,
            llm,
            llm_io,
        )

    def record_tool_failed(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: ToolFailedPayload,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._record_typed_event(
            event_id, EventType.TOOL_FAILED, run, actor, payload, target, metadata
        )

    def record_retry_scheduled(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: RetryScheduledPayload,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._record_typed_event(
            event_id, EventType.RETRY_SCHEDULED, run, actor, payload, target, metadata
        )

    def record_override_applied(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: OverrideAppliedPayload,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._record_typed_event(
            event_id, EventType.OVERRIDE_APPLIED, run, actor, payload, target, metadata
        )

    def record_evidence(
        self,
        *,
        run_id: str,
        evidence_kind: str,
        source_kind: str | None = None,
        source_url: str | None = None,
        local_path: str | None = None,
        mime_type: str | None = None,
        title: str | None = None,
        content: dict[str, object] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> str:
        evidence_id = f"evidence-{uuid4().hex}"
        self._connection.execute(
            """
            INSERT INTO evidence_records (
                evidence_id,
                run_id,
                evidence_kind,
                source_kind,
                source_url,
                local_path,
                mime_type,
                title,
                content_json,
                metadata_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence_id,
                run_id,
                evidence_kind,
                source_kind,
                source_url,
                local_path,
                mime_type,
                title,
                self._to_json(content or {}),
                self._to_json(metadata or {}),
                self._utcnow(),
            ),
        )
        self._connection.commit()
        return evidence_id

    def record_session(
        self,
        *,
        session_id: str,
        session_kind: str = "runtime",
        context: dict[str, object] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> str:
        now = self._utcnow()
        self._connection.execute(
            """
            INSERT INTO sessions (
                session_id,
                session_kind,
                created_at,
                updated_at,
                context_json,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                updated_at = excluded.updated_at,
                context_json = excluded.context_json,
                metadata_json = excluded.metadata_json
            """,
            (
                session_id,
                session_kind,
                now,
                now,
                self._to_json(context or {}),
                self._to_json(metadata or {}),
            ),
        )
        self._connection.commit()
        return session_id

    def record_message(
        self,
        *,
        session_id: str,
        role: str,
        content: dict[str, object],
        metadata: dict[str, object] | None = None,
    ) -> str:
        message_id = f"msg-{uuid4().hex}"
        self._connection.execute(
            """
            INSERT INTO messages (
                message_id,
                session_id,
                role,
                content_json,
                created_at,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                session_id,
                role,
                self._to_json(content),
                self._utcnow(),
                self._to_json(metadata or {}),
            ),
        )
        self._connection.commit()
        return message_id

    def record_evaluation(
        self,
        *,
        target_kind: str,
        evaluator_kind: str,
        run_id: str | None = None,
        session_id: str | None = None,
        score: float | None = None,
        label: str | None = None,
        usable_for_training: bool = False,
        feedback: dict[str, object] | None = None,
    ) -> str:
        evaluation_id = f"eval-{uuid4().hex}"
        if run_id:
            self._connection.execute(
                """
                INSERT INTO runs (
                    run_id,
                    workflow_name,
                    started_at,
                    metadata_json
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id) DO NOTHING
                """,
                (
                    run_id,
                    "unknown",
                    self._utcnow(),
                    self._to_json({"session_id": session_id} if session_id else {}),
                ),
            )
        self._connection.execute(
            """
            INSERT INTO evaluations (
                evaluation_id,
                session_id,
                run_id,
                target_kind,
                evaluator_kind,
                score,
                label,
                usable_for_training,
                feedback_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evaluation_id,
                session_id,
                run_id,
                target_kind,
                evaluator_kind,
                score,
                label,
                1 if usable_for_training else 0,
                self._to_json(feedback or {}),
                self._utcnow(),
            ),
        )
        if run_id:
            self._connection.execute(
                """
                UPDATE runs
                SET
                    quality_score = COALESCE(?, quality_score),
                    quality_label = COALESCE(?, quality_label)
                WHERE run_id = ?
                """,
                (
                    score,
                    label,
                    run_id,
                ),
            )
        self._connection.commit()
        return evaluation_id

    def _record_typed_event(
        self,
        event_id: str,
        event_type: EventType,
        run: RunCorrelation,
        actor: ActorKind,
        payload: object,
        target: TargetRef | None,
        metadata: dict[str, object] | None,
        llm: LlmCallMetadata | None = None,
        llm_io: LlmInteraction | None = None,
    ) -> None:
        self._insert_event(
            LedgerEvent(
                event_id=event_id,
                event_type=event_type,
                run=run,
                actor=actor,
                payload=payload,
                target=target,
                metadata=metadata or {},
                llm=llm,
                llm_io=llm_io,
            )
        )

    def _insert_event(self, event: LedgerEvent) -> None:
        self._ensure_run_row(event.run, metadata=event.metadata)
        payload_json = self._to_json(event.payload)
        metadata_json = self._to_json(event.metadata)
        llm_json = self._to_json(event.llm) if event.llm is not None else None
        llm_io_json = self._to_json(event.llm_io) if event.llm_io is not None else None
        target_context_json = self._to_json(event.target.context if event.target else {})
        occurred_at = event.occurred_at.astimezone(timezone.utc).isoformat()

        self._connection.execute(
            """
            INSERT INTO ledger_events (
                event_id,
                run_id,
                thread_id,
                workflow_name,
                attempt,
                node_name,
                branch_name,
                event_type,
                actor_kind,
                target_kind,
                target_id,
                target_context_json,
                payload_json,
                metadata_json,
                llm_json,
                llm_io_json,
                occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.run.run_id,
                event.run.thread_id,
                event.run.workflow_name,
                event.run.attempt,
                event.run.node_name,
                event.run.branch_name,
                str(event.event_type),
                str(event.actor),
                event.target.target_kind if event.target else None,
                event.target.target_id if event.target else None,
                target_context_json,
                payload_json,
                metadata_json,
                llm_json,
                llm_io_json,
                occurred_at,
            ),
        )
        self._connection.execute(
            """
            INSERT INTO run_steps (
                run_id,
                step_index,
                node_name,
                branch_name,
                event_type,
                payload_json,
                metadata_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.run.run_id,
                None,
                event.run.node_name,
                event.run.branch_name,
                str(event.event_type),
                payload_json,
                metadata_json,
                occurred_at,
            ),
        )
        self._update_run_projection(event, occurred_at)
        self._record_llm_call_projection(event, occurred_at)
        self._connection.commit()

    def _ensure_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                session_kind TEXT NOT NULL DEFAULT 'runtime',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                context_json TEXT NOT NULL DEFAULT '{}',
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                session_id TEXT,
                workflow_name TEXT NOT NULL,
                thread_id TEXT,
                attempt INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'running',
                started_at TEXT NOT NULL,
                finished_at TEXT,
                input_json TEXT NOT NULL DEFAULT '{}',
                final_output_json TEXT NOT NULL DEFAULT '{}',
                context_json TEXT NOT NULL DEFAULT '{}',
                quality_score REAL,
                quality_label TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS run_steps (
                step_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                step_index INTEGER,
                node_name TEXT,
                branch_name TEXT,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS llm_calls (
                call_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                session_id TEXT,
                operation_name TEXT NOT NULL,
                provider_name TEXT,
                model_name TEXT,
                prompt_version TEXT,
                structured_output_name TEXT,
                request_kind TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                success INTEGER NOT NULL DEFAULT 0,
                response_format_valid INTEGER,
                finish_reason TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                reasoning_tokens INTEGER,
                cached_tokens INTEGER,
                total_tokens INTEGER,
                latency_ms INTEGER,
                messages_json TEXT NOT NULL DEFAULT '{}',
                expected_output_json TEXT NOT NULL DEFAULT '{}',
                response_json TEXT NOT NULL DEFAULT '{}',
                validation_json TEXT NOT NULL DEFAULT '{}',
                raw_response_json TEXT NOT NULL DEFAULT '{}',
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS evidence_records (
                evidence_id TEXT PRIMARY KEY,
                run_id TEXT,
                step_id INTEGER,
                evidence_kind TEXT NOT NULL,
                source_kind TEXT,
                source_url TEXT,
                local_path TEXT,
                mime_type TEXT,
                title TEXT,
                content_json TEXT NOT NULL DEFAULT '{}',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS evaluations (
                evaluation_id TEXT PRIMARY KEY,
                session_id TEXT,
                run_id TEXT,
                step_id INTEGER,
                target_kind TEXT NOT NULL,
                evaluator_kind TEXT NOT NULL,
                score REAL,
                label TEXT,
                usable_for_training INTEGER NOT NULL DEFAULT 0,
                feedback_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ledger_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                thread_id TEXT,
                workflow_name TEXT NOT NULL,
                attempt INTEGER NOT NULL DEFAULT 1,
                node_name TEXT,
                branch_name TEXT,
                event_type TEXT NOT NULL,
                actor_kind TEXT,
                target_kind TEXT,
                target_id TEXT,
                target_context_json TEXT NOT NULL DEFAULT '{}',
                payload_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                llm_json TEXT,
                llm_io_json TEXT,
                occurred_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS navigation_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_ledger_events_run_id
                ON ledger_events(run_id, occurred_at);
            CREATE INDEX IF NOT EXISTS idx_ledger_events_type
                ON ledger_events(event_type, occurred_at);
            CREATE INDEX IF NOT EXISTS idx_runs_started_at
                ON runs(started_at);
            CREATE INDEX IF NOT EXISTS idx_run_steps_run_id
                ON run_steps(run_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_llm_calls_run_id
                ON llm_calls(run_id, started_at);
            CREATE INDEX IF NOT EXISTS idx_navigation_events_run_id
                ON navigation_events(run_id, created_at);
            """
        )
        self._connection.commit()

    def _ensure_run_row(
        self,
        run: RunCorrelation,
        *,
        metadata: dict[str, object] | None = None,
    ) -> None:
        now = self._utcnow()
        metadata_dict = dict(metadata or {})
        self._connection.execute(
            """
            INSERT INTO runs (
                run_id,
                session_id,
                workflow_name,
                thread_id,
                attempt,
                started_at,
                context_json,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO NOTHING
            """,
            (
                run.run_id,
                _optional_str(metadata_dict.get("session_id")),
                run.workflow_name,
                run.thread_id,
                run.attempt,
                now,
                self._to_json({}),
                self._to_json(metadata_dict),
            ),
        )

    def _record_llm_call_projection(self, event: LedgerEvent, occurred_at: str) -> None:
        if event.event_type not in {
            EventType.LLM_CALLED,
            EventType.LLM_COMPLETED,
            EventType.LLM_VALIDATION_FAILED,
        }:
            return

        metadata = event.metadata or {}
        call_id = str(metadata.get("call_id") or f"llm-{uuid4().hex}").strip()
        payload_dict = event.payload.to_dict()
        llm = event.llm
        llm_io = event.llm_io

        if event.event_type == EventType.LLM_CALLED:
            self._connection.execute(
                """
                INSERT INTO llm_calls (
                    call_id,
                    run_id,
                    operation_name,
                    provider_name,
                    model_name,
                    prompt_version,
                    structured_output_name,
                    request_kind,
                    started_at,
                    messages_json,
                    expected_output_json,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(call_id) DO NOTHING
                """,
                (
                    call_id,
                    event.run.run_id,
                    payload_dict.get("operation_name") or "unknown",
                    llm.provider if llm else None,
                    llm.model if llm else None,
                    llm.prompt_version if llm else None,
                    llm.structured_output_name if llm else None,
                    payload_dict.get("request_kind"),
                    occurred_at,
                    self._to_json(llm_io.input if llm_io else {}),
                    self._to_json(llm_io.expected_output if llm_io else {}),
                    self._to_json(metadata),
                ),
            )
            return

        if event.event_type == EventType.LLM_COMPLETED:
            self._connection.execute(
                """
                UPDATE llm_calls
                SET
                    completed_at = ?,
                    success = 1,
                    response_format_valid = ?,
                    finish_reason = ?,
                    provider_name = COALESCE(?, provider_name),
                    model_name = COALESCE(?, model_name),
                    prompt_version = COALESCE(?, prompt_version),
                    structured_output_name = COALESCE(?, structured_output_name),
                    input_tokens = COALESCE(?, input_tokens),
                    output_tokens = COALESCE(?, output_tokens),
                    reasoning_tokens = COALESCE(?, reasoning_tokens),
                    cached_tokens = COALESCE(?, cached_tokens),
                    total_tokens = COALESCE(?, total_tokens),
                    latency_ms = COALESCE(?, latency_ms),
                    response_json = ?,
                    validation_json = ?,
                    raw_response_json = ?,
                    metadata_json = ?
                WHERE call_id = ?
                """,
                (
                    occurred_at,
                    1 if payload_dict.get("response_format_valid") else 0,
                    payload_dict.get("finish_reason"),
                    llm.provider if llm else None,
                    llm.model if llm else None,
                    llm.prompt_version if llm else None,
                    llm.structured_output_name if llm else None,
                    llm.input_tokens if llm else None,
                    llm.output_tokens if llm else None,
                    llm.reasoning_tokens if llm else None,
                    llm.cached_tokens if llm else None,
                    llm.total_tokens if llm else None,
                    llm.latency_ms if llm else None,
                    self._to_json(llm_io.response if llm_io else {}),
                    self._to_json(llm_io.validation if llm_io else {}),
                    self._to_json(
                        (llm_io.response or {}).get("raw_response", {}) if llm_io else {}
                    ),
                    self._to_json(metadata),
                    call_id,
                ),
            )
            return

        self._connection.execute(
            """
            UPDATE llm_calls
            SET
                completed_at = COALESCE(completed_at, ?),
                success = 0,
                response_format_valid = 0,
                validation_json = ?,
                metadata_json = ?
            WHERE call_id = ?
            """,
            (
                occurred_at,
                self._to_json(llm_io.validation if llm_io else {}),
                self._to_json(metadata),
                call_id,
            ),
        )

    def _update_run_projection(self, event: LedgerEvent, occurred_at: str) -> None:
        if event.event_type == EventType.RUN_STARTED:
            self._connection.execute(
                """
                UPDATE runs
                SET
                    status = 'running',
                    started_at = COALESCE(started_at, ?),
                    metadata_json = ?
                WHERE run_id = ?
                """,
                (
                    occurred_at,
                    self._to_json(event.metadata or {}),
                    event.run.run_id,
                ),
            )
            return

        if event.event_type == EventType.RUN_COMPLETED:
            self._connection.execute(
                """
                UPDATE runs
                SET
                    status = 'completed',
                    finished_at = ?,
                    final_output_json = ?,
                    metadata_json = ?
                WHERE run_id = ?
                """,
                (
                    occurred_at,
                    self._to_json(event.metadata or {}),
                    self._to_json(event.metadata or {}),
                    event.run.run_id,
                ),
            )
            return

        if event.event_type == EventType.RUN_FAILED:
            self._connection.execute(
                """
                UPDATE runs
                SET
                    status = 'failed',
                    finished_at = ?,
                    metadata_json = ?
                WHERE run_id = ?
                """,
                (
                    occurred_at,
                    self._to_json(event.metadata or {}),
                    event.run.run_id,
                ),
            )

    @staticmethod
    def _utcnow() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _json_default(value: object) -> object:
        if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
            return value.to_dict()
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat()
        return str(value)

    def _to_json(self, value: object) -> str:
        return json.dumps(value, ensure_ascii=False, default=self._json_default)
