from __future__ import annotations
#graph_mapper_agent/application/services/goals/planner.py
import json
import re
from datetime import datetime
from dataclasses import dataclass
from typing import Any

from graph_mapper_agent.adapters.llm.composition.runtime_factory import (
    build_llm_runtime,
)
from graph_mapper_agent.platform.llm.config import (
    LlmRuntimeConfig,
)
from graph_mapper_agent.platform.llm.resolve_runtime_plan import (
    resolve_runtime_plan,
)
from graph_mapper_agent.application.services.goals.models import (
    DynamicGoalCondition,
    GoalTrace,
)
from graph_mapper_agent.application.services.goals.planner_models import (
    GoalPlanningOutput,
)
from graph_mapper_agent.application.services.goals.planner_trace_ops import (
    accept_proposal,
    build_goal_trace,
    build_replan_user_content,
    coerce_condition,
    revise_proposal,
    sanitize_goal_context,
    sanitize_goal_text,
)
from graph_mapper_agent.domain.ports.llm_runtime_port import (
    LlmRuntimeRequest,
)


@dataclass(frozen=True)
class GoalPlannerRequest:
    goal_context: str


def _current_date_context() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


@dataclass(frozen=True)
class GoalPlannerResult:
    planning_notes: str | None = None
    goal_trace: GoalTrace | None = None


@dataclass(frozen=True)
class GoalPlannerUseCase:
    llm_runtime_config: LlmRuntimeConfig

    def plan(self, request: GoalPlannerRequest) -> GoalPlannerResult:
        goal_context = sanitize_goal_context(request.goal_context)
        if not goal_context:
            return GoalPlannerResult(planning_notes=None, goal_trace=None)

        parsed = self._request_planning_output(user_content=goal_context)
        goal_trace = build_goal_trace(parsed, goal_context=goal_context)

        return GoalPlannerResult(
            planning_notes=sanitize_goal_text(parsed.planning_notes, max_len=400),
            goal_trace=goal_trace,
        )

    def replan(
        self,
        trace: GoalTrace,
        *,
        feedback: str,
        actor: str = "user",
    ) -> GoalPlannerResult:
        goal_context = sanitize_goal_context(trace.intent.source_goal_context)
        feedback_text = sanitize_goal_text(feedback, max_len=800)
        if not goal_context or not feedback_text:
            return GoalPlannerResult(planning_notes=None, goal_trace=trace)

        parsed = self._request_planning_output(
            user_content=build_replan_user_content(trace, feedback_text),
        )
        base_proposal = trace.active_proposal() or (trace.proposals[-1] if trace.proposals else None)
        if base_proposal is None:
            goal_trace = build_goal_trace(parsed, goal_context=goal_context)
            return GoalPlannerResult(
                planning_notes=sanitize_goal_text(parsed.planning_notes, max_len=400),
                goal_trace=goal_trace,
            )

        updated_trace = self.revise_proposal(
            trace,
            proposal_id=base_proposal.proposal_id,
            actor="planner",
            note=f"feedback_from_{actor}: {feedback_text}",
            summary=sanitize_goal_text(parsed.proposal_summary, max_len=240)
            or base_proposal.summary,
            conditions=tuple(coerce_condition(condition) for condition in parsed.conditions),
        )
        return GoalPlannerResult(
            planning_notes=sanitize_goal_text(parsed.planning_notes, max_len=400),
            goal_trace=updated_trace,
        )

    def _request_planning_output(self, *, user_content: str) -> GoalPlanningOutput:
        plan = resolve_runtime_plan(
            self.llm_runtime_config,
            expected_output_name="graph_mapper_goal_planning",
            tools_requested=False,
        )
        factory_result = build_llm_runtime(plan)
        runtime = factory_result.runtime

        llm_request = LlmRuntimeRequest(
            operation_name="graph_mapper_goal_planning",
            messages=[
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": user_content},
            ],
            expected_output_name="graph_mapper_goal_planning",
            metadata={
                "prompt_version": "goal_planner_v3",
                "structured_output_name": "graph_mapper_goal_planning",
            },
        )

        llm_response = _invoke_runtime(runtime, llm_request)
        payload = _extract_goal_planning_payload(llm_response)
        return GoalPlanningOutput.model_validate(payload)

    @staticmethod
    def accept_proposal(
        trace: GoalTrace,
        *,
        proposal_id: str,
        actor: str,
        note: str,
    ) -> GoalTrace:
        return accept_proposal(
            trace,
            proposal_id=proposal_id,
            actor=actor,
            note=note,
        )

    @staticmethod
    def revise_proposal(
        trace: GoalTrace,
        *,
        proposal_id: str,
        actor: str,
        note: str,
        summary: str,
        conditions: tuple[DynamicGoalCondition, ...],
    ) -> GoalTrace:
        return revise_proposal(
            trace,
            proposal_id=proposal_id,
            actor=actor,
            note=note,
            summary=summary,
            conditions=conditions,
        )


