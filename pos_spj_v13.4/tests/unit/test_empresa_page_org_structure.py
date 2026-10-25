"""«Estructura organizacional» en Empresa y sucursales (auditoría enterprise,
Fase 1), contra la composición REAL (`build_configuracion_view`) y SQLite en
memoria con la migración 351 aplicada."""

from __future__ import annotations

import importlib
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from backend.application.configuracion.permissions import ConfiguracionPermissions as P  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402
from frontend.desktop.modules.configuracion.configuracion_routes import (  # noqa: E402
    build_configuracion_view,
)
from tests.integration._born_clean_db import make_db  # noqa: E402

_351 = importlib.import_module("migrations.standalone.351_organizational_structure")
EMPRESA = "01a00000-0000-7000-8000-0000000000e1"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _Session:
    def __init__(self, permissions) -> None:
        self.user_id = new_uuid()
        self.is_active = True
        self.active_branch_id = "01900000-0000-7000-8000-000000000001"
        self._permissions = set(permissions)

    def tiene_permiso(self, code: str) -> bool:
        return code in self._permissions

    def es_admin(self) -> bool:
        return False


def _all() -> set:
    return {p for p in vars(P).values() if isinstance(p, str)}


@pytest.fixture
def conn():
    db = make_db()
    db.execute("INSERT INTO company_profiles (id, legal_name, default_currency,"
               " default_timezone, default_locale, created_at, updated_at)"
               " VALUES (?, 'JUANIS', 'MXN', 'America/Mexico_City', 'es-MX', '2026-01-01',"
               " '2026-01-01')", (EMPRESA,))
    db.commit()
    _351.run(db)
    return db


_VIEWS = []   # la página es hija de la vista: sin referencia, Qt la destruye


def _page(conn, permissions):
    view = build_configuracion_view(connection=conn, session_context=_Session(permissions))
    _VIEWS.append(view)
    view.show_route("config_empresa")
    return view._pages["config_empresa"]


def test_tree_lists_backfilled_branch_and_new_units_indented(app, conn):
    page = _page(conn, _all())
    assert not page.org_card.isHidden()
    assert page.org_table.rowCount() == 1   # «Principal», sembrada por el esquema base
    assert "Principal" in page.org_table.item(0, 0).text()
    assert "(esta instalación)" in page.org_table.item(0, 0).text()

    presenter = page._presenter
    ok, message = presenter.create_org_unit(unit_type="REGION", code="BAJIO", name="Bajío")
    assert ok, message
    region = conn.execute("SELECT id FROM org_units WHERE code='BAJIO'").fetchone()[0]
    ok, message = presenter.move_org_unit("01900000-0000-7000-8000-000000000001", region)
    assert ok, message
    page._reload_org_tree()
    textos = [page.org_table.item(r, 0).text() for r in range(page.org_table.rowCount())]
    assert textos[0] == "Bajío" and textos[1].startswith("    └ Principal")


def test_card_is_hidden_without_view_permission(app, conn):
    page = _page(conn, _all() - {P.ORGANIZACION_VIEW})
    assert page.org_card.isHidden()
    assert page._presenter.org_tree() == []


def test_command_buttons_follow_permissions(app, conn):
    page = _page(conn, {P.EMPRESA_VIEW, P.ORGANIZACION_VIEW})
    assert not page.org_card.isHidden()
    for boton in (page.new_unit_button, page.edit_unit_button, page.move_unit_button,
                  page.unit_capabilities_button, page.close_unit_button):
        assert boton.isHidden()
    ok, message = page._presenter.create_org_unit(unit_type="REGION", code="X1", name="X")
    assert not ok and "permiso" in message


def test_capability_dialog_orders_changes_so_pos_goes_first(app):
    from frontend.desktop.modules.configuracion.dialogs.org_structure_dialogs import (
        OrgUnitCapabilitiesDialog,
    )
    dlg = OrgUnitCapabilitiesDialog(unit_name="Centro",
                                    current=["SALES", "POS", "CASH", "INVENTORY"])
    for code in ("SALES", "POS", "CASH"):
        dlg.capabilities.boxes[code].setChecked(False)
    dlg.capabilities.boxes["BI"].setChecked(True)
    assert dlg.changes() == [("BI", True), ("POS", False), ("SALES", False), ("CASH", False)]
