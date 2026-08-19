"""SALES-6/POS-6 — Sales/POS application use cases. Mirrors
tests/integration/customers/test_customer_application.py's style: real
sqlite3 :memory: + real schema + real SalesUnitOfWork, permission checkers
via SalesAuthorizationPolicy.permissive_for_tests() (already built in
SALES-2) rather than mocking the UoW.

All branch/user/customer/workstation ids are real UUIDv7 strings (REGLA
CERO — Sale.start()/suspend()/resume()/assign_customer() all validate id
shape via backend.shared.ids.validate_uuidv7, human-readable literals like
"branch-1" raise ValueError)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    DenyAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.application.sales.result import SaleResult
from backend.application.sales.use_cases.cart_use_cases import (
    AddSaleLineUseCase,
    AssignCustomerToSaleUseCase,
    RemoveSaleLineUseCase,
    StartSaleUseCase,
    UpdateSaleLineQuantityUseCase,
)
from backend.application.sales.use_cases.discount_use_cases import (
    ApplyLineDiscountUseCase,
    ApplySaleDiscountUseCase,
)
from backend.application.sales.use_cases.lifecycle_use_cases import (
    BeginSaleCheckoutUseCase,
    CancelSaleUseCase,
    ResumeSaleUseCase,
    SuspendSaleUseCase,
)
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    create_sales_schema(c)
    # SALES-9: SuspendSaleUseCase now reserves inventory for real (see
    # test_sales_inventory_reservation.py) — these tables must exist for
    # any suspend-path test in this file, same minimal hand-rolled DDL used
    # there (not a full migration run).
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


def _deny_all() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(DenyAllSalesPermissionCheckerForTests())


def _seed_stock(conn, *, branch_id: str, product_id: str, quantity: float = 999.0) -> None:
    conn.execute("INSERT INTO inventory_stock (branch_id, product_id, quantity) VALUES (?,?,?)",
                 (branch_id, product_id, quantity))
    conn.commit()


def _start(conn, *, auth=None, cashier=None, branch=None) -> SaleResult:
    cashier = cashier or new_uuid()
    branch = branch or new_uuid()
    return StartSaleUseCase(auth or _allow_all()).execute(
        conn, branch_id=branch, cashier_user_id=cashier,
        operation_id=new_uuid(), actor_user_id=cashier)


def _active_sale(conn, *, cashier=None) -> tuple[str, str]:
    """Returns (sale_id, cashier_user_id). Seeds abundant stock for the
    line's product/branch so any suspend-path test can reserve it."""
    cashier = cashier or new_uuid()
    branch = new_uuid()
    product_id = new_uuid()
    _seed_stock(conn, branch_id=branch, product_id=product_id)
    sale_id = _start(conn, cashier=cashier, branch=branch).entity_id
    AddSaleLineUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, product_id=product_id, quantity=Decimal("1"),
        unit_price=Decimal("10.00"), actor_user_id=cashier, operation_id=new_uuid())
    return sale_id, cashier


class TestStartSaleUseCase:
    def test_happy_path_creates_sale_in_draft(self, conn):
        result = _start(conn)
        assert result.success
        assert result.entity_id
        assert result.data["sale"].status == "DRAFT"

    def test_permission_denied(self, conn):
        result = _start(conn, auth=_deny_all())
        assert not result.success
        assert result.error_code == "PERMISSION_DENIED"

    def test_idempotent_on_operation_id(self, conn):
        op_id = new_uuid()
        cashier = new_uuid()
        uc = StartSaleUseCase(_allow_all())
        first = uc.execute(conn, branch_id=new_uuid(), cashier_user_id=cashier,
                           operation_id=op_id, actor_user_id=cashier)
        second = uc.execute(conn, branch_id=new_uuid(), cashier_user_id=cashier,
                            operation_id=op_id, actor_user_id=cashier)
        assert first.entity_id == second.entity_id
        count = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
        assert count == 1