def _system_prompt() -> str:
    return (
        "You are a goal planner for the graph_mapper track.\n"
        f"Current system date: {_current_date_context()}.\n"
        "Your task is to convert a free user goal into a base intent and an operational proposal with structured active conditions.\n"
        "\n"
        "MANDATORY RULES:\n"
        "- Each condition must be verifiable with navigable, textual, or documentary evidence.\n"
        "- Prefer concrete and observable conditions, for example: presence of a deliverable, proof of date, evidence of temporality, or evidence of a specific document family.\n"
        "- DO NOT convert the goal into internal agent tasks.\n"
        "- DO NOT output free text as the only form of execution; always produce structured conditions.\n"
        "- If the goal mentions 'last', 'most recent', 'current', or equivalents, express a verifiable temporality condition.\n"
        "- Use short and stable condition_ids like c1, c2, c3.\n"
        "- Use target_kind as the general class of the objective or expected deliverable.\n"
        "- Use filters to express structured restrictions when necessary.\n"
        "- filters can include: year, date, document_family, preferred_carrier, accepted_carriers, strict_carrier_required, locale, institution, session_type, or any relevant verifiable restriction.\n"
        "- document_family describes the document family or class of the sought deliverable, without imposing a rigid carrier by itself.\n"
        "- preferred_carrier expresses preference, not obligation.\n"
        "- accepted_carriers expresses allowed carriers when you want to restrict or open the criteria.\n"
        "- strict_carrier_required=true only when the format is a hard requirement of the goal.\n"
        "- If the goal can be satisfied with terminal HTML, inline text, or final artifact, do not force strict_carrier_required=true.\n"
        "- If the goal strictly requires a specific carrier, express that restriction in accepted_carriers and strict_carrier_required.\n"
        "- Avoid redundant or ambiguous conditions; each condition must add clear operational value.\n"
        "- If the user asks for an explicit quantity of documents, news, pages, statistics, or sources, preserve that quantity in min_count or in verifiable filters; DO NOT lose it in the summary.\n"
        "- If the user asks for research depth, multiple visited pages, many sources, or wide coverage, model that expectation as verifiable multiplicity, not as a single generic condition.\n"
        "- If the user asks for different types of evidence, separate them into distinct conditions; for example: news, statistics, PDFs, reports, tables, or official pages.\n"
        "- Do not collapse a rich goal into a single document_presence condition if the user requested several types of deliverables or several pieces of evidence.\n"
        "\n"
        "MODELING CRITERIA:\n"
        "- Separate document family from carrier or format.\n"
        "- Do not confuse the type of deliverable sought with the medium in which it appears.\n"
        "- If the same goal can be satisfied by more than one carrier, model it in accepted_carriers.\n"
        "- If a condition requires count or multiplicity, use min_count.\n"
        "- If a condition only expresses a preference and not an obligation, do not convert it into a hard restriction.\n"
        "- If the user asks for example '4 PDFs', then the relevant condition must have min_count=4.\n"
        "- If the user asks for example '5 statistics', create a specific condition for statistical evidence with min_count=5.\n"
        "- If the user asks for example '4 pages visited' or 'multiple sources', model a separate condition for verifiable document coverage or multiplicity instead of ignoring it.\n"
        "- If the user asks for recent news, use target_kind/news_article or equivalent document_family; if they ask for weather reports, use a suitable document family; if they ask for statistics or tables, model that explicitly.\n"
        "\n"
        "Respond ONLY with valid JSON.\n"
        "Orientative format:\n"
        "{"
        '"goal_intent":"...",'
        '"proposal_summary":"...",'
        '"conditions":['
        "{"
        '"condition_id":"c1",'
        '"label":"...",'
        '"kind":"document_presence",'
        '"target_kind":"document_family_generic",'
        '"requiredness":"mandatory",'
        '"filters":{'
        '"year":2026,'
        '"document_family":"document_family_generic",'
        '"preferred_carrier":"pdf",'
        '"accepted_carriers":["pdf","html_inline","text_inline"],'
        '"strict_carrier_required":false'
        "},"
        '"min_count":1'
        "}"
        "],"
        '"planning_notes":"..."'
        "}"
        "\n"
        "Expected modeling examples:\n"
        '- Goal: "I want 4 PDFs about climate change in Mexico from 2026"\n'
        '  -> at least one condition with documentary target_kind, filters.year=2026 and min_count=4.\n'
        '- Goal: "look for 5 statistics and 3 recent news about drought in Chiapas"\n'
        '  -> create at least two conditions: one for statistics with min_count=5 and another for news with min_count=3.\n'
        '- Goal: "I want deep research, visit at least 4 pages about DID regulation in Chiapas"\n'
        '  -> do not reduce it to a single document_presence; preserve the requested coverage with min_count=4 or equivalent verifiable filters.\n'
    )


