"""SlaughterExecutedStubHandler (Inventory context) — FUTURE, not active (§33).

The subscription point for the future slaughter module. While ``SLAUGHTER_ENABLED``
is False it is a deliberate no-op: it never posts to the ledger. When the module
lands, this is where a SLAUGHTER_EXECUTED event would be turned — via
``SlaughterPlanningService`` — into SLAUGHTER_INPUT_FUTURE / SLAUGHTER_OUTPUT_FUTURE
movements plus SLAUGHTER genealogy links, through the existing canonical use
cases. Kept here so the wiring seam exists today without any live behavior.
"""

from __future__ import annotations

import logging

from backend.domain.inventory.slaughter import (
    SLAUGHTER_ENABLED,
    SlaughterEvents,
    SlaughterPlanningService,
)

logger = logging.getLogger("spj.inventory.slaughter_stub")


class SlaughterExecutedStubHandler:
    event_name = SlaughterEvents.SLAUGHTER_EXECUTED
    enabled = SLAUGHTER_ENABLED

    def __init__(self, connection,
                 planner: SlaughterPlanningService | None = None) -> None:
        self._conn = connection
        self._planner = planner or SlaughterPlanningService()

    def handle(self, payload: dict) -> None:
        if not self.enabled:
            logger.info(
                "slaughter: módulo no habilitado; evento %s ignorado (preparación §33)",
                payload.get("event_name") or self.event_name)
            return
        # Future: build contracts from payload → self._planner.plan(...) → post
        # SLAUGHTER_INPUT_FUTURE / SLAUGHTER_OUTPUT_FUTURE + genealogy via the
        # canonical use cases. Intentionally unreachable until INV enables faena.
        raise NotImplementedError(
            "El módulo de faena se habilita en una fase futura (§33)")
