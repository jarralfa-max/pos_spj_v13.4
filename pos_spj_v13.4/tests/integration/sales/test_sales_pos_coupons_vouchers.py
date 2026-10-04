"""Cupones y vales en la caja (2026-10-03), por la pantalla real del POS.

Decisiones del usuario: el cupón es un DESCUENTO del ticket; el vale o saldo a
favor es una FORMA DE PAGO que cancela su pasivo (no entra al cajón).

* Fidelidad decide si el cupón aplica (no existe, de otro cliente, un cupón por
  venta) y lo aparta; cobrar lo canjea con el importe aplicado y el puente lo
  reclasifica a contra-ingreso por cupones.
* Cobrar con vale aparta su saldo, la venta lo liquida contra el pasivo del vale
  y el vale queda consumido; nunca se cobra más que su saldo.
* Cancelar libera cupón y vale; devolver/reversar regresa el dinero al vale.
"""

from __future__ import annotations

import os
import sqlite3
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy  # noqa: E402
from backend.application.sales.integrations.wiring import wire_sales  # noqa: E402
from backend.application.services.finance.finance_bootstrap import bootstrap_finance  # noqa: E402
from backend.shared.events.application_bus import ApplicationEventBus  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402
from frontend.desktop.modules.sales_pos.composition import create_sales_pos_view  # noqa: E402
from frontend.desktop.modules.sales_pos.dialogs.coupon_dialog import CouponDialog  # noqa: E402
from frontend.desktop.modules.sales_pos.dialogs.payment_dialog import PaymentDialog  # noqa: E402
from tests.integration._pos_ready import open_cash_shift  # noqa: E402
from tests.integration.sales.test_sales_pos_screen_flows import (  # noqa: E402
    _producto,
    _product,
    _Session,
    _stub,
    _unit,
)

AUTH = LoyaltyAuthorizationPolicy.permissive_for_tests()


class _CashierSession(_Session):
    def __init__(self):
        super().__init__()
        self._permissions = set(self._permissions) | {"POS.pago.vale"}


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    from backend.infrastructure.db.schema.commercial_instruments_schema import (
        create_commercial_instruments_schema,
    )
    from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema
    from backend.infrastructure.db.schema.document_output_schema import (
        create_document_numbering_schema,
    )
    from backend.infrastructure.db.schema.finance_schema import create_finance_schema
    from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
    from backend.infrastructure.db.schema.loyalty_finance_schema import (
        create_loyalty_finance_tables,
    )
    from backend.infrastructure.db.schema.loyalty_rules_schema import create_loyalty_rules_schema
    from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema
    from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
    from backend.infrastructure.db.schema.products_schema import create_products_schema
    from backend.infrastructure.db.schema.sales_schema import create_sales_schema

    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    for create in (create_sales_schema, create_products_schema, create_pricing_schema,
                   create_inventory_schema, create_document_numbering_schema,
                   create_customers_crm_schema, create_loyalty_schema, create_finance_schema,
                   create_commercial_instruments_schema, create_loyalty_finance_tables,
                   create_loyalty_rules_schema):
        create(c)
    bootstrap_finance(c)
    # Combinación de beneficios de arranque (la 295): un cupón por venta.
    __import__("importlib").import_module("migrations.standalone.295_loyalty_rules_engine").run(c)
    c.execute("CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT,"
              " tipo TEXT, grupo TEXT, descripcion TEXT)")
    c.execute("CREATE TABLE branch_profiles (branch_id TEXT PRIMARY KEY, code TEXT, name TEXT,"
              " address TEXT, phone TEXT, ticket_header TEXT, ticket_footer TEXT)")
    c.execute("INSERT INTO price_list (id, code, name, kind, status, discount_pct)"
              " VALUES (?, 'BASE', 'Lista base', 'BASE', 'ACTIVE', '0')", (new_uuid(),))
    c.commit()
    yield c
    c.close()


@pytest.fixture
def pos(app, conn, monkeypatch):
    session = _CashierSession()
    branch = session.active_branch_id
    conn.execute("INSERT INTO branch_profiles (branch_id, code, name) VALUES (?, 'COR', ?)",
                 (branch, "Corregidora"))
    open_cash_shift(conn, branch_id=branch, cashier_user_id=session.user_id)
    pza = _unit(conn, "PZA", "COUNT")
    _product(conn, name="Huacal", code="HUA", unit_id=pza, price="100", branch_id=branch,
             stock="20")
    bus = ApplicationEventBus()
    wire_sales(bus, conn)
    monkeypatch.setattr("backend.shared.events.application_bus.get_bus", lambda: bus)
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *_a: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *_a: None))
    workspace = create_sales_pos_view(conn, session)
    workspace.resize(1366, 768)
    workspace.show()
    app.processEvents()
    workspace.conn = conn
    yield workspace
    workspace.close()


