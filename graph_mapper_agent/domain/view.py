from __future__ import annotations
#graph_mapper_agent/domain/view.py
from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class NodeViewCandidate:
    edge_id: str
    label: str
    target_url: str

    candidate_type: str = "unknown"
    relation: str = "unknown"
    status: str = "discovered"

    attempt_count: int = 0
    base_score: float | None = None

    resource_kind: str | None = None
    delivery_mode: str | None = None

    reason: str | None = None
    hint: str | None = None


@dataclass(slots=True, frozen=True)
class NodeViewArrival:
    from_node_id: str | None = None
    via_edge_id: str | None = None
    arrival_depth: int = 0
    arrival_mode: str = "follow"
    is_reentry: bool = False


@dataclass(slots=True, frozen=True)
class NodeViewMemory:
    local_summary: str = ""
    active_hypothesis: str | None = None
    next_hints: tuple[str, ...] = ()
    avoid_hints: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class ChoicePointViewItem:
    choice_point_id: str
    edge_id: str
    target_url: str
    priority: float = 0.0
    discovery_reason: str | None = None


@dataclass(slots=True, frozen=True)
class ChoicePointsView:
    total_count: int = 0
    top_items: tuple[ChoicePointViewItem, ...] = ()


@dataclass(slots=True, frozen=True)
class AnchorView:
    anchor_id: str
    anchor_url: str
    root_node_id: str
    label: str | None = None


@dataclass(slots=True, frozen=True)
class ActivePathView:
    anchor_url: str = ""
    current_url: str = ""
    current_node_id: str | None = None
    path_depth: int = 0
    semantic_prefix: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class PathContextView:
    current_url: str = ""
    arrived_from_url: str | None = None
    path_depth: int = 0
    recoverable_choice_points: int = 0


@dataclass(slots=True, frozen=True)
class RelevantFindingViewItem:
    finding_id: str
    label: str
    value: str = ""
    kind: str = "unknown"
    confidence: float = 0.0
    source_url: str | None = None
    year: int | None = None
    document_family: str | None = None


@dataclass(slots=True, frozen=True)
class RelevantFindingsView:
    total_count: int = 0
    items: tuple[RelevantFindingViewItem, ...] = ()


@dataclass(slots=True, frozen=True)
class TacticalScratchpadView:
    working_plan: str = ""
    tactical_observations: str = ""
    notes: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class NavigationPerceptionCandidateView:
    edge_id: str | None
    url: str
    label: str
    score: float
    rationale: str
    supports_condition_labels: tuple[str, ...] = ()
    target_document_kind_match: str | None = None
    temporal_match: tuple[str, ...] = ()
    progress_likelihood: str | None = None
    is_intra_page_anchor: bool | None = None


@dataclass(slots=True, frozen=True)
class NavigationPerceptionView:
    status: str
    confidence: float
    layout_kind: str | None = None
    recommended_next_step: str | None = None
    navigation_frame_detected: bool | None = None
    content_frame_detected: bool | None = None
    visible_candidate_count: int | None = None
    produced_meaningful_delta: bool | None = None
    goal_slice_exhausted: bool | None = None
    goal_slice_exhaustion_reason: str | None = None
    immediate_condition_gain: int | None = None
    best_immediate_condition_labels: tuple[str, ...] = ()
    current_node_document_family: str | None = None
    current_node_supports_condition_labels: tuple[str, ...] = ()
    current_node_match_rationale: str | None = None
    current_node_match_confidence: float | None = None
    strategic_return_suggested: bool | None = None
    strategic_return_reason: str | None = None
    strategic_return_priority: float | None = None
    can_refine_navigation_perception: bool = True
    refine_navigation_perception_reason: str | None = None
    summary: str = ""
    top_candidate_observations: tuple[NavigationPerceptionCandidateView, ...] = ()


@dataclass(slots=True, frozen=True)
class GoalValidationView:
    available: bool = False
    target_kind: str | None = None
    validation_status: str | None = None
    summary: str | None = None
    confidence: float | None = None
    document_family: str | None = None
    source_action: str | None = None
    recommended_next_step: str | None = None
    can_revalidate_current_node: bool = True
    revalidate_reason: str | None = None


DocumentValidationView = GoalValidationView


@dataclass(slots=True, frozen=True)
class StrategicReturnPointView:
    node_id: str
    url: str
    priority: float = 0.0
    supports_condition_ids: tuple[str, ...] = ()
    kind: str | None = None
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class GoalProgressConditionView:
    condition_id: str
    label: str
    kind: str
    target_kind: str
    requiredness: str = "mandatory"
    status: str = "pending"
    matched_finding_ids: tuple[str, ...] = ()
    year: int | None = None
    min_count: int = 1


@dataclass(slots=True, frozen=True)
class GoalProgressView:
    intent: str = ""
    active_proposal_id: str | None = None
    active_proposal_summary: str | None = None
    proposal_status: str | None = None
    satisfied_conditions: int = 0
    pending_conditions: int = 0
    conditions: tuple[GoalProgressConditionView, ...] = ()


@dataclass(slots=True, frozen=True)
class SearchTargetView:
    search_target_id: str
    label: str | None = None
    placeholder: str | None = None
    name: str | None = None
    input_type: str | None = None
    same_host: bool | None = None
    source_frame: str | None = None
    confidence: float | None = None


@dataclass(slots=True, frozen=True)
class NodeView:
    node_id: str
    url: str

    title: str | None = None
    page_type: str = "unknown"
    page_type_confidence: float | None = None
    node_status: str = "fresh"

    visited_count: int = 0
    exploration_ratio: float = 0.0
    useful_ratio: float = 0.0
    choice_points: ChoicePointsView | None = None

    goal_context: str = ""
    scope_strategy: str | None = None

    anchor: AnchorView | None = None
    active_path: ActivePathView | None = None
    path_context: PathContextView | None = None
    relevant_findings: RelevantFindingsView | None = None
    goal_progress: GoalProgressView | None = None
    scratchpad: TacticalScratchpadView | None = None
    navigation_perception: NavigationPerceptionView | None = None
    goal_validation: GoalValidationView | None = None
    strategic_return_point: StrategicReturnPointView | None = None
    can_refine_navigation_perception: bool = True
    refine_navigation_perception_reason: str | None = None
    can_validate_current_content: bool = False
    validate_current_content_reason: str | None = None

    memory: NodeViewMemory = field(default_factory=NodeViewMemory)
    arrival: NodeViewArrival | None = None

    candidates: tuple[NodeViewCandidate, ...] = ()
    restrictions: tuple[str, ...] = ()
    search_targets: tuple[SearchTargetView, ...] = ()
    search_capability_available: bool = False
    current_search_history: tuple[str, ...] = ()

    def has_candidates(self) -> bool:
        return len(self.candidates) > 0

    @property
    def document_validation(self) -> GoalValidationView | None:
        return self.goal_validation
