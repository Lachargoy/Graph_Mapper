from dataclasses import dataclass


@dataclass(frozen=True)
class RunCorrelation:
    run_id: str
    workflow_name: str
    thread_id: str | None = None
    attempt: int = 1
    node_name: str | None = None
    branch_name: str | None = None
