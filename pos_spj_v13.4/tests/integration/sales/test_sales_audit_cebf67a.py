"""Auditoría de Ventas / POS cebf67a (2026-10-15) — un caso por hallazgo.

Decisiones del usuario: cancelar con pagos = COMPENSAR Y AVISAR (V02); cada
caja sólo opera ventas de SU sucursal (V05); Caja "TODO O NADA" (V06).
"""

from __future__ import annotations

import os
import sqlite3
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.application.sales.authorization import SalesAuthorizationPolicy
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.queries.catalog_query_service import SalesCatalogQueryService
from backend.application.sales.use_cases.cart_use_cases import (
    AddSaleLineUseCase,
    AssignCustomerToSaleUseCase,
    StartSaleUseCase,
    UpdateSaleLineQuantityUseCase,
)
from backend.application.use_cases.finance.register_sale_credit_charge_use_case import RegisterSaleCreditChargeUseCase, VoidSaleCreditChargeUseCase
from backend.domain.sales.enums import PaymentMethod, SaleStatus
from backend.domain.sales.exceptions import SaleCancellationNotAllowedError
from backend.domain.sales.value_objects.sale_payment import SalePayment
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.db.schema.finance_schema import create_finance_schema
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.infrastructure.integrations import sales_cash_effects_client as cash_client
from backend.infrastructure.integrations.sales_cash_effects_client import SalesCashEffectsClient
from backend.infrastructure.integrations.sales_credit_client import SalesCreditClient
from backend.shared.ids import new_uuid
from frontend.desktop.modules.sales_pos.composition import build_sales_pos_presenter
from tests.integration._pos_ready import open_cash_shift, stock_product


class _Session:
    def __init__(self, branch_id: str | None = None, user_id: str | None = None):
        self.user_id = user_id or new_uuid()
        self.active_branch_id = branch_id or new_uuid()
        self.is_active = True
        self._permissions = ({v for v in vars(SalesPermissions).values() if isinstance(v, str)}
                             | {"INVENTARIO.reserva.crear", "INVENTARIO.reserva.liberar",
                                "INVENTARIO.reserva.ver"})

    def tiene_permiso(self, code: str) -> bool:
        return code in self._permissions


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_products_schema(c)
    create_pricing_schema(c)
    create_inventory_schema(c)
    create_finance_schema(c)
    c.commit()
    yield c
    c.close()


def _pos(conn, session=None):
    session = session or _Session()
    open_cash_shift(conn, branch_id=session.active_branch_id, cashier_user_id=session.user_id)
    product_id = new_uuid()
    stock_product(conn, product_id=product_id, branch_id=session.active_branch_id, quantity="10")
    return session, build_sales_pos_presenter(conn, session_context=session), product_id


def _sale_in_checkout(presenter, product_id, *, price="100.00"):
    sale_id = presenter.start_sale().entity_id
    assert presenter.add_line(sale_id=sale_id, product_id=product_id, quantity=Decimal("1"),
                              unit_price=Decimal(price),
                              product_snapshot={"name": "Pollo"}).success
    assert presenter.begin_checkout(sale_id=sale_id).success
    return sale_id


# ── V01 — dos pagos a crédito de una venta: una deuda por la suma ───────────
def test_v01_two_credit_payments_of_one_sale_owe_their_sum(conn):
    customer, sale_id = new_uuid(), new_uuid()
    client = SalesCreditClient(conn, actor_user_id=new_uuid())
    for payment, amount in (("pago-1", "30.00"), ("pago-2", "20.00")):
        client.register(customer_id=customer, sale_id=sale_id, folio="F-1",
                        amount=Decimal(amount), branch_id=new_uuid(), payment_id=payment)
    client.register(customer_id=customer, sale_id=sale_id, folio="F-1",
                    amount=Decimal("20.00"), branch_id=new_uuid(), payment_id="pago-2")
    row = conn.execute("SELECT original_amount, outstanding_amount FROM receivables").fetchall()
    assert len(row) == 1
    assert Decimal(row[0]["original_amount"]) == Decimal("50.00")


# ── V02 — cancelar con pagos: compensar y avisar ────────────────────────────
def test_v02_the_domain_never_cancels_with_live_payments(conn):
    session, presenter, product = _pos(conn)
    sale_id = _sale_in_checkout(presenter, product)
    presenter.record_payment(sale_id=sale_id, method="CASH", amount=Decimal("30.00"))
    sale = SaleRepository(conn).get(sale_id)
    with pytest.raises(SaleCancellationNotAllowedError):
        sale.cancel("salida del cliente")


