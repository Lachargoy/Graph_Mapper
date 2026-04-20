from __future__ import annotations
#graph_mapper_agent/interfaces/http/planning_service.py
import json
import logging
from datetime import datetime
from dataclasses import replace
from threading import Lock
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from graph_mapper_agent.adapters.llm.composition.runtime_factory import (
    build_llm_runtime,
)
from graph_mapper_agent.application.services.goals.planner import (
    GoalPlannerRequest,
    GoalPlannerUseCase,
)
from graph_mapper_agent.domain.ports.llm_runtime_port import (
    LlmRuntimeRequest,
)
from graph_mapper_agent.platform.llm.config import (
    LlmRuntimeConfig,
)
from graph_mapper_agent.platform.llm.resolve_runtime_plan import (
    resolve_runtime_plan,
)

from .planning_models import ConversationPlanState, PlanningMessage, ResearchPlan

logger = logging.getLogger(__name__)

# ── Timeouts (seconds) ──────────────────────────────────────────────────────
_PLANNING_TURN_TIMEOUT_S = 180
_GOAL_PLANNER_TIMEOUT_S = 180

_sessions: dict[str, ConversationPlanState] = {}
_lock = Lock()


# ── Explicit protocol for LLM runtime ──────────────────────────────────────
@runtime_checkable
class _LlmRuntime(Protocol):
    def invoke(self, request: LlmRuntimeRequest) -> Any: ...


def _current_date_context() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


# ── Public API ──────────────────────────────────────────────────────────────

def create_plan_state(
    profile: dict[str, Any],
    *,
    session_id: str | None = None,
) -> ConversationPlanState:
    resolved_session_id = (session_id or "").strip() or f"plan-{uuid4().hex[:12]}"
    plan = _plan_from_profile(profile)
    _sync_plan_consistency(plan)

    state = ConversationPlanState(
        session_id=resolved_session_id,
        plan=plan,
        messages=[
            PlanningMessage(
                role="agent",
                text=(
                    "Hi. I am your research agent. Tell me what you want to investigate "
                    "and I will build the plan on the right side."
                ),
            )
        ],
        suggested_mode=_suggested_mode(plan),
    )
    with _lock:
        _sessions[resolved_session_id] = state
    return state


def get_plan_state(session_id: str) -> ConversationPlanState | None:
    with _lock:
        state = _sessions.get(session_id)
        if state is None:
            return None
        return _clone_state(state)


def hydrate_plan_state_from_session(
    *,
    session_id: str,
    profile: dict[str, Any],
    session_payload: dict[str, Any],
) -> ConversationPlanState:
    plan_payload = _extract_research_plan_payload(session_payload) or {}
    plan = _plan_from_profile(profile)
    _merge_plan_payload(plan, plan_payload)
    _sync_plan_consistency(plan)

    messages = _extract_planning_messages(session_payload)
    if not messages:
        messages = [
            PlanningMessage(
                role="agent",
                text=(
                    "Session loaded. You can continue refining the plan or launch another "
                    "research from here."
                ),
            )
        ]
    state = ConversationPlanState(
        session_id=session_id,
        plan=plan,
        messages=messages,
        suggested_mode=_suggested_mode(plan),
    )
    with _lock:
        _sessions[session_id] = state
    return _clone_state(state)


