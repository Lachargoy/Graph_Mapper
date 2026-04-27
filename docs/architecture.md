# Architecture

The project is organized to separate tactical intent, operational execution, and structural memory mutation.

## Main Flow

```text
GraphMapperState
    -> NodeViewBuilder
    -> NodeView
    -> GraphMapperDecider
    -> GraphMapperActionExecutor
    -> ActionExecutionResult
    -> GraphUpdater
    -> mutated GraphMapperState
```

The important idea is that the LLM does not operate directly on the raw runtime or the raw DOM. It operates on a local tactical projection: `NodeView`.

Just as important, the LLM is not expected to understand or reconstruct the full causal story of the exploration. It is not the global memory of the system. Its role is to interpret a structured local state and collapse that state into the best next tactical action.

This is why the system invests so much in explicit runtime state, pathing, anchors, choice points, goal state, and node-local projections. The architecture is designed so that the model does not need to remember every previous thought. It only needs to interpret the current decision surface correctly.

## Three Graph Levels

The graph-oriented design works across three different levels of representation.

### 1. Global Graph Memory

This is the full structural memory of the exploration.

At this level, the system keeps track of:

- discovered nodes and edges
- visits and arrivals
- inspection, download, and artifact results
- findings and validation payloads
- accumulated perception state
- the broader explored space

This level answers the question:

> what does the system know about the explored territory as a whole?

It is not primarily about immediate action. It is about the complete structural memory of the run.

### 2. Branch, Path, Scope, and Anchors

This is the tactical navigation layer that sits between the global graph and the current node.

At this level, the system organizes:

- the active branch
- the active path
- scopes
- choice points
- strategic anchor points
- promising return locations
- trajectories that are more likely to resolve pending goal conditions

This level answers the question:

> within the full graph, from which paths, branches, or anchor points is it most promising to continue?

This layer is what prevents the system from behaving like a flat crawler. It turns the graph into directed exploration.

### 3. Current Node View

This is the local tactical projection of the current situation.

At this level, the system builds `NodeView`, which includes:

- the current node identity
- arrival context
- local candidates
- local node memory
- relevant findings
- local goal validation state
- navigation perception
- restrictions
- search targets
- tactical scratchpad context

This level answers the question:

> given where the agent is right now, what is the best next action?

This is the level the decider, and therefore the LLM-backed decision logic, actually sees.

## Why This Matters

These three levels clarify that the system does not operate on “the graph” in only one sense.

It operates on:

- a full graph memory level
- an intermediate tactical navigation level
- a local decision-surface level

That distinction matters because the model should not be asked to carry the full history of the run as free-form memory. The runtime carries the structural memory. The branching and anchor layer carries the tactical organization of exploration. `NodeView` carries the local decision surface.

In short:

- the graph stores structural memory
- branch/path/anchors organize tactical continuation
- `NodeView` exposes the current local state
- the LLM interprets that local state and collapses it into the next best move

## Main Layers

### 1. State and Runtime

The live agent state includes the graph, active path, scope, choice points, perception state, validation state, findings, scratchpad state, and pointers to the current node.

Relevant pieces:

- `graph_mapper_agent/runtime/state/*`
- `graph_mapper_agent/runtime/transitions.py`
- `graph_mapper_agent/runtime/nodes/*`

### 2. Decision

The decider answers a tactical question: what is the best next move from the current node?

Relevant pieces:

- `application/services/decision/*`
- `application/services/node_view_builder.py`
- `application/services/candidate_ranker.py`
- `application/services/candidate_selector.py`

### 3. Execution

The execution layer transforms an accepted decision into a structured operational outcome.

Relevant pieces:

- `application/services/execution/action_executor.py`
- `application/services/execution/contracts.py`
- `application/services/execution/edge_actions.py`
- `application/services/execution/search.py`
- `application/services/execution/validation.py`

Core contract:

- `ActionExecutionResult`

### 4. Graph and Runtime Mutation

The update layer absorbs operational outcomes and updates:

- the graph
- arrivals
- per-node local memory
- validation state
- findings
- the current node and active path

Central piece:

- `application/services/graph_updater.py`

### 5. Perception, Validation, and Extraction

These capabilities do not govern the system on their own. They feed the decider and refine the local state.

Relevant pieces:

- `application/services/navigation_perception.py`
- `application/local_perception/*`
- `application/goal_validation/*`
- `application/evidence_extraction/*`

### 6. Web Tooling

Navigation and inspection live behind an operational facade rather than being spread directly across the runtime.

Relevant pieces:

- `bootstrap/builders/tooling.py`
- `adapters/web_browser/tool.py`
- `adapters/tools/web_browser/driver.py`

### 7. LLM Runtime

The project separates:

- declarative configuration
- effective runtime resolution
- concrete adapter composition
- service-level consumption

Relevant pieces:

- `platform/llm/*`
- `adapters/llm/*`
- `bootstrap/builders/llm.py`

### 8. Ledger

The ledger persists operational history for observability, debugging, and future dataset extraction.

Relevant pieces:

- `ledger/adapters/sqlite_ledger_writer.py`
- `ledger/adapters/sqlite_ledger_query_service.py`
- `ledger/schemas/001_agent_memory.sql`

## Exposed Interfaces

- local HTTP interface in `interfaces/http/*`
- high-level chat interface in `interfaces/chat/*`
- high-level MCP interface in `interfaces/mcp/*`

## Recommended Next Read

If you want to go deeper, continue with [reference.md](reference.md).
