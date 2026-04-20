# Ledger Architecture and Operations Reference Manual

## Purpose

This document describes the ledger layer of `graph_mapper_agent` in detail.

It is not intended as a simple table reference. It is a full manual for understanding:

* what the ledger stores,
* how persistence is modeled,
* how it connects to sessions, runs, steps, LLM calls, evidence, and evaluations,
* what role it plays in the framework,
* what it is useful for and what it is not,
* how to query its data,
* how to use it for observability and debugging,
* and how to turn it into a useful dataset for model training or agentic subroutines adapted to the framework.

This manual is written for both humans and AI agents that need to maintain, extend, or analyze the ledger.

---

# 1. What the ledger is

The ledger is the persistent operational memory of the agent.

It is not just logging. It is not a semantic knowledge base. It is not a vector database. It is not just an audit table.

The ledger stores the structured history of what the system did:

* which session exists,
* which messages occurred,
* which run was executed,
* which internal steps were traversed,
* which LLM calls were made,
* which evidence was collected,
* which evaluation was assigned,
* and how everything ended.

Put simply:

> the ledger allows a run of the agent to be reconstructed as a traceable, persistent, queryable sequence.

---

# 2. What problem it solves

Without a ledger, a complex agent usually leaves scattered traces:

* prints,
* loose logs,
* model outputs without context,
* downloaded files without correlation,
* and errors that are hard to reconstruct.

The ledger solves that by splitting operational history into persistent entities:

* sessions,
* messages,
* runs,
* run_steps,
* llm_calls,
* evidence_records,
* evaluations.

This enables:

* real observability,
* strong debugging,
* auditing,
* mental replay of the process,
* offline evaluation,
* and dataset extraction for later research or training.

---

# 3. What the ledger is not

This needs to be very clear.

## It is not a RAG system

It is not designed as the primary semantic retrieval index.

## It is not an embedding memory

It does not store vectors and does not, by itself, provide fast semantic search.

## It is not a clean training dataset by default

It stores useful signal, yes, but it also contains operational noise:

* retries,
* errors,
* failed outputs,
* partial runs,
* old prompts,
* irrelevant evidence,
* failed validations.

## It does not replace the agent domain

The ledger observes and records. It does not decide agent logic.

---

# 4. Architectural overview

## Conceptual flow

```text
runner / use case / service
    -> LedgerEvent or specialized writer methods
    -> SqliteLedgerWriter
    -> SQLite tables
    -> SqliteLedgerQueryService
    -> debugging / analytics / evaluation / dataset extraction
```

## Typical flow of a run

```text
session bootstrap
    -> session
    -> input message
    -> run started
    -> run steps / node events
    -> llm calls
    -> evidence records
    -> evaluations
    -> run completed or failed
    -> output/failure message
```

## Correct mental hierarchy

```text
session
    -> messages
    -> runs
        -> run_steps
        -> llm_calls
        -> evidence_records
        -> evaluations
```

---

# 5. SQLite persistence model

The main ledger is modeled on SQLite.

## General idea

Each table represents a different dimension of agent behavior.

The system does not put everything into a single table because it separates:

* narrative history,
* workflow execution,
* node-level granularity,
* LLM telemetry,
* evidence,
* and evaluation.

That makes later analysis much stronger.

---

# 6. `sessions` table

```sql
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    session_kind TEXT NOT NULL DEFAULT 'runtime',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    context_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
```

## What it represents

An operational session of the system.

A session is the narrative and contextual container for one or more runs.

## Important fields

### `session_id`

Stable session identifier.

### `session_kind`

Classifies the session. In the reviewed code, the default is `runtime`.

### `created_at` / `updated_at`

Creation and update timestamps.

### `status`

Current session state.

### `context_json`

Primary session context.

### `metadata_json`

Additional free-form metadata.

## What it is for

* grouping messages,
* grouping related runs,
* preserving high-level context,
* reconstructing the history of a long interaction or execution.

---

# 7. `messages` table

```sql
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
```

## What it represents

Messages associated with a session.

## Important fields

### `message_id`

Message identifier.

