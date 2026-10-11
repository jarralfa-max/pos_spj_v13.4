"""Inventory/POS dialog adoption preserves captures, permissions and checkout order."""
from decimal import Decimal
from types import SimpleNamespace

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QDialog, QLabel, QMessageBox, QPushButton

from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.modules.inventory import dialogs as inventory
from frontend.desktop.modules.sales_pos.dialogs.discount_dialog import DiscountDialog
from frontend.desktop.modules.sales_pos.dialogs.payment_dialog import PaymentDialog
from frontend.desktop.modules.sales_pos.dialogs.quick_customer_dialog import QuickCustomerDialog
from frontend.desktop.themes.theme_manager import ThemeManager


SALE_ID = "019f327a-1694-7000-8000-000000000001"
CUSTOMER_ID = "019f327a-1694-7000-8000-000000000002"
AUTHORIZER_ID = "019f327a-1694-7000-8000-000000000003"


def _result(success=True, **kwargs):
    return SimpleNamespace(success=success, message="Solicitud rechazada", error_code=None,
                           entity_id=CUSTOMER_ID, **kwargs)


class Presenter:
    def __init__(self):
        self.calls = []
        self.result = _result()
        self.authorizer = (AUTHORIZER_ID, "")
        self.checkout_results = [_result()]

    def payment_methods(self, *, has_customer):
        return ["CASH", "CARD", "VOUCHER"]

    def cash_tender(self, *, total, received):
        return SimpleNamespace(change=max(Decimal("0"), received - total))

    def payment_amount_problem(self, **kwargs):
        return None

    def voucher_balance(self, reference):
        return {"found": True, "balance": "40"}

    def begin_checkout(self, **kwargs):
        self.calls.append(("begin", kwargs))
        return _result()

    def record_payment(self, **kwargs):
        self.calls.append(("payment", kwargs))
        return _result()

    def checkout_sale(self, **kwargs):
        self.calls.append(("checkout", kwargs))
        return self.checkout_results.pop(0)

    def quick_create_customer(self, **kwargs):
        self.calls.append(("customer", kwargs))
        return self.result

    def verify_authorizer(self, user, password):
        self.calls.append(("authorize", (user, password)))
        return self.authorizer

    def apply_sale_discount(self, **kwargs):
        self.calls.append(("discount", kwargs))
        return self.result


@pytest.fixture
def dialogs(qt_font_resources):
    instances = []
    yield instances
    for dialog in reversed(instances):
        dialog.close()
        sip.delete(dialog)
    qt_font_resources.processEvents()


def _show(dialog, dialogs, app):
    dialogs.append(dialog)
    dialog.show()
    _settle(app)
    return dialog


def _settle(app):
    for _ in range(4):
        app.processEvents()


def _button(dialog, text):
    return next(button for button in dialog.findChildren(QPushButton) if button.text() == text)


@pytest.mark.parametrize("kind", ["discount", "customer"])
@pytest.mark.parametrize("activation", ["click", "enter"])
def test_pos_validation_failure_and_retry_preserve_capture(
        qt_font_resources, dialogs, kind, activation):
    presenter = Presenter()
    dialog = (DiscountDialog(presenter, sale_id=SALE_ID) if kind == "discount"
              else QuickCustomerDialog(presenter))
    _show(dialog, dialogs, qt_font_resources)
    accepted = QSignalSpy(dialog.accepted)
    submit = _button(dialog, "Aplicar" if kind == "discount" else "Crear cliente")
    field = dialog._reason if kind == "discount" else dialog._name

    def activate():
        if activation == "click":
            QTest.mouseClick(submit, Qt.LeftButton)
        else:
            field.setFocus()
            QTest.keyClick(field, Qt.Key_Return)
        _settle(qt_font_resources)

    activate()
    assert presenter.calls == []
    assert len(accepted) == 0 and dialog.isVisible()
    if kind == "discount":
        dialog._amount.set_decimal_value(Decimal("12.50"))
        dialog._reason.setText("Ajuste autorizado")
    else:
        dialog._name.setText("Ana Pérez")
    captured = field.text()
    presenter.result = _result(False)
    activate()
    assert len(accepted) == 0 and dialog.isVisible()
    assert field.text() == captured
    presenter.result = _result()
    activate()
    assert len(accepted) == 1 and dialog.result() == QDialog.Accepted
    assert len(presenter.calls) == 2
    if kind == "discount":
        assert dialog.applied
        assert presenter.calls[-1][1] == dict(sale_id=SALE_ID,
            discount_amount=Decimal("12.50"), authorizer_user_id=None,
            reason="Ajuste autorizado")
    else:
        assert dialog.customer_id == CUSTOMER_ID
        assert presenter.calls[-1][1] == dict(display_name="Ana Pérez", phone_e164=None)