class TestCartUseCases:
    def test_add_line_activates_sale_and_updates_total(self, conn):
        cashier = new_uuid()
        sale_id = _start(conn, cashier=cashier).entity_id
        result = AddSaleLineUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("2"),
            unit_price=Decimal("25.00"), actor_user_id=cashier, operation_id=new_uuid())
        assert result.success
        dto = result.data["sale"]
        assert dto.status == "ACTIVE"
        assert dto.total == Decimal("50.00")
        assert len(dto.lines) == 1

    def test_add_line_to_missing_sale_fails(self, conn):
        result = AddSaleLineUseCase(_allow_all()).execute(
            conn, sale_id=new_uuid(), product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal("10.00"), actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "NOT_FOUND"

    def test_update_line_quantity(self, conn):
        cashier = new_uuid()
        sale_id = _start(conn, cashier=cashier).entity_id
        add = AddSaleLineUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal("10.00"), actor_user_id=cashier, operation_id=new_uuid())
        line_id = add.data["line_id"]

        result = UpdateSaleLineQuantityUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, line_id=line_id, quantity=Decimal("4"),
            actor_user_id=cashier, operation_id=new_uuid())
        assert result.success
        assert result.data["sale"].total == Decimal("40.00")

    def test_remove_line(self, conn):
        cashier = new_uuid()
        sale_id = _start(conn, cashier=cashier).entity_id
        add = AddSaleLineUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal("10.00"), actor_user_id=cashier, operation_id=new_uuid())
        line_id = add.data["line_id"]

        result = RemoveSaleLineUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, line_id=line_id, actor_user_id=cashier,
            operation_id=new_uuid())
        assert result.success
        assert result.data["sale"].lines == ()

    def test_assign_and_clear_customer(self, conn):
        """SALES-10: AssignCustomerToSaleUseCase now validates the customer
        exists in Customer Master — full coverage of that behavior lives in
        tests/unit/test_sales_customer_integration.py; this smoke test just
        needs a real row to assign, via the same customers_crm schema."""
        from backend.infrastructure.db.schema.customers_crm_schema import (
            create_customers_crm_schema,
        )
        create_customers_crm_schema(conn)
        from backend.application.customers.authorization import CustomerAuthorizationPolicy
        from backend.application.sales.use_cases.customer_use_cases import (
            QuickCreateCustomerForSaleUseCase,
        )

        cashier = new_uuid()
        sale_id = _start(conn, cashier=cashier).entity_id
        customer_id = QuickCreateCustomerForSaleUseCase(
            CustomerAuthorizationPolicy.permissive_for_tests()).execute(
            conn, actor_user_id=cashier, operation_id=new_uuid(),
            display_name="Cliente de prueba").entity_id
        result = AssignCustomerToSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, customer_id=customer_id, actor_user_id=cashier,
            operation_id=new_uuid())
        assert result.data["sale"].customer_id == customer_id

        cleared = AssignCustomerToSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, customer_id=None, actor_user_id=cashier,
            operation_id=new_uuid())
        assert cleared.data["sale"].customer_id is None


class TestApplySaleDiscountUseCase:
    def _sale_with_line(self, conn, cashier, *, price="100.00") -> str:
        sale_id = _start(conn, cashier=cashier).entity_id
        AddSaleLineUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal(price), actor_user_id=cashier, operation_id=new_uuid())
        return sale_id

    def test_small_discount_needs_no_authorization(self, conn):
        cashier = new_uuid()
        sale_id = self._sale_with_line(conn, cashier)
        result = ApplySaleDiscountUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, discount_amount=Decimal("5.00"),
            actor_user_id=cashier, operation_id=new_uuid())
        assert result.success
        assert result.data["sale"].total == Decimal("95.00")

    def test_large_discount_denied_without_authorizer(self, conn):
        cashier = new_uuid()
        sale_id = self._sale_with_line(conn, cashier)
        result = ApplySaleDiscountUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, discount_amount=Decimal("50.00"),
            actor_user_id=cashier, operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "DISCOUNT_NOT_ALLOWED"

    def test_large_discount_allowed_with_valid_hot_authorization(self, conn):
        cashier = new_uuid()
        supervisor = new_uuid()
        sale_id = self._sale_with_line(conn, cashier)
        result = ApplySaleDiscountUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, discount_amount=Decimal("50.00"),
            actor_user_id=cashier, operation_id=new_uuid(),
            authorizer_user_id=supervisor, reason="cliente frecuente")
        assert result.success
        assert result.data["sale"].total == Decimal("50.00")

    def test_self_authorization_rejected(self, conn):
        cashier = new_uuid()
        sale_id = self._sale_with_line(conn, cashier)
        result = ApplySaleDiscountUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, discount_amount=Decimal("50.00"),
            actor_user_id=cashier, operation_id=new_uuid(),
            authorizer_user_id=cashier, reason="motivo")
        assert not result.success
        assert result.error_code == "SEGREGATION_OF_DUTIES"


