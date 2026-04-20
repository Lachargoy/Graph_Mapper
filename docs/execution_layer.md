# Graph Mapper Execution Layer Reference Manual

## Purpose

This manual documents the **execution** sublayer of `graph_mapper_agent`, with a focus on how a decision that has already been accepted by the runtime is converted into a structured operational result.

The goal is to explain:

* what the executor is,
* which files compose this sublayer,
* what goes in,
* what comes out,
* how it relates to the decider, the runtime, the graph, and the updater,
* and why this layer does not mutate the graph directly, but instead produces an `ActionExecutionResult` that is later absorbed by another layer.

---

# 1. Core idea

The most correct way to understand this layer is this:

```text
a decision already accepted by the runtime
    -> GraphMapperActionExecutor.execute(...)
    -> specialized execution path
    -> ActionExecutionResult
    -> GraphMapperNodes.execute_action(...)
    -> _action_result
    -> GraphUpdater.apply_action_result(...)
```

## Correct mental formula

The executor **does not decide**.

The executor **executes**.

But it also does not mutate the graph directly.

Its actual responsibility is:

> translate an already validated operational decision into a structured operational result.

That structured result is represented as:

**`ActionExecutionResult`**

That is the central piece of this sublayer.

---

# 2. Position in the architecture

## Layer

`application/services/execution`

## Architectural role

This sublayer sits between:

* the **decision layer**,
* and the **graph and runtime mutation layer**.

In other words:

* the decider says what it wants to do,
* the executor attempts to do it,
* the updater internalizes what actually happened.

## Relationship to the main lane

Inside the lane flow:

```text
build_node_view
 -> decide_action
 -> execute_action
 -> update_graph
```

The execution sublayer lives entirely inside:

**`execute_action`**

but not as one flat function. It is a family of specialized modules.

---

# 3. What problem the executor solves

Without this sublayer, `GraphMapperNodes.execute_action(...)` would have to directly handle:

* opening artifacts,
* downloading documents,
* inspecting pages,
* executing searches,
* validating local evidence,
* reusing snapshots,
* deciding how to treat different carriers,
* building homogeneous results,
* and managing IO errors.

That would create too much coupling inside the nodes file.

The execution sublayer solves that by separating:

* **lane orchestration** (`GraphMapperNodes`)
* from **real operational execution** (`GraphMapperActionExecutor` + helpers)

---

# 4. Main pieces of the sublayer

## 1. `action_executor.py`

Main execution façade.

## 2. `contracts.py`

Canonical output contract: `ActionExecutionResult`.

## 3. `edge_actions.py`

Real execution of edge-based actions:

* `follow_edge`
* `download_artifact`
* `open_artifact`
* derived inspection

## 4. `search.py`

Execution of `search_with_text`.

## 5. `validation.py`

Execution of `validate_current_content`.

## 6. `artifact.py`

Hooks for local validation and perception over artifacts and terminal inspection content, including optional auto-persistence.

---

# 5. Central contract: `ActionExecutionResult`

## Role

`ActionExecutionResult` is the unifying output contract of the entire sublayer.

It does not matter whether the action was:

* terminal,
* search,
* validation,
* inspection,
* download,
* or artifact opening,

the result is always expressed through the same structure.

## Fields

It includes:

* `action`
* `status`
* `edge_id`
* `child_node_id`
* `inspection_result`
* `download_result`
* `artifact_result`
* `local_perception_result`
* `search_target_id`
* `query_text`
* `reason`

## Interpretation

This structure does not represent the graph or the final runtime state.

It represents:

> the immediate operational outcome of an action.

That makes it possible to cleanly decouple:

* execution,
* from internal state mutation.

---

# 6. `GraphMapperActionExecutor`

## File

`application/services/execution/action_executor.py`

## Role of the file

It is the **main execution façade**.

It centralizes action dispatch and builds specialized contexts for execution submodules.

## Main responsibility

Receive:

* `runtime`
* `decision: dict[str, object]`

And return:

* `ActionExecutionResult`

## What goes in

The central function is:

```text
execute(runtime, decision)
```

The expected decision already comes reasonably normalized from the decision sublayer.

## What comes out

It always returns `ActionExecutionResult`.

