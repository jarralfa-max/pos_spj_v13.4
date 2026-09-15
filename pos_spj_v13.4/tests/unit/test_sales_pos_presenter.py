"""POS-19 — SalesPosPresenter unit tests. Mirrors CRM's own presenter test
style: fakes at the `query_services`/`command_handlers` boundary, never a
real connection or Qt widget — this file proves the presenter's own lookup/
degrade-gracefully contract, independent of both the backend and the UI.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.sales.result import SaleResult
from frontend.desktop.modules.sales_pos.sales_pos_presenter import SalesPosPresenter


class _FakeSession:
    def __init__(self, *, user_id="u1", branch_id="b1", permissions=()):
        self.user_id = user_id
        self.active_branch_id = branch_id
        self._permissions = set(permissions)

    def tiene_permiso(self, code: str) -> bool:
        return code in self._permissions


class TestSalesPosPresenterDegradesGracefully:
    def test_start_sale_without_handler_fails_not_wired(self):
        presenter = SalesPosPresenter(session_context=_FakeSession())
        result = presenter.start_sale()
        assert isinstance(result, SaleResult)
        assert result.success is False
        assert result.error_code == "NOT_WIRED"

    def test_catalog_search_without_query_service_returns_empty(self):
        presenter = SalesPosPresenter(session_context=_FakeSession())
        assert presenter.catalog_search() == ()

    def test_get_sale_without_query_service_returns_none(self):
        presenter = SalesPosPresenter(session_context=_FakeSession())
        assert presenter.get_sale("sale-1") is None

    def test_count_suspended_without_query_service_returns_zero(self):
        presenter = SalesPosPresenter(session_context=_FakeSession())
        assert presenter.count_suspended() == 0


class TestSalesPosPresenterWiredHandlers:
    def test_start_sale_calls_handler_with_session_identity(self):
        captured = {}

        def handler(**kwargs):
            captured.update(kwargs)
            return SaleResult.ok("ok", entity_id="sale-1")

        presenter = SalesPosPresenter(
            session_context=_FakeSession(user_id="cashier-1", branch_id="branch-1"),
            command_handlers={"start_sale": handler})

        result = presenter.start_sale()

        assert result.success is True
        assert result.entity_id == "sale-1"
        assert captured["branch_id"] == "branch-1"
        assert captured["cashier_user_id"] == "cashier-1"
        assert captured["actor_user_id"] == "cashier-1"
        assert captured["operation_id"]

    def test_add_line_forwards_all_fields(self):
        captured = {}

        def handler(**kwargs):
            captured.update(kwargs)
            return SaleResult.ok("added")

        presenter = SalesPosPresenter(
            session_context=_FakeSession(), command_handlers={"add_line": handler})
        presenter.add_line(
            sale_id="sale-1", product_id="p1", quantity=Decimal("2"),
            unit_price=Decimal("10.00"), product_snapshot={"name": "Bistec"})

        assert captured["sale_id"] == "sale-1"
        assert captured["product_id"] == "p1"
        assert captured["quantity"] == Decimal("2")
        assert captured["unit_price"] == Decimal("10.00")
        assert captured["product_snapshot"] == {"name": "Bistec"}

    def test_add_line_uses_the_canonical_pricing_engine_when_wired(self):
        """§20: the charged price comes from Pricing (branch/customer/volume
        -aware), not whatever the caller passed in from the catalog grid."""
        captured = {}
        priced = {}

        def handler(**kwargs):
            captured.update(kwargs)
            return SaleResult.ok("added")

        class _FakeSaleQuery:
            def get(self, sale_id, *, requester_user_id):
                return type("SaleDTO", (), {"customer_id": "cust-1"})()

        class _FakePricing:
            def effective_price(self, product_id, *, branch_id, customer_id, quantity):
                priced.update(product_id=product_id, branch_id=branch_id,
                              customer_id=customer_id, quantity=quantity)
                return Decimal("8.50")

        presenter = SalesPosPresenter(
            session_context=_FakeSession(branch_id="branch-9"),
            command_handlers={"add_line": handler},
            query_services={"sale_query": _FakeSaleQuery(), "pricing": _FakePricing()})

        presenter.add_line(
            sale_id="sale-1", product_id="p1", quantity=Decimal("2"),
            unit_price=Decimal("999.00"), product_snapshot={"name": "Bistec"})

        assert captured["unit_price"] == Decimal("8.50")
        assert priced == {"product_id": "p1", "branch_id": "branch-9",
                          "customer_id": "cust-1", "quantity": Decimal("2")}

    def test_add_line_falls_back_to_caller_price_when_nothing_configured(self):
        captured = {}

        def handler(**kwargs):
            captured.update(kwargs)
            return SaleResult.ok("added")

        class _FakePricing:
            def effective_price(self, product_id, **kw):
                return None  # nothing configured for this product

        presenter = SalesPosPresenter(
            session_context=_FakeSession(), command_handlers={"add_line": handler},
            query_services={"pricing": _FakePricing()})

        presenter.add_line(sale_id="sale-1", product_id="p1", quantity=Decimal("1"),
                           unit_price=Decimal("10.00"))

        assert captured["unit_price"] == Decimal("10.00")

    def test_add_line_falls_back_to_caller_price_when_pricing_lookup_fails(self):
        captured = {}

        def handler(**kwargs):
            captured.update(kwargs)
            return SaleResult.ok("added")

        class _FailingPricing:
            def effective_price(self, product_id, **kw):
                raise RuntimeError("db unavailable")

        presenter = SalesPosPresenter(
            session_context=_FakeSession(), command_handlers={"add_line": handler},
            query_services={"pricing": _FailingPricing()})

        result = presenter.add_line(sale_id="sale-1", product_id="p1", quantity=Decimal("1"),
                                    unit_price=Decimal("10.00"))

        assert result.success is True
        assert captured["unit_price"] == Decimal("10.00")

    def test_catalog_search_delegates_to_query_service_with_current_branch(self):
        captured = {}

        class _FakeCatalog:
            def search(self, **kwargs):
                captured.update(kwargs)
                return ("p1", "p2")

        presenter = SalesPosPresenter(
            session_context=_FakeSession(branch_id="branch-9"),
            query_services={"catalog": _FakeCatalog()})

        results = presenter.catalog_search(search="bistec")

        assert results == ("p1", "p2")
        assert captured["branch_id"] == "branch-9"
        assert captured["search"] == "bistec"

    def test_search_customers_delegates_to_lookup_not_search(self):
        """`CustomerLookupQueryService` only exposes `.lookup(...)`; a call
        to `.search(...)` used to raise `AttributeError` every time this
        presenter method ran against the real query service."""
        captured = {}

        class _FakeCustomerLookup:
            def lookup(self, query, **kwargs):
                captured["query"] = query
                captured.update(kwargs)
                return ["r1"]

        presenter = SalesPosPresenter(
            session_context=_FakeSession(),
            query_services={"customer_search": _FakeCustomerLookup()})

        results = presenter.search_customers("Sol")

        assert results == ["r1"]
        assert captured["query"] == "Sol"
        assert captured["actor_user_id"] == presenter.current_user_id()


class TestSalesPosPresenterCapabilities:
    def test_capabilities_reflect_real_session_permissions(self):
        from backend.application.sales.permissions import SalesPermissions

        presenter = SalesPosPresenter(
            session_context=_FakeSession(permissions={SalesPermissions.SALE_COMPLETE}))
        capabilities = presenter.capabilities()
        assert capabilities.sale_complete is True
        assert capabilities.sale_cancel is False

    def test_no_session_denies_every_capability(self):
        presenter = SalesPosPresenter(session_context=None)
        capabilities = presenter.capabilities()
        assert capabilities.sale_complete is False
        assert capabilities.module_view is False
