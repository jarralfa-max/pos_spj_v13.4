"""PRC-4 — resolución de precio (prioridad + descuento + precio mínimo)."""

from decimal import Decimal

from backend.domain.pricing.enums import PriceSource
from backend.domain.pricing.services.pricing_resolution_service import (
    PricingResolutionService,
)
from backend.domain.pricing.value_objects.money import Money


def _m(v):
    return Money(Decimal(str(v)))


R = PricingResolutionService()


def test_base_only():
    r = R.resolve(base_price=_m(10))
    assert r.source is PriceSource.BASE and r.price.amount == Decimal("10")


def test_priority_volume_wins():
    r = R.resolve(base_price=_m(10), list_price=_m(9), customer_price=_m(8), volume_price=_m(7))
    assert r.source is PriceSource.VOLUME and r.price.amount == Decimal("7")


def test_priority_customer_over_list():
    r = R.resolve(base_price=_m(10), list_price=_m(9), customer_price=_m(8))
    assert r.source is PriceSource.CUSTOMER_LIST and r.price.amount == Decimal("8")


def test_priority_list_over_base():
    r = R.resolve(base_price=_m(10), list_price=_m(9))
    assert r.source is PriceSource.LIST


def test_discount_applies_to_list_not_volume():
    r = R.resolve(list_price=_m(100), discount_pct=Decimal("10"))
    assert r.price.amount == Decimal("90")
    r2 = R.resolve(list_price=_m(100), volume_price=_m(80), discount_pct=Decimal("10"))
    assert r2.price.amount == Decimal("80") and r2.source is PriceSource.VOLUME


def test_below_minimum_flagged():
    r = R.resolve(base_price=_m(5), min_price=_m(8))
    assert r.below_minimum and r.price.amount == Decimal("5")


def test_above_minimum_not_flagged():
    r = R.resolve(base_price=_m(10), min_price=_m(8))
    assert not r.below_minimum


def test_no_price_source_none():
    r = R.resolve()
    assert r.price is None and r.source is PriceSource.NONE