## What it depends on

It depends on:

* `NavigationActionsPort`
* `LocalPerceptionService`
* `edge_actions.py`
* `search.py`
* `validation.py`
* the runtime graph to resolve `edge_id`

## Who uses it

It is used by `GraphMapperNodes.execute_action(...)`.

---

# 7. Internal flow of `GraphMapperActionExecutor.execute(...)`

## General dispatch

The real flow can be read like this:

```text
read action from decision
    -> mark_exhausted -> immediate ok result
    -> success -> immediate ok result
    -> fail -> immediate ok result
    -> validate_current_content -> validation.py
    -> search_with_text -> search.py
    -> edge-based actions require edge_id
        -> resolve edge in graph
        -> follow_edge -> edge_actions.follow_edge_with_probe(...)
        -> download_artifact -> edge_actions.download_artifact_for_edge(...)
        -> open_artifact -> edge_actions.open_artifact_for_edge(...)
```

## Interpretation

The executor has a very clear policy:

* terminal actions do not perform real IO,
* specialized actions delegate to dedicated modules,
* edge-based actions must first resolve a real edge in the graph.

That protects execution from invented or inconsistent references.

---

# 8. Execution contexts

The executor builds three specialized contexts.

## 1. `ExecutionContext`

Used by `edge_actions.py`.

Includes:

* `navigation_actions`
* `jurisdiction_code`
* `document_key`
* `timeout_seconds`
* `storage_namespace`
* `session_id`
* `run_id`
* `capture_screenshot_for_observations`
* `local_perception_service`
* `allow_artifact_download`
* `artifact_persistence_mode`

### Meaning

This is the general operational context for navigation, artifacts, and local perception.

## 2. `ValidationExecutionContext`

Used by `validation.py`.

Includes:

* `navigation_actions`
* `jurisdiction_code`
* `document_key`
* `timeout_seconds`
* `local_perception_service`

### Meaning

This is a smaller context focused on validating local evidence.

## 3. `SearchExecutionContext`

Used by `search.py`.

Includes:

* `navigation_actions`
* `jurisdiction_code`
* `document_key`
* `timeout_seconds`
* `include_screenshot`

### Meaning

This is the specialized context for local searches over a visible target on the current node.

---

# 9. Terminal actions

## Actions

* `mark_exhausted`
* `success`
* `fail`

## What they do

These actions do not execute tooling or external IO.

They simply return an `ActionExecutionResult` with:

* `status="ok"`
* an appropriate `reason`
* no `edge_id`

## Interpretation

These actions are lane-control outcomes, not navigation or evidence-acquisition actions.

That is why the executor treats them as immediate results.

---

# 10. Edge-based execution

## General role

The edge-based actions are:

* `follow_edge`
* `download_artifact`
* `open_artifact`

All of them require:

1. an `edge_id`
2. resolution of the real edge in the graph

If the edge does not exist, the executor fails with an error.

## Interpretation

This makes it explicit that the executor does not operate on “imagined links” or on loose URLs invented by the LLM.

It operates on edges that already exist in the structured memory of the runtime.

---

# 11. `edge_actions.py`

## Role of the file

This file implements the real execution of edge-based actions.

## Main responsibility

Take:

* an `EdgeState`
* an `ExecutionContext`
* the `runtime`

And return an `ActionExecutionResult`.

## Main functions

* `inspect_edge(...)`
* `download_artifact_for_edge(...)`
* `open_artifact_for_edge(...)`
* `follow_edge_with_probe(...)`

---

# 12. `inspect_edge(...)`

## Role

Inspect the target resource of the edge as a navigable page or observation.

## Internal flow

1. Resolve the target URL.
2. Attempt to find an existing node by URL.
3. If it exists, try to reuse an observation snapshot.
4. If no snapshot exists, call `inspect_page(...)` through `NavigationActionsPort`.
5. It may run local validation over the inspected content.
6. It may trigger auto-persistence of a validated artifact.
7. It returns `ActionExecutionResult` with `inspection_result`.

## Meaning

`inspect_edge(...)` is the way to convert a navigable target into rich observation that the runtime can use.

## Important detail

This is already a place where inspection and local validation may be coupled in a single step.