def _invoke_runtime(runtime: object, llm_request: LlmRuntimeRequest):
    for method_name in ("invoke", "execute", "run", "complete", "generate", "call"):
        method = getattr(runtime, method_name, None)
        if callable(method):
            print(f"[goal_planner] using runtime.{method_name}(...)", flush=True)
            return method(llm_request)

    raise AttributeError(
        f"The runtime {type(runtime).__name__} does not expose a known method "
        "to execute LlmRuntimeRequest"
    )


def _extract_goal_planning_payload(llm_response: Any) -> dict[str, object]:
    interaction = getattr(llm_response, "interaction", None)
    if interaction is None:
        raise TypeError("LlmRuntimeResponse does not contain interaction")

    response_payload = getattr(interaction, "response", None)
    if not isinstance(response_payload, dict):
        raise TypeError("LlmRuntimeResponse.interaction.response must be dict[str, object]")

    candidate_keys = (
        "parsed_response",
        "output",
        "parsed_output",
        "structured_output",
        "json_output",
        "content",
        "text",
        "response_text",
        "completion",
    )

    for key in candidate_keys:
        if key in response_payload:
            parsed = _coerce_to_dict(response_payload[key])
            if parsed is not None:
                return parsed

    if (
        "goals" in response_payload
        or "conditions" in response_payload
        or "goal_intent" in response_payload
    ):
        return dict(response_payload)

    message = response_payload.get("message")
    if isinstance(message, dict):
        parsed = _coerce_to_dict(message.get("content"))
        if parsed is not None:
            return parsed

        reasoning_details = message.get("reasoning_details")
        parsed = _extract_from_reasoning_payload(reasoning_details)
        if parsed is not None:
            return parsed

    raw_response = getattr(llm_response, "raw_response", None)
    parsed = _extract_from_raw_response(raw_response)
    if parsed is not None:
        return parsed

    raise TypeError("Could not extract payload from goal planning")


def _extract_from_raw_response(raw_response: Any) -> dict[str, object] | None:
    if not isinstance(raw_response, dict):
        return None

    for key in ("output", "parsed_response"):
        parsed = _coerce_to_dict(raw_response.get(key))
        if parsed is not None:
            return parsed

    agent_response = raw_response.get("agent_response")
    parsed = _extract_from_reasoning_payload(agent_response)
    if parsed is not None:
        return parsed

    all_messages = raw_response.get("all_messages")
    parsed = _extract_from_reasoning_payload(all_messages)
    if parsed is not None:
        return parsed

    new_messages = raw_response.get("new_messages")
    parsed = _extract_from_reasoning_payload(new_messages)
    if parsed is not None:
        return parsed

    return None


def _extract_from_reasoning_payload(value: Any) -> dict[str, object] | None:
    if value is None:
        return None

    if isinstance(value, dict):
        for key in ("reasoning_content", "content", "text"):
            parsed = _coerce_to_dict(value.get(key))
            if parsed is not None:
                return parsed

        for key in ("reasoning_content", "content", "text"):
            parsed = _parse_pseudo_tool_call(value.get(key))
            if parsed is not None:
                return parsed

        for nested in value.values():
            parsed = _extract_from_reasoning_payload(nested)
            if parsed is not None:
                return parsed
        return None

    if isinstance(value, list):
        for item in value:
            parsed = _extract_from_reasoning_payload(item)
            if parsed is not None:
                return parsed
        return None

    if isinstance(value, str):
        parsed = _coerce_to_dict(value)
        if parsed is not None:
            return parsed
        return _parse_pseudo_tool_call(value)

    return None


def _parse_pseudo_tool_call(value: Any) -> dict[str, object] | None:
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    if "<function=final_result>" not in text:
        return None

    param_pattern = re.compile(
        r"<parameter=(?P<name>[a-zA-Z0-9_]+)>\s*(?P<value>.*?)\s*</parameter>",
        re.DOTALL,
    )
    found = {
        match.group("name"): match.group("value").strip()
        for match in param_pattern.finditer(text)
    }
    if not found:
        return None

    goal_intent = found.get("goal_intent")
    proposal_summary = found.get("proposal_summary")
    planning_notes = found.get("planning_notes")
    raw_conditions = found.get("conditions")

    if not goal_intent or not proposal_summary or raw_conditions is None:
        return None

    try:
        conditions = json.loads(raw_conditions)
    except json.JSONDecodeError:
        return None

    if not isinstance(conditions, list):
        return None

    return {
        "goal_intent": goal_intent,
        "proposal_summary": proposal_summary,
        "conditions": conditions,
        "planning_notes": planning_notes or "",
    }


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
        if isinstance(parsed, dict):
            return dict(parsed)
        return None

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


__all__ = [
    "GoalPlannerRequest",
    "GoalPlannerResult",
    "GoalPlannerUseCase",
]
