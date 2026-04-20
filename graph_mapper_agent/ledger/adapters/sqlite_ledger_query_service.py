from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class SqliteLedgerQueryService:
    def __init__(self, database_path: str) -> None:
        self._database_path = Path(database_path)

    @classmethod
    def connect(cls, database_path: str) -> "SqliteLedgerQueryService":
        return cls(database_path=database_path)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            run_row = connection.execute(
                """
                SELECT *
                FROM runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if run_row is None:
                return None

            steps = [
                self._decode_row(row)
                for row in connection.execute(
                    """
                    SELECT *
                    FROM run_steps
                    WHERE run_id = ?
                    ORDER BY step_id ASC
                    """,
                    (run_id,),
                ).fetchall()
            ]
            llm_calls = [
                self._decode_row(row)
                for row in connection.execute(
                    """
                    SELECT *
                    FROM llm_calls
                    WHERE run_id = ?
                    ORDER BY started_at ASC
                    """,
                    (run_id,),
                ).fetchall()
            ]
            evidence = [
                self._decode_row(row)
                for row in connection.execute(
                    """
                    SELECT *
                    FROM evidence_records
                    WHERE run_id = ?
                    ORDER BY created_at ASC
                    """,
                    (run_id,),
                ).fetchall()
            ]
            evaluations = [
                self._decode_row(row)
                for row in connection.execute(
                    """
                    SELECT *
                    FROM evaluations
                    WHERE run_id = ?
                    ORDER BY created_at ASC
                    """,
                    (run_id,),
                ).fetchall()
            ]

        run_data = self._decode_row(run_row)
        run_data["steps"] = steps
        run_data["llm_calls"] = llm_calls
        run_data["evidence_records"] = evidence
        run_data["evaluations"] = evaluations
        return run_data

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            session_row = connection.execute(
                """
                SELECT *
                FROM sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if session_row is None:
                return None

            messages = [
                self._decode_row(row)
                for row in connection.execute(
                    """
                    SELECT *
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY created_at ASC
                    """,
                    (session_id,),
                ).fetchall()
            ]
            runs = [
                self._decode_row(row)
                for row in connection.execute(
                    """
                    SELECT *
                    FROM runs
                    WHERE session_id = ?
                    ORDER BY started_at ASC
                    """,
                    (session_id,),
                ).fetchall()
            ]
            evaluations = [
                self._decode_row(row)
                for row in connection.execute(
                    """
                    SELECT *
                    FROM evaluations
                    WHERE session_id = ?
                    ORDER BY created_at ASC
                    """,
                    (session_id,),
                ).fetchall()
            ]

        session_data = self._decode_row(session_row)
        session_data["messages"] = messages
        session_data["runs"] = runs
        session_data["evaluations"] = evaluations
        return session_data

    def list_sessions(
        self,
        *,
        limit: int = 20,
        session_kind: str | None = None,
    ) -> list[dict[str, Any]]:
        where_sql = ""
        params: list[Any] = []
        if session_kind:
            where_sql = "WHERE s.session_kind = ?"
            params.append(session_kind)
        params.append(int(limit))

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    s.session_id,
                    s.session_kind,
                    s.context_json,
                    s.metadata_json,
                    s.created_at,
                    s.updated_at,
                    (
                        SELECT COUNT(*)
                        FROM messages m
                        WHERE m.session_id = s.session_id
                    ) AS message_count,
                    (
                        SELECT COUNT(*)
                        FROM runs r
                        WHERE r.session_id = s.session_id
                    ) AS run_count,
                    (
                        SELECT m.role
                        FROM messages m
                        WHERE m.session_id = s.session_id
                        ORDER BY m.created_at DESC
                        LIMIT 1
                    ) AS last_message_role,
                    (
                        SELECT m.content_json
                        FROM messages m
                        WHERE m.session_id = s.session_id
                        ORDER BY m.created_at DESC
                        LIMIT 1
                    ) AS last_message_content_json,
                    (
                        SELECT r.run_id
                        FROM runs r
                        WHERE r.session_id = s.session_id
                        ORDER BY r.started_at DESC
                        LIMIT 1
                    ) AS last_run_id
                FROM sessions s
                {where_sql}
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._decode_row(row) for row in rows]

    def get_evidence(
        self,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
        evidence_kind: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []

        if run_id:
            where.append("er.run_id = ?")
            params.append(run_id)
        if session_id:
            where.append("r.session_id = ?")
            params.append(session_id)
        if evidence_kind:
            where.append("er.evidence_kind = ?")
            params.append(evidence_kind)

        where_sql = "WHERE " + " AND ".join(where) if where else ""
        params.append(int(limit))

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT er.*
                FROM evidence_records er
                LEFT JOIN runs r ON r.run_id = er.run_id
                {where_sql}
                ORDER BY er.created_at ASC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._decode_row(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _decode_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        for key, value in tuple(data.items()):
            if not isinstance(value, str):
                continue
            if key.endswith("_json"):
                data[key] = self._loads_json(value)
        return data

    def _loads_json(self, value: str) -> Any:
        try:
            return json.loads(value)
        except Exception:
            return value
