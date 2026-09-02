"""SALES-11/POS-11 — Pricing y beneficios: Effective price, Promotions,
Loyalty, Coupons, Vouchers, Tests.

Builds real Pricing schema (`create_pricing_schema` + `PricingRepository`,
same fixture shape as tests/integration/pricing/test_pricing_query_services.py)
and a minimal hand-rolled `loyalty_ledger` (the exact final DDL from
migrations/standalone/092_loyalty_ledger_canonicalization.py, confirmed by
executing `LoyaltyService.preview_redemption` directly against an empty DB
first — it only needs this one table, `configuraciones`/`_cfg()` already
degrades gracefully without it).
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    DenyAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.application.sales.queries.benefit_evaluation_service import SaleBenefitEvaluationService
from backend.application.sales.use_cases.cart_use_cases import AddSaleLineUseCase, AssignCustomerToSaleUseCase, StartSaleUseCase
from backend.application.sales.use_cases.customer_use_cases import QuickCreateCustomerForSaleUseCase
from backend.application.sales.use_cases.discount_use_cases import ApplySaleDiscountUseCase
from backend.domain.pricing.entities.price_list import PriceList
from backend.domain.pricing.entities.product_price import ProductPrice
from backend.domain.pricing.enums import PriceListKind
from backend.domain.pricing.value_objects.money import Money
from backend.domain.sales.exceptions import SaleNotFoundError, SalesPermissionDeniedError
from backend.infrastructure.db.repositories.pricing.pricing_repository import PricingRepository
from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.infrastructure.integrations.sales_loyalty_client import SalesLoyaltyClient
from backend.infrastructure.integrations.sales_pricing_client import SalesPricingClient
from backend.shared.ids import new_uuid


def _m(v):
    return Money(Decimal(str(v)))


def _allow_all_sales() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


def _allow_all_customers() -> CustomerAuthorizationPolicy:
    return CustomerAuthorizationPolicy.permissive_for_tests()


# ── Effective price ─────────────────────────────────────────────────────

@pytest.fixture
def pricing_conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_pricing_schema(c)
    c.commit()
    yield c
    c.close()


def _active_base_list(repo):
    pl = PriceList(code="BASE", name="Base", kind=PriceListKind.BASE)
    pl.submit()
    pl.approve(approved_by_user_id="mgr")
    pl.activate()
    repo.save_list(pl)
    return pl


class TestSalesPricingClient:
    def test_effective_price_resolves_base_price(self, pricing_conn):
        repo = PricingRepository(pricing_conn)
        pl = _active_base_list(repo)
        repo.save_price(ProductPrice(price_list_id=pl.id, product_id="p1", sale_price=_m("45.50")))

        client = SalesPricingClient(pricing_conn)
        assert client.effective_price("p1") == Decimal("45.50")

    def test_effective_price_prefers_branch_override(self, pricing_conn):
        repo = PricingRepository(pricing_conn)
        pl = _active_base_list(repo)
        repo.save_price(ProductPrice(price_list_id=pl.id, product_id="p1", sale_price=_m("45.50")))
        repo.save_price(ProductPrice(price_list_id=pl.id, product_id="p1", branch_id="b1",
                                     sale_price=_m("40.00")))

        client = SalesPricingClient(pricing_conn)
        assert client.effective_price("p1", branch_id="b1") == Decimal("40.00")

    def test_effective_price_returns_none_when_unconfigured(self, pricing_conn):
        client = SalesPricingClient(pricing_conn)
        assert client.effective_price("no-such-product") is None


# ── Loyalty ──────────────────────────────────────────────────────────────

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_customers_crm_schema(c)
    c.execute("""
        CREATE TABLE clientes (
            id TEXT PRIMARY KEY, nombre TEXT NOT NULL, telefono TEXT, email TEXT,
            codigo_qr TEXT, codigo_fidelidad TEXT, activo INTEGER DEFAULT 1, puntos INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE loyalty_ledger (
            id TEXT NOT NULL PRIMARY KEY, cliente_id TEXT NOT NULL,
            tipo TEXT NOT NULL CHECK(tipo IN ('acumulacion','canje','reversa','ajuste')),
            puntos INTEGER NOT NULL, monto_equiv REAL DEFAULT 0, saldo_post INTEGER DEFAULT 0,
            referencia TEXT DEFAULT '', descripcion TEXT DEFAULT '', sucursal_id TEXT,
            usuario TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    c.commit()
    yield c
    c.close()


def _create_customer(conn, *, display_name="Ana Torres") -> str:
    return QuickCreateCustomerForSaleUseCase(_allow_all_customers()).execute(
        conn, actor_user_id=new_uuid(), operation_id=new_uuid(),
        display_name=display_name).entity_id


def _award_points(conn, *, legacy_customer_id: str, points: int) -> None:
    conn.execute(
        "INSERT INTO loyalty_ledger (id, cliente_id, tipo, puntos, saldo_post) "
        "VALUES (?, ?, 'acumulacion', ?, ?)",
        (new_uuid(), legacy_customer_id, points, points))
    conn.commit()


class TestSalesLoyaltyClient:
    def test_preview_redemption_bridges_identity_and_returns_real_preview(self, conn):
        customer_id = _create_customer(conn)
        # Bridge customer -> legacy id the same way the client itself will,
        # so we can award points on the LEGACY side before previewing.
        from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
            EnsureLegacyCustomerBridgeUseCase,
        )
        legacy_id = EnsureLegacyCustomerBridgeUseCase().execute(conn, customer_id=customer_id)
        conn.execute("INSERT OR IGNORE INTO clientes (id, nombre) VALUES (?, 'Bridge stub')",
                     (legacy_id,))
        conn.commit()
        _award_points(conn, legacy_customer_id=legacy_id, points=100)

        client = SalesLoyaltyClient(conn)
        preview = client.preview_redemption(customer_id=customer_id, subtotal=Decimal("500.00"))

        assert preview["enabled"] is True
        assert preview["puntos_disponibles"] == 100

    def test_preview_redemption_customer_with_no_points(self, conn):
        customer_id = _create_customer(conn)
        client = SalesLoyaltyClient(conn)
        preview = client.preview_redemption(customer_id=customer_id, subtotal=Decimal("100.00"))
        assert preview["puntos_disponibles"] == 0

    def test_peek_loyalty_summary_reads_balance_and_tier_without_side_effects(self, conn):
        from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
            EnsureLegacyCustomerBridgeUseCase,
        )

        customer_id = _create_customer(conn)
        legacy_id = EnsureLegacyCustomerBridgeUseCase().execute(conn, customer_id=customer_id)
        conn.execute("INSERT OR IGNORE INTO clientes (id, nombre) VALUES (?, 'Bridge stub')", (legacy_id,))
        conn.commit()
        _award_points(conn, legacy_customer_id=legacy_id, points=250)

        summary = SalesLoyaltyClient(conn).peek_loyalty_summary(customer_id=customer_id)

        assert summary.points_balance == 250
        assert summary.available is True
        assert summary.points_earned is None  # sales_pos has no earning pipeline yet

        # Never earns or redeems — the ledger must be untouched by a peek.
        rows = conn.execute(
            "SELECT COUNT(*) AS n FROM loyalty_ledger WHERE cliente_id=?", (legacy_id,)).fetchone()
        assert rows["n"] == 1  # only the one _award_points insert above

    def test_peek_loyalty_summary_customer_with_no_points(self, conn):
        customer_id = _create_customer(conn)
        summary = SalesLoyaltyClient(conn).peek_loyalty_summary(customer_id=customer_id)
        assert summary.points_balance == 0


