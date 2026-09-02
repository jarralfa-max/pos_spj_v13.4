"""`EmpresaPage` installation-branch pin widget smoke test, against the
REAL `create_configuracion_view()` factory and real (in-memory) SQLite —
first real caller of `SetInstallationBranchUseCase` (`backend/application/
use_cases/set_installation_branch_use_case.py`). Migrates the terminal-pin
write path (`configuraciones.sucursal_instalacion_id`) off legacy
`modulos/configuracion.py`, which previously called `CompanyProfileService
.set_installation_branch()` directly from two separate legacy call sites.

`configuraciones` and `sucursales.activa` are both base-schema (`migrations/
m000_base_schema.py`), so unlike `test_usuarios_roles_page.py` this file
needs no extra migration on top of `make_db()`.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from backend.application.configuracion.permissions import ConfiguracionPermissions  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402
from frontend.desktop.modules.configuracion.configuracion_routes import (  # noqa: E402
    create_configuracion_view,
)
from repositories.config_repository import ConfigRepository  # noqa: E402
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
    return {p for p in vars(ConfiguracionPermissions).values() if isinstance(p, str)}


def _view(app, conn):
    class _FakeContainer:
        db = conn
        session = _FakeSession(_all_permissions())

    return create_configuracion_view(_FakeContainer())


@pytest.fixture
def conn():
    return make_db()


def _branch_ids(conn) -> list[str]:
    rows = conn.execute("SELECT id FROM sucursales WHERE COALESCE(activa, 1) = 1").fetchall()
    return [str(row[0]) for row in rows]


class TestEmpresaPageInstallationBranch:
    def test_summary_shows_the_base_schema_seeded_pin(self, app, conn):
        # m000_base_schema.py seeds `configuraciones.sucursal_instalacion_id`
        # to the install branch (INSTALL_BRANCH_UUID, named "Principal") on
        # every fresh install — a born-clean DB is never actually unpinned.
        view = _view(app, conn)
        view.show_route("config_empresa")
        page = view._pages["config_empresa"]

        assert page.installation_summary_label.text() == "📍 Esta instalación: Principal"

    def test_summary_shows_unassigned_when_pin_is_absent(self, app, conn):
        conn.execute("DELETE FROM configuraciones WHERE clave = 'sucursal_instalacion_id'")
        conn.commit()

        view = _view(app, conn)
        view.show_route("config_empresa")
        page = view._pages["config_empresa"]

        assert "sin sucursal asignada" in page.installation_summary_label.text()

    def test_anchor_installation_button_present(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_empresa")
        page = view._pages["config_empresa"]

        assert page.anchor_installation_button.text() == "Anclar sucursal de esta instalación"

    def test_set_installation_branch_persists_and_updates_summary(self, app, conn):
        branch_ids = _branch_ids(conn)
        assert branch_ids, "seed data must include at least one active branch"
        branch_id = branch_ids[0]

        view = _view(app, conn)
        view.show_route("config_empresa")
        page = view._pages["config_empresa"]
        presenter = page._presenter

        ok, message = presenter.set_installation_branch(branch_id)
        assert ok is True, message

        page._reload_installation_summary()
        assert "Esta instalación:" in page.installation_summary_label.text()

        anchored = ConfigRepository(conn).get_installation_branch()
        assert anchored is not None and anchored[0] == branch_id

    def test_set_installation_branch_rejects_unknown_branch(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_empresa")
        presenter = view._pages["config_empresa"]._presenter

        ok, message = presenter.set_installation_branch(new_uuid())
        assert ok is False