def process_plan_turn(
    *,
    session_id: str | None,
    profile: dict[str, Any],
    user_message: str,
    entry_url: str | None = None,
    source_namespace: str | None = None,
    follow_up_context: dict[str, object] | None = None,
    llm_runtime_config: LlmRuntimeConfig | None = None,
) -> ConversationPlanState:
    text = user_message.strip()
    if not text:
        raise ValueError("user_message cannot be empty.")

    resolved_id = (session_id or "").strip()

    # ── 1. Read current state (brief lock) ──────────────────────────────────
    with _lock:
        existing = _sessions.get(resolved_id)
        if existing is None:
            working = ConversationPlanState(
                session_id=resolved_id or f"plan-{uuid4().hex[:12]}",
                plan=_plan_from_profile(profile),
                messages=[],
                suggested_mode="conversation",
            )
        else:
            working = _clone_state(existing)

    # ── 2. Apply profile updates on the copy ────────────────────────────────
    working.plan.profile_name = str(profile.get("name") or working.plan.profile_name).strip()
    if entry_url is not None:
        working.plan.entry_url = entry_url.strip() or working.plan.entry_url
    if source_namespace is not None:
        working.plan.source_namespace = source_namespace.strip() or working.plan.source_namespace
    if isinstance(follow_up_context, dict):
        working.plan.follow_up_context = dict(follow_up_context)

    _sync_plan_consistency(working.plan)

    # ── 3. LLM calls outside the lock ───────────────────────────────────────
    recent_messages = _recent_messages_payload(working.messages)
    goal_context = _build_goal_context(working.messages, working.plan, text)

    try:
        turn = _resolve_llm_turn(text, working.plan, recent_messages, llm_runtime_config)
    except Exception as exc:
        raise RuntimeError(
            f"Error in _resolve_llm_turn [session={working.session_id!r}]: {exc}"
        ) from exc

    assistant_reply = str(turn.get("assistant_reply") or "").strip()
    if not assistant_reply:
        raise RuntimeError("The conversational planner did not return assistant_reply.")

    # ── 4. Conversational mode (no researchable goal) ───────────────────────
    if turn["turn_kind"] == "conversation" or not bool(turn.get("has_research_goal", False)):
        working.plan.launch_ready = False
        working.plan.planner_backend = str(turn["backend"] or "fallback")
        working.plan.follow_up_context = dict(working.plan.follow_up_context)
        working.plan.follow_up_context["plan_state"] = "conversation"

        working.messages.append(PlanningMessage(role="user", text=text))
        working.messages.append(
            PlanningMessage(role="agent", text=assistant_reply, with_launch=False)
        )
        working.suggested_mode = "conversation"

        with _lock:
            _sessions[working.session_id] = working
        return _clone_state(working)

    # ── 5. plan_update / launch mode ────────────────────────────────────────
    _apply_turn_plan_patch(working.plan, turn)

    try:
        llm_plan = _resolve_llm_plan(goal_context, llm_runtime_config)
    except Exception as exc:
        logger.warning(
            "Error in _resolve_llm_plan [session=%r]: %s — using fallback.",
            working.session_id,
            exc,
        )
        llm_plan = _empty_llm_plan()

    # Curated/rich request for the interface
    working.plan.raw_goal = str(turn.get("structured_request") or text).strip()

    # Operational goal for the agent
    working.plan.goal = llm_plan["summary"] or text

    if llm_plan["summary"]:
        working.plan.planner_backend = "llm"
    else:
        working.plan.planner_backend = "fallback"

    working.plan.goal_intent = llm_plan["intent"]
    working.plan.goal_trace = dict(llm_plan["goal_trace"])
    working.plan.proposal_id = llm_plan["proposal_id"]
    working.plan.proposal_version = llm_plan["proposal_version"]
    working.plan.proposal_status = llm_plan["proposal_status"]
    working.plan.proposal_summary = llm_plan["proposal_summary"]
    working.plan.planning_notes = llm_plan["notes"]
    working.plan.goal_conditions = llm_plan["conditions"]

    _sync_plan_consistency(working.plan)

    explicit_launch_ready = (
        isinstance(turn.get("plan_patch"), dict)
        and "launch_ready" in turn["plan_patch"]
    )

    if explicit_launch_ready:
        # Clamp: never allow true if structurally not ready
        working.plan.launch_ready = bool(
            working.plan.launch_ready and working.plan.launch_ready_effective()
        )
    else:
        # Effective source for UI / launcher
        working.plan.launch_ready = working.plan.launch_ready_effective()

    working.suggested_mode = _suggested_mode(working.plan)
    working.messages.append(PlanningMessage(role="user", text=text))
    working.messages.append(
        PlanningMessage(
            role="agent",
            text=assistant_reply,
            with_launch=working.plan.launch_ready_effective(),
        )
    )

    # ── 6. Atomic commit of final state ──────────────────────────────────────
    with _lock:
        _sessions[working.session_id] = working

    return _clone_state(working)


