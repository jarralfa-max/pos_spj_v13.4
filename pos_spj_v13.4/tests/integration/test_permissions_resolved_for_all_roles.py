import os
import sqlite3

import pytest

from core.permissions import verificar_acceso_modulo
from core.session_context import SessionContext
from core.services.configuration_settings_service import PermissionQueryService
from repositories.config_repository import ConfigRepository

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE roles(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE, descripcion TEXT);
        CREATE TABLE usuarios(id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, nombre TEXT, rol TEXT, sucursal_id INTEGER, activo INTEGER DEFAULT 1);
        CREATE TABLE rol_permisos(rol_id INTEGER, modulo TEXT, accion TEXT, permitido INTEGER);
        INSERT INTO roles(nombre, descripcion) VALUES
            ('cajero', 'Caja'),
            ('cajero_sin_pos', 'Caja sin POS'),
            ('gerente', 'Gerencia');
        INSERT INTO usuarios(id, usuario, nombre, rol, sucursal_id, activo) VALUES
            (1, 'admin', 'Admin', 'admin', 1, 1),
            (2, 'super', 'Super', 'superadmin', 1, 1),
            (3, 'cajero_ok', 'Cajero OK', 'cajero', 1, 1),
            (4, 'cajero_no', 'Cajero NO', 'cajero_sin_pos', 1, 1),
            (5, 'gerente', 'Gerente', 'gerente', 1, 1),
            (6, 'cajero_upper', 'Cajero Upper', 'CAJERO', 1, 1),
            (7, 'cajero_spaces', 'Cajero Spaces', ' cajero ', 1, 1);
        INSERT INTO rol_permisos(rol_id, modulo, accion, permitido) VALUES
            (1, 'POS', 'ver', 1),
            (3, 'INVENTARIO', 'ver', 1),
            (3, 'CAJA', 'ver', 1);
        """
    )
    return conn


class _Container:
    def __init__(self, permissions: set[str]) -> None:
        self.session = SessionContext()
        self.session.set_user({"id": 999, "username": "test", "rol": "operador"})
        self.session.set_permisos(permissions)


def _resolved_permissions() -> tuple[set[str], set[str], PermissionQueryService]:
    query = PermissionQueryService(ConfigRepository(_connection()))
    cajero_permissions = query.permission_codes_for_user(3, 1)
    gerente_permissions = query.permission_codes_for_user(5, 1)
    return cajero_permissions, gerente_permissions, query


def _button(menu, code: str):
    from PyQt5.QtWidgets import QPushButton

    for btn in menu.findChildren(QPushButton):
        if str(btn.property("modulo_codigo") or "") == code:
            return btn
    raise AssertionError(f"Missing menu button {code}")


def test_permission_query_resolves_all_roles_without_role_text_visibility() -> None:
    cajero_permissions, gerente_permissions, query = _resolved_permissions()

    assert query.permission_codes_for_user(1, 1) == {"*"}
    assert query.permission_codes_for_user(2, 1) == {"*"}
    assert cajero_permissions == {"POS.VER"}
    assert query.permission_codes_for_user(4, 1) == set()
    assert gerente_permissions == {"INVENTARIO.VER", "CAJA.VER"}
    assert query.permission_codes_for_user(6, 1) == {"POS.VER"}
    assert query.permission_codes_for_user(7, 1) == {"POS.VER"}

    session = SessionContext()
    session.set_user({"id": 3, "username": "cajero_ok", "rol": " cajero "})
    session.set_permisos(cajero_permissions)
    assert session._permisos == cajero_permissions
    assert verificar_acceso_modulo(_Container(cajero_permissions), "POS", None) is True
    assert verificar_acceso_modulo(_Container(cajero_permissions), "CAJA", None) is False


def test_menu_session_and_navigation_share_resolved_permissions_when_qt_available() -> None:
    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError as exc:
        pytest.skip(f"PyQt runtime unavailable: {exc}")

    from interfaz.menu_lateral import MenuLateral

    cajero_permissions, gerente_permissions, _query = _resolved_permissions()
    session = SessionContext()
    session.set_user({"id": 3, "username": "cajero_ok", "rol": " cajero "})
    session.set_permisos(cajero_permissions)

    app = QApplication.instance() or QApplication([])
    menu = MenuLateral()
    menu.set_permisos(cajero_permissions, " cajero ")
    assert session._permisos == menu._permisos
    assert _button(menu, "POS").isVisible()
    assert not _button(menu, "CAJA").isVisible()

    menu.set_permisos(gerente_permissions, "gerente")
    assert _button(menu, "INVENTARIO").isVisible()
    assert _button(menu, "CAJA").isVisible()
    assert not _button(menu, "POS").isVisible()

    menu.set_permisos({"*"}, "admin")
    assert _button(menu, "POS").isVisible()
    assert _button(menu, "CONFIG_SEGURIDAD").isVisible()
    assert _button(menu, "CONFIG_MODULOS").isVisible()

    menu.deleteLater()
    app.processEvents()
