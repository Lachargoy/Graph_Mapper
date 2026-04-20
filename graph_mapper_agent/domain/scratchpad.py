from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TraversalScratchpad:
    working_plan: str = ""
    tactical_observations: str = ""
    notes: tuple[str, ...] = ()

    def add_note(self, note: str) -> None:
        cleaned = str(note or "").strip()
        if not cleaned:
            return
        self.notes = (*self.notes, cleaned)
