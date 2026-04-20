# Graph Mapper Update and Graph Mutation Reference Manual

## Purpose

This manual documents the **graph mutation / runtime update** sublayer of `graph_mapper_agent`, with a focus on how an operational result produced by the executor becomes a real mutation of the:

* graph,
* runtime,
* local node memory,
* findings,
* validation state,
* and navigation context.

The goal is to explain:

* what the updater is,
* what problem it solves,
* what goes in,
* what comes out,
* how it relates to the executor,
* how it relates to `GraphMapperState`,
* and how it transforms `action_result` into live structural memory.

---

# 1. Core idea

The correct way to understand this layer is this:

```text
Decision
    -> Executor
    -> ActionExecutionResult
    -> GraphMapperNodes.execute_action(...)
    -> _action_result
    -> GraphUpdater.apply_action_result(...)
    -> graph + runtime mutation
```

## Correct mental formula

The updater **does not decide**.

The updater **does not perform external IO**.

The updater **does not call the browser directly**.

Its responsibility is different:

> absorb the already-produced operational outcome and translate it into internal changes in the graph and runtime.

That is the essence of this sublayer.

---

# 2. Position in the architecture

## Layer

`application/services/graph_updater.py`

## Architectural role

It sits between:

* the **operational execution** layer,
* and the **live structural memory** of the system.

That means:

* the executor obtains results,
* the updater interprets those results,
* and the runtime and graph change as a result of that interpretation.

## Relationship to the main lane

Inside the lane flow:

```text
decide_action
 -> execute_action
 -> update_graph
 -> advance_branch
```

The updater sublayer lives entirely inside:

**`update_graph`**

but the step `GraphMapperNodes.update_graph(...)` is only the entry point. The real interpretation logic lives in `GraphUpdater.apply_action_result(...)`.

---

# 3. What problem the updater solves

Without this sublayer, `GraphMapperNodes.update_graph(...)` would have to directly handle:

* moving `current_node_id`,
* creating arrivals,
* registering visits,
* updating `inspection_result_by_node`, `download_result_by_node`, `artifact_result_by_node`,
* updating `current_content_owner_node_id`,
* marking edges as useful or failed,
* marking nodes as expanded, partially exhausted, or exhausted,
* registering findings,
* updating document validation,
* changing `active_path`,
* and reinterpreting search results.

That would create too much coupling for a single function.

The updater solves that by separating:

* **operational result**
* from **internal structural memory**

---

# 4. Main pieces that compose this part

## 1. `runtime_views.py`

Defines the **runtime protocols** consumed by the executor, perception, updater, and advance policy.

## 2. `graph_updater.py`

Implements the real mutation of runtime and graph from `action_result`.

## 3. `finding_extractor.py`

Converts artifacts, downloads, local perception, or navigation-perception matches into reusable `FindingRecord` entries for the goal system.

---

# 5. `runtime_views.py`

## Role of the file

This file defines the **minimal runtime interfaces** expected by different sublayers.

It does not implement behavior. It defines access contracts.

## Why it matters for the updater

The updater does not depend on the concrete `GraphMapperState` class.

It depends on the protocol:

**`RuntimeUpdaterPort`**

That allows the updater to demand only what it actually needs:

* access to the graph,
* access to observation caches,
* active path,
* content owner,
* per-node validation,
* per-node perception,
* arrival registration,
* choice-point reprioritization,
* and more.

## Conceptual reading

This file plays an important architectural role:

> prevent the updater from depending on the entire `GraphMapperState` as one amorphous mass.

Instead, it declares which parts of runtime are actually needed by each sublayer.

---

# 6. What `RuntimeUpdaterPort` is

## Role

It is the runtime contract that `GraphUpdater` needs in order to work.

## What it exposes

Among other things, it includes:

