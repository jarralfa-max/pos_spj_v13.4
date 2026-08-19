"""SALES-7/POS-7 — ProductAvailabilityPolicy + SalesCatalogQueryService.

The query service tests build real Products/Pricing/Inventory schema via
their own canonical schema modules (backend/infrastructure/db/schema/
{products,pricing,inventory}_schema.py) — not a hand-rolled fixture — so the
SQL is verified against the actual bounded-context tables it joins, not an
approximation of them.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.sales.queries.catalog_query_service import SalesCatalogQueryService
from backend.domain.sales.enums import ProductStockState
from backend.domain.sales.policies.product_availability_policy import ProductAvailabilityPolicy
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.shared.ids import new_uuid


class TestProductAvailabilityPolicy:
    def test_out_of_stock_when_zero_or_negative(self):
        state = ProductAvailabilityPolicy.classify(Decimal("0"), Decimal("5"))
        assert state is ProductStockState.OUT_OF_STOCK

    def test_critical_stock_at_or_below_minimum(self):
        state = ProductAvailabilityPolicy.classify(Decimal("5"), Decimal("5"))
        assert state is ProductStockState.CRITICAL_STOCK

    def test_low_stock_between_minimum_and_double(self):
        state = ProductAvailabilityPolicy.classify(Decimal("9"), Decimal("5"))
        assert state is ProductStockState.LOW_STOCK

    def test_available_above_double_minimum(self):
        state = ProductAvailabilityPolicy.classify(Decimal("11"), Decimal("5"))
        assert state is ProductStockState.AVAILABLE

    def test_no_minimum_configured_is_available_if_positive(self):
        state = ProductAvailabilityPolicy.classify(Decimal("1"), Decimal("0"))
        assert state is ProductStockState.AVAILABLE

    def test_not_sellable_overrides_quantity(self):
        state = ProductAvailabilityPolicy.classify(
            Decimal("100"), Decimal("5"), sellable_override=False)
        assert state is ProductStockState.NOT_SELLABLE

    def test_simple_product_out_of_stock_is_not_sellable(self):
        assert ProductAvailabilityPolicy.is_sellable(
            ProductStockState.OUT_OF_STOCK, is_composite=False) is False

    def test_composite_product_out_of_stock_is_still_sellable(self):
        """A bundle/recipe product is composed from components at checkout —
        zero raw stock on its own row doesn't block the sale."""
        assert ProductAvailabilityPolicy.is_sellable(
            ProductStockState.OUT_OF_STOCK, is_composite=True) is True

    def test_not_sellable_state_is_never_sellable_even_if_composite(self):
        assert ProductAvailabilityPolicy.is_sellable(
            ProductStockState.NOT_SELLABLE, is_composite=True) is False


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    create_products_schema(c)
    create_pricing_schema(c)
    create_inventory_schema(c)
    base_list_id = new_uuid()
    c.execute(
        "INSERT INTO price_list (id, code, name, kind, status, discount_pct) "
        "VALUES (?, 'BASE', 'Lista base', 'BASE', 'ACTIVE', '0')", (base_list_id,))
    c.commit()
    yield c
    c.close()


def _add_product(
    conn, *, name, code, price, quantity, minimum="0", category_id=None,
    branch_id, barcode=None, is_composite=False,
) -> str:
    product_id = new_uuid()
    conn.execute(
        "INSERT INTO products (id, code, name, product_type, base_unit_id, "
        "lifecycle_status, bundle_allowed, category_id) VALUES (?,?,?,?,?,?,?,?)",
        (product_id, code, name, "SIMPLE", "PZA", "ACTIVE",
         1 if is_composite else 0, category_id))
    base_list_id = conn.execute("SELECT id FROM price_list WHERE code='BASE'").fetchone()[0]
    conn.execute(
        "INSERT INTO product_price (id, price_list_id, product_id, sale_price, branch_id) "
        "VALUES (?,?,?,?,'')", (new_uuid(), base_list_id, product_id, price))
    conn.execute(
        "INSERT INTO inventory_replenishment_rule "
        "(id, product_id, branch_id, warehouse_id, min_quantity, created_at) "
        "VALUES (?,?,?,'',?,datetime('now'))", (new_uuid(), product_id, "", minimum))
    conn.execute(
        "INSERT INTO inventory_balances "
        "(id, product_id, branch_id, warehouse_id, quantity, updated_at) "
        "VALUES (?,?,?,?,?,datetime('now'))",
        (new_uuid(), product_id, branch_id, new_uuid(), quantity))
    if barcode:
        conn.execute(
            "INSERT INTO product_barcodes "
            "(id, product_id, barcode_value, barcode_type, is_primary) "
            "VALUES (?,?,?,'EAN13',1)", (new_uuid(), product_id, barcode))
    conn.commit()
    return product_id


