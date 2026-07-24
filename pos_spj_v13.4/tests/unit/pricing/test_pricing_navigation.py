"""PRC-7 — navegación declarativa + presenter (sin Qt)."""

from backend.application.pricing.permissions import (
    ALL_PRICING_PERMISSIONS,
    PricingPermissions,
)
from frontend.desktop.modules.pricing.navigation import PRICING_NAV, visible_entries
from frontend.desktop.modules.pricing.presenter import PricingPresenter


def test_nav_entries_use_pricing_permissions():
    codes = {e.permission for e in PRICING_NAV}
    assert codes <= set(ALL_PRICING_PERMISSIONS)
    assert any(e.page_id == "pricing_costs" and e.permission == PricingPermissions.VIEW_COST
               for e in PRICING_NAV)


def test_visible_entries_filters_by_permission():
    granted = {PricingPermissions.VIEW, PricingPermissions.LIST_VIEW}
    visible = visible_entries(lambda c: c in granted)
    ids = {e.page_id for e in visible}
    assert "pricing_prices" in ids and "pricing_lists" in ids
    assert "pricing_costs" not in ids  # requiere VIEW_COST


class _FakeRead:
    def overview_counts(self):
        return {"lists_active": 2, "lists_pending": 1, "priced": 5, "costed": 4,
                "volume_tiers": 3, "below_min": 1}
    def list_price_lists(self, **kw):
        return [{"id": "l1", "code": "BASE", "name": "Base", "kind": "BASE",
                 "status": "ACTIVE", "discount_pct": "0"}]
    def list_product_prices(self, **kw):
        return []
    def list_costs(self, **kw):
        return []
    def list_price_history(self, **kw):
        return []


def test_presenter_overview_kpis():
    p = PricingPresenter(read_service_factory=_FakeRead)
    kpis = p.overview_kpis()
    keys = {k.key for k in kpis}
    assert {"lists_active", "priced", "below_min"} <= keys
    below = next(k for k in kpis if k.key == "below_min")
    assert below.variant == "danger"  # hay precios bajo mínimo


def test_presenter_price_lists_table():
    p = PricingPresenter(read_service_factory=_FakeRead)
    t = p.price_lists()
    assert t.total == 1 and t.rows[0][0] == "BASE"


def test_presenter_swallows_read_errors():
    class _Boom:
        def overview_counts(self):
            raise RuntimeError("db down")
    assert PricingPresenter(read_service_factory=_Boom).overview_kpis() == []