# ── Construction helpers ─────────────────────────────────────────────────────

def _plan_from_profile(profile: dict[str, Any]) -> ResearchPlan:
    return ResearchPlan(
        profile_name=str(profile.get("name") or "no-config.json").strip(),
        raw_goal=None,
        goal=None,
        entry_url=str(profile.get("entry_url") or "").strip() or None,
        source_namespace=str(profile.get("source_namespace") or "generic").strip() or "generic",
        research_mode=str(profile.get("research_mode") or "collect_artifacts").strip() or "collect_artifacts",
        principal_model=str(profile.get("principal_model") or "").strip() or None,
        ocr_model=str(profile.get("ocr_model") or "").strip() or None,
        ocr_mode=str(profile.get("ocr_mode") or "").strip() or None,
        validation_model=str(profile.get("validation_model") or "").strip() or None,
        allow_artifact_download=bool(profile.get("allow_artifact_download", True)),
        artifact_persistence_mode=str(
            profile.get("artifact_persistence_mode") or "on_validation"
        ).strip() or "on_validation",
        decision_mode=str(profile.get("decision_mode") or "llm").strip() or "llm",
        planner_backend="profile",
    )


def _merge_plan_payload(plan: ResearchPlan, payload: dict[str, Any]) -> None:
    plan.raw_goal = _clean_text(payload.get("raw_goal")) or plan.raw_goal
    plan.goal = _clean_text(payload.get("goal")) or plan.goal

    goal_trace = payload.get("goal_trace")
    if isinstance(goal_trace, dict):
        plan.goal_trace = dict(goal_trace)

    plan.goal_intent = _clean_text(payload.get("goal_intent")) or plan.goal_intent
    plan.proposal_id = _clean_text(payload.get("proposal_id")) or plan.proposal_id

    proposal_version = payload.get("proposal_version")
    if isinstance(proposal_version, int):
        plan.proposal_version = proposal_version

    plan.proposal_status = _clean_text(payload.get("proposal_status")) or plan.proposal_status
    plan.proposal_summary = _clean_text(payload.get("proposal_summary")) or plan.proposal_summary

    goal_conditions = payload.get("goal_conditions")
    if isinstance(goal_conditions, list):
        plan.goal_conditions = [dict(item) for item in goal_conditions if isinstance(item, dict)]

    launch_ready = payload.get("launch_ready")
    if isinstance(launch_ready, bool):
        plan.launch_ready = launch_ready

    plan.entry_url = _clean_text(payload.get("entry_url")) or plan.entry_url
    plan.source_namespace = _clean_text(payload.get("source_namespace")) or plan.source_namespace
    plan.research_mode = _clean_text(payload.get("research_mode")) or plan.research_mode
    plan.principal_model = _clean_text(payload.get("principal_model")) or plan.principal_model
    plan.ocr_model = _clean_text(payload.get("ocr_model")) or plan.ocr_model
    plan.ocr_mode = _clean_text(payload.get("ocr_mode")) or plan.ocr_mode
    plan.validation_model = _clean_text(payload.get("validation_model")) or plan.validation_model

    allow_artifact_download = payload.get("allow_artifact_download")
    if isinstance(allow_artifact_download, bool):
        plan.allow_artifact_download = allow_artifact_download

    plan.artifact_persistence_mode = (
        _clean_text(payload.get("artifact_persistence_mode")) or plan.artifact_persistence_mode
    )
    plan.decision_mode = _clean_text(payload.get("decision_mode")) or plan.decision_mode
    plan.planner_backend = _clean_text(payload.get("planner_backend")) or plan.planner_backend
    plan.planning_notes = _clean_text(payload.get("planning_notes")) or plan.planning_notes

    follow_up_context = payload.get("follow_up_context")
    if isinstance(follow_up_context, dict):
        plan.follow_up_context = dict(follow_up_context)

    _sync_plan_consistency(plan)


