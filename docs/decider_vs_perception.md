# Technical Manual: the Decider as Orchestrator and Its Relationship with Validation and Perception in `graph_mapper_agent`

## Purpose

This manual documents a central architectural idea of `graph_mapper_agent`:

* the **decider** as the main coordinator of tactical action,

* and **validation** and **perception** as specialized subroutines that do not govern the system on their own, but instead feed and refine the system’s decision-making capacity.

The goal is to explain:

* why the decider can be understood as the local “boss” of the cycle,

* why navigation perception and document validation should be seen as subroutines rather than final authorities,

* how they connect to each other,

* what the architecture gains by separating them,

* and what advantages this approach has over designs where everything is mixed into a single call or a single module.

# 1. Core idea

The best way to summarize this architecture is this:

```text
GraphMapperState
    -> NodeView
    -> Decider
        -> may rely on perception signals
        -> may rely on validation capability
        -> decides the next action
```

## Correct mental model

The system is not designed so that:

* perception decides everything,

* validation decides everything,

* or the LLM performs all the logic in a single step.

It is designed around a **decision core** that coordinates specialized subroutines.

In that structure:

* **Decider** = main tactical orchestrator

* **Perception** = local reading subroutine for the navigable space

* **Validation** = formal evaluation subroutine for local evidence

# 2. What it means to say the decider is “the boss”

It does not mean the decider is omniscient or that it does everything directly.

It means something more precise:

the decider is the layer that has the authority to choose the agent’s next operational action.

## What it can decide

Actions such as:

* `follow_edge`

* `download_artifact`

* `open_artifact`

* `search_with_text`

* `validate_current_content`

* `refine_navigation_perception`

* `mark_exhausted`

* `success`

## What it does not do directly

* it does not inspect the browser by itself

* it does not read the PDF by itself

* it does not validate all pages by itself

* it does not directly mutate the graph

Its job is not to execute everything. Its job is to **choose what should be done now**.

# 3. What a subroutine means in this architecture

Here, “subroutine” does not mean something minor or irrelevant.

It means:

a specialized capability that solves a local or technical problem, but whose output must be interpreted by a higher-level layer.

## In this case

### Navigation perception

It resolves:

* what the node looks like locally

* what kind of layout it seems to have

* which candidates appear most promising

* whether the current node already suggests immediate progress

* whether it is better to search, validate, return later, or refine perception

### Document validation

It resolves:

* whether the current local evidence satisfies one or more pending conditions

* whether it contradicts the expected deliverable type

* whether the carrier is correct or not

* whether the evidence is final or only intermediate

* whether another pass is needed

## What matters

Neither of these two subroutines decides the agent’s next global step on its own.

Both produce **specialized signals**.

# 4. Relationship between the three pieces

## General view

```text
runtime state
    -> NodeViewBuilder
        -> projection of local state
        -> embeds perception state
        -> embeds validation state
    -> NodeView
    -> Decider
        -> chooses the next action
```

## Correct reading

Perception and validation do not live “next to” the decider as isolated modules.

They live **underneath** the decision surface, because their results are projected into `NodeView`.

That allows the decider to see:

* the local reading of the node,

* the current validation situation,

* and the rest of the tactical context,

as part of a single coherent cognitive interface.

# 5. The role of `NodeView` in this relationship

## Why it matters so much

`NodeView` is the piece that makes this architecture possible without chaos.

If the decider had to talk directly to:

* perception,

* validation,

* runtime,

* findings,

* goal trace,

* raw inspection,

* search history,

* and choice points,

then the decision layer would become unmanageable.

## What `NodeView` does

It turns all of that into a stable local projection.

So the correct chain is:

```text
Perception result + Validation state + Local runtime context
    -> NodeView
    -> Decider
```

## Meaning

Perception and validation are not plugged directly into the decider as scattered if-elses.

They are first integrated into a common decision surface.

That is extremely elegant.

# 6. Navigation Perception as a subroutine

## What problem it solves

Navigation perception answers a local question:

“what kind of navigable scene do I have in front of me, and how promising does it look for the current goal?”

## What it produces

It produces things such as:

* `recommended_next_step`

* `layout_kind`

* `immediate_condition_gain`

* `best_immediate_condition_labels`

* `strategic_return_suggested`

* `current_node_goal_match`

* `top_candidate_observations`

* `visual_recovery_hints`

## What it should not do

It should not assume control of the agent.

For example:

* if perception says `search_with_text`, that does not mean the system must obey automatically;

* if perception says `validate_current_content`, that does not mean the goal is already closed.

## Correct interpretation

Perception is an **expert local reading**, not a global governor.

# 7. Document Validation as a subroutine

## What problem it solves

Document validation answers a different question:

“does the current local evidence actually satisfy any pending goal condition?”

## What it produces

It produces things such as:

* `status`

* `matched_condition_ids`

* `validated_document_family`

* `validated_year`

* `validated_carrier`

* `carrier_requirement_assessment`

* `validation_scope_assessment`

* `recommended_next_strategy`

## What it should not do

It should not:

* decide the next edge in the graph,

* open new navigation routes,

