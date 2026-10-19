"""La pantalla del POS, de punta a punta, contra una conexión real.

Re-auditoría POS (2026-10-01). Cada prueba fija un hueco que se midió con la
pantalla real sobre una copia de la base del usuario:

* un producto por KG se agregaba como "1", sin pedir el peso;
* el carrito no permitía corregir ni quitar una línea;
* Cancelar no confirmaba ni pedía motivo;
* tras cobrar no se decía el folio ni el cambio, y no se pedía el ticket;
* Reimprimir actuaba sobre la venta NUEVA, vacía;
* Reanudar tomaba siempre la primera suspendida y perdía la venta en curso;
* Devolución/F10 no tenía manejador;
* el cliente asignado no se mostraba.

Presentador, casos de uso y esquema son los reales. Sólo los diálogos modales
se sustituyen (un `exec_()` real bloquearía la prueba); la pantalla los busca
por nombre en `workspace.dialogs` justo para esto.
"""

from __future__ import annotations

import os
import sqlite3
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from backend.application.sales.permissions import SalesPermissions  # noqa: E402
from backend.infrastructure.db.schema.customers_crm_schema import (  # noqa: E402
    create_customers_crm_schema,
)
from backend.infrastructure.db.schema.document_output_schema import (  # noqa: E402
    create_document_numbering_schema,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema  # noqa: E402
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema  # noqa: E402
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402
from backend.infrastructure.db.schema.sales_schema import create_sales_schema  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402
from frontend.desktop.modules.sales_pos.composition import create_sales_pos_view  # noqa: E402
from tests.integration._pos_ready import open_cash_shift, stock_product  # noqa: E402


class _Session:
    def __init__(self):
        self.user_id = new_uuid()
        self.active_branch_id = new_uuid()
        self.is_active = True
        self.nombre_completo = "Jose Cajero"
        self.sucursal_nombre = "Corregidora"
        self._permissions = (
            {v for v in vars(SalesPermissions).values() if isinstance(v, str)}
            | {"INVENTARIO.reserva.crear", "INVENTARIO.reserva.liberar",
               "INVENTARIO.reserva.ver", "CLIENTES.ver", "CLIENTES.buscar",
               "CLIENTES.crear"})

    def tiene_permiso(self, code: str) -> bool:
        return code in self._permissions or code.startswith("CLIENTES")


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    for create in (create_sales_schema, create_products_schema, create_pricing_schema,
                   create_inventory_schema, create_document_numbering_schema,
                   create_customers_crm_schema):
        create(c)
    c.execute("CREATE TABLE branch_profiles (branch_id TEXT PRIMARY KEY, code TEXT, name TEXT,"
              " address TEXT, phone TEXT, ticket_header TEXT, ticket_footer TEXT)")
    c.execute("INSERT INTO price_list (id, code, name, kind, status, discount_pct)"
              " VALUES (?, 'BASE', 'Lista base', 'BASE', 'ACTIVE', '0')", (new_uuid(),))
    c.commit()
    yield c
    c.close()


def _unit(conn, code, dimension):
    unit_id = new_uuid()
    conn.execute("INSERT INTO units_of_measure (id, code, name, dimension, active)"
                 " VALUES (?,?,?,?,1)", (unit_id, code, code, dimension))
    return unit_id


def _product(conn, *, name, code, unit_id, price, branch_id=None, stock="0"):
    product_id = new_uuid()
    conn.execute("INSERT INTO products (id, code, name, product_type, base_unit_id,"
                 " lifecycle_status) VALUES (?,?,?,?,?,?)",
                 (product_id, code, name, "SIMPLE", unit_id, "ACTIVE"))
    if price is not None:
        base = conn.execute("SELECT id FROM price_list WHERE code='BASE'").fetchone()[0]
        conn.execute("INSERT INTO product_price (id, price_list_id, product_id, sale_price,"
                     " branch_id) VALUES (?,?,?,?,'')", (new_uuid(), base, product_id, price))
    conn.commit()
    if branch_id and Decimal(stock) > 0:
        stock_product(conn, product_id=product_id, branch_id=branch_id, quantity=stock)
    return product_id


@pytest.fixture
def pos(app, conn, monkeypatch):
    session = _Session()
    branch = session.active_branch_id
    conn.execute("INSERT INTO branch_profiles (branch_id, code, name) VALUES (?, 'COR', ?)",
                 (branch, "Corregidora"))
    open_cash_shift(conn, branch_id=branch, cashier_user_id=session.user_id)
    kg, pza = _unit(conn, "KG", "WEIGHT"), _unit(conn, "PZA", "COUNT")
    _product(conn, name="Alas", code="ALAS", unit_id=kg, price="80", branch_id=branch, stock="23")
    _product(conn, name="Huacal", code="HUA", unit_id=pza, price="15", branch_id=branch, stock="5")
    _product(conn, name="Cabeza", code="CAB", unit_id=kg, price=None)

    mensajes = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda _p, title, text: mensajes.append(("info", title, text))))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda _p, title, text: mensajes.append(("warn", title, text))))

    workspace = create_sales_pos_view(conn, session)
    workspace.resize(1366, 768)
    workspace.show()
    app.processEvents()
    workspace.mensajes = mensajes
    yield workspace
    workspace.close()


