# Navigation Perception Reference Manual

## Purpose

This manual explains the role of navigation perception inside `graph_mapper_agent`.

Navigation perception is not the global decider and not the full planner. It is a specialized local-reading capability that helps the runtime understand what a node looks like, which candidates appear locally promising, and whether the current place is worth further effort.

Its role is to improve the quality of local state before the decider chooses the next action.

---

## Core Idea

The correct mental model is:

```text
current node
    -> inspection
    -> navigation perception
    -> local structured signals
    -> NodeView
    -> decider
```

Navigation perception does not decide the whole run.

It produces structured local signals such as:

- layout interpretation
- candidate prioritization hints
- immediate condition gain
- strategic return suggestions
- whether a local search or refinement looks justified

Those signals are then folded into `NodeView`.

---

## Where It Lives

Relevant pieces:

- `graph_mapper_agent/application/services/navigation_perception.py`
- `graph_mapper_agent/application/navigation_perception/*`
- `graph_mapper_agent/bootstrap/builders/perception.py`
- `graph_mapper_agent/adapters/perception/*`
- `graph_mapper_agent/runtime/nodes/graph_mapper_nodes.py`

---

## What Problem It Solves

Without navigation perception, the agent would see only:

- raw inspection payloads
- raw candidates
- local text excerpts

That is often not enough to decide well in dense or ambiguous pages.

Navigation perception improves the local decision surface by answering questions such as:

- what kind of page is this locally?
- which candidates seem most useful for the pending goal slice?
- does the current node already provide immediate progress?
- is it better to continue here, search here, refine here, or return later?

---

## Main Runtime Role

Navigation perception is triggered when the runtime believes the node needs a stronger local reading.

That decision is governed by the trigger policy in:

- `NavigationPerceptionTriggerPolicy`

The service then builds a request that summarizes:

- the current node
- the local goal context
- pending goal conditions
- target document kinds
- temporal constraints
- pattern hints

This intent-building step lives in:

- `NavigationPerceptionIntentBuilder`

The executor then produces a structured `NavigationPerceptionResult`.

That result is later consumed by `NodeViewBuilder`, which projects it into the final decision surface.

---

## Relationship to the Decider

Navigation perception is a subroutine, not an authority.

It does not replace the decider.
It does not mutate the graph by itself.
It does not execute browser actions by itself.

Its job is narrower:

> provide a better local interpretation of the current node so the decider can choose better.

That is why this architecture stays clean:

- perception reads
- the decider decides
- execution acts
- the updater mutates runtime state

---

## Important Outputs

Typical signals include:

- `recommended_next_step`
- `goal_slice_exhausted`
- `immediate_condition_gain`
- `best_immediate_condition_labels`
- `strategic_return_suggested`
- `strategic_return_reason`
- `strategic_return_priority`
- top candidate observations

These are useful because they compress local complexity into structured tactical hints.

---

## Why It Matters

Navigation perception is one of the key reasons this project is not just a browser plus an LLM prompt.

It shows that the runtime is willing to build intermediate structural understanding before choosing the next action.

That matters especially for:

- dense index pages
- pages with many weak candidates
- ambiguous document collections
- cases where immediate local progress is possible but easy to miss

---

## Relationship to Future Work

Navigation perception is also an early example of the subroutine direction described elsewhere in the docs.

It already behaves like a bounded state-processing component:

- it consumes a bounded local state
- it produces structured output
- it improves decision quality without becoming a second orchestrator

That makes it a good reference point for future subroutine architecture.