* or impose the global flow of the agent on its own.

## Correct interpretation

Validation is a **semantic closure subroutine**, not a global navigation subroutine.

# 8. The decider as coordinator of subroutines

## What coordinating them means

The decider:

* does not replace perception,

* does not replace validation,

* but interprets their signals inside the general context of the current node.

## Conceptual example

### Case 1

Perception says:

* “there is a very promising candidate”

Validation says:

* “the current evidence is not enough”

Then the decider may choose:

* `follow_edge`

* or `open_artifact`

### Case 2

Perception says:

* “the current node already appears to be the final deliverable”

Validation state says:

* “it can still be revalidated and doing so would not be redundant”

Then the decider may choose:

* `validate_current_content`

### Case 3

Perception says:

* “there is no useful local progress”

Validation does not provide local closure.

Then the decider may choose:

* `mark_exhausted`

* or let branching policy take over later.

## Conclusion

The decider is the layer that **combines context, perception, and validation into a single action**.

# 9. Why this hierarchy is good

## Mental model

```text
subroutines
    -> produce specialized signals
orchestrator
    -> decides what to do with them
```

## Why it works well

Because it avoids two very common errors:

### Error 1: giving total authority to perception

That would incorrectly turn the local reading of the layout into global strategy.

### Error 2: giving total authority to validation

That would let the current evidence monopolize the decision, even when it is no longer the best local tactical move.

## What is correct

Perception and validation are experts in their domain.

The decider is the layer that arbitrates between their outputs and the rest of the context.

# 10. Advantage 1: clean separation of responsibilities

## What you gain

Each subroutine can specialize in its own problem:

* perception in local navigational reading

* validation in formal evidence evaluation

* decider in action selection

## Result

You can improve one layer without destroying the others.

For example:

* change the perception executor

* improve validation prompts

* harden decider guardrails

without turning everything into spaghetti.

# 11. Advantage 2: better interpretability

When something goes wrong, you can ask:

* did the local reading of the node fail?

* did the evidence evaluation fail?

* did the integration of signals into the decision fail?

That is much better than having a single monolithic call where you do not know whether the error was:

* in navigation,

* in validation,

* in selection,

* or in global reasoning.

## Result

Better debugging. Better documentation. Better traceability.

# 12. Advantage 3: better LLM control

## What changes with this approach

The LLM does not have to do everything at once.

Instead:

* one part of the system uses it for local perception,

* another part uses it for bounded validation,

* and the decider operates over an already structured view.

## Result

Less dependence on one giant reasoning step.

More control over:

* prompts

* contracts

* structured outputs

* retries

* fallbacks

* guardrails

# 13. Advantage 4: possibility of fallback per subroutine

## Clear example

Navigation perception can already have:

* LLM path

* heuristic fallback

And document validation can also separate:

* textual pass

* visual pass

* retries without image

## Meaning

The system does not collapse entirely if one subroutine fails.

You can degrade one capability locally without losing the full workflow.

That is a huge advantage over architectures where a single model failure breaks the whole cycle.

# 14. Advantage 5: better reuse

## Perception

It can feed:

* `NodeView`

* strategic anchors

* local candidate ranking

* current node findings

## Validation

It can feed:

* `validate_current_content`

* local perception

* goal validation state

* matched condition ids

* structured findings

## Decider

It can remain the same core even as perception and validation evolve.

## Result

The architecture gains real modularity.

# 15. Advantage 6: it avoids mixing “seeing” with “deciding” with “closing goals”

This is one of the best things about the approach.

Because in many agentic systems all of that collapses into a single prompt:

* see the page,

* interpret layout,

* decide next action,

* decide whether the goal is already satisfied,

* decide whether another page is needed,

* etc.

That produces opaque and fragile systems.

## Here instead

* perception = see locally

* decider = choose action

* validation = decide whether the evidence closes conditions

## Result

Each cognitive operation has its place.

This looks much more like a serious architecture than a single black-box magic box.

# 16. Advantage 7: better grounding

## Why

Validation works against structured conditions.

Perception works against candidates and local layout.

The decider works against `NodeView`, not against loose text from the world.

## Result

The agent’s final action is better anchored in:

* real local state,

* real evidence carriers,

* real formal conditions,

* real tactical constraints.

That reduces operational hallucination.

# 17. How this connects in the real flow

## Conceptual flow

```text
GraphMapperState
    -> current node
    -> NodeViewBuilder
        -> incorporates perception
        -> incorporates validation state
    -> NodeView
    -> Decider
        -> chooses action
    -> Executor
        -> executes
    -> Updater
        -> internalizes results
```

## Key point

Perception and validation help the decider **before** the action.

Then execution and updater handle what happens **after** the action.

That cleanly separates:

* cognitive reading/evaluation subroutines

* from operational and mutation layers.

# 18. What happens if you invert this hierarchy

## If perception were the boss

The system would tend to follow the local reading of the layout too strongly, even when validation or goal context said otherwise.

## If validation were the boss

The system would tend to obsess over the current local evidence, even when the best move would be to navigate to another candidate.

## If everything were a single LLM call

You would have:

