#graph_mapper_agent/adapters/perception/snapshot_aware_inspection_adapter.py
from __future__ import annotations

from typing import Any, Mapping

from graph_mapper_agent.application.ports.inspection_source import (
    InspectionSourcePort,
    InspectionSourceRequest,
)
from graph_mapper_agent.application.ports.live_inspection import (
    LiveInspectionPort,
    LiveInspectionRequest,
)


class SnapshotAwareInspectionAdapter(InspectionSourcePort):
    """
    Bridge temporal del agente Graph Mapper.

    Resuelve inspección para perception con esta política:
    1. usa snapshot prefetched si existe en metadata
    2. si no existe, delega a un port de inspección viva

    Sigue siendo compatibilidad temporal, pero ya no depende
    directamente de WebBrowserTool.
    """

    SNAPSHOT_KEYS = (
        "frozen_snapshot",
        "prefetched_inspection",
        "search_snapshot",
        "inspection_snapshot",
    )

    def __init__(self, live_inspection: LiveInspectionPort) -> None:
        self._live_inspection = live_inspection

    def resolve_for_perception(
        self,
        request: InspectionSourceRequest,
    ) -> dict[str, Any]:
        metadata = (
            dict(request.metadata)
            if isinstance(request.metadata, Mapping)
            else {}
        )

        snapshot = self._resolve_prefetched_snapshot(metadata)
        if snapshot is not None:
            enriched = dict(snapshot)
            enriched_metadata = dict(enriched.get("metadata") or {})
            enriched_metadata["used_prefetched_inspection"] = True
            enriched_metadata["inspection_source_kind"] = "prefetched"
            enriched["metadata"] = enriched_metadata
            return enriched

        if not request.url:
            raise ValueError(
                "resolve_for_perception requiere url o snapshot prefetched"
            )

        inspection = self._live_inspection.inspect_live(
            LiveInspectionRequest(
                url=request.url,
                question=request.question,
                metadata=metadata,
                include_screenshot=request.include_screenshot,
                max_candidates=request.max_candidates,
            )
        )
        if not isinstance(inspection, dict):
            raise TypeError("inspect_live(...) debe regresar dict[str, Any]")

        enriched = dict(inspection)
        enriched_metadata = dict(enriched.get("metadata") or {})
        enriched_metadata["used_prefetched_inspection"] = False
        enriched_metadata["inspection_source_kind"] = "live_inspect"
        enriched["metadata"] = enriched_metadata
        return enriched

    @classmethod
    def _resolve_prefetched_snapshot(
        cls,
        metadata: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        for key in cls.SNAPSHOT_KEYS:
            value = metadata.get(key)
            if isinstance(value, dict) and value:
                return dict(value)
        return None