class TestSalesCatalogQueryService:
    def test_search_returns_resolved_stock_state_not_a_dead_placeholder(self, conn):
        branch = new_uuid()
        _add_product(conn, name="Bistec", code="BST-1", price="120.50",
                     quantity="0", branch_id=branch)
        service = SalesCatalogQueryService(conn)
        results = service.search(branch_id=branch)
        assert len(results) == 1
        entry = results[0]
        assert entry.stock_state == "OUT_OF_STOCK"  # not the legacy service's hardcoded "ok"
        assert entry.effective_price == Decimal("120.50")
        assert isinstance(entry.effective_price, Decimal)
        assert entry.sellable is False

    def test_composite_product_out_of_stock_is_sellable(self, conn):
        branch = new_uuid()
        _add_product(conn, name="Combo Familiar", code="CMB-1", price="199.00",
                     quantity="0", branch_id=branch, is_composite=True)
        service = SalesCatalogQueryService(conn)
        entry = service.search(branch_id=branch)[0]
        assert entry.stock_state == "OUT_OF_STOCK"
        assert entry.sellable is True

    def test_search_by_name(self, conn):
        branch = new_uuid()
        _add_product(conn, name="Bistec de Res", code="BST-1", price="1", quantity="10",
                     branch_id=branch)
        _add_product(conn, name="Pechuga de Pollo", code="PCH-1", price="1", quantity="10",
                     branch_id=branch)
        service = SalesCatalogQueryService(conn)
        results = service.search(branch_id=branch, search="Bistec")
        assert [r.name for r in results] == ["Bistec de Res"]

    def test_search_by_exact_code(self, conn):
        branch = new_uuid()
        _add_product(conn, name="Bistec", code="BST-1", price="1", quantity="10", branch_id=branch)
        service = SalesCatalogQueryService(conn)
        results = service.search(branch_id=branch, search="BST-1")
        assert len(results) == 1
        assert results[0].sku == "BST-1"

    def test_search_by_barcode(self, conn):
        branch = new_uuid()
        _add_product(conn, name="Bistec", code="BST-1", price="1", quantity="10",
                     branch_id=branch, barcode="7501234567890")
        service = SalesCatalogQueryService(conn)
        results = service.search(branch_id=branch, search="7501234567890")
        assert len(results) == 1
        assert results[0].barcode == "7501234567890"

    def test_available_quantity_scoped_to_branch(self, conn):
        branch_a = new_uuid()
        branch_b = new_uuid()
        _add_product(conn, name="Bistec", code="BST-1", price="1", quantity="20",
                     branch_id=branch_a)
        service = SalesCatalogQueryService(conn)
        assert service.search(branch_id=branch_a)[0].available_quantity == Decimal("20")
        # Same product, different branch: no inventory_balances row there — zero, not a leak.
        other_branch_results = service.search(branch_id=branch_b)
        assert other_branch_results[0].available_quantity == Decimal("0")

    def test_low_stock_warning_present(self, conn):
        branch = new_uuid()
        _add_product(conn, name="Bistec", code="BST-1", price="1", quantity="5",
                     minimum="5", branch_id=branch)
        service = SalesCatalogQueryService(conn)
        entry = service.search(branch_id=branch)[0]
        assert entry.stock_state == "CRITICAL_STOCK"
        assert entry.warnings

    def test_categories_listed(self, conn):
        conn.execute("INSERT INTO product_categories (id, code, name) VALUES (?,?,?)",
                     (new_uuid(), "CARNES", "Carnes"))
        conn.commit()
        service = SalesCatalogQueryService(conn)
        assert "Carnes" in service.get_categories()
