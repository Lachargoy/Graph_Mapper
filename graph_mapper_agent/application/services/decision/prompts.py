from __future__ import annotations
#graph_mapper_agent/application/services/decision/prompts.py
from graph_mapper_agent.application.services.decision.search_helpers import (
    is_authorized_search_host,
)
from graph_mapper_agent.domain.view import NodeView


def build_decision_prompt(node_view: NodeView) -> str:
    lines: list[str] = []

    lines.append("You are an expert structured web-navigation decision-maker.")
    lines.append("Choose the next most useful action with real progress and minimal waste.")
    lines.append("Respond only with an allowed action and valid JSON.")
    lines.append("")

    lines.append("DECISION RULES:")
    lines.append("- Use refine_navigation_perception if you need a richer local reading of the current node before choosing an edge.")
    lines.append("- If can_refine_navigation_perception is false, DO NOT choose refine_navigation_perception.")
    lines.append("- Use validate_current_content when the current local evidence can already be formally validated without navigating.")
    lines.append("- Use search_with_text when the current node has a visible search field and that can reduce the exploration space better than blindly following ambiguous candidates.")
    lines.append("- search_with_text only applies if AVAILABLE SEARCH TARGETS is not empty.")
    lines.append("- search_with_text does not use edge_id.")
    lines.append("- For search_with_text you must include search_target_id and query_text.")
    lines.append("- Do not use search_with_text to repeat an identical query already tried on this node unless there is new local evidence.")
    lines.append("- If there is already a visible candidate strongly aligned with a pending condition, normally prioritize follow_edge or open_artifact over search_with_text.")
    lines.append("- Build query_text using distinctive goal terms: year, document type, document name, or visible keywords from pending conditions.")
    lines.append("- download_artifact is only for a real direct artifact, normally a final .pdf URL or delivery_mode=direct.")
    lines.append("- If the persistence policy is on_validation, avoid early download_artifact unless downloading is strictly necessary to access the evidence.")
    lines.append("- If the target URL is HTML/index/listing, normally use follow_edge.")
    lines.append("- Do not confuse a PDF index/listing with a final downloadable artifact.")
    lines.append("- Reaching a PDF sheet does not imply global success.")
    lines.append("- If there is no real progress available, use mark_exhausted.")
    lines.append("- Avoid repeating already useless paths or rejected edge_id values.")
    lines.append("- IMPORTANT: you may only choose an edge_id that appears in AVAILABLE CANDIDATES.")
    lines.append("- DO NOT choose edge_id from RECOVERABLE CHOICE POINTS. That is lateral context, not the immediate action space.")
    lines.append("- NAVIGATION PERCEPTION LOCAL perceived_candidate entries are not actionable by themselves unless their edge_id also appears in AVAILABLE CANDIDATES.")
    lines.append("- Use NAVIGATION PERCEPTION LOCAL as a prioritization signal, not as an independent operational list.")
    lines.append("- If perception suggests promising candidates but they do not appear in AVAILABLE CANDIDATES, use that signal to decide between refine_navigation_perception, follow_edge over visible candidates, or mark_exhausted.")
    lines.append("- Use success only if there is already enough evidence that the formal goal has been satisfied.")
    lines.append("- Formal documentary satisfaction must come from DOCUMENT VALIDATION when available; navigation_perception does not close documentary goals.")
    lines.append("- Do not resolve pending conditions in fixed narrative order; prioritize the action with the highest probable gain on pending conditions and the lowest waste.")
    lines.append("- If the current node can already satisfy a pending condition with high probability, prioritize capturing that progress before switching branches.")
    lines.append("- Prefer actions that can resolve one or more pending conditions immediately or with shorter structural distance.")
    lines.append("")

    lines.append("DOCUMENT VALIDATION:")
    if node_view.goal_validation is None:
        lines.append("- none")
    else:
        lines.append(f"- available: {node_view.goal_validation.available}")
        lines.append(f"- target_kind: {_sanitize_prompt_text(node_view.goal_validation.target_kind, max_len=60)}")
        lines.append(f"- validation_status: {_sanitize_prompt_text(node_view.goal_validation.validation_status, max_len=40)}")
        lines.append(f"- document_family: {_sanitize_prompt_text(node_view.goal_validation.document_family, max_len=60)}")
        lines.append(f"- confidence: {node_view.goal_validation.confidence}")
        lines.append(f"- source_action: {_sanitize_prompt_text(node_view.goal_validation.source_action, max_len=40)}")
        lines.append(f"- recommended_next_step: {_sanitize_prompt_text(node_view.goal_validation.recommended_next_step, max_len=80)}")
        lines.append(f"- can_revalidate_current_node: {node_view.goal_validation.can_revalidate_current_node}")
        lines.append(f"- revalidate_reason: {_sanitize_prompt_text(node_view.goal_validation.revalidate_reason, max_len=160)}")
        lines.append(f"- summary: {_sanitize_prompt_text(node_view.goal_validation.summary, max_len=220)}")
    lines.append("")

    lines.append("ACTIVE GOAL:")
    lines.append(_sanitize_prompt_text(node_view.goal_context, max_len=500) or "Explore with structured progress.")
    if node_view.scope_strategy:
        lines.append(f"- scope_strategy: {_sanitize_prompt_text(node_view.scope_strategy, max_len=220)}")
    lines.append("")

    lines.append("SEARCH ANCHOR:")
    if node_view.anchor is None:
        lines.append("- none")
    else:
        lines.append(f"- anchor_url: {node_view.anchor.anchor_url}")
        lines.append(f"- root_node_id: {node_view.anchor.root_node_id}")
        lines.append(f"- label: {_sanitize_prompt_text(node_view.anchor.label, max_len=140) or ''}")
    lines.append("")

    lines.append("ACTIVE PATH:")
    if node_view.active_path is None:
        lines.append("- none")
    else:
        lines.append(f"- current_url: {node_view.active_path.current_url}")
        lines.append(f"- path_depth: {node_view.active_path.path_depth}")
        lines.append(f"- semantic_prefix: {_sanitize_text_tuple(node_view.active_path.semantic_prefix, max_items=4, max_item_len=120)}")
    lines.append("")

    lines.append("PATH CONTEXT:")
    if node_view.path_context is None:
        lines.append("- none")
    else:
        lines.append(f"- current_url: {node_view.path_context.current_url}")
        lines.append(f"- arrived_from_url: {_sanitize_prompt_text(node_view.path_context.arrived_from_url, max_len=160)}")
        lines.append(f"- path_depth: {node_view.path_context.path_depth}")
        lines.append(f"- recoverable_choice_points: {node_view.path_context.recoverable_choice_points}")
    lines.append("")

    lines.append("CURRENT NODE:")
    lines.append(f"- node_id: {node_view.node_id}")
    lines.append(f"- url: {node_view.url}")
    lines.append(f"- title: {_sanitize_prompt_text(node_view.title, max_len=140) or ''}")
    lines.append(f"- page_type: {node_view.page_type}")
    lines.append(f"- page_type_confidence: {node_view.page_type_confidence}")
    lines.append(f"- visited_count: {node_view.visited_count}")
    lines.append(f"- exploration_ratio: {node_view.exploration_ratio:.2f}")
    lines.append(f"- useful_ratio: {node_view.useful_ratio:.2f}")
    lines.append(f"- can_refine_navigation_perception: {node_view.can_refine_navigation_perception}")
    lines.append(f"- refine_navigation_perception_reason: {_sanitize_prompt_text(node_view.refine_navigation_perception_reason, max_len=160)}")
    lines.append(f"- can_validate_current_content: {node_view.can_validate_current_content}")
    lines.append(f"- validate_current_content_reason: {_sanitize_prompt_text(node_view.validate_current_content_reason, max_len=160)}")
    lines.append("")

    lines.append("AVAILABLE SEARCH TARGETS:")
    if not getattr(node_view, "search_targets", ()):
        lines.append("- no visible search targets")
    else:
        lines.append(f"- search_capability_available: {getattr(node_view, 'search_capability_available', False)}")
        lines.append(
            f"- current_search_history: "
            f"{_sanitize_text_tuple(getattr(node_view, 'current_search_history', ()), max_items=5, max_item_len=80)}"
        )
        for item in node_view.search_targets[:3]:
            lines.append(
                f"- search_target_id={item.search_target_id} | "
                f"label={_sanitize_prompt_text(item.label, max_len=80)!r} | "
                f"placeholder={_sanitize_prompt_text(item.placeholder, max_len=80)!r} | "
                f"name={_sanitize_prompt_text(item.name, max_len=50)!r} | "
                f"input_type={_sanitize_prompt_text(item.input_type, max_len=20)!r} | "
                f"same_host={item.same_host} | "
                f"confidence={item.confidence}"
            )
    lines.append("")

    lines.append("LOCAL NAVIGATION PERCEPTION:")
    if node_view.navigation_perception is None:
        lines.append("- none")
    else:
        lines.append(f"- status: {node_view.navigation_perception.status}")
        lines.append(f"- confidence: {node_view.navigation_perception.confidence}")
        lines.append(f"- layout_kind: {node_view.navigation_perception.layout_kind}")
        lines.append(f"- recommended_next_step: {_sanitize_prompt_text(node_view.navigation_perception.recommended_next_step, max_len=120)}")
        lines.append(f"- navigation_frame_detected: {node_view.navigation_perception.navigation_frame_detected}")
        lines.append(f"- content_frame_detected: {node_view.navigation_perception.content_frame_detected}")
        lines.append(f"- visible_candidate_count: {node_view.navigation_perception.visible_candidate_count}")
        lines.append(f"- produced_meaningful_delta: {node_view.navigation_perception.produced_meaningful_delta}")
        lines.append(f"- goal_slice_exhausted: {node_view.navigation_perception.goal_slice_exhausted}")
        lines.append(f"- goal_slice_exhaustion_reason: {_sanitize_prompt_text(node_view.navigation_perception.goal_slice_exhaustion_reason, max_len=160)}")
        lines.append(f"- immediate_condition_gain: {node_view.navigation_perception.immediate_condition_gain}")
        lines.append(f"- best_immediate_condition_labels: {_sanitize_text_tuple(node_view.navigation_perception.best_immediate_condition_labels, max_items=4, max_item_len=80)}")
        lines.append(f"- current_node_document_family: {_sanitize_prompt_text(node_view.navigation_perception.current_node_document_family, max_len=60)}")
        lines.append(f"- current_node_supports_condition_labels: {_sanitize_text_tuple(node_view.navigation_perception.current_node_supports_condition_labels, max_items=4, max_item_len=80)}")
        lines.append(f"- current_node_match_confidence: {node_view.navigation_perception.current_node_match_confidence}")
        lines.append(f"- current_node_match_rationale: {_sanitize_prompt_text(node_view.navigation_perception.current_node_match_rationale, max_len=160)}")
        lines.append(f"- can_refine_navigation_perception: {node_view.navigation_perception.can_refine_navigation_perception}")
        lines.append(f"- refine_navigation_perception_reason: {_sanitize_prompt_text(node_view.navigation_perception.refine_navigation_perception_reason, max_len=160)}")
        lines.append(f"- summary: {_sanitize_prompt_text(node_view.navigation_perception.summary, max_len=240)}")
        lines.append("- perceived_candidate = local prioritization signal; not automatically eligible.")
        for item in node_view.navigation_perception.top_candidate_observations[:3]:
            lines.append(
                f"- perceived_candidate edge_id={item.edge_id} | "
                f"label={_sanitize_prompt_text(item.label, max_len=100)!r} | "
                f"url={_sanitize_prompt_text(item.url, max_len=140)!r} | "
                f"score={item.score} | "
                f"supports_conditions={_sanitize_text_tuple(item.supports_condition_labels, max_items=3, max_item_len=80)} | "
                f"target_document_kind_match={_sanitize_prompt_text(item.target_document_kind_match, max_len=60)} | "
                f"temporal_match={_sanitize_text_tuple(item.temporal_match, max_items=4, max_item_len=40)} | "
                f"progress_likelihood={_sanitize_prompt_text(item.progress_likelihood, max_len=20)} | "
                f"is_intra_page_anchor={item.is_intra_page_anchor} | "
                f"rationale={_sanitize_prompt_text(item.rationale, max_len=100)}"
            )
    lines.append("")

    lines.append("STRATEGIC ANCHOR:")
    if node_view.strategic_return_point is None:
        lines.append("- none")
    else:
        lines.append(
            f"- node_id={node_view.strategic_return_point.node_id} | "
            f"priority={node_view.strategic_return_point.priority} | "
            f"supports={_sanitize_text_tuple(node_view.strategic_return_point.supports_condition_ids, max_items=3, max_item_len=12)} | "
            f"kind={_sanitize_prompt_text(node_view.strategic_return_point.kind, max_len=24)} | "
            f"url={_sanitize_prompt_text(node_view.strategic_return_point.url, max_len=140)!r}"
        )
    lines.append("")

    lines.append("LOCAL MEMORY:")
    lines.append(f"- summary: {_sanitize_prompt_text(node_view.memory.local_summary, max_len=260)}")
    lines.append(f"- active_hypothesis: {_sanitize_prompt_text(node_view.memory.active_hypothesis, max_len=180)}")
    lines.append(f"- next_hints: {_sanitize_text_tuple(node_view.memory.next_hints, max_items=4, max_item_len=90)}")
    lines.append(f"- avoid_hints: {_sanitize_text_tuple(node_view.memory.avoid_hints, max_items=4, max_item_len=90)}")
    lines.append("")

    lines.append("TACTICAL SCRATCHPAD:")
    if node_view.scratchpad is None:
        lines.append("- none")
    else:
        lines.append(f"- working_plan: {_sanitize_prompt_text(node_view.scratchpad.working_plan, max_len=650)}")
        lines.append(f"- tactical_observations: {_sanitize_prompt_text(node_view.scratchpad.tactical_observations, max_len=850)}")
        lines.append(f"- notes: {_sanitize_text_tuple(node_view.scratchpad.notes, max_items=5, max_item_len=120)}")
    lines.append("")

    lines.append("ACTIVE GOAL PROGRESS:")
    if node_view.goal_progress is None:
        lines.append("- none")
    else:
        lines.append(f"- intent: {_sanitize_prompt_text(node_view.goal_progress.intent, max_len=220)}")
        lines.append(f"- active_proposal_id: {node_view.goal_progress.active_proposal_id}")
        lines.append(f"- active_proposal_summary: {_sanitize_prompt_text(node_view.goal_progress.active_proposal_summary, max_len=220)}")
        lines.append(f"- proposal_status: {_sanitize_prompt_text(node_view.goal_progress.proposal_status, max_len=60)}")
        lines.append(
            f"- condition_totals: satisfied={node_view.goal_progress.satisfied_conditions} pending={node_view.goal_progress.pending_conditions}"
        )
        for condition in node_view.goal_progress.conditions[:6]:
            lines.append(
                f"- condition_id={condition.condition_id} | "
                f"label={_sanitize_prompt_text(condition.label, max_len=90)!r} | "
                f"status={condition.status} | "
                f"requiredness={condition.requiredness} | "
                f"target_kind={_sanitize_prompt_text(condition.target_kind, max_len=60)} | "
                f"year={condition.year} | "
                f"matched={len(condition.matched_finding_ids)}/{condition.min_count}"
            )
    lines.append("")

    lines.append("RELEVANT FORMAL FINDINGS:")
    if node_view.relevant_findings is None or not node_view.relevant_findings.items:
        lines.append("- no visible formal findings")
    else:
        for item in node_view.relevant_findings.items[:5]:
            lines.append(
                f"- finding_id={item.finding_id} | "
                f"label={_sanitize_prompt_text(item.label, max_len=90)!r} | "
                f"year={item.year} | "
                f"document_family={_sanitize_prompt_text(item.document_family, max_len=60)} | "
                f"source_url={_sanitize_prompt_text(item.source_url, max_len=140)}"
            )
    lines.append("")

    lines.append("ARRIVAL CONTEXT:")
    if node_view.arrival is None:
        lines.append("- none")
    else:
        lines.append(
            f"- via_edge_id={node_view.arrival.via_edge_id} | "
            f"arrival_depth={node_view.arrival.arrival_depth} | "
            f"is_reentry={node_view.arrival.is_reentry}"
        )
    lines.append("")

    lines.append("RECOVERABLE CHOICE POINTS:")
    lines.append("- this is lateral memory for resuming scope, not eligible edges in this turn")
    if node_view.choice_points is None or not node_view.choice_points.top_items:
        lines.append("- no visible recoverable alternatives")
    else:
        lines.append(f"- total_count: {node_view.choice_points.total_count}")
        for item in node_view.choice_points.top_items[:3]:
            lines.append(
                f"- choice_point_id={item.choice_point_id} | "
                f"target_url={_sanitize_prompt_text(item.target_url, max_len=160)!r} | "
                f"priority={item.priority} | "
                f"discovery_reason={_sanitize_prompt_text(item.discovery_reason, max_len=90)}"
            )
    lines.append("")

    lines.append("RESTRICTIONS:")
    if not node_view.restrictions:
        lines.append("- none")
    else:
        for restriction in node_view.restrictions[:8]:
            lines.append(f"- {_sanitize_prompt_text(restriction, max_len=120)}")
    lines.append("")

    lines.append("AVAILABLE CANDIDATES:")
    lines.append("- this is the real operational list of edge_id values eligible in this turn")
    if not node_view.candidates:
        lines.append("- no eligible candidates")
    else:
        for c in node_view.candidates[:8]:
            lines.append(
                f"- edge_id={c.edge_id} | "
                f"label={_sanitize_prompt_text(c.label, max_len=120)!r} | "
                f"target_url={_sanitize_prompt_text(c.target_url, max_len=160)!r} | "
                f"attempts={c.attempt_count} | "
                f"reason={_sanitize_prompt_text(c.reason, max_len=80)} | "
                f"hint={_sanitize_prompt_text(c.hint, max_len=80)}"
            )
    lines.append("")

    lines.append("ALLOWED ACTIONS:")
    lines.append(
        f"- refine_navigation_perception"
        f"{'' if node_view.can_refine_navigation_perception else ' (disabled)'}"
    )
    lines.append(
        f"- validate_current_content"
        f"{'' if node_view.can_validate_current_content else ' (disabled)'}"
    )
    lines.append(
        f"- search_with_text"
        f"{'' if getattr(node_view, 'search_capability_available', False) and is_authorized_search_host(node_view.url, node_view.anchor.anchor_url if node_view.anchor else None) else ' (disabled: search only allowed on search engine host)'}"
    )
    lines.append("- follow_edge")
    lines.append("- download_artifact")
    lines.append("- open_artifact")
    lines.append("- mark_exhausted")
    lines.append("- success")
    lines.append("")

    lines.append("OUTPUT:")
    lines.append("- Respond ONLY in JSON.")
    lines.append("- If you choose follow_edge, download_artifact, or open_artifact, include edge_id.")
    lines.append("- If you choose search_with_text, include search_target_id and query_text.")
    lines.append("- edge_id must come exclusively from AVAILABLE CANDIDATES.")
    lines.append("- refine_navigation_perception does not use edge_id and does not navigate; it only refines current-node context.")
    lines.append("- validate_current_content does not use edge_id; it validates the local evidence already available in the current node.")
    lines.append("- search_with_text does not use edge_id; it interacts with the visible search target on the current node.")
    lines.append("- Use decision_rationale to justify the chosen action.")
    lines.append("- Use scratchpad_update only when you want to update the tactical scratchpad.")
    lines.append('- Format: {"action":"...","edge_id":"<id or null>","search_target_id":"<id or null>","query_text":"<text or null>","decision_rationale":"<brief>","confidence":0.0,"scratchpad_update":{"working_plan":"...","tactical_observations":"..."}}')

    return "\n".join(lines)


