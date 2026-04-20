Graph Mapper Transition Topology Manual
Purpose

This manual documents the file graph_mapper_agent/runtime/transitions.py as the transition topology definition of the graph_mapper lane.

Its purpose is to explain:

how the lane state machine is declared,
how each runtime step is connected,
where fixed sequencing ends and dynamic routing begins,
how route_hint is actually used,
how this file fits between the generic engine and the concrete lane nodes,
and how to maintain or extend the transition graph safely.
1. General overview

The graph_mapper lane is not assembled implicitly by calling methods ad hoc.
Its executable shape is declared explicitly as a transition graph. The file runtime/transitions.py is the place where that graph is defined.

This file does not:

inspect pages,
classify nodes,
decide actions,
mutate the graph,
or persist evidence.

Instead, it does something narrower and more structural:

it binds state names to callable lane step methods,
it chooses between fixed transitions and routed transitions,
it declares the lane entry point,
and it declares the terminal states.

The correct mental model is:

GraphMapperNodes
    -> provides step implementations

runtime/transitions.py
    -> maps step names to TransitionDefinition
    -> declares routing policy for the lane

StateMachineEngine
    -> executes the declared graph

This makes transitions.py the composition layer of the lane workflow, not the workflow logic itself.

2. File
Path

graph_mapper_agent/runtime/transitions.py

Main exports
route_after_execute_action(state)
route_after_advance_branch(state)
build_transitions(nodes)
TERMINAL_STATES
START_STATE
3. Role of the file
Role

This file is the formal lane transition map for graph_mapper. It defines the set of runtime states and how execution moves from one state to the next.

It is the missing piece between:

the generic execution engine (StateMachineEngine),
and the concrete lane behavior (GraphMapperNodes).

Without this file, the engine would know how to execute a state machine in general, and GraphMapperNodes would know how to implement lane steps, but the lane would still lack its concrete topology.

4. Main responsibility

The main responsibility of runtime/transitions.py is to build the transition graph of the lane.

That responsibility is divided into three parts:

1. Declare the ordered backbone of the lane

The file defines the main chain:

bootstrap
 -> inspect_node
 -> classify_node
 -> build_node_view
 -> decide_action
 -> execute_action
 -> update_graph
 -> advance_branch
 -> success / fail

This is the same operational cycle already described in the execution manual, but here it is declared as actual transition configuration, not just described conceptually.

2. Restrict dynamic routing to a small set of states

Only two states use routers:

execute_action
advance_branch

Everything else follows a fixed next_step. This is important because it keeps the lane readable: most of the graph is deterministic, and only the places that genuinely need dynamic resolution are routed.

3. Declare start and terminal states

The file sets:

START_STATE = "bootstrap"
TERMINAL_STATES = {"success", "fail"}

That means this file is also the canonical source of the lane’s entry point and formal stop states.

5. What comes in
build_transitions(nodes)

The main input is a nodes object. The file expects that object to expose callable step methods with engine-compatible signatures. The expected methods are:

bootstrap
inspect_node
classify_node
build_node_view
decide_action
execute_action
update_graph
advance_branch
success
fail

Although nodes is typed as object, the actual contract is structural: it must behave like the concrete GraphMapperNodes implementation.

Router input

Both router functions receive:

state: dict[str, object]

They read only one routing signal from that state:

route_hint

So the router layer is intentionally minimal.

6. What goes out
Main output

build_transitions(nodes) returns:

dict[str, TransitionDefinition]

Each key is a runtime state name, and each value is a TransitionDefinition that tells the engine:

which step function to execute,
whether the next state is fixed,
or whether it must be resolved by a router.
Additional outputs

The file also exports:

START_STATE
TERMINAL_STATES

These are not runtime data produced per step; they are part of the lane definition itself.

7. Dependency map
Direct dependency

The file imports TransitionDefinition from the runtime engine module. That means it consumes the engine’s transition contract rather than redefining its own.