* access to the graph
* `current_content_owner_node_id`
* `step_count`
* `navigation_perception_refine_state_by_node`
* `active_path`
* `last_node_view`
* `get_active_scope()`
* `get_arrival(...)`
* `register_arrival(...)`
* `mark_frozen_dom_snapshot(...)`
* `register_search_query(...)`
* `reprioritize_choice_points(...)`

## Interpretation

This makes the architectural view explicit:

The updater is not a small graph utility.

It is a piece that mutates:

* the graph,
* runtime caches,
* tactical memory,
* choice points,
* validation,
* and the active trajectory.

---

# 7. What `GraphUpdater` is

## File

`application/services/graph_updater.py`

## Role of the file

It is the **main façade for internal mutation**.

## Main responsibility

Receive:

* `runtime: RuntimeUpdaterPort`
* `action_result: dict[str, object]`

And translate that result into internal system changes.

## What goes in

The input is an `action_result` that is already structured and produced by the previous layer.

## What comes out

It does not return a rich new object. Its job is to **mutate the runtime in place**.

That is very important.

The updater does not produce another large output contract.

Its real output is:

> the new internal state of the system.

---

# 8. Relationship between executor and updater

## Golden rule

The executor produces outcomes.

The updater produces structural memory.

## Essential difference

### Executor

Performs:

* inspect
* probe
* download
* open
* search
* validate
* and obtains results

### Updater

Performs:

* register current node
* move current node
* update caches
* mark edges and nodes
* update path
* register findings
* update validation
* reinterpret search as delta or no-op

## Correct formula

```text
executor = side effects
updater = state mutation
```

That separation is one of the strongest points of the design.

---

# 9. Main updater flow

## General entry point

`GraphUpdater.apply_action_result(runtime, action_result)`

## General logic

```text
read action and status
    -> if status != ok
        -> _apply_failed_action_result(...)
    -> else
        -> resolve handler by action
            -> follow_edge
            -> download_artifact
            -> open_artifact
            -> validate_current_content
            -> search_with_text
            -> mark_exhausted
```

## Interpretation

The updater has logic based on:

* outcome status,
* and action type.

That cleanly separates failure cases from success cases.

---

# 10. `_EdgeContext`

## Role

It is a small internal wrapper that encapsulates:

* `edge`
* `parent_node`

And exposes convenient properties such as:

* `edge_id`
* `from_node_id`
* `label`
* `target_url`

## What it is for

It avoids repeating edge and parent-node resolution in every handler.

## Meaning

It is a helper structure that stabilizes the reading of edge-based mutations.

---

# 11. Edge-context resolution

## `_resolve_edge_context(...)`

### Role

Resolve the real edge and associated parent node from `action_result`.

### What it does

1. Reads `edge_id`.
2. Looks up the edge in the graph.
3. Looks up the parent node using `edge.from_node_id`.
4. Returns `_EdgeContext`.

### Interpretation

This confirms again that the updater does not operate on “abstract intentions,” but on real graph entities.

---

# 12. Edge marking

## `_mark_edge_useful(...)`

Marks:

* `edge.status = "useful"`
* adds the edge as explored in the parent node
* adds the edge as useful in the parent node

## `_mark_edge_failed(...)`

Marks:

* failed attempt on the edge
* parent node as partially exhausted or exhausted depending on remaining pending work
* scope progress

## Meaning

Operational outcomes directly affect the structural semantics of both the edge and the parent node.

This is an essential part of the graph’s local learning behavior.

---

# 13. Failure handling

## `_apply_failed_action_result(...)`

### Role

Interpret a failed `action_result`.

### What it does

1. Resolves edge context.
2. Marks the edge as failed.
3. Updates `working_memory.local_summary` of the parent node.
4. Increments `revision_count`.
5. Registers logs.
6. Marks `last_progress_step`.

### Interpretation

A failure is not lost as a simple log. It is internalized as local memory in the node and edge.

That avoids pointless retries and preserves useful tactical context.

---

# 14. Findings integration