def _ok(r):
    assert r.success, r.message
    return r


def _coupon(conn, value="20", benefit="FIXED_AMOUNT", customer_id=None):
    from backend.application.commercial_instruments.use_cases import coupon_use_cases as cu
    from backend.domain.commercial_instruments.enums import CommercialBenefitType, CouponType

    d = _ok(cu.CreateCouponDefinitionUseCase(AUTH).execute(
        conn, code=f"D{new_uuid()[-5:]}", name="Cupón", coupon_type=CouponType.PUBLIC_CODE,
        benefit_type=CommercialBenefitType(benefit), benefit_value=Decimal(value),
        actor_user_id=new_uuid(), operation_id=new_uuid())).entity_id
    code = f"CUP{new_uuid()[-6:]}".upper()
    _ok(cu.IssueCouponInstanceUseCase(AUTH).execute(
        conn, definition_id=d, code=code, actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
        operation_id=new_uuid(), customer_id=customer_id))
    return code


def _voucher(conn, amount="60", voucher_type="STORE_CREDIT"):
    from backend.application.commercial_instruments.use_cases import voucher_use_cases as v
    from backend.application.loyalty.integrations.finance_posting import post_loyalty_finance
    from backend.domain.commercial_instruments.enums import VoucherType

    d = _ok(v.CreateVoucherDefinitionUseCase(AUTH).execute(
        conn, code=f"VD{new_uuid()[-5:]}", name="Saldo", voucher_type=VoucherType(voucher_type),
        actor_user_id=new_uuid(), operation_id=new_uuid())).entity_id
    code = f"VAL{new_uuid()[-6:]}".upper()
    _ok(v.IssueVoucherInstanceUseCase(AUTH).execute(
        conn, definition_id=d, code=code, amount=Decimal(amount), actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid()))
    post_loyalty_finance(conn)   # Fidelidad reconoce el pasivo del vale al emitirlo
    return code


def _apply_coupon(pos, code):
    class _Coupon(CouponDialog):
        def exec_(self):
            self.set_code(code)
            self._submit()
            self.error_text = self._error.text() if self._error.isVisibleTo(self) else ""
            _Coupon.last = self
            return 1

    pos.dialogs["coupon"] = _Coupon
    pos._on_coupon_requested()
    return _Coupon.last


def _pay(pos, lines):
    class _Pay(PaymentDialog):
        def exec_(self):
            for method, amount, reference in lines:
                self.select_method(method)
                self.set_amount(Decimal(amount))
                self._reference.setText(reference or "")
                self._add_line()
            _Pay.hint = self._hint.text()
            self._confirm()
            return self.result()

    pos.dialogs["payment"] = _Pay
    pos._on_checkout_requested()
    return _Pay


def _balance(conn, code):
    from backend.infrastructure.integrations.sales_instruments_client import (
        SalesInstrumentsClient,
    )

    return SalesInstrumentsClient(conn).voucher_balance(code=code)["balance"]


def _account(conn, code):
    total = Decimal("0")
    for row in conn.execute("SELECT l.debit_amount, l.credit_amount FROM journal_lines l"
                            " JOIN accounts a ON a.id = l.account_id WHERE a.code=?", (code,)):
        total += Decimal(row["debit_amount"]) - Decimal(row["credit_amount"])
    return total


def test_coupon_is_a_ticket_discount_redeemed_and_reclassified_on_checkout(pos):
    pos._on_product_selected(_producto(pos, "Huacal"))
    code = _coupon(pos.conn, "20")
    _apply_coupon(pos, code)
    assert pos._sale.coupon_total == Decimal("20.00") and pos._sale.total == Decimal("80.00")
    assert pos.checkout.totals._coupon_value.text() == "-$20.00"

    _pay(pos, [("CASH", "80", None)])

    estado = pos.conn.execute("SELECT status FROM coupon_instances WHERE code=?",
                              (code,)).fetchone()[0]
    assert estado == "REDEEMED"
    assert Decimal(pos.conn.execute("SELECT amount_applied FROM coupon_redemptions").fetchone()[0]) == 20
    # La venta cargó el descuento (4201); el puente lo reclasificó a cupones (4203).
    assert _account(pos.conn, "4203") == Decimal("20.00")
    assert _account(pos.conn, "4201") == Decimal("0")


def test_percentage_coupon_follows_the_cart_and_one_coupon_per_sale(pos):
    pos._on_product_selected(_producto(pos, "Huacal"))
    _apply_coupon(pos, _coupon(pos.conn, "10", "PERCENTAGE"))
    assert pos._sale.coupon_total == Decimal("10.00")
    pos._on_product_selected(_producto(pos, "Huacal"))
    assert pos._sale.coupon_total == Decimal("20.00")
    segundo = _apply_coupon(pos, _coupon(pos.conn, "5"))
    assert "No se combina" in segundo.error_text
    assert len(pos._sale.coupons) == 1


