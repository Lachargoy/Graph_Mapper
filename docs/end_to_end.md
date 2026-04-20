# End-to-end Manual: Decider -> Executor -> Updater in `graph_mapper_agent`

## Purpose

This manual brings together the three central sublayers of `graph_mapper_agent` into a single narrative:

* **decision layer**
* **execution layer**
* **graph mutation / updater layer**

Its goal is to explain the complete flow from the moment the system is situated at a graph node to the moment a chosen action modifies the agent’s live memory.

In other words, this document answers one simple but critical question:

> how does the system move from “being at a point in the graph” to “structurally changing its state” based on a decision?

---

# 1. Core idea

The full architecture can be understood like this:

```text
GraphMapperState
    -> current node in graph
    -> NodeViewBuilder
    -> NodeView
    -> GraphMapperDecider
    -> decision
    -> GraphMapperActionExecutor
    -> ActionExecutionResult
    -> GraphUpdater
    -> mutated graph + mutated runtime
```

## Correct mental model

The system does not work like this:

* “LLM sees a page”
* “LLM decides something”
* “browser does something”

It works more like this:

1. there is a total live memory of the agent,
2. that memory is projected as a local view of the current node,
3. the decider acts on that view,
4. the execution layer converts the decision into an operational outcome,
5. the updater layer transforms that outcome into new structural memory.

That sequence is the heart of the design.

---

# 2. The three major sublayers

## 1. Decider

It answers:

> “what is the best next move from this node?”

## 2. Executor

It answers:

> “what happened when we tried to do that?”

## 3. Updater

It answers:

> “how should the graph and runtime change based on what happened?”

## Correct reading

```text
Decider = tactical intention
Executor = operational outcome
Updater = structural internalization
```

---

# 3. Starting point: `GraphMapperState`

## What it is

`GraphMapperState` is the complete live memory of the lane.

It contains, among other things:

* graph
* scopes
* arrivals
* path and anchor
* choice points
* navigation perception by node
* validation state by node
* findings
* tactical scratchpad
* inspection, search, download, and artifact results
* current node
* current content owner
* step count

## Why it matters here

The end-to-end flow does not begin with the decider. It begins with the live state.

Every decision, execution, and mutation happens inside that state.

---

# 4. The current node as the point of situation

## What it represents

The current node is the active point in the graph where the agent is located.

That node does not exhaust the whole runtime, but it does define the local action frontier for the current turn.

## Relationship to the flow

The flow always starts from a situated node.

That is why the system is not globally omniscient. It is tactically localized.

---

# 5. The local projection: `NodeView`

## What it is

`NodeView` is the structured, tactical representation of the current node inside the active context.

It is not the full runtime.
It is not the whole graph.
It is not the raw DOM.

It is the local projection of the state required by the decision layer.

## What it summarizes

It includes things such as:

* node identity and type
* actionable candidates
* arrival context
* node-local memory
* goal progress
* tactical scratchpad
* navigation perception
* goal validation
* search targets
* restrictions
* path context
* choice points
* strategic return point

## Core idea

The “vision of the LLM” is not the whole system.

The vision of the LLM is:

> a local decision state situated at a point in the graph

And that vision is represented as `NodeView`.

---

# 6. Building `NodeView`

## Responsible component

`NodeViewBuilder`

## What it does

It converts:

```text
live runtime + current node + scope + path + findings + validation + perception
```

into:

```text
NodeView
```

## Result

The decision layer does not operate on the raw runtime. It operates on a stable cognitive interface.

---

# 7. First major transition: from live state to tactical intention

## Main responsible component

`GraphMapperDecider`

## Input

* `NodeView`
* ledger / run / actor / target context when applicable

## Output

* `GraphMapperDecision`

## What it actually does

It does not navigate.
It does not inspect.
It does not mutate the runtime.

Its job is to choose the next action.

## Possible modes

### 1. Heuristic mode

If there is no LLM use case.

### 2. LLM mode

