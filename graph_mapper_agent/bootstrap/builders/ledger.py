from __future__ import annotations
#graph_mapper_agent/bootstrap/builders/ledger.py
from graph_mapper_agent.ledger.adapters.sqlite_ledger_writer import (
    SqliteLedgerWriter,
)
from graph_mapper_agent.ledger.config import (
    resolve_ledger_db_path,
)
from ..timing import ts


def build_ledger_writer(database_url: str | None = None):
    database_path = resolve_ledger_db_path(database_url)

    print(
        f"[{ts()}] [graph_mapper] connecting sqlite ledger writer path={database_path}",
        flush=True,
    )
    return SqliteLedgerWriter.connect(str(database_path))