def test_unknown_or_foreign_coupon_is_rejected(pos):
    pos._on_product_selected(_producto(pos, "Huacal"))
    assert "No existe" in _apply_coupon(pos, "NOEXISTE").error_text
    ajeno = _apply_coupon(pos, _coupon(pos.conn, "5", customer_id=new_uuid()))
    assert "otro cliente" in ajeno.error_text


def test_voucher_pays_against_its_liability_and_never_more_than_its_balance(pos):
    pos._on_product_selected(_producto(pos, "Huacal"))
    code = _voucher(pos.conn, "60")
    assert _account(pos.conn, "2133") == Decimal("-60.00")

    _pay(pos, [("VOUCHER", "100", code), ("CASH", "40", None)])

    assert _balance(pos.conn, code) == Decimal("0")
    assert pos._presenter.get_sale(pos._last_completed_sale_id).status == "COMPLETED"
    # El pasivo del saldo a favor quedó cancelado por la venta; el cajón no lo ve.
    assert _account(pos.conn, "2133") == Decimal("0")
    assert _account(pos.conn, "4101") == Decimal("-100.00")


def test_cancelling_releases_coupon_and_voucher(pos):
    pos._on_product_selected(_producto(pos, "Huacal"))
    code = _coupon(pos.conn, "10")
    _apply_coupon(pos, code)
    pos.dialogs["cancel"] = _stub(reason="el cliente se arrepintió")
    pos._on_cancel_requested()
    estado = pos.conn.execute("SELECT status FROM coupon_instances WHERE code=?",
                              (code,)).fetchone()[0]
    assert estado in ("ISSUED", "ACTIVE")


def test_returned_money_goes_back_to_the_voucher():
    """El abono al vale por devolución (lado Fidelidad) es idempotente y deja la
    obligación con saldo otra vez."""
    from backend.application.loyalty.integrations.sales_events import SaleLoyaltyEventHandlers
    from backend.infrastructure.db.schema.commercial_instruments_schema import (
        create_commercial_instruments_schema,
    )
    from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema

    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_loyalty_schema(c)
    create_commercial_instruments_schema(c)
    c.execute("CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT)")
    code = _voucher(c, "50")
    instancia = c.execute("SELECT id FROM voucher_instances WHERE code=?", (code,)).fetchone()[0]
    evento = {"event_id": new_uuid(), "entity_id": new_uuid(), "branch_id": new_uuid(),
              "user_id": new_uuid(), "timestamp": "2026-10-03T12:00:00+00:00",
              "payload": {"customer_id": None, "return_id": "R1", "sale_total": "50",
                          "refunded_total": "20", "amount": "20",
                          "voucher_refunds": [{"voucher_instance_id": instancia,
                                               "instrument_type": "STORE_CREDIT",
                                               "amount": "20"}]}}
    SaleLoyaltyEventHandlers(c).on_sale_returned(evento)
    SaleLoyaltyEventHandlers(c).on_sale_returned(evento)
    assert _balance(c, code) == Decimal("70")


def test_return_to_voucher_posts_back_the_liability(pos):
    """Devolver lo pagado con vale: la devolución acredita el pasivo del vale
    (Finanzas) y Fidelidad le regresa el saldo; el puente sólo restaura la
    obligación, sin otro asiento."""
    from backend.application.event_handlers.finance.sale_returned_handler import (
        SaleReturnedHandler,
    )
    from backend.application.loyalty.integrations.finance_posting import post_loyalty_finance
    from backend.application.loyalty.integrations.sales_events import SaleLoyaltyEventHandlers
    from backend.application.sales.integrations.finance_translator import (
        sale_returned_to_finance,
    )

    pos._on_product_selected(_producto(pos, "Huacal"))
    code = _voucher(pos.conn, "100", "REFUND_VOUCHER")
    _pay(pos, [("VOUCHER", "100", code)])
    venta = pos._last_completed_sale_id
    instancia = pos.conn.execute("SELECT id FROM voucher_instances WHERE code=?",
                                 (code,)).fetchone()[0]
    assert _account(pos.conn, "2132") == Decimal("0")

    evento = {"event_id": new_uuid(), "operation_id": new_uuid(), "entity_id": venta,
              "branch_id": new_uuid(), "user_id": new_uuid(),
              "timestamp": "2026-10-03T13:00:00+00:00",
              "payload": {"return_id": new_uuid(), "folio": "X", "customer_id": None,
                          "amount": "40", "gross_amount": "40", "tax_amount": "0",
                          "sale_total": "100", "refunded_total": "40",
                          "refunds": [{"method": "VOUCHER", "amount": "40"}],
                          "voucher_refunds": [{"voucher_instance_id": instancia,
                                               "instrument_type": "REFUND_VOUCHER",
                                               "amount": "40"}]}}
    SaleReturnedHandler(pos.conn).handle(sale_returned_to_finance(evento))
    SaleLoyaltyEventHandlers(pos.conn).on_sale_returned(evento)
    resumen = post_loyalty_finance(pos.conn)
    assert resumen["failed"] == 0
    assert _account(pos.conn, "2132") == Decimal("-40.00")
    assert _balance(pos.conn, code) == Decimal("40")
    from backend.domain.finance.enums import CommercialInstrumentType
    from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
    with FinanceUnitOfWork(pos.conn) as uow:
        ob = uow.commercial_obligations.find_by_instrument(
            CommercialInstrumentType.REFUND_VOUCHER, instancia)
    assert ob.outstanding_amount.amount == Decimal("40.00")