If `GraphMapperDecisionLlmUseCase` exists.

---

# 8. How the system decides

## General path

```text
NodeView
    -> GraphMapperDecider.decide(...)
        -> heuristic engine
        or
        -> LLM path
            -> prompt construction
            -> structured output
            -> llm_pipeline refinement
```

## Decision contract

The domain output is `GraphMapperDecision`, which contains:

* action
* edge_id
* search_target_id
* query_text
* decision_rationale
* confidence
* scratchpad_update

## Meaning

The decision layer produces a **structured intention**, not an execution.

---

# 9. LLM decision path

## Pieces

* `GraphMapperDecisionLlmUseCase`
* `llm_pipeline.py`
* prompt builders
* condition matching
* fallback selection
* guardrails

## Flow

```text
NodeView
    -> prompt builder
    -> LLM runtime with ledger
    -> structured JSON
    -> DecisionLlmContext
    -> guardrails
    -> refinement / fallback selection
    -> GraphMapperDecision
```

## Core idea

The LLM is not acting on its own.

The LLM proposes a structured decision that still passes through:

* action validation,
* matching against pending goals,
* fallback selection,
* tactical degradations,
* and guardrails.

---

# 10. Decision guardrails in runtime

## Responsible component

`GraphMapperNodes.decide_action(...)`

## What happens after the decider

Even after the decider has returned a decision, the runtime re-checks things such as:

* actual validation target
* existing `edge_id`
* valid `search_target_id`
* present `query_text`

## Meaning

There is a double barrier:

1. guardrails inside the decision pipeline
2. guardrails inside the runtime before execution

This cleanly separates:

* a plausible decision,
* from an executable decision.

---

# 11. Second major transition: from tactical intention to operational outcome

## Main responsible component

`GraphMapperActionExecutor`

## Input

* `runtime`
* `decision`

## Output

* `ActionExecutionResult`

## What it does

It takes an already accepted decision and turns it into a real operational result.

## What it does not do

It does not directly mutate the graph.

---

# 12. What the executor executes

## Action families

### 1. Terminal actions

* `mark_exhausted`
* `success`
* `fail`

### 2. Validation action

* `validate_current_content`

### 3. Search action

* `search_with_text`

### 4. Edge-based actions

* `follow_edge`
* `download_artifact`
* `open_artifact`

## Meaning

The executor acts as a dispatcher for operational action families.

---

# 13. Canonical execution result

## Contract

`ActionExecutionResult`

## What it contains

It may include:

* action
* status
* edge_id
* child_node_id
* inspection_result
* download_result
* artifact_result
* local_perception_result
* search_target_id
* query_text
* reason

## Core idea

This contract represents:

> what happened when we tried to execute the action

It still does not represent the new state of the system.

---

# 14. Edge execution

## Responsible component

`edge_actions.py`

## What it handles

* page inspection
* downloads
* artifact opening
* `follow_edge` with prior probe

## Important conceptual point

`follow_edge` does not simply mean “go to an HTML page.”

First, the resource is probed.
Then it is resolved whether the edge leads to:

* HTML inspection
* PDF / direct artifact download
* ambiguous resource

This makes navigation carrier-aware.

---

# 15. Search execution

## Responsible component

`search.py`

## What it does

It executes a localized search on the current node using a visible `search_target_id`.

## What it returns

An `ActionExecutionResult` with `inspection_result` representing the new scene produced by the search.

## Important point

Not every search is automatically considered real progress.

The execution layer already detects:

* silent no-op
* missing target
* absence of delta
* same URL with no real change

---

# 16. Validation execution

## Responsible component

`validation.py`

## What it does

It implements `validate_current_content` over local evidence already available.

## What it validates

It can validate from carriers such as:

* inspection
* artifact
* download

## Important point

`validate_current_content` does not navigate.

It operates on evidence already possessed by the runtime.

---

# 17. Local perception during execution

## Responsible components

* `validation.py`
* `artifact.py`