Execution is not “just fetch HTML”; it may also produce formal local perception.

---

# 13. `download_artifact_for_edge(...)`

## Role

Download an artifact associated with an edge.

## Internal flow

1. Resolve the target URL.
2. Call `download_artifact(...)` on the navigation port.
3. If an `HTTPError` occurs, build a structured failed `ActionExecutionResult`.
4. If download succeeds, it may attempt local validation over the downloaded artifact.
5. Return `ActionExecutionResult` with `download_result`.

## Meaning

Not every download is automatically useful; that is why the layer may attach a `local_perception_result` that can later support evaluation or validation.

---

# 14. `open_artifact_for_edge(...)`

## Role

Open an artifact locally, usually after downloading it.

## Internal flow

1. Resolve the target URL.
2. Check `runtime.last_download_result`.
3. If the last download matches the current edge, reuse it.
4. If not, download again.
5. Call `open_artifact(...)` on the navigation port.
6. Attempt local validation of the opened artifact.
7. Return `ActionExecutionResult` with:

   * `download_result`
   * `artifact_result`
   * optional `local_perception_result`

## Meaning

Opening an artifact is not just local IO. It may also be the point where the content becomes explicit enough to validate or extract formal evidence.

---

# 15. `follow_edge_with_probe(...)`

## Role

Follow an edge with prior resolution of the resource type.

## Internal flow

1. Resolve the target URL.
2. Execute `probe_content(...)`.
3. Interpret `resource_kind`, `content_type`, and `final_url`.
4. If it detects a PDF and policy allows it, internally redirect to download.
5. If it detects HTML, redirect to inspection.
6. If the probe is ambiguous, return an `uncertain` result with a synthetic `inspection_result`.

## Core idea

`follow_edge` does not mean “always open an HTML page.”

It means:

> resolve what that edge actually represents and act according to the detected carrier.

## Why this matters

That resolution prevents the system from treating PDFs, HTML pages, and ambiguous resources as if they were exactly the same thing.

---

# 16. `search.py`

## Role of the file

Implement `search_with_text`.

## Main responsibility

Execute a localized textual search on the current node using a visible `search_target_id`.

## Internal flow

1. Validate `search_target_id`.
2. Validate `query_text`.
3. Validate `runtime.current_node_id`.
4. Resolve the current node.
5. Call `search_with_text(...)` through `NavigationActionsPort`.
6. Analyze the outcome using `_resolve_search_outcome(...)`.
7. Return `ActionExecutionResult` with `inspection_result=raw`.

## Why `inspection_result`

Because the result of a search is modeled as a new observation of local state, not as an entirely separate entity.

That makes it easier for the runtime to later treat it similarly to node inspection.

## `_resolve_search_outcome(...)`

This function distinguishes between:

* useful search,
* silent no-op,
* nonexistent target,
* lack of real delta,
* same page without meaningful change.

## Meaning

The execution sublayer does not automatically assume that every search produced real progress.

That improves robustness.

---

# 17. `validation.py`

## Role of the file

Implement the action `validate_current_content`.

## Core idea

This action **does not navigate to a new node**.

It operates on local evidence already available for a target node.

## Supported carriers

* `inspection`
* `artifact`
* `download`

## General flow

1. Requires `local_perception_service`.
2. Reads `validation_target` from the decision.
3. Extracts `node_id` and `source_kind`.
4. Resolves the target node in the runtime.
5. Depending on `source_kind`, looks for the appropriate frozen evidence:

   * `inspection_result_by_node`
   * `artifact_result_by_node`
   * `download_result_by_node`
6. Executes local perception or validation.
7. Returns an enriched `ActionExecutionResult`.

## Meaning

`validate_current_content` is an action over evidence already possessed by the runtime, not over future possibilities.

That clearly distinguishes it from:

* `follow_edge`
* `download_artifact`
* `open_artifact`
* `search_with_text`

---

# 18. `ensure_validation_observation_with_screenshot(...)`

## Role

Ensure that an inspection observation used for validation includes a screenshot when needed.

## Behavior

* If the node has a frozen DOM snapshot, it does not inspect again.
* If a screenshot already exists, it reuses the existing observation.
* If the screenshot is missing, it calls `inspect_page(...)` with `include_screenshot=True` and merges useful fields.

