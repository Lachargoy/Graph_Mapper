# Overview

`graph_mapper_agent` is a web research agent that combines navigation, local perception, tactical decision-making, goal validation, evidence extraction, and persistent observability.

The core unit of the system is not an isolated page, but a live agent state that is projected locally as a `NodeView`, evaluated by the decider, executed through tools, and then internalized as real changes in the graph and runtime memory.

Another important design choice is that the LLM is not treated as the global memory of the agent and not as a narrator of the full exploration history. Its role is narrower and more tactical: it interprets the current node as a situated decision surface and collapses the available context into the best next action.

The system therefore does not rely on the model to remember every prior step, every intermediate thought, or the full causal chain of the run. Instead, it maintains a structured state representation and gives the model a local projection of that state. In practice, this means the model operates more like an interpreter of the current situation than like a free-form planner that must reconstruct the whole journey from scratch.

## What This Project Does Well

- traverses a navigable space as a graph of nodes and edges
- makes tactical decisions in context instead of issuing isolated clicks
- validates whether the current evidence actually satisfies the active goal
- extracts usable evidence only after validation
- preserves traceability for runs, messages, runtime steps, LLM calls, and evidence in SQLite

## State Over Narrative Memory

The project is built around the idea that the agent should preserve state, not a textual replay of every thought it ever had.

A human does not usually need to remember every internal thought that led to a conclusion. What matters more is a usable representation of the current situation: where they are, what they already know, what remains unresolved, and which next moves are promising. This system follows the same principle.

That is why the goal notebook, tactical scratchpad, path state, anchors, and node view should be understood as compact operational state, not as chain-of-thought storage. The objective is not to preserve a full narrative of the run, but to preserve the minimum structured context needed to make the next decision well.

## Interfaces Available Today

### Runtime

The main runtime lives in `graph_mapper_agent/bootstrap/runner.py` and orchestrates:

- web tooling
- LLM runtimes
- perception and validation
- action execution
- graph mutation
- ledger persistence

### HTTP

The local HTTP interface lets you run research sessions from a browser and inspect sessions, runs, and evidence.

Primary entry point:

- `python -m graph_mapper_agent.interfaces.http.server`

The HTTP surface reads its runtime profiles from:

- `graph_mapper_agent/bootstrap/configs/`

and the current repository intentionally keeps only three canonical profiles:

- `config_qwen.json`
- `config_lm_studio.json`
- `config_ollama.json`

### MCP

The MCP surface does not expose low-level browser tools directly. It exposes high-level operations over the complete agent, such as:

- `process_chat_turn`
- `run_graph_mapper`
- `get_run`
- `get_session`
- `get_evidence`

## Use Cases the Project Already Communicates Well

- assisted web research
- guided navigation with structured memory
- validation of documents and artifacts against goals
- evidence extraction with traceability
- groundwork for a reusable agent interface over HTTP or MCP

## What You Should Not Promise Yet

- a production-hardened experience without additional work
- fully polished public-facing documentation across every submodule
- complete removal of all legacy compatibility shims

## Recommended Reading Order

1. [quickstart.md](quickstart.md)
2. [architecture.md](architecture.md)
3. [reference.md](reference.md)