Structural dependencies

This file also depends implicitly on:

a valid nodes object exposing all required step methods,
the engine honoring router resolution over fixed sequencing where configured,
GraphMapperNodes.execute_action(...) setting route_hint consistently when post-action routing must change,
and advance_branch(...) or its helpers returning a route outcome compatible with the router policy.
Architectural dependency graph
StateMachineEngine
    <- consumes TransitionDefinition graph

runtime/transitions.py
    <- imports TransitionDefinition
    <- expects callable step methods on nodes

GraphMapperNodes
    <- provides concrete step implementations

GraphMapperState
    <- is carried through those steps

This file does not mutate GraphMapperState directly, but it determines which step gets the chance to do so next.

8. Who uses it

The file is used by the lane assembly/bootstrap phase, where the concrete state machine is built before execution begins.

Its consumer is conceptually something like:

nodes = GraphMapperNodes(...)
transitions = build_transitions(nodes)
engine = StateMachineEngine(
    transitions=transitions,
    terminal_states=TERMINAL_STATES,
)
engine.execute(initial_state, start_at=START_STATE)

Even if that exact assembly code lives elsewhere, this is the runtime role this file serves.

9. Internal flow
9.1 route_after_execute_action(state)
Role

This router resolves the state that follows execute_action.

Logic

Its priority is:

use route_hint if present,
otherwise default to update_graph.
Why this matters

This matches the actual behavior of GraphMapperNodes.execute_action(...), which:

executes the chosen action,
builds _action_result,
records evidence,
and sets route_hint to:
"update_graph" by default,
"success" for terminal success,
"fail" for terminal failure.
Operational meaning

The default policy says:

After an action, the normal next move is to internalize its result into the graph.

That is why update_graph is the fallback. Only if the action itself already implies a terminal result does the router bypass graph update and jump directly to success or fail.

9.2 route_after_advance_branch(state)
Role

This router resolves the state that follows advance_branch.

Logic

Its priority is:

use route_hint if present,
otherwise default to inspect_node.
Why this matters

This reflects the real meaning of branch advancement in the lane:

choose the next scope,
resume from a choice point,
re-enter via a strategic anchor,
or finalize the run.

If no explicit terminal route is produced, the lane should continue by observing the next active node. That is why inspect_node is the fallback.

Operational meaning

The default branch policy is:

After branch resolution, exploration normally returns to observation.

That keeps the loop coherent.

9.3 build_transitions(nodes)
Role

Construct the concrete transition table of the graph_mapper lane.

Resulting transition graph
bootstrap         -> inspect_node
inspect_node      -> classify_node
classify_node     -> build_node_view
build_node_view   -> decide_action
decide_action     -> execute_action
execute_action    -> route_after_execute_action(...)
update_graph      -> advance_branch
advance_branch    -> route_after_advance_branch(...)
success           -> terminal
fail              -> terminal
Interpretation

This graph is intentionally simple in its spine:

deterministic progression through observation and decision preparation,
dynamic routing only after action execution,
dynamic routing only after branch resolution,
explicit terminal states.

This is not a free-form graph where any state can jump anywhere. It is a controlled workflow with two carefully chosen flex points.

10. How it fits in the architecture

The file belongs to the execution composition layer. It is not pure engine code and not pure lane logic. It is the bridge between them.

Correct architectural placement
Engine layer

The engine knows how to:

run a step,
apply updates,
resolve next state,
stop at terminal states.
Lane logic layer

GraphMapperNodes knows how to:

bootstrap runtime,
inspect,
classify,
build view,
decide,
execute,
update graph,
advance branches,
and terminate.
Transition composition layer

runtime/transitions.py knows:

which concrete method corresponds to each state,
where sequencing is fixed,
where routing is dynamic,
what the start state is,
and what states are terminal.
Architectural summary
generic engine
    + concrete steps
    + concrete transition map
    = executable graph_mapper lane