def _producto(workspace, name):
    return next(p for p in workspace._presenter.catalog_search() if p.name == name)


def _stub(**attrs):
    """Fábrica de diálogo falsa: acepta con los valores dados, o rechaza."""
    abiertos = []

    class _Dialog:
        def __init__(self, *args, **kwargs):
            abiertos.append(kwargs)
            for key, value in attrs.items():
                setattr(self, key, value)

        def exec_(self):
            return bool(attrs.get("_accept", True))

        def focus_sale(self, sale_id):
            abiertos[-1]["focused"] = sale_id

        select_sale = focus_sale

    _Dialog.abiertos = abiertos
    return _Dialog


# ── barra del cajero ─────────────────────────────────────────────────────────

def test_the_cashier_bar_names_cashier_branch_and_open_shift(pos):
    assert pos.cashier_bar._cashier.text() == "Jose Cajero"
    assert pos.cashier_bar._branch.text() == "Corregidora"
    assert pos.cashier_bar._shift_badge.text() == "Caja: abierta"


# ── peso (§18-19) ────────────────────────────────────────────────────────────

def test_a_kg_product_asks_for_the_weight_and_keeps_the_unit(pos):
    pos.dialogs["weight"] = _stub(weight=Decimal("1.250"), weight_source="MANUAL")

    pos._on_product_selected(_producto(pos, "Alas"))

    [line] = pos._sale.lines
    assert (line.quantity, line.quantity_unit) == (Decimal("1.250"), "KG")
    assert line.line_total == Decimal("100")
    assert line.weight_source == "MANUAL"


def test_cancelling_the_weight_adds_nothing(pos):
    pos.dialogs["weight"] = _stub(weight=None, _accept=False)

    pos._on_product_selected(_producto(pos, "Alas"))

    assert pos._sale.lines == ()


def test_a_piece_product_is_added_directly_with_its_unit(pos):
    pos._on_product_selected(_producto(pos, "Huacal"))

    [line] = pos._sale.lines
    assert (line.quantity, line.quantity_unit) == (Decimal("1"), "PZA")


def test_a_product_without_price_says_why_instead_of_doing_nothing(pos):
    pos._on_product_selected(_producto(pos, "Cabeza"))

    assert pos._sale.lines == ()
    assert "Precios" in pos.mensajes[-1][2]


# ── carrito (§12) ────────────────────────────────────────────────────────────

def test_scale_capture_is_validated_by_application_and_current_weight_is_not_cart(pos):
    from backend.application.sales.scale_reading_service import ScaleReadingService
    from backend.domain.inventory.value_objects.catch_weight import WeightReading
    from backend.infrastructure.hardware.scale_gateway import StubScaleGateway
    service = ScaleReadingService(StubScaleGateway([WeightReading(Decimal(".850")) for _ in range(2)]))
    service.poll()
    service.poll()
    pos._presenter._live_scale = service
    product = _producto(pos, "Alas")
    good = pos._presenter.add_product(sale_id=pos._sale_id, product=product,
                                     quantity=Decimal(".850"), weight_source="SCALE")
    assert good.success
    bad = pos._presenter.add_product(sale_id=pos._sale_id, product=product,
                                    quantity=Decimal("6.5"), weight_source="SCALE")
    assert not bad.success and bad.error_code == "INVALID_SCALE_READING"
    service.invalidate("STALE", "lectura vencida")
    stale = pos._presenter.add_product(sale_id=pos._sale_id, product=product,
                                      quantity=Decimal(".850"), weight_source="SCALE")
    assert not stale.success
    assert len(pos._presenter.get_sale(pos._sale_id).lines) == 1


