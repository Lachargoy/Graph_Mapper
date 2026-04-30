# Repo Map

This document is a short orientation guide for the repository.

Its purpose is not to explain the full architecture in detail. Its purpose is to help a new human reader, or an automated agent, answer four questions quickly:

1. where the main runtime lives
2. which folders matter first
3. which docs should be read first
4. which areas are canonical versus secondary or legacy

## Start Here

If you are new to the repository, the fastest useful reading path is:

1. `README.md`
2. `docs/overview.md`
3. `docs/quickstart.md`
4. `docs/architecture.md`
5. this file

After that, move to:

- `docs/goal_validation.md`
- `docs/node_identity_and_dom_mutation.md`
- `docs/future_graph_dynamics.md`
- `docs/reference.md`

## Main Runtime

The main runtime lives under:

- `graph_mapper_agent/`

This is the center of the project.

At a high level:

- `domain/` defines structural concepts
- `application/` holds use cases and services
- `adapters/` connects the runtime to providers and infrastructure
- `interfaces/` exposes the runtime through HTTP, chat, and MCP-oriented surfaces
- `runtime/` holds active runtime state and execution flow pieces
- `platform/` holds cross-cutting runtime support such as LLM runtime planning
- `ledger/` contains persistence and query logic for the local ledger
- `bootstrap/` assembles configurations and entry flows

## Directory Guide

### `graph_mapper_agent/domain/`

Read this when you want the structural vocabulary of the system.

Important examples:

- graph state
- paths
- anchors
- findings
- local views

This layer answers:

> what are the core concepts the runtime thinks with?

### `graph_mapper_agent/application/`

Read this when you want to understand behavior and use cases.

Important areas:

- `goal_validation/`
- `evidence_extraction/`
- `local_perception/`
- `navigation_perception/`
- `services/`
- `use_cases/`

This layer answers:

> what does the runtime actually do with the domain concepts?

### `graph_mapper_agent/adapters/`

Read this when you want concrete integrations.

Important areas:

- `llm/`
- `evidence_extraction/`
- `web_browser/`
- `tooling/`
- `perception/`

This layer answers:

> how does the runtime speak to models, browsers, OCR, and other concrete systems?

### `graph_mapper_agent/interfaces/`

Read this when you want entry surfaces.

Important areas:

- `http/`
- `chat/`
- `mcp/`

This layer answers:

> how can an external caller interact with the runtime?

### `graph_mapper_agent/runtime/`

Read this when you want to understand the active execution loop and stateful mechanics.

Important areas:

- `nodes/`
- `state/`
- `transitions.py`

This layer answers:

> how does the runtime move from one local step to another during execution?

### `graph_mapper_agent/platform/`

Read this when you want cross-cutting support logic that is not tied to one use case.

Right now the most important piece here is:

- `platform/llm/`

This layer answers:

> how are provider policies, runtime plans, and LLM capability decisions resolved?

### `graph_mapper_agent/bootstrap/`

Read this when you want to know how the system is assembled and launched.

Important areas:

- config parsing
- runtime builders
- runner entry flow
- canonical profiles under `bootstrap/configs/`

This layer answers:

> how is a concrete runnable agent instance created?

### `graph_mapper_agent/ledger/`

Read this when you want persistence and traceability.

This layer answers:

> how are runs, steps, calls, evidence, and trace records stored and queried locally?

## Canonical Areas

These areas are the main current architecture and should be treated as canonical:

- `goal_validation`
- `evidence_extraction`
- `platform/llm`
- the HTTP interface
- the local SQLite ledger
- the graph/runtime split centered on `NodeView`, decision, execution, and update

## Secondary or Transitional Areas

Some areas still exist for compatibility or historical reasons and should be read with care:

- `document_validation` naming and wrappers
- some older internal manuals in `docs/` that are longer than necessary

These are not necessarily broken, but they are not the best starting point for understanding the current direction of the project.

## Config Profiles

The canonical runtime profiles live under:

- `graph_mapper_agent/bootstrap/configs/`

Current public set:

- `config_qwen.json`
- `config_lm_studio.json`
- `config_ollama.json`

## Best Docs By Question

If your question is:

### What is this project?

Read:

- `README.md`
- `docs/overview.md`

### How do I run it?

Read:

- `docs/quickstart.md`

### How does the runtime work?

Read:

- `docs/architecture.md`
- `docs/end_to_end.md`
- `docs/execution_layer.md`
- `docs/graph_updater.md`

### How does validation work?

Read:

- `docs/goal_validation.md`

### How does the LLM runtime work?

Read:

- `docs/llm_runtime.md`

### How should I think about node identity and mutation?

Read:

- `docs/node_identity_and_dom_mutation.md`
- `docs/future_graph_dynamics.md`

## What To Ignore At First

If you are trying to get oriented quickly, do not start with:

- every file under `application/services/`
- legacy compatibility wrappers
- long internal manuals in arbitrary order
- low-level implementation details before reading the architecture docs

## Agent-Friendly Reading Advice

For automated analysis, a good sequence is:

1. read `README.md`
2. read `docs/architecture.md`
3. read `docs/repo_map.md`
4. inspect `graph_mapper_agent/domain/`
5. inspect `graph_mapper_agent/application/`
6. inspect `graph_mapper_agent/platform/llm/`
7. inspect `graph_mapper_agent/interfaces/http/`

That gives a good top-down view before descending into detailed modules.
