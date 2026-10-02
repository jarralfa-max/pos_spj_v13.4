"""Reglas de Ventas cerradas en la re-auditoría del POS (2026-10-01).

Cada una salió de medir el POS sobre una copia de la base real, no de leer el
prompt maestro:

* ningún producto tenía precio y el carrito aceptaba vender a $0.00;
* los 11 productos se venden por KG y el POS agregaba "1" pieza;
* cambiar la cantidad de una línea en KG la convertía en piezas;
* una tarjeta por más del total dejaba un "cambio" que salía del efectivo;
* `sales.sale_number` (el folio comercial, §6) no lo asignaba nadie.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.application.sales.queries.catalog_query_service import SalesCatalogQueryService
from backend.application.sales.queries.sale_query_service import SaleQueryService
from backend.application.sales.use_cases.cart_use_cases import (
    AddSaleLineUseCase,
    StartSaleUseCase,
    UpdateSaleLineQuantityUseCase,
)
from backend.application.sales.use_cases.checkout_use_cases import CheckoutSaleUseCase
from backend.application.sales.use_cases.lifecycle_use_cases import BeginSaleCheckoutUseCase
from backend.application.sales.use_cases.payment_use_cases import RecordSalePaymentUseCase
from backend.application.sales.use_cases.scan_use_cases import ScanCodeRouter
from backend.domain.sales.entities import Sale
from backend.domain.sales.enums import PaymentMethod, ScanContext
from backend.domain.sales.exceptions import (
    InvalidWeightError,
    PaymentExceedsBalanceError,
    PricingUnavailableError,
    SaleInvalidStateError,
)
from backend.domain.sales.policies.line_policies import WeightPolicy
from backend.domain.sales.policies.payment_policy import CashPaymentPolicy
from backend.domain.sales.value_objects.quantity import Quantity
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import new_uuid

_PREP = {"settle_inventory": False, "require_cash_shift": False}


def _auth() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


def _sale(**kwargs) -> Sale:
    return Sale.start(branch_id=new_uuid(), cashier_user_id=new_uuid(), operation_id=new_uuid(),
                      **kwargs)


# ── dominio ─────────────────────────────────────────────────────────────────

class TestALineNeedsAPrice:
    def test_a_zero_priced_line_is_refused(self):
        with pytest.raises(PricingUnavailableError, match="Precios"):
            _sale().add_line(product_id=new_uuid(), quantity=Quantity(Decimal("1")),
                             unit_price=Decimal("0"))

    def test_a_priced_line_is_accepted(self):
        sale = _sale()
        sale.add_line(product_id=new_uuid(), quantity=Quantity(Decimal("1.250"), "KG"),
                      unit_price=Decimal("80"))
        assert sale.totals.total == Decimal("100.00")


class TestWeight:
    @pytest.mark.parametrize("weight", [Decimal("0"), Decimal("-1"), Decimal("1.2345")])
    def test_invalid_weights_are_refused(self, weight):
        with pytest.raises(InvalidWeightError):
            WeightPolicy.ensure_valid(weight)

    def test_a_float_is_never_a_weight(self):
        with pytest.raises(InvalidWeightError):
            WeightPolicy.ensure_valid(1.25)

    def test_grams_are_a_valid_weight(self):
        assert WeightPolicy.ensure_valid(Decimal("1.250")) == Decimal("1.250")


class TestCashTender:
    def test_change(self):
        tender = CashPaymentPolicy.evaluate(total=Decimal("230.50"), received=Decimal("500"))
        assert (tender.accepted, tender.change, tender.shortfall) == (
            True, Decimal("269.50"), Decimal("0"))

    def test_shortfall(self):
        tender = CashPaymentPolicy.evaluate(total=Decimal("230.50"), received=Decimal("200"))
        assert (tender.accepted, tender.change, tender.shortfall) == (
            False, Decimal("0"), Decimal("30.50"))


class TestOnlyCashGivesChange:
    def _checkout_ready(self) -> Sale:
        sale = _sale()
        sale.add_line(product_id=new_uuid(), quantity=Quantity(Decimal("1")),
                      unit_price=Decimal("100"))
        sale.begin_checkout()
        return sale

    def test_a_card_payment_cannot_exceed_what_is_owed(self):
        with pytest.raises(PaymentExceedsBalanceError):
            self._checkout_ready().record_payment(
                method=PaymentMethod.CARD, amount=Decimal("150"), captured_by_user_id=new_uuid())

    def test_cash_may_exceed_and_the_rest_is_change(self):
        sale = self._checkout_ready()
        sale.record_payment(method=PaymentMethod.CASH, amount=Decimal("150"),
                            captured_by_user_id=new_uuid())
        sale.complete()

    def test_mixed_card_then_cash_change(self):
        sale = self._checkout_ready()
        sale.record_payment(method=PaymentMethod.CARD, amount=Decimal("60"),
                            captured_by_user_id=new_uuid())
        with pytest.raises(PaymentExceedsBalanceError):
            sale.record_payment(method=PaymentMethod.TRANSFER, amount=Decimal("41"),
                                captured_by_user_id=new_uuid())
        sale.record_payment(method=PaymentMethod.CASH, amount=Decimal("100"),
                            captured_by_user_id=new_uuid())
        sale.complete()


class TestCommercialFolio:
    def test_is_assigned_once(self):
        sale = _sale()
        sale.assign_number("V-COR-000001")
        sale.assign_number("V-COR-000001")  # reintento: no cambia nada
        with pytest.raises(SaleInvalidStateError):
            sale.assign_number("V-COR-000002")


# ── aplicación ──────────────────────────────────────────────────────────────

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_products_schema(c)
    create_pricing_schema(c)
    create_inventory_schema(c)
    c.execute("INSERT INTO price_list (id, code, name, kind, status, discount_pct)"
              " VALUES (?, 'BASE', 'Lista base', 'BASE', 'ACTIVE', '0')", (new_uuid(),))
    c.commit()
    yield c
    c.close()


def _unit(conn, code: str, dimension: str) -> str:
    unit_id = new_uuid()
    conn.execute("INSERT INTO units_of_measure (id, code, name, dimension, active)"
                 " VALUES (?,?,?,?,1)", (unit_id, code, code, dimension))
    return unit_id


def _product(conn, *, name: str, code: str, unit_id: str, price: str | None) -> str:
    product_id = new_uuid()
    conn.execute(
        "INSERT INTO products (id, code, name, product_type, base_unit_id, lifecycle_status)"
        " VALUES (?,?,?,?,?,?)", (product_id, code, name, "SIMPLE", unit_id, "ACTIVE"))
    if price is not None:
        base = conn.execute("SELECT id FROM price_list WHERE code='BASE'").fetchone()[0]
        conn.execute("INSERT INTO product_price (id, price_list_id, product_id, sale_price,"
                     " branch_id) VALUES (?,?,?,?,'')", (new_uuid(), base, product_id, price))
    conn.commit()
    return product_id


class TestCatalogSpeaksTheCashiersLanguage:
    def test_the_unit_is_its_code_and_weight_products_say_so(self, conn):
        kg = _unit(conn, "KG", "WEIGHT")
        _product(conn, name="Alas", code="ALAS", unit_id=kg, price="80")

        [alas] = SalesCatalogQueryService(conn).search(branch_id=new_uuid(), search="Alas")

        assert alas.unit == "KG"
        assert alas.sold_by_weight is True
        assert alas.priced is True

    def test_a_product_without_price_is_not_sellable_and_says_why(self, conn):
        pza = _unit(conn, "PZA", "COUNT")
        _product(conn, name="Huacal", code="HUA", unit_id=pza, price=None)

        [huacal] = SalesCatalogQueryService(conn).search(branch_id=new_uuid(), search="Huacal")

        assert huacal.sold_by_weight is False
        assert huacal.priced is False
        assert huacal.sellable is False
        assert any("Precios" in warning for warning in huacal.warnings)


class TestScanner:
    def _route(self, conn, code: str):
        branch, cashier = new_uuid(), new_uuid()
        sale_id = StartSaleUseCase(_auth()).execute(
            conn, branch_id=branch, cashier_user_id=cashier, operation_id=new_uuid(),
            actor_user_id=cashier).entity_id
        result = ScanCodeRouter(_auth()).route(
            conn, sale_id=sale_id, code=code, context=ScanContext.PRODUCT, branch_id=branch,
            actor_user_id=cashier, operation_id=new_uuid())
        return result, sale_id

    def test_a_weight_product_asks_for_the_weight_instead_of_adding_one(self, conn):
        _product(conn, name="Alas", code="ALAS", unit_id=_unit(conn, "KG", "WEIGHT"), price="80")

        result, sale_id = self._route(conn, "ALAS")

        assert result.error_code == "WEIGHT_REQUIRED"
        assert result.data["product"].name == "Alas"
        assert SaleRepository(conn).get(sale_id).lines == []

    def test_a_piece_product_is_added_with_its_real_unit(self, conn):
        _product(conn, name="Huacal", code="HUA", unit_id=_unit(conn, "PZA", "COUNT"),
                 price="15")

        result, sale_id = self._route(conn, "HUA")

        assert result.success, result.message
        assert SaleRepository(conn).get(sale_id).lines[0].quantity.unit == "PZA"

    def test_a_product_without_price_is_refused_with_the_reason(self, conn):
        _product(conn, name="Huacal", code="HUA", unit_id=_unit(conn, "PZA", "COUNT"),
                 price=None)

        result, _sale_id = self._route(conn, "HUA")

        assert result.error_code == "PRODUCT_NOT_SELLABLE"
        assert "Precios" in result.message


class TestUpdatingQuantityKeepsTheUnit:
    def test_a_kg_line_stays_in_kg(self, conn):
        branch, cashier = new_uuid(), new_uuid()
        sale_id = StartSaleUseCase(_auth()).execute(
            conn, branch_id=branch, cashier_user_id=cashier, operation_id=new_uuid(),
            actor_user_id=cashier).entity_id
        line_id = AddSaleLineUseCase(_auth()).execute(
            conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1.250"),
            unit_price=Decimal("80"), quantity_unit="KG", actor_user_id=cashier,
            operation_id=new_uuid()).data["line_id"]

        UpdateSaleLineQuantityUseCase(_auth()).execute(
            conn, sale_id=sale_id, line_id=line_id, quantity=Decimal("2.000"),
            actor_user_id=cashier, operation_id=new_uuid())

        line = SaleRepository(conn).get(sale_id).lines[0]
        assert (line.quantity.value, line.quantity.unit) == (Decimal("2.000"), "KG")


def _completed(conn, *, branch: str) -> str:
    cashier = new_uuid()
    sale_id = StartSaleUseCase(_auth()).execute(
        conn, branch_id=branch, cashier_user_id=cashier, operation_id=new_uuid(),
        actor_user_id=cashier).entity_id
    AddSaleLineUseCase(_auth()).execute(
        conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
        unit_price=Decimal("10"), actor_user_id=cashier, operation_id=new_uuid())
    BeginSaleCheckoutUseCase(_auth()).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    RecordSalePaymentUseCase(_auth()).execute(
        conn, sale_id=sale_id, method="CASH", amount=Decimal("10"), actor_user_id=cashier,
        operation_id=new_uuid())
    result = CheckoutSaleUseCase(_auth(), **_PREP).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    assert result.success, result.message
    return sale_id


class TestCheckoutAssignsTheFolio:
    @pytest.fixture
    def folio_conn(self, conn):
        from backend.infrastructure.db.schema.document_output_schema import (
            create_document_numbering_schema,
        )
        create_document_numbering_schema(conn)
        conn.execute("CREATE TABLE branch_profiles (branch_id TEXT PRIMARY KEY, code TEXT)")
        conn.commit()
        return conn

    def test_consecutive_folios_per_branch_code(self, folio_conn):
        branch = new_uuid()
        folio_conn.execute("INSERT INTO branch_profiles VALUES (?, 'COR')", (branch,))

        first = _completed(folio_conn, branch=branch)
        second = _completed(folio_conn, branch=branch)

        repo = SaleRepository(folio_conn)
        assert repo.get(first).sale_number == "V-COR-000001"
        assert repo.get(second).sale_number == "V-COR-000002"

    def test_a_branch_without_code_still_sells(self, folio_conn):
        sale_id = _completed(folio_conn, branch=new_uuid())
        assert SaleRepository(folio_conn).get(sale_id).sale_number == "V-000001"

    def test_a_posted_sale_is_found_by_folio_and_listed_newest_first(self, folio_conn):
        branch = new_uuid()
        folio_conn.execute("INSERT INTO branch_profiles VALUES (?, 'COR')", (branch,))
        first = _completed(folio_conn, branch=branch)
        second = _completed(folio_conn, branch=branch)
        service = SaleQueryService(folio_conn, _auth())

        found = service.find_posted_by_number(
            branch_id=branch, sale_number="v-cor-000001", requester_user_id=new_uuid())
        recent = service.list_recent_posted(branch_id=branch, requester_user_id=new_uuid())

        assert found.id == first
        assert [dto.id for dto in recent] == [second, first]