## `_try_extract_and_register_finding(...)`

### Role

Extract and register a finding from:

* `local_perception`
* `inspection_result`
* `artifact_text`
* `artifact_url`
* `source_action`

### What it does

1. Verifies that `finding_extractor` exists.
2. Verifies that `local_perception` exists.
3. Enriches metadata with `evidence_ref`.
4. Updates `goal_validation_payload_by_node`.
5. Updates `document_validation_state_updater` if present.
6. Builds `FindingRecord` using `finding_extractor.from_open_artifact(...)`.
7. Registers the finding and reevaluates goals.

## `_register_and_match_finding(...)`

### Role

Register the finding in runtime and trigger reevaluation of the goal trace and reprioritization of choice points.

### Meaning

The updater does not just move nodes and edges; it also connects execution to the goal system.

That is very important.

The operational outcome can become formal goal progress.

---

# 15. `finding_extractor.py`

## Role of the file

Convert operational evidence or local perception into `FindingRecord`.

## Main functions

* `from_open_artifact(...)`
* `from_download_artifact(...)`
* `from_navigation_perception_current_node(...)`

## What it models

A finding contains:

* kind
* label
* value
* confidence
* evidence
* attributes such as:

  * artifact_url
  * document_family
  * year
  * validation_status
  * matched_condition_ids
  * perception summary

## Meaning

The finding extractor is the hinge between:

* execution and runtime evidence,
* and the goal system.

---

# 16. `_apply_follow_edge(...)`

## Role

Update runtime and graph when `follow_edge` succeeded.

## Internal flow

1. Resolves `_EdgeContext`.
2. Reads `inspection_result`.
3. Resolves child-node URL and title.
4. Creates or ensures the child node in the graph.
5. Links `child_node_id` to the edge.
6. Stores `inspection_result_by_node`.
7. Updates `current_content_owner_node_id`.
8. Marks the edge as useful.
9. Marks the parent node as expanded.
10. Creates an `ArrivalContext`.
11. Registers the arrival.
12. Changes `runtime.current_node_id`.
13. Registers the child-node visit.
14. Updates `working_memory.local_summary` of the parent node.
15. Updates scope and `active_path`.
16. If `local_perception` exists, attempts to extract findings.

## Meaning

This is the handler that converts a successful observation into:

* a new active node,
* a new agent position,
* new arrival semantics,
* and a possible new finding.

It is one of the most structural handlers in the entire updater.

---

# 17. `_create_arrival(...)`

## Role

Build `ArrivalContext` for the child node.

## What it models

* `from_node_id`
* `via_edge_id`
* `arrival_depth`
* `arrival_mode`
* `parent_scope_id`
* `discovery_reason`
* `is_reentry`
* `step_index`

## Meaning

This makes arrival at a node more than a simple `current_node_id` change. It becomes a structured navigation event.

---

# 18. `_apply_download_artifact(...)`

## Role

Update runtime and owner-node memory when `download_artifact` succeeded.

## Internal flow

1. Resolves `_EdgeContext`.
2. Resolves the owner node with `_resolve_content_owner_node(...)`.
3. Reads `download_result`.
4. Computes `artifact_url`.
5. Updates `download_result_by_node`.
6. Clears `artifact_result_by_node` on the owner.
7. Updates `current_content_owner_node_id`.
8. Marks the edge as useful.
9. Adds the artifact URL to the owner.
10. Updates `working_memory.local_summary`.
11. Registers scope progress.
12. If `local_perception` exists, registers an enriched finding.
13. If `local_perception` does not exist, attempts to extract a simple download finding.

## Meaning

A download does not necessarily move the agent to another node, but it does strongly change the local evidence associated with the owner node.

---

# 19. `_apply_open_artifact(...)`

## Role

Update runtime and memory when an artifact was opened.

## Internal flow

