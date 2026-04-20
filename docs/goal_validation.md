# Goal Validation

## Purpose

This document explains the `goal_validation` subdomain in `graph_mapper_agent`.

Goal validation is the part of the system that answers a narrow but critical question:

> does the current local content actually help satisfy the active goal?

It is not the global planner, not the browser layer, and not the graph mutator. It is a bounded evaluation capability that turns local evidence into a structured validation result.

---

## Core Idea

The right mental model is:

```text
current content or artifact
    -> GoalValidationRequest
    -> GoalValidationPolicy
    -> one or more validation passes
    -> GoalValidationResult
    -> projected into runtime and NodeView
```

Goal validation exists to prevent the agent from treating every opened page, PDF, or artifact as equally useful.

It creates a formal step between:

- seeing content
- and accepting that content as relevant to the goal

---

## Why It Exists

Without goal validation, a web agent usually falls into one of two weak patterns:

1. it treats every plausible artifact as success too early
2. it extracts content too early, before confirming that the carrier and content are actually relevant

Goal validation solves that by explicitly asking:

- does this content match the intended goal?
- does it satisfy one or more pending goal conditions?
- is the carrier acceptable?
- is the evidence final, partial, or inconclusive?
- should the system continue escalating validation or stop here?

That makes the runtime much more disciplined.

---

## Canonical Concepts

The current subdomain is centered on these types:

- `GoalValidationRequest`
- `GoalCondition`
- `GoalValidationPass`
- `GoalValidationResult`
- `GoalValidationPolicy`
- `GoalValidationService`

Relevant files:

- `graph_mapper_agent/application/goal_validation/validation_models.py`
- `graph_mapper_agent/application/goal_validation/policy.py`
- `graph_mapper_agent/application/goal_validation/service.py`
- `graph_mapper_agent/application/goal_validation/use_cases/progressive_validate_goal.py`

---

## Main Inputs

### `GoalValidationRequest`

This is the main input contract.

It includes:

- the current artifact or local content
- a `validation_goal`
- pending `goal_conditions`
- preferred strategy
- page and escalation limits
- pattern hints
- optional target page
- metadata

This matters because validation is not free-form. It is asked to evaluate a bounded local target against a bounded local goal.

### `GoalCondition`

Goal conditions give the validation layer a more structured target than a plain natural-language question.

They describe things such as:

- condition id
- label
- target kind
- year
- requiredness
- minimum count
- document family
- accepted carriers
- whether strict carrier matching is required

That lets the validation layer reason in a more formal way about what would count as a useful match.

---

## Validation Strategies

The system currently recognizes four validation strategies:

- `first_page`
- `first_pages_window`
- `pattern_search`
- `visual_page`

These strategies reflect a progressive validation model rather than a single monolithic call.

### 1. `first_page`

Cheap first look at page 1.

This is the default initial pass unless the request explicitly prefers visual validation.

### 2. `first_pages_window`

Escalates from a single page to a small initial window when page 1 alone is inconclusive.

### 3. `pattern_search`

Uses text hints to search for stronger signals before escalating to a more expensive confirmation step.

### 4. `visual_page`

Used when textual evidence is insufficient, when the target page is known, or when visual confirmation is required.

---

## Policy and Progressive Validation

Goal validation is intentionally progressive.

The main policy lives in:

- `GoalValidationPolicy.next_pass(...)`

The policy decides:

- what the initial pass should be
- whether escalation is allowed
- whether there is remaining page budget
- when to move from `first_page` to `first_pages_window`
- when to move from text strategies to `pattern_search`
- when to escalate to `visual_page`

This makes validation more efficient and more interpretable than a single oversized pass.

The use case that executes this policy is:

- `ProgressiveGoalValidationUseCase`

It repeatedly:

1. asks the policy for the next pass
2. executes that pass through a validation executor
3. appends the result to history
4. stops when the result is final or no more escalation is possible

The final output is:

- `ProgressiveGoalValidationResult`

which contains:

- the full validation history
- the final validation result

---

## Status Model

The current status vocabulary is:

- `validated`
- `invalid`
- `inconclusive`
- `needs_more_pages`

This is one of the strengths of the subdomain.

The output is not just binary success or failure. It can distinguish between:

- confirmed match
- clear mismatch
- not enough evidence yet
- more pages needed

That is important because the runtime can react differently to each case.

---

## Relationship to Evidence Extraction

Goal validation and evidence extraction are closely related, but they are not the same thing.

The intended order is:

```text
goal_validation
    -> if positive enough
    -> evidence_extraction
```

This is one of the core discipline rules in the system.

The agent should not aggressively extract evidence from every artifact it touches. It should first determine whether the content is actually relevant enough to justify extraction.

That keeps the evidence layer cleaner and reduces downstream noise.

---

## Relationship to `NodeView`

Goal validation does not stay isolated in a submodule. Its result is projected into runtime state and then exposed in `NodeView`.

That means the decider can see:

- whether local content is already validated
- whether the node is inconclusive
- whether more local validation is still possible
- whether the current content appears promising enough to justify the next step

This is one of the reasons the decider does not need to reason over raw artifacts directly.

The runtime absorbs validation complexity first.

---

## Deterministic and LLM-Backed Execution

The validation layer can be executed through different backends.

At build time, the system can choose:

- deterministic validation
- LLM-backed validation

That wiring happens in:

- `graph_mapper_agent/bootstrap/builders/validation.py`

The LLM-backed path uses:

- `LlmBackedGoalValidationPassExecutor`

The deterministic path uses:

- `DeterministicGoalValidationPassExecutor`

This is important architecturally because the runtime can preserve the same subdomain contracts while changing the implementation strategy underneath.

---

## Why This Subdomain Matters

`goal_validation` is one of the cleanest examples of the project’s broader design philosophy:

- bounded contracts
- progressive stateful evaluation
- explicit separation between interpretation and mutation
- structured results instead of free-form memory

It is also one of the clearest improvements over the older `document_validation` framing.

The system is no longer just validating whether a document looks right in isolation. It is evaluating whether local evidence advances the active goal of the agent.

That is a better and more accurate domain boundary.

---

## Relationship to Future Work

As the runtime becomes more dynamic, goal validation will likely remain important.

Even in richer node mutation or higher-dimensional graph models, the system will still need a bounded way to answer:

- does the current local state satisfy a pending goal condition?
- is this evidence worth accepting?
- should the system extract more, search more, or move on?

So while implementation details may evolve, the subdomain itself is likely to remain central.