def test_quantity_edit_cannot_claim_a_stale_scale_reading(pos):
    pos.dialogs["weight"] = _stub(weight=Decimal("1.250"), weight_source="MANUAL")
    pos._on_product_selected(_producto(pos, "Alas"))
    line = pos._sale.lines[0]
    result = pos._presenter.update_line_quantity(
        sale_id=pos._sale_id, line_id=line.id, quantity=Decimal(".850"), weight_source="SCALE")
    assert not result.success and result.error_code == "INVALID_SCALE_READING"
    assert pos._presenter.get_sale(pos._sale_id).lines[0].quantity == Decimal("1.250")


def test_sale_discount_is_visible_and_removable_from_cart_without_removing_line_discount(pos):
    pos._on_product_selected(_producto(pos, "Huacal"))
    line = pos._sale.lines[0]
    assert pos._presenter.apply_line_discount(sale_id=pos._sale_id, line_id=line.id,
                                             discount_amount=Decimal("1")).success
    assert pos._presenter.apply_sale_discount(sale_id=pos._sale_id,
                                             discount_amount=Decimal("1")).success
    pos._refresh()
    cart = pos.checkout.cart
    table = cart._table
    assert pos._sale.sale_level_discount == Decimal("1")
    assert any("Descuento de venta" in table.item(row, 0).text()
               for row in range(table.rowCount()))
    assert not table.isColumnHidden(4)
    before = pos._sale.total
    cart._tools.aboutToShow.emit()
    assert cart.btn_remove_sale_discount._menu_action.isEnabled()
    cart.btn_remove_sale_discount._menu_action.trigger()
    assert pos._sale.sale_level_discount == 0
    assert pos._sale.lines[0].discount_total == Decimal("1")
    assert pos._sale.total == before + Decimal("1")
    assert not cart.btn_remove_sale_discount.isEnabled()


def test_remove_individual_discount_preserves_other_lines_and_sale_discount(pos):
    pos._on_product_selected(_producto(pos, "Huacal"))
    pos._on_product_selected(_producto(pos, "Huacal"))
    first, second = pos._sale.lines
    presenter = pos._presenter
    assert presenter.apply_line_discount(sale_id=pos._sale_id, line_id=first.id, discount_amount=Decimal("1")).success
    assert presenter.apply_line_discount(sale_id=pos._sale_id, line_id=second.id, discount_amount=Decimal("1")).success
    assert presenter.apply_sale_discount(sale_id=pos._sale_id, discount_amount=Decimal("1")).success
    before = presenter.get_sale(pos._sale_id)
    assert presenter.remove_line_discount(sale_id=pos._sale_id, line_id=first.id).success
    after = presenter.get_sale(pos._sale_id)
    assert after.lines[0].discount_total == 0
    assert after.lines[1].discount_total == 1
    assert after.total == before.total + 1
    assert presenter.remove_line_discount(sale_id=pos._sale_id, line_id=first.id).success
    assert presenter.get_sale(pos._sale_id).total == after.total
    presenter._session._permissions.discard(SalesPermissions.DISCOUNT_APPLY)
    assert not presenter.remove_line_discount(sale_id=pos._sale_id, line_id=second.id).success

def test_a_weighed_line_can_be_corrected_and_removed(pos):
    pos.dialogs["weight"] = _stub(weight=Decimal("1.250"), weight_source="MANUAL")
    pos._on_product_selected(_producto(pos, "Alas"))
    line_id = pos._sale.lines[0].id

    pos.dialogs["weight"] = _stub(weight=Decimal("2.000"), weight_source="MANUAL")
    pos._on_line_quantity_requested(line_id)
    assert pos.dialogs["weight"].abiertos[-1]["current_weight"] == Decimal("1.250")
    assert pos._sale.lines[0].quantity == Decimal("2.000")
    assert pos._sale.lines[0].quantity_unit == "KG"

    pos.checkout.line_remove_requested.emit(line_id)
    assert pos._sale.lines == ()


# ── cancelar (§42) ───────────────────────────────────────────────────────────

def test_cancel_asks_for_a_reason_and_keeps_the_sale_if_declined(pos):
    pos._on_product_selected(_producto(pos, "Huacal"))
    sale_id = pos._sale_id

    pos.dialogs["cancel"] = _stub(reason=None, _accept=False)
    pos._on_cancel_requested()
    assert pos._sale_id == sale_id and len(pos._sale.lines) == 1

    pos.dialogs["cancel"] = _stub(reason="el cliente se arrepintió")
    pos._on_cancel_requested()
    assert pos._sale_id != sale_id
    assert pos._presenter.get_sale(sale_id).status == "CANCELLED"


# ── cobro (§30-38, §46) ──────────────────────────────────────────────────────

