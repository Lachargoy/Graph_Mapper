from enum import StrEnum


class EventType(StrEnum):
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    NODE_EXECUTED = "node.executed"
    LLM_CALLED = "llm.called"
    LLM_COMPLETED = "llm.completed"
    LLM_VALIDATION_FAILED = "llm.validation_failed"
    TOOL_FAILED = "tool.failed"
    RETRY_SCHEDULED = "retry.scheduled"
    OVERRIDE_APPLIED = "override.applied"