# ── SaleBenefitEvaluationDTO composition ────────────────────────────────

def _start_sale_with_line(conn, *, price="100.00") -> tuple[str, str]:
    cashier = new_uuid()
    sale_id = StartSaleUseCase(_allow_all_sales()).execute(
        conn, branch_id=new_uuid(), cashier_user_id=cashier,
        operation_id=new_uuid(), actor_user_id=cashier).entity_id
    AddSaleLineUseCase(_allow_all_sales()).execute(
        conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
        unit_price=Decimal(price), actor_user_id=cashier, operation_id=new_uuid())
    return sale_id, cashier


class TestSaleBenefitEvaluationService:
    def test_evaluate_missing_sale_raises(self, conn):
        service = SaleBenefitEvaluationService(conn, _allow_all_sales())
        with pytest.raises(SaleNotFoundError):
            service.evaluate(new_uuid(), requester_user_id=new_uuid())

    def test_evaluate_requires_permission(self, conn):
        sale_id, cashier = _start_sale_with_line(conn)
        service = SaleBenefitEvaluationService(
            conn, SalesAuthorizationPolicy(DenyAllSalesPermissionCheckerForTests()))
        with pytest.raises(SalesPermissionDeniedError):
            service.evaluate(sale_id, requester_user_id=cashier)

    def test_no_customer_warns_and_zeroes_loyalty(self, conn):
        sale_id, cashier = _start_sale_with_line(conn)
        service = SaleBenefitEvaluationService(conn, _allow_all_sales())
        dto = service.evaluate(sale_id, requester_user_id=cashier)

        assert dto.loyalty_points_available == 0
        assert dto.loyalty_max_redemption_value == Decimal("0")
        assert any("Sin cliente asignado" in w for w in dto.warnings)

    def test_promotions_coupons_vouchers_always_zero_with_warnings(self, conn):
        sale_id, cashier = _start_sale_with_line(conn)
        service = SaleBenefitEvaluationService(conn, _allow_all_sales())
        dto = service.evaluate(sale_id, requester_user_id=cashier)

        assert dto.promotion_discount == Decimal("0")
        assert dto.coupon_discount == Decimal("0")
        assert dto.voucher_amount == Decimal("0")
        assert any("Promociones" in w for w in dto.warnings)
        assert any("Cupones" in w for w in dto.warnings)
        assert any("Vales" in w for w in dto.warnings)

    def test_commercial_discount_reflected_and_manual_auth_flagged(self, conn):
        sale_id, cashier = _start_sale_with_line(conn, price="100.00")
        ApplySaleDiscountUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, discount_amount=Decimal("50.00"), actor_user_id=cashier,
            operation_id=new_uuid(), authorizer_user_id=new_uuid(), reason="autorizado")

        service = SaleBenefitEvaluationService(conn, _allow_all_sales())
        dto = service.evaluate(sale_id, requester_user_id=cashier)

        assert dto.commercial_discount == Decimal("50.00")
        assert dto.requires_manual_authorization is True

    def test_small_discount_does_not_require_manual_authorization(self, conn):
        sale_id, cashier = _start_sale_with_line(conn, price="100.00")
        ApplySaleDiscountUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, discount_amount=Decimal("5.00"), actor_user_id=cashier,
            operation_id=new_uuid())

        service = SaleBenefitEvaluationService(conn, _allow_all_sales())
        dto = service.evaluate(sale_id, requester_user_id=cashier)
        assert dto.requires_manual_authorization is False

    def test_customer_with_points_surfaces_real_redemption_preview(self, conn):
        sale_id, cashier = _start_sale_with_line(conn, price="500.00")
        customer_id = _create_customer(conn)
        AssignCustomerToSaleUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, customer_id=customer_id, actor_user_id=cashier,
            operation_id=new_uuid())

        from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
            EnsureLegacyCustomerBridgeUseCase,
        )
        legacy_id = EnsureLegacyCustomerBridgeUseCase().execute(conn, customer_id=customer_id)
        conn.execute("INSERT OR IGNORE INTO clientes (id, nombre) VALUES (?, 'Bridge stub')",
                     (legacy_id,))
        conn.commit()
        _award_points(conn, legacy_customer_id=legacy_id, points=200)

        service = SaleBenefitEvaluationService(conn, _allow_all_sales())
        dto = service.evaluate(sale_id, requester_user_id=cashier)

        assert dto.loyalty_points_available > 0
        assert dto.loyalty_max_redemption_value > Decimal("0")
        assert not any("Sin cliente asignado" in w for w in dto.warnings)