def test_v02_cancel_voids_each_payment_and_tells_what_to_return(conn):
    session, presenter, product = _pos(conn)
    sale_id = _sale_in_checkout(presenter, product)
    assert presenter.record_payment(sale_id=sale_id, method="CASH",
                                    amount=Decimal("30.00")).success
    assert presenter.record_payment(sale_id=sale_id, method="CARD", amount=Decimal("20.00"),
                                    reference="AUT-77").success

    result = presenter.cancel_sale(sale_id=sale_id, reason="salida del cliente")

    assert result.success, result.message
    texts = [r["text"] for r in result.data["refunds"]]
    assert "Devuelve $30.00 en efectivo al cliente" in texts
    assert any("tarjeta por $20.00" in t and "AUT-77" in t for t in texts)
    sale = SaleRepository(conn).get(sale_id)
    assert sale.status is SaleStatus.CANCELLED
    assert sale.payments == [] and sale.total_paid == Decimal("0")
    assert {v.method for v in sale.voided_payments} == {PaymentMethod.CASH, PaymentMethod.CARD}
    assert conn.execute("SELECT COUNT(*) FROM sale_payment_voids").fetchone()[0] == 2


def test_v02_cancel_removes_the_credit_charge_from_receivables(conn, monkeypatch):
    monkeypatch.setattr(SalesCreditClient, "validate", lambda self, **kw: (True, ""))
    session, presenter, product = _pos(conn)
    sale_id = _sale_in_checkout(presenter, product)
    repo = SaleRepository(conn)
    sale = repo.get(sale_id)
    sale.customer_id = new_uuid()
    repo.save(sale)
    conn.commit()
    assert presenter.record_payment(sale_id=sale_id, method="CREDIT",
                                    amount=Decimal("40.00")).success
    assert Decimal(conn.execute("SELECT outstanding_amount FROM receivables")
                   .fetchone()[0]) == Decimal("40.00")

    result = presenter.cancel_sale(sale_id=sale_id, reason="cliente se arrepintió")

    assert result.success, result.message
    cxc = conn.execute("SELECT status, outstanding_amount FROM receivables").fetchone()
    assert cxc["status"] == "CANCELLED" and Decimal(cxc["outstanding_amount"]) == 0
    assert result.data["refunds"][0]["action"] == "SYSTEM"


def test_v02_voiding_one_of_two_credit_charges_keeps_the_other(conn):
    customer, sale_id = new_uuid(), new_uuid()
    for payment, amount in (("p1", "30.00"), ("p2", "20.00")):
        RegisterSaleCreditChargeUseCase().execute(
            conn, customer_id=customer, sale_id=sale_id, payment_id=payment, folio="F",
            amount=amount, issue_date=__import__("datetime").date.today())
    VoidSaleCreditChargeUseCase().execute(conn, sale_id=sale_id, payment_id="p2")
    VoidSaleCreditChargeUseCase().execute(conn, sale_id=sale_id, payment_id="p2")  # reintento
    cxc = conn.execute("SELECT status, original_amount, outstanding_amount FROM receivables"
                       ).fetchone()
    assert Decimal(cxc["original_amount"]) == Decimal("30.00")
    assert Decimal(cxc["outstanding_amount"]) == Decimal("30.00")
    doc = conn.execute("SELECT total_amount FROM financial_documents").fetchone()
    assert Decimal(doc[0]) == Decimal("30.00")


# ── V03 — retomar el cobro, quitar un pago, volver al carrito ───────────────
def test_v03_a_second_checkout_resumes_with_its_payments(conn):
    session, presenter, product = _pos(conn)
    sale_id = _sale_in_checkout(presenter, product)
    presenter.record_payment(sale_id=sale_id, method="CASH", amount=Decimal("30.00"))

    again = presenter.begin_checkout(sale_id=sale_id)

    assert again.success and again.data.get("resumed") is True
    assert again.data["sale"].total_paid == Decimal("30.00")
    assert presenter.record_payment(sale_id=sale_id, method="CASH",
                                    amount=Decimal("70.00")).success
    assert presenter.checkout_sale(sale_id=sale_id).success


