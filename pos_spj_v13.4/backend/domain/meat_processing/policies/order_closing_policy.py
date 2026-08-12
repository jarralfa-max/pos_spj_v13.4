"""Order-closing preconditions (§35). Pure domain contract: this phase does not
integrate with Inventory/Quality/Costing yet, so the checklist is populated by the
future CloseProcessingOrder use case (PROC-6+) after querying those modules —
OrderClosingPolicy only enforces that every box is checked before allowing a close.
"""

from dataclasses import dataclass

from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError


@dataclass(frozen=True)
class ProcessingOrderCloseChecklist:
    consumptions_posted: bool
    outputs_registered: bool
    no_pending_weighings: bool
    quality_resolved: bool
    yield_calculated: bool
    variances_reviewed: bool
    critical_losses_have_case: bool
    inventory_confirmed: bool
    costs_notified: bool

    @property
    def is_complete(self) -> bool:
        return all((
            self.consumptions_posted, self.outputs_registered,
            self.no_pending_weighings, self.quality_resolved,
            self.yield_calculated, self.variances_reviewed,
            self.critical_losses_have_case, self.inventory_confirmed,
            self.costs_notified,
        ))

    @property
    def pending_items(self) -> tuple[str, ...]:
        return tuple(
            name for name, value in (
                ("consumptions_posted", self.consumptions_posted),
                ("outputs_registered", self.outputs_registered),
                ("no_pending_weighings", self.no_pending_weighings),
                ("quality_resolved", self.quality_resolved),
                ("yield_calculated", self.yield_calculated),
                ("variances_reviewed", self.variances_reviewed),
                ("critical_losses_have_case", self.critical_losses_have_case),
                ("inventory_confirmed", self.inventory_confirmed),
                ("costs_notified", self.costs_notified),
            ) if not value
        )


class OrderClosingPolicy:
    @staticmethod
    def ensure_can_close(checklist: ProcessingOrderCloseChecklist) -> None:
        if not checklist.is_complete:
            pending = ", ".join(checklist.pending_items)
            raise MeatProcessingInvariantError(
                f"La orden no puede cerrarse: pendientes {pending}")
