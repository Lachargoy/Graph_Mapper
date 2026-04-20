from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AnchorState:
    """
    Raiz operativa estable de la busqueda actual.

    En esta fase inicial solo fija identidad y URL de referencia.
    """

    anchor_id: str
    anchor_url: str
    root_node_id: str
    label: str | None = None
