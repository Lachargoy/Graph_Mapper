# Reference Index

This index organizes the existing internal manuals. They are useful and technically rich, but not all of them are yet in polished editorial shape.

## Main Manuals

- [node_identity_and_dom_mutation.md](/home/luis/mapper/docs/node_identity_and_dom_mutation.md): node identity, URL anchoring, DOM observation, and search-driven mutation
- [future_graph_dynamics.md](/home/luis/mapper/docs/future_graph_dynamics.md): future direction for dynamic graph modeling, structural projection, and subroutine contracts
- [goal_validation.md](/home/luis/mapper/docs/goal_validation.md): validation requests, passes, statuses, and progressive goal-oriented validation
- [navigation_perception.md](/home/luis/mapper/docs/navigation_perception.md): role, inputs, and outputs of navigation perception as a local-reading subroutine
- [decision_layer.md](/home/luis/mapper/docs/decision_layer.md): decision layer, tactical action selection, and the role of `NodeView`
- [end_to_end.md](/home/luis/mapper/docs/end_to_end.md): full decider -> executor -> updater flow
- [execution_layer.md](/home/luis/mapper/docs/execution_layer.md): execution layer and `ActionExecutionResult`
- [graph_updater.md](/home/luis/mapper/docs/graph_updater.md): graph and runtime mutation
- [llm_runtime.md](/home/luis/mapper/docs/llm_runtime.md): complete LLM runtime pipeline
- [ledger.md](/home/luis/mapper/docs/ledger.md): ledger persistence model and operations
- [web_tooling.md](/home/luis/mapper/docs/web_tooling.md): web tooling, Playwright, downloads, and artifacts
- [node_estate.md](/home/luis/mapper/docs/node_estate.md): lane transition topology
- [decider_vs_perception.md](/home/luis/mapper/docs/decider_vs_perception.md): relationship between decider, validation, and perception

## Gaps or Files That Still Need Cleanup

- some internal manuals are still longer than they need to be for public reading
- some naming inside the manuals still refers to older migration-era concepts

## Editorial Recommendation

For external publication:

1. use these files as technical source material
2. condense repeated ideas into shorter public-facing manuals
3. normalize file naming and formatting
4. keep reducing older naming inconsistencies before presenting `docs/` as fully finished

## Current Repo Conventions

The repository currently keeps its canonical runtime profiles in:

- `graph_mapper_agent/bootstrap/configs/`

The intended public set is:

- `config_qwen.json`
- `config_lm_studio.json`
- `config_ollama.json`