def test_v03_a_recorded_payment_can_be_voided_and_replaced(conn):
    session, presenter, product = _pos(conn)
    sale_id = _sale_in_checkout(presenter, product)
    paid = presenter.record_payment(sale_id=sale_id, method="CASH", amount=Decimal("100.00"))
    payment_id = paid.data["sale"].payments[0].id

    voided = presenter.void_payment(sale_id=sale_id, payment_id=payment_id,
                                    reason="era con tarjeta")

    assert voided.success, voided.message
    assert voided.data["refund"]["text"] == "Devuelve $100.00 en efectivo al cliente"
    assert presenter.get_sale(sale_id).total_paid == Decimal("0")
    assert presenter.record_payment(sale_id=sale_id, method="CARD",
                                    amount=Decimal("100.00")).success
    assert presenter.checkout_sale(sale_id=sale_id).success


def test_v03_closing_the_charge_without_payments_returns_to_the_cart(conn):
    session, presenter, product = _pos(conn)
    sale_id = _sale_in_checkout(presenter, product)
    assert presenter.return_to_cart(sale_id=sale_id).success
    sale = presenter.get_sale(sale_id)
    assert sale.status == "ACTIVE"
    line_id = sale.lines[0].id
    assert presenter.update_line_quantity(sale_id=sale_id, line_id=line_id,
                                          quantity=Decimal("2")).success


def test_v03_with_payments_the_sale_does_not_go_back_to_the_cart(conn):
    session, presenter, product = _pos(conn)
    sale_id = _sale_in_checkout(presenter, product)
    presenter.record_payment(sale_id=sale_id, method="CASH", amount=Decimal("30.00"))
    result = presenter.return_to_cart(sale_id=sale_id)
    assert not result.success
    assert presenter.get_sale(sale_id).status == "CHECKOUT_PENDING"


# ── V04 — mismo precio por clic, escáner, cantidad y cliente ────────────────
def _scannable(conn, *, branch_id, base="45.00", branch_price="40.00"):
    product_id = new_uuid()
    list_id = new_uuid()
    conn.execute("INSERT INTO price_list (id, code, name, kind, status, discount_pct)"
                 " VALUES (?, 'BASE', 'Lista base', 'BASE', 'ACTIVE', '0')", (list_id,))
    conn.execute("INSERT INTO products (id, code, name, product_type, base_unit_id,"
                 " lifecycle_status) VALUES (?,?,?,?,?,?)",
                 (product_id, "SKU-1", "Bistec", "SIMPLE", "PZA", "ACTIVE"))
    for branch, price in (("", base), (branch_id, branch_price)):
        conn.execute("INSERT INTO product_price (id, price_list_id, product_id, sale_price,"
                     " branch_id) VALUES (?,?,?,?,?)",
                     (new_uuid(), list_id, product_id, price, branch))
    conn.execute("INSERT INTO product_barcodes (id, product_id, barcode_value, barcode_type,"
                 " is_primary) VALUES (?,?,?,'EAN13',1)", (new_uuid(), product_id, "750111"))
    conn.commit()
    return product_id


def test_v04_scanner_and_click_charge_the_same_branch_price(conn):
    session = _Session()
    open_cash_shift(conn, branch_id=session.active_branch_id, cashier_user_id=session.user_id)
    product_id = _scannable(conn, branch_id=session.active_branch_id)
    presenter = build_sales_pos_presenter(conn, session_context=session)

    clicked = presenter.start_sale().entity_id
    entry = SalesCatalogQueryService(conn).find_by_code(
        branch_id=session.active_branch_id, code="750111")
    assert presenter.add_product(sale_id=clicked, product=entry).success
    scanned = presenter.start_sale().entity_id
    assert presenter.scan_code(sale_id=scanned, code="750111", context="AUTO").success

    assert presenter.get_sale(clicked).lines[0].unit_price == Decimal("40.00")
    assert presenter.get_sale(scanned).lines[0].unit_price == Decimal("40.00")
    assert presenter.get_sale(scanned).lines[0].product_snapshot["price_source"] == "PRICING"


def test_v04_the_scanner_charges_the_customer_price_like_a_click(conn):
    """Antes el escáner agregaba con el precio de la tarjeta del catálogo, que
    no conoce al cliente: un cliente con precio especial pagaba distinto según
    escaneara o tocara el producto."""
    from backend.application.sales.use_cases.scan_use_cases import ScanCodeRouter
    from backend.domain.sales.enums import ScanContext
    auth, cashier, vip, branch = (SalesAuthorizationPolicy.permissive_for_tests(),
                                  new_uuid(), new_uuid(), new_uuid())
    _scannable(conn, branch_id=branch)
    sale_id = StartSaleUseCase(auth).execute(
        conn, branch_id=branch, cashier_user_id=cashier, operation_id=new_uuid(),
        actor_user_id=cashier).entity_id
    repo = SaleRepository(conn)
    sale = repo.get(sale_id)
    sale.customer_id = vip
    repo.save(sale)
    conn.commit()

    result = ScanCodeRouter(auth, pricing=_TieredPricing(vip)).route(
        conn, sale_id=sale_id, code="750111", context=ScanContext.PRODUCT, branch_id=branch,
        actor_user_id=cashier, operation_id=new_uuid())

    assert result.success, result.message
    assert repo.get(sale_id).lines[0].unit_price == Decimal("8.00")


