from __future__ import annotations
#graph_mapper_agent/interfaces/http/planning_models.py
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class PlanningMessage:
    role: str
    text: str
    with_launch: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ResearchPlan:
    profile_name: str
    raw_goal: str | None = None
    goal: str | None = None
    goal_trace: dict[str, object] = field(default_factory=dict)
    goal_intent: str | None = None
    proposal_id: str | None = None
    proposal_version: int | None = None
    proposal_status: str | None = None
    proposal_summary: str | None = None
    goal_conditions: list[dict[str, object]] = field(default_factory=list)
    launch_ready: bool = False  # conversational / historical hint
    entry_url: str | None = None
    source_namespace: str | None = None
    research_mode: str | None = None
    principal_model: str | None = None
    ocr_model: str | None = None
    ocr_mode: str | None = None
    validation_model: str | None = None
    allow_artifact_download: bool | None = None
    artifact_persistence_mode: str | None = None
    decision_mode: str | None = None
    planner_backend: str | None = None
    planning_notes: str | None = None
    follow_up_context: dict[str, object] = field(default_factory=dict)

    def has_structured_plan(self) -> bool:
        if isinstance(self.goal_trace, dict) and self.goal_trace:
            return True
        if self.goal_conditions:
            return True
        if (self.proposal_id or "").strip():
            return True
        if (self.proposal_summary or "").strip():
            return True
        if (self.goal_intent or "").strip():
            return True
        if (self.planning_notes or "").strip():
            return True
        return False

    def goal_progress_counts(self) -> dict[str, int]:
        satisfied = 0
        pending = 0

        for item in self.goal_conditions:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "").strip().lower()
            if status == "satisfied":
                satisfied += 1
            else:
                pending += 1

        return {
            "satisfied": satisfied,
            "pending": pending,
            "total": satisfied + pending,
        }

    def launch_ready_effective(self) -> bool:
        return bool(
            self.has_structured_plan()
            and ((self.goal or "").strip() or (self.raw_goal or "").strip())
            and (self.entry_url or "").strip()
            and (self.principal_model or "").strip()
        )

    def plan_state(self) -> str:
        if self.launch_ready_effective():
            return "ready"
        if self.has_structured_plan():
            return "draft"
        return "conversation"

    def ready_to_launch(self) -> bool:
        # Fuente efectiva para la interfaz
        return self.launch_ready_effective()

    def to_dict(self) -> dict[str, object]:
        progress = self.goal_progress_counts()
        return {
            "profile_name": self.profile_name,
            "raw_goal": self.raw_goal,
            "goal": self.goal,
            "goal_trace": dict(self.goal_trace),
            "goal_intent": self.goal_intent,
            "proposal_id": self.proposal_id,
            "proposal_version": self.proposal_version,
            "proposal_status": self.proposal_status,
            "proposal_summary": self.proposal_summary,
            "goal_conditions": list(self.goal_conditions),
            "launch_ready": self.launch_ready,  # historical hint
            "launch_ready_effective": self.launch_ready_effective(),  # for UI
            "entry_url": self.entry_url,
            "source_namespace": self.source_namespace,
            "research_mode": self.research_mode,
            "principal_model": self.principal_model,
            "ocr_model": self.ocr_model,
            "ocr_mode": self.ocr_mode,
            "validation_model": self.validation_model,
            "allow_artifact_download": self.allow_artifact_download,
            "artifact_persistence_mode": self.artifact_persistence_mode,
            "decision_mode": self.decision_mode,
            "planner_backend": self.planner_backend,
            "planning_notes": self.planning_notes,
            "follow_up_context": dict(self.follow_up_context),
            "ready_to_launch": self.ready_to_launch(),
            "has_structured_plan": self.has_structured_plan(),
            "plan_state": self.plan_state(),
            "goal_progress": progress,
        }


@dataclass
class ConversationPlanState:
    session_id: str
    plan: ResearchPlan
    messages: list[PlanningMessage] = field(default_factory=list)
    suggested_mode: str = "conversation"

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "plan": self.plan.to_dict(),
            "messages": [item.to_dict() for item in self.messages],
            "suggested_mode": self.suggested_mode,
        }