1. Resolves `_EdgeContext`.
2. Resolves the owner node.
3. Reads `download_result` and `artifact_result`.
4. Computes `artifact_url`.
5. Updates `download_result_by_node`.
6. Updates `artifact_result_by_node`.
7. Updates `current_content_owner_node_id`.
8. Marks the edge as useful.
9. Registers the artifact URL in the owner node.
10. Extracts artifact text if available.
11. Updates `working_memory.local_summary` with detected text or absence of text.
12. Registers scope progress.
13. If `local_perception` exists, attempts to extract an enriched finding.
14. If not, attempts to extract a simple finding from the opened artifact.

## Meaning

Opening an artifact transforms the owner node into a carrier of richer evidence than a simple download.

---

# 20. `_apply_mark_exhausted(...)`

## Role

Mark the current node as exhausted.

## What it does

1. Gets the active scope.
2. Gets the current node.
3. Marks the node as exhausted.
4. Registers scope progress.
5. If there is an `active_path`, closes the suffix from the tip.

## Meaning

This is not just a label. It is a structural signal that this branch or point in the graph should no longer be explored as an immediately useful source.

---

# 21. `_apply_validate_current_content(...)`

## Role

Update caches, validation state, and findings when `validate_current_content` produced a result.

## Internal flow

1. Resolves `target_node_id` from `validation_target`, `current_content_owner_node_id`, or `current_node_id`.
2. Gets the target node.
3. Reads `inspection_result`, `download_result`, and `artifact_result`.
4. Resolves `local_perception` according to `source_kind`.
5. Updates caches with `_update_validation_caches(...)`.
6. Registers scope progress.
7. Updates the node’s `working_memory.local_summary`.
8. If `finding_extractor` and `local_perception` exist, attempts to build and register a finding.

## Meaning

Local validation does not just produce a payload; it also modifies node memory and updates the formal validation layer of the runtime.

---

# 22. `_update_validation_caches(...)`

## Role

Synchronize runtime caches with validation results.

## What it does

* updates `inspection_result_by_node`
* updates `download_result_by_node`
* updates `artifact_result_by_node`
* updates `current_content_owner_node_id`
* registers `goal_validation_payload_by_node`
* invokes `document_validation_state_updater` if present

## Meaning

This function ensures that local validation is reflected in the live memory of the runtime, not only as an ephemeral executor result.

---

# 23. `_apply_search_with_text(...)`

## Role

Update the runtime when `search_with_text` either did or did not produce a real delta.

## Core idea

This handler has very important logic:

> not every search should mutate the node or the state.

## Internal flow

### Case 1: there is no real delta

1. Checks `_search_result_has_real_delta(...)`.
2. If there is no delta:

   * registers the query if appropriate,
   * updates `working_memory.local_summary` of the current node,
   * registers `search_with_text_noop` scope progress if appropriate,
   * and **does not mutate** the node as if new valid results existed.

### Case 2: there is a real delta

1. Stores `inspection_result_by_node[target_id]`.
2. Stores `search_result_by_node[target_id]`.
3. Marks a frozen DOM snapshot.
4. Registers the query.
5. Changes `current_node_id`.
6. Changes `current_content_owner_node_id`.
7. Clears navigation-perception and refine caches of the target node.
8. May create a new node or reuse the current one according to `_search_should_create_new_node(...)`.
9. May create a new arrival.
10. May extend `active_path`.
11. Updates `working_memory.local_summary` of the target node.
12. Registers scope progress.

## Meaning

This handler treats search as a possible mutation of local state, but only if it truly produced a new useful cognitive scene.

That is a very good design decision.

---

# 24. `_search_should_create_new_node_static(...)`

## Role

Decide whether a search result deserves a new node or should reuse the current one.

## Criteria

* `state_delta_kind == navigation`
* `state_delta_kind == dom_mutation`
* URL change
* inspection-signature change

## Meaning

This shows that search can be modeled in two ways:

* as a local mutation of the current node,
* or as a new effective position inside the graph.