class TestApplyLineDiscountUseCase:
    def _sale_with_line(self, conn, cashier, *, price="100.00"):
        sale_id = _start(conn, cashier=cashier).entity_id
        add = AddSaleLineUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal(price), actor_user_id=cashier, operation_id=new_uuid())
        return sale_id, add.data["line_id"]

    def test_small_line_discount_needs_no_authorization(self, conn):
        cashier = new_uuid()
        sale_id, line_id = self._sale_with_line(conn, cashier)
        result = ApplyLineDiscountUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, line_id=line_id, discount_amount=Decimal("5.00"),
            actor_user_id=cashier, operation_id=new_uuid())
        assert result.success
        assert result.data["sale"].lines[0].discount_total == Decimal("5.00")
        assert result.data["sale"].total == Decimal("95.00")

    def test_large_line_discount_denied_without_authorizer(self, conn):
        cashier = new_uuid()
        sale_id, line_id = self._sale_with_line(conn, cashier)
        result = ApplyLineDiscountUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, line_id=line_id, discount_amount=Decimal("50.00"),
            actor_user_id=cashier, operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "DISCOUNT_NOT_ALLOWED"

    def test_large_line_discount_allowed_with_hot_authorization(self, conn):
        cashier = new_uuid()
        supervisor = new_uuid()
        sale_id, line_id = self._sale_with_line(conn, cashier)
        result = ApplyLineDiscountUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, line_id=line_id, discount_amount=Decimal("50.00"),
            actor_user_id=cashier, operation_id=new_uuid(),
            authorizer_user_id=supervisor, reason="producto con defecto menor")
        assert result.success
        assert result.data["sale"].total == Decimal("50.00")

    def test_self_authorization_rejected(self, conn):
        cashier = new_uuid()
        sale_id, line_id = self._sale_with_line(conn, cashier)
        result = ApplyLineDiscountUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, line_id=line_id, discount_amount=Decimal("50.00"),
            actor_user_id=cashier, operation_id=new_uuid(),
            authorizer_user_id=cashier, reason="motivo")
        assert not result.success
        assert result.error_code == "SEGREGATION_OF_DUTIES"

    def test_unknown_line_fails(self, conn):
        cashier = new_uuid()
        sale_id, _line_id = self._sale_with_line(conn, cashier)
        result = ApplyLineDiscountUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, line_id=new_uuid(), discount_amount=Decimal("1.00"),
            actor_user_id=cashier, operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "LINE_NOT_FOUND"