### `session_id`

The session it belongs to.

### `role`

Message role, for example `user` or `assistant`.

### `content_json`

Structured message content.

### `metadata_json`

Additional metadata.

## What it is for

* recording the initial runtime input,
* recording final results,
* recording failure messages,
* providing a narrative layer above technical events.

## Difference from `run_steps`

`messages` tell a conversational or session-level story.
`run_steps` describe the technical granularity of the workflow.

---

# 8. `runs` table

```sql
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT,
    workflow_name TEXT NOT NULL,
    thread_id TEXT,
    attempt INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'running',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    input_json TEXT NOT NULL DEFAULT '{}',
    final_output_json TEXT NOT NULL DEFAULT '{}',
    context_json TEXT NOT NULL DEFAULT '{}',
    quality_score REAL,
    quality_label TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
```

## What it represents

A concrete execution of the system.

This is the central unit of workflow execution.

## Important fields

### `run_id`

Unique run identifier.

### `session_id`

The session it belongs to.

### `workflow_name`

Name of the executed workflow.

### `thread_id`

Additional correlation with a document or processing thread.

### `attempt`

Attempt number.

### `status`

Run state.

### `started_at` / `finished_at`

Primary timestamps.

### `input_json`

Structured run input.

### `final_output_json`

Final run result.

### `context_json`

Additional context.

### `quality_score` / `quality_label`

High-level quality signals.

### `metadata_json`

Free-form metadata.

## What it is for

* macro reconstruction of the run,
* workflow summary,
* the joining point between steps, LLM calls, evidence, and evaluation.

---

# 9. `run_steps` table

```sql
CREATE TABLE IF NOT EXISTS run_steps (
    step_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    step_index INTEGER,
    node_name TEXT,
    branch_name TEXT,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
```

## What it represents

The internal granularity of a run.

## Important fields

### `step_id`

Autoincrement step identifier.

### `run_id`

The run it belongs to.

### `step_index`

Logical step index when provided.

### `node_name`

Executed node.

### `branch_name`

Flow branch.

### `event_type`

Type of event.

### `payload_json`

Structured event payload.

### `metadata_json`

Additional metadata.

### `created_at`

Event timestamp.

## What kinds of events it can store

* node execution,
* phase changes,
* tool failures,
* retries,
* overrides,
* workflow events.

## What it is for

* step-by-step technical reconstruction,
* analyzing where a run failed,
* measuring problematic nodes,
* comparing trajectories across runs.

---

# 10. `llm_calls` table

```sql
CREATE TABLE IF NOT EXISTS llm_calls (
    call_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    session_id TEXT,
    operation_name TEXT NOT NULL,
    provider_name TEXT,
    model_name TEXT,
    prompt_version TEXT,
    structured_output_name TEXT,
    request_kind TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    success INTEGER NOT NULL DEFAULT 0,
    response_format_valid INTEGER,
    finish_reason TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    reasoning_tokens INTEGER,
    cached_tokens INTEGER,
    total_tokens INTEGER,
    latency_ms INTEGER,
    messages_json TEXT NOT NULL DEFAULT '{}',
    expected_output_json TEXT NOT NULL DEFAULT '{}',
    response_json TEXT NOT NULL DEFAULT '{}',
    validation_json TEXT NOT NULL DEFAULT '{}',
    raw_response_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
```

## What it represents

A concrete call to the LLM runtime.

This is one of the most valuable tables in the system.

## Important fields

### Call identity

* `call_id`
* `run_id`
* `session_id`
* `operation_name`
* `provider_name`
* `model_name`

### Contract and prompting

* `prompt_version`
* `structured_output_name`
* `request_kind`

### Timing and outcome

* `started_at`
* `completed_at`
* `success`
* `response_format_valid`
* `finish_reason`
* `latency_ms`

### Tokens

* `input_tokens`
* `output_tokens`
* `reasoning_tokens`
* `cached_tokens`
* `total_tokens`

### IO and validation

* `messages_json`
* `expected_output_json`
* `response_json`
* `validation_json`
* `raw_response_json`
* `metadata_json`