That subtlety is architecturally valuable.

---

# 25. `_search_result_has_real_delta(...)`

## Role

Determine whether the search really changed the observable state.

## What it checks

* `status`
* `state_delta_kind`
* `results_detected`
* comparison between current URL and new URL
* real presence of candidates
* absence of strong metadata

## Meaning

This prevents failed or ineffective searches from contaminating the runtime as if they were progress.

---

# 26. `_resolve_content_owner_node(...)`

## Role

Resolve which node is the logical owner of the current content or artifact.

## Policy

It prioritizes:

* `current_content_owner_node_id`
* then `current_node_id`
* and if neither is valid, uses a fallback

## Meaning

This function is key to separating:

* the node where the agent is navigating,
* and the node that owns the current content.

Those are not always exactly the same.

---

# 27. `_resolve_validation_local_perception(...)`

## Role

Resolve from which carrier to take `local_perception` for a current validation.

## Policy

It prioritizes according to `source_kind`:

* `artifact`
* `download`
* `inspection`

And if `source_kind` is unclear, it tries a fallback.

## Meaning

This stabilizes the relationship between:

* validation target,
* evidence carrier,
* and local-perception payload.

---

# 28. `_extract_artifact_text(...)`

## Role

Extract useful text from `artifact_result`.

## What it checks

* direct keys such as `text`, `content_text`, `extracted_text`, `markdown_text`
* or partial pages up to a controlled maximum

## Meaning

This allows findings and local memory to capture useful text without depending on a single artifact-opener output convention.

---

# 29. Relationship with `GraphMapperState`

The updater does not depend on the full concrete class, but it does mutate central parts of the runtime.

## Fields and structures it touches

Among other things:

* `current_node_id`
* `current_content_owner_node_id`
* `inspection_result_by_node`
* `download_result_by_node`
* `artifact_result_by_node`
* `search_result_by_node`
* `goal_validation_payload_by_node`
* `goal_validation_state_by_node`
* `navigation_perception_*`
* `active_path`
* arrivals
* choice-point reprioritization
* findings

## Interpretation

The updater is one of the layers that most deeply modifies the live memory of the system.

---

# 30. Relationship with `GraphMemory`

## What it mutates in the graph

* edges: useful / failed / child_node_id / attempts
* parent nodes: explored edges, useful edges, exhaustion, expansion, working memory
* child nodes: creation or ensure, visits, artifact URLs

## Meaning

The updater converts operational outcome into navigable structure and persistent local memory inside the graph.

---

# 31. Relationship with the goal system

The updater does not just move nodes.

It also:

* registers findings,
* updates validation payloads,
* triggers goal reevaluation,
* and reprioritizes choice points.

## Meaning

That directly connects:

* execution outcome
* with goal progress

The updater is a key grounding layer between evidence and the active goal.

---

# 32. What goes into the updater

In functional terms, three things go in.

## 1. `action_result`

Operational result produced by the executor.

## 2. `runtime`

Live memory of the system, exposed through `RuntimeUpdaterPort`.

## 3. Optional dependencies

* `finding_extractor`
* `document_validation_state_updater`

---

# 33. What comes out of the updater

No large contract comes out.

The real output is:

* mutated runtime
* mutated graph
* registered findings
* updated validation
* updated path
* updated current node or content owner

## Correct formula

```text
Action result
    -> updater
    -> mutated runtime
```

---

# 34. Risks and subtle details

## 1. This is one of the layers with the most internal side effects

It touches many parts of the runtime at once.

That makes it powerful, but also delicate.

## 2. Search has especially subtle logic

It may:

* mutate nothing,
* mutate the current node,
* or create a new node.

That must always remain well documented.

## 3. `current_content_owner_node_id` is not trivial

It does not always match `current_node_id`.

If that is misunderstood, artifacts and validation may end up attached to the wrong node.

## 4. Findings and validation are deeply coupled