def _sync_plan_consistency(plan: ResearchPlan) -> None:
    trace = plan.goal_trace if isinstance(plan.goal_trace, dict) else {}
    if not trace:
        plan.follow_up_context = dict(plan.follow_up_context)
        plan.follow_up_context["plan_state"] = plan.plan_state()
        plan.follow_up_context["launch_ready_effective"] = plan.launch_ready_effective()
        return

    intent = trace.get("intent")
    if isinstance(intent, dict):
        normalized_goal = _clean_text(intent.get("normalized_goal"))
        if normalized_goal and not (plan.goal_intent or "").strip():
            plan.goal_intent = normalized_goal

    proposals = trace.get("proposals")
    active_id = _clean_text(trace.get("active_proposal_id"))

    active: dict[str, Any] | None = None
    if isinstance(proposals, list) and proposals:
        if active_id:
            for proposal in proposals:
                if isinstance(proposal, dict) and _clean_text(proposal.get("proposal_id")) == active_id:
                    active = proposal
                    break
        if active is None:
            for proposal in reversed(proposals):
                if isinstance(proposal, dict):
                    active = proposal
                    break

    if isinstance(active, dict):
        plan.proposal_id = _clean_text(active.get("proposal_id")) or plan.proposal_id

        version = active.get("version")
        if isinstance(version, int):
            plan.proposal_version = version

        plan.proposal_status = _clean_text(active.get("status")) or plan.proposal_status
        plan.proposal_summary = _clean_text(active.get("summary")) or plan.proposal_summary
        plan.planning_notes = _clean_text(active.get("planning_notes")) or plan.planning_notes

        conditions = active.get("conditions")
        if isinstance(conditions, list):
            plan.goal_conditions = [
                dict(item) for item in conditions if isinstance(item, dict)
            ]

        if not (plan.goal or "").strip():
            summary = _clean_text(active.get("summary"))
            if summary:
                plan.goal = summary

    plan.follow_up_context = dict(plan.follow_up_context)
    plan.follow_up_context["plan_state"] = plan.plan_state()
    plan.follow_up_context["launch_ready_effective"] = plan.launch_ready_effective()


def _extract_research_plan_payload(session_payload: dict[str, Any]) -> dict[str, Any] | None:
    context = session_payload.get("context_json")
    if isinstance(context, dict):
        research_plan = context.get("research_plan")
        if isinstance(research_plan, dict):
            return dict(research_plan)

    messages = session_payload.get("messages")
    if not isinstance(messages, list):
        return None

    for item in reversed(messages):
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata_json")
        if isinstance(metadata, dict) and metadata.get("kind") == "research_plan_update":
            content = item.get("content_json")
            if isinstance(content, dict):
                research_plan = content.get("research_plan")
                if isinstance(research_plan, dict):
                    return dict(research_plan)
    return None


def _extract_planning_messages(session_payload: dict[str, Any]) -> list[PlanningMessage]:
    raw_messages = session_payload.get("messages")
    if not isinstance(raw_messages, list):
        return []

    messages: list[PlanningMessage] = []
    for item in raw_messages:
        if not isinstance(item, dict):
            continue

        role = str(item.get("role") or "").strip().lower()
        content = item.get("content_json")
        metadata = item.get("metadata_json")
        kind = metadata.get("kind") if isinstance(metadata, dict) else None

        if kind in {"research_plan_update", "runtime_bootstrap_input"}:
            continue

        text = _extract_message_text(role, content)
        if not text:
            continue

        normalized_role = "agent" if role == "assistant" else role
        if normalized_role not in {"user", "agent", "system"}:
            normalized_role = "system"

        messages.append(PlanningMessage(role=normalized_role, text=text, with_launch=False))
    return messages


