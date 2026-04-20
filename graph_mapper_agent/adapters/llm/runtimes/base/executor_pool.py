from __future__ import annotations

import atexit
import os
from concurrent.futures import ThreadPoolExecutor

_AGENT_EXECUTOR: ThreadPoolExecutor | None = None
_AGENT_EXECUTOR_REGISTERED: bool = False


def get_agent_executor() -> ThreadPoolExecutor:
    global _AGENT_EXECUTOR, _AGENT_EXECUTOR_REGISTERED
    if _AGENT_EXECUTOR is None:
        max_workers = int(os.getenv("AITHER_PYDANTICAI_MAX_WORKERS", "8"))
        _AGENT_EXECUTOR = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="pydantic-ai-agent-",
        )
        if not _AGENT_EXECUTOR_REGISTERED:
            atexit.register(cleanup_agent_executor)
            _AGENT_EXECUTOR_REGISTERED = True
    return _AGENT_EXECUTOR


def cleanup_agent_executor() -> None:
    global _AGENT_EXECUTOR
    if _AGENT_EXECUTOR is not None:
        _AGENT_EXECUTOR.shutdown(wait=False)
        _AGENT_EXECUTOR = None