## What it is for

* fine-grained observability of model behavior,
* cost and latency analysis,
* prompt debugging,
* contract debugging,
* dataset extraction,
* comparison across providers and models.

---

# 11. `evidence_records` table

```sql
CREATE TABLE IF NOT EXISTS evidence_records (
    evidence_id TEXT PRIMARY KEY,
    run_id TEXT,
    step_id INTEGER,
    evidence_kind TEXT NOT NULL,
    source_kind TEXT,
    source_url TEXT,
    local_path TEXT,
    mime_type TEXT,
    title TEXT,
    content_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
```

## What it represents

Evidence collected during the run.

## Important fields

* `evidence_id`
* `run_id`
* `step_id`
* `evidence_kind`
* `source_kind`
* `source_url`
* `local_path`
* `mime_type`
* `title`
* `content_json`
* `metadata_json`
* `created_at`

## What it is for

* linking the run with real artifacts and documents,
* persisting navigated or downloaded evidence,
* building datasets that connect decisions to evidence.

## Special value

This table bridges the tooling layer and the LLM or execution layer.

---

# 12. `evaluations` table

```sql
CREATE TABLE IF NOT EXISTS evaluations (
    evaluation_id TEXT PRIMARY KEY,
    session_id TEXT,
    run_id TEXT,
    step_id INTEGER,
    target_kind TEXT NOT NULL,
    evaluator_kind TEXT NOT NULL,
    score REAL,
    label TEXT,
    usable_for_training INTEGER NOT NULL DEFAULT 0,
    feedback_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
```

## What it represents

Judgments or evaluations about system behavior.

## Important fields

* `evaluation_id`
* `session_id`
* `run_id`
* `step_id`
* `target_kind`
* `evaluator_kind`
* `score`
* `label`
* `usable_for_training`
* `feedback_json`
* `created_at`

## What it is for

* heuristic scoring,
* quality control,
* run ranking,
* dataset filtering,
* reward modeling or later analysis.

## Key field

`usable_for_training` is already an explicit signal indicating dataset usefulness.

---

# 13. Main indexes

Indexes are defined on:

* `runs(started_at)`
* `run_steps(run_id, created_at)`
* `llm_calls(run_id, started_at)`
* `evidence_records(run_id, created_at)`
* `evaluations(run_id, created_at)`

## What they optimize

* temporal reconstruction of runs,
* step lookup by run,
* analysis of LLM calls,
* evidence retrieval by run,
* evaluation queries by run.

---

# 14. Conceptual model of the ledger

## Correct reading by levels

### Level 1 — session

Groups a high-level story.

### Level 2 — messages

Stores narrative or input and output inside the session.

### Level 3 — run

Stores one concrete workflow execution.

### Level 4 — run steps

Stores the technical granularity of the run.

### Level 5 — LLM calls

Stores detailed model invocation information.

### Level 6 — evidence

Stores artifacts and observed content.

### Level 7 — evaluations

Stores quality judgment.

## Why this separation is correct

Because a single table cannot cleanly model, at the same time:

* conversation,
* execution,
* telemetry,
* evidence,
* evaluation.

---

# 15. Typed domain events

## File: `ledger/domain/event_payloads.py`

This file models typed payloads for different ledger events.

## General contract

Every payload must:

* declare `event_type`,
* be serializable through `to_dict()`,
* be consistent with the registered `EventType`.

## Common base

`_EventPayloadBase` serializes:

* enums,
* dataclasses,
* tuples,
* lists,
* dicts.

That avoids scattering serialization logic across the system.

## Reviewed payloads

### `RunStartedPayload`

Describes the start of a run.

### `RunCompletedPayload`

Describes a successful or finished run.

### `RunFailedPayload`

Describes run failure.

### `NodeExecutedPayload`

Describes execution of a node.

### `LlmCalledPayload`

Describes an LLM call being started.

### `LlmCompletedPayload`

Describes an LLM call being completed.

### `LlmValidationFailedPayload`

Describes failure of LLM output validation.

### `ToolFailedPayload`

Describes a tool failure.

### `RetryScheduledPayload`