class _TieredPricing:
    """10 o más: 9.00; cliente VIP: 8.00; si no, 10.00."""

    def __init__(self, vip):
        self.vip = vip

    def effective_price(self, product_id, *, branch_id, customer_id, quantity):
        if customer_id == self.vip:
            return Decimal("8.00")
        return Decimal("9.00") if Decimal(str(quantity)) >= 10 else Decimal("10.00")


def test_v04_quantity_and_customer_changes_reprice_the_line(conn, monkeypatch):
    from backend.infrastructure.integrations import sales_customer_client
    monkeypatch.setattr(sales_customer_client.SalesCustomerClient, "exists",
                        lambda self, customer_id: True)
    auth, cashier, vip = SalesAuthorizationPolicy.permissive_for_tests(), new_uuid(), new_uuid()
    pricing = _TieredPricing(vip)
    sale_id = StartSaleUseCase(auth).execute(
        conn, branch_id=new_uuid(), cashier_user_id=cashier, operation_id=new_uuid(),
        actor_user_id=cashier).entity_id
    added = AddSaleLineUseCase(auth, pricing=pricing).execute(
        conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
        unit_price=Decimal("99"), actor_user_id=cashier, operation_id=new_uuid())
    line_id = added.data["line_id"]
    assert SaleRepository(conn).get(sale_id).lines[0].unit_price == Decimal("10.00")

    UpdateSaleLineQuantityUseCase(auth, pricing=pricing).execute(
        conn, sale_id=sale_id, line_id=line_id, quantity=Decimal("12"),
        actor_user_id=cashier, operation_id=new_uuid())
    assert SaleRepository(conn).get(sale_id).lines[0].unit_price == Decimal("9.00")

    AssignCustomerToSaleUseCase(auth, pricing=pricing).execute(
        conn, sale_id=sale_id, customer_id=vip, actor_user_id=cashier, operation_id=new_uuid())
    assert SaleRepository(conn).get(sale_id).lines[0].unit_price == Decimal("8.00")


# ── V05 — alcance por sucursal sobre el recurso ─────────────────────────────
def test_v05_another_branch_cannot_read_or_operate_the_sale(conn):
    session_a, presenter_a, product = _pos(conn)
    sale_id = _sale_in_checkout(presenter_a, product)
    presenter_a.record_payment(sale_id=sale_id, method="CASH", amount=Decimal("100.00"))
    assert presenter_a.checkout_sale(sale_id=sale_id).success

    presenter_b = build_sales_pos_presenter(conn, session_context=_Session())

    assert presenter_b.get_sale(sale_id) is None
    for result in (
        presenter_b.cancel_sale(sale_id=sale_id, reason="x"),
        presenter_b.reprint_receipt(sale_id=sale_id, reason="copia"),
        presenter_b.request_invoice(sale_id=sale_id, tax_identifier="XAXX010101000",
                                    legal_name="Público", cfdi_use="S01"),
    ):
        assert not result.success
        assert result.error_code == "OUT_OF_BRANCH_SCOPE", result.message
    assert presenter_a.get_sale(sale_id).status == "COMPLETED"


# ── V06 — Caja todo o nada ──────────────────────────────────────────────────
def test_v06_a_caja_failure_leaves_the_sale_uncompleted_and_the_stock_in_place(conn,
                                                                               monkeypatch):
    session, presenter, product = _pos(conn)
    sale_id = _sale_in_checkout(presenter, product)
    presenter.record_payment(sale_id=sale_id, method="CASH", amount=Decimal("100.00"))

    def boom(self, *args, **kwargs):
        raise RuntimeError("cajón fuera de servicio")
    monkeypatch.setattr(cash_client.SalesCashEffectsClient, "record_completed_sale", boom)
    result = presenter.checkout_sale(sale_id=sale_id)

    assert not result.success and result.error_code == "CASH_EFFECTS_FAILED"
    assert "cajón fuera de servicio" in result.message
    sale = presenter.get_sale(sale_id)
    assert sale.status == "CHECKOUT_PENDING" and not sale.sale_number
    available = InventoryAvailabilityQueryService(conn).get_availability(
        product_id=product, branch_id=session.active_branch_id).available
    assert available == Decimal("10")

    monkeypatch.undo()
    assert presenter.checkout_sale(sale_id=sale_id).success     # corregido, se cobra