This file is the concrete transition map.

11. Full flow integration with the lane

To understand this file correctly, it must be read together with the lane cycle already documented in the execution manual.

Integrated cycle
bootstrap
 -> inspect_node
 -> classify_node
 -> build_node_view
 -> decide_action
 -> execute_action
    -> success
    -> fail
    -> update_graph
 -> update_graph
 -> advance_branch
    -> success
    -> fail
    -> inspect_node
What this reveals
execute_action is the first major routing hinge

It can:

continue normal graph mutation,
or terminate immediately.
advance_branch is the second major routing hinge

It can:

continue exploration through a new observation cycle,
or terminate after branch policy resolution.

This is one of the clearest places where the lane’s real operational design becomes visible.

12. Relationship with GraphMapperNodes

This file is tightly coupled to GraphMapperNodes, but in a disciplined way.

Mapping between states and methods
"bootstrap" -> nodes.bootstrap
"inspect_node" -> nodes.inspect_node
"classify_node" -> nodes.classify_node
"build_node_view" -> nodes.build_node_view
"decide_action" -> nodes.decide_action
"execute_action" -> nodes.execute_action
"update_graph" -> nodes.update_graph
"advance_branch" -> nodes.advance_branch
"success" -> nodes.success
"fail" -> nodes.fail
Important behavioral alignment

This file assumes a specific runtime discipline from GraphMapperNodes:

fixed-sequence steps should not depend on routing side effects,
routed steps should leave clear routing signals when needed,
and terminal states should be reachable through explicit router outcomes.

That aligns with the documented design note in GraphMapperNodes that says this version tries to avoid depending on route_hint in states that already use a fixed next_step.

So this file is not just wiring. It also encodes a workflow philosophy:

fixed sequencing where possible,
dynamic routing only where necessary.
13. Relationship with GraphMapperState

This file does not manipulate GraphMapperState directly, but it controls when and where the runtime state will be read and mutated next.

For example:

execute_action can set route_hint based on action outcome,
the router reads that value from the shared engine state dict,
and the engine then advances to either update_graph, success, or fail.

Likewise:

advance_branch may resolve a new exploration path,
leave a route outcome,
and the router either loops back into inspect_node or terminates.

So while this file is not itself stateful, it is a state progression controller.

14. Relationship with the engine

This file only works correctly if read in the context of the engine contract documented earlier. The engine is responsible for executing steps and resolving the next state according to the transition definition.

Why this file exists instead of hardcoding flow in the engine

Because the engine is generic. It should not know anything about:

inspect_node,
decide_action,
advance_branch,
or the semantics of graph_mapper.

This file keeps domain workflow out of the engine while still making the lane explicit and inspectable.

That is a clean separation.

15. Risks and fine details
1. String-based state names

All state names are plain strings. That makes them readable and easy to inspect, but it also means they must stay perfectly synchronized across:

transition keys,
router return values,
terminal state declarations,
and step naming conventions.

A typo here is not “cute dynamic flexibility”; it is a future support ticket in disguise.

2. nodes is structurally typed, not explicitly typed

Because build_transitions(nodes) accepts object, this file relies on runtime shape rather than strict static typing.

That gives composition flexibility, but also means:

missing methods are caught late,
and the transition map is only as valid as the object passed in.
3. route_hint is intentionally constrained

This is one of the most important design details in the file.

route_hint is not used everywhere. It is used only behind routers, and routers exist only for:

execute_action
advance_branch

That prevents the workflow from becoming opaque.

4. Default routes are meaningful, not arbitrary

The fallback to update_graph after execution is not random. It reflects the architectural rule that action results should normally be internalized.

The fallback to inspect_node after branch advancement is also not random. It reflects the rule that branch switching normally leads back into another observation cycle.

5. Terminal states are both methods and formal terminals

success and fail are not just labels. They are:

real steps in GraphMapperNodes,
and also explicit terminal states in the transition topology.