def _extract_message_text(role: str, content: Any) -> str | None:
    if isinstance(content, str):
        return _clean_text(content)
    if not isinstance(content, dict):
        return None
    if role == "user":
        return _clean_text(content.get("text") or content.get("goal"))
    if role == "assistant":
        return _clean_text(content.get("text") or content.get("answer") or content.get("summary"))
    return _clean_text(
        content.get("text") or content.get("summary") or content.get("answer")
    )


def _clean_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _apply_turn_plan_patch(plan: ResearchPlan, turn: dict[str, object]) -> None:
    plan_patch = turn.get("plan_patch")
    if not isinstance(plan_patch, dict):
        return

    if "launch_ready" in plan_patch:
        value = plan_patch.get("launch_ready")
        if isinstance(value, bool):
            plan.launch_ready = value

    research_mode = str(plan_patch.get("research_mode") or "").strip()
    if research_mode:
        plan.research_mode = research_mode

    artifact_persistence_mode = str(plan_patch.get("artifact_persistence_mode") or "").strip()
    if artifact_persistence_mode:
        plan.artifact_persistence_mode = artifact_persistence_mode

    if "allow_artifact_download" in plan_patch:
        value = plan_patch.get("allow_artifact_download")
        if isinstance(value, bool):
            plan.allow_artifact_download = value

    source_namespace = str(plan_patch.get("source_namespace") or "").strip()
    if source_namespace:
        plan.source_namespace = source_namespace

    entry_url = str(plan_patch.get("entry_url") or "").strip()
    if entry_url:
        plan.entry_url = entry_url


# ── LLM ─────────────────────────────────────────────────────────────────────

def _empty_llm_plan() -> dict[str, object]:
    return {
        "intent": None,
        "goal_trace": {},
        "summary": None,
        "proposal_id": None,
        "proposal_version": None,
        "proposal_status": None,
        "proposal_summary": None,
        "notes": None,
        "conditions": [],
    }


def _resolve_llm_plan(
    user_message: str,
    llm_runtime_config: LlmRuntimeConfig | None,
) -> dict[str, object]:
    if llm_runtime_config is None:
        return _empty_llm_plan()

    runtime_config = llm_runtime_config
    if runtime_config.timeout_seconds is None or runtime_config.timeout_seconds > _GOAL_PLANNER_TIMEOUT_S:
        runtime_config = replace(runtime_config, timeout_seconds=_GOAL_PLANNER_TIMEOUT_S)

    try:
        result = GoalPlannerUseCase(llm_runtime_config=runtime_config).plan(
            GoalPlannerRequest(goal_context=user_message)
        )
    except Exception:
        return _empty_llm_plan()

    trace = result.goal_trace
    proposal = None if trace is None else trace.active_proposal()
    intent = None if trace is None else (_clean_text(getattr(trace.intent, "normalized_goal", None)))
    trace_payload = _goal_trace_payload(trace)
    summary = _clean_text(getattr(proposal, "summary", None)) if proposal is not None else None
    if summary is None:
        summary = intent
    notes = _clean_text(result.planning_notes)

    conditions: list[dict[str, object]] = []
    if proposal is not None:
        for item in proposal.conditions:
            conditions.append(
                {
                    "condition_id": item.condition_id,
                    "label": item.label,
                    "kind": item.kind,
                    "target_kind": item.target_kind,
                    "requiredness": item.requiredness,
                    "filters": dict(item.filters),
                    "min_count": item.min_count,
                    "status": item.status,
                    "matched_finding_ids": list(item.matched_finding_ids or ()),
                }
            )

    return {
        "intent": intent,
        "goal_trace": trace_payload,
        "summary": summary,
        "proposal_id": None if proposal is None else proposal.proposal_id,
        "proposal_version": None if proposal is None else proposal.version,
        "proposal_status": None if proposal is None else proposal.status,
        "proposal_summary": None if proposal is None else _clean_text(getattr(proposal, "summary", None)),
        "notes": notes,
        "conditions": conditions,
    }