def test_discount_rejected_authorizer_never_applies(qt_font_resources, dialogs):
    presenter = Presenter()
    presenter.authorizer = (None, "Credenciales inválidas")
    dialog = _show(DiscountDialog(presenter, sale_id=SALE_ID), dialogs, qt_font_resources)
    dialog._amount.set_decimal_value(Decimal("5"))
    dialog._authorizer.setText("gerente")
    dialog._password.setText("captura")
    _button(dialog, "Aplicar").click()
    assert presenter.calls == [("authorize", ("gerente", "captura"))]
    assert not dialog.applied and dialog.isVisible()
    assert "inválidas" in dialog._status.text()


@pytest.mark.parametrize("kind", ["payment", "discount", "customer"])
def test_pos_escape_rejects_without_mutations(qt_font_resources, dialogs, kind):
    presenter = Presenter()
    dialog = _build(kind, presenter)
    _show(dialog, dialogs, qt_font_resources)
    accepted, rejected = QSignalSpy(dialog.accepted), QSignalSpy(dialog.rejected)
    QTest.keyClick(dialog, Qt.Key_Escape)
    assert len(accepted) == 0 and len(rejected) == 1
    assert presenter.calls == []


def test_payment_enter_adds_local_line_and_cancel_never_starts_checkout(qt_font_resources, dialogs):
    presenter = Presenter()
    dialog = _show(_build("payment", presenter), dialogs, qt_font_resources)
    assert not dialog._btn_confirm.isEnabled()
    dialog._reference.setFocus()
    QTest.keyClick(dialog._reference, Qt.Key_Return)
    assert dialog._lines == [("CASH", Decimal("100"), None)]
    assert dialog._btn_confirm.isEnabled()
    assert presenter.calls == []
    _button(dialog, "Cancelar").click()
    assert not dialog.completed and dialog.result() == QDialog.Rejected
    assert presenter.calls == []


def test_payment_retry_keeps_recorded_lines_and_accepts_once(
        qt_font_resources, dialogs, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: None)
    presenter = Presenter()
    presenter.checkout_results = [_result(False), _result()]
    dialog = _show(_build("payment", presenter), dialogs, qt_font_resources)
    accepted = QSignalSpy(dialog.accepted)
    dialog.set_amount(Decimal("120"))
    dialog._btn_add.click()
    assert dialog.change == Decimal("20")
    dialog._btn_confirm.click()
    assert dialog.isVisible() and len(accepted) == 0
    assert dialog._recorded == 1 and dialog._btn_confirm.isEnabled()
    dialog._list.setCurrentRow(0)
    dialog._btn_remove.click()
    assert len(dialog._lines) == 1
    dialog._btn_confirm.click()
    assert len(accepted) == 1 and dialog.completed
    assert [name for name, _kwargs in presenter.calls] == ["begin", "payment", "checkout", "checkout"]
    assert presenter.calls[1][1] == dict(sale_id=SALE_ID, method="CASH", amount=Decimal("120"), reference=None)


def test_payment_voucher_keeps_reference_and_rejects_duplicates(qt_font_resources, dialogs):
    presenter = Presenter()
    dialog = _show(_build("payment", presenter), dialogs, qt_font_resources)
    dialog.select_method("VOUCHER")
    dialog._reference.setText("VALE-PRUEBA")
    dialog._btn_add.click()
    assert dialog._lines == [("VOUCHER", Decimal("40"), "VALE-PRUEBA")]
    dialog._reference.setText("VALE-PRUEBA")
    dialog._btn_add.click()
    assert len(dialog._lines) == 1
    assert not dialog._btn_confirm.isEnabled() and presenter.calls == []