def test_v06_a_voucher_plus_cash_sale_reaches_the_drawer(conn):
    """Caja exigía la referencia del vale y Ventas no la mandaba: el cobro
    entero se rechazaba y el error se tragaba después del commit."""
    branch, cashier, sale_id = new_uuid(), new_uuid(), new_uuid()
    open_cash_shift(conn, branch_id=branch, cashier_user_id=cashier)
    payments = [
        SalePayment.create(sale_id=sale_id, method=PaymentMethod.VOUCHER,
                           amount=Decimal("50.00"), captured_by_user_id=cashier,
                           reference=f"REFUND_VOUCHER:{new_uuid()}"),
        SalePayment.create(sale_id=sale_id, method=PaymentMethod.CASH,
                           amount=Decimal("60.00"), captured_by_user_id=cashier),
    ]
    SalesCashEffectsClient().record_completed_sale(
        conn, sale_id=sale_id, branch_id=branch, cashier_user_id=cashier,
        operation_id=new_uuid(), payments=payments, change=Decimal("10.00"))
    entry = conn.execute("SELECT amount FROM cash_ledger_entries WHERE reference_id=?",
                         (sale_id,)).fetchone()
    assert Decimal(entry[0]) == Decimal("50.00")


# ── V08 — existencia decimal exacta en el catálogo ──────────────────────────
def test_v08_fractional_stock_is_summed_exactly(conn):
    branch = new_uuid()
    product_id = _scannable(conn, branch_id=branch)
    stock_product(conn, product_id=product_id, branch_id=branch, quantity="0.1",
                  warehouse_id=new_uuid())
    stock_product(conn, product_id=product_id, branch_id=branch, quantity="0.2",
                  warehouse_id=new_uuid())
    entry = SalesCatalogQueryService(conn).find_by_code(branch_id=branch, code="750111")
    assert entry.available_quantity == Decimal("0.3")


# ── 2026-10-16: pendientes cerrados ─────────────────────────────────────────
def test_v03_opening_the_pos_recovers_the_sale_left_in_checkout(conn):
    """En la base real había 10 carritos con productos y 58 borradores
    abandonados: cada apertura del POS creaba una venta nueva."""
    session, presenter, product = _pos(conn)
    sale_id = _sale_in_checkout(presenter, product)
    presenter.record_payment(sale_id=sale_id, method="CASH", amount=Decimal("30.00"))

    reopened = build_sales_pos_presenter(conn, session_context=session).open_sale(recover=True)

    assert reopened.success and reopened.entity_id == sale_id
    assert reopened.data["recovered"] is True and reopened.data["status"] == "CHECKOUT_PENDING"


def test_v03_a_new_sale_reuses_the_empty_draft_and_does_not_load_old_carts(conn):
    session, presenter, product = _pos(conn)
    old = presenter.start_sale().entity_id
    presenter.add_line(sale_id=old, product_id=product, quantity=Decimal("1"),
                       unit_price=Decimal("10"), product_snapshot={"name": "Pollo"})
    draft = presenter.start_sale().entity_id

    first = presenter.open_sale()
    second = presenter.open_sale()

    assert first.entity_id == second.entity_id == draft      # ni otra nueva, ni el carrito viejo
    assert presenter.open_sale(recover=True).entity_id == old
    drafts = conn.execute("SELECT COUNT(*) FROM sales WHERE status='DRAFT'").fetchone()[0]
    assert drafts == 1


def test_v08_the_catalog_comes_in_pages(conn):
    session = _Session()
    list_id = new_uuid()
    conn.execute("INSERT INTO price_list (id, code, name, kind, status, discount_pct)"
                 " VALUES (?, 'BASE', 'Lista base', 'BASE', 'ACTIVE', '0')", (list_id,))
    for i in range(65):
        pid = new_uuid()
        conn.execute("INSERT INTO products (id, code, name, product_type, base_unit_id,"
                     " lifecycle_status) VALUES (?,?,?,?,?,?)",
                     (pid, f"SKU-{i:03d}", f"Producto {i:03d}", "SIMPLE", "PZA", "ACTIVE"))
        conn.execute("INSERT INTO product_price (id, price_list_id, product_id, sale_price,"
                     " branch_id) VALUES (?,?,?,?,'')", (new_uuid(), list_id, pid, "10"))
    conn.commit()
    presenter = build_sales_pos_presenter(conn, session_context=session)

    first, more = presenter.catalog_page(page=0)
    second, more_after = presenter.catalog_page(page=1)

    assert len(first) == 60 and more is True
    assert len(second) == 5 and more_after is False
    assert {p.product_id for p in first}.isdisjoint({p.product_id for p in second})


