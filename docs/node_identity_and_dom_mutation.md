# Node Identity and DOM Mutation

## Purpose

This document explains one of the most delicate parts of the `graph_mapper_agent` architecture:

- what a node actually is
- how URL participates in node identity
- how DOM observation participates in node identity
- how agent actions can mutate a node's operational state
- when the runtime reuses a node and when it materializes a new one
- why this area is only partially modeled today

The goal is to avoid two incomplete readings:

1. a node is just a URL
2. a node is just the current DOM

Neither is sufficient on its own.

---

## Core Claim

A node is best understood as a **graph-level navigable identity**, stabilized primarily by canonical URL, but enriched and sometimes reinterpreted through DOM observation and runtime mutation.

In practical terms:

- the URL provides structural continuity
- the DOM provides local evidence
- the runtime decides how that evidence mutates the node's operational state

This means a node has:

- a relatively stable structural side
- a mutable operational side

---

## 1. URL as Structural Identity

The strongest current anchor of node identity is the canonical URL.

This is visible in the graph model:

- [`GraphMemory.get_node_by_url(...)`](../graph_mapper_agent/domain/graph.py)
- [`GraphMemory.ensure_node(...)`](../graph_mapper_agent/domain/graph.py)

`ensure_node(...)` looks up an existing node by `canonical_url` and reuses it if found. If none exists, it creates a new `GraphNodeState`.

So, today, the runtime effectively answers the question:

> "Is this the same structural place in the graph?"

mostly by asking:

> "Does this canonical URL already exist?"

That makes URL the main structural identity anchor.

### Relevant Code

- `graph_mapper_agent/domain/graph.py`
  - `GraphMemory.url_to_node_id`
  - `GraphMemory.get_node_by_url(...)`
  - `GraphMemory.ensure_node(...)`

---

## 2. The DOM Does Not Directly Create Nodes

The DOM is not treated as a node by itself. It is treated as an **observation source**.

The observation flow starts here:

- [`get_observation_for_current_node(...)`](../graph_mapper_agent/runtime/nodes/observation.py)
- [`resolve_node_observation(...)`](../graph_mapper_agent/runtime/nodes/inspect_helpers.py)

The browser tooling returns observation data such as:

- `page_url`
- `final_url`
- `title`
- `content`
- `text_excerpt`
- `candidates`
- `search_targets`
- `metadata`
- `frame_summaries`

That is already meaningful state, but it is still an **observation of the current node**, not a new node materialization.

### Relevant Code

- `graph_mapper_agent/runtime/nodes/observation.py`
  - `get_observation_for_current_node(...)`
- `graph_mapper_agent/runtime/nodes/inspect_helpers.py`
  - `resolve_node_observation(...)`
- `graph_mapper_agent/adapters/web_browser/inspection.py`
  - inspection result assembly

---

## 3. DOM Candidates Become Edges Before They Become Nodes

After inspection, raw candidates from the DOM are converted into `ObservedCandidate` objects:

- [`build_observed_candidate(...)`](../graph_mapper_agent/runtime/nodes/observation.py)

Those candidates are then merged into the graph as edges:

- [`merge_observed_candidates(...)`](../graph_mapper_agent/runtime/nodes/inspect_helpers.py)
- [`ObservedCandidateMergePolicy.merge(...)`](../graph_mapper_agent/domain/graph_merge.py)

This matters because the first stable graph-level entity produced from DOM observation is usually an **edge**, not a new node.

That means the architecture distinguishes between:

- current-page observation
- outgoing possibilities discovered on that page
- actual node materialization after traversal or strong state change

### Relevant Code

- `graph_mapper_agent/runtime/nodes/observation.py`
  - `build_observed_candidate(...)`
- `graph_mapper_agent/runtime/nodes/inspect_helpers.py`
  - `merge_observed_candidates(...)`
- `graph_mapper_agent/domain/graph_merge.py`
  - `ObservedCandidateMergePolicy`
  - `_find_existing_edge(...)`
  - `_build_edge(...)`
  - `_enrich_edge(...)`

---

## 4. The Simple Case: `follow_edge`

The cleanest node materialization path is `follow_edge`.

Execution inspects the target:

- [`inspect_edge(...)`](../graph_mapper_agent/application/services/execution/edge_actions.py)

Then the updater resolves the target into a child node:

- [`GraphUpdater._apply_follow_edge(...)`](../graph_mapper_agent/application/services/graph_updater.py)

There, the system:

1. reads `inspection_result`
2. resolves `page_url` or falls back to the edge target URL
3. derives a title
4. calls `runtime.graph.ensure_node(...)`
5. links `edge.child_node_id`
6. stores inspection results under the child node
7. registers arrival
8. updates `current_node_id`
9. appends to the active path

This is the most intuitive identity path:

- navigate to a place
- observe that place
- reuse or create a node for that place

### Relevant Code

- `graph_mapper_agent/application/services/execution/edge_actions.py`
  - `inspect_edge(...)`
- `graph_mapper_agent/application/services/graph_updater.py`
  - `_apply_follow_edge(...)`
  - `_create_arrival(...)`
- `graph_mapper_agent/domain/graph.py`
  - `ensure_node(...)`

---

## 5. The Hard Case: `search_with_text`

`search_with_text` is where node identity becomes much less trivial.

Unlike `follow_edge`, local search may:

- stay on the same URL
- mutate the DOM significantly
- reveal new candidates
- change the tactical meaning of the current location
- or effectively navigate within the same broader page context

This raises the architectural question:

> if search changes the visible state of the page, is it still the same node?

The current runtime answer is:

> sometimes yes, sometimes no

And it decides using heuristics.

### Relevant Code

- `graph_mapper_agent/application/services/execution/search.py`
  - `search_with_text(...)`
- `graph_mapper_agent/adapters/web_browser/search.py`
  - browser-level search execution and search metadata assembly
- `graph_mapper_agent/application/services/graph_updater.py`
  - `_apply_search_with_text(...)`
  - `_search_should_create_new_node(...)`
  - `_search_should_create_new_node_static(...)`
  - `_search_result_has_real_delta(...)`

---

## 6. What `search_with_text` Actually Does Today

After a search action returns, the updater first checks whether the search produced a real delta.

If there is no real change, the runtime does **not** reinterpret the same state as a new node. Instead it:

- records the query
- writes working memory notes
- marks the search as a no-op or failed state change
- leaves node identity untouched

That logic is visible in:

- [`_search_result_has_real_delta(...)`](../graph_mapper_agent/application/services/graph_updater.py)
- [`GraphUpdater._apply_search_with_text(...)`](../graph_mapper_agent/application/services/graph_updater.py)

If there is a real delta, the runtime computes whether the search should create a new node.

The current heuristic creates a new node when:

- `state_delta_kind == "navigation"`
- `state_delta_kind == "dom_mutation"`
- the URL changes
- or the inspection signature changes significantly

If not, the current node is reused.

### Relevant Code

- `graph_mapper_agent/application/services/graph_updater.py`
  - `_search_result_has_real_delta(...)`
  - `_inspection_signature(...)`
  - `_search_should_create_new_node_static(...)`
  - `_apply_search_with_text(...)`

---

## 7. Why This Matters

This shows that a node is not fully static in the runtime model.

The system already recognizes that agent actions can mutate the current situation enough to justify:

- keeping the same node
- or materializing a new one

That is especially clear in `search_with_text`, where the same general place can produce a different tactical surface after a search interaction.

So the correct reading is not:

> a node is fixed forever

but rather:

> a node has structural continuity, but its operational state can mutate, and some mutations are strong enough to justify a new node materialization

---

## 8. Structural Identity vs Operational State

This distinction is the most useful way to think about the current architecture.

### Structural Identity

This answers:

- what place in the graph is this?
- what gives this location continuity across the run?

Today this is mostly anchored by:

- canonical URL
- graph registration
- arrivals and path integration

### Operational State

This answers:

- what is visible here right now?
- what candidates are available?
- what search results are present?
- what local validation or perception has already been computed?
- what did the last action reveal or change?

This state is carried across:

- `inspection_result_by_node`
- `search_result_by_node`
- `goal_validation_payload_by_node`
- `navigation_perception_by_node`
- node working memory
- `NodeView`

This is why the node should not be reduced either to URL or to DOM.

---

## 9. The Current Modeling Limitation

The runtime already acknowledges node mutation, but only partially models it.

### What Is Already Modeled

The system already has practical machinery for:

- freezing observation snapshots
- storing search results by node
- invalidating and rebuilding perception after search
- deciding whether to reuse or create a node
- updating path and arrivals after search-derived transitions

### What Is Not Yet Explicitly Modeled

The system still lacks an explicit concept of:

- node version
- node state transition
- DOM mutation identity semantics
- a formal materialization reason model

Right now, these decisions are implemented as runtime heuristics rather than as a first-class state transition model.

This is not a bug in itself, but it is a real architectural limitation worth documenting.

---

## 10. The Best Current Definition

The best current definition of a node in this system is:

> A node is a graph-level navigable identity, stabilized primarily by canonical URL, but enriched and sometimes reinterpreted through DOM observation and action-induced state mutation.

Or more compactly:

> A node is a structurally anchored location with mutable operational state.

---

## 11. Relation to `NodeView`

`NodeView` does not solve structural identity.

Instead, `NodeView` solves a different problem:

> how to collapse the current state of the node into a local tactical decision surface

So:

- the graph stores structural memory
- the runtime stores mutable operational state
- `NodeView` exposes the current local decision surface

This is why DOM mutation matters so much operationally, even when node identity remains structurally continuous.

### Relevant Code

- `graph_mapper_agent/application/services/node_view_builder.py`
- `graph_mapper_agent/runtime/nodes/build_view_helpers.py`
- `graph_mapper_agent/domain/view.py`

---

## 12. Practical Reading for the Current System

If you want the most accurate practical reading of the current implementation, it is this:

1. URL is the main anchor of structural identity.
2. DOM observation does not directly create nodes; it creates evidence and candidates.
3. Candidates first become edges.
4. Nodes are materialized or reused when navigation or strong state mutation justifies it.
5. `search_with_text` is the main place where node identity becomes fluid.
6. The runtime already handles this with heuristics.
7. The underlying theory of node identity versus node mutation is still incomplete.

---

## 13. Future Direction

A cleaner future model would likely separate:

- node identity
- node operational state
- node transitions
- node materialization policy

That would make the current implicit heuristics explicit and easier to reason about.

Until then, the correct way to understand the current system is:

> node identity is mostly URL-anchored, but node state is mutable, and some local mutations are already treated as sufficient to create a new node.