Describes scheduling of a retry.

### `OverrideAppliedPayload`

Describes application of an override.

## Why this matters

It prevents the ledger from devolving into just “free JSON everywhere.”

---

# 16. `LedgerEvent`

## File: `ledger/domain/ledger_event.py`

`LedgerEvent` is the typed event unit of the ledger.

## Main fields

* `event_id`
* `event_type`
* `run`
* `actor`
* `payload`
* `target`
* `metadata`
* `llm`
* `llm_io`
* `occurred_at`

## Guarantees

### Non-empty `event_id`

### Payload consistent with `event_type`

This is validated in `__post_init__()`.

## What role it plays

It is the domain object that represents an event before it is persisted.

---

# 17. Additional context: correlation, actor, and LLM metadata

Even though not all auxiliary files were included, the intent of these pieces is already clear.

## `RunCorrelation`

Correlates the event with:

* `run_id`
* `thread_id`
* `workflow_name`

## `ActorKind`

Classifies who produced the event.

## `TargetRef`

Associates the event with a domain target.

## `LlmCallMetadata`

Summarizes:

* provider,
* model,
* prompt_version,
* prompt_hash,
* structured_output_name.

## `LlmInteraction`

Stores:

* input,
* expected_output,
* response,
* validation.

## Importance

These pieces give the ledger enough semantic structure to be genuinely useful, not just raw persistence.

---

# 18. Ledger builders

## `build_ledger_writer(...)`

### Role

Construct `SqliteLedgerWriter`.

### Current flow

```text
database_url explicit
    -> or AITHER_LEDGER_DATABASE_URL
    -> or hardcoded default
    -> parse path
    -> SqliteLedgerWriter.connect(path)
```

## `build_ledger_query_service(...)`

### Role

Construct `SqliteLedgerQueryService`.

### Current flow

Same pattern:

```text
database_url explicit
    -> or env var
    -> or hardcoded default
    -> parse path
    -> SqliteLedgerQueryService.connect(path)
```

## What they do well

* allow explicit override,
* support environment variables,
* separate writing and reading.

## What is not ideal

They use hardcoded local absolute paths as defaults.

---

# 19. The problem with absolute paths

This is a weak long-term default.

## Why

* it breaks portability,
* it breaks clean project cloning,
* it makes one machine look like the “official universe,”
* it forces configuration rewrites when the repo is shared.

## What would be better

Move to project-relative paths, for example:

```text
graph_mapper_agent/data/ledger/graph_mapper_agent.sqlite3
```

And resolve it through a central helper plus environment-variable override.

---

# 20. Ledger integration with the LLM pipeline

## Key file: `ledger/application/invoke_llm_with_ledger_use_case.py`

This is the component that wraps a normal LLM call and turns it into a persistently observed call.

## Conceptual flow

```text
LLM request
    -> record_llm_called(...)
    -> llm_runtime.invoke(request)
    -> response
    -> record_llm_completed(...)
    -> if validation fails -> record_llm_validation_failed(...)
    -> return response
```

## What it receives

* `ledger: LedgerWritePort`
* `llm_runtime: LlmRuntimePort`
* `provider_name`
* event_id_factory
* call_id_factory

## What `execute(...)` does

### Step 1

Determines `request_kind`.

Current rule:

* if `expected_output_name` exists -> `structured_generation`
* otherwise -> `chat_completion`

### Step 2

Generates `call_id` and base metadata.

### Step 3

Records `record_llm_called(...)` with:

* `LlmCalledPayload`
* `LlmCallMetadata`
* initial `LlmInteraction`

### Step 4

Invokes the real runtime.

### Step 5

Evaluates whether the response satisfied the contract.

### Step 6

Records `record_llm_completed(...)`.

### Step 7

If validation fails, records `record_llm_validation_failed(...)`.

## What the framework gains from this

* persistent LLM observability,
* prompt and output traceability,
* structured validation signal,
* potential training data for later use.

---

# 21. How the ledger enters the runner

In `runner.py`, the ledger is constructed very early and used throughout the run.

## What it conceptually records

