"""Slaughter (faena) preparation — FUTURE sub-domain (§33, INV-21).

A stub: contracts, vocabulary and a pure planner that maps a future slaughter
flow onto the born-clean inventory primitives already in place. No schema, no
persistence, not wired to the live bus. ``SLAUGHTER_ENABLED`` stays False until
the real module lands; the planner lets tests prove the mapping today.
"""

from backend.domain.inventory.slaughter.contracts import (
    CarcassContract,
    SlaughterOrderContract,
    SlaughterOutputContract,
)
from backend.domain.inventory.slaughter.events import (
    ALL_SLAUGHTER_EVENTS,
    SlaughterEvents,
)
from backend.domain.inventory.slaughter.planning import (
    SLAUGHTER_ENABLED,
    PlannedGenealogyEdge,
    PlannedMovement,
    SlaughterPlan,
    SlaughterPlanningService,
)

__all__ = [
    "ALL_SLAUGHTER_EVENTS",
    "CarcassContract",
    "PlannedGenealogyEdge",
    "PlannedMovement",
    "SLAUGHTER_ENABLED",
    "SlaughterEvents",
    "SlaughterOrderContract",
    "SlaughterOutputContract",
    "SlaughterPlan",
    "SlaughterPlanningService",
]
