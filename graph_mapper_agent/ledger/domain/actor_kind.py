from enum import StrEnum


class ActorKind(StrEnum):
    SYSTEM = "system"
    SUPERVISOR = "supervisor"
    AGENT = "agent"
    HUMAN = "human"