Changes in local perception or validation payload directly affect the goal system.

## 5. The updater depends on runtime contracts, not concrete types

That provides flexibility, but it requires the protocols in `runtime_views.py` to be kept in good shape.

---

# 35. How to maintain or extend this layer

## If you add a new action

You must review:

* `_action_handlers()`
* the new `_apply_*` handler
* which caches it touches
* whether it produces findings
* whether it alters validation
* whether it should change path, scope, or current node

## If you change search

You must review:

* `_apply_search_with_text(...)`
* `_search_result_has_real_delta(...)`
* `_search_should_create_new_node_static(...)`

## If you change validation

You must review:

* `_apply_validate_current_content(...)`
* `_update_validation_caches(...)`
* `_resolve_validation_local_perception(...)`
* `document_validation_state_updater`

## If you change findings

You must review:

* `finding_extractor.py`
* `_try_extract_and_register_finding(...)`
* `_try_extract_download_finding(...)`
* `_register_and_match_finding(...)`

## General rule

Do not mix external IO into the updater. That is not its role.

---

# 36. How to read this layer as a human

Recommended order:

1. `runtime_views.py`
2. `graph_updater.py`
3. `finding_extractor.py`
4. specific handlers:

   * `_apply_follow_edge`
   * `_apply_download_artifact`
   * `_apply_open_artifact`
   * `_apply_validate_current_content`
   * `_apply_search_with_text`
   * `_apply_mark_exhausted`

That helps you understand, in order:

* the runtime contract,
* then the updater façade,
* then the main mutation paths,
* and finally the integration with findings and goals.

---

# 37. How to read this layer as an AI agent

## Objective

Understand how an operational result is internalized as the agent’s structural memory.

## Procedure

### Step 1

Read `RuntimeUpdaterPort` in `runtime_views.py`.

### Step 2

Read `apply_action_result(...)` as the central dispatcher.

### Step 3

Separate:

* failed path
* follow edge
* download
* open artifact
* validate current content
* search
* mark exhausted

### Step 4

Observe which runtime fields each handler touches.

### Step 5

Observe when findings are registered and when validation is updated.

### Step 6

Observe when `current_node_id` changes and when only `current_content_owner_node_id` changes.

### Step 7

Relate goal-trace reevaluation to registered findings.

---

# 38. Executive summary

The updater sublayer of `graph_mapper_agent` converts operational results into live structural memory.

Its central piece is `GraphUpdater`, which receives `action_result` and mutates the runtime and graph according to the action type and result status. The main handlers cover `follow_edge`, `download_artifact`, `open_artifact`, `validate_current_content`, `search_with_text`, and `mark_exhausted`, plus a special failure path.

The updater does not perform external IO. Its job is different: create arrivals, move the current node, update per-node caches, mark edges as useful or failed, modify local working memory, update content ownership, register findings, update validation payloads, reevaluate goals, and reprioritize choice points.

`runtime_views.py` makes explicit that this layer does not depend on the full concrete runtime, but on minimal contracts such as `RuntimeUpdaterPort`. `finding_extractor.py` complements this sublayer by turning artifacts, downloads, and local perception into `FindingRecord`, which directly connects operational result with the goal system.

The key conceptual idea is this:

> the updater does not obtain new evidence from the world; it transforms evidence already obtained into internal structure, tactical memory, and formal progress for the agent.

That separation between:

* decision,
* execution,
* and internal mutation,

is one of the strongest foundations of this architecture.

---

# 39. Ultra-short summary

## What the updater is

The layer that internalizes `action_result` into the graph and runtime.

## What it does

* moves current node
* updates per-node caches
* registers arrivals
* marks edges useful or failed
* updates working memory
* registers findings
* updates validation
* reprioritizes choice points

## What it does not do

It does not call tooling or perform external IO.

## Final formula

```text
ActionExecutionResult
    -> GraphUpdater
    -> mutated graph + mutated runtime
```
