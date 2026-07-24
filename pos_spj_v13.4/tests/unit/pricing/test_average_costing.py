"""PRC-6 — costo promedio móvil (dominio puro)."""

from decimal import Decimal

import pytest

from backend.domain.pricing.exceptions import InvalidCostError
from backend.domain.pricing.services.average_costing_service import AverageCostingService
from backend.domain.pricing.value_objects.money import Money

S = AverageCostingService()


def _m(v):
    return Money(Decimal(str(v)))


def test_first_receipt_sets_cost():
    u = S.apply_receipt(prior_average=None, prior_quantity=Decimal("0"),
                        unit_cost=_m(60), incoming_quantity=Decimal("10"))
    assert u.average_cost.amount == Decimal("60") and u.tracked_quantity == Decimal("10")
    assert u.last_cost.amount == Decimal("60")


def test_weighted_average():
    # 10 @ 60 luego 10 @ 80 → 70
    u = S.apply_receipt(prior_average=_m(60), prior_quantity=Decimal("10"),
                        unit_cost=_m(80), incoming_quantity=Decimal("10"))
    assert u.average_cost.amount == Decimal("70")
    assert u.tracked_quantity == Decimal("20") and u.last_cost.amount == Decimal("80")


def test_weighted_average_uneven():
    # 30 @ 10 luego 10 @ 20 → 12.5
    u = S.apply_receipt(prior_average=_m(10), prior_quantity=Decimal("30"),
                        unit_cost=_m(20), incoming_quantity=Decimal("10"))
    assert u.average_cost.amount == Decimal("12.5")


def test_zero_incoming_rejected():
    with pytest.raises(InvalidCostError):
        S.apply_receipt(prior_average=_m(10), prior_quantity=Decimal("5"),
                        unit_cost=_m(20), incoming_quantity=Decimal("0"))


def test_currency_guard():
    from backend.domain.pricing.exceptions import CurrencyMismatchError
    with pytest.raises(CurrencyMismatchError):
        S.apply_receipt(prior_average=Money(Decimal("10"), "USD"),
                        prior_quantity=Decimal("5"), unit_cost=_m(20),
                        incoming_quantity=Decimal("5"))