def _resolve_llm_turn(
    user_message: str,
    plan: ResearchPlan,
    recent_messages: list[dict[str, str]],
    llm_runtime_config: LlmRuntimeConfig | None,
) -> dict[str, object]:
    if llm_runtime_config is None:
        raise RuntimeError("No hay llm_runtime_config para el planner conversacional.")

    runtime_config = llm_runtime_config
    if runtime_config.timeout_seconds is None or runtime_config.timeout_seconds > _PLANNING_TURN_TIMEOUT_S:
        runtime_config = replace(runtime_config, timeout_seconds=_PLANNING_TURN_TIMEOUT_S)

    plan_runtime = resolve_runtime_plan(
        runtime_config,
        expected_output_name="graph_mapper_planning_turn",
        tools_requested=False,
    )
    runtime = build_llm_runtime(plan_runtime).runtime

    response = _invoke_runtime(
        runtime,
        LlmRuntimeRequest(
            operation_name="graph_mapper_conversation_planning_turn",
            expected_output_name="graph_mapper_planning_turn",
            messages=(
                {"role": "system", "content": _planning_turn_system_prompt()},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "user_message": user_message,
                            "recent_messages": recent_messages,
                            "current_plan": {
                                "goal": plan.goal,
                                "raw_goal": plan.raw_goal,
                                "entry_url": plan.entry_url,
                                "source_namespace": plan.source_namespace,
                                "research_mode": plan.research_mode,
                                "follow_up_context": dict(plan.follow_up_context),
                            },
                        },
                        ensure_ascii=True,
                    ),
                },
            ),
            metadata={
                "prompt_version": "planning_turn_v2",
                "structured_output_name": "graph_mapper_planning_turn",
            },
        ),
    )

    payload = _extract_llm_json_payload(response)
    turn_kind = str(payload.get("turn_kind") or "").strip().lower()
    if turn_kind not in {"conversation", "plan_update", "launch"}:
        turn_kind = "conversation"

    assistant_reply = str(payload.get("assistant_reply") or "").strip()
    structured_request = str(payload.get("structured_request") or "").strip()
    has_research_goal = bool(payload.get("has_research_goal", turn_kind != "conversation"))

    plan_patch = payload.get("plan_patch")
    if not isinstance(plan_patch, dict):
        plan_patch = {}

    return {
        "turn_kind": turn_kind,
        "assistant_reply": assistant_reply,
        "structured_request": structured_request,
        "has_research_goal": has_research_goal,
        "plan_patch": plan_patch,
        "backend": "llm",
    }


_PLANNING_TURN_SYSTEM_PROMPT_TEMPLATE = (
    "You are the conversational orchestrator and expert curator for a research agent.\n"
    "Current system date: {current_date}.\n"
    "Your mission is to transform the user request into a clear and structured research strategy.\n"
    "\n"
    "CURATION RULES:\n"
    "1. Extract and format a 'structured_request' with this scheme:\n"
    "   GOAL: <summary of the goal>\n"
    "   ENTITIES: <companies, people, or key topics>\n"
    "   TEMPORALITY: <detected years or periods>\n"
    "   REQUIREMENTS: <what specifically to look for>\n"
    "\n"
    "RESPONSE STYLE (assistant_reply):\n"
    "- Be professional and briefly confirm what you are going to investigate.\n"
    "\n"
    "Responde ONLY valid JSON with this format:\n"
    '{{"turn_kind":"conversation|plan_update|launch","has_research_goal":true,"assistant_reply":"...","structured_request":"GOAL: ...\\nENTITIES: ...","plan_patch":{{"launch_ready":false}}}}'
)


