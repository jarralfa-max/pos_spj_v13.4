"""Visibilidad de las secciones de Configuración en la shell VIVA.

Hallazgo de la re-auditoría del 2026-10-04 sobre una copia de la base real: la
shell armaba la vista con `ConfiguracionModuleActivator`, que nunca pasaba
`has_permission`, así que un usuario `solo_lectura` (sólo `CONFIGURACION.ver`)
veía las once secciones —usuarios, auditoría, integraciones— y el presenter
tampoco revalidaba las lecturas. Las pruebas de páginas no lo veían porque
usaban otra fábrica, la única que sí filtraba.

Estas pruebas recorren el activador real, el mismo que construye la shell.
"""

from __future__ import annotations

import importlib
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from PyQt5.QtCore import Qt  # noqa: E402

from backend.application.configuracion.permissions import ConfiguracionPermissions  # noqa: E402
from backend.domain.settings.exceptions import ConfigurationPermissionDeniedError  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402
from frontend.desktop.components import ViewState  # noqa: E402
from frontend.desktop.modules.configuracion.shell_registration import (  # noqa: E402
    CONFIGURACION_VIEW_FACTORY_ID,
    ConfiguracionModuleActivator,
)
from tests.integration._born_clean_db import make_db  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    connection = make_db()
    importlib.import_module("migrations.standalone.047_v13_schema").up(connection)
    yield connection
    connection.close()


class _Session:
    def __init__(self, permissions) -> None:
        self.user_id = new_uuid()
        self.is_active = True
        self.active_branch_id = "branch-1"
        self._permissions = set(permissions)

    def tiene_permiso(self, code: str) -> bool:
        return code in self._permissions


class _Registry:
    def register(self, factory_id, factory):
        self.factory_id, self.factory = factory_id, factory


def _live_view(conn, permissions):
    registry = _Registry()
    ConfiguracionModuleActivator(
        connection=conn, view_factory_registry=registry, session_context=_Session(permissions),
    ).activate(None)
    assert registry.factory_id == CONFIGURACION_VIEW_FACTORY_ID
    return registry.factory()


def _sidebar_ids(view):
    return [view.sidebar.item(i).data(Qt.UserRole) for i in range(view.sidebar.count())]


def test_read_only_user_sees_only_the_general_section(app, conn):
    view = _live_view(conn, {ConfiguracionPermissions.GENERAL_VIEW})

    assert _sidebar_ids(view) == ["config_general"]


def test_route_without_permission_is_not_built(app, conn):
    view = _live_view(conn, {ConfiguracionPermissions.GENERAL_VIEW})

    view.show_route("config_usuarios_roles")

    assert "config_usuarios_roles" not in view._pages
    assert view.stack.currentWidget().property("state") == ViewState.NO_PERMISSION


def test_presenter_revalidates_reads_without_permission(app, conn):
    view = _live_view(conn, {ConfiguracionPermissions.GENERAL_VIEW})
    presenter = view._presenter

    with pytest.raises(ConfigurationPermissionDeniedError):
        presenter.load_page("config_usuarios_roles")
    for reader in (presenter.list_users, presenter.list_roles, presenter.audit_log_rows,
                   presenter.list_integration_definitions, presenter.list_feature_flags):
        with pytest.raises(ConfigurationPermissionDeniedError):
            reader()


def test_users_page_hides_roles_and_audit_cards_without_their_permissions(app, conn):
    view = _live_view(conn, {
        ConfiguracionPermissions.GENERAL_VIEW, ConfiguracionPermissions.USUARIOS_VIEW})

    view.show_route("config_usuarios_roles")
    page = view._pages["config_usuarios_roles"]

    assert page.roles_empty.property("state") == ViewState.NO_PERMISSION
    assert page.audit_empty.property("state") == ViewState.NO_PERMISSION
    assert not page.roles_table.isVisibleTo(page)
    assert not page.audit_table.isVisibleTo(page)


def test_full_grant_sees_every_section(app, conn):
    every = {p for p in vars(ConfiguracionPermissions).values() if isinstance(p, str)}
    view = _live_view(conn, every)

    assert len(_sidebar_ids(view)) == 11