def test_v04_the_weight_dialog_previews_the_price_that_will_be_charged(conn):
    session = _Session()
    open_cash_shift(conn, branch_id=session.active_branch_id, cashier_user_id=session.user_id)
    product_id = _scannable(conn, branch_id=session.active_branch_id, base="45.00",
                            branch_price="40.00")
    presenter = build_sales_pos_presenter(conn, session_context=session)
    sale_id = presenter.start_sale().entity_id
    assert presenter.price_preview(sale_id=sale_id, product_id=product_id,
                                   quantity=Decimal("1")) == Decimal("40.00")
    assert build_sales_pos_presenter(conn, session_context=_Session()).price_preview(
        sale_id=sale_id, product_id=product_id, quantity=Decimal("1")) is None


def _completed(presenter, product_id):
    sale_id = _sale_in_checkout(presenter, product_id)
    presenter.record_payment(sale_id=sale_id, method="CASH", amount=Decimal("100.00"))
    assert presenter.checkout_sale(sale_id=sale_id).success
    return sale_id


def test_v09_invoice_status_is_recorded_and_visible(conn):
    session, presenter, product = _pos(conn)
    sale_id = _completed(presenter, product)
    assert presenter.request_invoice(sale_id=sale_id, tax_identifier="XAXX010101000",
                                     legal_name="Público", cfdi_use="S01").success
    request_id = presenter.get_sale(sale_id).invoice_requests[0].id

    bad = presenter.mark_invoice_issued(sale_id=sale_id, invoice_request_id=request_id,
                                        uuid_fiscal="no-es-uuid")
    assert not bad.success and "formato del SAT" in bad.message
    ok = presenter.mark_invoice_issued(
        sale_id=sale_id, invoice_request_id=request_id,
        uuid_fiscal="6f9619ff-8b86-d011-b42d-00c04fc964ff")
    assert ok.success, ok.message
    issued = presenter.get_sale(sale_id).invoice_requests[0]
    assert issued.status == "ISSUED"
    assert issued.uuid_fiscal == "6F9619FF-8B86-D011-B42D-00C04FC964FF"


def test_v09_after_an_error_a_new_invoice_can_be_requested(conn):
    session, presenter, product = _pos(conn)
    sale_id = _completed(presenter, product)
    presenter.request_invoice(sale_id=sale_id, tax_identifier="XAXX010101000",
                              legal_name="Público", cfdi_use="S01")
    request_id = presenter.get_sale(sale_id).invoice_requests[0].id
    assert not presenter.mark_invoice_error(sale_id=sale_id, invoice_request_id=request_id,
                                            error_message="  ").success
    assert presenter.mark_invoice_error(sale_id=sale_id, invoice_request_id=request_id,
                                        error_message="CFDI40147: RFC no registrado").success
    assert presenter.request_invoice(sale_id=sale_id, tax_identifier="XAXX010101000",
                                     legal_name="Público", cfdi_use="S01").success
    statuses = [r.status for r in presenter.get_sale(sale_id).invoice_requests]
    assert sorted(statuses) == ["ERROR", "REQUESTED"]


@pytest.fixture(scope="module")
def qt_app():
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_v09_the_status_dialog_shows_each_request(conn, qt_app):
    from frontend.desktop.modules.sales_pos.dialogs.invoice_status_dialog import (
        InvoiceStatusDialog,
    )
    session, presenter, product = _pos(conn)
    sale_id = _completed(presenter, product)
    presenter.request_invoice(sale_id=sale_id, tax_identifier="XAXX010101000",
                              legal_name="Público", cfdi_use="S01")
    dialog = InvoiceStatusDialog(presenter, sale=presenter.get_sale(sale_id), folio="V-1")
    assert dialog._list.count() == 1
    assert dialog._list.item(0).text().startswith("Solicitada")
    assert dialog._btn_issued.isEnabled() and not dialog._btn_new.isEnabled()
