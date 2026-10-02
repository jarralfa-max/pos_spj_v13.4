"""Compra rápida — FASE 2 (2026-09-25): destino elegido por el usuario, idempotencia
estable, confirmación con fuente de pago, fuente persistida, costo > 0 y errores
visibles.

CAUSA RAÍZ que estas pruebas fijan: la pantalla de captura NO tenía sucursal ni
almacén y dependía de `session.active_warehouse_id`, que el adaptador REAL de
sesión fija en "" — así que TODO guardado devolvía SESSION_CONTEXT_REQUIRED. Las
pruebas anteriores siempre pasaban ids explícitos y una sesión con
`active_warehouse_id="wh-1"`, de modo que la ruta real nunca se ejercitaba.

Aquí la sesión imita el adaptador real (`active_warehouse_id=""`) y se maneja la
página de verdad (Qt offscreen, QTest). El QApplication vive en un fixture de
módulo (crearlo dentro de una prueba mata pytest en silencio).
"""

import os
import sqlite3
from decimal import Decimal
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication, QLabel  # noqa: E402

from backend.application.procurement.permissions import ALL_PURCHASE_PERMISSIONS  # noqa: E402
from backend.infrastructure.db.repositories.procurement.direct_purchase_repository import (  # noqa: E402
    DirectPurchaseRepository,
)
from backend.infrastructure.db.schema.document_output_schema import (  # noqa: E402
    create_document_numbering_schema,
)
from backend.infrastructure.db.schema.procurement_schema import (  # noqa: E402
    create_procurement_schema,
)
from frontend.desktop.modules.purchasing.dialogs import direct_purchase_dialogs as dialogs  # noqa: E402
from frontend.desktop.modules.purchasing.direct_purchase_routes import (  # noqa: E402
    build_direct_purchase_presenter,
)
from frontend.desktop.modules.purchasing.direct_purchase_view_models import (  # noqa: E402
    CartLineVM, error_text,
)
from frontend.desktop.modules.purchasing.pages.direct_purchase_create_page import (  # noqa: E402
    DirectPurchaseCreatePage,
)
from frontend.desktop.modules.purchasing.pages.direct_purchase_history_page import (  # noqa: E402
    DirectPurchaseHistoryPage,
)
from tests.integration._supplier_cutover import apply_supplier_cutover  # noqa: E402
from tests.integration.procurement._purchase_context import seed_purchase_context  # noqa: E402


class RealShapedSession:
    """Lo que devuelve el adaptador REAL (`legacy_session_adapter.py`): sucursal
    activa sí, almacén activo SIEMPRE vacío."""

    is_active = True
    user_id = "user-1"
    active_branch_id = "br-1"
    active_warehouse_id = ""

    def tiene_permiso(self, code):
        return code in ALL_PURCHASE_PERMISSIONS


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    create_procurement_schema(c)
    create_document_numbering_schema(c)
    c.execute("CREATE TABLE proveedores(id TEXT PRIMARY KEY, nombre TEXT, activo INTEGER)")
    c.execute("INSERT INTO proveedores VALUES ('sup-1','Proveedor Uno',1)")
    apply_supplier_cutover(c)
    seed_purchase_context(c)   # producto p1/p2 activos, almacén wh-1 de br-1, Finanzas
    c.execute("CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER)")
    for branch_id, name in (("br-1", "Sucursal Uno"), ("br-2", "Sucursal Dos"),
                            ("br-3", "Sucursal Sin Almacen")):
        c.execute("INSERT INTO sucursales VALUES (?,?,1)", (branch_id, name))
    c.execute("CREATE TABLE usuarios_sucursales (usuario_id TEXT, sucursal_id TEXT)")
    for branch_id in ("br-1", "br-2", "br-3"):
        c.execute("INSERT INTO usuarios_sucursales VALUES ('user-1', ?)", (branch_id,))
    c.execute("INSERT INTO warehouses (id, code, name, branch_id)"
              " VALUES ('wh-2','AL2','Almacen Dos','br-2')")
    c.execute("INSERT INTO warehouses (id, code, name, branch_id)"
              " VALUES ('wh-1b','ALB','Almacen Uno B','br-1')")
    c.commit()
    yield c
    c.close()


@pytest.fixture
def presenter(conn):
    return build_direct_purchase_presenter(conn, RealShapedSession())


