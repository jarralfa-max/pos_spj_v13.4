"""Regression test — the live POS's customer search was silently dead.

`SalesPosPresenter.search_customers()` looked up a `"customer_search"` query
service that `composition.py::build_sales_pos_presenter` never registered
(`query_service()` is a plain `dict.get`, so it always returned `None`), the
presenter then called a `.search(...)` method `CustomerLookupQueryService`
doesn't have (it's `.lookup(...)`), and `CustomerPanel._search_provider`
read `result.id` on a `CustomerLookupResult` that only has `.customer_id`.
Three independent bugs stacked so that typing a customer's name into the POS
always silently produced zero results, with no exception and nothing to log
— exactly the "cliente no muestra resultados" failure mode. This test
exercises the real composition, not a hand-wired fake, so it would have
caught all three.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.use_cases.lifecycle_use_cases import CreateCustomerUseCase
from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import new_uuid
from frontend.desktop.modules.sales_pos.composition import build_sales_pos_presenter


class _AllowAllSession:
    def __init__(self):
        self.user_id = new_uuid()
        self.active_branch_id = new_uuid()
        self.is_active = True

    def tiene_permiso(self, code: str) -> bool:
        return True


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    create_customers_crm_schema(c)
    create_sales_schema(c)
    create_products_schema(c)
    create_pricing_schema(c)
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def test_search_customers_finds_a_real_customer_by_name(conn):
    created = CreateCustomerUseCase(CustomerAuthorizationPolicy.permissive_for_tests()).execute(
        conn, actor_user_id="u1", display_name="Restaurante El Sol",
        operation_id=new_uuid())
    assert created.success, created.message

    presenter = build_sales_pos_presenter(conn, session_context=_AllowAllSession())

    results = presenter.search_customers("Sol")

    assert len(results) == 1
    assert results[0].customer_id == created.entity_id
    assert results[0].display_name == "Restaurante El Sol"


def test_search_customers_returns_empty_for_no_match_not_an_error(conn):
    presenter = build_sales_pos_presenter(conn, session_context=_AllowAllSession())

    assert presenter.search_customers("nadie coincide") == []
