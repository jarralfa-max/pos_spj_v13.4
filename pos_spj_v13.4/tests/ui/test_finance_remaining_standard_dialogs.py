"""Remaining finance dialogs keep their capture and read-only contracts."""
from decimal import Decimal
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QPoint, QRect, QSettings, Qt
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QLineEdit, QMessageBox, QPushButton

from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.components.tables import StandardTable
from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.dialogs.table_dialog import TableDialog
from frontend.desktop.modules.finance.suppliers.dialogs import supplier_dialogs as forms
from frontend.desktop.modules.finance.suppliers.pages.supplier_detail_dialog import SupplierDetailDialog
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics


FORM_KINDS = ("form", "contact", "bank", "terms", "block", "reason", "address", "evaluation")
ALL_KINDS = (*FORM_KINDS, "profile", "journal", "detail")
SUPPLIER_ID = "019f327a-1694-7000-8000-000000000001"
CONTACT_ID = "019f327a-1694-7000-8000-000000000002"


def _settle(app):
    for _ in range(4):
        app.processEvents()


@pytest.fixture
def desktop(qt_font_resources, ui_tmp_path, monkeypatch):
    app = qt_font_resources
    manager = ThemeManager(QSettings(str(ui_tmp_path / "finance-dialogs.ini"), QSettings.IniFormat))
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, "light", density="comfortable")
    return app, manager


def _presenter():
    presenter = Mock()
    presenter.supplier_header.return_value = {
        "supplier_code": "PRV-000001", "legal_name": "Proveedor de prueba",
        "status_label": "Activo", "status": "ACTIVE", "risk_label": "Bajo",
        "risk_level": "LOW", "counts": {"contacts": 1, "addresses": 1},
    }
    presenter.contacts.return_value = SimpleNamespace(
        rows=[["Ana", "Compras", "Encargada", "+525511112222", "", "", "Sí"]],
        row_ids=[CONTACT_ID],
    )
    for name in ("addresses", "bank_accounts", "products", "documents"):
        getattr(presenter, name).return_value = SimpleNamespace(rows=[], row_ids=[])
    presenter.terms_summary.return_value = "Crédito a 15 días"
    presenter.risk.return_value = {"label": "Bajo", "causes": []}
    return presenter


def _build(kind):
    classes = {
        "form": forms.SupplierFormDialog, "contact": forms.SupplierContactDialog,
        "bank": forms.SupplierBankAccountDialog, "terms": forms.SupplierTermsDialog,
        "block": forms.SupplierBlockDialog, "reason": forms.SupplierReasonDialog,
        "address": forms.SupplierAddressDialog, "evaluation": forms.SupplierEvaluationDialog,
    }
    if kind in classes:
        return classes[kind]()
    if kind == "profile":
        return TableDialog(None, "Perfil contable", [ColumnSpec("Rol"), ColumnSpec("Cuenta")],
                           SimpleNamespace(rows=[["Ingreso", "401-01"]], row_ids=[]))
    if kind == "journal":
        return TableDialog(None, "Detalle del asiento",
                           [ColumnSpec("Cuenta"), ColumnSpec("Nombre"), ColumnSpec("Concepto"),
                            ColumnSpec("Debe", "numeric"), ColumnSpec("Haber", "numeric")],
                           SimpleNamespace(rows=[["101-01", "Caja", "Venta", "125.50", "0.00"]],
                                           row_ids=[]))
    return SupplierDetailDialog(_presenter(), SUPPLIER_ID)


def _fill(dialog, kind):
    if kind == "form":
        dialog._legal.setText("Distribuidora del Valle")
        dialog._trade.setText("Del Valle")
        dialog._rfc.set_value("DVA010203XY1")
    elif kind == "contact":
        dialog._name.setText("Ana Pérez")
        dialog._type.set_current_id("PURCHASING")
    elif kind == "bank":
        dialog._bank.setText("Banco de prueba")
        dialog._holder.setText("Distribuidora del Valle")
        dialog._clabe.setText("012345678901231234")
    elif kind == "terms":
        dialog._payment_mode.set_current_id("CREDIT")
        dialog._credit_days.setValue(15)
        dialog._credit_limit.set_decimal_value(Decimal("125.50"))
    elif kind in ("block", "reason"):
        if kind == "block":
            dialog._type.set_current_id("PAYMENT_BLOCK")
        dialog._reason.setPlainText("Motivo de prueba")
    elif kind == "address":
        dialog._type.set_current_id("FISCAL")
        dialog._label.setText("Bodega Norte")
        dialog._address.set_value("Av. Juárez 100")
    elif kind == "evaluation":
        dialog._period.set_month_text("2026-10")
        dialog._scores["QUALITY"].setValue(80)
        dialog._comments.setPlainText("Entrega verificada")
    return dialog.values()


def _close_button(dialog, kind):
    if kind == "detail":
        return next(button for button in dialog.findChildren(QPushButton) if button.text() == "Cerrar")
    return dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Close)


