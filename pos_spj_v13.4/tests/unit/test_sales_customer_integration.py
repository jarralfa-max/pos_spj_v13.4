"""SALES-10/POS-10 — Cliente: Search, Assign, Quick create, Loyalty card
scan, Tests. Builds real Customer Master schema
(`create_customers_crm_schema`) + minimal hand-rolled legacy `clientes`
tables (the only real card-scan path, confirmed by research) alongside
`create_sales_schema` — same "call the real bounded-context schema modules
directly" pattern SALES-7/9 already established, not a full migration run.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.application.sales.use_cases.cart_use_cases import AssignCustomerToSaleUseCase, StartSaleUseCase
from backend.application.sales.use_cases.customer_use_cases import (
    QuickCreateCustomerForSaleUseCase,
    ScanLoyaltyCardForSaleUseCase,
)
from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.infrastructure.integrations.sales_customer_client import SalesCustomerClient
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_customers_crm_schema(c)
    c.execute("""
        CREATE TABLE clientes (
            id TEXT PRIMARY KEY, nombre TEXT NOT NULL, telefono TEXT, email TEXT,
            codigo_qr TEXT, codigo_fidelidad TEXT, activo INTEGER DEFAULT 1
        )
    """)
    c.commit()
    yield c
    c.close()


def _allow_all_sales() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


def _allow_all_customers() -> CustomerAuthorizationPolicy:
    return CustomerAuthorizationPolicy.permissive_for_tests()


def _start_sale(conn) -> tuple[str, str]:
    cashier = new_uuid()
    result = StartSaleUseCase(_allow_all_sales()).execute(
        conn, branch_id=new_uuid(), cashier_user_id=cashier,
        operation_id=new_uuid(), actor_user_id=cashier)
    return result.entity_id, cashier


def _create_real_customer(conn, *, display_name="Ana Torres", phone_e164=None) -> str:
    result = QuickCreateCustomerForSaleUseCase(_allow_all_customers()).execute(
        conn, actor_user_id=new_uuid(), operation_id=new_uuid(),
        display_name=display_name, phone_e164=phone_e164)
    assert result.success
    return result.entity_id


class TestSalesCustomerClientSearch:
    def test_search_finds_created_customer(self, conn):
        _create_real_customer(conn, display_name="Bistecas del Norte")
        client = SalesCustomerClient(conn, authorization=_allow_all_customers())
        results = client.search("Bistecas", actor_user_id=new_uuid())
        assert any(r.display_name == "Bistecas del Norte" for r in results)

    def test_blank_query_returns_empty(self, conn):
        client = SalesCustomerClient(conn, authorization=_allow_all_customers())
        assert client.search("", actor_user_id=new_uuid()) == []


class TestQuickCreateCustomerForSaleUseCase:
    def test_creates_with_only_name(self, conn):
        result = QuickCreateCustomerForSaleUseCase(_allow_all_customers()).execute(
            conn, actor_user_id=new_uuid(), operation_id=new_uuid(),
            display_name="Cliente de mostrador")
        assert result.success
        assert result.entity_id

    def test_creates_with_name_and_phone_stores_contact(self, conn):
        result = QuickCreateCustomerForSaleUseCase(_allow_all_customers()).execute(
            conn, actor_user_id=new_uuid(), operation_id=new_uuid(),
            display_name="Juan Perez", phone_e164="+525512345678")
        assert result.success
        row = conn.execute(
            "SELECT phone_e164 FROM customer_contacts WHERE customer_id=?",
            (result.entity_id,)).fetchone()
        assert row is not None
        assert row["phone_e164"] == "+525512345678"

    def test_does_not_create_any_loyalty_card_or_points(self, conn):
        """§22: quick create must never auto-create membership/tarjeta/puntos."""
        result = QuickCreateCustomerForSaleUseCase(_allow_all_customers()).execute(
            conn, actor_user_id=new_uuid(), operation_id=new_uuid(),
            display_name="Cliente Nuevo")
        assert result.success
        count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='tarjetas_fidelidad'"
        ).fetchone()[0]
        # tarjetas_fidelidad isn't even part of this fixture's schema — proves
        # nothing in the quick-create path needed it to exist.
        assert count == 0


class TestAssignCustomerToSaleUseCase:
    def test_assigns_a_real_existing_customer(self, conn):
        sale_id, cashier = _start_sale(conn)
        customer_id = _create_real_customer(conn)
        result = AssignCustomerToSaleUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, customer_id=customer_id, actor_user_id=cashier,
            operation_id=new_uuid())
        assert result.success
        assert result.data["sale"].customer_id == customer_id

    def test_rejects_a_nonexistent_customer_id(self, conn):
        """SALES-10 regression: before this phase, any UUIDv7-shaped string
        was silently accepted with zero existence check."""
        sale_id, cashier = _start_sale(conn)
        result = AssignCustomerToSaleUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, customer_id=new_uuid(), actor_user_id=cashier,
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "CUSTOMER_NOT_FOUND"

    def test_clearing_customer_still_works_without_existence_check(self, conn):
        sale_id, cashier = _start_sale(conn)
        customer_id = _create_real_customer(conn)
        AssignCustomerToSaleUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, customer_id=customer_id, actor_user_id=cashier,
            operation_id=new_uuid())
        result = AssignCustomerToSaleUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, customer_id=None, actor_user_id=cashier,
            operation_id=new_uuid())
        assert result.success
        assert result.data["sale"].customer_id is None


class TestScanLoyaltyCardForSaleUseCase:
    def test_scan_resolves_and_assigns(self, conn):
        sale_id, cashier = _start_sale(conn)
        legacy_id = new_uuid()
        conn.execute(
            "INSERT INTO clientes (id, nombre, codigo_qr) VALUES (?,?,?)",
            (legacy_id, "Maria Lopez", "QR-0001"))
        conn.commit()

        result = ScanLoyaltyCardForSaleUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, card_code="QR-0001", actor_user_id=cashier,
            operation_id=new_uuid())

        assert result.success
        assigned_customer_id = result.data["sale"].customer_id
        assert assigned_customer_id is not None
        # Must be a REAL bridged Customer Master id, never the raw legacy id.
        assert assigned_customer_id != legacy_id
        bridged_row = conn.execute(
            "SELECT legacy_customer_id, display_name FROM customers WHERE id=?",
            (assigned_customer_id,)).fetchone()
        assert bridged_row["legacy_customer_id"] == legacy_id
        assert bridged_row["display_name"] == "Maria Lopez"

    def test_scan_is_idempotent_across_repeated_scans(self, conn):
        """Scanning the same card twice must bridge to the SAME customer,
        not create a duplicate Customer Master row each time."""
        sale_id, cashier = _start_sale(conn)
        legacy_id = new_uuid()
        conn.execute("INSERT INTO clientes (id, nombre, codigo_qr) VALUES (?,?,?)",
                     (legacy_id, "Pedro Diaz", "QR-0002"))
        conn.commit()

        first = ScanLoyaltyCardForSaleUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, card_code="QR-0002", actor_user_id=cashier,
            operation_id=new_uuid())
        second_sale_id, _ = _start_sale(conn)
        second = ScanLoyaltyCardForSaleUseCase(_allow_all_sales()).execute(
            conn, sale_id=second_sale_id, card_code="QR-0002", actor_user_id=cashier,
            operation_id=new_uuid())

        assert first.data["sale"].customer_id == second.data["sale"].customer_id

    def test_unknown_card_fails_cleanly(self, conn):
        sale_id, cashier = _start_sale(conn)
        result = ScanLoyaltyCardForSaleUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, card_code="NO-SUCH-CARD", actor_user_id=cashier,
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "CUSTOMER_NOT_FOUND"

    def test_scan_by_phone_also_resolves(self, conn):
        sale_id, cashier = _start_sale(conn)
        legacy_id = new_uuid()
        conn.execute("INSERT INTO clientes (id, nombre, telefono) VALUES (?,?,?)",
                     (legacy_id, "Luis Ramirez", "5559876543"))
        conn.commit()
        result = ScanLoyaltyCardForSaleUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, card_code="5559876543", actor_user_id=cashier,
            operation_id=new_uuid())
        assert result.success