## Meaning

This avoids aggressive re-reading of the node when evidence is already frozen, while still allowing the observation to be completed when visual signal is missing for validation.

---

# 19. Local validation over current content

## `maybe_validate_current_node_inspection(...)`

Validates inline content from the current node using:

* inline text,
* screenshot,
* metadata,
* and an intent constructed from the current goal.

It uses `LocalPerceptionService` and models the carrier as `inline_document_content`.

## `maybe_validate_current_artifact_result(...)`

Validates an already opened artifact associated with the current node.

## `maybe_validate_current_download(...)`

Validates a downloaded artifact associated with the current node.

## Interpretation

The action `validate_current_content` is designed to exploit carriers already present in the runtime and submit them to formal local validation.

---

# 20. `artifact.py`

## Role of the file

Centralize validation and perception hooks over artifacts and terminal content, as well as optional auto-persistence.

## Main functions

* `maybe_auto_persist_validated_artifact(...)`
* `maybe_validate_opened_artifact(...)`
* `maybe_validate_downloaded_artifact(...)`
* `maybe_validate_inspected_content(...)`

---

# 21. `maybe_validate_inspected_content(...)`

## Role

Attempt validation over inspected page content when that page looks like a terminal document.

## Conditions

It only runs if:

* there is a `local_perception_service`,
* there is content or a screenshot,
* and `inspection_looks_like_terminal_document(...)` allows the content to be treated as terminal evidence.

## Meaning

This avoids validating hubs or listing pages as if they were final documents.

---

# 22. `maybe_validate_downloaded_artifact(...)`

## Role

Attempt local validation over a downloaded artifact.

## Carrier

It uses `ArtifactReference` with `local_path` and `source_url`.

## Meaning

It turns a download into a formally evaluable carrier.

---

# 23. `maybe_validate_opened_artifact(...)`

## Role

Attempt local validation over an opened artifact, allowing use of:

* `local_path`
* `inline_text`
* file metadata

## Meaning

This route is especially useful when opening the artifact produces more evidence than the download alone.

---

# 24. `maybe_auto_persist_validated_artifact(...)`

## Role

Automatically download a direct artifact when positive validation already occurred and policy allows it.

## Requirements

* `allow_artifact_download=True`
* `artifact_persistence_mode == "on_validation"`
* positive validation
* the edge really looks like a direct artifact

## Meaning

This behavior makes the executor more intelligent than simple tooling:

> it not only observes or validates; it can also automatically materialize artifacts that have already been confirmed as valuable.

---

# 25. What goes into the executor

In functional terms, three things enter.

## 1. An already accepted decision

The decision has already passed through:

* the decider,
* the LLM or heuristic pipeline,
* guardrails in `decide_action(...)`

## 2. The runtime

The executor needs runtime in order to:

* resolve edges,
* inspect snapshots,
* reuse the last download,
* locate frozen evidence by node,
* query the graph.

## 3. Services and ports

* `NavigationActionsPort`
* `LocalPerceptionService`

---

# 26. What comes out of the executor

An `ActionExecutionResult` always comes out.

## What matters

That result may contain:

* observation,
* download,
* opened artifact,
* local perception,
* search metadata,
* explanatory reason,
* and status.

But it is still **not** the new runtime state.

It is the raw operational outcome, already structured.

---

# 27. Relationship with `GraphMapperNodes.execute_action(...)`

`GraphMapperNodes.execute_action(...)` acts as the fine-grained step orchestrator of the lane.

## What it does around the executor

1. Takes `runtime.last_decision`.
2. If the action is `refine_navigation_perception`, it uses a special path.
3. Otherwise, it calls `self.action_executor.execute(...)`.
4. Projects result fields into:

   * `runtime.last_inspection_result`
   * `runtime.last_download_result`
   * `runtime.last_artifact_result`
   * `runtime.last_search_result`
5. Builds `_action_result`.
6. Decides `route_hint`.
7. Records evidence in the ledger.

## Conclusion

The executor does not replace `execute_action(...)`; it feeds it.

`GraphMapperNodes.execute_action(...)` remains the lane step, but delegates the real operational work to the executor.

---

