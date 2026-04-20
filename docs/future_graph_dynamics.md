# Future Direction: Dynamic Graphs, Structural State, and Subroutines

## Purpose

This document describes a future direction for `graph_mapper_agent`.

The current architecture already recognizes that agent actions can change the local state of a node. That is visible today in search-driven DOM mutation, reinspection, and the runtime heuristics that decide whether to reuse a node or materialize a new one.

But that recognition is still partial. The project does not yet expose a fully explicit model for:

- node identity versus node state
- action-induced node mutation
- local state transitions inside the same broader place
- structural compression of richer runtime state before it reaches the decider
- a formal architectural contract for future subroutines

This document does not propose an immediate refactor. It defines the direction more clearly: the web should eventually be treated less like a flat graph of fixed pages and more like a dynamic state space, while the model-facing representation remains structural, bounded, and centered on the current task state.

---

## 1. The Current Graph Model Is Strong, but Still Relatively Flat

Today the system already has a strong navigational architecture:

- a global graph memory
- active paths, branches, and anchor points
- local `NodeView` projections for tactical decisions
- explicit decider -> executor -> updater flow

This gives the project a serious runtime model instead of a loose prompt loop.

The current design is especially clear in:

- [`GraphMapperNodes`](../graph_mapper_agent/runtime/nodes/graph_mapper_nodes.py)
- [`NavigationLaneTransitions`](../graph_mapper_agent/runtime/transitions.py)
- [`NodeViewBuilder`](../graph_mapper_agent/application/services/node_view_builder.py)
- [`GraphUpdater`](../graph_mapper_agent/application/services/graph_updater.py)

Even so, the graph model still behaves mostly like a navigable surface of relatively stable nodes and edges.

That is good enough for many flows, but it is not yet the full shape of the web.

---

## 2. Why DOM Mutation Changes the Picture

Some relevant changes in the web do not happen as classic movement from one URL to another.

They happen because the agent acts on the current environment:

- it submits a local search
- it changes a filter
- it expands a section
- it reveals hidden content
- it interacts with a dynamic container
- it triggers an in-page transition that materially changes the visible state

The current runtime already handles part of this problem.

Search-driven mutation is the clearest example:

- [`search_with_text(...)`](../graph_mapper_agent/application/services/execution/search.py)
- [`GraphUpdater._apply_search_with_text(...)`](../graph_mapper_agent/application/services/graph_updater.py)
- [`GraphUpdater._search_should_create_new_node_static(...)`](../graph_mapper_agent/application/services/graph_updater.py)
- [`GraphUpdater._search_result_has_real_delta(...)`](../graph_mapper_agent/application/services/graph_updater.py)

Those paths show that the system already recognizes something important:

> a node may change under agent action, and sometimes that change is strong enough to justify a new node materialization.

So the problem is not hypothetical. The runtime has already encountered it.

---

## 3. From a Flat Graph to a Dynamic State Space

The deeper future direction is to treat the web as more than a static graph of stable page identities.

The richer interpretation is this:

- the graph still provides structural continuity
- but nodes may have mutable local states
- and agent actions may induce transitions between those states

In that view, the system is not only exploring places. It is also exploring possible local states of those places.

That means the runtime would gradually evolve from something like:

```text
stable nodes + navigable edges
```

toward something more like:

```text
structural identities + local states + action-induced transitions
```

This is why the current graph can be described as still somewhat "2D", while a more dynamic model would add another dimension:

- not just where the agent is
- but how that place has been transformed by interaction

That extra dimension is not geometry in a literal sense. It is the space of node mutation under action.

---

## 4. The Core Constraint: The Model Must Still See Structure, Not Raw History

This future direction does **not** mean the decider should receive more and more raw context.

That would be the wrong direction.

Even if the runtime becomes better at modeling dynamic node mutation, the representation shown to the model should remain:

- structural
- compact
- bounded
- centered on the current task state

The model should not be responsible for carrying:

- the full history of the run
- every prior branch exploration
- every DOM mutation ever observed
- the full causal narrative of how the system arrived here

That complexity belongs in the runtime.

This is already part of the architecture today:

- global runtime state lives in [`GraphMapperState`](../graph_mapper_agent/runtime/state/models.py)
- tactical projection is built by [`NodeViewBuilder`](../graph_mapper_agent/application/services/node_view_builder.py)
- the decider consumes that structured local view in [`GraphMapperDecider`](../graph_mapper_agent/application/services/decision/decider.py)

The future model should preserve that principle, not weaken it.

### Core Principle

> The runtime should absorb complexity, and the decider should receive only the current task-relevant structural state.

That remains true even if the runtime eventually models richer node mutation and dynamic state transitions.

---

## 5. State Understanding Matters More Than Total Recall

The system should behave more like a structured navigator in a digital environment than like a narrator of its full past.

A person does not need to remember every prior thought or every exact intermediate step in order to act well in a space. What matters is a compact operational understanding of the current state:

- where they are
- what is currently visible
- what is already known
- what remains unresolved
- which routes are more promising
- which action is most appropriate now

The same principle applies here.

The point is not to expose total recall to the model. The point is to expose useful state understanding.

That is why the long-term shape of the system should still be:

- graph memory for structural continuity
- branch and anchor organization for tactical exploration
- local node state for immediate action
- compact model-facing projection for decision-making

Not:

- full narrative replay
- full raw history
- full mutation history inside a giant prompt

---

## 6. A Better Dynamic Model Should Increase Runtime Intelligence, Not Prompt Burden

If the runtime starts representing richer local mutation, that should mostly produce **more system intelligence below the decider**, not larger prompts above it.

In practice, that means more specialized processing before decision-making, for example:

- interpreting whether a DOM mutation is meaningful
- deciding whether two local states are equivalent
- deciding whether a mutation should stay inside the same node or materialize a new state
- compressing mutation history into a compact state summary
- evaluating whether a branch or anchor became more promising after a local interaction

Those are good candidates for future subroutines.

But the important design rule is this:

> richer runtime modeling should collapse complexity before the decider, not dump unresolved complexity into the decider.

---

## 7. Subroutines Need a Clear Architectural Contract

The current system already contains multiple specialized services and focused runtime steps, but it does not yet expose a fully explicit architectural contract for future subroutines.

Before expanding this area, that contract should be made clear.

Otherwise the likely failure mode is predictable:

- each new need creates a custom helper
- each helper carries its own assumptions
- state boundaries get blurry
- more logic leaks into prompts
- the system accumulates local patches instead of a coherent extension model

That would weaken the architecture rather than extend it.

### What a Future Subroutine Should Be

A future subroutine should be a disciplined state-processing component.

It should:

- consume a bounded structural slice of runtime state
- perform a narrow interpretation, transformation, or compression task
- return structured output
- avoid direct hidden orchestration
- avoid becoming a second decider
- avoid pushing raw unresolved complexity into the model prompt

### What the Contract Should Define

A clean architectural contract for subroutines should answer at least these questions:

1. What state can a subroutine read?
   Only the bounded portion of runtime state relevant to its purpose.

2. What can it produce?
   Typed structured output, not open-ended narrative memory.

3. Can it mutate runtime directly?
   Preferably no. In most cases it should return explicit results that the main runtime can absorb in a controlled way.

4. Where does it sit?
   Below orchestration, above raw infrastructure, as a focused processing layer.

5. How does it relate to the decider?
   It should reduce complexity before decision-making, not increase it.

6. How is it evaluated?
   By whether it improves structural state representation, action quality, and downstream data quality.

This contract matters even more if the project starts modeling dynamic node state more seriously.

---

## 8. Why This Direction Also Matters for Smaller Specialized Models

One long-term value of a stronger structural runtime is not only better online behavior. It is also better data.

If the system can represent current state more cleanly, then it can generate better examples of:

- structural state
- local task situation
- action choice
- state update after action

That is much better training material for smaller specialized models than:

- long raw trajectories
- overloaded prompts
- loosely structured reasoning traces
- uncompressed exploration history

This is one reason to preserve the structural philosophy even while making the runtime more dynamic.

The aim is not to build a system that depends on an ever-larger general model prompt.
The aim is to build a system that can:

- understand state more precisely
- act from structured state
- and eventually produce high-quality state-action-update data for more specialized models

---

## 9. What Is Still Missing Today

The project is not there yet, and that is fine.

What is still missing is not only implementation, but conceptual closure.

The system does not yet have a fully explicit model for concepts such as:

- `NodeIdentity`
- `NodeState`
- `NodeStateTransition`
- `MutationKind`
- `StateEquivalencePolicy`
- `MaterializationPolicy`
- a general subroutine contract for dynamic-state interpretation and compression

Today the runtime handles parts of the problem through useful heuristics and localized mechanisms.

That is visible in:

- node reuse and materialization through [`GraphMemory.ensure_node(...)`](../graph_mapper_agent/domain/graph.py)
- search delta handling in [`GraphUpdater._apply_search_with_text(...)`](../graph_mapper_agent/application/services/graph_updater.py)
- tactical view compression in [`NodeViewBuilder`](../graph_mapper_agent/application/services/node_view_builder.py)

Those are good foundations, but they are not yet the full explicit theory of the space.

---

## 10. Recommended Direction

The right next step is not to prematurely model the whole dynamic space.

The right next step is to strengthen the base:

1. preserve structural model-facing projections
2. define a clear architectural contract for subroutines
3. keep complexity in runtime processing rather than in prompt payloads
4. gradually clarify node identity versus node state versus node transition
5. let richer mutation handling emerge from explicit runtime mechanisms, not ad hoc helpers

This keeps the project aligned with its strongest architectural idea:

> the agent should not think by carrying everything in free-form text; it should act from a structured understanding of state.

---

## Summary

The current graph architecture is already strong, but still relatively flat.

The web is more dynamic than a static graph of fixed pages, and the runtime has already started to encounter that reality through DOM mutation and search-driven state changes.

A richer future model would treat the web as a dynamic state space where structural identities, local node states, and action-induced transitions all matter.

But that richer model should not be paid for by increasing model burden.

The correct direction is:

- more runtime structure
- more disciplined subroutines
- better compression of dynamic state
- the same compact structural projection to the decider
- and cleaner data for future smaller specialized models
