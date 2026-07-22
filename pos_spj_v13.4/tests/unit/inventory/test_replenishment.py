"""INV-18 unit — replenishment rule/suggestion invariants + policy (§34)."""

from decimal import Decimal

import pytest

from backend.domain.inventory.entities.replenishment import (
    ReplenishmentRule,
    ReplenishmentSuggestion,
)
from backend.domain.inventory.enums import (
    ReplenishmentBasis,
    ReplenishmentSource,
    ReplenishmentUrgency,
)
from backend.domain.inventory.exceptions import InventoryDomainError
from backend.domain.inventory.services.replenishment_policy import ReplenishmentPolicy


def _rule(**kw):
    base = dict(product_id="p1", branch_id="b1", warehouse_id="w1",
                reorder_point=Decimal("10"), target_quantity=Decimal("30"))
    base.update(kw)
    return ReplenishmentRule.create(**base)


class TestReplenishmentRule:
    def test_valid_rule(self):
        r = _rule(safety_stock=Decimal("3"), min_quantity=Decimal("5"),
                  max_quantity=Decimal("40"))
        assert r.id and r.reorder_point == Decimal("10")
        assert r.preferred_source is ReplenishmentSource.PURCHASE

    def test_target_below_reorder_rejected(self):
        with pytest.raises(InventoryDomainError):
            _rule(reorder_point=Decimal("30"), target_quantity=Decimal("10"))

    def test_target_above_max_rejected(self):
        with pytest.raises(InventoryDomainError):
            _rule(target_quantity=Decimal("30"), max_quantity=Decimal("20"))

    def test_transfer_requires_source(self):
        with pytest.raises(InventoryDomainError):
            _rule(preferred_source=ReplenishmentSource.TRANSFER)

    def test_float_rejected(self):
        with pytest.raises(InventoryDomainError):
            _rule(reorder_point=10.0)

    def test_suggestion_requires_positive_quantity(self):
        with pytest.raises(InventoryDomainError):
            ReplenishmentSuggestion.create(
                rule_id="r1", product_id="p1", branch_id="b1", warehouse_id="w1",
                basis=ReplenishmentBasis.QUANTITY, current_available=Decimal("5"),
                suggested_quantity=Decimal("0"), source_type=ReplenishmentSource.PURCHASE,
                urgency=ReplenishmentUrgency.REORDER)


class TestReplenishmentPolicy:
    def setup_method(self):
        self.policy = ReplenishmentPolicy()

    def test_above_reorder_no_suggestion(self):
        assert self.policy.evaluate(_rule(), available=Decimal("15")) is None

    def test_purchase_deficit_and_reorder_urgency(self):
        d = self.policy.evaluate(_rule(safety_stock=Decimal("3")), available=Decimal("8"))
        assert d.source_type is ReplenishmentSource.PURCHASE
        assert d.suggested_quantity == Decimal("22")  # 30 - 8
        assert d.urgency is ReplenishmentUrgency.REORDER

    def test_critical_at_or_below_safety(self):
        d = self.policy.evaluate(_rule(safety_stock=Decimal("5")), available=Decimal("5"))
        assert d.urgency is ReplenishmentUrgency.CRITICAL

    def test_stockout(self):
        d = self.policy.evaluate(_rule(), available=Decimal("0"))
        assert d.urgency is ReplenishmentUrgency.STOCKOUT

    def test_transfer_when_source_covers_deficit(self):
        rule = _rule(preferred_source=ReplenishmentSource.TRANSFER,
                     source_warehouse_id="w2")
        d = self.policy.evaluate(rule, available=Decimal("4"),
                                 source_surplus=Decimal("50"))
        assert d.source_type is ReplenishmentSource.TRANSFER
        assert d.source_warehouse_id == "w2" and d.suggested_quantity == Decimal("26")

    def test_falls_back_to_purchase_when_source_insufficient(self):
        rule = _rule(preferred_source=ReplenishmentSource.TRANSFER,
                     source_warehouse_id="w2")
        d = self.policy.evaluate(rule, available=Decimal("4"),
                                 source_surplus=Decimal("2"))
        assert d.source_type is ReplenishmentSource.PURCHASE