@pytest.fixture
def page(app, presenter):
    widget = DirectPurchaseCreatePage(presenter)
    widget.resize(1366, 768)
    widget.show()
    app.processEvents()
    yield widget
    widget.close()


def _rows(conn, sql="SELECT COUNT(*) FROM direct_purchases"):
    return conn.execute(sql).fetchone()[0]


def _line():
    return CartLineVM("p1", "Pollo", Decimal("3"), Decimal("100"))


def _fill(page, *, condition="IMMEDIATE_PAYMENT"):
    page._supplier_selected("sup-1")
    page._payment.set_current_id(condition)
    page._cart = [_line()]
    page._render()


def _click(button):
    QTest.mouseClick(button, Qt.LeftButton)


def _create(presenter, *, branch="br-1", warehouse="wh-1",
            condition="IMMEDIATE_PAYMENT", operation_id=None):
    return presenter.create(
        supplier_id="sup-1", lines=[_line()], mode="DIRECT_WITH_IMMEDIATE_RECEIPT",
        payment_condition=condition, branch_id=branch, warehouse_id=warehouse,
        operation_id=operation_id)


# ── A. sucursal y almacén pertenecen al documento ────────────────────────────

def test_real_session_shape_has_no_warehouse(presenter):
    """La premisa: con la sesión real no hay almacén activo."""
    with pytest.raises(PermissionError):
        presenter.default_warehouse()


def test_presenter_saves_with_selected_destination_without_session_warehouse(conn, presenter):
    ok, msg, data = _create(presenter)
    assert ok, msg
    row = conn.execute("SELECT branch_id, warehouse_id FROM direct_purchases WHERE id=?",
                       (data["entity_id"],)).fetchone()
    assert row == ("br-1", "wh-1")


def test_page_opens_preselecting_session_branch_and_single_warehouse(page):
    assert page._branch.current_id() == "br-1"
    # br-1 tiene DOS almacenes de compra (wh-1 y wh-1b) y la sesión no trae
    # almacén: no se adivina uno.
    assert not page._warehouse.has_selection()
    assert {page._warehouse.itemData(i) for i in range(1, page._warehouse.count())} == {
        "wh-1", "wh-1b"}


def test_page_saves_for_real_with_empty_session_warehouse(conn, page):
    """EL BUG: `_save_draft` nunca mandaba destino y la sesión real no tiene
    almacén, así que cada guardado terminaba en SESSION_CONTEXT_REQUIRED."""
    _fill(page)
    assert page._warehouse.set_current_id("wh-1")
    _click(page._save)
    assert _rows(conn) == 1
    row = conn.execute("SELECT branch_id, warehouse_id, status FROM direct_purchases").fetchone()
    assert row[:2] == ("br-1", "wh-1")
    assert "SESSION_CONTEXT" not in page._notice.text()
    # "No pasa nada" (2026-09-25): el guardado SÍ ocurría pero el aviso era una
    # línea pequeña y la captura seguía igual. Ahora: aviso de éxito destacado con
    # folio, folio en el resumen y captura bloqueada.
    assert page._notice.property("state") == "success"
    assert page._notice.property("role") == "banner"
    assert "CD-2026-000001" in page._notice.text()
    assert "CD-2026-000001" in page.summary._values["document"].text()
    assert not page._add.isEnabled() and not page._save.isEnabled()
    assert page._cancel.text() == "Nueva compra"


def test_saving_without_destination_shows_inline_message_and_skips_use_case(conn, page):
    _fill(page)
    assert not page._warehouse.has_selection()
    _click(page._save)
    assert _rows(conn) == 0
    assert page._notice.isVisibleTo(page)
    assert "Selecciona sucursal y almacén destino" in page._notice.text()
    assert page._notice.property("state") == "error"


def test_summary_panel_shows_names_never_ids(page):
    _fill(page)
    page._warehouse.set_current_id("wh-1")
    destination = page.summary._values["destination"].text()
    assert "Sucursal Uno" in destination and "Almac" in destination
    assert "br-1" not in destination and "wh-1" not in destination