* less control,

* less fallback per capability,

* less traceability,

* more mixing between cognitive roles,

* and more difficulty debugging why it failed.

## Conclusion

The current hierarchy is better.

# 19. What the decider gains from this approach

## It gains better context

Because it receives a view already enriched by perception and validation.

## It gains better authority

Because it can choose among several actions without being hijacked by a single subroutine.

## It gains better robustness

Because perception and validation can fail partially without destroying the ability to decide.

## It gains better stability

Because `NodeView` maintains a coherent interface even when the internals of subroutines change.

# 20. What perception gains from this approach

## It gains focus

It does not have to close goals or plan the whole navigation.

## It gains clarity

It can focus on:

* layout

* local shortlist

* immediate gain

* strategic return

* visual recovery

## It gains flexibility

It can have:

* heuristic executor

* LLM-rich executor

* local validation metadata

without becoming the final arbiter.

# 21. What validation gains from this approach

## It gains precision

It does not have to invent global strategy.

## It gains discipline

It can evaluate:

* carrier

* document family

* year

* scope

* matched conditions

without mixing with edge selection or branching.

## It gains reuse

It can be used from:

* opened artifact

* downloaded artifact

* inline content

* `validate_current_content`

as a formal semantic-closure capability.

# 22. What role `NodeView` plays in making this work

`NodeView` is the interface that prevents all of this from becoming a disaster.

## Because without `NodeView`

The decider would have to read separately:

* raw runtime

* raw perception

* raw validation

* findings

* path

* restrictions

* raw candidates

## With `NodeView`

All of that enters a single local decision surface.

## Conclusion

`NodeView` is the piece that allows the decider to be the boss **without turning into a coupling monster**.

# 23. Risks of this approach

## 1. The decider may become too central

If you start putting too much logic into it that actually belongs to perception or validation, you lose the healthy hierarchy and drift back into a monolith.

## 2. `NodeView` may become too bloated

If you add too many signals without discipline, the decider loses clarity and the cognitive interface gets dirty.

## 3. There may be misalignment between subroutines

For example:

* perception suggests validating,

* validation says no,

* the decider misinterprets the combination.

That does not invalidate the approach, but it does require the contracts to be very well defined.

## 4. The conceptual wiring needs good documentation

If you do not document clearly who is in charge and who is advisory, then later it starts to look as if everything does everything.

And no: here there is a fairly clear hierarchy worth preserving.

# 24. How to keep this approach healthy

## Rule 1

Do not let perception make final decisions.

## Rule 2

Do not let validation turn into global navigation strategy.

## Rule 3

Keep the decider as a coordinator of signals, not as the executor of everything.

## Rule 4

Keep `NodeView` as a useful local projection, not as a full runtime dump.

## Rule 5

Make subroutines expose clear, typed outputs.

That allows the decider to arbitrate without guessing.

# 25. How to read this architecture as a human

Recommended order:

1. `NodeView` and `NodeViewBuilder`

2. navigation perception

3. validation state + validation executor

4. decider

5. runtime guardrails

That lets you see:

* what the decider sees,

* what the subroutines contribute,

* and how the decider integrates those pieces.

# 26. How to read this architecture as an AGI

## Objective

Understand the hierarchy between tactical coordination and specialized capabilities.

## Procedure

### Step 1

Identify the decider as the only layer with authority to choose the next action.

### Step 2

Identify navigation perception as the local navigational-reading subroutine.

### Step 3

Identify document validation as the formal local-evidence evaluation subroutine.

### Step 4

Observe how both are projected into `NodeView` or into the state consumed by the decider.

### Step 5

Clearly distinguish between:

* local signals,

* formal validation,

* and global tactical decision.

# 27. Executive summary

The architecture of `graph_mapper_agent` treats the decider as the central tactical coordinator of the local cycle. Navigation perception and document validation are not final authorities or global strategy engines: they are specialized subroutines that produce structured signals about the current node. Perception contributes a local reading of the navigable space — layout, shortlist, immediate gain, strategic return, and current node match — while validation contributes a formal evaluation of local evidence against pending goal conditions — carrier, family, year, scope, and matched conditions.

The great advantage of this approach is that it separates three distinct cognitive operations: **seeing**, **evaluating**, and **choosing**. Perception sees locally. Validation evaluates the evidence semantically. The decider chooses the next action by integrating those outputs inside `NodeView`, together with the rest of the tactical context. This improves interpretability, LLM control, modularity, grounding, and fallback capacity per subroutine, while avoiding a single monolithic call carrying the full responsibility of the agent.

The most important idea can be summarized like this:

the decider is the boss of local action; perception and validation are specialists that inform it, not replace it.

# 28. Ultra-summary

## What the decider is

The tactical coordinator that chooses the next action.

## What perception is

The subroutine that reads the node locally as a navigable space.

## What validation is

The subroutine that evaluates whether local evidence satisfies goal conditions.

## How they connect

```text
perception + validation + local runtime context
    -> NodeView
    -> decider
```

## Central advantage

Separating seeing, validating, and deciding makes the system more robust, modular, interpretable, and controllable.
