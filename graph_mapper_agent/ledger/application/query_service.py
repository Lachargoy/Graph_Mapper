from __future__ import annotations

from graph_mapper_agent.ledger.adapters.sqlite_ledger_query_service import (
    SqliteLedgerQueryService,
)
from graph_mapper_agent.ledger.config import (
    resolve_ledger_db_path,
)


def build_ledger_query_service(
    database_url: str | None = None,
) -> SqliteLedgerQueryService:
    database_path = resolve_ledger_db_path(database_url)
    return SqliteLedgerQueryService.connect(str(database_path))