### Session bootstrap

* registers the session,
* registers the initial input message.

### Run started

* entry URL,
* goal,
* decision mode,
* execution metadata.

### During the run

* may record node events,
* may wrap LLM calls,
* may record evidence and evaluations.

### Run completed

* final status,
* final state,
* final message,
* heuristic evaluation.

### Run failed

* error class,
* error message,
* failure message,
* failure evaluation.

## Correct interpretation

The ledger is not attached at the end “just in case.” It is integrated from the very beginning.

---

# 22. What the ledger is actually useful for

## 1. Observability

It allows you to see what the system did and in what order.

## 2. Strong debugging

It allows failures to be reconstructed by:

* session,
* run,
* step,
* llm_call,
* evidence,
* evaluation.

## 3. Auditing

It allows you to justify:

* which inputs the agent received,
* which outputs it produced,
* which evidence it observed,
* which contract it expected,
* and whether it satisfied that contract.

## 4. Analytics

It allows you to measure:

* latency,
* tokens,
* models,
* provider behavior,
* errors,
* successful and failed runs.

## 5. Offline evaluation

It allows comparison across:

* prompts,
* models,
* workflows,
* subtasks,
* strategies.

## 6. Dataset extraction

It serves as a mine for building training datasets.

---

# 23. What it is not sufficient for by itself

## It does not replace data curation

The ledger contains signal, but it also contains noise.

## It is not automatically a fine-tuning dataset

It must be filtered, normalized, and curated.

## It is not a semantic memory graph

It is not designed as a representation of complex vector or graph-style relational memory.

## It does not replace agent policy

It observes execution, but it does not define the final trained policy.

---

# 24. Can it be used to train agentic models adapted to the framework?

Yes. Quite effectively.

But the correct answer is:

> the ledger is an excellent source mine for datasets, not a clean final dataset by default.

## Where the most valuable signal lives

### `llm_calls`

Because it contains:

* messages,
* expected contract,
* response,
* validation,
* raw response,
* tokens,
* provider and model,
* prompt_version.

### `run_steps`

Because it contains the agent’s operational sequence.

### `evaluations`

Because it provides quality signal.

### `evidence_records`

Because it links decisions to real evidence.

## What kinds of training it enables

### 1. Supervised fine-tuning of subroutines

For example:

* planner,
* validation,
* navigation perception,
* answer synthesis,
* coverage assessment.

### 2. Behavior cloning of the framework

Using sequences of runs, steps, and LLM calls.

### 3. Reward modeling or heuristic ranking

Using `evaluations`.

### 4. Router training

Learning which model or subtask to use in which context.

### 5. Tool-usage analysis

Learning when a tool path works better or worse.

---

# 25. How to turn the ledger into a useful dataset

## General principle

Do not export “everything.” Extract concrete tasks.

## Example 1 — Planner dataset

Take:

* goal context,
* prompt_version,
* expected_output_name,
* validated response,
* later score or label.

## Example 2 — Structured validation dataset

Take:

* messages,
* expected_output_json,
* response_json,
* validation_json,
* usable_for_training.

## Example 3 — Agent policy dataset

Take:

* state before the step,
* action or node executed,
* step outcome,
* later evaluation.

## Example 4 — Evidence ranking dataset

Take:

* run context,
* evidence_records,
* later label or score,
* run success or failure.

## What should usually be filtered out

* useless failed runs,
* responses with failed validation,
* redundant retries,
* old experimental prompts,
* unusable evidence,
* empty or corrupt outputs.

## What should usually be preserved

* `prompt_version`
* `model_name`
* `provider_name`
* `structured_output_name`
* `quality_label`
* `usable_for_training`
* `feedback_json`

---

# 26. What it still lacks to become an even better training source

Not strictly required, but very valuable additions would be:

* before/after snapshots per step,
* more uniform typed errors,
* clear versioning of policy and config per run,
* a stable hash of the effective prompt,
* a more direct link between step and llm_call,
* more normalized outcome labels.

---

# 27. How to query the ledger as a maintainer

## If I want to reconstruct a run

Inspect:

1. `runs`
2. `run_steps`
3. `llm_calls`
4. `evidence_records`
5. `evaluations`

## If I want to see narrative history or messages

Inspect:

1. `sessions`
2. `messages`

## If I want to debug one LLM call

Inspect:

1. `llm_calls`
2. `LlmCallMetadata`
3. `LlmInteraction`
4. `InvokeLlmWithLedgerUseCase`

## If I want to see why a run failed

Inspect:

1. `runs.status`
2. `run_steps`
3. `messages`
4. `llm_calls.validation_json`
5. `evaluations`

## If I want to see which evidence a run produced

Inspect:

1. `evidence_records`
2. `run_id`
3. `step_id`
4. `source_url` / `local_path`

---

# 28. How to extend the ledger

## Case A — new event

1. add the event type,
2. create a typed payload,
3. persist it in the writer,
4. expose it in the query service if needed.

## Case B — new evidence class

1. define `evidence_kind`,
2. store the relevant metadata,
3. correctly register `run_id` and `step_id`.

## Case C — new evaluation signal

1. decide `target_kind`,
2. decide `evaluator_kind`,
3. persist `score`, `label`, `usable_for_training`, and `feedback_json`.

## Case D — new LLM instrumentation path

Keep it passing through a wrapper such as `InvokeLlmWithLedgerUseCase`; do not scatter writes everywhere.

---

# 29. How to debug the ledger

## If the SQLite connection fails

Review:

1. writer/query-service builder
2. resolved path
3. folder existence
4. filesystem permissions

## If runs do not appear

Review:

1. connected writer
2. runner bootstrap
3. run correlation

## If runs appear but messages do not

Review:

1. `record_message(...)`
2. session bootstrap

## If LLM events do not appear

Review:

1. whether the call passes through `InvokeLlmWithLedgerUseCase`
2. `record_llm_called/completed/validation_failed`
3. correlation metadata

## If validation fails but the cause is unclear

Review:

1. `validation_json`
2. `expected_output_json`
3. `response_json`
4. `raw_response_json`

---

# 30. Maintenance rules

## Rule 1

Do not use local absolute paths as permanent defaults.

## Rule 2

Keep table responsibilities separated.

## Rule 3

Every new event must have a coherent typed payload.

## Rule 4

LLM instrumentation should stay centralized in clear wrappers.

## Rule 5

The ledger should not be mixed with semantic knowledge storage or document storage unless strictly necessary.

## Rule 6

If a signal should later serve training, document it and mark it explicitly.

---

# 31. Checklist for human contributors and AI agents

Before touching the ledger, answer:

1. Am I changing schema, writer, query service, or only instrumentation?
2. Does the change affect sessions, messages, runs, steps, llm_calls, evidence, or evaluations?
3. Do I need to add a new payload?
4. Do I need a new index?
5. Am I breaking compatibility with existing queries?
6. Am I leaving paths portable?
7. Do I want this signal to be useful for training later?
8. Does this manual need to be updated?

---

# 32. Executive summary

The ledger of `graph_mapper_agent` is the persistent operational memory of the framework.

It stores:

* sessions,
* messages,
* runs,
* steps,
* LLM calls,
* evidence,
* evaluations.

It is useful for:

* traceability,
* debugging,
* auditing,
* observability,
* offline evaluation,
* and dataset extraction.

It is not a clean dataset by itself, but it is a rich behavioral mine of the agent.

The most important integration with the LLM pipeline happens through `InvokeLlmWithLedgerUseCase`, which turns a normal LLM call into a persistently traced one.

The most obvious near-term technical improvement is to remove hardcoded absolute-path defaults and move ledger-path resolution to project-relative configuration.

---

# 33. Ultra-short summary for AI agents

## What it does

Stores the persistent operational trace of the agent.

## What it stores

* sessions
* messages
* runs
* run_steps
* llm_calls
* evidence_records
* evaluations

## What it enables

* debugging
* observability
* auditing
* dataset extraction

## Golden rule

Do not treat it as just a log or as a final training dataset.
It is a rich trace that must be queried, interpreted, and curated.