# 28. Relationship with the updater

## Golden rule

The executor does not mutate the graph.

## What it does instead

It returns an `ActionExecutionResult`.

Then `GraphMapperNodes.execute_action(...)` translates that into `_action_result`, and later:

```text
update_graph
    -> graph_updater.apply_action_result(runtime, action_result)
```

## Interpretation

The architecture cleanly separates:

* **executor** = side effects / IO / acquisition / validation attachment
* **updater** = internal graph and runtime mutation

That separation is one of the strengths of this layer.

---

# 29. Risks and subtle details

## 1. `follow_edge` is not a single thing

It can end in:

* HTML inspection
* PDF download
* ambiguous result

That should always be made explicit in the documentation.

## 2. Validation is coupled to execution

After inspection, download, or opening, a `local_perception_result` may appear.

That means execution is not “just IO.” It is also a source of local evaluation.

## 3. Snapshot and download reuse

The executor tries to avoid redundant work by reusing:

* prior snapshots
* the last download
* frozen evidence by node

If that logic breaks, the system can become excessively repetitive.

## 4. Part of the behavior depends on policy

* `allow_artifact_download`
* `artifact_persistence_mode`
* presence of `local_perception_service`

That means the executor is partially configured by policy, not only by action.

---

# 30. How to maintain or extend this layer

## If you add a new action

You must review:

* `GraphMapperActionExecutor.execute(...)`
* whether a new context is required
* whether a new execution module is required
* the `ActionExecutionResult` contract
* `GraphMapperNodes.execute_action(...)`
* and probably the updater

## If you change artifacts or validation

You must review:

* `edge_actions.py`
* `validation.py`
* `artifact.py`
* any `LocalPerceptionService` logic

## General rule

Do not put graph mutation inside the executor. That is not its role.

---

# 31. How to read this layer as a human

Recommended order:

1. `contracts.py`
2. `action_executor.py`
3. `edge_actions.py`
4. `search.py`
5. `validation.py`
6. `artifact.py`

That lets you see, in order:

* the output contract,
* the main dispatcher,
* each execution family,
* and finally the validation and perception hooks.

---

# 32. How to read this layer as an AI agent

## Objective

Understand how a decision becomes an operational result before internal state is mutated.

## Procedure

### Step 1

Read `ActionExecutionResult` as the canonical contract.

### Step 2

Read `GraphMapperActionExecutor.execute(...)` as the dispatcher.

### Step 3

Separate four action families:

* terminal
* validation
* search
* edge-based

### Step 4

Read `edge_actions.py` to understand carriers and resource resolution.

### Step 5

Read `validation.py` to understand validation over local evidence already available.

### Step 6

Read `artifact.py` to understand validation over artifact carriers and auto-persistence.

### Step 7

Relate the output to `_action_result` and the updater.

---

# 33. Executive summary

The execution sublayer of `graph_mapper_agent` converts an already accepted decision into a structured operational result.

Its central piece is `GraphMapperActionExecutor`, which distributes execution across terminal actions, local validation, search, and edge-based actions. All paths return the same output contract: `ActionExecutionResult`.

Edge-based actions use `edge_actions.py`, where one edge may resolve into HTML inspection, artifact download, artifact opening, or an ambiguous result after probing. Search actions live in `search.py`, and the action `validate_current_content` lives in `validation.py`, where frozen local evidence from the runtime is validated without navigating to new nodes.

In addition, `artifact.py` allows local perception and formal validation to be attached to inspected content, downloaded artifacts, and opened artifacts, and can even auto-persist a validated artifact when policy allows it.

The key conceptual idea is this:

> the executor does not decide and does not mutate the graph; it executes an intent and produces a structured operational outcome that another layer later internalizes.

That separation between:

* decision,
* execution,
* and state mutation,

is one of the strongest foundations of this architecture.

---

# 34. Ultra-short summary

## What the executor is

The layer that executes an already accepted decision.

## What it returns

`ActionExecutionResult`

## What it does not do

It does not mutate the graph directly.

## What it does do

* inspect
* download
* open artifacts
* execute search
* validate local evidence
* attach local perception

## Final formula

```text
decision
    -> executor
    -> ActionExecutionResult
    -> updater
```