That matters because the engine will only stop if those states are recognized as terminal.

16. Maintenance rules
Rule 1: every new step must be registered here

If a new step is added to GraphMapperNodes, this file must be updated or the new behavior will not become part of the executable lane.

Rule 2: prefer next_step over router

If a transition is deterministic, use next_step.
Only use a router when the step truly needs runtime-dependent routing.

That preserves readability and keeps routing logic local.

Rule 3: if a router returns a new state name, that state must exist

Any router outcome must correspond to a real transition key or a terminal state. Otherwise execution will fail at runtime.

Rule 4: terminal additions require TERMINAL_STATES updates

If a new terminal-like state is introduced, it must be added to the terminal set. Otherwise the engine will not treat it as a stopping point.

Rule 5: renaming steps requires synchronized renaming here

Since state names are string-based, renaming a step or transition name requires updating:

the transition key,
any router return values,
any engine references,
and any manual describing the lane.
17. Contributor checklist
For humans
[ ] Did I add or rename a step in GraphMapperNodes?
[ ] If yes, did I update build_transitions(...)?
[ ] Is the transition fixed (next_step) or dynamic (router)?
[ ] If dynamic, is the routing condition truly necessary?
[ ] If a router returns a new state, is that state declared?
[ ] If the new state is terminal, did I add it to TERMINAL_STATES?
[ ] Does the new path preserve lane readability?
[ ] Does the default route still reflect the lane’s operational logic?
For AI agents
1. Read START_STATE and TERMINAL_STATES first.
2. Expand build_transitions(nodes) into a graph.
3. Separate fixed transitions from router-based transitions.
4. Inspect route_after_execute_action(...) and route_after_advance_branch(...).
5. Cross-check which GraphMapperNodes methods can set route_hint.
6. Verify that all returned state names exist in the transition map.
18. Debugging guide
If the lane jumps to the wrong next step

Check:

whether the transition uses next_step or router,
whether route_hint was set by the step,
whether the router fallback is masking a missing route signal.
If execution never reaches update_graph

Check:

whether execute_action is returning route_hint = "success" or "fail" too early,
or whether some action path bypasses expected graph mutation semantics.
If branch advancement loops strangely

Check:

whether advance_branch is leaving an explicit terminal route_hint,
or whether the fallback to inspect_node is being triggered repeatedly without changing effective runtime context.
If the engine fails on an unknown state

Check:

router return values,
transition keys,
and terminal state declarations.
19. How to extend this file safely
Case 1: insert a new fixed step

Example pattern:

decide_action -> new_step -> execute_action

You must:

add the method to GraphMapperNodes,
insert the transition here,
update the preceding step’s next_step,
and decide the next step from the new state.
Case 2: add a new routed step

You must:

create the step method,
decide the router contract,
add the router function,
and ensure all router outcomes resolve to declared states.
Case 3: add a new terminal outcome

You must:

create the state,
wire it in transitions,
and include it in TERMINAL_STATES.
20. Architectural summary

runtime/transitions.py is the file that makes the graph_mapper lane executable as a declared workflow graph.

It does not perform the work of the lane.
It defines the order in which that work can happen.

Its design is strong because it keeps the lane topology:

explicit,
centralized,
readable,
and only mildly dynamic.

The two main routing hinges are:

after action execution,
and after branch advancement.

Everything else remains fixed and legible.

That is exactly the kind of file that saves future maintenance from turning into cave archaeology with a flashlight and bad coffee.

21. Ultra-short summary for AI agents
What this file does

Declares the concrete transition graph of the graph_mapper lane.

Main exports
build_transitions(nodes)
route_after_execute_action(state)
route_after_advance_branch(state)
START_STATE
TERMINAL_STATES
Key rule

Most states use fixed next_step.
Only execute_action and advance_branch use routed continuation.

Golden mental model
engine executes
nodes implement
transitions declare
state remembers