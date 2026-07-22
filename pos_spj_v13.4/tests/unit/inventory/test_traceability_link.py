"""INV-17 unit — TraceabilityLink entity invariants (§32-33)."""

from decimal import Decimal

import pytest

from backend.domain.inventory.entities.traceability_link import TraceabilityLink
from backend.domain.inventory.enums import TraceabilityLinkType
from backend.domain.inventory.exceptions import InventoryDomainError


class TestTraceabilityLink:
    def test_create_defaults_and_ids(self):
        link = TraceabilityLink.create(
            parent_lot_id="lotA", child_lot_id="lotB",
            link_type=TraceabilityLinkType.PRODUCTION, quantity=Decimal("5"))
        assert link.id and link.parent_lot_id == "lotA" and link.child_lot_id == "lotB"
        assert link.link_type is TraceabilityLinkType.PRODUCTION
        assert link.quantity == Decimal("5") and link.weight == Decimal("0")
        assert link.source_module == "inventory" and link.created_at

    def test_requires_both_lots(self):
        with pytest.raises(InventoryDomainError):
            TraceabilityLink.create(parent_lot_id="", child_lot_id="lotB",
                                    link_type=TraceabilityLinkType.PRODUCTION)

    def test_rejects_self_reference(self):
        with pytest.raises(InventoryDomainError):
            TraceabilityLink.create(parent_lot_id="lotA", child_lot_id="lotA",
                                    link_type=TraceabilityLinkType.MERGE)

    def test_rejects_float_quantity(self):
        with pytest.raises(InventoryDomainError):
            TraceabilityLink.create(parent_lot_id="lotA", child_lot_id="lotB",
                                    link_type=TraceabilityLinkType.SPLIT, quantity=1.5)

    def test_rejects_negative(self):
        with pytest.raises(InventoryDomainError):
            TraceabilityLink.create(parent_lot_id="lotA", child_lot_id="lotB",
                                    link_type=TraceabilityLinkType.SPLIT,
                                    quantity=Decimal("-1"))
