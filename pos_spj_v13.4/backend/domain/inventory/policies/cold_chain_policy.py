"""ColdChainPolicy — classify a temperature reading and decide the action (§21).

Pure domain logic. A compliant reading needs no action; a warning is logged; an
out-of-range reading is an excursion that (when the product/warehouse is
configured to auto-block) quarantines the affected lot. Inventory keeps the
status; Quality decides release or disposal.
"""

from __future__ import annotations

from backend.domain.inventory.enums import ColdChainStatus, ExcursionAction
from backend.domain.inventory.value_objects.cold_chain import ColdChainRange


class ColdChainPolicy:
    def classify(self, temperature, cold_range: ColdChainRange) -> ColdChainStatus:
        if cold_range.is_compliant(temperature):
            return ColdChainStatus.COMPLIANT
        if cold_range.is_within_warning(temperature):
            return ColdChainStatus.WARNING
        return ColdChainStatus.OUT_OF_RANGE

    def decide_action(self, status: ColdChainStatus, *,
                      auto_block: bool = False) -> ExcursionAction:
        if status is ColdChainStatus.COMPLIANT:
            return ExcursionAction.NONE
        if status is ColdChainStatus.WARNING:
            return ExcursionAction.WARN
        # OUT_OF_RANGE
        return ExcursionAction.QUARANTINE if auto_block else ExcursionAction.WARN

    def is_excursion(self, status: ColdChainStatus) -> bool:
        return status in (ColdChainStatus.WARNING, ColdChainStatus.OUT_OF_RANGE)