def _planning_turn_system_prompt() -> str:
    return _PLANNING_TURN_SYSTEM_PROMPT_TEMPLATE.replace("{current_date}", _current_date_context())


# ── Message Utilities ────────────────────────────────────────────────────────

def _recent_messages_payload(
    messages: list[PlanningMessage],
    *,
    limit: int = 8,
) -> list[dict[str, str]]:
    return [
        {"role": str(message.role), "text": str(message.text)}
        for message in messages[-limit:]
        if str(message.text).strip()
    ]


def _build_goal_context(
    messages: list[PlanningMessage],
    plan: ResearchPlan,
    current_user_message: str,
) -> str:
    prior_user_goals = [
        str(message.text).strip()
        for message in messages
        if message.role == "user" and str(message.text).strip()
    ]
    merged_user_context = prior_user_goals + [current_user_message]

    lines: list[str] = []
    if plan.raw_goal:
        lines.append(f"current_goal: {plan.raw_goal}")
    if plan.goal:
        lines.append(f"operational_goal: {plan.goal}")
    if plan.entry_url:
        lines.append(f"entry_url: {plan.entry_url}")
    if plan.source_namespace:
        lines.append(f"source_namespace: {plan.source_namespace}")
    if plan.research_mode:
        lines.append(f"research_mode: {plan.research_mode}")
    if plan.follow_up_context:
        lines.append("follow_up_context:")
        lines.append(json.dumps(plan.follow_up_context, ensure_ascii=True))
    lines.append(f"current_date: {_current_date_context()}")
    lines.append("conversation_user_context:")
    for item in merged_user_context[-6:]:
        lines.append(f"- {item}")
    return "\n".join(lines).strip()


# ── Runtime Invocation ───────────────────────────────────────────────────────

def _invoke_runtime(runtime: object, llm_request: LlmRuntimeRequest) -> Any:
    if isinstance(runtime, _LlmRuntime):
        return runtime.invoke(llm_request)

    for method_name in ("execute", "run", "complete", "generate", "call"):
        method = getattr(runtime, method_name, None)
        if callable(method):
            logger.warning(
                "Runtime %s does not implement _LlmRuntime.invoke; using legacy method %r.",
                type(runtime).__name__,
                method_name,
            )
            return method(llm_request)

    raise AttributeError(
        f"The runtime {type(runtime).__name__} does not expose any known method "
        "to execute LlmRuntimeRequest. Please implement the `invoke` method."
    )


# ── JSON Payload Extraction ──────────────────────────────────────────────────

def _extract_llm_json_payload(llm_response: Any) -> dict[str, object]:
    response_payload = getattr(getattr(llm_response, "interaction", None), "response", None)
    if not isinstance(response_payload, dict):
        raise TypeError("LlmRuntimeResponse.interaction.response must be dict[str, object]")

    for key in (
        "parsed_response",
        "output",
        "parsed_output",
        "structured_output",
        "json_output",
        "content",
        "text",
        "response_text",
        "completion",
    ):
        payload = _coerce_to_dict(response_payload.get(key))
        if payload is not None:
            return payload

    message = response_payload.get("message")
    if isinstance(message, dict):
        payload = _coerce_to_dict(message.get("content"))
        if payload is not None:
            return payload

    raw_response = getattr(llm_response, "raw_response", None)
    if isinstance(raw_response, dict):
        for key in ("output", "parsed_response", "content", "text"):
            payload = _coerce_to_dict(raw_response.get(key))
            if payload is not None:
                return payload

    raise TypeError("Could not extract JSON payload from conversational turn")