## What they add

They may attach `local_perception_result` to outcomes of:

* inspected content
* downloaded artifact
* opened artifact
* `validate_current_content`

## Meaning

The execution sublayer does not only move bytes or HTML.

It can also produce formal local evaluation that will later be absorbed by the updater.

---

# 18. Third major transition: from operational outcome to structural memory

## Main responsible component

`GraphUpdater`

## Input

* `runtime`
* `action_result`

## Real output

* mutated graph
* mutated runtime

It does not return another large contract. Its job is to update the internal state.

---

# 19. What the updater does

## Core responsibility

Interpret `action_result` and update:

* nodes
* edges
* arrivals
* active path
* current node
* content owner
* per-node caches
* findings
* validation payloads
* goal matching
* choice point priorities

## Correct formula

```text
ActionExecutionResult
    -> GraphUpdater
    -> internal memory mutation
```

---

# 20. Updater handlers

## Main paths

* `_apply_follow_edge`
* `_apply_download_artifact`
* `_apply_open_artifact`
* `_apply_validate_current_content`
* `_apply_search_with_text`
* `_apply_mark_exhausted`
* `_apply_failed_action_result`

## What this means

Each family of operational result has its own internal mutation semantics.

The updater does not treat all actions as if they were equivalent.

---

# 21. What happens when `follow_edge` succeeds

## Typical effects

* ensures or creates child node
* links `child_node_id` to the edge
* stores `inspection_result_by_node`
* changes `current_node_id`
* creates `ArrivalContext`
* records the visit
* updates `active_path`
* marks the edge as useful
* marks the parent node as expanded
* may register a finding if there is local perception

## Meaning

This is where the system truly changes its position in the graph.

---

# 22. What happens when `download_artifact` or `open_artifact` succeeds

## Typical effects

* updates `download_result_by_node`
* updates `artifact_result_by_node` when applicable
* updates `current_content_owner_node_id`
* marks the edge as useful
* records artifact URLs in the owner node
* updates local working memory
* may register findings

## Meaning

Here the current node does not always change, but the locally owned evidence of the system changes substantially.

---

# 23. What happens when `validate_current_content` succeeds

## Typical effects

* resolves `target_node_id`
* updates inspection/download/artifact caches if they are present in the result
* updates `goal_validation_payload_by_node`
* updates `document_validation_state_updater`
* modifies the node’s working memory
* may register a formal finding

## Meaning

Validation transforms local evidence into formal progress and reusable validation memory.

---

# 24. What happens with `search_with_text`

## Case 1: no real delta

The updater:

* records the query if applicable
* updates working memory
* records no-op style progress
* and does not mutate the node as if a useful new scene had appeared

## Case 2: real delta

The updater may:

* freeze snapshot
* store `search_result_by_node`
* change `current_node_id`
* change `current_content_owner_node_id`
* create a new node or reuse the current one
* record arrival
* extend path
* clear perception/refine caches of the target node

## Meaning

Search can be:

* a no-op,
* a local mutation,
* or an effective scene transition.

---

# 25. Integration with findings and goals

## Main responsible components

* `GraphUpdater`
* `FindingExtractor`

## What happens

From artifacts, downloads, local inspection, or local validation, the updater can register `FindingRecord`.

Those findings then help to:

* reevaluate goal trace
* count satisfied / pending conditions
* reprioritize choice points

## Meaning

This is where grounding closes:

```text
execution outcome
    -> finding
    -> goal evaluation update
```

That converts navigation and artifacts into formal semantic progress.

---

# 26. The complete chain in one reading

## End-to-end flow

```text
GraphMapperState
    -> current node
    -> NodeViewBuilder
    -> NodeView
    -> GraphMapperDecider
        -> heuristic or LLM path
        -> GraphMapperDecision
    -> GraphMapperNodes.decide_action(...)
        -> runtime guardrails
    -> GraphMapperActionExecutor.execute(...)
        -> ActionExecutionResult
    -> GraphMapperNodes.execute_action(...)
        -> _action_result
    -> GraphUpdater.apply_action_result(...)
        -> graph mutation
        -> runtime mutation
        -> findings / validation / path updates
    -> next cycle
```

