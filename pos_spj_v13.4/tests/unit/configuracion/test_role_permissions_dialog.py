"""Diálogo de permisos de un rol: junta lo marcado y desmarcado, nada más."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from backend.application.security.role_permission_matrix import (  # noqa: E402
    ModulePermissions,
    PermissionOption,
    RolePermissionMatrix,
)
from frontend.desktop.modules.configuracion.dialogs.role_permissions_dialog import (  # noqa: E402
    RolePermissionsDialog,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _matrix(mode="EDITABLE", granted=("POS.ver",)):
    modules = (
        ModulePermissions("POS", "Punto de venta", (
            PermissionOption("POS.ver", "Ver"), PermissionOption("POS.cobrar", "Cobrar"))),
        ModulePermissions("CAJA", "Caja", (PermissionOption("CAJA.ver", "Ver"),)),
    )
    return RolePermissionMatrix("r1", "cajero", mode, "nota", frozenset(granted), modules)


def test_only_what_changed_is_returned(app):
    dlg = RolePermissionsDialog(matrix=_matrix())
    assert dlg.changes() == {}
    dlg._boxes["POS.cobrar"].setChecked(True)
    dlg._boxes["POS.ver"].setChecked(False)
    assert dlg.changes() == {"POS.cobrar": True, "POS.ver": False}
    dlg._boxes["POS.ver"].setChecked(True)
    assert dlg.changes() == {"POS.cobrar": True}


def test_changes_survive_switching_modules_and_check_all(app):
    dlg = RolePermissionsDialog(matrix=_matrix())
    dlg.module.set_current_id("CAJA")
    dlg.check_all_button.click()
    dlg.module.set_current_id("POS")
    dlg.uncheck_all_button.click()
    assert dlg.changes() == {"CAJA.ver": True, "POS.ver": False}
    assert "1 por otorgar, 1 por retirar" in dlg.summary.text()


def test_the_owner_role_cannot_uncheck_what_it_has(app):
    dlg = RolePermissionsDialog(matrix=_matrix(mode="GRANT_ONLY"))
    assert not dlg._boxes["POS.ver"].isEnabled()
    assert dlg._boxes["POS.cobrar"].isEnabled()
    dlg.uncheck_all_button.click()
    assert dlg.changes() == {}