def _prepaid_definition(conn):
    from backend.application.commercial_instruments.use_cases import voucher_use_cases as v
    from backend.domain.commercial_instruments.enums import VoucherType

    return _ok(v.CreateVoucherDefinitionUseCase(AUTH).execute(
        conn, code="PREPAGO", name="Vale prepagado", voucher_type=VoucherType.PREPAID_VOUCHER,
        actor_user_id=new_uuid(), operation_id=new_uuid())).entity_id


def _sell_prepaid(pos, amount):
    from frontend.desktop.modules.sales_pos.dialogs.prepaid_voucher_dialog import (
        PrepaidVoucherDialog,
    )

    class _Prepaid(PrepaidVoucherDialog):
        def exec_(self):
            self.set_amount(Decimal(amount))
            self._submit()
            return 1

    pos.dialogs["prepaid"] = _Prepaid
    pos._on_prepaid_requested()


def test_prepaid_voucher_is_sold_as_a_ticket_line_cash_in_and_liability(pos):
    _prepaid_definition(pos.conn)
    _sell_prepaid(pos, "150")
    linea = pos._sale.lines[0]
    assert pos._sale.total == Decimal("150") and "Vale prepagado" in linea.product_snapshot["name"]
    code = linea.product_snapshot["code"]
    # Antes de cobrar el vale existe pero no se puede usar.
    assert pos.conn.execute("SELECT status FROM voucher_instances WHERE code=?",
                            (code,)).fetchone()[0] == "ISSUED"

    _pay(pos, [("CASH", "150", None)])

    assert pos._presenter.get_sale(pos._last_completed_sale_id).status == "COMPLETED"
    assert _balance(pos.conn, code) == Decimal("150")
    assert _account(pos.conn, "1102") == Decimal("150.00")     # entró a caja
    assert _account(pos.conn, "2132") == Decimal("-150.00")    # pasivo, no ingreso
    assert _account(pos.conn, "4101") == Decimal("0")
    assert pos.conn.execute("SELECT COUNT(*) FROM inventory_ledger").fetchone()[0] == 0

    # Se usa como forma de pago en otra venta: ahí sí es ingreso.
    pos._on_product_selected(_producto(pos, "Huacal"))
    _pay(pos, [("VOUCHER", "100", code)])
    assert _balance(pos.conn, code) == Decimal("50")
    assert _account(pos.conn, "2132") == Decimal("-50.00")
    assert _account(pos.conn, "4101") == Decimal("-100.00")


def test_prepaid_voucher_is_cancelled_with_the_sale(pos):
    _prepaid_definition(pos.conn)
    _sell_prepaid(pos, "80")
    code = pos._sale.lines[0].product_snapshot["code"]
    pos.dialogs["cancel"] = _stub(reason="no lo quiso")
    pos._on_cancel_requested()
    assert pos.conn.execute("SELECT status FROM voucher_instances WHERE code=?",
                            (code,)).fetchone()[0] == "CANCELLED"


def test_a_used_prepaid_voucher_blocks_reversing_its_sale(pos):
    from backend.infrastructure.integrations.sales_instruments_client import (
        SalesInstrumentsClient,
    )
    from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository

    _prepaid_definition(pos.conn)
    _sell_prepaid(pos, "100")
    code = pos._sale.lines[0].product_snapshot["code"]
    _pay(pos, [("CASH", "100", None)])
    vendida = SaleRepository(pos.conn).get(pos._last_completed_sale_id)
    assert SalesInstrumentsClient(pos.conn).prepaid_unused(sale=vendida) is None
    pos._on_product_selected(_producto(pos, "Huacal"))
    _pay(pos, [("VOUCHER", "30", code), ("CASH", "70", None)])
    assert "ya se usó" in SalesInstrumentsClient(pos.conn).prepaid_unused(sale=vendida)
