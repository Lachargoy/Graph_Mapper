from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter, strftime
from typing import Callable, Literal, Mapping, MutableMapping


StateDict = MutableMapping[str, object]
StepFn = Callable[[StateDict], Mapping[str, object] | None]
RouterFn = Callable[[StateDict], str]
TransitionHook = Callable[["TransitionEvent"], None]
StepErrorHook = Callable[["StepErrorEvent"], None]


class StateMachineError(RuntimeError):
    """Base error for the navigation state machine."""


class InvalidGraphError(StateMachineError):
    """Raised when the transition graph is structurally invalid."""


class UnknownStateError(StateMachineError):
    """Raised when the engine attempts to execute or route to an unknown state."""


class MissingRouteError(StateMachineError):
    """Raised when a transition cannot determine the next state."""


class MaxStepsExceededError(StateMachineError):
    """Raised when execution exceeds the configured maximum number of steps."""


@dataclass(frozen=True)
class TransitionDefinition:
    step: StepFn
    router: RouterFn | None = None
    next_step: str | None = None


@dataclass(frozen=True)
class TransitionEvent:
    step_index: int
    from_state: str
    to_state: str | None
    duration_ms: float
    route_source: Literal["router", "next_step", "route_hint", "terminal"]
    state_snapshot: dict[str, object] | None = None


@dataclass(frozen=True)
class StepErrorEvent:
    step_index: int
    state_name: str
    error: Exception
    duration_ms: float
    state_snapshot: dict[str, object] | None = None


