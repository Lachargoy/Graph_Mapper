from __future__ import annotations
# graph_mapper_agent/ledger/config.py

import os
from pathlib import Path
from urllib.parse import urlparse


GRAPH_MAPPER_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = GRAPH_MAPPER_ROOT / "data"
LEDGER_ROOT = DATA_ROOT / "ledger"
DEFAULT_LEDGER_FILENAME = "graph_mapper_agent.sqlite3"
DEFAULT_LEDGER_PATH = LEDGER_ROOT / DEFAULT_LEDGER_FILENAME


def resolve_graph_mapper_path(raw_path: str | None = None) -> Path:
    """
    Resolve a filesystem path against the graph_mapper_agent package root.

    Rules:
    - None or empty -> graph_mapper_agent/
    - absolute path -> returned as-is
    - relative path -> treated as relative to graph_mapper_agent/
    """
    raw = (raw_path or "").strip()
    if not raw:
        return GRAPH_MAPPER_ROOT

    path = Path(raw)
    if path.is_absolute():
        return path
    return GRAPH_MAPPER_ROOT / path


def resolve_ledger_db_path(database_url: str | None = None) -> Path:
    """
    Resolve the physical ledger DB path.

    Priority:
    1. explicit database_url
    2. AITHER_LEDGER_DATABASE_URL
    3. project-relative default:
       graph_mapper_agent/data/ledger/graph_mapper_agent.sqlite3

    Supported inputs:
    - None
    - 'data/ledger/file.sqlite3'
    - '/absolute/path/file.sqlite3'
    - 'sqlite:///data/ledger/file.sqlite3'      -> treated as project-relative
    - 'sqlite:////absolute/path/file.sqlite3'   -> treated as absolute
    """
    raw = (database_url or os.getenv("AITHER_LEDGER_DATABASE_URL", "") or "").strip()

    if not raw:
        path = DEFAULT_LEDGER_PATH

    elif raw.startswith("sqlite:"):
        path = _path_from_sqlite_url(raw)

    else:
        path = resolve_graph_mapper_path(raw)

    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _path_from_sqlite_url(raw: str) -> Path:
    parsed = urlparse(raw)

    
    # sqlite:///data/ledger/db.sqlite3   -> relative to project
    # sqlite:////tmp/db.sqlite3          -> absolute
    # sqlite:///C:/temp/db.sqlite3       -> windows-ish absolute style
    candidate = (parsed.path or parsed.netloc or "").strip()

    if not candidate:
        return DEFAULT_LEDGER_PATH

    # Unix absolute real: sqlite:////tmp/db.sqlite3
    if candidate.startswith("//"):
        return Path(candidate[1:])

    
    if candidate.startswith("/") and not _looks_like_absolute_windows_path(candidate):
        candidate = candidate.lstrip("/")
        return resolve_graph_mapper_path(candidate)

    return resolve_graph_mapper_path(candidate)


def _looks_like_absolute_windows_path(value: str) -> bool:
    # /C:/temp/file.sqlite3
    return len(value) >= 4 and value[0] == "/" and value[2] == ":" and value[3] in {"/", "\\"}