## Interpretation

Each sublayer transforms the system in a different way:

* **NodeView layer**: local cognitive projection
* **Decider layer**: tactical intention
* **Executor layer**: operational outcome
* **Updater layer**: updated structural memory

---

# 27. What the LLM really sees inside this flow

The LLM’s view sits in the mid-upper part of the flow.

It does not see:

* the full runtime,
* the updater,
* the future result,
* the whole raw graph.

It sees:

* `NodeView`

That means:

> the LLM decides from a situated state, not from total omniscience.

Then other layers turn that situated view into action and memory.

---

# 28. Separation of responsibilities

## Decider

Chooses the action.

## Executor

Produces the result of executing the action.

## Updater

Transforms that result into new internal state.

## Why this is good

Because it prevents a single layer from mixing:

* reasoning,
* IO,
* and structural mutation.

That makes the system more controllable and more documentable.

---

# 29. Risks in the end-to-end flow

## 1. If `NodeView` is poor, the decider will choose badly

The problem will not always be in the LLM. It may be in the state projection.

## 2. If the executor misinterprets a carrier, the updater will inherit garbage

Resolving HTML/PDF/ambiguous resource is critical.

## 3. If the updater internalizes an `action_result` incorrectly, the system learns incorrectly

That affects:

* current node
* content ownership
* findings
* validation memory
* active path

## 4. Search is especially delicate

Because it may have no delta, mutate the current node, or create a new one.

## 5. Validation connects many layers

It depends on:

* decision guardrails
* validation target
* executor validation path
* updater validation caches
* finding extraction
* goal evaluation

---

# 30. How to read this flow as a human

Recommended order:

1. `GraphMapperState`
2. `domain/view.py`
3. `node_view_builder.py`
4. `decision/*`
5. `execution/*`
6. `runtime_views.py`
7. `graph_updater.py`
8. `finding_extractor.py`

That lets you follow the flow from:

* live memory,
* to local projection,
* to decision,
* to execution,
* to internal mutation.

---

# 31. How to read this flow as an AGI

## Objective

Understand how the agent becomes situated, decides, acts, and learns internally in each cycle.

## Procedure

### Step 1

Identify the current node and active context in `GraphMapperState`.

### Step 2

Follow how `NodeView` is built.

### Step 3

Follow how `GraphMapperDecider` transforms `NodeView` into a decision.

### Step 4

Follow how the executor transforms that decision into `ActionExecutionResult`.

### Step 5

Follow how the updater transforms that result into new structural memory.

### Step 6

Observe what changes in:

* current node
* content owner
* per-node caches
* findings
* validation state
* active path
* choice point priorities

---

# 32. Executive summary

The end-to-end flow of `graph_mapper_agent` does not consist of a single model making decisions over web pages. It consists of a staged architecture where the agent’s live state is projected as a local view (`NodeView`), that view feeds a decision layer (`GraphMapperDecider`), the decision is turned into an operational outcome by the execution layer (`GraphMapperActionExecutor`), and finally that outcome is internalized as a real mutation of both the graph and the runtime through the updater (`GraphUpdater`).

The conceptual key is this:

> the system separates local representation, tactical intention, operational outcome, and structural memory.

That separation allows the agent to be:

* situated,
* controllable,
* auditable,
* and capable of learning locally without mixing reasoning, IO, and internal mutation into a single piece.

---

# 33. Ultra-summary

## Where everything starts

`GraphMapperState`

## What the decider sees

`NodeView`

## What the decider produces

`GraphMapperDecision`

## What the executor produces

`ActionExecutionResult`

## What the updater produces

New runtime + new internal graph

## Final formula

```text
state -> NodeView -> decision -> execution result -> updated state
```