def test_changing_branch_reloads_warehouses_and_clears_incompatible_selection(page):
    page._warehouse.set_current_id("wh-1b")
    assert page._warehouse.current_id() == "wh-1b"
    page._branch.set_current_id("br-2")
    offered = {page._warehouse.itemData(i) for i in range(1, page._warehouse.count())}
    assert offered == {"wh-2"}                       # jamás el de otra sucursal
    assert page._warehouse.findData("wh-1b") < 0 and page._warehouse.findData("wh-1") < 0
    assert page._warehouse.current_id() == "wh-2"    # único válido: preseleccionado
    page._branch.set_current_id("br-3")              # sucursal sin almacén de compras
    assert page._warehouse.count() == 1 and not page._warehouse.has_selection()
    page._branch.set_current_id("br-1")
    assert page._warehouse.findData("wh-2") < 0


def test_session_warehouse_of_another_branch_is_never_preselected(conn):
    class Session(RealShapedSession):
        active_warehouse_id = "wh-2"      # de br-2, la sesión está en br-1

    presenter = build_direct_purchase_presenter(conn, Session())
    branches = presenter.branch_options()
    branch, warehouse = presenter.preselected_destination(branches)
    assert branch == "br-1" and warehouse == ""


def test_session_warehouse_of_the_branch_is_preselected(conn):
    class Session(RealShapedSession):
        active_warehouse_id = "wh-1b"

    presenter = build_direct_purchase_presenter(conn, Session())
    assert presenter.preselected_destination(presenter.branch_options()) == ("br-1", "wh-1b")


def test_session_branch_outside_the_allowed_scope_is_not_preselected(conn):
    conn.execute("DELETE FROM usuarios_sucursales WHERE sucursal_id='br-1'")
    conn.commit()
    presenter = build_direct_purchase_presenter(conn, RealShapedSession())
    assert presenter.preselected_destination(presenter.branch_options()) == ("", "")


def test_warehouse_options_are_exactly_what_the_backend_accepts(presenter):
    assert {w for w, _ in presenter.warehouse_options("br-1")} == {"wh-1", "wh-1b"}
    assert presenter.warehouse_options("") == []
    assert presenter.warehouse_options("br-3") == []


def test_backend_still_rejects_a_warehouse_of_another_branch(conn, presenter):
    ok, msg, data = _create(presenter, branch="br-1", warehouse="wh-2")
    assert not ok and data["error_code"] == "WAREHOUSE_NOT_IN_BRANCH"
    assert _rows(conn) == 0
    # y la pantalla lo traduce sin mostrar el código técnico
    shown = error_text(msg, data)
    assert "WAREHOUSE_NOT_IN_BRANCH" not in shown and "almacén" in shown.lower()


# ── B. idempotencia estable ──────────────────────────────────────────────────

def test_double_click_and_retry_yield_one_draft(conn, page):
    _fill(page)
    page._warehouse.set_current_id("wh-1")
    first_operation = page._operation_id
    _click(page._save)
    _click(page._save)          # doble clic
    page._save_draft()          # reintento
    assert _rows(conn) == 1
    assert page._operation_id == first_operation
    assert "ya está guardada como cd-2026-000001" in page._notice.text().lower()
    # y el reintento a nivel presentador (misma operación) devuelve el mismo documento
    ok, _msg, data = page._presenter.create(
        supplier_id="sup-1", lines=[_line()], mode="DIRECT_WITH_IMMEDIATE_RECEIPT",
        payment_condition="IMMEDIATE_PAYMENT", branch_id="br-1", warehouse_id="wh-1",
        operation_id=first_operation)
    assert ok and data.get("already_registered") is True


def test_same_operation_id_returns_the_existing_document(conn, presenter):
    ok1, _m, d1 = _create(presenter, operation_id="op-fixed")
    ok2, _m, d2 = _create(presenter, operation_id="op-fixed")
    assert ok1 and ok2 and d1["entity_id"] == d2["entity_id"]
    assert d2.get("already_registered") is True
    assert _rows(conn) == 1


def test_cancelling_the_capture_starts_a_new_operation(conn, page):
    _fill(page)
    page._warehouse.set_current_id("wh-1")
    _click(page._save)
    before = page._operation_id
    _click(page._cancel)
    assert page._operation_id != before and page._current_id is None


def test_capture_is_locked_after_saving_so_no_orphan_second_draft(conn, page):
    _fill(page)
    page._warehouse.set_current_id("wh-1")
    _click(page._save)
    for widget in (page._supplier, page._branch, page._warehouse, page._payment,
                   page._add, page._edit, page._remove):
        assert not widget.isEnabled()
    page._add_line()            # bloqueado: ni abre el diálogo
    page._save_draft()
    assert _rows(conn) == 1
    assert "Nueva compra" in page._notice.text()
    _click(page._cancel)        # «Nueva compra» desbloquea con operación nueva
    assert page._add.isEnabled() and page._current_id is None
    assert "sigue en Historial" in page._notice.text()


