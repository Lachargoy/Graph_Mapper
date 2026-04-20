from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from graph_mapper_agent.application.services.goals.planner import (
    GoalPlannerRequest,
    GoalPlannerUseCase,
)
from graph_mapper_agent.bootstrap.execution_config import (
    GuidedGraphMapperConfig,
)

from graph_mapper_agent.bootstrap.dto import RunGraphMapperInput
from graph_mapper_agent.bootstrap.runner import run_graph_mapper
from .config import GraphMapperConfig

def select_configuration() -> Path | None:
    base_path = Path(__file__).resolve().parent / "configs"

    if not base_path.exists():
        print("Error: configurations folder not found.")
        print(f"Expected at: {base_path}")
        return None

    files = sorted([f for f in base_path.iterdir() if f.suffix == ".json"])

    if not files:
        print(f"No JSON files found in {base_path}")
        return None

    print("\n=== SELECT A GRAPH_MAPPER CONFIGURATION ===")
    print(f"Directory: {base_path}")
    for i, file in enumerate(files, 1):
        print(f"{i}. {file.name}")
    print("0. Exit")

    try:
        selection = int(input("\nEnter the file number: ").strip())
    except ValueError:
        print("You must enter a valid number.")
        return None

    if selection == 0:
        return None

    if 1 <= selection <= len(files):
        return files[selection - 1]

    print("Invalid selection.")
    return None


def pretty_json(data: object) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def main() -> None:
    path = select_configuration()

    if path is None:
        print("Execution cancelled.")
        return

    print(f"\nLoading configuration: {path.name}")
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    request = GraphMapperConfig.from_json_dict(payload.get("request") or {})
    execution_payload = dict(payload.get("execution") or {})

    llm_runtime_payload = payload.get("llm_runtime")
    navigation_perception_llm_runtime_payload = payload.get(
        "navigation_perception_llm_runtime"
    )
    goal_validation_llm_runtime_payload = payload.get(
        "goal_validation_llm_runtime"
    ) or payload.get("document_validation_llm_runtime")
    evidence_extraction_visual_llm_runtime_payload = payload.get(
        "evidence_extraction_visual_llm_runtime"
    )
    evidence_extraction_ocr_llm_runtime_payload = payload.get(
        "evidence_extraction_ocr_llm_runtime"
    )

    if isinstance(llm_runtime_payload, dict):
        execution_payload["llm_runtime"] = dict(llm_runtime_payload)
    if isinstance(navigation_perception_llm_runtime_payload, dict):
        execution_payload["navigation_perception_llm_runtime"] = dict(
            navigation_perception_llm_runtime_payload
        )
    if isinstance(goal_validation_llm_runtime_payload, dict):
        execution_payload["goal_validation_llm_runtime"] = dict(
            goal_validation_llm_runtime_payload
        )
    if isinstance(evidence_extraction_visual_llm_runtime_payload, dict):
        execution_payload["evidence_extraction_visual_llm_runtime"] = dict(
            evidence_extraction_visual_llm_runtime_payload
        )
    if isinstance(evidence_extraction_ocr_llm_runtime_payload, dict):
        execution_payload["evidence_extraction_ocr_llm_runtime"] = dict(
            evidence_extraction_ocr_llm_runtime_payload
        )

    execution = GuidedGraphMapperConfig.from_json_dict(execution_payload)
    mock_observations = payload.get("mock_observations")

    pre_run_goal_trace, planning_notes, cancelled = _interactive_goal_confirmation_loop(
        request=request,
        execution=execution,
    )
    if cancelled:
        print("Execution cancelled before main run.")
        return

    if pre_run_goal_trace is not None:
        execution_metadata = dict(execution.execution_metadata or {})
        execution_metadata["precomputed_goal_trace"] = pre_run_goal_trace
        if planning_notes:
            execution_metadata["goal_planning_notes"] = planning_notes
        execution = replace(execution, execution_metadata=execution_metadata)

    print("\nStarting GraphMapper...")
    print("-" * 60)

    try:
        result = run_graph_mapper(
            RunGraphMapperInput(
                request=request,
                execution=execution,
                mock_observations=(
                    mock_observations if isinstance(mock_observations, dict) else None
                ),
            )
        )

        print("\nExecution finished")
        print("-" * 60)

        print("\nFinal status:")
        print(result.final_status)

        print("\nFinal state:")
        print(pretty_json(result.final_state))

    except Exception as e:
        print(f"\nCritical error: {e}")
        raise


def _interactive_goal_confirmation_loop(
    *,
    request: GraphMapperConfig,
    execution: GuidedGraphMapperConfig,
):
    if execution.llm_runtime is None:
        print(
            "No llm_runtime configured for goal planning before run. "
            "Continuing without prior goal confirmation."
        )
        return None, None, False

    planner = GoalPlannerUseCase(llm_runtime_config=execution.llm_runtime)
    result = planner.plan(GoalPlannerRequest(goal_context=request.goal))

    if result.goal_trace is None:
        print("Planner did not return goal_trace. Continuing with direct goal.")
        return None, None, False

    current_trace = result.goal_trace
    planning_notes = result.planning_notes

    while True:
        _print_goal_trace(current_trace, planning_notes)
        action = input("\n[a]ccept / [r]evise / [c]ancel: ").strip().lower()

        if action in {"a", "accept"}:
            proposal = current_trace.active_proposal() or (
                current_trace.proposals[-1] if current_trace.proposals else None
            )
            if proposal is None:
                print("No proposal to activate.")
                continue

            accepted_trace = GoalPlannerUseCase.accept_proposal(
                current_trace,
                proposal_id=proposal.proposal_id,
                actor="user",
                note="accepted_from_terminal_runner",
            )
            _print_goal_trace(accepted_trace, planning_notes)
            return accepted_trace, planning_notes, False

        if action in {"r", "revise"}:
            feedback = input(
                "\nEnter feedback to revise the proposal: "
            ).strip()
            if not feedback:
                print("Empty feedback. No new revision generated.")
                continue

            revised = planner.replan(current_trace, feedback=feedback, actor="user")
            if revised.goal_trace is None:
                print("Planner could not generate a new revision.")
                continue

            current_trace = revised.goal_trace
            planning_notes = revised.planning_notes or planning_notes
            continue

        if action in {"c", "cancel"}:
            return None, None, True

        print("Invalid option.")


def _print_goal_trace(trace, planning_notes: str | None) -> None:
    print("\n=== PROPOSED GOAL TRACE ===")
    print(f"Intent: {trace.intent.normalized_goal}")
    if planning_notes:
        print(f"Planning notes: {planning_notes}")

    proposal = trace.active_proposal() or (trace.proposals[-1] if trace.proposals else None)
    if proposal is None:
        print("No proposal available.")
        return

    print(f"Proposal id: {proposal.proposal_id}")
    print(f"Version: {proposal.version}")
    print(f"Status: {proposal.status}")
    print(f"Summary: {proposal.summary}")
    print("Conditions:")

    if not proposal.conditions:
        print("- none")
        return

    for condition in proposal.conditions:
        year = condition.filters.get("year")
        print(
            f"- {condition.condition_id} | {condition.label} | {condition.kind} | "
            f"{condition.target_kind} | requiredness={condition.requiredness} | "
            f"year={year} | min_count={condition.min_count}"
        )


if __name__ == "__main__":
    main()
