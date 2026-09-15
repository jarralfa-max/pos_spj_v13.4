"""Fase 5 (§20) — the live POS used to never call the canonical Pricing
engine at all. `SalesPricingClient.effective_price()` was fully built,
tested in isolation (SALES-11), and its own module docstring named the
exact call site ("before AddSaleLineUseCase is called with the resolved
unit_price") — but nothing in `composition.py`/`sales_pos_presenter.py`
ever wired it in. `AddSaleLineUseCase` still just trusted whatever
`unit_price` the caller passed, which in the live UI came from
`SalesCatalogQueryService`'s flat BASE-list grid price — no branch
override, no customer tier, no volume break ever applied to what a
customer was actually charged. This proves the real, wired chain: a
branch-specific price beats the grid's flat price once the presenter
resolves it through the real composition, against a real connection.
"""

from __future__ import annotations

import os
import sqlite3
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from backend.domain.pricing.entities.price_list import PriceList
from backend.domain.pricing.entities.product_price import ProductPrice
from backend.domain.pricing.enums import PriceListKind
from backend.domain.pricing.value_objects.money import Money
from backend.infrastructure.db.repositories.pricing.pricing_repository import PricingRepository
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import new_uuid
from frontend.desktop.modules.sales_pos.composition import build_sales_pos_presenter


class _AllowAllSession:
    def __init__(self, branch_id):
        self.user_id = new_uuid()
        self.active_branch_id = branch_id
        self.is_active = True

    def tiene_permiso(self, code: str) -> bool:
        return True


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_products_schema(c)
    create_pricing_schema(c)
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _active_base_list(repo: PricingRepository) -> PriceList:
    pl = PriceList(code="BASE", name="Base", kind=PriceListKind.BASE)
    pl.submit()
    pl.approve(approved_by_user_id="mgr")
    pl.activate()
    repo.save_list(pl)
    return pl


def test_add_line_charges_the_branch_price_not_the_grid_price(conn):
    branch_id = new_uuid()
    product_id = new_uuid()

    repo = PricingRepository(conn)
    price_list = _active_base_list(repo)
    repo.save_price(ProductPrice(price_list_id=price_list.id, product_id=product_id,
                                 sale_price=Money(Decimal("150.00"))))
    repo.save_price(ProductPrice(price_list_id=price_list.id, product_id=product_id,
                                 branch_id=branch_id, sale_price=Money(Decimal("135.00"))))

    presenter = build_sales_pos_presenter(conn, session_context=_AllowAllSession(branch_id))

    sale_id = presenter.start_sale().entity_id
    # The caller passes the GRID's flat price (150.00) — exactly what
    # `SalesCatalogQueryService`'s BASE-list-only query would show. The
    # presenter must override it with the real branch price (135.00).
    added = presenter.add_line(
        sale_id=sale_id, product_id=product_id, quantity=Decimal("1"),
        unit_price=Decimal("150.00"), product_snapshot={"name": "Producto"})
    assert added.success, added.message

    sale = presenter.get_sale(sale_id)
    assert len(sale.lines) == 1
    assert sale.lines[0].unit_price == Decimal("135.00")


def test_add_line_falls_back_to_caller_price_when_product_has_no_price_configured(conn):
    """A product Pricing has never priced must not block the sale — the
    cashier's/grid's own price still wins."""
    branch_id = new_uuid()
    presenter = build_sales_pos_presenter(conn, session_context=_AllowAllSession(branch_id))

    sale_id = presenter.start_sale().entity_id
    added = presenter.add_line(
        sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
        unit_price=Decimal("99.99"), product_snapshot={"name": "Sin precio"})
    assert added.success, added.message

    sale = presenter.get_sale(sale_id)
    assert sale.lines[0].unit_price == Decimal("99.99")