# ── C/D. confirmación con fuente de pago, persistida ─────────────────────────

@pytest.fixture
def history(app, presenter):
    widget = DirectPurchaseHistoryPage(presenter)
    widget.resize(1200, 700)
    widget.show()
    yield widget
    widget.close()


def _patch_dialog(monkeypatch, choose=None):
    """Sustituye `exec_` (bloquearía la prueba): elige una fuente si se pide y
    acepta, y guarda la instancia para inspeccionarla."""
    seen = {}

    def fake_exec(self):
        seen["dialog"] = self
        seen["texts"] = [label.text() for label in self.findChildren(QLabel)]
        if choose:
            self._source.set_current_id(choose)
        self.accept()
        return self.result()

    monkeypatch.setattr(dialogs.ConfirmDirectPurchaseDialog, "exec_", fake_exec)
    return seen


def _status_and_source(conn, dp_id):
    return conn.execute("SELECT status, payment_source, payment_instruction_id"
                        " FROM direct_purchases WHERE id=?", (dp_id,)).fetchone()


def test_history_confirm_immediate_requires_a_payment_source(conn, presenter, history,
                                                             monkeypatch):
    _ok, _m, data = _create(presenter)
    history._current_id = data["entity_id"]
    seen = _patch_dialog(monkeypatch, choose=None)     # el usuario NO elige fuente
    history._confirm_current()
    assert _status_and_source(conn, data["entity_id"])[0] == "DRAFT"
    assert "fuente de pago" in seen["dialog"].error_text().lower()


def test_history_confirm_immediate_with_source_persists_it(conn, presenter, history,
                                                           monkeypatch):
    _ok, _m, data = _create(presenter)
    history._current_id = data["entity_id"]
    seen = _patch_dialog(monkeypatch, choose="BANK_TRANSFER")
    history._confirm_current()
    status, source, instruction_id = _status_and_source(conn, data["entity_id"])
    assert status == "RECEIVED"
    assert source == "BANK_TRANSFER" and instruction_id
    # el diálogo resume la compra con NOMBRES
    texts = " | ".join(seen["texts"])
    assert "Proveedor Uno" in texts and "Sucursal Uno" in texts and "Almac" in texts
    assert "sup-1" not in texts and "br-1" not in texts and "wh-1" not in texts
    assert "Pago inmediato" in texts


def test_payment_source_survives_a_later_save_of_the_aggregate(conn, presenter):
    """Rehidratar el agregado sin la instrucción de pago hacía que el reverso
    escribiera NULL sobre `payment_source`."""
    _ok, _m, data = _create(presenter)
    ok, msg, _ = presenter.confirm(data["entity_id"], "BANK_TRANSFER")
    assert ok, msg
    ok, msg, _ = presenter.reverse(data["entity_id"], "devolución")
    assert ok, msg
    assert _status_and_source(conn, data["entity_id"])[:2] == ("REVERSED", "BANK_TRANSFER")


def test_repository_round_trip_keeps_the_payment_instruction(conn, presenter):
    _ok, _m, data = _create(presenter)
    presenter.confirm(data["entity_id"], "BANK_TRANSFER")
    dp = DirectPurchaseRepository(conn).get(data["entity_id"])
    assert dp.payment_instruction is not None
    assert dp.payment_instruction.source.value == "BANK_TRANSFER"
    assert dp.payment_instruction.amount.amount == dp.total().amount


def test_history_confirm_supplier_credit_needs_no_dialog_nor_source(conn, presenter, history,
                                                                    monkeypatch):
    _ok, _m, data = _create(presenter, condition="SUPPLIER_CREDIT")
    history._current_id = data["entity_id"]

    def no_dialog(self):
        raise AssertionError("El crédito de proveedor no debe pedir fuente de pago")

    monkeypatch.setattr(dialogs.ConfirmDirectPurchaseDialog, "exec_", no_dialog)
    history._confirm_current()
    status, source, _ = _status_and_source(conn, data["entity_id"])
    assert status == "RECEIVED" and source is None


