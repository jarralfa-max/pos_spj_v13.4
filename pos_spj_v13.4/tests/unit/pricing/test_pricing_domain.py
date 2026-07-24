"""PRC-2 — dominio de Pricing/Costing: Money, MarginPolicy, entidades, eventos."""

from decimal import Decimal

import pytest

from backend.domain.pricing.entities.price_list import PriceList
from backend.domain.pricing.entities.product_cost import ProductCost
from backend.domain.pricing.entities.product_price import ProductPrice, VolumePrice
from backend.domain.pricing.enums import (
    CostMethod,
    PriceListKind,
    PriceListStatus,
)
from backend.domain.pricing.events import ALL_PRICING_EVENTS, PricingEvents
from backend.domain.pricing.exceptions import (
    CurrencyMismatchError,
    InvalidMoneyError,
    InvalidPriceListError,
)
from backend.domain.pricing.value_objects.margin_policy import MarginPolicy
from backend.domain.pricing.value_objects.money import Money


# ── Money ────────────────────────────────────────────────────────────────────
class TestMoney:
    def test_float_rejected(self):
        with pytest.raises(InvalidMoneyError):
            Money(25.5)

    def test_decimal_and_currency(self):
        m = Money(Decimal("25.5"), "mxn")
        assert m.currency == "MXN" and m.amount == Decimal("25.5000")

    def test_negative_rejected_by_default(self):
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("-1"))

    def test_arithmetic_and_currency_guard(self):
        a, b = Money(Decimal("10")), Money(Decimal("3"))
        assert a.add(b).amount == Decimal("13")
        assert a.subtract(b).amount == Decimal("7")
        with pytest.raises(CurrencyMismatchError):
            a.add(Money(Decimal("1"), "USD"))

    def test_comparison(self):
        assert Money(Decimal("5")) < Money(Decimal("6"))
        assert Money(Decimal("5")) <= Money(Decimal("5"))

    def test_multiply(self):
        assert Money(Decimal("10")).multiply(Decimal("1.5")).amount == Decimal("15")


# ── MarginPolicy ─────────────────────────────────────────────────────────────
class TestMarginPolicy:
    def test_allows_above_minimum(self):
        p = MarginPolicy(minimum_price=Money(Decimal("10")))
        assert p.allows(Money(Decimal("12")))
        assert not p.allows(Money(Decimal("8")))

    def test_no_minimum_allows_all(self):
        assert MarginPolicy().allows(Money(Decimal("1")))

    def test_target_price_from_cost(self):
        p = MarginPolicy(target_margin_pct=Decimal("50"))
        # costo 10, margen 50% → precio 20
        assert p.target_price_from_cost(Money(Decimal("10"))).amount == Decimal("20")

    def test_float_margin_rejected(self):
        with pytest.raises(Exception):
            MarginPolicy(target_margin_pct=50.0)


# ── PriceList lifecycle ──────────────────────────────────────────────────────
class TestPriceList:
    def _draft(self):
        return PriceList(code="base", name="Lista base", kind=PriceListKind.BASE)

    def test_normalizes_and_defaults(self):
        pl = self._draft()
        assert pl.code == "BASE" and pl.status is PriceListStatus.DRAFT

    def test_lifecycle(self):
        pl = self._draft()
        pl.submit(); pl.approve(approved_by_user_id="mgr"); pl.activate()
        assert pl.is_active and not pl.is_editable

    def test_illegal_transition(self):
        pl = self._draft()
        with pytest.raises(InvalidPriceListError):
            pl.activate()

    def test_cannot_inherit_self(self):
        pl = self._draft()
        with pytest.raises(InvalidPriceListError):
            PriceList(id=pl.id, code="X", name="X", kind=PriceListKind.BASE,
                      inherits_from_id=pl.id)

    def test_discount_bounds(self):
        with pytest.raises(InvalidPriceListError):
            PriceList(code="X", name="X", kind=PriceListKind.BASE, discount_pct=Decimal("120"))


# ── ProductPrice / VolumePrice ───────────────────────────────────────────────
class TestProductPrice:
    def test_requires_money(self):
        with pytest.raises(InvalidPriceListError):
            ProductPrice(price_list_id="l1", product_id="p1", sale_price=Decimal("10"))

    def test_min_price_guard(self):
        with pytest.raises(InvalidPriceListError):
            ProductPrice(price_list_id="l1", product_id="p1",
                         sale_price=Money(Decimal("5")), min_price=Money(Decimal("8")))

    def test_valid(self):
        pp = ProductPrice(price_list_id="l1", product_id="p1",
                          sale_price=Money(Decimal("12")), min_price=Money(Decimal("8")))
        assert pp.sale_price.amount == Decimal("12")

    def test_volume_tier(self):
        v = VolumePrice(product_price_id="pp1", min_quantity=Decimal("10"),
                        price=Money(Decimal("9")))
        assert v.applies_to(Decimal("12")) and not v.applies_to(Decimal("5"))


# ── ProductCost ──────────────────────────────────────────────────────────────
class TestProductCost:
    def test_effective_cost_by_method(self):
        c = ProductCost(product_id="p1", average_cost=Money(Decimal("10")),
                        last_cost=Money(Decimal("11")), cost_method=CostMethod.LAST)
        assert c.effective_cost().amount == Decimal("11")

    def test_default_average(self):
        c = ProductCost(product_id="p1", average_cost=Money(Decimal("10")))
        assert c.effective_cost().amount == Decimal("10")

    def test_cost_must_be_money(self):
        with pytest.raises(Exception):
            ProductCost(product_id="p1", average_cost=Decimal("10"))


# ── eventos ──────────────────────────────────────────────────────────────────
class TestEvents:
    def test_canonical_events_present(self):
        assert PricingEvents.PRODUCT_PRICE_CHANGED in ALL_PRICING_EVENTS
        assert PricingEvents.PRODUCT_COST_UPDATED in ALL_PRICING_EVENTS

    def test_no_legacy_spanish_event(self):
        assert "PRECIO_ACTUALIZADO" not in ALL_PRICING_EVENTS
