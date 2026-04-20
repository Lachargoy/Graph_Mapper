# Docs

This folder is organized into two layers:

- entry-point documentation for understanding and running the project
- deeper internal architectural reference manuals

## Entry Docs

- [overview.md](/home/luis/mapper/docs/overview.md): what `graph_mapper_agent` is, what problem it solves, and which interfaces it exposes today
- [quickstart.md](/home/luis/mapper/docs/quickstart.md): how to validate the project locally and launch its main entry points
- [architecture.md](/home/luis/mapper/docs/architecture.md): the main runtime flow and the project’s high-level architectural slices
- [goal_validation.md](/home/luis/mapper/docs/goal_validation.md): the validation subdomain, progressive passes, and how local evidence is accepted or rejected
- [node_identity_and_dom_mutation.md](/home/luis/mapper/docs/node_identity_and_dom_mutation.md): how node identity is anchored, how DOM observation feeds it, and how search-driven mutation is handled today
- [future_graph_dynamics.md](/home/luis/mapper/docs/future_graph_dynamics.md): future direction for dynamic node mutation, structural state projection, and subroutine architecture
- [reference.md](/home/luis/mapper/docs/reference.md): index of the existing internal reference manuals

## Internal Manuals

The deeper technical manuals in this folder are useful and increasingly consistent, but they still lean more toward internal architectural reference than toward polished public-facing documentation. They are strong source material, but some of them still need editorial compression and cleanup.

If the goal is to publish the repository, the recommended reading order is:

1. start with `overview.md`
2. continue with `quickstart.md`
3. use `architecture.md` as the mental model
4. then move into `reference.md` and the detailed manuals
