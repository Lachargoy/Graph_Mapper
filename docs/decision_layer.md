# Decision Layer Reference Manual

## Purpose

This manual explains the decision layer of `graph_mapper_agent`.

The decision layer is responsible for choosing the next tactical action from the current `NodeView`.

It does not browse directly, it does not mutate the graph directly, and it does not own the full runtime state. Its job is to read the local decision surface and select the most appropriate next move.

---

## Core Idea

The correct mental model is:

```text
GraphMapperState
    -> NodeViewBuilder
    -> NodeView
    -> GraphMapperDecider
    -> GraphMapperDecision
```

The decider sits between:

- local structural interpretation
- and operational execution

Its output is a tactical decision, not a browser side effect and not a graph mutation.

---

## Where It Lives

Relevant pieces:

- `graph_mapper_agent/application/services/decision/decider.py`
- `graph_mapper_agent/application/services/decision/llm_pipeline.py`
- `graph_mapper_agent/application/services/decision/fallback_selection.py`
- `graph_mapper_agent/application/services/decision/guardrails/*`
- `graph_mapper_agent/application/services/candidate_selector.py`
- `graph_mapper_agent/application/services/candidate_ranker.py`

---

## What It Decides

Typical actions include:

- `follow_edge`
- `download_artifact`
- `open_artifact`
- `search_with_text`
- `validate_current_content`
- `refine_navigation_perception`
- `mark_exhausted`
- `success`
- `fail`

The decider chooses among these based on the current node view and the current tactical situation.

---

## Inputs

The decision layer does not consume the whole raw runtime directly.

Its main input is:

- `NodeView`

That matters because the system does not ask the model or heuristic engine to reconstruct the entire run from scratch.

Instead, the runtime compresses relevant state into a bounded local representation.

This is one of the core architectural differences of the project.

---

## Two Operating Modes

The decider currently supports two broad modes:

### 1. Heuristic mode

If no LLM use case is configured, the decider falls back to:

- `HeuristicDecisionEngine`

This allows the runtime to keep moving without a model-backed decision call.

### 2. LLM-backed mode

If an LLM use case is available, the decider routes the current `NodeView` through:

- `decide_llm(...)`

This means the model interprets the local structured state and collapses it into the best next action.

---

## Relationship to Perception and Validation

The decider is not alone.

Its decision quality depends on the quality of the local state it receives. That means it relies on upstream capabilities such as:

- navigation perception
- local perception
- goal validation
- findings
- choice points
- tactical path and anchor context

But those systems do not replace the decider.

They feed and refine the state that the decider sees.

That is why the clean formula is:

```text
specialized subroutines
    -> NodeView
    -> decider
    -> decision
```

---

## Why This Layer Matters

If decision-making were mixed directly into execution or graph mutation, the runtime would become much harder to maintain.

Separating the decision layer gives the architecture a cleaner shape:

- `NodeViewBuilder` prepares state
- `GraphMapperDecider` selects action
- `GraphMapperActionExecutor` performs action
- `GraphUpdater` mutates graph and runtime

That division is one of the strongest parts of the project.

---

## Relationship to Future Work

As the system becomes more dynamic, the decision layer should still stay narrow.

The runtime may gain:

- richer node mutation models
- better subroutines
- better tactical compression

But the decider should continue to operate on a bounded current-state projection rather than on a giant history dump.

That principle should remain stable even as the rest of the runtime grows in sophistication.