class TestCartTotals:
    """§27/§12 — the cart's totals are always SaleTotalsService-derived and
    fully surfaced through SaleDTO, never recomputed or partially exposed."""

    def test_dto_surfaces_the_full_totals_breakdown(self, conn):
        cashier = new_uuid()
        sale_id = _start(conn, cashier=cashier).entity_id
        AddSaleLineUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal("100.00"), actor_user_id=cashier, operation_id=new_uuid())

        dto = ApplySaleDiscountUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, discount_amount=Decimal("10.00"),
            actor_user_id=cashier, operation_id=new_uuid()).data["sale"]

        # All 8 SaleTotals components must be reachable from the DTO, not
        # just the 4 that happened to be there before this phase.
        assert dto.gross_subtotal == Decimal("100.00")
        assert dto.discount_total == Decimal("10.00")
        assert dto.promotion_total == Decimal("0")
        assert dto.coupon_total == Decimal("0")
        assert dto.loyalty_total == Decimal("0")
        assert dto.tax_total == Decimal("0")
        assert dto.rounding_adjustment == Decimal("0")
        assert dto.total == Decimal("90.00")

    def test_line_and_sale_level_discounts_stack_correctly(self, conn):
        cashier = new_uuid()
        sale_id = _start(conn, cashier=cashier).entity_id
        add = AddSaleLineUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal("200.00"), actor_user_id=cashier, operation_id=new_uuid())
        line_id = add.data["line_id"]

        ApplyLineDiscountUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, line_id=line_id, discount_amount=Decimal("20.00"),
            actor_user_id=cashier, operation_id=new_uuid())
        result = ApplySaleDiscountUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, discount_amount=Decimal("10.00"),
            actor_user_id=cashier, operation_id=new_uuid())

        dto = result.data["sale"]
        # discount_total combines the line's own discount (20) with the
        # sale-level discount (10) — SaleTotalsService's own job, not
        # recomputed by this test.
        assert dto.discount_total == Decimal("30.00")
        assert dto.total == Decimal("170.00")


class TestSuspendResumeCancel:
    def test_suspend_and_resume(self, conn):
        sale_id, cashier = _active_sale(conn)
        suspended = SuspendSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid(),
            max_suspended_sales=5)
        assert suspended.success
        assert suspended.data["sale"].status == "SUSPENDED"

        resumed = ResumeSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert resumed.success
        assert resumed.data["sale"].status == "ACTIVE"

    def test_suspend_enforces_limit(self, conn):
        sale_id, cashier = _active_sale(conn)
        workstation = new_uuid()
        result = SuspendSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid(),
            max_suspended_sales=5, workstation_id=workstation)
        assert result.success  # 0 currently suspended, under the limit

    def test_resume_denies_cross_user_when_configured(self, conn):
        sale_id, cashier = _active_sale(conn)
        other_cashier = new_uuid()
        SuspendSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid(),
            max_suspended_sales=5)

        result = ResumeSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=other_cashier, operation_id=new_uuid(),
            allow_cross_user_resume=False)
        assert not result.success
        assert result.error_code == "RESUME_NOT_ALLOWED"

    def test_cancel_active_sale(self, conn):
        sale_id, cashier = _active_sale(conn)
        result = CancelSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, reason="cliente se arrepintió",
            actor_user_id=cashier, operation_id=new_uuid())
        assert result.success
        assert result.data["sale"].status == "CANCELLED"


class TestBeginSaleCheckoutUseCase:
    def test_happy_path(self, conn):
        sale_id, cashier = _active_sale(conn)
        result = BeginSaleCheckoutUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert result.success
        assert result.data["sale"].status == "CHECKOUT_PENDING"

    def test_empty_cart_rejected(self, conn):
        cashier = new_uuid()
        sale_id = _start(conn, cashier=cashier).entity_id
        result = BeginSaleCheckoutUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert not result.success
        # DRAFT (no lines yet) can't even reach CHECKOUT_PENDING via the
        # lifecycle transition table — same structural-impossibility shape
        # already documented in SALES-3's own test suite.
        assert result.error_code == "INVALID_STATE"


class TestEventsAreEnqueued:
    def test_start_sale_enqueues_outbox_event(self, conn):
        _start(conn)
        pending = conn.execute(
            "SELECT COUNT(*) FROM sales_outbox WHERE event_name='SALE_STARTED'").fetchone()[0]
        assert pending == 1

    def test_atomicity_rollback_leaves_no_outbox_event(self, conn):
        """A denied permission never even opens the UoW — no outbox row."""
        _start(conn, auth=_deny_all())
        pending = conn.execute("SELECT COUNT(*) FROM sales_outbox").fetchone()[0]
        assert pending == 0