@pytest.mark.parametrize("kind", FORM_KINDS)
@pytest.mark.parametrize("activation", ["click", "enter"])
def test_supplier_capture_validates_then_accepts_once(desktop, monkeypatch, kind, activation):
    app, _ = desktop
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    dialog = _build(kind)
    accepted = QSignalSpy(dialog.accepted)
    try:
        dialog.show()
        _settle(app)
        button = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok)
        if kind != "evaluation":
            QTest.mouseClick(button, Qt.LeftButton)
            _settle(app)
            assert dialog.isVisible() and len(accepted) == 0
            assert len(warnings) == 1
        expected = _fill(dialog, kind)
        if activation == "click":
            QTest.mouseClick(button, Qt.LeftButton)
        else:
            button.setFocus()
            assert button.hasFocus()
            QTest.keyClick(button, Qt.Key_Return)
        _settle(app)
        assert dialog.result() == QDialog.Accepted
        assert len(accepted) == 1 and not dialog.isVisible()
        assert dialog.values() == expected
    finally:
        sip.delete(dialog)


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_finance_dialog_escape_preserves_data_and_rejects(desktop, kind):
    app, _ = desktop
    dialog = _build(kind)
    expected = _fill(dialog, kind) if kind in FORM_KINDS else None
    accepted, rejected = QSignalSpy(dialog.accepted), QSignalSpy(dialog.rejected)
    try:
        dialog.show()
        _settle(app)
        QTest.keyClick(dialog, Qt.Key_Escape)
        _settle(app)
        assert dialog.result() == QDialog.Rejected
        assert len(accepted) == 0 and len(rejected) == 1
        if expected is not None:
            assert dialog.values() == expected
    finally:
        sip.delete(dialog)


@pytest.mark.parametrize("kind", ["profile", "journal", "detail"])
def test_read_only_close_keeps_existing_result(desktop, kind):
    app, _ = desktop
    dialog = _build(kind)
    try:
        dialog.show()
        _settle(app)
        QTest.mouseClick(_close_button(dialog, kind), Qt.LeftButton)
        _settle(app)
        assert not dialog.isVisible()
        # Los diálogos de sólo lectura de Finanzas cierran con «Cerrar» (rechazo).
        assert dialog.result() == (QDialog.Accepted if kind == "detail" else QDialog.Rejected)
        if kind != "detail":
            table = dialog.findChild(StandardTable)
            assert table.rowCount() == 1
            assert table.item(0, 0).text() == ("Ingreso" if kind == "profile" else "101-01")
    finally:
        sip.delete(dialog)


def test_supplier_detail_keeps_lazy_tabs_and_uuid_selection(desktop):
    presenter = _presenter()
    dialog = SupplierDetailDialog(presenter, SUPPLIER_ID)
    try:
        presenter.supplier_header.assert_called_once_with(SUPPLIER_ID)
        presenter.contacts.assert_not_called()
        dialog._tabs.setCurrentIndex(1)
        dialog._contacts_table.selectRow(0)
        assert dialog._contacts_table.selected_row_id() == CONTACT_ID
        dialog._tabs.setCurrentIndex(0)
        dialog._tabs.setCurrentIndex(1)
        presenter.contacts.assert_called_once_with(SUPPLIER_ID)
        for index in range(2, dialog._tabs.count()):
            dialog._tabs.setCurrentIndex(index)
        for name in ("addresses", "bank_accounts", "products", "documents", "terms_summary", "risk"):
            getattr(presenter, name).assert_called_once_with(SUPPLIER_ID)
        assert dialog._terms_label.text() == "Crédito a 15 días"
    finally:
        sip.delete(dialog)


@pytest.mark.parametrize("kind", ALL_KINDS)
@pytest.mark.parametrize("theme,density", [("light", "compact"), ("light", "comfortable"), ("dark", "touch")])
def test_finance_shell_keeps_actions_reachable_on_small_screen(desktop, monkeypatch, kind, theme, density):
    app, manager = desktop
    manager.apply(app, theme, density=density)
    dialog = _build(kind)
    try:
        assert isinstance(dialog, StandardDialog)
        monkeypatch.setattr(dialog, "available_geometry", lambda: QRect(0, 0, 640, 480))
        expected = _fill(dialog, kind) if kind in FORM_KINDS else None
        dialog.show()
        _settle(app)
        assert dialog.available_geometry().contains(dialog.frameGeometry())
        if kind in FORM_KINDS:
            buttons = dialog.findChild(QDialogButtonBox).buttons()
        else:
            buttons = [_close_button(dialog, kind)]
        positions = []
        for button in buttons:
            assert not dialog.viewport.isAncestorOf(button)
            position = QRect(button.mapTo(dialog, QPoint()), button.size())
            assert dialog.rect().contains(position)
            assert not button.visibleRegion().isEmpty()
            assert button.height() >= density_metrics(density).button_height
            assert button.accessibleName() == button.text()
            positions.append(position)
        scrollbar = dialog.viewport.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        _settle(app)
        assert positions == [QRect(button.mapTo(dialog, QPoint()), button.size()) for button in buttons]
        if expected is not None:
            assert dialog.values() == expected
        artifact_path = os.environ.get("SPJ_DIALOG_VISUAL_ARTIFACTS")
        if artifact_path:
            destination = Path(artifact_path)
            destination.mkdir(parents=True, exist_ok=True)
            assert dialog.grab().save(str(destination / f"finance-{kind}-{theme}-{density}-640x480.png"))
    finally:
        sip.delete(dialog)
