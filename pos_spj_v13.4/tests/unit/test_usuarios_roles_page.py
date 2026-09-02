"""`UsuariosRolesPage` widget smoke tests, against the REAL
`create_configuracion_view()` factory and real (in-memory) SQLite —
mirrors the "verified end-to-end through the real factory" discipline
every prior Configuración CRUD round in this track used. This is the
first real caller of the dormant "FASE 6" `SaveUserUseCase`/
`SetUserActiveUseCase` canonical use-case layer (`backend/application/
use_cases/`) — see `usuarios_roles_page.py`'s module docstring.

`tests/integration/_born_clean_db.py::make_db()` doesn't run migration
047 (which adds `usuarios.email`/`empleado_id`/etc.) — a pre-existing
gap in that shared helper, confirmed unrelated to this round. Scoped
locally here (not touching the shared helper, to avoid any risk to the
~15 other test files that already depend on its exact current
behavior): `_conn()` runs `make_db()` then applies migration 047 on top,
matching the real production migration chain this page's application
services (`UserManagementService`, already live-tested elsewhere)
actually run against.
"""

from __future__ import annotations

import importlib
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

import bcrypt  # noqa: E402

from backend.application.configuracion.permissions import ConfiguracionPermissions  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402
from frontend.desktop.modules.configuracion.configuracion_routes import (  # noqa: E402
    create_configuracion_view,
)
from tests.integration._born_clean_db import make_db  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeSession:
    def __init__(self, permissions=()) -> None:
        self.user_id = new_uuid()
        self.is_active = True
        self.active_branch_id = "branch-1"
        self._permissions = set(permissions)

    def tiene_permiso(self, code: str) -> bool:
        return code in self._permissions

    def es_admin(self) -> bool:
        return False


def _all_permissions() -> set:
    return {p for p in vars(ConfiguracionPermissions).values() if isinstance(p, str)} | {
        "CONFIG_SEGURIDAD.editar", "USUARIOS.desbloquear",
    }


def _view(app, conn):
    class _FakeContainer:
        db = conn
        session = _FakeSession(_all_permissions())

    return create_configuracion_view(_FakeContainer())


@pytest.fixture
def conn():
    connection = make_db()
    module = importlib.import_module("migrations.standalone.047_v13_schema")
    module.up(connection)
    return connection


def _first_branch_id(conn) -> str:
    row = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()
    return str(row[0])


class TestUsuariosRolesPageStructure:
    def test_builds_via_the_real_route(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_usuarios_roles")
        page = view._pages["config_usuarios_roles"]

        assert page.table.accessibleName() == "Listado de Usuarios y Roles"
        assert page.roles_table.accessibleName() == "Roles del sistema"
        assert page.audit_table.accessibleName() == "Últimas acciones registradas en el sistema"

    def test_buttons_present(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_usuarios_roles")
        page = view._pages["config_usuarios_roles"]

        assert page.new_user_button.text() == "Nuevo usuario"
        assert page.unlock_user_button.text() == "Desbloquear"
        assert page.new_role_button.text() == "Nuevo rol"


class TestUsuariosRolesPageLoadsRealData:
    def test_roles_table_loads_real_roles(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_usuarios_roles")
        page = view._pages["config_usuarios_roles"]

        # seeded by m000_base_schema.py's default role catalog
        assert page.roles_table.rowCount() > 0


class TestUsuariosRolesFullLoop:
    def test_create_edit_deactivate_reactivate_user(self, app, conn):
        branch_id = _first_branch_id(conn)
        view = _view(app, conn)
        view.show_route("config_usuarios_roles")
        page = view._pages["config_usuarios_roles"]
        presenter = page._presenter

        rows_before = page.table.rowCount()
        ok, message = presenter.create_user(
            username="ana", full_name="Ana", email="ana@x.mx", password="secreto123",
            role="gerente", branch_id=branch_id, employee_id="", active=True,
        )
        assert ok is True, message

        page.reload()
        assert page.table.rowCount() == rows_before + 1

        row = conn.execute("SELECT id, password_hash FROM usuarios WHERE usuario='ana'").fetchone()
        user_id, stored_hash = row["id"], row["password_hash"]
        assert bcrypt.checkpw(b"secreto123", stored_hash.encode())

        # edit without touching the password — hash must remain unchanged
        ok, message = presenter.update_user(
            user_id=user_id, username="ana", full_name="Ana Actualizada", email="ana@x.mx",
            password="", role="gerente", branch_id=branch_id, employee_id="", active=True,
        )
        assert ok is True, message
        row = conn.execute("SELECT nombre, password_hash FROM usuarios WHERE id=?", (user_id,)).fetchone()
        assert row["nombre"] == "Ana Actualizada"
        assert row["password_hash"] == stored_hash

        ok, message = presenter.set_user_active(user_id=user_id, active=False)
        assert ok is True, message
        assert conn.execute("SELECT activo FROM usuarios WHERE id=?", (user_id,)).fetchone()["activo"] == 0

        ok, message = presenter.set_user_active(user_id=user_id, active=True)
        assert ok is True, message
        assert conn.execute("SELECT activo FROM usuarios WHERE id=?", (user_id,)).fetchone()["activo"] == 1

    def test_create_user_requires_password(self, app, conn):
        branch_id = _first_branch_id(conn)
        view = _view(app, conn)
        view.show_route("config_usuarios_roles")
        presenter = view._pages["config_usuarios_roles"]._presenter

        ok, message = presenter.create_user(
            username="sinpass", role="gerente", branch_id=branch_id, password="",
        )
        assert ok is False

    def test_unlock_user_resets_failed_attempts(self, app, conn):
        branch_id = _first_branch_id(conn)
        view = _view(app, conn)
        view.show_route("config_usuarios_roles")
        page = view._pages["config_usuarios_roles"]
        presenter = page._presenter

        ok, message = presenter.create_user(
            username="lockeduser", password="secreto123", role="gerente", branch_id=branch_id,
        )
        assert ok is True, message
        user_id = conn.execute("SELECT id FROM usuarios WHERE usuario='lockeduser'").fetchone()["id"]
        conn.execute(
            "UPDATE usuarios SET intentos_fallidos=5, bloqueado_hasta=? WHERE id=?",
            ("2099-01-01 00:00:00", user_id),
        )
        conn.commit()

        ok, message = presenter.unlock_user(user_id)
        assert ok is True, message
        row = conn.execute(
            "SELECT intentos_fallidos, bloqueado_hasta FROM usuarios WHERE id=?", (user_id,)
        ).fetchone()
        assert row["intentos_fallidos"] == 0
        assert row["bloqueado_hasta"] is None

    def test_create_and_edit_role(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_usuarios_roles")
        page = view._pages["config_usuarios_roles"]
        presenter = page._presenter

        ok, message = presenter.save_role(name="supervisor_turno", description="Supervisor de turno")
        assert ok is True, message

        page.reload()
        roles = presenter.list_roles()
        role = next(r for r in roles if r.name == "supervisor_turno")

        ok, message = presenter.save_role(role_id=role.id, name=role.name, description="Actualizado")
        assert ok is True, message
        updated = next(r for r in presenter.list_roles() if r.id == role.id)
        assert updated.description == "Actualizado"

    def test_auditoria_card_has_no_action_buttons(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_usuarios_roles")
        page = view._pages["config_usuarios_roles"]

        assert not hasattr(page, "new_audit_button")
        assert not hasattr(page, "edit_audit_button")
