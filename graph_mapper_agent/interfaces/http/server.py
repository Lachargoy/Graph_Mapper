import os
from graph_mapper_agent.interfaces.http import create_app
from graph_mapper_agent.ledger.adapters.sqlite_ledger_writer import SqliteLedgerWriter
from graph_mapper_agent.ledger.config import resolve_ledger_db_path

app = create_app()

def main():
    # Initialize the database (create tables if they don't exist) before starting
    db_path = resolve_ledger_db_path()
    print(f"[*] Initializing database at: {db_path}")
    SqliteLedgerWriter(str(db_path))

    # Original legacy port
    DEFAULT_PORT = 8791
    host = os.getenv("GRAPH_MAPPER_AGENT_HTTP_HOST", "127.0.0.1")
    port = int(os.getenv("GRAPH_MAPPER_AGENT_HTTP_PORT", str(DEFAULT_PORT)))
    
    # Debug False just like the legacy
    print(f"[*] HTTP server started at http://{host}:{port}")
    app.run(host=host, port=port, debug=False)

if __name__ == "__main__":
    main()
