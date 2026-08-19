"""SALES-6/POS-6 — SaleQueryService. Mirrors
backend/application/cash_register/shift_query_service.py's test coverage
shape: permission-gated, own SQL, DTO results. All branch/user ids are real
UUIDv7 strings (REGLA CERO — see test_sales_use_cases.py's own note)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    DenyAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.application.sales.queries.sale_query_service import SaleQueryService
from backend.application.sales.use_cases.cart_use_cases import AddSaleLineUseCase, StartSaleUseCase
from backend.application.sales.use_cases.lifecycle_use_cases import SuspendSaleUseCase
from backend.domain.sales.exceptions import SalesPermissionDeniedError
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    create_sales_schema(c)
    # SALES-9: SuspendSaleUseCase now reserves inventory for real — these
    # tables must exist for this file's suspend-path tests (same minimal
    # hand-rolled DDL as test_sales_inventory_reservation.py).
    c.execute("CREATE TABLE inventory_stock (branch_id TEXT, product_id TEXT, quantity REAL)")
    c.execute("""
        CREATE TABLE stock_reservas (
            id TEXT NOT NULL PRIMARY KEY, folio TEXT UNIQUE, branch_id TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'activa', payload_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')),
            expires_at TEXT DEFAULT (datetime('now', '+30 minutes'))
        )
    """)
    c.execute("""
        CREATE TABLE stock_reserva_detalles (
            id TEXT NOT NULL PRIMARY KEY, reserva_id TEXT NOT NULL REFERENCES stock_reservas(id),
            producto_id TEXT NOT NULL, cantidad REAL NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    c.commit()
    yield c
    c.close()


def _allow_all() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


def _new_sale_with_line(conn, auth, *, branch_id, cashier) -> str:
    product_id = new_uuid()
    conn.execute("INSERT INTO inventory_stock (branch_id, product_id, quantity) VALUES (?,?,?)",
                 (branch_id, product_id, 999.0))
    sale_id = StartSaleUseCase(auth).execute(
        conn, branch_id=branch_id, cashier_user_id=cashier,
        operation_id=new_uuid(), actor_user_id=cashier).entity_id
    AddSaleLineUseCase(auth).execute(
        conn, sale_id=sale_id, product_id=product_id, quantity=Decimal("1"),
        unit_price=Decimal("10.00"), actor_user_id=cashier, operation_id=new_uuid())
    return sale_id


class TestGetSale:
    def test_returns_dto_for_existing_sale(self, conn):
        cashier = new_uuid()
        start = StartSaleUseCase(_allow_all()).execute(
            conn, branch_id=new_uuid(), cashier_user_id=cashier,
            operation_id=new_uuid(), actor_user_id=cashier)
        service = SaleQueryService(conn, _allow_all())
        dto = service.get(start.entity_id, requester_user_id=cashier)
        assert dto is not None
        assert dto.id == start.entity_id

    def test_returns_none_for_missing_sale(self, conn):
        service = SaleQueryService(conn, _allow_all())
        assert service.get(new_uuid(), requester_user_id=new_uuid()) is None

    def test_permission_denied_raises(self, conn):
        service = SaleQueryService(
            conn, SalesAuthorizationPolicy(DenyAllSalesPermissionCheckerForTests()))
        with pytest.raises(SalesPermissionDeniedError):
            service.get(new_uuid(), requester_user_id=new_uuid())


class TestListSuspended:
    def test_lists_only_suspended_sales_for_branch(self, conn):
        auth = _allow_all()
        cashier = new_uuid()
        branch_1 = new_uuid()
        branch_2 = new_uuid()

        active_id = _new_sale_with_line(conn, auth, branch_id=branch_1, cashier=cashier)

        suspended_id = _new_sale_with_line(conn, auth, branch_id=branch_1, cashier=cashier)
        SuspendSaleUseCase(auth).execute(
            conn, sale_id=suspended_id, actor_user_id=cashier, operation_id=new_uuid(),
            max_suspended_sales=5)

        # A suspended sale in a DIFFERENT branch must not leak into results.
        other_branch_id = _new_sale_with_line(conn, auth, branch_id=branch_2, cashier=cashier)
        SuspendSaleUseCase(auth).execute(
            conn, sale_id=other_branch_id, actor_user_id=cashier, operation_id=new_uuid(),
            max_suspended_sales=5)

        service = SaleQueryService(conn, auth)
        results = service.list_suspended(branch_id=branch_1, requester_user_id=cashier)
        assert [dto.id for dto in results] == [suspended_id]
        assert active_id not in [dto.id for dto in results]

    def test_empty_when_nothing_suspended(self, conn):
        service = SaleQueryService(conn, _allow_all())
        assert service.list_suspended(branch_id=new_uuid(), requester_user_id=new_uuid()) == ()