def _table(columns):
    return SimpleNamespace(rows=[["Captura"] * columns], row_ids=[SALE_ID])


def _build(kind, presenter=None):
    presenter = presenter or Presenter()
    if kind == "payment":
        return PaymentDialog(presenter, sale_id=SALE_ID, total_due=Decimal("100"))
    if kind == "discount":
        return DiscountDialog(presenter, sale_id=SALE_ID)
    if kind == "customer":
        return QuickCustomerDialog(presenter)
    if kind == "zones":
        return inventory.ManageZonesDialog(warehouse_label="Principal", table=_table(3), create_zone=lambda **kw: None)
    if kind == "movement":
        return inventory.MovementDetailDialog(header={"status": "POSTED"}, lines=_table(6),
            source_document=_table(5), audit=_table(5), can_reverse=True, reverse=lambda reason: None)
    if kind == "lot":
        return inventory.LotDetailDialog(header={"lot_code": "LOTE-PRUEBA"}, stock=_table(5),
            movements=_table(5), traceability=_table(5), can_edit=True, can_change_status=True,
            can_print=True, can_reprint=True, edit=lambda: None, change_status=lambda *args: None,
            print_label=lambda reprint: None)
    return inventory.WeightHistoryDialog(table=_table(5))


@pytest.mark.parametrize("kind", ["zones", "movement", "lot", "weight"])
def test_inventory_close_accepts_and_escape_rejects(qt_font_resources, dialogs, kind):
    dialog = _show(_build(kind), dialogs, qt_font_resources)
    accepted, rejected = QSignalSpy(dialog.accepted), QSignalSpy(dialog.rejected)
    _button(dialog, "Cerrar").click()
    assert len(accepted) == 1 and dialog.result() == QDialog.Accepted
    dialog.show()
    QTest.keyClick(dialog, Qt.Key_Escape)
    assert len(rejected) == 1 and dialog.result() == QDialog.Rejected


def test_inventory_permissions_and_callbacks_remain_authoritative(qt_font_resources, dialogs):
    dialog = _show(_build("lot"), dialogs, qt_font_resources)
    events = []
    dialog._edit = lambda: events.append("edit")
    dialog._print_label = lambda reprint: events.append(reprint)
    dialog.edit_button.click()
    dialog.print_button.click()
    dialog.reprint_button.click()
    assert events == ["edit", False, True] and dialog.isVisible()
    denied = inventory.MovementDetailDialog(header={"status": "REVERSED"}, lines=_table(6),
        source_document=_table(5), audit=_table(5), can_reverse=False, reverse=lambda reason: events.append(reason))
    _show(denied, dialogs, qt_font_resources)
    assert not denied.reverse_button.isVisible() and not denied.reverse_button.isEnabled()
    assert events == ["edit", False, True]


@pytest.mark.parametrize("kind", ["zones", "movement", "lot", "weight", "payment", "discount", "customer"])
def test_operations_use_scroll_body_and_sticky_footer(qt_font_resources, dialogs, monkeypatch, kind):
    dialog = _build(kind)
    dialogs.append(dialog)
    assert isinstance(dialog, StandardDialog)
    monkeypatch.setattr(dialog, "available_geometry", lambda: QRect(0, 0, 1024, 600))
    for index in range(20):
        dialog.content_layout().addWidget(QLabel(f"Fila adicional {index}"))
    dialog.show()
    _settle(qt_font_resources)
    assert dialog.available_geometry().contains(dialog.frameGeometry())
    assert dialog._heading.text() == dialog.windowTitle()
    footer_text = {"payment": "Confirmar y cobrar", "discount": "Aplicar", "customer": "Crear cliente"}.get(kind, "Cerrar")
    footer = _button(dialog, footer_text)
    assert footer.isVisible() and not dialog.viewport.isAncestorOf(footer)
    assert dialog.rect().contains(QRect(footer.mapTo(dialog, QPoint()), footer.size()))
    assert dialog.viewport.verticalScrollBar().maximum() > 0
    previous = footer.mapTo(dialog, QPoint())
    dialog.viewport.verticalScrollBar().setValue(dialog.viewport.verticalScrollBar().maximum())
    _settle(qt_font_resources)
    assert footer.mapTo(dialog, QPoint()) == previous