def _cobrar(pos, amount):
    from frontend.desktop.modules.sales_pos.dialogs.payment_dialog import PaymentDialog

    class _Pay(PaymentDialog):
        def exec_(self):
            self.select_method("CASH")
            self.set_amount(Decimal(amount))
            self._add_line()
            self._confirm()
            return self.result()

    pos.dialogs["payment"] = _Pay
    pos._on_checkout_requested()


def test_checkout_tells_folio_change_and_ticket_status_then_opens_a_new_sale(pos):
    pos.dialogs["weight"] = _stub(weight=Decimal("1.250"), weight_source="MANUAL")
    pos._on_product_selected(_producto(pos, "Alas"))
    sold = pos._sale_id

    _cobrar(pos, "500")

    _kind, title, text = pos.mensajes[-1]
    assert title == "Venta completada"
    assert "V-COR-000001" in text
    assert "Cambio: $400.00" in text
    assert "ticket NO se imprimió" in text and "Dispositivos" in text
    assert pos._sale_id != sold and pos._sale.lines == ()
    assert pos._presenter.get_sale(sold).status == "COMPLETED"


def test_public_display_only_thanks_after_committed_sale_and_clears_on_next_sale(pos):
    projected = []
    pos._presenter._command_handlers["push_customer_display"] = lambda **kw: projected.append(kw["state"])
    pos._customer_display_gateway = object()
    pos._on_product_selected(_producto(pos, "Huacal"))
    pos._on_public_payment("FAILED")
    assert projected[-1].screen == "PAYMENT_PENDING"
    assert "no se confirmó" in projected[-1].payment_text
    pos._public_payment = None
    pos._refresh()
    assert projected[-1].screen == "CART"
    _cobrar(pos, "50")
    assert projected[-1].screen == "THANK_YOU"
    assert pos._presenter.get_sale(projected[-1].sale_id).status == "COMPLETED"
    assert "Cambio:" in projected[-1].payment_text
    pos._thank_you_timer.stop()
    pos._push_customer_display()
    assert projected[-1].screen == "IDLE"
    assert not projected[-1].lines


def test_reprint_targets_the_sale_just_charged_not_the_new_empty_one(pos):
    pos._on_product_selected(_producto(pos, "Huacal"))
    sold = pos._sale_id
    _cobrar(pos, "15")
    sale = pos._presenter.get_sale(sold)
    pos.dialogs["posted_sale"] = _stub(sale=sale, reason="otra copia")

    pos._on_reprint_requested()

    assert pos.dialogs["posted_sale"].abiertos[-1]["focused"] == sold
    _kind, title, text = pos.mensajes[-1]
    # Sin impresora configurada: el motivo es la impresora, no "nunca completó".
    assert "impresora" in text.lower() and "nunca" not in text


# ── suspender / reanudar (§40) ───────────────────────────────────────────────

def test_resuming_parks_the_current_sale_instead_of_losing_it(pos):
    pos._on_product_selected(_producto(pos, "Huacal"))
    first = pos._sale_id
    pos._on_suspend_requested()
    pos._on_product_selected(_producto(pos, "Huacal"))
    second = pos._sale_id
    pos.dialogs["resume"] = _stub(sale_id=first)

    pos._on_resume_requested()

    assert pos._sale_id == first
    assert pos._presenter.get_sale(second).status == "SUSPENDED"


# ── devolución (§43) ─────────────────────────────────────────────────────────

def test_f10_opens_the_return_dialog_on_the_last_sale(pos):
    pos._on_product_selected(_producto(pos, "Huacal"))
    sold = pos._sale_id
    _cobrar(pos, "15")
    pos.dialogs["return"] = _stub(changed=False)

    [f10] = [s for s in pos._shortcuts if s.key().toString() == "F10"]
    f10.activated.emit()

    assert pos.dialogs["return"].abiertos[-1]["focused"] == sold


# ── descuento rápido (§25) ───────────────────────────────────────────────────

def test_a_quick_ten_percent_discount_is_computed_by_the_domain(pos):
    pos._on_product_selected(_producto(pos, "Huacal"))
    pos._on_product_selected(_producto(pos, "Huacal"))

    pos.checkout.actions.quick_discount_buttons[1].click()

    assert pos._sale.discount_total == Decimal("3.00")
    assert pos._sale.total == Decimal("27.00")


# ── cliente (§21) ────────────────────────────────────────────────────────────

def test_an_assigned_customer_is_shown_and_can_be_cleared(pos):
    created = pos._presenter.quick_create_customer(display_name="Ana Torres")
    assert created.success, created.message

    pos._on_customer_selected(created.entity_id)
    assert pos.checkout.customer._display.text() == "Ana Torres"

    pos._on_customer_cleared()
    assert pos.checkout.customer._display.text() == "Público en general"
