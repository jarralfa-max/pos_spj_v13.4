"""Diseñador de tickets y carga de logo (comparativa de tickets, 2026-10-16).

Cada control del diseñador debe tener efecto en el diseño guardado (y por tanto
en los bytes, que prueba `test_ticket_design_main_vs_erp`)."""

from __future__ import annotations

import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image, ImageDraw
from PyQt5.QtCore import Qt

from backend.application.use_cases.configuracion.ticket_designer_service import (
    TicketDesignerService,
)
from backend.domain.document_output.ticket_layout import parse
from backend.infrastructure.db.schema.branding_schema import create_branding_schema


@pytest.fixture(scope="module")
def app():
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _Presenter:
    """Lo que el diseñador pide al presentador, sobre el servicio real."""

    def __init__(self, conn):
        self._service = TicketDesignerService(conn)
        self.tests = []

    def validate_ticket_layout(self, layout_json):
        return self._service.validate(layout_json)

    def ticket_preview(self, *, layout_json, document_type, paper_width_mm):
        p = self._service.preview(layout_json, document_type=document_type, branch_id=None,
                                  paper_width_mm=paper_width_mm)
        return p.png, p.warnings, None

    def ticket_print_test(self, *, layout_json, document_type):
        self.tests.append(layout_json)
        return True, "ok"

    def logo_preview(self, **kwargs):
        try:
            return self._service.preview_logo(**kwargs), None
        except ValueError as exc:
            return None, str(exc)


@pytest.fixture
def presenter():
    conn = sqlite3.connect(":memory:")
    create_branding_schema(conn)
    yield _Presenter(conn)
    conn.close()


def _item(dialog, block_type):
    for row in range(dialog._blocks.count()):
        item = dialog._blocks.item(row)
        if item.data(Qt.UserRole) == block_type:
            return row, item
    raise AssertionError(block_type)


def test_designer_controls_change_the_saved_design(app, presenter):
    from frontend.desktop.modules.configuracion.dialogs.ticket_designer_dialog import (
        TicketDesignerDialog,
    )
    dialog = TicketDesignerDialog(presenter, document_type="SALE_TICKET")
    assert dialog._preview.pixmap() is not None and not dialog._preview.pixmap().isNull()

    _row, payment = _item(dialog, "payment")
    payment.setCheckState(Qt.Unchecked)
    row, qr = _item(dialog, "qr")
    qr.setCheckState(Qt.Checked)
    assert not dialog._btn_save.isEnabled()            # QR activo sin URL
    assert "URL" in dialog._warnings.text()
    dialog._blocks.setCurrentRow(row)
    dialog._option_pages["qr"]["url"].setText("https://spj.mx/f?folio={folio}")
    assert dialog._btn_save.isEnabled()

    dialog._blocks.setCurrentRow(_item(dialog, "thanks")[0])
    dialog._move(-1)
    dialog._save()
    saved = parse(dialog.layout_json)
    assert not saved.is_enabled("payment")
    assert saved.qr_url() == "https://spj.mx/f?folio={folio}"
    order = [b.type for b in saved.blocks]
    assert order.index("thanks") < order.index("qr")


def test_print_test_sends_the_design_being_edited(app, presenter, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox

    from frontend.desktop.modules.configuracion.dialogs.ticket_designer_dialog import (
        TicketDesignerDialog,
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    dialog = TicketDesignerDialog(presenter, document_type="SWEEPSTAKES_TICKET")
    dialog._print_test()
    assert parse(presenter.tests[-1]).kind == "RAFFLE"


def test_logo_dialog_shows_before_and_after(app, presenter, tmp_path):
    from frontend.desktop.modules.configuracion.dialogs.logo_upload_dialog import (
        LogoUploadDialog,
    )
    source = tmp_path / "logo.png"
    image = Image.new("RGB", (200, 200), (235, 235, 235))
    ImageDraw.Draw(image).ellipse((40, 40, 160, 160), fill=(150, 0, 0))
    image.save(source)
    dialog = LogoUploadDialog(presenter, title="Logo", branch_scope=True)
    dialog._remove.setChecked(True)
    dialog.set_source(str(source))
    assert not dialog._before.pixmap().isNull() and not dialog._after.pixmap().isNull()
    assert dialog._save.isEnabled()
    dialog._accept()
    assert dialog.source_path == str(source) and dialog.remove_background
