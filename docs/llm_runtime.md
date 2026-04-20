LLM Runtime Pipeline Reference Manual
Purpose

This document describes the full LLM pipeline inside graph_mapper_agent, from configuration loading to runtime execution, structured output validation, and extension points for new adapters or providers.

It is intended to serve as a reference for:

maintenance,
debugging,
onboarding,
publishing the codebase,
and collaborative work between humans and AI agents.

The core design idea is to clearly separate five layers:

raw configuration,
effective runtime resolution,
adapter composition,
consumption by services and use cases,
contracts and structured outputs.

When that separation is preserved, the system can:

combine multiple models in a single run,
switch providers without rewriting the domain,
add new structured output paths,
and introduce new adapters without turning the rest of the system into spaghetti with a degree in chaos.
1. System overview
Full conceptual flow
JSON / env
    -> LlmRuntimeConfig
    -> GuidedGraphMapperConfig or another operational config
    -> resolve_runtime_plan(...)
    -> ResolvedRuntimePlan
    -> build_llm_runtime(...)
    -> concrete provider adapter
    -> usable runtime
    -> runner / planner / services
    -> structured_output_registry
    -> Pydantic model
    -> validated payload
Correct intuition

The system does not take a JSON config and send it directly to the provider.

It first:

interprets the configuration,
decides which real provider corresponds to it,
degrades or adapts capabilities when needed,
resolves structured output and reasoning behavior,
builds the correct adapter,
and only then invokes the runtime.

That is why there is an important distinction between:

what the user or config requests,
what the system resolves as compatible,
what the adapter actually executes.
2. System layers
Layer 1 — Raw configuration
Main files
platform/llm/config.py
bootstrap/execution_config.py
Responsibility

Represent the declarative intent of the LLM runtime and the execution run.

What lives here
requested backend,
base URL,
default model,
API key,
timeout,
vision support,
requested structured output mode,
requested reasoning,
requested provider routing,
runtime configs per subtask,
ledger config,
operational metadata.
What does not live here
the final effective provider,
actual compatibility,
the final structured output mode,
reasoning degradation,
the concrete adapter class.
Layer 2 — Effective runtime resolution
Main files
platform/llm/resolve_runtime_plan.py
platform/llm/runtime_plan.py
platform/llm/provider_policies.py
platform/llm/capabilities.py
platform/llm/output_resolution.py
Responsibility

Transform a declarative configuration into a resolved, consistent, provider-compatible runtime plan.

Main output

ResolvedRuntimePlan

This object is the contract between the resolution layer and the composition layer.