def _coerce_to_dict(value: Any) -> dict[str, object] | None:
    if isinstance(value, dict):
        return dict(value)

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        return dict(parsed) if isinstance(parsed, dict) else None

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict):
            return dict(dumped)

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        dumped = to_dict()
        if isinstance(dumped, dict):
            return dict(dumped)

    return None


# ── Cloning and state utilities ──────────────────────────────────────────────

def _clone_state(state: ConversationPlanState) -> ConversationPlanState:
    cloned_plan = ResearchPlan(
        profile_name=state.plan.profile_name,
        raw_goal=state.plan.raw_goal,
        goal=state.plan.goal,
        goal_trace=dict(state.plan.goal_trace),
        goal_intent=state.plan.goal_intent,
        proposal_id=state.plan.proposal_id,
        proposal_version=state.plan.proposal_version,
        proposal_status=state.plan.proposal_status,
        proposal_summary=state.plan.proposal_summary,
        goal_conditions=list(state.plan.goal_conditions),
        launch_ready=state.plan.launch_ready,
        entry_url=state.plan.entry_url,
        source_namespace=state.plan.source_namespace,
        research_mode=state.plan.research_mode,
        principal_model=state.plan.principal_model,
        ocr_model=state.plan.ocr_model,
        ocr_mode=state.plan.ocr_mode,
        validation_model=state.plan.validation_model,
        allow_artifact_download=state.plan.allow_artifact_download,
        artifact_persistence_mode=state.plan.artifact_persistence_mode,
        decision_mode=state.plan.decision_mode,
        planner_backend=state.plan.planner_backend,
        planning_notes=state.plan.planning_notes,
        follow_up_context=dict(state.plan.follow_up_context),
    )
    _sync_plan_consistency(cloned_plan)

    return ConversationPlanState(
        session_id=state.session_id,
        plan=cloned_plan,
        messages=[
            PlanningMessage(
                role=item.role,
                text=item.text,
                with_launch=item.with_launch,
            )
            for item in state.messages
        ],
        suggested_mode=_suggested_mode(cloned_plan),
    )


def _suggested_mode(plan: ResearchPlan) -> str:
    return "planner" if plan.has_structured_plan() else "conversation"


def _goal_trace_payload(trace: object) -> dict[str, object]:
    if trace is None:
        return {}

    intent = getattr(trace, "intent", None)
    proposals = tuple(getattr(trace, "proposals", ()) or ())

    return {
        "intent": {
            "intent_id": getattr(intent, "intent_id", None),
            "source_goal_context": getattr(intent, "source_goal_context", None),
            "normalized_goal": getattr(intent, "normalized_goal", None),
        } if intent is not None else None,
        "proposals": [
            {
                "proposal_id": getattr(proposal, "proposal_id", None),
                "version": getattr(proposal, "version", None),
                "summary": getattr(proposal, "summary", None),
                "status": getattr(proposal, "status", None),
                "planning_notes": getattr(proposal, "planning_notes", None),
                "parent_proposal_id": getattr(proposal, "parent_proposal_id", None),
                "conditions": [
                    {
                        "condition_id": getattr(condition, "condition_id", None),
                        "label": getattr(condition, "label", None),
                        "kind": getattr(condition, "kind", None),
                        "target_kind": getattr(condition, "target_kind", None),
                        "requiredness": getattr(condition, "requiredness", None),
                        "filters": dict(getattr(condition, "filters", {}) or {}),
                        "min_count": getattr(condition, "min_count", None),
                        "status": getattr(condition, "status", None),
                        "matched_finding_ids": list(
                            getattr(condition, "matched_finding_ids", ()) or ()
                        ),
                    }
                    for condition in tuple(getattr(proposal, "conditions", ()) or ())
                ],
            }
            for proposal in proposals
        ],
        "active_proposal_id": getattr(trace, "active_proposal_id", None),
        "validation_log": list(getattr(trace, "validation_log", ()) or ()),
    }