def build_decision_prompt_v2(node_view: NodeView) -> str:
    lines: list[str] = []

    lines.append("You are an expert structured web-navigation decision-maker.")
    lines.append("Choose the next most useful action with real progress and minimal waste.")
    lines.append("Respond only with an allowed action and valid JSON.")
    lines.append("")

    lines.append("RULES:")
    lines.append("- Use refine_navigation_perception if local reading is still missing or the current node remains ambiguous.")
    lines.append("- If can_refine_navigation_perception=false, do not choose refine_navigation_perception.")
    lines.append("- Use validate_current_content only to evaluate the local evidence of the current node against pending goal conditions.")
    lines.append("- If can_validate_current_content=false, do not choose validate_current_content.")
    lines.append("- validate_current_content is NOT for comparing, inspecting, or ranking visible child candidates; it only evaluates the current node.")
    lines.append("- If the current node is an index/listing/hub/calendar and there are directly visible candidates well aligned with a pending condition, normally prioritize follow_edge or download_artifact over validate_current_content.")
    lines.append("- If the current node already looks like an inline terminal document or terminal artifact, and it can confirm or reject a pending condition, prioritize validate_current_content.")
    lines.append("- Use search_with_text when the current node has a visible search field and that can reduce the exploration space better than following ambiguous candidates.")
    lines.append("- search_with_text only applies if AVAILABLE SEARCH TARGETS is not empty.")
    lines.append("- search_with_text does not use edge_id.")
    lines.append("- For search_with_text you must include search_target_id and query_text.")
    lines.append("- Do not repeat an identical query already tried on this node unless there is new local evidence.")
    lines.append("- If there is already a visible candidate strongly aligned with a pending condition, normally prioritize follow_edge or open_artifact over search_with_text.")
    lines.append("- download_artifact is only for a real direct artifact, normally .pdf or delivery_mode=direct.")
    lines.append("- With artifact_persistence_mode=on_validation, normally validate first and download later if the evidence was accepted.")
    lines.append("- open_artifact only when it is already appropriate to open the current artifact, not to invent navigation.")
    lines.append("- If the destination is HTML/index/listing, normally use follow_edge.")
    lines.append("- You may only choose edge_id values from AVAILABLE CANDIDATES.")
    lines.append("- Never choose edge_id from RECOVERABLE CHOICE POINTS.")
    lines.append("- perceived_candidate items are not eligible by themselves; use them only as signals to prioritize AVAILABLE CANDIDATES or decide refine_navigation_perception.")
    lines.append("- If there is no real progress, use mark_exhausted.")
    lines.append("- Use success only if the formal goal has already been satisfied.")
    lines.append("- If DOCUMENT VALIDATION exists, that is the formal source for documentary closure; navigation_perception only prioritizes navigation.")
    lines.append("- Prioritize the highest probable gain over pending conditions with the least waste.")
    lines.append("- If a pending condition can likely be resolved locally, prioritize it.")
    lines.append("- If you can already formally close a pending condition on this node or with an immediately visible candidate, do that before pivoting to another branch.")
    lines.append("- Do not use refine_navigation_perception to delay an already reachable closure.")
    lines.append("- Avoid candidates whose visible year or type contradict the pending condition; do not chase 2026 annexes for a 2025 condition or equivalents.")
    lines.append("- If DOCUMENT VALIDATION was already invalid or inconclusive on the same local evidence and there is no clear new evidence, do not repeat validate_current_content out of inertia.")
    lines.append("- If the current node has directly visible artifact candidates that already support a pending condition, do not use validate_current_content on the hub unless the hub content itself can formally satisfy that condition.")
    lines.append("")

    lines.append("OPERATIONAL INTERPRETATION:")
    lines.append("- A node may be HTML and still be useful terminal evidence, for example a news article, official notice, official note, or written transcript.")
    lines.append("- A node may contain local text and still only be a documentary hub; in that case validate_current_content is rarely the best action.")
    lines.append("- If the current node is a broad hub/listing and there is a visible search field, search_with_text may be better than follow_edge when a specific query drastically reduces the space.")
    lines.append("- Always ask yourself: can the current node satisfy a pending condition by itself, or does it only distribute links toward better evidence?")
    lines.append("")

    lines.append("DOCUMENT VALIDATION:")
    if node_view.goal_validation is None:
        lines.append("- none")
    else:
        lines.append(f"- available={node_view.goal_validation.available}")
        lines.append(f"- target_kind={_sanitize_prompt_text(node_view.goal_validation.target_kind, max_len=40)}")
        lines.append(f"- validation_status={_sanitize_prompt_text(node_view.goal_validation.validation_status, max_len=30)}")
        lines.append(f"- document_family={_sanitize_prompt_text(node_view.goal_validation.document_family, max_len=40)}")
        lines.append(f"- confidence={node_view.goal_validation.confidence}")
        lines.append(f"- source_action={_sanitize_prompt_text(node_view.goal_validation.source_action, max_len=30)}")
        lines.append(f"- can_revalidate_current_node={node_view.goal_validation.can_revalidate_current_node}")
        lines.append(f"- revalidate_reason={_sanitize_prompt_text(node_view.goal_validation.revalidate_reason, max_len=100)}")
        lines.append(f"- summary={_sanitize_prompt_text(node_view.goal_validation.summary, max_len=140)}")
    lines.append("")

    lines.append("GOAL:")
    lines.append(_sanitize_prompt_text(node_view.goal_context, max_len=360) or "Explore with structured progress.")
    lines.append("")

    lines.append("STRUCTURAL CONTEXT:")
    anchor_url = None if node_view.anchor is None else node_view.anchor.anchor_url
    current_url = None if node_view.active_path is None else node_view.active_path.current_url
    path_depth = None if node_view.active_path is None else node_view.active_path.path_depth
    arrived_from_url = None if node_view.path_context is None else node_view.path_context.arrived_from_url
    recoverable_choice_points = (
        None if node_view.path_context is None else node_view.path_context.recoverable_choice_points
    )
    lines.append(f"- anchor_url={_sanitize_prompt_text(anchor_url, max_len=140)}")
    lines.append(f"- current_url={_sanitize_prompt_text(current_url, max_len=140)}")
    lines.append(f"- path_depth={path_depth}")
    lines.append(f"- arrived_from_url={_sanitize_prompt_text(arrived_from_url, max_len=140)}")
    lines.append(f"- recoverable_choice_points={recoverable_choice_points}")
    lines.append("")

    lines.append("CURRENT NODE:")
    lines.append(f"- node_id={node_view.node_id}")
    lines.append(f"- page_type={node_view.page_type} ({node_view.page_type_confidence})")
    lines.append(f"- visited_count={node_view.visited_count}")
    lines.append(f"- exploration_ratio={node_view.exploration_ratio:.2f}")
    lines.append(f"- useful_ratio={node_view.useful_ratio:.2f}")
    lines.append(f"- can_refine_navigation_perception={node_view.can_refine_navigation_perception}")
    lines.append(f"- refine_navigation_perception_reason={_sanitize_prompt_text(node_view.refine_navigation_perception_reason, max_len=120)}")
    lines.append(f"- can_validate_current_content={node_view.can_validate_current_content}")
    lines.append(f"- validate_current_content_reason={_sanitize_prompt_text(node_view.validate_current_content_reason, max_len=140)}")
    lines.append("")

    lines.append("AVAILABLE SEARCH TARGETS:")
    if not getattr(node_view, "search_targets", ()):
        lines.append("- no visible search targets")
    else:
        lines.append(f"- search_capability_available={getattr(node_view, 'search_capability_available', False)}")
        lines.append(
            f"- current_search_history={_sanitize_text_tuple(getattr(node_view, 'current_search_history', ()), max_items=5, max_item_len=70)}"
        )
        for item in node_view.search_targets[:3]:
            lines.append(
                f"- search_target_id={item.search_target_id} | "
                f"label={_sanitize_prompt_text(item.label, max_len=70)!r} | "
                f"placeholder={_sanitize_prompt_text(item.placeholder, max_len=70)!r} | "
                f"name={_sanitize_prompt_text(item.name, max_len=40)!r} | "
                f"input_type={_sanitize_prompt_text(item.input_type, max_len=20)!r} | "
                f"same_host={item.same_host} | "
                f"confidence={item.confidence}"
            )
    lines.append("")

    lines.append("NAVIGATION PERCEPTION:")
    if node_view.navigation_perception is None:
        lines.append("- none")
    else:
        lines.append(f"- layout_kind={node_view.navigation_perception.layout_kind}")
        lines.append(
            f"- recommended_next_step={_sanitize_prompt_text(node_view.navigation_perception.recommended_next_step, max_len=90)}"
        )
        lines.append(f"- visible_candidate_count={node_view.navigation_perception.visible_candidate_count}")
        lines.append(f"- goal_slice_exhausted={node_view.navigation_perception.goal_slice_exhausted}")
        lines.append(f"- immediate_condition_gain={node_view.navigation_perception.immediate_condition_gain}")
        lines.append(
            f"- best_immediate_condition_labels={_sanitize_text_tuple(node_view.navigation_perception.best_immediate_condition_labels, max_items=3, max_item_len=50)}"
        )
        lines.append(f"- can_refine_navigation_perception={node_view.navigation_perception.can_refine_navigation_perception}")
        lines.append(
            f"- refine_navigation_perception_reason={_sanitize_prompt_text(node_view.navigation_perception.refine_navigation_perception_reason, max_len=120)}"
        )
        lines.append(
            f"- summary={_sanitize_prompt_text(node_view.navigation_perception.summary, max_len=160)}"
        )
        for item in node_view.navigation_perception.top_candidate_observations[:3]:
            lines.append(
                f"- perceived_candidate edge_id={item.edge_id} | "
                f"score={item.score} | "
                f"supports_conditions={_sanitize_text_tuple(item.supports_condition_labels, max_items=3, max_item_len=40)} | "
                f"progress_likelihood={_sanitize_prompt_text(item.progress_likelihood, max_len=20)}"
            )
    lines.append("")

    lines.append("STRATEGIC ANCHOR:")
    if node_view.strategic_return_point is None:
        lines.append("- none")
    else:
        lines.append(
            f"- node_id={node_view.strategic_return_point.node_id} | "
            f"priority={node_view.strategic_return_point.priority} | "
            f"supports={_sanitize_text_tuple(node_view.strategic_return_point.supports_condition_ids, max_items=3, max_item_len=12)} | "
            f"kind={_sanitize_prompt_text(node_view.strategic_return_point.kind, max_len=24)} | "
            f"url={_sanitize_prompt_text(node_view.strategic_return_point.url, max_len=120)!r}"
        )
    lines.append("")

    lines.append("GOAL PROGRESS:")
    if node_view.goal_progress is None:
        lines.append("- none")
    else:
        lines.append(
            f"- satisfied={node_view.goal_progress.satisfied_conditions} pending={node_view.goal_progress.pending_conditions}"
        )
        for condition in node_view.goal_progress.conditions[:6]:
            matched_count = len(getattr(condition, "matched_finding_ids", ()) or ())
            required_count = max(1, getattr(condition, "min_count", 1) or 1)

            lines.append(
                f"- {condition.condition_id} | "
                f"status={condition.status} | "
                f"matched={matched_count}/{required_count} | "
                f"target_kind={_sanitize_prompt_text(condition.target_kind, max_len=48)} | "
                f"year={condition.year}"
            )
    lines.append("")

    lines.append("RELEVANT FINDINGS:")
    if node_view.relevant_findings is None or not node_view.relevant_findings.items:
        lines.append("- none")
    else:
        for item in node_view.relevant_findings.items[:4]:
            lines.append(
                f"- finding_id={item.finding_id} | "
                f"year={item.year} | "
                f"document_family={_sanitize_prompt_text(item.document_family, max_len=40)}"
            )
    lines.append("")

    if node_view.scratchpad and (
        node_view.scratchpad.working_plan
        or node_view.scratchpad.tactical_observations
        or node_view.scratchpad.notes
    ):
        lines.append("SCRATCHPAD:")
        lines.append(
            f"- working_plan={_sanitize_prompt_text(node_view.scratchpad.working_plan, max_len=260)}"
        )
        lines.append(
            f"- tactical_observations={_sanitize_prompt_text(node_view.scratchpad.tactical_observations, max_len=320)}"
        )
        lines.append(
            f"- notes={_sanitize_text_tuple(node_view.scratchpad.notes, max_items=3, max_item_len=90)}"
        )
        lines.append("")

    lines.append("RECOVERABLE CHOICE POINTS:")
    lines.append("- lateral memory, not eligible in this turn")
    if node_view.choice_points is None or not node_view.choice_points.top_items:
        lines.append("- none")
    else:
        lines.append(f"- total_count={node_view.choice_points.total_count}")
        for item in node_view.choice_points.top_items[:2]:
            lines.append(
                f"- choice_point_id={item.choice_point_id} | "
                f"target_url={_sanitize_prompt_text(item.target_url, max_len=140)!r} | "
                f"priority={item.priority}"
            )
    lines.append("")

    lines.append("RESTRICTIONS:")
    if not node_view.restrictions:
        lines.append("- none")
    else:
        for restriction in node_view.restrictions[:5]:
            lines.append(f"- {_sanitize_prompt_text(restriction, max_len=90)}")
    lines.append("")

    lines.append("AVAILABLE CANDIDATES:")
    lines.append("- this is the actual operational list of eligible edge_id values")
    if not node_view.candidates:
        lines.append("- no eligible candidates")
    else:
        for c in node_view.candidates[:8]:
            lines.append(
                f"- edge_id={c.edge_id} | "
                f"label={_sanitize_prompt_text(c.label, max_len=100)!r} | "
                f"target_url={_sanitize_prompt_text(c.target_url, max_len=140)!r} | "
                f"attempts={c.attempt_count} | "
                f"reason={_sanitize_prompt_text(c.reason, max_len=50)} | "
                f"hint={_sanitize_prompt_text(c.hint, max_len=50)}"
            )
    lines.append("")

    lines.append("ACTIONS:")
    lines.append(
        "- refine_navigation_perception"
        f"{'' if node_view.can_refine_navigation_perception else ' (disabled)'}"
    )
    lines.append(
        "- validate_current_content"
        f"{'' if node_view.can_validate_current_content else ' (disabled)'}"
    )
    lines.append(
        "- search_with_text"
        f"{'' if getattr(node_view, 'search_capability_available', False) and is_authorized_search_host(node_view.url, node_view.anchor.anchor_url if node_view.anchor else None) else ' (disabled: search only allowed on search engine host)'}"
    )
    lines.append("- follow_edge")
    lines.append("- download_artifact")
    lines.append("- open_artifact")
    lines.append("- mark_exhausted")
    lines.append("- success")
    lines.append("")

    lines.append("QUICK HEURISTIC:")
    lines.append("- Hub/listing with good visible PDFs: normally follow_edge or open_artifact; download early only if strictly necessary.")
    lines.append("- Inline terminal document or terminal artifact: normally validate_current_content.")
    lines.append("- Broad hub with visible search and many ambiguous candidates: search_with_text may be better.")
    lines.append("- If you can formally close a condition now, do it.")
    lines.append("- If there is no real local progress, mark_exhausted.")
    lines.append("")

    lines.append("OUTPUT:")
    lines.append("- JSON only.")
    lines.append("- Do not choose actions marked as (disabled).")
    lines.append("- If you choose follow_edge, download_artifact, or open_artifact, include edge_id.")
    lines.append("- If you choose search_with_text, include search_target_id and query_text.")
    lines.append("- edge_id must come exclusively from AVAILABLE CANDIDATES.")
    lines.append("- validate_current_content does not use edge_id.")
    lines.append("- search_with_text does not use edge_id.")
    lines.append('- Format: {"action":"...","edge_id":"<id or null>","search_target_id":"<id or null>","query_text":"<text or null>","decision_rationale":"<brief>","confidence":0.0,"scratchpad_update":{"working_plan":"...","tactical_observations":"..."}}')

    return "\n".join(lines)


def _sanitize_prompt_text(value: object, *, max_len: int = 1000) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    cleaned = "".join(ch for ch in text if ch.isprintable() or ch in "\n\t")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n").strip()

    if not cleaned:
        return None

    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()

    return cleaned or None


def _sanitize_text_tuple(
    values: tuple[str, ...] | tuple[object, ...],
    *,
    max_items: int = 10,
    max_item_len: int = 160,
) -> list[str]:
    sanitized: list[str] = []

    for value in values[:max_items]:
        cleaned = _sanitize_prompt_text(value, max_len=max_item_len)
        if cleaned:
            sanitized.append(cleaned)

    return sanitized