Layer 3 — Composition and instantiation
Main files
adapters/llm/composition/runtime_factory.py
adapters/llm/runtimes/providers/*
adapters/llm/runtimes/base/*
Responsibility

Take a ResolvedRuntimePlan and return a concrete runtime ready to use.

Layer 4 — Operational consumption
Main files
bootstrap/builders/llm.py
bootstrap/runner.py
application/services/goals/planner.py
other direct consumers and use cases
Responsibility

Use the runtime inside the real execution flow of the agent.

Layer 5 — Structured outputs and contracts
Main files
adapters/llm/outputs/structured_output_registry.py
application/services/goals/planner_models.py
equivalent Pydantic contracts
Responsibility

Define which structured output the system expects and how it should be validated.

3. Base runtime configuration
File: platform/llm/config.py

This file defines LlmRuntimeConfig, which represents the base configuration of an LLM runtime.

Main fields
backend

Identifies the requested backend.

Supported values in the reviewed code:

ollama
chatopenai_direct
pydantic_ai_adapter
pydantic_ai_openrouter
openrouter_chatopenai
How it affects the runtime

This field is the main anchor used to resolve the ProviderPolicy. From this value, the system decides:

the real provider,
the runtime family,
the adapter_key,
default values,
expected capabilities.
base_url

Base URL of the backend.

How it affects the runtime
if present, it overrides the provider default;
if absent, the plan uses policy.default_base_url.
default_model

Default model to use if the request does not specify another one.

How it affects the runtime
determines the effective model in the plan;
may be replaced by the provider default if not defined.
api_key

Credential for providers that require it.

How it affects the runtime
if the provider policy declares requires_api_key=True and no API key is present, resolve_runtime_plan(...) raises an error.
timeout_seconds

Requested timeout for the call.

How it affects the runtime
travels through plan metadata;
the factory uses it, for example, for Ollama;
in the OpenAI-compatible base runtime it is used for execution timeout handling.
supports_vision

Declarative override for vision support.

How it affects the runtime

It is combined with provider-derived capabilities to determine whether message parsing may accept images and whether the runtime may operate on visual inputs.

structured_output_mode

Declarative preference for the structured output mechanism.

Valid system values:

auto
native
prompted
tool
How it affects the runtime

This is not the final value by itself. It is the initial preference. The system then passes it through resolve_output_mode(...), where the effective mode is determined based on:

provider policy,
capabilities,
whether expected_output_name is present,
whether tools were requested.
Meaning of each mode
auto

The system chooses the best compatible mechanism.

native

Use native structured output support from the provider or stack when available.

prompted

Force structured output through prompting or coercion.

tool

Use tool-style or function-style output.

Where it materializes

In the OpenAI-compatible base runtime, _configured_output_type() maps:

native -> NativeOutput
prompted -> PromptedOutput
tool -> ToolOutput
any other value, such as auto, -> returns the raw output_type directly.
enable_reasoning

Declarative flag to request reasoning.

How it affects the runtime

It does not guarantee that reasoning is actually enabled. It first passes through resolve_reasoning_policy(...), which checks whether the provider truly supports reasoning.

reasoning_effort

Requested effort level for reasoning.

How it affects the runtime

It is only preserved as effective_effort if provider capabilities say the provider supports that parameter.

reasoning_max_tokens

Requested token budget for reasoning.

How it affects the runtime

It only becomes effective if the provider supports it. Otherwise it degrades to None.

reasoning_exclude

Flag indicating whether reasoning content should be excluded or specially controlled.

How it affects the runtime

It is only preserved if the provider and capabilities support it. Otherwise it is disabled during runtime resolution.

provider_require_parameters

Declarative preference for provider routing parameters.

How it affects the runtime

It is stored in ResolvedProviderRouting.require_parameters and eventually reaches OpenAI-compatible provider settings.

provider_allow_fallbacks

Allow fallbacks between routed providers.

How it affects the runtime

It flows into the resolved plan and later into the concrete adapter settings.

provider_order

Preferred provider order for routing.

How it affects the runtime

It is used to build ResolvedProviderRouting.order and later reaches the concrete adapter.

4. Operational run configuration
File: bootstrap/execution_config.py

GuidedGraphMapperConfig represents the operational execution config and may contain several runtime configs for different subtasks.

Main fields
jurisdiction_code

Jurisdictional context of the run.

document_key

Document or thread key for the run.

timeout_seconds

Global run timeout, distinct from LLM runtime timeout.

execution_metadata

General execution metadata.

ledger_database_url

Ledger path or URL for the run.

Per-subtask runtimes
llm_runtime
navigation_perception_llm_runtime
goal_validation_llm_runtime
evidence_extraction_visual_llm_runtime
evidence_extraction_ocr_llm_runtime
How this affects runtime behavior

It does not define only one global runtime. It defines a potential mesh of runtimes per stage of the workflow.

5. Runtime inheritance and fallback across subtasks
Where it happens

In bootstrap/runner.py.

Conceptual logic
llm_runtime main
    -> navigation_perception_llm_runtime      (if present, overrides)
    -> goal_validation_llm_runtime            (if present, overrides)
    -> evidence_extraction_visual_runtime     (if present, overrides; otherwise inherits)
    -> evidence_extraction_ocr_runtime        (if present, overrides; otherwise inherits)
Human-readable interpretation
if there is no runtime for navigation perception, use the main runtime;
if there is no runtime for goal validation, use the main runtime;
if there is no visual runtime, use the goal validation runtime;
if there is no OCR runtime, use the visual runtime.
Real impact

This allows one run to use:

a large remote model for main decision-making,
a lighter one for navigation or perception,
another one specialized for validation,
and a local runtime for OCR.
6. Real hybrid JSON example

A payload like this represents a hybrid configuration:

OpenRouter/Qwen for reasoning,
OpenRouter also for perception and validation,
local Ollama for OCR.
Semantic reading
request

Describes the user goal and the agent’s operational limits.

execution

Describes the execution context and ledger.

llm_runtime

This is the general runtime for the agent. In your example, it uses OpenRouter with a large Qwen model, vision enabled, structured output set to prompted, reasoning enabled, and reasoning_exclude=true.

navigation_perception_llm_runtime

Specific override for navigation perception with another Qwen model, still keeping vision and reasoning.

goal_validation_llm_runtime

Override for goal validation using OpenRouter and a large model.

evidence_extraction_visual_llm_runtime

Override for visual extraction with OpenRouter.

evidence_extraction_ocr_llm_runtime

Local override using Ollama and glm-ocr:latest for OCR.

Architectural conclusion of the example

There is not just one LLM. There is a network of specialized runtimes inside the same run.

7. Provider policies
File: platform/llm/provider_policies.py

This file contains the declarative definition of what each provider supports and how it should be resolved.

ProviderPolicy

Important fields:

backend_names
runtime_family
provider
provider_name
adapter_key
default_base_url
default_model
requires_api_key
supports_vision
supports_reasoning
supports_provider_routing
supports_structured_output
supported_structured_output_modes
default_structured_output_mode
supports_tools
supports_structured_and_tools_together
Reviewed policies
LM Studio
runtime_family="pydantic_ai"
provider="lm_studio"
adapter_key="pydantic_ai_lm_studio"
supports vision
does not support reasoning
supports structured output in auto and prompted
default structured output: auto
OpenRouter
runtime_family="pydantic_ai"
provider="openrouter"
adapter_key="pydantic_ai_openrouter"
requires API key
supports vision
supports reasoning
supports provider routing
supports structured output in auto, native, prompted, tool
default structured output: prompted
Ollama
runtime_family="callable"
provider="ollama"
adapter_key="ollama_native"
does not require API key
supports vision
does not support reasoning
supports structured output only in prompted
does not support tools
What resolve_provider_policy(...) does

It resolves the policy from:

backend_name, or
runtime_family + provider.

That converts raw config into a concrete provider policy used by the system.

8. Runtime plan
File: platform/llm/runtime_plan.py

This file defines the types and dataclasses used by the resolved runtime plan.

Key types
RuntimeFamily
pydantic_ai
callable
ProviderKind
lm_studio
openrouter
ollama
AdapterKey
pydantic_ai_lm_studio
pydantic_ai_openrouter
ollama_native
StructuredOutputMode
auto
native
prompted
tool
EffectiveToolMode
disabled
native
OutputCombination
plain_text
structured_only
tools_only
incompatible
Key dataclasses
ResolvedProviderRouting

Stores provider order, fallback behavior, parameter requirements, and data_collection.

ResolvedReasoningPolicy

Separates what was requested from what is actually effective.

ResolvedOutputMode

Separates:

requested structured output mode,
expected output name,
requested tool mode,
effective structured output mode,
effective tool mode,
final combination,
resolution reason.
ResolvedRuntimeIdentity

Final runtime identity:

backend_name
runtime_family
provider
provider_name
adapter_key
ResolvedRuntimePlan

Central object passed to the factory:

identity
model
base_url
api_key
supports_vision
provider_routing
reasoning
output_mode
metadata
9. Runtime resolution
File: platform/llm/resolve_runtime_plan.py

This is the phase where declarative configuration becomes an effective runtime plan.

Internal flow
LlmRuntimeConfig
 -> resolve_provider_policy(...)
 -> derive_runtime_capabilities(...)
 -> resolve_output_mode(...)
 -> resolve_reasoning_policy(...)
 -> ResolvedRuntimeIdentity
 -> ResolvedProviderRouting
 -> metadata
 -> ResolvedRuntimePlan
Step 1 — Provider policy

Based on config.backend, the system resolves the concrete provider policy.

Step 2 — Capabilities

Using the policy and vision override, it derives the actual runtime capabilities.

Step 3 — Output resolution

resolve_output_mode(...) receives:

expected_output_name
requested_structured_output_mode
tools_requested
requested_tool_mode

and returns the final output resolution.

Step 4 — Effective model and URL

The system uses:

config.default_model or policy.default_model
config.base_url or policy.default_base_url
Step 5 — API key validation

If the policy requires an API key and config does not provide one, an error is raised.

Step 6 — Provider routing

The system packages provider_order, allow_fallbacks, and require_parameters into ResolvedProviderRouting.

Step 7 — Reasoning resolution

resolve_reasoning_policy(...) applies controlled degradation:

if reasoning was not requested -> it stays disabled;
if the provider does not support it -> it is disabled with an explicit reason;
if only some reasoning parameters are supported -> the supported ones are preserved and the unsupported ones are cleared.
Step 8 — Traceability metadata

The plan stores useful metadata such as:

requested backend,
resolved provider,
resolved adapter,
timeout,
requested and effective structured output,
tool mode,
requested and effective reasoning.
10. Factory and adapter composition
File: adapters/llm/composition/runtime_factory.py

The factory converts ResolvedRuntimePlan into a concrete runtime.

Internal flow
ResolvedRuntimePlan
 -> validation
 -> read adapter_key
 -> matching builder
 -> concrete provider settings
 -> concrete adapter
 -> LlmRuntimeFactoryResult
LlmRuntimeFactoryResult

Returns:

runtime
backend
provider_name
runtime_family
adapter_key
plan
What the factory validates
backend_name is not empty,
provider is not empty,
adapter_key is not empty,
model is not empty,
output_mode.combination != "incompatible",
OpenRouter has an API key when required.
Reviewed builders
LM Studio

Builds PydanticAiLmStudioSettings and then PydanticAiLmStudioAdapter.

OpenRouter

Builds PydanticAiOpenRouterSettings using:

URL,
model,
API key,
vision support,
effective structured output mode,
effective reasoning settings,
effective provider routing.
Ollama

Builds OllamaNativeSettings, including timeout read from plan.metadata.

11. Concrete providers
Folder: adapters/llm/runtimes/providers/*

This folder contains the concrete implementation for each provider.

General pattern

Each provider should define:

a provider-specific settings dataclass,
a concrete adapter class.
Reviewed case: OpenRouter
File

pydantic_ai_openrouter_adapter.py

PydanticAiOpenRouterSettings

Contains:

base_url
default_model
api_key
timeout_seconds
backend_name
supports_vision
enable_reasoning
reasoning_effort
reasoning_max_tokens
reasoning_exclude
structured_output_mode
provider_require_parameters
provider_allow_fallbacks
provider_order
PydanticAiOpenRouterAdapter

It does not reimplement everything from scratch. It translates those settings into PydanticAiOpenAiCompatibleSettings and delegates execution to PydanticAiOpenAiCompatibleAdapter.

Architectural meaning

OpenRouter follows this pattern:

OpenRouterSettings
 -> OpenAICompatibleSettings
 -> PydanticAiOpenAiCompatibleAdapter

That makes it a provider wrapper over a shared base runtime.

12. OpenAI-compatible base runtime
File: adapters/llm/runtimes/base/pydantic_ai_openai_compatible_adapter.py

This is one of the real execution cores of the system.

What it does
resolves the Pydantic output_type using the registry,
parses messages,
builds model settings,
creates a PydanticAI Agent,
executes the call,
converts the response into a uniform result,
handles errors and timeouts,
supports structured outputs, reasoning, and structured logging.
_STRUCTURED_OUTPUT_MODES

Real mapping:

native -> NativeOutput
prompted -> PromptedOutput
tool -> ToolOutput
_configured_output_type(...)

Applies the wrapper according to self._settings.structured_output_mode.

_invoke_with_pydantic_ai(...)

Main flow:

request.expected_output_name
 -> structured_output_registry.resolve_output_type(...)
 -> parse_messages(...)
 -> _build_model_settings(...)
 -> Agent(...)
 -> run
 -> build_success_result(...)
What happens if the output type is missing

If there is no registered output_type and no fallback_runtime, the system raises LlmRuntimeError with MissingOutputType.

How configuration affects this layer

Everything resolved earlier — structured output mode, reasoning, provider routing, vision support, timeout — arrives here as effective runtime settings.

13. Operational builder
File: bootstrap/builders/llm.py

This file is the operational bridge of the bootstrap layer.

Flow
LlmRuntimeConfig
 -> resolve_runtime_plan(...)
 -> build_llm_runtime(...)
 -> runtime
 -> optionally InvokeLlmWithLedgerUseCase
 -> LlmRuntimeBundle
LlmRuntimeBundle

Returns:

runtime
provider_name
invoke_llm_use_case
Why it matters

It allows the runner to obtain a usable runtime without knowing provider or factory internals.

14. Runner and operational consumption
File: bootstrap/runner.py

This is the large operational orchestrator of the agent.

What it does regarding LLMs
decides which config to use for each subtask,
builds runtimes for the main decision path, navigation perception, goal validation, and extraction,
integrates everything with the ledger,
starts the orchestrator.
Very important note

There are specific rules such as _build_generic_runtime(...), which does not build a runtime when the backend is ollama for some generic paths. That also forms part of the real behavior of the system.

15. Direct consumers outside bootstrap
File: application/services/goals/planner.py

This file shows that not everything passes through build_llm_runtime_bundle(...). There are also direct consumers of the pipeline.

Internal flow
LlmRuntimeConfig
 -> resolve_runtime_plan(...)
 -> build_llm_runtime(...)
 -> runtime
 -> invoke
 -> payload
 -> GoalPlanningOutput.model_validate(...)
Architectural conclusion

If you change config, resolution, or factory behavior, you also affect these direct consumers.

16. Structured outputs and contracts
File: adapters/llm/outputs/structured_output_registry.py

This file maps expected_output_name to concrete Pydantic models.

Flow
expected_output_name
 -> resolve_output_type(...)
 -> concrete BaseModel
Registered examples
graph_mapper_navigation_decision
graph_mapper_goal_planning
graph_mapper_planning_turn
graph_mapper_research_answer_synthesis
graph_mapper_evidence_coverage
document_validation_output
navigation_perception_output
Impact

Every new structured output path must be registered here.

File: application/services/goals/planner_models.py

Defines the structured models expected by the planner.

Reviewed models
PlannedGoalCondition
GoalPlanningOutput
PlanningTurnOutput
Impact

If you change the planner prompt or expected schema, this file is part of the contract.

17. What each major decision means for the runtime
Changing backend

Changes:

provider policy,
runtime family,
adapter_key,
defaults,
capabilities,
concrete provider.
Changing structured_output_mode

Changes:

output mode resolution,
the final wrapper (NativeOutput, PromptedOutput, ToolOutput),
compatibility with tools and Pydantic contracts.
Changing enable_reasoning

Changes:

the resolved reasoning policy,
effective provider settings,
how reasoning parameters are sent to the model.
Changing supports_vision

Changes:

capability derivation,
whether images are accepted during parsing,
whether certain subtasks can operate visually.
Changing provider_order / provider_allow_fallbacks / provider_require_parameters

Changes:

provider routing,
parameters passed into model settings,
behavior of the OpenAI-compatible adapter when relevant.
Changing expected_output_name

Changes:

which Pydantic model is resolved,
which structured output the use case expects,
and it may break parsing if the registry is not aligned.
18. How to add a new provider
Step 1 — Config

Make sure the backend can be represented in LlmRuntimeConfig.

Step 2 — Policy

Add a ProviderPolicy with:

backend_names,
runtime_family,
provider,
provider_name,
adapter_key,
defaults,
declarative capabilities.
Step 3 — Capabilities and output resolution

Confirm support for:

vision,
structured output,
reasoning,
tools.
Step 4 — Provider file

Create in runtimes/providers/:

XProviderSettings
XProviderAdapter
Step 5 — Choose a pattern

Decide whether it:

inherits from a shared base, or
is fully native.
Step 6 — Factory

Add a branch for adapter_key in runtime_factory.py.

Step 7 — Test real consumption

Test it from:

build_llm_runtime_bundle(...),
runner.py,
or a direct consumer.
Step 8 — Structured outputs if needed

Register any new contracts if that path needs them.

Step 9 — Update this manual

Always. Future-you is already annoyed if you skip it.

19. How to debug the system
If provider selection fails

Review:

config.py
provider_policies.py
resolve_runtime_plan.py
If structured output fails

Review:

output_resolution.py
structured_output_registry.py
the corresponding Pydantic contract
the OpenAI-compatible base runtime or concrete adapter
If reasoning fails

Review:

capabilities.py
resolve_runtime_plan.py
provider settings
adapter or base runtime
If a specific subtask fails

Review:

runner.py
builders/llm.py or the direct consumer
the specific use case
the factory
the provider adapter
If only one provider fails

Review:

provider policy
provider implementation file
reused base runtime
factory
20. Maintenance rules
Rule 1

Do not mix in the same change:

config or policy changes,
factory changes,
and agent logic changes,

unless it is strictly necessary.

Rule 2

If you change an expected_output_name, review:

who emits it,
who resolves it,
which model validates it.
Rule 3

If you change a provider, review:

config,
provider policy,
capabilities,
output resolution,
factory,
provider file,
base runtime.
Rule 4

If you add a new subtask, decide:

whether it inherits a runtime,
whether it needs an override,
whether it requires a new structured contract.
Rule 5

Direct consumers outside bootstrap must be documented. They are also part of the pipeline.

21. Checklist for human contributors and AI agents

Before changing anything, answer these questions:

Am I changing configuration, resolution, composition, consumption, or contracts?
Does this change affect one provider or all providers?
Am I modifying a preference or an effective resolved value?
Are structured outputs involved?
Is there another direct consumer outside bootstrap?
Do I need to update the registry?
Do I need to update the manual?
22. Executive summary

The project’s LLM pipeline transforms declarative configurations into effective runtimes, materialized through concrete adapters and consumed by specialized agent services.

The system supports multiple runtimes per subtask, so a single run can combine:

remote reasoning through OpenRouter,
vision across multiple stages,
and local OCR through Ollama.

The key to maintaining the system is understanding that each decision belongs to a different layer:

config requests,
resolution decides,
the factory builds,
the provider executes,
the consumer uses,
and the contracts validate.

If that separation is respected, the system can grow without collapsing into a hidden web of cross-layer coupling.

23. Ultra-short summary for AI agents
What the system does

Transforms LLM config into operational runtimes consumed by the agent.

Layers
config
resolution
factory
provider implementation
consumption
structured contracts
Key objects
LlmRuntimeConfig
ProviderPolicy
ResolvedRuntimePlan
adapter_key
expected_output_name
Golden rule

Do not confuse:

what was requested,
what was resolved,
what was built,
what was executed,
and what was validated.