def test_create_page_confirm_uses_the_dialog_and_persists_the_source(conn, page, monkeypatch):
    _fill(page)
    page._warehouse.set_current_id("wh-1")
    seen = _patch_dialog(monkeypatch, choose="BANK_TRANSFER")
    _click(page._confirm)
    row = conn.execute("SELECT status, payment_source FROM direct_purchases").fetchone()
    assert row == ("RECEIVED", "BANK_TRANSFER")
    assert seen["dialog"] is not None
    assert page._current_id is None and not page._cart      # lista para la siguiente
    assert "confirmada" in page._notice.text().lower()


def test_create_page_confirm_without_a_source_keeps_the_draft(conn, page, monkeypatch):
    _fill(page)
    page._warehouse.set_current_id("wh-1")
    _patch_dialog(monkeypatch, choose=None)
    _click(page._confirm)
    assert conn.execute("SELECT status, payment_source FROM direct_purchases").fetchone() \
        == ("DRAFT", None)


def test_payment_sources_follow_the_branch_of_the_purchase(presenter):
    assert [k for k, _ in presenter.payment_source_options("br-1")] == [
        "BANK_TRANSFER", "MERCADO_PAGO"]


# ── E. costo > 0 ─────────────────────────────────────────────────────────────

def _dialog_with(app, cost):
    dialog = dialogs.AddCartLineDialog(None, product_provider=lambda _q: [])
    dialog._product.set_selected_label("p1", "Pollo")
    dialog._quantity.set_decimal("2")
    dialog._unit_cost.setText(cost)
    return dialog


@pytest.mark.parametrize("cost", ["0", "0.00", "-5", ""])
def test_add_line_dialog_blocks_zero_or_negative_cost(app, cost):
    dialog = _dialog_with(app, cost)
    assert "mayor a cero" in dialog.validation_message()
    dialog.accept()
    assert dialog.result() == 0 and "mayor a cero" in dialog.error_text()
    assert dialog.line() is None


def test_add_line_dialog_accepts_a_positive_cost(app):
    dialog = _dialog_with(app, "10")
    dialog.accept()
    assert dialog.result() == 1 and dialog.line().unit_cost == Decimal("10.00")


def test_edit_cost_dialog_blocks_zero(app):
    dialog = dialogs.EditLineCostDialog(None, description="Pollo")
    dialog.accept()
    assert dialog.result() == 0 and dialog.unit_cost() is None
    dialog._cost.setText("25")
    dialog.accept()
    assert dialog.result() == 1 and dialog.unit_cost() == Decimal("25.00")


def test_requisition_lines_without_cost_are_flagged_and_block_saving(conn, page):
    detail = SimpleNamespace(
        id="req-1", branch_id="br-1",
        lines=[SimpleNamespace(product_id="p1", quantity="2", estimated_unit_cost=None),
               SimpleNamespace(product_id="p2", quantity="1", estimated_unit_cost="0")])
    page.start_from_requisition(detail)
    assert all(line.cost_missing for line in page._cart)
    assert page._cart[0].description == "Pollo"          # nombre, no el id
    assert page._table.item(0, 2).text() == "Falta costo"
    page._supplier_selected("sup-1")
    page._warehouse.set_current_id("wh-1")
    assert page._save_draft() is False
    assert _rows(conn) == 0
    assert "costo" in page._notice.text().lower() and page._notice.isVisibleTo(page)


# ── F. errores visibles y en español ─────────────────────────────────────────

@pytest.mark.parametrize("code", ["SESSION_CONTEXT_REQUIRED", "WAREHOUSE_NOT_IN_BRANCH",
                                  "BRANCH_NOT_ALLOWED", "PAYMENT_NOT_BOOKABLE",
                                  "AUTHORIZATION_REQUIRED"])
def test_known_error_codes_have_spanish_text(code):
    shown = error_text("mensaje técnico PETTY_CASH 0192-uuid", {"error_code": code})
    assert code not in shown and "PETTY_CASH" not in shown and "uuid" not in shown


def test_unknown_code_falls_back_to_the_use_case_message():
    assert error_text("La compra requiere al menos una línea", {"error_code": "EMPTY"}) \
        == "La compra requiere al menos una línea"
    assert error_text("", None) == "No se pudo completar la operación."


def test_notice_is_repolished_and_visible_on_error(page):
    page._show(True, "Algo salió mal")
    assert page._notice.isVisibleTo(page)
    assert page._notice.property("state") == "error"
    page._show(False, "")
    assert not page._notice.isVisibleTo(page)
