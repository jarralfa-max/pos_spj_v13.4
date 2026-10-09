"""Finance/HR forms retain validation while adopting the shared dialog shell."""
from decimal import Decimal

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QEvent, QPoint, QRect, Qt
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QLineEdit, QMessageBox

from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.modules.finance.dialogs.bank_transfer_dialog import BankTransferDialog
from frontend.desktop.modules.hr.dialogs.hr_dialogs import EmployeeDialog
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics


def _build(kind):
    if kind == "finance":
        return BankTransferDialog(None, [
            ("019f327a-1694-7000-8000-000000000001", "Cuenta origen"),
            ("019f327a-1694-7000-8000-000000000002", "Cuenta destino"),
        ])
    return EmployeeDialog()


def _fill_valid(dialog, kind):
    if kind == "finance":
        dialog.target_combo.setCurrentIndex(1)
        dialog.amount_input.set_decimal_value(Decimal("125.50"))
        dialog.reference_input.setText("Captura pendiente")
        return dialog.reference_input, dialog.data()
    dialog._code.setText("EMP-PRUEBA")
    dialog._first.setText("Ana")
    dialog._last.setText("Pérez")
    return dialog._first, dialog.values()


def _settle(app):
    for _ in range(4):
        app.processEvents()


def _dispose(dialog, app):
    dialog.close()
    sip.delete(dialog)
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    _settle(app)


@pytest.mark.parametrize("kind", ["finance", "hr"])
@pytest.mark.parametrize("activation", ["click", "enter"])
def test_real_form_validates_before_accepting(qt_font_resources, monkeypatch, kind, activation):
    app = qt_font_resources
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: warnings.append(_args))
    dialog = _build(kind)
    accepted = QSignalSpy(dialog.accepted)
    try:
        dialog.show()
        _settle(app)
        box = dialog.findChild(QDialogButtonBox)
        button = box.button(QDialogButtonBox.Ok)
        for valid in (False, True):
            if valid:
                field, expected = _fill_valid(dialog, kind)
            else:
                field = dialog.reference_input if kind == "finance" else dialog._first
            if activation == "click":
                QTest.mouseClick(button, Qt.LeftButton)
            else:
                field.setFocus()
                QTest.keyClick(field, Qt.Key_Return)
            _settle(app)
            if not valid:
                assert dialog.isVisible()
                assert len(accepted) == 0
            else:
                assert dialog.result() == QDialog.Accepted
                assert len(accepted) == 1
                actual = dialog.data() if kind == "finance" else dialog.values()
                assert actual == expected
        assert len(warnings) == (1 if kind == "hr" else 0)
    finally:
        _dispose(dialog, app)


@pytest.mark.parametrize("kind", ["finance", "hr"])
def test_real_form_escape_rejects_without_accepting(qt_font_resources, kind):
    app = qt_font_resources
    dialog = _build(kind)
    accepted, rejected = QSignalSpy(dialog.accepted), QSignalSpy(dialog.rejected)
    try:
        field, expected = _fill_valid(dialog, kind)
        dialog.show()
        field.setFocus()
        _settle(app)
        QTest.keyClick(field, Qt.Key_Escape)
        _settle(app)
        assert len(accepted) == 0
        assert len(rejected) == 1
        assert dialog.result() == QDialog.Rejected
        assert (dialog.data() if kind == "finance" else dialog.values()) == expected
    finally:
        _dispose(dialog, app)


@pytest.mark.parametrize("kind", ["finance", "hr"])
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["compact", "comfortable", "touch"])
def test_real_form_keeps_footer_visible_and_capture_intact(
        qt_font_resources, monkeypatch, kind, theme, density):
    app = qt_font_resources
    manager = ThemeManager()
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, theme, density=density)
    dialog = _build(kind)
    try:
        assert isinstance(dialog, StandardDialog)
        monkeypatch.setattr(dialog, "available_geometry", lambda: QRect(0, 0, 640, 480))
        field, expected = _fill_valid(dialog, kind)
        for index in range(24):
            dialog.form.addRow(f"Dato adicional {index}", QLineEdit())
        dialog.show()
        _settle(app)
        assert not dialog.windowIcon().isNull()
        assert dialog.windowTitle() == dialog.dialog_title
        assert dialog.available_geometry().contains(dialog.frameGeometry())
        box = dialog.findChild(QDialogButtonBox)
        assert not dialog.viewport.isAncestorOf(box)
        assert dialog.rect().contains(QRect(box.mapTo(dialog, QPoint()), box.size()))
        assert box.button(QDialogButtonBox.Ok).text() == "Aceptar"
        assert box.button(QDialogButtonBox.Cancel).text() == "Cancelar"
        for button in box.buttons():
            assert button.height() >= density_metrics(density).button_height
            assert button.accessibleName() == button.text()
        scrollbar = dialog.viewport.verticalScrollBar()
        assert scrollbar.maximum() > 0
        footer_geometry = box.geometry()
        scrollbar.setValue(scrollbar.maximum())
        _settle(app)
        assert box.geometry() == footer_geometry
        assert (dialog.data() if kind == "finance" else dialog.values()) == expected
        assert field.text()
    finally:
        _dispose(dialog, app)