class StateMachineEngine:
    def __init__(
        self,
        *,
        transitions: dict[str, TransitionDefinition],
        terminal_states: set[str] | None = None,
        max_steps: int = 500,
        on_transition: TransitionHook | None = None,
        on_step_error: StepErrorHook | None = None,
        copy_mode: Literal["none", "shallow", "deep"] = "shallow",
        snapshot_mode: Literal["none", "shallow"] = "none",
        debug: bool = True,
    ) -> None:
        self._transitions = dict(transitions)
        self._terminal_states = set(terminal_states or {"success", "fail"})
        self._max_steps = max_steps if max_steps > 0 else 500
        self._on_transition = on_transition
        self._on_step_error = on_step_error
        self._copy_mode = copy_mode
        self._snapshot_mode = snapshot_mode
        self._debug = debug
        self._validate_graph()

    def execute(
        self,
        initial_state: Mapping[str, object],
        *,
        start_at: str,
    ) -> dict[str, object]:
        state = self._prepare_initial_state(initial_state)
        current = start_at
        step_index = 0

        self._debug_log(
            f"ENGINE START start_at={start_at!r} max_steps={self._max_steps} "
            f"terminal_states={sorted(self._terminal_states)!r}"
        )
        self._debug_log(f"INITIAL SUMMARY {self._summarize_state(state)}")

        while True:
            if step_index >= self._max_steps:
                self._debug_log(
                    f"MAX STEPS EXCEEDED step_index={step_index} max_steps={self._max_steps}"
                )
                raise MaxStepsExceededError(
                    f"State machine exceeded max_steps={self._max_steps}"
                )

            if current not in self._transitions:
                self._debug_log(f"UNKNOWN STATE current={current!r}")
                raise UnknownStateError(f"Unknown state machine step: {current}")

            transition = self._transitions[current]

            self._debug_log(
                f"STEP START idx={step_index} state={current!r} "
                f"summary={self._summarize_state(state)}"
            )

            started = perf_counter()
            try:
                updates = transition.step(state)
                if updates:
                    updates_dict = dict(updates)
                    state.update(updates_dict)
                    self._debug_log(
                        f"STEP UPDATES idx={step_index} state={current!r} "
                        f"keys={sorted(updates_dict.keys())!r}"
                    )
                else:
                    self._debug_log(
                        f"STEP UPDATES idx={step_index} state={current!r} keys=[]"
                    )
            except Exception as exc:
                duration_ms = (perf_counter() - started) * 1000.0
                self._debug_log(
                    f"STEP ERROR idx={step_index} state={current!r} "
                    f"duration_ms={duration_ms:.2f} error={exc!r} "
                    f"summary={self._summarize_state(state)}"
                )
                self._emit_step_error(
                    StepErrorEvent(
                        step_index=step_index,
                        state_name=current,
                        error=exc,
                        duration_ms=duration_ms,
                        state_snapshot=self._snapshot_state(state),
                    )
                )
                raise

            duration_ms = (perf_counter() - started) * 1000.0

            if current in self._terminal_states:
                self._debug_log(
                    f"STEP TERMINAL idx={step_index} state={current!r} "
                    f"duration_ms={duration_ms:.2f} "
                    f"final_status={state.get('final_status')!r} "
                    f"summary={self._summarize_state(state)}"
                )
                self._emit_transition(
                    TransitionEvent(
                        step_index=step_index,
                        from_state=current,
                        to_state=None,
                        duration_ms=duration_ms,
                        route_source="terminal",
                        state_snapshot=self._snapshot_state(state),
                    )
                )
                return dict(state)

            next_state, route_source = self._resolve_next_state(
                current=current,
                transition=transition,
                state=state,
            )

            if next_state not in self._transitions:
                self._debug_log(
                    f"ROUTED TO UNKNOWN idx={step_index} from_state={current!r} "
                    f"to_state={next_state!r} route_source={route_source!r}"
                )
                raise UnknownStateError(
                    f"Transition from '{current}' routed to unknown state '{next_state}'"
                )

            self._debug_log(
                f"STEP END idx={step_index} from_state={current!r} to_state={next_state!r} "
                f"route_source={route_source!r} "
                f"route_hint={state.get('route_hint')!r} "
                f"duration_ms={duration_ms:.2f} "
                f"summary={self._summarize_state(state)}"
            )

            self._emit_transition(
                TransitionEvent(
                    step_index=step_index,
                    from_state=current,
                    to_state=next_state,
                    duration_ms=duration_ms,
                    route_source=route_source,
                    state_snapshot=self._snapshot_state(state),
                )
            )

            current = next_state
            step_index += 1

    def _resolve_next_state(
        self,
        *,
        current: str,
        transition: TransitionDefinition,
        state: StateDict,
    ) -> tuple[str, Literal["router", "next_step", "route_hint"]]:
        if transition.router is not None:
            routed = str(transition.router(state)).strip()
            if routed:
                return routed, "router"

        if transition.next_step is not None:
            routed = str(transition.next_step).strip()
            if routed:
                return routed, "next_step"

        route_hint = str(state.get("route_hint") or "").strip()
        if route_hint:
            return route_hint, "route_hint"

        self._debug_log(
            f"MISSING ROUTE state={current!r} route_hint={state.get('route_hint')!r} "
            f"summary={self._summarize_state(state)}"
        )
        raise MissingRouteError(
            f"State '{current}' has no router result, no next_step, and no route_hint in state"
        )

    def _prepare_initial_state(
        self,
        initial_state: Mapping[str, object],
    ) -> dict[str, object]:
        if self._copy_mode == "none":
            if isinstance(initial_state, dict):
                return initial_state
            return dict(initial_state)

        if self._copy_mode == "shallow":
            return dict(initial_state)

        if self._copy_mode == "deep":
            from copy import deepcopy

            return deepcopy(dict(initial_state))

        raise ValueError(f"Unsupported copy_mode: {self._copy_mode}")

    def _snapshot_state(self, state: StateDict) -> dict[str, object] | None:
        if self._snapshot_mode == "none":
            return None
        if self._snapshot_mode == "shallow":
            return dict(state)
        raise ValueError(f"Unsupported snapshot_mode: {self._snapshot_mode}")

    def _emit_transition(self, event: TransitionEvent) -> None:
        if self._on_transition is None:
            return
        try:
            self._on_transition(event)
        except Exception:
            return

    def _emit_step_error(self, event: StepErrorEvent) -> None:
        if self._on_step_error is None:
            return
        try:
            self._on_step_error(event)
        except Exception:
            return

    def _validate_graph(self) -> None:
        if not self._transitions:
            raise InvalidGraphError("State machine requires at least one transition")

        missing_terminals = [
            state_name
            for state_name in self._terminal_states
            if state_name not in self._transitions
        ]
        if missing_terminals:
            raise InvalidGraphError(
                f"Terminal states are not defined in transitions: {missing_terminals}"
            )

        for state_name, transition in self._transitions.items():
            if transition.next_step is not None:
                next_name = str(transition.next_step).strip()
                if not next_name:
                    raise InvalidGraphError(
                        f"State '{state_name}' has an empty next_step"
                    )
                if next_name not in self._transitions:
                    raise InvalidGraphError(
                        f"State '{state_name}' points to unknown next_step '{next_name}'"
                    )

    def _debug_log(self, message: str) -> None:
        if not self._debug:
            return
        print(f"[{strftime('%H:%M:%S')}] [engine] {message}", flush=True)

    def _summarize_state(self, state: StateDict) -> str:
        runtime = state.get("runtime")

        summary = {
            "route_hint": state.get("route_hint"),
            "final_status": state.get("final_status"),
        }

        if runtime is not None:
            summary["runtime_type"] = type(runtime).__name__
            active_scope_id = getattr(runtime, "active_scope_id", None)
            current_node_id = getattr(runtime, "current_node_id", None)
            frontier = getattr(runtime, "frontier", None)
            step_count = getattr(runtime, "step_count", None)
            last_decision = getattr(runtime, "last_decision", None)

            summary["active_scope_id"] = active_scope_id
            summary["current_node_id"] = current_node_id
            summary["frontier_count"] = len(frontier) if isinstance(frontier, dict) else None
            summary["runtime_step_count"] = step_count

            if isinstance(last_decision, dict):
                summary["last_action"] = last_decision.get("action")
                summary["last_edge_id"] = last_decision.get("edge_id")

        return str(summary)

